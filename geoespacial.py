# ============================================================
#   PARTE 1 / 2  —  BACKEND COMPLETO + LOGIN + SELECTOR
# ============================================================

import os
import re
import unicodedata
import json
import pandas as pd
import numpy as np
from flask import (
    Flask,
    render_template_string,
    request,
    jsonify,
    redirect,
    url_for,
    session,
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
    except Exception:
        key = f"{lat},{lon}"
    return address_cache.get(key, "Dirección no encontrada")


# ============================================================
# 2. CARGAR EXCEL PRINCIPAL (OFICINAS + ISLAS + AGENTES)
# ============================================================
BASE_DIR = os.path.dirname(__file__)
excel_main = os.path.join(BASE_DIR, "data", "Mapa Geoespacial ATM (1) (1).xlsx")

if not os.path.exists(excel_main):
    raise FileNotFoundError("No encontré archivo Excel de ATMs.")

raw = pd.read_excel(excel_main)


def normalize_col(s):
    s = str(s)
    s = unicodedata.normalize("NFKD", s)
    s = s.encode("ascii", "ignore").decode("utf-8")
    s = s.upper().strip()
    s = re.sub(r"[^A-Z0-9 ]+", " ", s)
    return re.sub(r"\s+", " ", s).strip()


norm_map = {normalize_col(c): c for c in raw.columns}


def find_col(keys):
    for norm, orig in norm_map.items():
        for k in keys:
            if k in norm:
                return orig
    return None


COL_ATM = find_col(["COD_ATM", "ATM"]) or "ATM"
COL_NAME = find_col(["NOMBRE", "CAJERO"]) or None
COL_DEPT = find_col(["DEPARTAMENTO"]) or "DEPARTAMENTO"
COL_PROV = find_col(["PROVINCIA"]) or "PROVINCIA"
COL_DIST = find_col(["DISTRITO"]) or "DISTRITO"
COL_LAT = find_col(["LATITUD", "LAT"]) or "LATITUD"
COL_LON = find_col(["LONGITUD", "LON"]) or "LONGITUD"
COL_DIV = find_col(["DIVISION", "DIVISIÓN"]) or "DIVISIÓN"
COL_TIPO = find_col(["TIPO"]) or "TIPO"
COL_UBIC = find_col(["UBICACION", "UBICACIÓN"]) or "UBICACION_INTERNA"
PROM_COL = find_col(["PROM", "PROMEDIO"]) or None

if PROM_COL is None:
    raw["PROM_FAKE"] = 0.0
    PROM_COL = "PROM_FAKE"

df = raw.copy()

df[COL_LAT] = pd.to_numeric(df[COL_LAT], errors="coerce")
df[COL_LON] = pd.to_numeric(df[COL_LON], errors="coerce")
df = df.dropna(subset=[COL_LAT, COL_LON]).reset_index(drop=True)

df[PROM_COL] = pd.to_numeric(df[PROM_COL], errors="coerce").fillna(0.0)
df[COL_TIPO] = df[COL_TIPO].astype(str)
df[COL_UBIC] = df[COL_UBIC].astype(str)

DEPARTAMENTOS = sorted(df[COL_DEPT].dropna().unique())
PROVINCIAS_BY_DEPT = df.groupby(COL_DEPT)[COL_PROV].apply(lambda s: sorted(s.dropna().unique())).to_dict()
DIST_BY_PROV = df.groupby(COL_PROV)[COL_DIST].apply(lambda s: sorted(s.dropna().unique())).to_dict()
DIV_BY_DEPT = df.groupby(COL_DEPT)[COL_DIV].apply(lambda s: sorted(s.dropna().unique())).to_dict()
DIV_BY_PROV = df.groupby(COL_PROV)[COL_DIV].apply(lambda s: sorted(s.dropna().unique())).to_dict()
DIV_BY_DIST = df.groupby(COL_DIST)[COL_DIV].apply(lambda s: sorted(s.dropna().unique())).to_dict()

DIVISIONES = sorted(df[COL_DIV].dropna().unique())


# ============================================================
# 3. FLASK + LOGIN
# ============================================================
app = Flask(__name__)
app.secret_key = os.getenv("SECRET_KEY", "123")
APP_USER = os.getenv("APP_USERNAME")
APP_PASS = os.getenv("APP_PASSWORD")


def login_required(f):
    @wraps(f)
    def wrap(*args, **kwargs):
        if session.get("user") != APP_USER:
            return redirect(url_for("login"))
        return f(*args, **kwargs)
    return wrap


LOGIN_TEMPLATE = """
<!DOCTYPE html>
<html>
<head>
<meta charset="utf-8">
<title>Acceso Seguro — BBVA</title>
<style>
body{
  margin:0; padding:0;
  background:url('{{ url_for('static', filename='bbva.png') }}') no-repeat center center fixed;
  background-size:cover;
  display:flex; justify-content:center; align-items:center;
  height:100vh;
  font-family:Arial;
}
.box{
  background:white;
  padding:30px;
  border-radius:12px;
  width:350px;
  text-align:center;
  box-shadow:0 10px 30px rgba(0,0,0,0.3);
}
h2{ margin:0 0 20px 0; color:#1464A5; }
input{ width:100%; padding:10px; margin:8px 0; border-radius:8px; border:1px solid #ccc; }
button{
  width:100%; padding:10px; border:none; border-radius:8px;
  background:#1464A5; color:white; font-weight:bold;
}
.error{ color:red; margin-bottom:10px; }
</style>
</head>
<body>
<div class="box">
<h2>Iniciar Sesión</h2>
{% if error %}<div class="error">{{error}}</div>{% endif %}
<form method="post">
<input name="username" placeholder="Usuario" required>
<input name="password" type="password" placeholder="Contraseña" required>
<button>Ingresar</button>
</form>
</div>
</body>
</html>
"""


@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        u = request.form.get("username")
        p = request.form.get("password")

        if u == APP_USER and p == APP_PASS:
            session.clear()
            session["user"] = u
            return redirect("/selector")

        return render_template_string(LOGIN_TEMPLATE, error="Credenciales incorrectas")

    return render_template_string(LOGIN_TEMPLATE)


@app.route("/logout")
def logout():
    session.clear()
    return redirect("/login")


# ============================================================
# 4. SELECTOR DE CAPAS (IMÁGENES GRANDES)
# ============================================================
SELECTOR_TEMPLATE = """
<!DOCTYPE html>
<html>
<head>
<meta charset="utf-8">
<title>Selector de Capas — BBVA</title>
<style>
body{
  background:#eef4fb;
  font-family:Arial;
  padding:40px;
  text-align:center;
}
.grid{
  margin-top:40px;
  display:flex;
  justify-content:center;
  gap:50px;
}
.card{
  width:380px;
  height:320px;
  background:white;
  border-radius:22px;
  box-shadow:0 10px 30px rgba(0,0,0,0.2);
  cursor:pointer;
  transition:0.2s;
  padding:14px;
}
.card:hover{
  transform:scale(1.03);
}
.card img{
  width:100%;
  height:230px;
  border-radius:16px;
  object-fit:cover;
}
.card-title{
  margin-top:10px;
  font-size:22px;
  font-weight:bold;
  color:#072146;
}
</style>
</head>
<body>

<h1>Seleccione la capa</h1>

<div class="grid">

  <div class="card" onclick="location.href='/mapa/oficinas'">
    <img src="{{ url_for('static', filename='oficina.png') }}">
    <div class="card-title">🏦 Oficinas</div>
  </div>

  <div class="card" onclick="location.href='/mapa/islas'">
    <img src="{{ url_for('static', filename='isla.png') }}">
    <div class="card-title">🌐 Islas</div>
  </div>

  <div class="card" onclick="location.href='/mapa/agentes'">
    <img src="{{ url_for('static', filename='agente.png') }}">
    <div class="card-title">🧍 Agentes</div>
  </div>

</div>

</body>
</html>
"""


@app.route("/selector")
@login_required
def selector():
    return render_template_string(SELECTOR_TEMPLATE)


# ============================================================
# 5. MAPA POR CAPA
# ============================================================
@app.route("/mapa/<tipo>")
@login_required
def mapa_tipo(tipo):
    if tipo not in ["oficinas", "islas", "agentes"]:
        return "No existe esa capa", 404

    return render_template_string(
        TEMPLATE_MAPA,
        tipo_mapa=tipo,
        departamentos=DEPARTAMENTOS,
        provincias_by_dept=PROVINCIAS_BY_DEPT,
        dist_by_prov=DIST_BY_PROV,
        divisiones=DIVISIONES,
        div_by_dept=DIV_BY_DEPT,
        div_by_prov=DIV_BY_PROV,
        div_by_dist=DIV_BY_DIST,
        initial_center=df[[COL_LAT, COL_LON]].mean().tolist(),
        initial_zoom=6,
    )


# ============================================================
# 6. API PARA OBTENER PUNTOS FILTRADOS
# ============================================================
@app.route("/api/points")
@login_required
def api_points():
    tipo = request.args.get("tipo", "")
    dpto = request.args.get("departamento", "").upper()
    prov = request.args.get("provincia", "").upper()
    dist = request.args.get("distrito", "").upper()
    divi = request.args.get("division", "").upper()

    dff = df.copy()

    dff[COL_DEPT] = dff[COL_DEPT].astype(str).str.upper()
    dff[COL_PROV] = dff[COL_PROV].astype(str).str.upper()
    dff[COL_DIST] = dff[COL_DIST].astype(str).str.upper()
    dff[COL_UBIC] = dff[COL_UBIC].astype(str).str.upper()
    dff[COL_TIPO] = dff[COL_TIPO].astype(str).str.upper()

    if tipo == "oficinas":
        dff = dff[dff[COL_UBIC].str.contains("OFICINA")]
    elif tipo == "islas":
        dff = dff[dff[COL_UBIC].str.contains("ISLA")]
    elif tipo == "agentes":
        dff = dff[dff[COL_UBIC].str.contains("AGENTE")]

    if dpto:
        dff = dff[dff[COL_DEPT] == dpto]
    if prov:
        dff = dff[dff[COL_PROV] == prov]
    if dist:
        dff = dff[dff[COL_DIST] == dist]
    if divi:
        dff = dff[dff[COL_DIV] == divi]

    puntos = []
    for _, r in dff.iterrows():
        puntos.append({
            "lat": float(r[COL_LAT]),
            "lon": float(r[COL_LON]),
            "atm": str(r[COL_ATM]),
            "nombre": str(r[COL_NAME] or r[COL_ATM]),
            "promedio": float(r[PROM_COL]),
            "division": str(r[COL_DIV]),
            "tipo": str(r[COL_TIPO]),
            "ubicacion": str(r[COL_UBIC]),
            "departamento": str(r[COL_DEPT]),
            "provincia": str(r[COL_PROV]),
            "distrito": str(r[COL_DIST]),
            "direccion": get_address(r[COL_LAT], r[COL_LON]),
        })

    return jsonify(puntos)


# ============================================================
# 7. TEMPLATE_MAPA (PARTE 2)
# ============================================================


TEMPLATE_MAPA = """
<!doctype html>
<html>
<head>
<meta charset="utf-8">
<title>Mapa BBVA — {{ tipo_mapa|upper }}</title>

<link rel="stylesheet" href="https://unpkg.com/leaflet@1.9.4/dist/leaflet.css"/>
<link rel="stylesheet" href="https://unpkg.com/leaflet.markercluster@1.5.3/dist/MarkerCluster.css"/>
<link rel="stylesheet" href="https://unpkg.com/leaflet.markercluster@1.5.3/dist/MarkerCluster.Default.css"/>

<style>
body{
  margin:0; background:#eef4fb;
  font-family:Arial,Helvetica,sans-serif;
}
header{
  height:70px; background:#003366; color:white;
  display:flex; justify-content:center; align-items:center;
  position:relative;
  box-shadow:0 6px 18px rgba(0,0,0,0.25);
}
.logout{
  position:absolute; right:20px; top:20px;
  padding:8px 16px; border-radius:8px;
  background:#1464A5; color:white; text-decoration:none;
  font-weight:bold;
}
.main{
  display:flex; padding:20px; gap:20px;
}
#map{
  flex:1; height:78vh;
  border-radius:12px;
  box-shadow:0 10px 28px rgba(0,0,0,0.25);
}
.side{
  width:380px;
}

/* PANEL RESUMEN */
.side-card{
  background:white; padding:20px;
  border-radius:12px;
  box-shadow:0 6px 22px rgba(0,0,0,0.12);
  margin-bottom:10px;
  font-size:14px;
}

/* PANEL ATM */
.side-card-atm{
  background:white; padding:24px;
  border-radius:12px;
  box-shadow:0 10px 30px rgba(0,0,0,0.25);
  white-space:pre-line;
  font-family:"Consolas","Fira Code",monospace;
  font-size:15px;
  border-left:6px solid #1464A5;
}
.btn-small{
  margin-top:14px; padding:10px 18px;
  background:#1464A5; border:none;
  border-radius:8px; color:white;
  font-weight:600;
}
.hidden { display:none; }

</style>
</head>

<body>

<header>
  <h2>Mapa BBVA — {{ tipo_mapa|upper }}</h2>
  <a class="logout" href="/logout">Cerrar sesión</a>
</header>

<div class="main">

  <div id="map"></div>

  <div class="side">

    <div id="panelResumen" class="side-card">
      <h3>Resumen — {{ tipo_mapa|capitalize }}</h3>
      <b>Promedio total:</b> <span id="resPromedio">0</span>
      <hr>
      <b>Total ATMs:</b> <span id="resTotal">0</span><br>
      <b>Dispensador:</b> <span id="resDisp">0</span><br>
      <b>Monedero:</b> <span id="resMon">0</span><br>
      <b>Reciclador:</b> <span id="resRec">0</span><br>
    </div>

    <div id="panelATM" class="side-card-atm hidden">
      <h3>ATM Seleccionado</h3>
      <div id="atmDetalle"></div>
      <button id="btnVolver" class="btn-small">VOLVER</button>
    </div>

  </div>

</div>

<script src="https://unpkg.com/leaflet@1.9.4/dist/leaflet.js"></script>
<script src="https://unpkg.com/leaflet.markercluster@1.5.3/dist/leaflet.markercluster.js"></script>

<script>
const PROV_BY_DEPT = {{ provincias_by_dept|tojson }};
const DIST_BY_PROV = {{ dist_by_prov|tojson }};
const TIPO_MAPA = "{{ tipo_mapa }}";
const INITIAL_CENTER = [{{ initial_center[0] }}, {{ initial_center[1] }}];

const map = L.map('map').setView(INITIAL_CENTER, {{ initial_zoom }});
L.tileLayer('https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png', {maxZoom:19}).addTo(map);

const markers = L.markerClusterGroup();
markers.addTo(map);

// ICONO
function getIcon(pt){
  const ub = (pt.ubicacion||"").toUpperCase();

  if(ub.includes("OFICINA"))
    return L.divIcon({html:"<div style='font-size:32px'>🏦</div>", iconSize:[36,36]});

  if(ub.includes("ISLA"))
    return L.divIcon({html:"<div style='font-size:32px'>🌐</div>", iconSize:[36,36]});

  if(ub.includes("AGENTE"))
    return L.divIcon({html:"<div style='font-size:32px'>🧍</div>", iconSize:[36,36]});

  const color = (pt.promedio||0)>=4 ? "red":"green";
  return L.divIcon({
    html:`<div style='width:18px;height:18px;background:${color};border-radius:50%'></div>`
  });
}

const panelResumen = document.getElementById("panelResumen");
const panelATM = document.getElementById("panelATM");
const atmDetalle = document.getElementById("atmDetalle");

function showATMPanel(pt){
  atmDetalle.textContent = `
ATM: ${pt.atm}
Nombre: ${pt.nombre}
Dirección: ${pt.direccion}
División: ${pt.division}
Tipo: ${pt.tipo}
Ubicación: ${pt.ubicacion}

Dept / Prov / Dist:
${pt.departamento} / ${pt.provincia} / ${pt.distrito}

Promedio: ${pt.promedio}
`;

  panelResumen.classList.add("hidden");
  panelATM.classList.remove("hidden");
}

document.getElementById("btnVolver").onclick = ()=>{
  panelATM.classList.add("hidden");
  panelResumen.classList.remove("hidden");
};

async function fetchPoints(){
  markers.clearLayers();

  const q = `tipo=${TIPO_MAPA}&departamento=${selDepartamento?.value||""}&provincia=${selProvincia?.value||""}&distrito=${selDistrito?.value||""}&division=${selDivision?.value||""}`;
  const res = await fetch('/api/points?'+q);
  const data = await res.json();

  let total=0, disp=0, mon=0, rec=0, sumProm=0;

  data.forEach(pt=>{
    total++;
    sumProm += pt.promedio || 0;

    if(pt.tipo.includes("DISP")) disp++;
    if(pt.tipo.includes("MON")) mon++;
    if(pt.tipo.includes("REC")) rec++;

    const m = L.marker([pt.lat, pt.lon], {icon:getIcon(pt)});
    m.on("click", ()=> showATMPanel(pt));
    markers.addLayer(m);
  });

  document.getElementById("resTotal").innerText = total;
  document.getElementById("resPromedio").innerText = sumProm;
  document.getElementById("resDisp").innerText = disp;
  document.getElementById("resMon").innerText = mon;
  document.getElementById("resRec").innerText = rec;
}

fetchPoints();
</script>

</body>
</html>
"""