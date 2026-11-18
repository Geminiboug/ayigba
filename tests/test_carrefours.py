"""Tests du module carrefours. Aucun accès réseau : rues synthétiques en coordonnées métriques."""
import math

import pytest
from shapely.geometry import LineString, Point, box
from shapely.ops import unary_union

from ayigba import carrefours as C


def P(classe="primary", largeur=8.0, **kw):
    d = {"classe": classe, "largeur": largeur, "revetement": "pave", "tunnel": False, "pont": False,
         "pieton": False, "rond_point": False}
    d.update(kw)
    return d


def chaussee_de(routes):
    return unary_union([g.buffer(p["largeur"] / 2.0, cap_style="flat") for g, p in routes])


def croix(long=50.0, p1=None, p2=None):
    return [(LineString([(-long, 0), (long, 0)]), p1 or P("primary", 8.0)),
            (LineString([(0, -long), (0, long)]), p2 or P("secondary", 7.0))]


def pieces(g):
    return list(g.geoms) if hasattr(g, "geoms") else [g]


# 1) croisement en +
def test_croisement_en_plus():
    n = C.noeuds(croix())
    assert len(n) == 1
    cf = n[0]
    assert cf.point.distance(Point(0, 0)) < 1e-6
    assert len(cf.bras) == 4
    for b in cf.bras:
        assert math.hypot(*b.direction) == pytest.approx(1.0)
    for i, a in enumerate(cf.bras):
        opposes = [b for b in cf.bras[i + 1:] if a.direction[0] * b.direction[0] + a.direction[1] * b.direction[1] < -0.99]
        assert len(opposes) <= 1
    # chaque bras a son opposé
    for a in cf.bras:
        assert any(a.direction[0] * b.direction[0] + a.direction[1] * b.direction[1] < -0.99 for b in cf.bras)


# 2) T
def test_carrefour_en_t():
    routes = [(LineString([(-50, 0), (50, 0)]), P()), (LineString([(0, 0), (0, 50)]), P("secondary", 7.0))]
    n = C.noeuds(routes)
    assert len(n) == 1
    assert len(n[0].bras) == 3


# 3) prolongement
def test_prolongement_pas_un_carrefour():
    routes = [(LineString([(-50, 0), (0, 0)]), P()), (LineString([(0, 0), (50, 0)]), P())]
    assert C.noeuds(routes) == []


# 4) rues non éligibles
@pytest.mark.parametrize("cle,val", [("tunnel", True), ("pont", True), ("pieton", True),
                                     ("revetement", "terre"), ("rond_point", True)])
def test_rues_non_eligibles(cle, val):
    routes = [(LineString([(-50, 0), (50, 0)]), P()), (LineString([(0, -50), (0, 50)]), P(**{cle: val}))]
    assert C.noeuds(routes) == []
    # même une rue éligible de plus ne fait pas un carrefour avec la rue exclue
    routes.append((LineString([(0, 0), (30, 30)]), P(**{cle: val})))
    assert C.noeuds(routes) == []


# 5) fusion des points proches
def test_points_proches_fusionnes():
    routes = [(LineString([(-50, 0), (50, 0)]), P()), (LineString([(0, -50), (0, 50)]), P()),
              (LineString([(1.0, -50), (1.0, 50)]), P())]
    assert len(C.noeuds(routes)) == 1


def test_points_proches_fusionnes_bras_dedoubles():
    routes = [(LineString([(-50, 0), (50, 0)]), P()), (LineString([(0, -50), (0, 50)]), P()),
              (LineString([(1.0, -50), (1.0, 50)]), P())]
    assert len(C.noeuds(routes)[0].bras) == 4


def test_points_eloignes_non_fusionnes():
    routes = [(LineString([(-50, 0), (50, 0)]), P()), (LineString([(0, -50), (0, 50)]), P()),
              (LineString([(10.0, -50), (10.0, 50)]), P())]
    assert len(C.noeuds(routes)) == 2


# 6) arrondir
def test_arrondir_ajoute_surface_pres_du_croisement():
    routes = croix()
    ch = chaussee_de(routes)
    n = C.noeuds(routes)
    a = C.arrondir(ch, n)
    assert a is not None and a.area > 0
    assert a.area < 80.0
    for p in pieces(a):
        assert p.intersects(ch)
        assert p.distance(n[0].point) <= 16.0


