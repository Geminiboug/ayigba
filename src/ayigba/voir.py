"""Visionneuse de carte : UN fichier HTML autonome (sans serveur, sans réseau) pour regarder un projet généré.

`ayigba voir projects/<ville>` écrit `reports/voir.html` : la carte vue de dessus (bâtiments colorés par couleur de mur,
par source de données, par hauteur ou par indice de suspicion ; routes ; points d'intérêt), les chiffres du rapport de qualité,
les erreurs et avertissements en rouge, et, si on les fournit avec `--bots`, les défauts trouvés par les bots Godot (blocages, chutes),
cliquables pour zoomer dessus. C'est la première brique de l'étape 8 (interface) : elle ne modifie rien, elle ne fait que montrer.
Elle n'utilise ni Tauri ni Rust (pas installés ici) : le même fichier pourra être ouvert plus tard dans une fenêtre Tauri.

Repère : mètres locaux autour du centre de la zone (x est, y nord), comme `routes_local.json`. Un défaut de bot (x, y, z en repère Godot)
est converti en (x, -z). LIMITES : pas de relief, pas de rejeu animé d'un bot (seulement la position du défaut), pas de validation de
correction ; les indices de suspicion viennent de `ayigba controler-detections` (à lancer avant), pas d'une vérité terrain.
"""
from __future__ import annotations

import json
from pathlib import Path

import numpy as np

from .geo import LocalFrame, read_features
from .project import Project, open_context

SOURCES = {"osm": 0, "google_25d": 1, "genere": 2, "microsoft": 3}


def _anneau(coords, frame: LocalFrame) -> list[float]:
    a = np.asarray(coords, dtype=float)
    x, y = frame.to_local(a[:, 0], a[:, 1])
    return [round(float(v), 1) for pair in zip(x, y) for v in pair]


def _polygones(geom, frame):
    if geom.geom_type == "Polygon":
        return [_anneau(geom.exterior.coords, frame)]
    if geom.geom_type == "MultiPolygon":
        return [_anneau(g.exterior.coords, frame) for g in geom.geoms]
    return []


def construire_donnees(projet_dossier: Path, fichiers_bots: list[Path] | None = None) -> dict:
    project = Project(Path(projet_dossier).resolve())
    ctx = open_context(Path(projet_dossier).resolve(), offline=True)
    frame = LocalFrame(ctx.config.bbox)
    out = project.out / "neutre"
    if not (out / "batiments.geojson").is_file():
        raise LookupError(f"Pas de résultat dans {out} : lance d'abord « ayigba generer {projet_dossier} ».")

    suspicion: dict[str, int] = {}
    ctl = project.reports / "controle_detections.json"
    if ctl.is_file():
        d = json.loads(ctl.read_text(encoding="utf-8"))
        for x in d.get("detections", []):
            suspicion[str(x["id"])] = int(x.get("score", len(x.get("indices", []))))

    batiments = []
    for g, p in read_features(out / "batiments.geojson"):
        for poly in _polygones(g, frame):
            batiments.append({"p": poly, "c": p.get("couleur_mur") or "#cccccc", "t": p.get("couleur_toit") or "#888888",
                              "h": round(float(p.get("hauteur") or 0.0), 1), "s": SOURCES.get(str(p.get("source")), 9),
                              "id": str(p.get("id", "")), "q": suspicion.get(str(p.get("id", "")), -1)})
    routes = []
    for g, p in read_features(out / "routes.geojson"):
        if g.geom_type == "LineString":
            a = np.asarray(g.coords, dtype=float)
            x, y = frame.to_local(a[:, 0], a[:, 1])
            routes.append({"p": [round(float(v), 1) for pair in zip(x, y) for v in pair], "k": str(p.get("classe", "")),
                           "w": float(p.get("largeur") or 3.0), "v": 1 if p.get("pieton") else 0, "id": str(p.get("id", ""))})
    pois = []
    pf = out / "points_interet.geojson"
    if pf.is_file():
        for g, p in read_features(pf):
            if g.geom_type == "Point":
                x, y = frame.to_local(g.x, g.y)
                pois.append([round(float(x), 1), round(float(y), 1), str(p.get("type", "")), str(p.get("nom", ""))])

    q = json.loads((project.reports / "qualite.json").read_text(encoding="utf-8")) if (project.reports / "qualite.json").is_file() else {}
    defauts = []
    for kind, cle in (("erreur", "erreurs"), ("avertissement", "avertissements")):
        for e in q.get(cle, []):
            defauts.append({"genre": kind, "texte": e if isinstance(e, str) else json.dumps(e, ensure_ascii=False)[:200]})
    for f in fichiers_bots or []:
        d = json.loads(Path(f).read_text(encoding="utf-8"))
        for e in d.get("defauts", []):
            defauts.append({"genre": "bot_" + str(e.get("genre", "?")), "texte": f"{e.get('genre')} sur {e.get('route')} ({Path(f).stem})",
                            "x": float(e["x"]), "y": -float(e["z"]), "alt": float(e["y"])})
    xs = [v for b in batiments for v in b["p"][0::2]] or [0.0]
    ys = [v for b in batiments for v in b["p"][1::2]] or [0.0]
    return {
        "titre": f"{q.get('ville', ctx.config.city)} : {q.get('quartier', ctx.config.district)}" if q else ctx.config.city,
        "emprise": [min(xs), min(ys), max(xs), max(ys)],
        "batiments": batiments, "routes": routes, "pois": pois, "defauts": defauts,
        "chiffres": {k: q.get(k) for k in ("zone_km2", "batiments", "routes", "routes_km", "triangles", "pente_max_deg", "part_generee")}
                    | {"accessible": (q.get("marcheur") or {}).get("part_accessible"), "poches": (q.get("marcheur") or {}).get("poches_inaccessibles")},
        "non_verifie": q.get("non_verifie", []),
        "suspicion_disponible": bool(suspicion),
    }


