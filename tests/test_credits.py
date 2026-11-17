"""Tests du fichier CREDITS.md."""
from ayigba.credits import build_credits, write_credits
from ayigba.project import open_context
from ayigba.sources import read_sources, register_source


def _ctx(tmp_path):
    d = tmp_path / "ville-test"
    d.mkdir()
    (d / "config.toml").write_text(
        '[ville]\nnom = "Cotonou"\nquartier = "Test"\n\n'
        "[zone]\nbbox = [2.372, 6.346, 2.402, 6.366]\n\n"
        "[generation]\ngraine = 1\n",
        encoding="utf-8",
    )
    return open_context(d)


def _src(id_, licence="ODbL 1.0", **extra):
    s = {
        "id": id_,
        "nom": f"Source {id_}",
        "licence": licence,
        "url_licence": f"https://exemple.org/{id_}/licence",
        "attribution": f"Données {id_}",
        "url_source": f"https://exemple.org/{id_}",
        "date_collecte": "2026-01-02",
    }
    s.update(extra)
    return s


def test_source_odbl(tmp_path):
    ctx = _ctx(tmp_path)
    register_source(ctx.project.data, _src("osm", zone="Cotonou", note="une note"))
    txt = build_credits(read_sources(ctx.project.data), "Cotonou, Test")
    assert txt.startswith("# Sources et licences : Cotonou, Test")
    assert "Données osm" in txt
    assert "[ODbL 1.0](https://exemple.org/osm/licence)" in txt
    assert "## Rappel ODbL" in txt
    assert "Zone : Cotonou" in txt and "Note : une note" in txt


def test_pas_de_rappel_cc(tmp_path):
    txt = build_credits([_src("a", licence="CC BY 4.0")], "T")
    assert "Rappel ODbL" not in txt


def test_liste_vide():
    txt = build_credits([], "T")
    assert "Aucune source extérieure enregistrée." in txt


def test_ordre_trie():
    a = build_credits([_src("b"), _src("a")], "T")
    assert a.index("Source a") < a.index("Source b")
    assert a == build_credits([_src("a"), _src("b")], "T")


def test_deterministe():
    s = [_src("x"), _src("y")]
    assert build_credits(s, "T", 3) == build_credits(s, "T", 3)


def test_nb_generes():
    assert "42" in build_credits([], "T", 42)
    assert "Nombre d'éléments générés" not in build_credits([], "T")


def test_write_credits(tmp_path):
    ctx = _ctx(tmp_path)
    register_source(ctx.project.data, _src("osm"))
    p = write_credits(ctx, tmp_path / "sortie" / "x", nb_generes=5)
    assert p.name == "CREDITS.md" and p.is_file()
    txt = p.read_text(encoding="utf-8")
    assert "# Sources et licences : Cotonou, Test" in txt
    assert "Nombre d'éléments générés : 5." in txt
