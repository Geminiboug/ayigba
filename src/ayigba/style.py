"""Style d'une carte : couleurs du sol, des murs et des toits, règles régionales, et cohérence entre bâtiments voisins.

Pourquoi : les données libres ne disent presque rien de la couleur ou de la matière d'un bâtiment (OpenStreetMap : aucun tag
`building:colour` ni `roof:shape` sur les zones testées). Sans règle, chaque bâtiment tirait sa couleur au hasard, donc deux voisins
pouvaient diverger, et les couleurs étaient celles du Bénin partout. Ce module sépare trois choses :

1. un PRÉRÉGLAGE régional (palette du sol, des murs et des toits, nombre d'étages habituel, rues revêtues par défaut) : c'est un
   choix de style, jamais une mesure ; `[style] preset = "..."` dans config.toml, ou choisi par `ayigba creer` d'après le pays ;
2. la COHÉRENCE : un champ lisse (bruit de valeur) sur la zone donne à chaque quartier une couleur de mur et de toit dominante ;
   un bâtiment prend la dominante avec la probabilité `coherence`, sinon un tirage libre dans la palette ;
3. une MESURE de cohérence (distance de couleur entre voisins comparée à celle de paires au hasard), écrite dans le rapport.

Les couleurs des murs sont triées de la plus sombre à la plus claire pour que deux indices proches soient deux teintes proches.
Rien ici n'invente la réalité d'un bâtiment : sans photo de référence, le style reste celui du quartier (voir docs/CHANTIER.md).
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field, replace

import numpy as np

Couleur = tuple[float, float, float]


@dataclass(frozen=True)
class Style:
    nom: str
    sol: Couleur
    laterite: Couleur            # chaussées non revêtues
    asphalte: Couleur
    piste: Couleur               # pistes d'aéroport
    trottoir: Couleur
    eau: Couleur
    fond: Couleur
    peinture: Couleur
    murs: tuple[Couleur, ...]
    toits: tuple[Couleur, ...]
    # étages : (poids de 1, 2, 3, ... étages) pour une emprise petite (< 250 m2), moyenne (< 1 200 m2), grande
    etages_petit: tuple[int, ...] = (70, 24, 6)
    etages_moyen: tuple[int, ...] = (45, 30, 17, 8)
    etages_grand: tuple[int, ...] = (55, 30, 15)
    revetues_par_defaut: frozenset = frozenset({"motorway", "trunk", "primary", "secondary", "tertiary"})
    coherence: float = 0.0       # 0 = tirage indépendant par bâtiment (ancien comportement)
    taille_quartier_m: float = 150.0
    classes: bool = False        # vrai : la couleur dépend aussi de la classe du bâtiment (règles ci-dessous)
    note: str = ""

    def murs_tries(self) -> tuple[Couleur, ...]:
        return tuple(sorted(self.murs, key=_luminance))

    def toits_tries(self) -> tuple[Couleur, ...]:
        return tuple(sorted(self.toits, key=_luminance))


def _luminance(c: Couleur) -> float:
    return 0.2126 * c[0] + 0.7152 * c[1] + 0.0722 * c[2]


# Valeurs historiques (Bénin) : elles ne changent pas, pour que les cartes déjà générées restent identiques.
AFRIQUE_DE_L_OUEST = Style(
    nom="afrique_de_l_ouest",
    sol=(0.78, 0.69, 0.52), laterite=(0.72, 0.52, 0.36), asphalte=(0.23, 0.23, 0.25), piste=(0.33, 0.33, 0.35),
    trottoir=(0.63, 0.62, 0.59), eau=(0.16, 0.38, 0.47), fond=(0.45, 0.41, 0.33), peinture=(0.92, 0.92, 0.89),
    murs=((0.86, 0.80, 0.68), (0.90, 0.86, 0.78), (0.80, 0.70, 0.55), (0.93, 0.91, 0.87), (0.76, 0.74, 0.70), (0.85, 0.73, 0.66), (0.70, 0.76, 0.72)),
    toits=((0.55, 0.56, 0.58), (0.47, 0.36, 0.30), (0.62, 0.62, 0.60), (0.40, 0.42, 0.45), (0.52, 0.30, 0.24)),
    note="sable clair, latérite, murs crème et ocre, toits de tôle ; surtout du plain-pied ; rues non revêtues par défaut sauf grands axes",
)

EUROPE_TEMPEREE = Style(
    nom="europe_temperee",
    sol=(0.52, 0.54, 0.44), laterite=(0.58, 0.52, 0.42), asphalte=(0.21, 0.21, 0.23), piste=(0.31, 0.31, 0.33),
    trottoir=(0.66, 0.65, 0.62), eau=(0.20, 0.36, 0.46), fond=(0.40, 0.38, 0.33), peinture=(0.93, 0.93, 0.91),
    murs=((0.88, 0.84, 0.74), (0.82, 0.76, 0.64), (0.74, 0.68, 0.58), (0.91, 0.89, 0.85), (0.78, 0.60, 0.48), (0.68, 0.66, 0.62), (0.85, 0.80, 0.70)),
    toits=((0.62, 0.32, 0.24), (0.55, 0.29, 0.22), (0.42, 0.43, 0.46), (0.34, 0.35, 0.38), (0.58, 0.40, 0.32)),
    etages_petit=(25, 40, 28, 7), etages_moyen=(10, 25, 35, 22, 8), etages_grand=(8, 20, 30, 25, 17),
    revetues_par_defaut=frozenset({"motorway", "trunk", "primary", "secondary", "tertiary", "unclassified", "residential", "living_street", "service", "pedestrian"}),
    note="pierre et crépi clairs, brique, toits de tuile ou de zinc ; immeubles de 3 à 5 étages en ville ; rues revêtues par défaut",
)

ANDES = Style(
    nom="andes",
    sol=(0.55, 0.46, 0.34), laterite=(0.62, 0.48, 0.34), asphalte=(0.25, 0.24, 0.24), piste=(0.33, 0.32, 0.32),
    trottoir=(0.60, 0.57, 0.52), eau=(0.20, 0.38, 0.46), fond=(0.42, 0.37, 0.30), peinture=(0.92, 0.91, 0.87),
    murs=((0.76, 0.58, 0.42), (0.83, 0.68, 0.50), (0.90, 0.85, 0.77), (0.70, 0.52, 0.38), (0.88, 0.80, 0.66), (0.80, 0.72, 0.62)),
    toits=((0.63, 0.33, 0.24), (0.56, 0.30, 0.22), (0.50, 0.38, 0.30), (0.45, 0.46, 0.48), (0.68, 0.40, 0.28)),
    etages_petit=(45, 40, 15), etages_moyen=(30, 40, 25, 5),
    revetues_par_defaut=frozenset({"motorway", "trunk", "primary", "secondary", "tertiary", "unclassified", "residential"}),
    note="adobe et crépi ocre, toits de tuile rouge ; 1 à 3 étages ; rues de ville revêtues",
)

GENERIQUE = Style(
    nom="generique",
    sol=(0.62, 0.60, 0.50), laterite=(0.60, 0.52, 0.42), asphalte=(0.22, 0.22, 0.24), piste=(0.32, 0.32, 0.34),
    trottoir=(0.64, 0.63, 0.60), eau=(0.18, 0.37, 0.47), fond=(0.42, 0.39, 0.33), peinture=(0.92, 0.92, 0.90),
    murs=((0.84, 0.80, 0.72), (0.88, 0.85, 0.79), (0.76, 0.72, 0.66), (0.92, 0.90, 0.86), (0.72, 0.70, 0.66)),
    toits=((0.52, 0.52, 0.54), (0.50, 0.38, 0.32), (0.60, 0.60, 0.58), (0.40, 0.41, 0.44)),
    etages_petit=(50, 35, 15), etages_moyen=(30, 35, 25, 10), etages_grand=(30, 35, 25, 10),
    revetues_par_defaut=frozenset({"motorway", "trunk", "primary", "secondary", "tertiary", "unclassified", "residential"}),
    note="palette neutre, utilisée quand le pays n'a pas de préréglage",
)

PRESETS: dict[str, Style] = {s.nom: s for s in (AFRIQUE_DE_L_OUEST, EUROPE_TEMPEREE, ANDES, GENERIQUE)}

# Codes pays ISO (minuscules) -> préréglage. Un choix de départ pour `ayigba creer`, modifiable dans config.toml.
PAYS_PRESET: dict[str, str] = {}
for _codes, _preset in (
    ("bj tg gh ng ci sn ml bf ne gn sl lr gm cm gw mr cv", "afrique_de_l_ouest"),
    ("fr be nl lu de ch at it es pt gb ie dk se no fi pl cz sk hu ro bg gr hr si ee lv lt", "europe_temperee"),
    ("pe bo ec co", "andes"),
):
    for _c in _codes.split():
        PAYS_PRESET[_c] = _preset


def preset_pour_pays(code_pays: str | None) -> str:
    return PAYS_PRESET.get((code_pays or "").strip().lower(), "generique")


def _couleur(valeur, defaut: Couleur) -> Couleur:
    """Accepte [r, g, b] entre 0 et 1, ou « #rrggbb »."""
    if valeur is None:
        return defaut
    if isinstance(valeur, str):
        v = valeur.lstrip("#")
        if len(v) != 6:
            raise ValueError(f"couleur invalide : « {valeur} » (attendu #rrggbb)")
        return tuple(round(int(v[i:i + 2], 16) / 255.0, 3) for i in (0, 2, 4))  # type: ignore[return-value]
    t = tuple(float(x) for x in valeur)
    if len(t) != 3 or not all(0.0 <= x <= 1.0 for x in t):
        raise ValueError(f"couleur invalide : {valeur} (attendu trois nombres entre 0 et 1)")
    return t  # type: ignore[return-value]


