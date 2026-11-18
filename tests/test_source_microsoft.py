"""Tests de la source Microsoft Global ML Building Footprints. Données synthétiques, aucun accès réseau."""
import gzip
import io
import json
import ssl
import urllib.error

import pytest

from ayigba import empreintes
from ayigba.geo import LocalFrame
from ayigba.project import open_context
from ayigba.sources import read_sources
from ayigba.sources_empreintes import microsoft as ms

BBOX = (2.0718, 6.35314, 2.09892, 6.38009)  # Ouidah


def test_quadkey_valeurs_connues():
    assert ms.quadkey_de(2.39, 6.37) == "122220231"   # Cotonou
    assert ms.quadkey_de(2.08, 6.37) == "122220230"   # Ouidah


def test_quadkey_aller_retour():
    for qk in ("122220230", "122220231", "000000000", "333333333"):
        x, y, n = ms.tuile_de_quadkey(qk)
        assert n == 9 and ms.quadkey_de_tuile(x, y) == qk
        o, s, e, no = ms.limites_quadkey(qk)
        assert ms.quadkey_de((o + e) / 2, (s + no) / 2) == qk
    with pytest.raises(ValueError):
        ms.tuile_de_quadkey("1224")


def test_tuiles_bbox_cheval_sur_deux():
    o, s, e, n = ms.limites_quadkey("122220230")
    assert e == pytest.approx(2.109375)  # frontière entre les deux tuiles
    bbox = (e - 0.01, 6.37, e + 0.01, 6.38)
    assert ms.quadkeys_pour(bbox) == ["122220230", "122220231"]
    assert ms.quadkeys_pour(BBOX) == ["122220230"]


INDEX = ("Location,QuadKey,Url,Size,UploadDate\n"
         "Africa,122220231,https://x/a.csv.gz,1.1KB,2026-08-13\n"
         "Benin,122220230,https://x/b.csv.gz,22.6MB,2026-08-13\n"
         "Togo,122220230,https://x/t.csv.gz,10.2MB,2026-08-13\n"
         "Benin,122220231,https://x/c.csv.gz,76.7MB,2026-08-13\n")


def test_index_et_tailles():
    idx = ms.lire_index(INDEX)
    assert len(idx) == 4 and idx[1]["QuadKey"] == "122220230"
    f = ms.fichiers_pour(idx, ["122220230"])
    assert [x["Location"] for x in f] == ["Benin", "Togo"]
    assert ms.taille_en_octets("22.6MB") == int(22.6 * 1024 * 1024)
    assert ms.taille_en_octets("1.1KB") == int(1.1 * 1024)
    assert ms.taille_en_octets("???") == 0
    with pytest.raises(ValueError):
        ms.lire_index("a,b\n1,2\n")


def carre(lon, lat, d=0.0001):
    return [[lon, lat], [lon + d, lat], [lon + d, lat + d], [lon, lat + d], [lon, lat]]


def feature(coords, h=-1.0, conf=-1.0, type_="Polygon"):
    return json.dumps({"type": "Feature", "properties": {"height": h, "confidence": conf},
                       "geometry": {"type": type_, "coordinates": [coords] if type_ == "Polygon" else coords}})


LIGNES = [
    feature(carre(2.08, 6.36), h=-1.0),
    feature(carre(2.085, 6.365), h=6.0, conf=0.9),
    feature(carre(2.5, 6.9), h=4.0),                       # hors bbox
    "ligne cassée",
    "",
    feature([[carre(2.081, 6.361)], [carre(2.30, 6.9)]], type_="MultiPolygon"),  # une partie dedans, une dehors
]


def test_parsing_et_filtrage():
    els, ill = ms.filtrer_flux(LIGNES, BBOX)
    assert ill == 1 and len(els) == 3
    assert [e["hauteur"] for e in els] == [None, 6.0, None]   # -1 = inconnue
    assert els[1]["confiance"] == 0.9 and els[0]["confiance"] is None
    # octets acceptés aussi
    assert len(ms.filtrer_flux([l.encode() for l in LIGNES], BBOX)[0]) == 3


def test_conversion_repere_local():
    frame = LocalFrame(BBOX)
    els, _ = ms.filtrer_flux(LIGNES[:2], BBOX)
    cands = ms.vers_empreintes(els, frame)
    assert len(cands) == 2 and cands[0].hauteur is None and cands[1].hauteur == 6.0
    z = frame.zone_polygon()
    for c in cands:
        assert c.geom.is_valid and z.contains(c.geom)
        assert 100 < c.geom.area < 140  # 0,0001 degré ~ 11 m de côté
    assert cands[1].extra == {"confiance": 0.9}


def test_simplification_legere():
    frame = LocalFrame(BBOX)
    # point quasi colinéaire (écart < 0,2 m) retiré
    anneau = [[2.08, 6.36], [2.0801, 6.36], [2.08015, 6.360000005], [2.0802, 6.36], [2.0802, 6.3601], [2.08, 6.3601], [2.08, 6.36]]
    els, _ = ms.filtrer_flux([feature(anneau)], BBOX)
    g = ms.vers_empreintes(els, frame)[0].geom
    assert len(g.exterior.coords) == 5


# --- source complète, avec un faux « opener » -----------------------------------------------------------------------------

