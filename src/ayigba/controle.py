"""Contrôle des bâtiments détectés par IA (source « google_25d ») : indices de suspicion, sans réseau.

Ce module ne mesure PAS la vérité : aucune vérité terrain n'est disponible. Il calcule des indices géométriques
(surface, forme, hauteur, voisinage, couverture de présence) qui rendent un bâtiment détecté plus ou moins plausible.
Le score est une somme de poids documentés (`POIDS`), un outil de tri : il n'est pas une probabilité d'erreur.
Un bâtiment réel peut avoir un score élevé (un hangar, une cour couverte), un faux positif peut avoir un score nul.

Les fonctions d'indicateurs sont pures (géométrie en mètres dans le repère local) pour être testées avec des données
synthétiques. `controler` lit les fichiers d'un projet ; `rendre_planche` dessine l'échantillon (matplotlib requis).
"""
from __future__ import annotations

import json
import math
import re
from collections import Counter
from pathlib import Path

import numpy as np
import shapely
from shapely import STRtree
from shapely.ops import unary_union

from . import batiments25d
from .geo import LocalFrame, read_features
from .mesh import rng_for
from .stages.relief import vers_donnees

SOURCE_CONTROLEE = "google_25d"
GRAINE_ECHANTILLON = 20261117      # fixe : le même projet donne toujours le même échantillon
TAILLE_ECHANTILLON = 8              # par strate (suspects, hasard, plus sûrs)
NB_LISTE = 20                       # longueur de la liste des plus suspects
COTE_VIGNETTE = 80.0                # m

# Seuils (ceux de la demande d'Olympe, sauf mention)
AIRE_TRES_PETITE = 20.0             # m2
AIRE_TRES_GRANDE = 800.0            # m2
ALLONGEMENT_MAX = 6.0               # longueur / largeur du rectangle englobant minimal
HAUTEUR_MIN = 2.4                   # m
HAUTEUR_MAX = 40.0                  # m
DENSITE_MAX = 0.85                  # part du disque de 50 m occupée par du bâti
RAYON_DENSITE = 50.0                # m
DISTANCE_PROCHE = 1.0               # m : « proche » de l'eau ou d'une route
RECTANGULARITE_MIN = 0.5            # aire / aire du rectangle englobant minimal (choix de l'auteur, voir ci-dessous)
PRESENCE_MIN = 0.55               # présence moyenne sous l'emprise (choix de l'auteur, voir ci-dessous)
# Ces deux seuils sont réglés sur la distribution observée (les détections ont une présence >= 0,5 par construction, et
# leur forme est soit un rectangle, soit un contour simplifié) pour que l'indice ne se déclenche que sur les plus bas
# (environ 10 à 25 %), pas pour coller à des erreurs réelles, qu'on ne connaît pas.

# Poids de chaque indice dans le score. Réglage de l'auteur, sans étalonnage sur des erreurs réelles.
POIDS = {
    "aire_tres_petite": 2,
    "aire_tres_grande": 2,
    "allonge": 2,
    "hauteur_incoherente": 2,
    "hauteur_absente": 1,
    "zone_tres_dense": 1,
    "proche_eau": 2,
    "proche_route": 1,
    "faible_rectangularite": 1,
    "presence_faible": 2,
}

AVERTISSEMENT = ("Ces indices mesurent la plausibilité géométrique des détections, pas leur exactitude. "
                 "Le score est un outil de tri (somme de poids), jamais une probabilité d'erreur. "
                 "Aucune vérité terrain n'a servi : les seuils et les poids sont des choix, non étalonnés.")


# ---------- indicateurs purs ----------

def _rectangle(poly):
    r = poly.minimum_rotated_rectangle
    if r.geom_type != "Polygon":
        return None, 0.0, 0.0
    c = list(r.exterior.coords)
    a = math.hypot(c[1][0] - c[0][0], c[1][1] - c[0][1])
    b = math.hypot(c[2][0] - c[1][0], c[2][1] - c[1][1])
    return r, max(a, b), min(a, b)