def charger(config) -> Style:
    """Style du projet : `[style] preset` (défaut : afrique_de_l_ouest, l'ancien comportement), puis les surcharges
    `[style] sol`, `laterite`, `asphalte`, `trottoir`, `eau`, `murs`, `toits`, `coherence`, `taille_quartier_m`."""
    nom = str(config.option("style", "preset", "afrique_de_l_ouest"))
    if nom not in PRESETS:
        raise ValueError(f"préréglage de style inconnu : « {nom} ». Disponibles : {', '.join(sorted(PRESETS))}")
    s = PRESETS[nom]
    champs: dict = {}
    for k in ("sol", "laterite", "asphalte", "piste", "trottoir", "eau", "fond", "peinture"):
        v = config.option("style", k, None)
        if v is not None:
            champs[k] = _couleur(v, getattr(s, k))
    for k in ("murs", "toits"):
        v = config.option("style", k, None)
        if v is not None:
            if not v:
                raise ValueError(f"[style] {k} ne peut pas être vide")
            champs[k] = tuple(_couleur(c, (0, 0, 0)) for c in v)
    co = float(config.option("style", "coherence", s.coherence))
    if not 0.0 <= co <= 1.0:
        raise ValueError("[style] coherence doit être entre 0 et 1")
    champs["coherence"] = co
    tq = float(config.option("style", "taille_quartier_m", s.taille_quartier_m))
    if tq < 20.0:
        raise ValueError("[style] taille_quartier_m doit être au moins 20")
    champs["taille_quartier_m"] = tq
    champs["classes"] = bool(config.option("style", "classes", s.classes))
    return replace(s, **champs)