class Rep(io.BytesIO):
    def __enter__(self):
        return self

    def __exit__(self, *a):
        self.close()
        return False


class Faux:
    """Faux opener : sert l'index et les fichiers gz, compte les appels."""

    def __init__(self, fichiers):
        self.fichiers = fichiers
        self.appels = []

    def __call__(self, req, timeout=None):
        url = req.full_url
        self.appels.append(url)
        if url.endswith("dataset-links.csv"):
            return Rep(INDEX.replace("https://x/", "https://x/").encode())
        if url not in self.fichiers:
            raise urllib.error.HTTPError(url, 404, "nf", {}, None)
        return Rep(self.fichiers[url])


def faire_ctx(tmp_path, offline=False, extra=""):
    d = tmp_path / "projet"
    d.mkdir()
    (d / "config.toml").write_text(
        '[ville]\nnom = "Test"\n[zone]\nbbox = [2.0718, 6.35314, 2.09892, 6.38009]\n[generation]\ngraine = 1\n' + extra, encoding="utf-8")
    return open_context(d, offline=offline)


def fichiers():
    benin = gzip.compress("\n".join(LIGNES).encode())
    togo = gzip.compress(feature(carre(2.09, 6.37), h=3.0).encode())
    return {"https://x/b.csv.gz": benin, "https://x/t.csv.gz": togo}


def test_collecter_et_cache(tmp_path):
    ctx = faire_ctx(tmp_path)
    faux = Faux(fichiers())
    src = ms.MicrosoftEmpreintes(opener=faux, sleep=lambda s: None)
    cands = src.collecter(ctx, LocalFrame(ctx.config.bbox), None)
    assert len(cands) == 4 and sorted(c.hauteur for c in cands if c.hauteur) == [3.0, 6.0]
    assert sum(1 for u in faux.appels if u.endswith(".csv.gz")) == 2
    s = read_sources(ctx.project.data)
    assert s[0]["id"] == "microsoft" and s[0]["licence"] == "CDLA Permissive 2.0" and s[0]["elements"] == 4
    # second appel : rien n'est retéléchargé, même résultat
    faux2 = Faux({})
    src2 = ms.MicrosoftEmpreintes(opener=faux2, sleep=lambda s: None)
    cands2 = src2.collecter(ctx, LocalFrame(ctx.config.bbox), None)
    assert faux2.appels == [] and len(cands2) == 4


def test_hors_ligne_sans_cache(tmp_path):
    ctx = faire_ctx(tmp_path, offline=True)
    faux = Faux(fichiers())
    with pytest.raises(RuntimeError, match="Mode hors ligne"):
        ms.MicrosoftEmpreintes(opener=faux).collecter(ctx, LocalFrame(ctx.config.bbox), None)
    assert faux.appels == []


def test_hors_ligne_avec_option_telecharger(tmp_path):
    ctx = faire_ctx(tmp_path, offline=True, extra='[empreintes.microsoft]\ntelecharger = true\n')
    cands = ms.MicrosoftEmpreintes(opener=Faux(fichiers()), sleep=lambda s: None).collecter(ctx, LocalFrame(ctx.config.bbox), None)
    assert len(cands) == 4
    # puis hors ligne pur avec le cache : fonctionne
    ctx2 = open_context(ctx.project.root, offline=True)
    ctx2.config.options  # noqa: B018
    assert len(ms.MicrosoftEmpreintes(opener=Faux({})).collecter(ctx2, LocalFrame(ctx2.config.bbox), None)) == 4


def test_certificat_refuse_reessaie_une_fois(tmp_path):
    ctx = faire_ctx(tmp_path)
    appels = []

    def opener(req, timeout=None):
        appels.append(req.full_url)
        raise urllib.error.URLError(ssl.SSLCertVerificationError("certificate verify failed"))
    src = ms.MicrosoftEmpreintes(opener=opener, sleep=lambda s: None)
    with pytest.raises(RuntimeError, match="certificat SSL"):
        src._avec_reessai("https://x/y", lambda r: r.read())
    assert len(appels) == 2


def test_limite_de_telechargement(tmp_path, monkeypatch):
    monkeypatch.setattr(ms, "LIMITE_OCTETS", 100)
    ctx = faire_ctx(tmp_path)
    src = ms.MicrosoftEmpreintes(opener=Faux(fichiers()), sleep=lambda s: None)
    with pytest.raises(RuntimeError, match="limite|dépasse"):
        src.collecter(ctx, LocalFrame(ctx.config.bbox), None)


def test_enregistree_dans_le_registre():
    assert empreintes.obtenir("microsoft").licence == "CDLA Permissive 2.0"
    assert "microsoft" in [c.id for c in empreintes.disponibles()]


def test_decoupe_a_la_zone():
    frame = LocalFrame(BBOX)
    zone = frame.zone_polygon()
    els, _ = ms.filtrer_flux([feature(carre(BBOX[0] - 0.00005, BBOX[1] + 0.01)), feature(carre(2.08, 6.36))], BBOX)
    cands = ms.decouper_a_la_zone(ms.vers_empreintes(els, frame), zone)
    assert len(cands) == 2 and all(zone.contains(c.geom) for c in cands)
    assert cands[0].geom.area < cands[1].geom.area  # le premier est coupé
    assert ms.decouper_a_la_zone(cands, None) == cands