def allongement(poly) -> float:
    """Longueur / largeur du rectangle englobant minimal (1 = carré ; infini si dégénéré)."""
    _, long_, large = _rectangle(poly)
    if large < 1e-6:
        return math.inf
    return long_ / large


def rectangularite(poly) -> float:
    """Aire du polygone / aire de son rectangle englobant minimal (1 = rectangle parfait)."""
    r, _, _ = _rectangle(poly)
    if r is None or r.area <= 0:
        return 0.0
    return min(1.0, poly.area / r.area)


def densite_locale(poly, arbre: STRtree, geoms: list, zone=None, rayon: float = RAYON_DENSITE) -> float:
    """Part du disque (rayon `rayon`, centré sur le bâtiment, limité à `zone`) couverte par du bâti de `geoms`."""
    disque = poly.centroid.buffer(rayon, 32)
    if zone is not None:
        disque = disque.intersection(zone)
    if disque.is_empty or disque.area <= 0:
        return 0.0
    idx = arbre.query(disque)
    if len(idx) == 0:
        return 0.0
    couvert = unary_union([geoms[i] for i in idx]).intersection(disque).area
    return float(min(1.0, couvert / disque.area))


def proche_de(poly, surface, distance: float = DISTANCE_PROCHE) -> bool:
    """Vrai si le polygone est à `distance` mètres ou moins de `surface` (None = rien à comparer)."""
    if surface is None or surface.is_empty:
        return False
    return bool(poly.distance(surface) <= distance)


def pixels_sous(h: batiments25d.Hauteurs, poly_data):
    """(hauteurs, présences) des pixels dont le centre est dans le polygone (coordonnées de la grille 2.5D).
    Si aucun centre n'est dedans (très petit polygone), le pixel du centroïde."""
    n, m = h.hauteur.shape
    xmin, ymin, xmax, ymax = poly_data.bounds
    j0 = max(0, int(math.floor((xmin - h.x0) / h.pas)))
    j1 = min(m, int(math.ceil((xmax - h.x0) / h.pas)))
    i0 = max(0, int(math.floor((h.y0 - ymax) / h.pas)))
    i1 = min(n, int(math.ceil((h.y0 - ymin) / h.pas)))
    if j1 > j0 and i1 > i0:
        cx = h.x0 + (np.arange(j0, j1) + 0.5) * h.pas
        cy = h.y0 - (np.arange(i0, i1) + 0.5) * h.pas
        gx, gy = np.meshgrid(cx, cy)
        dedans = shapely.contains_xy(poly_data, gx, gy)
        if dedans.any():
            return h.hauteur[i0:i1, j0:j1][dedans], h.presence[i0:i1, j0:j1][dedans]
    c = poly_data.centroid
    return h.echantillon([c.x], [c.y])


def hauteur_et_presence(h: batiments25d.Hauteurs, poly_data) -> tuple[float | None, float]:
    """(hauteur calculée comme à la génération : médiane des pixels de présence >= 0,5 ; présence moyenne sous l'emprise)."""
    _, ps = pixels_sous(h, poly_data)
    return h.pour_emprise(poly_data), float(np.mean(ps)) if len(ps) else 0.0


def drapeaux(*, aire, allong, rectang, hauteur, presence, densite, eau, route) -> list[str]:
    """Liste des indices déclenchés, dans l'ordre de POIDS."""
    d = set()
    if aire < AIRE_TRES_PETITE:
        d.add("aire_tres_petite")
    if aire > AIRE_TRES_GRANDE:
        d.add("aire_tres_grande")
    if allong > ALLONGEMENT_MAX:
        d.add("allonge")
    if hauteur is None:
        d.add("hauteur_absente")
    elif hauteur < HAUTEUR_MIN or hauteur > HAUTEUR_MAX:
        d.add("hauteur_incoherente")
    if densite > DENSITE_MAX:
        d.add("zone_tres_dense")
    if eau:
        d.add("proche_eau")
    if route:
        d.add("proche_route")
    if rectang < RECTANGULARITE_MIN:
        d.add("faible_rectangularite")
    if presence < PRESENCE_MIN:
        d.add("presence_faible")
    return [k for k in POIDS if k in d]


