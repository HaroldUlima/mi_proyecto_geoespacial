# ============================================================
#   BACKEND COMPLETO — CARGA EXCEL, LOGIN, SELECTOR, RUTAS
# ============================================================

import os
import re
import unicodedata
import json
import pandas as pd
import numpy as np
from flask import (
    Flask, render_template_string, request,
    jsonify, redirect, url_for, session
)
from functools import wraps

# ============================================================
# 1. CACHE DE DIRECCIONES
# ============================================================
CACHE_FILE = "address_cache.json"
if os.path.exists(CACHE_FILE):
    with open(CACHE_FILE, "r", encoding="utf-8") as f:
        address_cache = json.load(f)
else:
    address_cache = {}

def get_address(lat, lon):
    try:
        key = f"{float(lat):.6f},{float(lon):.6f}"
    except:
        key = f"{lat},{lon}"
    return address_cache.get(key, "Dirección no encontrada")

# ============================================================
# 2. CARGAR EXCEL PRINCIPAL
# ============================================================
BASE_DIR = os.path.dirname(__file__)
excel_main = os.path.join(BASE_DIR, "data", "Mapa Geoespacial ATM (1) (1).xlsx")

if not os.path.exists(excel_main):
    raise FileNotFoundError("⚠ No encontré el archivo Excel.")

raw = pd.read_excel(excel_main)

# Normalización de columnas
def normalize_col(s):
    s = unicodedata.normalize("NFKD", str(s))
    s = s.encode("ascii", "ignore").decode("utf-8")
    s = re.sub(r"[^A-Za-z0-9 ]+", " ", s.upper().strip())
    return re.sub(r"\s+", " ", s)

norm_map = {normalize_col(c): c for c in raw.columns}

def find_col(names):
    for norm, orig in norm_map.items():
        if any(n in norm for n in names):
            return orig
    return None

COL_ATM  = find_col(["COD_ATM", "ATM"]) or "ATM"
COL_NAME = find_col(["NOMBRE", "CAJERO"])
COL_DEPT = find_col(["DEPARTAMENTO"]) or "DEPARTAMENTO"
COL_PROV = find_col(["PROVINCIA"]) or "PROVINCIA"
COL_DIST = find_col(["DISTRITO"])   or "DISTRITO"
COL_LAT  = find_col(["LATITUD", "LAT"]) or "LATITUD"
COL_LON  = find_col(["LONGITUD", "LON"]) or "LONGITUD"
COL_DIV  = find_col(["DIVISION", "DIVISIÓN"]) or "DIVISIÓN"
COL_TIPO = find_col(["TIPO"]) or "TIPO"
COL_UBIC = find_col(["UBICACION", "UBICACIÓN"]) or "UBICACION_INTERNA"
PROM_COL = find_col(["PROMEDIO", "PROM"])

if PROM_COL is None:
    raw["PROM_FAKE"] = 0
    PROM_COL = "PROM_FAKE"

# Limpieza de coordenadas
raw[COL_LAT] = (
    raw[COL_LAT].astype(str)
    .str.replace(",", ".", regex=False)
    .str.replace(r"[^\d\.\-]", "", regex=True)
    .replace("", np.nan).astype(float)
)
raw[COL_LON] = (
    raw[COL_LON].astype(str)
    .str.replace(",", ".", regex=False)
    .str.replace(r"[^\d\.\-]", "", regex=True)
    .replace("", np.nan).astype(float)
)

df = raw.dropna(subset=[COL_LAT, COL_LON]).copy()
df[PROM_COL] = pd.to_numeric(df[PROM_COL], errors="coerce").fillna(0)

# Filtros jerárquicos
DEPARTAMENTOS   = sorted(df[COL_DEPT].dropna().unique())
PROVINCIAS_BY_DEPT = df.groupby(COL_DEPT)[COL_PROV].apply(lambda x: sorted(x.dropna().unique())).to_dict()
DIST_BY_PROV       = df.groupby(COL_PROV)[COL_DIST].apply(lambda x: sorted(x.dropna().unique())).to_dict()
DIV_BY_DEPT        = df.groupby(COL_DEPT)[COL_DIV].apply(lambda x: sorted(x.dropna().unique())).to_dict()
DIV_BY_PROV        = df.groupby(COL_PROV)[COL_DIV].apply(lambda x: sorted(x.dropna().unique())).to_dict()
DIV_BY_DIST        = df.groupby(COL_DIST)[COL_DIV].apply(lambda x: sorted(x.dropna().unique())).to_dict()