def test_arrondir_ne_comble_pas_chaussees_paralleles():
    par = unary_union([LineString([(0, 0), (60, 0)]).buffer(3), LineString([(0, 11), (60, 11)]).buffer(3)])
    cf = C.Carrefour(Point(30, 5))
    assert par.buffer(-0.01).geom_type == "MultiPolygon"  # bien deux chaussées séparées (espace de 5 m)
    assert C.arrondir(par, [cf]) is None


def test_arrondir_ne_comble_pas_un_terre_plein():
    ch = box(0, 0, 60, 20).difference(box(5, 8, 55, 13))  # terre-plein de 50 x 5 m
    cf = C.Carrefour(Point(30, 10))
    a = C.arrondir(ch, [cf])
    assert a is None or not a.intersects(box(10, 8.5, 50, 12.5))


def test_arrondir_ne_comble_pas_un_petit_ilot():
    # îlot de 6 x 6 m (36 m2, sous le seuil de 80 m2) au milieu d'une grande chaussée, près d'un carrefour
    ch = box(0, 0, 40, 40).difference(box(17, 17, 23, 23))
    cf = C.Carrefour(Point(20, 20))
    a = C.arrondir(ch, [cf])
    assert a is None or not a.intersects(box(17.5, 17.5, 22.5, 22.5))


def test_arrondir_none_sans_carrefour_ou_rayon_nul():
    routes = croix()
    ch = chaussee_de(routes)
    n = C.noeuds(routes)
    assert C.arrondir(ch, []) is None
    assert C.arrondir(ch, n, rayon_m=0) is None
    assert C.arrondir(None, n) is None


# 7) passages
def _nb_attendu(w):
    return int((w - 2 * 0.8) // 1.0) + 1


def test_passages_nombre_de_bandes():
    routes = croix()
    ch = chaussee_de(routes)
    z = C.passages(C.noeuds(routes), routes, ch)
    assert z is not None
    attendu = 2 * _nb_attendu(8.0) + 2 * _nb_attendu(7.0)
    assert len(pieces(z)) == attendu == 26


def test_passages_bandes_dans_la_chaussee():
    routes = croix()
    ch = chaussee_de(routes)
    z = C.passages(C.noeuds(routes), routes, ch)
    sure = ch.buffer(-0.05)
    assert all(sure.contains(p) for p in pieces(z))
    assert all(p.area == pytest.approx(1.5) for p in pieces(z))


def test_passages_aucun_pour_classe_residentielle():
    routes = croix(p1=P("residential", 8.0), p2=P("residential", 7.0))
    assert C.passages(C.noeuds(routes), routes, chaussee_de(routes)) is None


def test_passages_seulement_grandes_classes():
    # une grande rue croisée par une résidentielle : bandes sur les 2 bras de la grande seulement
    routes = croix(p1=P("primary", 8.0), p2=P("residential", 7.0))
    z = C.passages(C.noeuds(routes), routes, chaussee_de(routes))
    assert len(pieces(z)) == 2 * _nb_attendu(8.0)


def test_passages_aucun_pour_rue_trop_etroite():
    routes = croix(p1=P("primary", 4.5), p2=P("secondary", 4.0))
    assert C.passages(C.noeuds(routes), routes, chaussee_de(routes)) is None


def test_passages_aucun_si_bras_trop_court():
    routes = croix(long=8.0)  # 8 m < 5,5 + 1,5 + 1,5
    n = C.noeuds(routes)
    assert len(n) == 1
    assert C.passages(n, routes, chaussee_de(routes)) is None


def test_passages_sans_carrefour():
    routes = croix()
    assert C.passages([], routes, chaussee_de(routes)) is None


# 8) déterminisme
def test_determinisme():
    routes = croix() + [(LineString([(30, 0), (30, 40)]), P("tertiary", 6.0))]
    ch = chaussee_de(routes)
    n1, n2 = C.noeuds(routes), C.noeuds(routes)
    assert len(n1) == len(n2)
    for a, b in zip(n1, n2):
        assert a.point.equals(b.point)
        assert [(x.ligne, x.direction, x.longueur) for x in a.bras] == [(x.ligne, x.direction, x.longueur) for x in b.bras]
    a1, a2 = C.arrondir(ch, n1), C.arrondir(ch, n2)
    assert a1 is not None and a1.equals(a2)
    z1, z2 = C.passages(n1, routes, ch), C.passages(n2, routes, ch)
    assert z1 is not None and z1.equals(z2)