def score(liste: list[str]) -> int:
    """Somme des poids des indices déclenchés (outil de tri, pas une probabilité)."""
    return int(sum(POIDS[k] for k in liste))


def cle_suspicion(e: dict) -> tuple:
    """Ordre décroissant de suspicion, déterministe : score, puis critère continu (moins de présence et de
    rectangularité = plus suspect), puis identifiant."""
    continu = (1.0 - e["presence_moyenne"]) + (1.0 - e["rectangularite"])
    return (-e["score"], -continu, e["id"])


def echantillon(entrees: list[dict], graine: int = GRAINE_ECHANTILLON, n: int = TAILLE_ECHANTILLON) -> list[dict]:
    """Échantillon stratifié et reproductible : n plus suspects, n au hasard parmi le reste, n plus sûrs.
    Renvoie des copies avec la clé « strate » (suspect, hasard, sur). Avec moins de 3n entrées : trois tiers."""
    ordre = sorted(entrees, key=cle_suspicion)
    if len(ordre) <= 3 * n:
        t = len(ordre) // 3
        haut, milieu, bas = ordre[:t], ordre[t: len(ordre) - t], ordre[len(ordre) - t:]
        hasard = milieu
    else:
        haut, bas, milieu = ordre[:n], ordre[len(ordre) - n:], ordre[n: len(ordre) - n]
        rng = rng_for(graine, "controle_detections")
        hasard = [milieu[i] for i in sorted(rng.sample(range(len(milieu)), n))]
    parts = [("suspect", haut), ("hasard", hasard), ("sur", bas[::-1])]
    return [{**e, "strate": nom} for nom, liste in parts for e in liste]


# ---------- calcul sur un projet ----------

def _surface_routes(routes):
    morceaux = [g.buffer(max(float(p.get("largeur") or 0.0), 1.0) / 2.0) for g, p in routes if not p.get("tunnel")]
    return unary_union(morceaux) if morceaux else None


def _surface_eau(eau):
    morceaux = [g.buffer(1.0) if g.geom_type in ("LineString", "MultiLineString") else g for g, _ in eau]
    return unary_union(morceaux) if morceaux else None


def analyser(batiments: list, routes: list, eau: list, bat25: dict, frame: LocalFrame) -> dict:
    """Calcule les indices de toutes les détections. batiments : [(géométrie locale, propriétés)]."""
    par_source = Counter(p.get("source") or "osm" for _, p in batiments)
    zone = frame.zone_polygon()
    geoms = [g for g, _ in batiments]
    arbre = STRtree(geoms) if geoms else None
    routes_s, eau_s = _surface_routes(routes), _surface_eau(eau)
    mesure = batiments25d.Hauteurs(bat25)
    vers_data = vers_donnees(frame, bat25["epsg"])
    sortie = []
    for g, p in sorted(((g, p) for g, p in batiments if p.get("source") == SOURCE_CONTROLEE), key=lambda t: t[1]["id"]):
        poly = g if g.geom_type == "Polygon" else max(g.geoms, key=lambda q: q.area)
        haut, pres = hauteur_et_presence(mesure, vers_data(poly))
        e = {
            "id": p["id"],
            "aire_m2": round(float(poly.area), 1),
            "allongement": round(min(allongement(poly), 99.0), 2),
            "rectangularite": round(rectangularite(poly), 3),
            "hauteur_m": None if haut is None else round(float(haut), 1),
            "presence_moyenne": round(pres, 3),
            "densite_locale": round(densite_locale(poly, arbre, geoms, zone), 3),
            "proche_eau": proche_de(poly, eau_s),
            "proche_route": proche_de(poly, routes_s),
        }
        e["indices"] = drapeaux(aire=e["aire_m2"], allong=e["allongement"], rectang=e["rectangularite"], hauteur=e["hauteur_m"],
                                presence=e["presence_moyenne"], densite=e["densite_locale"], eau=e["proche_eau"], route=e["proche_route"])
        e["score"] = score(e["indices"])
        lon, lat = frame.to_wgs84(poly.centroid.x, poly.centroid.y)
        e["lat"], e["lon"] = round(float(lat), 6), round(float(lon), 6)
        e["x"], e["y"] = round(float(poly.centroid.x), 2), round(float(poly.centroid.y), 2)
        sortie.append(e)
    return {"par_source": dict(sorted(par_source.items())), "detections": sortie}