# ------------------------------------------------------------------------------------------------ classes de bâtiments

_CLASSES = {
    "commerce": "commercial retail supermarket kiosk shop",
    "industriel": "industrial warehouse factory manufacture storage_tank hangar service garage garages",
    "religieux": "church mosque temple cathedral chapel synagogue shrine religious",
    "institution": "school hospital university college kindergarten public civic government office clinic fire_station train_station hotel",
}


def classe_batiment(genre: str | None) -> str:
    """Classe d'un bâtiment d'après la valeur OSM `building=*` : commerce, industriel, religieux, institution, sinon résidentiel.
    C'est une règle de style : elle ne regarde que ce type, jamais la forme ni la couleur réelle."""
    g = (genre or "").strip().lower()
    for classe, mots in _CLASSES.items():
        if g in mots.split():
            return classe
    return "residentiel"


def _saturation(c: Couleur) -> float:
    return max(c) - min(c)


def _restreindre(palette: tuple, classe: str | None, objet: str) -> tuple:
    """Sous-palette de la classe : institutions et commerces plus clairs, lieux de culte presque blancs, industrie en gris.
    Palette triée de la plus sombre à la plus claire ; jamais vide."""
    n = len(palette)
    if classe in (None, "residentiel") or n < 3:
        return palette
    if objet == "murs":
        if classe in ("institution", "commerce"):
            sous = palette[n // 2:]
        elif classe == "religieux":
            sous = palette[-max(1, n // 4):]
        else:
            sous = tuple(sorted(sorted(palette, key=_saturation)[:max(2, n // 3)], key=_luminance))
    else:
        if classe == "industriel":
            sous = tuple(sorted(sorted(palette, key=_saturation)[:max(2, n // 2)], key=_luminance))
        elif classe == "religieux":
            sous = palette[-max(1, n // 3):]
        else:
            return palette
    return sous or palette


# ---------------------------------------------------------------------------------------------------- cohérence spatiale

def _hash01(seed: int, i: int, j: int) -> float:
    """Nombre entre 0 et 1 attaché au nœud (i, j) de la grille : mélange d'entiers, identique partout et à chaque exécution."""
    h = (i * 374761393 + j * 668265263 + seed * 2246822519) & 0xFFFFFFFF
    h = ((h ^ (h >> 13)) * 1274126177) & 0xFFFFFFFF
    h ^= h >> 16
    return (h & 0xFFFFFF) / float(0x1000000)


def champ(seed: int, taille_m: float):
    """Fonction (x, y) -> valeur lissée dans [0, 1] : bruit de valeur sur une grille de `taille_m`. Deux points proches ont
    des valeurs proches ; la valeur est étirée vers les extrêmes pour que toute la palette serve."""
    def f(x: float, y: float) -> float:
        gx, gy = x / taille_m, y / taille_m
        i, j = math.floor(gx), math.floor(gy)
        fx, fy = gx - i, gy - j
        sx, sy = fx * fx * (3 - 2 * fx), fy * fy * (3 - 2 * fy)
        a, b = _hash01(seed, i, j), _hash01(seed, i + 1, j)
        c, d = _hash01(seed, i, j + 1), _hash01(seed, i + 1, j + 1)
        v = (a * (1 - sx) + b * sx) * (1 - sy) + (c * (1 - sx) + d * sx) * sy
        return min(1.0, max(0.0, 0.5 + (v - 0.5) * 1.8))
    return f


class Teinte:
    """Choisit les couleurs de mur et de toit d'un bâtiment : la dominante du quartier avec la probabilité `coherence`,
    sinon un tirage libre (le générateur `rng` du bâtiment, donc reproductible)."""

    def __init__(self, style: Style, seed: int):
        self.style = style
        self._murs = style.murs_tries()
        self._toits = style.toits_tries()
        self._fm = champ(seed ^ 0x5A17, style.taille_quartier_m)
        self._ft = champ(seed ^ 0xC3B9, style.taille_quartier_m * 1.3)

    def choisir(self, x: float, y: float, rng, genre: str | None = None) -> tuple[Couleur, Couleur]:
        if self.style.classes:
            classe = classe_batiment(genre)
            murs, toits = _restreindre(self._murs, classe, "murs"), _restreindre(self._toits, classe, "toits")
            return self._pick(murs, self._fm(x, y), rng), self._pick(toits, self._ft(x, y), rng)
        if self.style.coherence <= 0.0:
            return rng.choice(self.style.murs), rng.choice(self.style.toits)   # ancien comportement, mêmes tirages
        mur = self._pick(self._murs, self._fm(x, y), rng)
        toit = self._pick(self._toits, self._ft(x, y), rng)
        return mur, toit

    def _pick(self, palette, v: float, rng):
        # un seul tirage `rng.random()` pour décider, puis éventuellement un tirage dans la palette : toujours la même séquence
        r = rng.random()
        base = min(int(v * len(palette)), len(palette) - 1)
        if r < self.style.coherence:
            return palette[base]
        return rng.choice(palette)


# ----------------------------------------------------------------------------------------------------- mesure

def distance_couleur(a: Couleur, b: Couleur) -> float:
    return float(math.dist(a, b))


def coherence_voisins(points: np.ndarray, couleurs: np.ndarray, rayon_m: float = 60.0, k: int = 5, graine: int = 1) -> dict:
    """Compare la distance de couleur entre voisins proches à celle de paires prises au hasard.

    points : (N, 2) positions en mètres ; couleurs : (N, 3). Renvoie {"voisins": ..., "hasard": ..., "rapport": ..., "n": ...}.
    Un rapport inférieur à 1 veut dire que les voisins se ressemblent plus que des bâtiments pris au hasard (cohérence) ; vers 1,
    il n'y a pas de structure spatiale. C'est une mesure de style, pas de fidélité à la réalité."""
    n = len(points)
    if n < 20:
        return {"n": n, "voisins": None, "hasard": None, "rapport": None}
    cases: dict[tuple[int, int], list[int]] = {}
    ij = np.floor(points / rayon_m).astype(int)
    for idx, (i, j) in enumerate(ij):
        cases.setdefault((int(i), int(j)), []).append(idx)
    somme, compte = 0.0, 0
    for idx in range(n):
        i, j = int(ij[idx, 0]), int(ij[idx, 1])
        cand = [m for di in (-1, 0, 1) for dj in (-1, 0, 1) for m in cases.get((i + di, j + dj), ()) if m != idx]
        if not cand:
            continue
        cand = np.array(cand)
        d = np.linalg.norm(points[cand] - points[idx], axis=1)
        ordre = np.argsort(d, kind="stable")
        proches = cand[ordre[:k]][d[ordre[:k]] <= rayon_m]
        if len(proches) == 0:
            continue
        somme += float(np.linalg.norm(couleurs[proches] - couleurs[idx], axis=1).mean())
        compte += 1
    rng = np.random.default_rng(graine)
    a, b = rng.integers(0, n, 4000), rng.integers(0, n, 4000)
    ok = a != b
    hasard = float(np.linalg.norm(couleurs[a[ok]] - couleurs[b[ok]], axis=1).mean())
    voisins = somme / compte if compte else None
    return {"n": n, "voisins": None if voisins is None else round(voisins, 4), "hasard": round(hasard, 4),
            "rapport": None if voisins is None or hasard == 0 else round(voisins / hasard, 3)}