DIVISIONES = sorted(df[COL_DIV].dropna().unique())

# ============================================================
# 3. FLASK + LOGIN
# ============================================================
app = Flask(__name__)
app.secret_key = os.getenv("SECRET_KEY", "local_fallback")

APP_USER = os.getenv("APP_USERNAME")
APP_PASS = os.getenv("APP_PASSWORD")

@app.after_request
def add_header(r):
    r.headers["Cache-Control"] = "no-store"
    return r

# Template simple de login
LOGIN_TEMPLATE = """
<!DOCTYPE html>
<html>
<body>
<h2>LOGIN BBVA</h2>
<form method="post">
<input name="username" placeholder="Usuario">
<input name="password" placeholder="Contraseña" type="password">
<button>Entrar</button>
</form>
</body>
</html>
"""

def login_required(f):
    @wraps(f)
    def wrap(*a, **k):
        if session.get("user") != APP_USER:
            return redirect("/login")
        return f(*a, **k)
    return wrap

@app.route("/login", methods=["GET","POST"])
def login():
    if request.method == "POST":
        if request.form["username"] == APP_USER and request.form["password"] == APP_PASS:
            session["user"] = APP_USER
            return redirect("/selector")
    return render_template_string(LOGIN_TEMPLATE)

@app.route("/logout")
def logout():
    session.clear()
    return redirect("/login")

# ============================================================
# 4. SELECTOR DE CAPAS
# ============================================================
SELECTOR_TEMPLATE = """
<h1>Selector de capas</h1>
<a href="/mapa/oficinas">Oficinas</a><br>
<a href="/mapa/islas">Islas</a><br>
<a href="/mapa/agentes">Agentes</a><br>
"""

@app.route("/selector")
@login_required
def selector():
    return render_template_string(SELECTOR_TEMPLATE)