def resumer(analyse: dict) -> dict:
    """Statistiques globales des détections (nombre par indice, répartition des scores, quantiles)."""
    det = analyse["detections"]
    c = Counter(i for e in det for i in e["indices"])
    sc = Counter(e["score"] for e in det)

    def q(cle, p):
        v = [e[cle] for e in det if e[cle] is not None]
        return round(float(np.percentile(v, p)), 2) if v else None

    return {
        "nombre": len(det),
        "par_indice": {k: c.get(k, 0) for k in POIDS},
        "part_par_indice": {k: round(c.get(k, 0) / len(det), 3) if det else 0.0 for k in POIDS},
        "repartition_scores": {str(k): sc[k] for k in sorted(sc)},
        "sans_aucun_indice": sc.get(0, 0),
        "score_1_ou_plus": sum(v for k, v in sc.items() if k >= 1),
        "score_4_ou_plus": sum(v for k, v in sc.items() if k >= 4),
        "aire_m2_mediane": q("aire_m2", 50), "aire_m2_p5_p95": [q("aire_m2", 5), q("aire_m2", 95)],
        "hauteur_m_mediane": q("hauteur_m", 50), "hauteur_m_p5_p95": [q("hauteur_m", 5), q("hauteur_m", 95)],
        "presence_moyenne_mediane": q("presence_moyenne", 50),
    }


def lien_carte(e: dict) -> str:
    return f"https://www.openstreetmap.org/?mlat={e['lat']}&mlon={e['lon']}#map=20/{e['lat']}/{e['lon']}"


def rapport(analyse: dict, graine: int = GRAINE_ECHANTILLON) -> dict:
    det = analyse["detections"]
    ordre = sorted(det, key=cle_suspicion)
    cles = ("id", "score", "indices", "aire_m2", "hauteur_m", "lat", "lon")
    return {
        "avertissement": AVERTISSEMENT,
        "parametres": {
            "source_controlee": SOURCE_CONTROLEE,
            "seuils": {"aire_tres_petite_m2": AIRE_TRES_PETITE, "aire_tres_grande_m2": AIRE_TRES_GRANDE,
                       "allongement_max": ALLONGEMENT_MAX, "hauteur_min_m": HAUTEUR_MIN, "hauteur_max_m": HAUTEUR_MAX,
                       "densite_max": DENSITE_MAX, "rayon_densite_m": RAYON_DENSITE, "distance_proche_m": DISTANCE_PROCHE,
                       "rectangularite_min": RECTANGULARITE_MIN, "presence_min": PRESENCE_MIN},
            "poids": POIDS,
            "echantillon": {"graine": graine, "par_strate": TAILLE_ECHANTILLON, "cote_vignette_m": COTE_VIGNETTE},
        },
        "batiments_par_source": analyse["par_source"],
        "resume": resumer(analyse),
        "plus_suspects": [{**{k: e[k] for k in cles}, "carte": lien_carte(e)} for e in ordre[:NB_LISTE]],
        "echantillon": [{**{k: e[k] for k in cles}, "strate": e["strate"]} for e in echantillon(det, graine)],
        "detections": [{k: e[k] for k in e if k not in ("x", "y")} for e in det],
        "non_verifie": [
            "Aucune comparaison avec le terrain ou une image satellite : les indices sont géométriques.",
            "L'étape secours retire déjà des détections ce qui chevauche eau et chaussées : « proche » veut dire à "
            f"{DISTANCE_PROCHE} m ou moins, pas « en chevauchement ».",
            "Seuils de rectangularité et de présence, et tous les poids : choix de l'auteur, non étalonnés.",
        ],
    }