def ecrire(projet_dossier: Path, fichiers_bots: list[Path] | None = None, sortie: Path | None = None) -> Path:
    data = construire_donnees(projet_dossier, fichiers_bots)
    sortie = Path(sortie) if sortie else Path(projet_dossier) / "reports" / "voir.html"
    sortie.parent.mkdir(parents=True, exist_ok=True)
    html = _MODELE.replace("/*DONNEES*/null", json.dumps(data, ensure_ascii=False, separators=(",", ":")))
    sortie.write_text(html, encoding="utf-8")
    return sortie


_MODELE = r"""<!doctype html>
<html lang="fr"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Carte ayigba</title>
<style>
:root{--bg:#f4f1ea;--fg:#2a2623;--mut:#6d655d;--pan:#fffdf8;--bd:#d9d2c6;--rouge:#c4281c;--acc:#9a4a1e}
@media (prefers-color-scheme:dark){:root{--bg:#1c1a18;--fg:#ece6dc;--mut:#a39a8e;--pan:#25221f;--bd:#3a3631;--rouge:#ff6b5a;--acc:#e0975f}}
*{box-sizing:border-box}body{margin:0;background:var(--bg);color:var(--fg);font:14px/1.45 system-ui,sans-serif;display:flex;height:100vh}
#cote{width:330px;max-width:42vw;overflow:auto;padding:14px;background:var(--pan);border-right:1px solid var(--bd)}
#carte{flex:1;position:relative;min-width:0}canvas{width:100%;height:100%;display:block;cursor:grab}
h1{font-size:17px;margin:0 0 2px}h2{font-size:12px;letter-spacing:.06em;text-transform:uppercase;color:var(--mut);margin:16px 0 6px}
.ch{display:grid;grid-template-columns:1fr auto;gap:2px 10px;font-variant-numeric:tabular-nums}.ch b{text-align:right}
label{display:block;margin:2px 0}select{width:100%;padding:3px;background:var(--bg);color:var(--fg);border:1px solid var(--bd)}
.def{display:block;width:100%;text-align:left;margin:3px 0;padding:5px 7px;border:1px solid var(--bd);background:var(--bg);color:var(--fg);cursor:pointer;font:inherit;font-size:12.5px}
.def.r{border-left:4px solid var(--rouge)}.def:hover{border-color:var(--acc)}
.ok{color:var(--mut)}small,.nv{color:var(--mut);font-size:12px}#info{position:absolute;left:10px;bottom:10px;background:var(--pan);border:1px solid var(--bd);padding:5px 9px;font-size:12.5px;pointer-events:none;max-width:70%}
@media (max-width:700px){body{flex-direction:column}#cote{width:100%;max-width:none;max-height:40vh;border-right:0;border-bottom:1px solid var(--bd)}}
</style></head><body>
<div id="cote"><h1 id="titre"></h1><small>Vue de dessus, mètres locaux. Glisser = déplacer, molette = zoom.</small>
<h2>Affichage</h2>
<label>Bâtiments colorés par <select id="mode"><option value="mur">couleur du mur</option><option value="toit">couleur du toit</option><option value="source">source des données</option><option value="hauteur">hauteur</option><option value="suspicion">indice de suspicion</option></select></label>
<label><input type="checkbox" id="lb" checked> bâtiments</label><label><input type="checkbox" id="lr" checked> routes</label>
<label><input type="checkbox" id="lp"> points d'intérêt</label><label><input type="checkbox" id="ld" checked> défauts</label>
<h2>Rapport de qualité</h2><div class="ch" id="chiffres"></div>
<h2>Erreurs, avertissements, défauts des bots</h2><div id="defauts"></div>
<h2>Non vérifié</h2><div class="nv" id="nv"></div></div>
<div id="carte"><canvas id="c"></canvas><div id="info"></div></div>
<script>
const D=/*DONNEES*/null;
const $=i=>document.getElementById(i);const cv=$('c'),cx=cv.getContext('2d');
$('titre').textContent=D.titre;
const noms={zone_km2:'Surface (km²)',batiments:'Bâtiments',routes:'Routes',routes_km:'Routes (km)',triangles:'Triangles',pente_max_deg:'Pente max (°)',part_generee:'Part générée',accessible:'Accessible à pied',poches:'Poches inaccessibles'};
$('chiffres').innerHTML=Object.keys(noms).filter(k=>D.chiffres[k]!=null).map(k=>{let v=D.chiffres[k];if(k==='part_generee'||k==='accessible')v=(v*100).toFixed(1)+' %';else if(typeof v==='number'&&k!=='triangles')v=v.toLocaleString('fr-FR');else if(k==='triangles')v=v.toLocaleString('fr-FR');return `<span>${noms[k]}</span><b>${v}</b>`}).join('');
$('nv').innerHTML=D.non_verifie.map(t=>'• '+t).join('<br>')||'—';
let [x0,y0,x1,y1]=D.emprise;let sc=1,ox=0,oy=0,dpr=1;
function fit(){const w=cv.clientWidth,h=cv.clientHeight;sc=Math.min(w/(x1-x0),h/(y1-y0))*.95;ox=w/2-(x0+x1)/2*sc;oy=h/2+(y0+y1)/2*sc}
function X(x){return x*sc+ox}function Y(y){return oy-y*sc}
function lerp(a,b,t){return a+(b-a)*t}
function rampe(t){t=Math.max(0,Math.min(1,t));const c=[[247,232,170],[240,160,70],[196,70,40],[90,20,50]];const i=Math.min(2,Math.floor(t*3)),f=t*3-i;return `rgb(${c[i].map((v,k)=>Math.round(lerp(v,c[i+1][k],f))).join(',')})`}
const SRC=['#c9a063','#4f8fc0','#b04fa0','#5aa75a','#999'];
function couleur(b){const m=$('mode').value;if(m==='mur')return b.c;if(m==='toit')return b.t;if(m==='source')return SRC[b.s]||SRC[4];if(m==='hauteur')return rampe(b.h/20);if(b.q<0)return '#bbb';return rampe(b.q/8)}
const RK={motorway:'#c0392b',trunk:'#c0392b',primary:'#d9822b',secondary:'#c9a227',tertiary:'#999',residential:'#aaa',path:'#8a9a5b',footway:'#8a9a5b'};
function dessiner(){dpr=window.devicePixelRatio||1;const w=cv.clientWidth,h=cv.clientHeight;if(cv.width!==w*dpr){cv.width=w*dpr;cv.height=h*dpr}cx.setTransform(dpr,0,0,dpr,0,0);
cx.fillStyle=getComputedStyle(document.body).backgroundColor;cx.fillRect(0,0,w,h);
if($('lr').checked)for(const r of D.routes){cx.strokeStyle=RK[r.k]||'#9a9a9a';cx.lineWidth=Math.max(.6,r.w*sc*(r.v?1:.7));cx.beginPath();const p=r.p;cx.moveTo(X(p[0]),Y(p[1]));for(let i=2;i<p.length;i+=2)cx.lineTo(X(p[i]),Y(p[i+1]));cx.stroke()}
if($('lb').checked)for(const b of D.batiments){const p=b.p;cx.beginPath();cx.moveTo(X(p[0]),Y(p[1]));for(let i=2;i<p.length;i+=2)cx.lineTo(X(p[i]),Y(p[i+1]));cx.closePath();cx.fillStyle=couleur(b);cx.fill();if(sc>2){cx.strokeStyle='rgba(0,0,0,.35)';cx.lineWidth=.6;cx.stroke()}}
if($('lp').checked){cx.fillStyle='#1a6fb5';for(const p of D.pois){cx.beginPath();cx.arc(X(p[0]),Y(p[1]),2.5,0,7);cx.fill()}}
if($('ld').checked)for(const d of D.defauts){if(d.x==null)continue;const R=getComputedStyle(document.documentElement).getPropertyValue('--rouge');cx.strokeStyle=R;cx.fillStyle=R+'55';cx.lineWidth=2;cx.beginPath();cx.arc(X(d.x),Y(d.y),9,0,7);cx.fill();cx.stroke()}
const m=100*sc;cx.fillStyle=getComputedStyle(document.body).color;cx.fillRect(12,h-24,m,3);cx.font='11px system-ui';cx.fillText('100 m',12,h-30)}
function aller(x,y){sc=Math.max(sc,6);ox=cv.clientWidth/2-x*sc;oy=cv.clientHeight/2+y*sc;dessiner()}
$('defauts').innerHTML=D.defauts.length?D.defauts.map((d,i)=>`<button class="def ${d.genre.startsWith('avert')?'':'r'}" data-i="${i}">${d.genre} : ${d.texte}${d.x!=null?' <small>('+d.x.toFixed(0)+', '+d.y.toFixed(0)+')</small>':''}</button>`).join(''):'<span class="ok">Aucune erreur ni aucun avertissement dans le rapport. Pour voir les défauts des bots : <code>ayigba voir &lt;projet&gt; --bots rapport.json</code>.</span>';
$('defauts').onclick=e=>{const b=e.target.closest('.def');if(!b)return;const d=D.defauts[+b.dataset.i];if(d.x!=null)aller(d.x,d.y)};
let drag=null;cv.onmousedown=e=>{drag=[e.clientX,e.clientY,ox,oy];cv.style.cursor='grabbing'};window.onmouseup=()=>{drag=null;cv.style.cursor='grab'};
cv.onmousemove=e=>{if(drag){ox=drag[2]+e.clientX-drag[0];oy=drag[3]+e.clientY-drag[1];dessiner()}else survol(e)};
cv.onwheel=e=>{e.preventDefault();const r=cv.getBoundingClientRect(),mx=e.clientX-r.left,my=e.clientY-r.top,f=e.deltaY<0?1.2:1/1.2;ox=mx-(mx-ox)*f;oy=my-(my-oy)*f;sc*=f;dessiner()};
function dans(p,x,y){let c=false;for(let i=0,j=p.length-2;i<p.length;j=i,i+=2){const xi=p[i],yi=p[i+1],xj=p[j],yj=p[j+1];if((yi>y)!==(yj>y)&&x<(xj-xi)*(y-yi)/(yj-yi)+xi)c=!c}return c}
function survol(e){const r=cv.getBoundingClientRect(),x=(e.clientX-r.left-ox)/sc,y=(oy-(e.clientY-r.top))/sc;let t='';for(const b of D.batiments){const p=b.p;if(dans(p,x,y)){t=`Bâtiment ${b.id} : ${b.h} m, ${['OSM','Google 2.5D','généré','Microsoft','?'][b.s]}`+(b.q>=0?`, suspicion ${b.q}`:'')+`, mur ${b.c}`;break}}$('info').style.display=t?'block':'none';$('info').textContent=t}
for(const i of ['mode','lb','lr','lp','ld'])$(i).onchange=dessiner;window.onresize=()=>{fit();dessiner()};
if(!D.suspicion_disponible)document.querySelector('#mode option[value=suspicion]').textContent='indice de suspicion (lancer controler-detections)';
fit();dessiner();
</script></body></html>
"""