# ============================================================
# 5. TEMPLATE MAPA COMPLETO
# ============================================================
TEMPLATE_MAPA = """
<!doctype html>
<html>
<head>
<meta charset="utf-8">
<title>Mapa BBVA — {{ tipo_mapa|upper }}</title>
<meta name="viewport" content="width=device-width, initial-scale=1.0">

<link rel="stylesheet" href="https://unpkg.com/leaflet@1.9.4/dist/leaflet.css"/>
<link rel="stylesheet" href="https://unpkg.com/leaflet.markercluster@1.5.3/dist/MarkerCluster.css"/>
<link rel="stylesheet" href="https://unpkg.com/leaflet.markercluster@1.5.3/dist/MarkerCluster.Default.css"/>

<style>
:root{
  --bbva-blue:#1464A5;
  --bbva-dark:#072146;
  --muted:#6b7a8a;
  --card:#ffffff;
}

html,body{
  margin:0;
  padding:0;
  height:100%;
  font-family:Inter,Arial,Helvetica,sans-serif;
  background:#eef4fb;
}

header{
  background:#003366;
  color:white;
  height:70px;
  display:flex;
  align-items:center;
  justify-content:center;
  position:relative;
  box-shadow:0 6px 18px rgba(0,0,0,0.25);
}
header h1{ margin:0; font-size:1.9rem; }

.logout{
  position:absolute;
  right:20px;
  background:#1464A5;
  color:white;
  padding:8px 16px;
  border-radius:8px;
  text-decoration:none;
  font-weight:600;
}

/* TOPBAR */
.topbar{ padding:16px 20px 8px 20px; }
.controls{
  background:white;
  padding:12px;
  border-radius:12px;
  box-shadow:0 4px 16px rgba(0,0,0,0.12);
  display:flex;
  gap:12px;
  align-items:center;
  flex-wrap:wrap;
}

.controls label{ font-size:13px; color:var(--muted); }
select{
  padding:6px 10px;
  border-radius:8px;
  border:1px solid #d0d7e3;
}

/* MAIN LAYOUT */
.main{
  display:flex;
  padding:0 20px 20px 20px;
  gap:18px;
}
#map{
  flex:1;
  height:74vh;
  border-radius:12px;
  overflow:hidden;
  box-shadow:0 8px 24px rgba(0,0,0,0.18);
}

/* SIDE PANEL */
.side{ width:330px; }
.side-card{
  background:white;
  border-radius:12px;
  padding:14px 16px;
  box-shadow:0 6px 22px rgba(0,0,0,0.12);
  margin-bottom:12px;
  font-size:13px;
}
.side-title{
  font-weight:700;
  margin-bottom:4px;
}

.side-card-atm{
  border-left:4px solid var(--bbva-blue);
  font-family:"Consolas","Fira Code",monospace;
  white-space:pre-line;
  line-height:1.35;
}

.btn-small{
  margin-top:8px;
  padding:4px 10px;
  border-radius:6px;
  border:none;
  background:var(--bbva-blue);
  color:white;
  font-size:12px;
  cursor:pointer;
}

/* ATM Colors */
.icon-round div{
  width:14px;
  height:14px;
  border-radius:50%;
  border:2px solid white;
}

.hidden{ display:none; }
</style>
</head>

<body>

<header>
  <h1>Mapa BBVA — {{ tipo_mapa|upper }}</h1>
  <a href="/logout" class="logout">Cerrar sesión</a>
</header>

<div class="topbar">
  <div class="controls">

    <label>Departamento:
      <select id="selDepartamento">
        <option value="">-- Todos --</option>
        {% for d in departamentos %}
        <option value="{{d}}">{{d}}</option>
        {% endfor %}
      </select>
    </label>

    <label>Provincia:
      <select id="selProvincia"><option value="">-- Todas --</option></select>
    </label>

    <label>Distrito:
      <select id="selDistrito"><option value="">-- Todos --</option></select>
    </label>

    <label>División:
      <select id="selDivision">
        <option value="">-- Todas --</option>
        {% for dv in divisiones %}
        <option value="{{dv}}">{{dv}}</option>
        {% endfor %}
      </select>
    </label>

    <label style="margin-left:22px;">
      <input type="checkbox" checked id="chkHeat"> Heatmap
    </label>

    <div style="flex:1"></div>
    <div style="font-size:13px;color:var(--muted);">Mostrando <span id="infoCount">--</span> ATMs</div>

  </div>
</div>

<div class="main">
  <div id="map"></div>

  <div class="side">

    <!-- PANEL RESUMEN -->
    <div id="panelResumen" class="side-card">
      <div class="side-title">Resumen</div>
      <div>Promedio total: <span id="resPromedio">0</span></div>

      <div style="margin-top:6px;font-weight:600;">ATMs</div>
      <div>Total: <span id="resTotal">0</span></div>
      <div>Dispensador: <span id="resDisp">0</span></div>
      <div>Monedero: <span id="resMon">0</span></div>
      <div>Reciclador: <span id="resRec">0</span></div>

      <div style="margin-top:10px;font-weight:600;">Leyenda:</div>
      <div>🔴 ATM ≥ 4</div>
      <div>🟢 ATM ≤ 3</div>
    </div>

    <!-- PANEL ATM -->
    <div id="panelATM" class="side-card side-card-atm hidden">
      <h3>ATM Seleccionado</h3>
      <div id="atmDetalle"></div>
      <button class="btn-small" id="btnVolver">VOLVER</button>
    </div>
  </div>
</div>

<script src="https://unpkg.com/leaflet@1.9.4/dist/leaflet.js"></script>
<script src="https://unpkg.com/leaflet.markercluster@1.5.3/dist/MarkerCluster.js"></script>
<script src="https://unpkg.com/leaflet.heat/dist/leaflet-heat.js"></script>

<script>
/* ============================================================
   VARIABLES DESDE PYTHON
============================================================ */
const PROV_BY_DEPT = {{ provincias_by_dept|tojson }};
const DIST_BY_PROV = {{ dist_by_prov|tojson }};
const DIV_BY_DEPT  = {{ div_by_dept|tojson }};
const DIV_BY_PROV  = {{ div_by_prov|tojson }};
const DIV_BY_DIST  = {{ div_by_dist|tojson }};
const TIPO_MAPA    = "{{ tipo_mapa }}";
const INITIAL_CENTER = [{{ initial_center[0] }}, {{ initial_center[1] }}];
const INITIAL_ZOOM   = {{ initial_zoom }};

/* ============================================================
   MAP + CLUSTERS + HEATMAP COLOR ROJO / VERDE
============================================================ */
const map = L.map('map').setView(INITIAL_CENTER, INITIAL_ZOOM);
L.tileLayer('https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png',{maxZoom:19}).addTo(map);

const markers = L.markerClusterGroup();
markers.addTo(map);

const heat = L.heatLayer([], {
  radius: 35,
  blur: 20,
  maxZoom: 17,
  gradient:{
    0.3:"green",
    1.0:"red"
  }
});

/* ============================================================
   DOM ELEMENTS
============================================================ */
const selDep  = document.getElementById("selDepartamento");
const selProv = document.getElementById("selProvincia");
const selDist = document.getElementById("selDistrito");
const selDiv  = document.getElementById("selDivision");
const chkHeat = document.getElementById("chkHeat");

const infoCount = document.getElementById("infoCount");
const panelResumen = document.getElementById("panelResumen");
const panelATM = document.getElementById("panelATM");
const atmDetalle = document.getElementById("atmDetalle");
const btnVolver = document.getElementById("btnVolver");

const resProm = document.getElementById("resPromedio");
const resTotal = document.getElementById("resTotal");
const resDisp = document.getElementById("resDisp");
const resMon  = document.getElementById("resMon");
const resRec  = document.getElementById("resRec");

/* ============================================================
   ICONOS
============================================================ */
function getIcon(pt){
  const color = (pt.promedio >= 4) ? "red" : "green";
  return L.divIcon({
    className:"icon-round",
    html:`<div style="background:${color};"></div>`,
    iconSize:[14,14],
    iconAnchor:[7,7]
  });
}

/* ============================================================
   PANEL ATM
============================================================ */
function showATM(pt){
  atmDetalle.textContent =
`ATM ${pt.atm}
Nombre: ${pt.nombre}
Dirección: ${pt.direccion}
División: ${pt.division}
Tipo: ${pt.tipo}
Promedio: ${pt.promedio}`;

  panelResumen.classList.add("hidden");
  panelATM.classList.remove("hidden");
}
btnVolver.onclick = ()=>{
  panelATM.classList.add("hidden");
  panelResumen.classList.remove("hidden");
};

/* ============================================================
   FILTROS JERÁRQUICOS
============================================================ */
function updateProvincias(){
  selProv.innerHTML = '<option value="">-- Todas --</option>';
  let d = selDep.value;
  if(d && PROV_BY_DEPT[d]){
    PROV_BY_DEPT[d].forEach(x=> selProv.innerHTML += `<option>${x}</option>`);
  }
  updateDistritos();
  updateDivisiones();
}

function updateDistritos(){
  selDist.innerHTML = '<option value="">-- Todos --</option>';
  let p = selProv.value;
  if(p && DIST_BY_PROV[p]){
    DIST_BY_PROV[p].forEach(x=> selDist.innerHTML += `<option>${x}</option>`);
  }
  updateDivisiones();
}

function updateDivisiones(){
  selDiv.innerHTML = '<option value="">-- Todas --</option>';
  let d = selDep.value, p = selProv.value, di = selDist.value;

  if(di && DIV_BY_DIST[di]) return DIV_BY_DIST[di].forEach(v=> selDiv.innerHTML+=`<option>${v}</option>`);
  if(p  && DIV_BY_PROV[p])  return DIV_BY_PROV[p].forEach(v => selDiv.innerHTML+=`<option>${v}</option>`);
  if(d  && DIV_BY_DEPT[d])  return DIV_BY_DEPT[d].forEach(v => selDiv.innerHTML+=`<option>${v}</option>`);
}

/* ============================================================
   FETCH + RENDER
============================================================ */
async function fetchPoints(){

  const url = `/api/points?tipo=${TIPO_MAPA}&departamento=${selDep.value}&provincia=${selProv.value}&distrito=${selDist.value}&division=${selDiv.value}`;
  const res = await fetch(url);
  const data = await res.json();

  markers.clearLayers();
  heat.setLatLngs([]);

  let heatPts=[];
  let sum=0, tot=0, disp=0, mon=0, rec=0;

  data.forEach(pt=>{
    tot++;
    sum += pt.promedio;

    if(pt.tipo.toUpperCase().includes("DISPENSADOR")) disp++;
    if(pt.tipo.toUpperCase().includes("MONEDERO")) mon++;
    if(pt.tipo.toUpperCase().includes("RECICLADOR")) rec++;

    const m = L.marker([pt.lat, pt.lon],{icon:getIcon(pt)});
    m.on("click",()=>showATM(pt));
    markers.addLayer(m);

    let inten = pt.promedio >= 4 ? 1.0 : 0.3;
    heatPts.push([pt.lat, pt.lon, inten]);
  });

  heat.setLatLngs(heatPts);

  if(chkHeat.checked){
    if(!map.hasLayer(heat)) map.addLayer(heat);
  } else {
    if(map.hasLayer(heat)) map.removeLayer(heat);
  }

  infoCount.textContent = tot;
  resProm.textContent = tot ? Math.round(sum/tot) : 0;
  resTotal.textContent = tot;
  resDisp.textContent  = disp;
  resMon.textContent   = mon;
  resRec.textContent   = rec;
}

/* ============================================================
   EVENTOS
============================================================ */
selDep.onchange = ()=>{ updateProvincias(); fetchPoints(); };
selProv.onchange = ()=>{ updateDistritos(); fetchPoints(); };
selDist.onchange = ()=>{ updateDivisiones(); fetchPoints(); };
selDiv.onchange = ()=> fetchPoints();
chkHeat.onchange = ()=> fetchPoints();

/* INIT */
updateProvincias();
fetchPoints();

</script>

</body>
</html>
"""