def texte_resume(rap: dict, nom: str = "") -> str:
    r = rap["resume"]
    L = [f"Contrôle des détections{(' : ' + nom) if nom else ''}", "", rap["avertissement"], "",
         "Bâtiments par source : " + ", ".join(f"{k} {v}" for k, v in rap["batiments_par_source"].items())]
    if not r["nombre"]:
        L.append("Aucune détection « google_25d » à contrôler.")
        return "\n".join(L)
    L += ["", f"Détections contrôlées : {r['nombre']} ; sans aucun indice : {r['sans_aucun_indice']} ; "
              f"score 1 ou plus : {r['score_1_ou_plus']} ; score 4 ou plus : {r['score_4_ou_plus']}.",
          f"Surface médiane {r['aire_m2_mediane']} m2 (5 à 95 % : {r['aire_m2_p5_p95'][0]} à {r['aire_m2_p5_p95'][1]}) ; "
          f"hauteur médiane {r['hauteur_m_mediane']} m ; présence moyenne médiane {r['presence_moyenne_mediane']}.",
          "", "Indices déclenchés (poids) :"]
    for k, w in POIDS.items():
        L.append(f"  {k} ({w}) : {r['par_indice'][k]} ({100 * r['part_par_indice'][k]:.1f} %)")
    L += ["", f"Les {NB_LISTE} plus suspects (à vérifier sur une carte ou une image satellite) :"]
    for e in rap["plus_suspects"]:
        L.append(f"  {e['id']}  score {e['score']}  lat {e['lat']}, lon {e['lon']}  {e['aire_m2']} m2  "
                 f"h {e['hauteur_m']}  [{', '.join(e['indices'])}]")
    L += ["", "Non vérifié :"] + [f"  - {t}" for t in rap["non_verifie"]]
    return "\n".join(L)


# ---------- rendu ----------

def grille_locale(bat25: dict, frame: LocalFrame, cx: float, cy: float, demi: float = COTE_VIGNETTE / 2, n: int = 160):
    """(hauteur, présence) échantillonnées sur une grille locale n x n de côté 2*demi centrée en (cx, cy) ; ligne 0 = nord."""
    xs = cx + (np.arange(n) + 0.5) / n * 2 * demi - demi
    ys = cy + demi - (np.arange(n) + 0.5) / n * 2 * demi
    gx, gy = np.meshgrid(xs, ys)
    if int(bat25["epsg"]) == frame.epsg:
        ux, uy = gx + frame._e0, gy + frame._n0
    else:
        from pyproj import Transformer
        lon, lat = frame.to_wgs84(gx, gy)
        ux, uy = Transformer.from_crs(4326, int(bat25["epsg"]), always_xy=True).transform(lon, lat)
    return batiments25d.Hauteurs(bat25).echantillon(ux, uy)


def rendre_planche(entrees: list[dict], batiments: list, bat25: dict, frame: LocalFrame, dossier: Path, planche: Path,
                   colonnes: int = 6, titre: str = "") -> None:
    """Une vignette PNG par bâtiment dans `dossier`, puis la planche assemblée `planche`. Demande matplotlib."""
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    dossier.mkdir(parents=True, exist_ok=True)
    for ancien in dossier.glob("*.png"):
        ancien.unlink()
    geoms = [g for g, _ in batiments]
    arbre = STRtree(geoms)
    par_id = {p.get("id"): g for g, p in batiments}
    couleur_strate = {"suspect": "#d62728", "hasard": "#7f7f7f", "sur": "#2ca02c"}
    vmax = 20.0

    def dessiner(ax, e, compact):
        d = COTE_VIGNETTE / 2
        h, p = grille_locale(bat25, frame, e["x"], e["y"])
        ext = (e["x"] - d, e["x"] + d, e["y"] - d, e["y"] + d)
        im = ax.imshow(h, extent=ext, origin="upper", cmap="viridis", vmin=0, vmax=vmax, interpolation="nearest")
        if p.max() >= 0.5 >= p.min():
            ax.contour(np.linspace(ext[0], ext[1], p.shape[1]), np.linspace(ext[3], ext[2], p.shape[0]), p, levels=[0.5],
                       colors="white", linewidths=0.8)
        for i in arbre.query(shapely.box(ext[0], ext[2], ext[1], ext[3])):
            gg = geoms[i]
            if gg.geom_type == "Polygon" and batiments[i][1].get("id") != e["id"]:
                ax.plot(*gg.exterior.xy, color="#aaaaaa", lw=0.5, ls="--")
        cible = par_id.get(e["id"])
        if cible is not None and cible.geom_type == "Polygon":
            ax.plot(*cible.exterior.xy, color="#ff2d2d", lw=1.6)
        ax.set_xlim(ext[0], ext[1])
        ax.set_ylim(ext[2], ext[3])
        ax.set_xticks([])
        ax.set_yticks([])
        for s in ax.spines.values():
            s.set_edgecolor(couleur_strate[e["strate"]])
            s.set_linewidth(3)
        hh = "h ?" if e["hauteur_m"] is None else f"h {e['hauteur_m']:.1f} m"
        ax.set_title(f"{e['id'].replace('g25d/', '')}\n{e['aire_m2']:.0f} m2, {hh}, score {e['score']}", fontsize=7 if compact else 10)
        return im

    for k, e in enumerate(entrees):
        fig, ax = plt.subplots(figsize=(3.4, 3.6), dpi=110)
        im = dessiner(ax, e, compact=False)
        fig.colorbar(im, ax=ax, fraction=0.046, pad=0.02, label="hauteur 2.5D (m)")
        fig.tight_layout()
        fig.savefig(dossier / f"{k + 1:02d}_{e['strate']}_{e['id'].replace('/', '_')}.png")
        plt.close(fig)

    lignes = max(1, math.ceil(len(entrees) / colonnes))
    fig, axes = plt.subplots(lignes, colonnes, figsize=(2.5 * colonnes + 0.8, 2.75 * lignes + 1.0), dpi=100, squeeze=False)
    for ax in axes.ravel():
        ax.axis("off")
    im = None
    for ax, e in zip(axes.ravel(), entrees):
        ax.axis("on")
        im = dessiner(ax, e, compact=True)
    fig.suptitle((titre + " : " if titre else "") + "contrôle des détections IA, indices de suspicion et NON vérité terrain.\n"
                 "Cadre rouge : suspects ; gris : au hasard ; vert : les plus sûrs. Contour rouge : détection ; trait blanc : présence 0,5 ; "
                 f"tirets gris : autres bâtiments. Côté {COTE_VIGNETTE:.0f} m, nord en haut.", fontsize=8)
    if im is not None:
        fig.colorbar(im, ax=axes.ravel().tolist(), fraction=0.012, pad=0.01, label="hauteur 2.5D brute (m, échelle fixée de 0 à 20)")
    planche.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(planche)
    plt.close(fig)


# ---------- exclusion à la demande ----------