# ============================================================
# 6. RUTA DEL MAPA
# ============================================================
@app.route("/mapa/<tipo>")
@login_required
def mapa(tipo):

    return render_template_string(
        TEMPLATE_MAPA,
        tipo_mapa=tipo,
        departamentos=DEPARTAMENTOS,
        provincias_by_dept=PROVINCIAS_BY_DEPT,
        dist_by_prov=DIST_BY_PROV,
        div_by_dept=DIV_BY_DEPT,
        div_by_prov=DIV_BY_PROV,
        div_by_dist=DIV_BY_DIST,
        divisiones=DIVISIONES,
        initial_center=[-12.0464,-77.0428],
        initial_zoom=12
    )

# ============================================================
# 7. API POINTS
# ============================================================
@app.route("/api/points")
@login_required
def api_points():

    d = request.args.get("departamento","")
    p = request.args.get("provincia","")
    di = request.args.get("distrito","")
    dv = request.args.get("division","")
    tipo = request.args.get("tipo","")

    q = df.copy()

    if d:  q = q[q[COL_DEPT] == d]
    if p:  q = q[q[COL_PROV] == p]
    if di: q = q[q[COL_DIST] == di]
    if dv: q = q[q[COL_DIV] == dv]

    out = []
    for _,r in q.iterrows():
        out.append({
            "atm": r[COL_ATM],
            "nombre": r.get(COL_NAME,""),
            "direccion": get_address(r[COL_LAT],r[COL_LON]),
            "departamento": r[COL_DEPT],
            "provincia": r[COL_PROV],
            "distrito": r[COL_DIST],
            "division": r[COL_DIV],
            "tipo": r[COL_TIPO],
            "ubicacion": r[COL_UBIC],
            "promedio": float(r[PROM_COL]),
            "lat": float(r[COL_LAT]),
            "lon": float(r[COL_LON])
        })

    return jsonify(out)

# ============================================================
# 8. RUN LOCAL
# ============================================================
if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000, debug=True)