def ecrire_exclusions(config_path: Path, ids: list[str]) -> list[str]:
    """Ajoute `ids` à la liste `exclure` de la section [batiments25d] de config.toml (réunion avec l'existant).
    Renvoie la liste complète écrite. À n'appeler que si l'utilisateur le demande."""
    texte = Path(config_path).read_text(encoding="utf-8")
    m = re.search(r"^\[batiments25d\][ \t]*\r?\n", texte, flags=re.M)
    existants: list[str] = []
    mm = None
    if m:
        suivant = re.search(r"^\[", texte[m.end():], flags=re.M)
        fin_section = m.end() + (suivant.start() if suivant else len(texte) - m.end())
        mm = re.search(r"^exclure[ \t]*=[ \t]*\[(.*?)\][^\n]*\n?", texte[m.end():fin_section], flags=re.M | re.S)
        if mm:
            existants = re.findall(r'"([^"]*)"', mm.group(1))
    total = sorted(set(existants) | set(ids))
    bloc = "exclure = [\n" + "".join(f'    "{i}",\n' for i in total) + "]\n"
    if m and mm:
        nouveau = texte[: m.end() + mm.start()] + bloc + texte[m.end() + mm.end():]
    elif m:
        nouveau = texte[: m.end()] + bloc + texte[m.end():]
    else:
        nouveau = (texte.rstrip("\n") + "\n\n[batiments25d]\n"
                   "# Détections IA exclues à la demande de l'utilisateur (ayigba controler-detections --exclure-score)\n" + bloc)
    Path(config_path).write_text(nouveau, encoding="utf-8")
    return total


# ---------- commande ----------

def charger_projet(projet):
    """Lit les fichiers déjà générés : bâtiments et routes de work/secours, eau de work/nettoyage, grille 2.5D du cache."""
    from .config import load_config
    cfg = load_config(projet.config_path)
    frame = LocalFrame(cfg.bbox)
    f_bat = projet.work / "secours" / "buildings.geojson"
    if not f_bat.is_file():
        raise LookupError(f"Pas de bâtiments générés ({f_bat}) : lance d'abord « ayigba generer {projet.root} ».")
    f25 = projet.cache / "batiments25d.npz"
    if not f25.is_file():
        raise LookupError(f"Grille 2.5D absente ({f25}) : hauteurs et présence indisponibles, rien à contrôler.")
    f_routes = projet.work / "secours" / "roads.geojson"
    f_eau = projet.work / "nettoyage" / "water.geojson"
    return (read_features(f_bat), read_features(f_routes) if f_routes.is_file() else [],
            read_features(f_eau) if f_eau.is_file() else [], batiments25d.charger(f25), frame)


def controler(projet, sans_images: bool = False, exclure_score: int | None = None) -> dict:
    """Exécute le contrôle d'un projet (sans réseau) et écrit les rapports. Renvoie le rapport (clés « _… » : sorties
    pour l'affichage, absentes du fichier)."""
    batiments, routes, eau, bat25, frame = charger_projet(projet)
    ana = analyser(batiments, routes, eau, bat25, frame)
    rap = rapport(ana)
    projet.reports.mkdir(parents=True, exist_ok=True)
    (projet.reports / "controle_detections.json").write_text(
        json.dumps(rap, ensure_ascii=False, indent=1, sort_keys=True) + "\n", encoding="utf-8")
    texte = texte_resume(rap, projet.slug)
    (projet.reports / "controle_detections.txt").write_text(texte + "\n", encoding="utf-8")
    rap["_texte"] = texte
    rap["_images"] = None
    if not sans_images and ana["detections"]:
        try:
            rendre_planche(echantillon(ana["detections"]), batiments, bat25, frame,
                           projet.reports / "controle_detections", projet.reports / "controle_detections.png", titre=projet.slug)
            rap["_images"] = str(projet.reports / "controle_detections.png")
        except ImportError:
            rap["_images"] = "matplotlib absent : images non produites (pip install matplotlib)"
    if exclure_score is not None:
        ids = [e["id"] for e in ana["detections"] if e["score"] >= exclure_score]
        rap["_exclus_nouveaux"] = len(ids)
        rap["_exclus_total"] = len(ecrire_exclusions(projet.config_path, ids)) if ids else None
    return rap
