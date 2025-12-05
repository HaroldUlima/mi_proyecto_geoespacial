# geoespacial.py
import os
import re
import unicodedata
import json
import pandas as pd
import numpy as np
from flask import Flask, render_template_string, request, jsonify

# ===================================================================
#  CACHE DE DIRECCIONES
# ===================================================================
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

# ===================================================================
#  CARGAR ARCHIVO EXCEL
# ===================================================================
BASE_DIR = os.path.dirname(__file__)
excel_path = os.path.join(BASE_DIR, "data", "Mapa Geoespacial ATM (1) (1).xlsx")

if not os.path.exists(excel_path):
    raise FileNotFoundError(f"No se encontró el excel en: {excel_path}")

print("✅ Usando archivo Excel:", excel_path)

# ===================================================================
#  DETECCIÓN AUTOMÁTICA DE COLUMNAS
# ===================================================================
def normalize_col(s):
    s = str(s)
    s = unicodedata.normalize("NFKD", s).encode("ascii","ignore").decode("utf-8")
    s = re.sub(r"[^A-Za-z0-9 ]+", "", s)
    return s.upper().strip()

raw = pd.read_excel(excel_path)
norm_map = {normalize_col(c): c for c in raw.columns}

def find_col(keywords):
    for k in norm_map:
        if any(word in k for word in keywords):
            return norm_map[k]
    return None

COL_ATM = find_col(["ATM"]) or "ATM"
COL_NAME = find_col(["NOMBRE", "CAJERO"])
COL_DEPT = find_col(["DEPARTAMENTO"]) or "DEPARTAMENTO"
COL_PROV = find_col(["PROVINCIA"]) or "PROVINCIA"
COL_DIST = find_col(["DISTRITO"]) or "DISTRITO"
COL_LAT  = find_col(["LAT"]) or "LAT"
COL_LON  = find_col(["LON", "LONG"]) or "LON"
PROM_COL = find_col(["PROM"]) or None
COL_DIV  = find_col(["DIVISION"]) or "DIVISION"
COL_TIPO = find_col(["TIPO"]) or "TIPO"
COL_UBIC = find_col(["UBICACION", "UBICACION INTERNA"]) or "UBICACION_INTERNA"

if PROM_COL is None:
    raw["PROM_FAKE"] = 0.0
    PROM_COL = "PROM_FAKE"

# Convertir coordenadas
df = raw.copy()
df[COL_LAT] = df[COL_LAT].astype(str).str.replace(",", ".").astype(float)
df[COL_LON] = df[COL_LON].astype(str).str.replace(",", ".").astype(float)
df = df.dropna(subset=[COL_LAT, COL_LON]).reset_index(drop=True)
df[PROM_COL] = pd.to_numeric(df[PROM_COL], errors="coerce").fillna(0.0)

print("📊 Total registros válidos:", len(df))

# ===================================================================
#  LISTAS PARA FILTROS
# ===================================================================
DEPARTAMENTOS = sorted(df[COL_DEPT].astype(str).unique())
PROVINCIAS_ALL = df.groupby(COL_DEPT)[COL_PROV].apply(lambda x: sorted(x.unique())).to_dict()
DISTRITOS_BY_PROV = df.groupby(COL_PROV)[COL_DIST].apply(lambda x: sorted(x.unique())).to_dict()
DIST_BY_DEPT = df.groupby(COL_DEPT)[COL_DIST].apply(lambda x: sorted(x.unique())).to_dict()
DIVISIONES = sorted(df[COL_DIV].astype(str).unique())

# ===================================================================
#  FLASK APP + LOGIN
# ===================================================================
from functools import wraps
from flask import redirect, url_for, session

app = Flask(__name__)
app.secret_key = os.getenv("SECRET_KEY", "local")

APP_USER = os.getenv("APP_USERNAME")
APP_PASS = os.getenv("APP_PASSWORD")

if not APP_USER or not APP_PASS:
    print("⚠️ Advertencia: APP_USERNAME o APP_PASSWORD no configurados en Render.")

def login_required(f):
    @wraps(f)
    def wrapper(*args, **kwargs):
        if session.get("user") != APP_USER:
            return redirect(url_for("login"))
        return f(*args, **kwargs)
    return wrapper

@app.after_request
def no_cache(r):
    r.headers["Cache-Control"] = "no-store"
    return r

LOGIN_TEMPLATE = """
<!DOCTYPE html>
<html>
<head>
<meta charset="utf-8">
<title>Login</title>
<style>
body{
  display:flex; align-items:center; justify-content:center;
  height:100vh; margin:0;
  background:#003366;
  font-family:Arial;
}
.box{
  background:white; padding:30px; border-radius:10px; width:300px;
  box-shadow:0 0 20px rgba(0,0,0,0.3);
}
</style>
</head>
<body>
<div class="box">
<h2>Iniciar Sesión</h2>
<form method="post">
  <input name="username" placeholder="Usuario" style="width:100%;padding:10px;"><br><br>
  <input name="password" type="password" placeholder="Contraseña" style="width:100%;padding:10px;"><br><br>
  <button style="width:100%;padding:10px;background:#1464A5;color:white;">Entrar</button>
</form>
</div>
</body>
</html>
"""

@app.route("/login", methods=["GET","POST"])
def login():
    if request.method == "POST":
        u = request.form.get("username")
        p = request.form.get("password")
        if u == APP_USER and p == APP_PASS:
            session["user"] = u
            return redirect("/")
    return LOGIN_TEMPLATE

@app.route("/logout")
def logout():
    session.clear()
    return redirect("/login")

# ===================================================================
#  TEMPLATE HTML PRINCIPAL
# ===================================================================
TEMPLATE = """
<!DOCTYPE html>
<html>
<head>
<meta charset="utf-8">
<title>Mapa de ATMs — BBVA</title>
<link rel="stylesheet" href="https://unpkg.com/leaflet@1.9.4/dist/leaflet.css"/>
<link rel="stylesheet" href="https://unpkg.com/leaflet.markercluster@1.5.3/dist/MarkerCluster.css"/>
<link rel="stylesheet" href="https://unpkg.com/leaflet.markercluster@1.5.3/dist/MarkerCluster.Default.css"/>
<style>
body{ margin:0; font-family:Arial;}
header{
  background:#003366; color:white; padding:20px;
  text-align:center; font-size:28px; font-weight:bold;
}
#top{
  padding:10px; background:#f4f4f4; display:flex; gap:10px;
}
select{ padding:5px;}
#map{ width:100%; height:80vh; }
</style>
</head>
<body>

<header>
  Mapa de ATMs — BBVA
  <a href="/logout" style="color:white; float:right; margin-right:20px; font-size:16px;">Cerrar sesión</a>
</header>

<div id="top">
  <label>Departamento:
    <select id="dep">
      <option value="">Todos</option>
      {% for d in departamentos %}
      <option>{{d}}</option>
      {% endfor %}
    </select>
  </label>

  <label>Provincia:
    <select id="prov"><option value="">Todas</option></select>
  </label>

  <label>Distrito:
    <select id="dist"><option value="">Todos</option></select>
  </label>

  <label>División:
    <select id="division">
      <option value="">Todas</option>
      {% for d in divisiones %}
      <option>{{d}}</option>
      {% endfor %}
    </select>
  </label>

  <label><input type="checkbox" id="heat" checked> Heatmap</label>

  <div style="margin-left:auto; padding:5px;">ATMs: <span id="count"></span></div>
</div>

<div id="map"></div>

<script src="https://unpkg.com/leaflet@1.9.4/dist/leaflet.js"></script>
<script src="https://unpkg.com/leaflet.markercluster@1.5.3/dist/MarkerCluster.js"></script>
<script src="https://unpkg.com/leaflet.heat/dist/leaflet-heat.js"></script>

<script>
// Datos iniciales
const PROVS = {{ provincias_all|tojson }};
const DISTS_PROV = {{ distritos_by_prov|tojson }};
const DISTS_DEP = {{ dist_by_dept|tojson }};
const CENTER = [{{ initial_center[0] }}, {{ initial_center[1] }}];
const ZOOM = {{ initial_zoom }};

// Mapa
const map = L.map("map").setView(CENTER, ZOOM);
L.tileLayer("https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png").addTo(map);

const markers = L.markerClusterGroup();
map.addLayer(markers);

const heat = L.heatLayer([], {radius:25}).addTo(map);

// Selects
const dep = document.getElementById("dep");
const prov = document.getElementById("prov");
const dist = document.getElementById("dist");
const divi = document.getElementById("division");
const chkHeat = document.getElementById("heat");
const count = document.getElementById("count");

// Actualizar provincias
dep.addEventListener("change", () => {
  prov.innerHTML = "<option value=''>Todas</option>";
  dist.innerHTML = "<option value=''>Todos</option>";
  if (PROVS[dep.value]) {
    PROVS[dep.value].forEach(p => prov.innerHTML += `<option>${p}</option>`);
  }
  load();
});

// Actualizar distritos
prov.addEventListener("change", () => {
  dist.innerHTML = "<option value=''>Todos</option>";
  if (DISTS_PROV[prov.value]) {
    DISTS_PROV[prov.value].forEach(d => dist.innerHTML += `<option>${d}</option>`);
  } else if (DISTS_DEP[dep.value]) {
    DISTS_DEP[dep.value].forEach(d => dist.innerHTML += `<option>${d}</option>`);
  }
  load();
});

dist.addEventListener("change", load);
divi.addEventListener("change", load);
chkHeat.addEventListener("change", load);

async function load() {
  const params = new URLSearchParams();
  if (dep.value) params.append("departamento", dep.value);
  if (prov.value) params.append("provincia", prov.value);
  if (dist.value) params.append("distrito", dist.value);
  if (divi.value) params.append("division", divi.value);

  const res = await fetch("/api/points?" + params.toString());
  const data = await res.json();

  markers.clearLayers();
  heat.setLatLngs([]);

  const heatPoints = [];
  data.forEach(a => {
    const m = L.marker([a.lat, a.lon]).bindPopup(`
      <b>${a.nombre}</b><br>
      ATM: ${a.atm}<br>
      División: ${a.division}<br>
      Tipo: ${a.tipo}<br>
      Ubicación: ${a.ubicacion}<br>
      Dirección: ${a.direccion}<br>
      Promedio: ${a.promedio}
    `);
    markers.addLayer(m);
    heatPoints.push([a.lat, a.lon, Math.max(1, a.promedio)]);
  });

  if (chkHeat.checked) heat.setLatLngs(heatPoints);
  else heat.setLatLngs([]);

  if (data.length > 0) {
    const bounds = data.map(x => [x.lat, x.lon]);
    map.fitBounds(bounds);
  }

  count.textContent = data.length;
}
load();
</script>
</body>
</html>
"""

# ===================================================================
#  API DE PUNTOS
# ===================================================================
@app.route("/api/points")
@login_required
def api_points():
    departamento = request.args.get("departamento","").upper()
    provincia    = request.args.get("provincia","").upper()
    distrito     = request.args.get("distrito","").upper()
    division     = request.args.get("division","").upper()

    df2 = df.copy()
    df2[COL_DEPT] = df2[COL_DEPT].astype(str).str.upper()
    df2[COL_PROV] = df2[COL_PROV].astype(str).str.upper()
    df2[COL_DIST] = df2[COL_DIST].astype(str).str.upper()
    df2[COL_DIV]  = df2[COL_DIV].astype(str).str.upper()

    if departamento:
        df2 = df2[df2[COL_DEPT] == departamento]
    if provincia:
        df2 = df2[df2[COL_PROV] == provincia]
    if distrito:
        df2 = df2[df2[COL_DIST] == distrito]
    if division:
        df2 = df2[df2[COL_DIV] == division]

    points = []
    for _, r in df2.iterrows():
        points.append({
            "lat": float(r[COL_LAT]),
            "lon": float(r[COL_LON]),
            "atm": str(r.get(COL_ATM,"")),
            "nombre": str(r.get(COL_NAME,"")),
            "promedio": float(r.get(PROM_COL,0)),
            "division": str(r.get(COL_DIV,"")),
            "tipo": str(r.get(COL_TIPO,"")),
            "ubicacion": str(r.get(COL_UBIC,"")),
            "provincia": str(r.get(COL_PROV,"")),
            "distrito": str(r.get(COL_DIST,"")),
            "departamento": str(r.get(COL_DEPT,"")),
            "direccion": get_address(r[COL_LAT], r[COL_LON])
        })
    return jsonify(points)

# ===================================================================
#  INDEX
# ===================================================================
@app.route("/")
@login_required
def index():
    initial_center = df[[COL_LAT, COL_LON]].mean().tolist()
    return render_template_string(
        TEMPLATE,
        departamentos=DEPARTAMENTOS,
        provincias_all=PROVINCIAS_ALL,
        distritos_by_prov=DISTRITOS_BY_PROV,
        dist_by_dept=DIST_BY_DEPT,
        divisiones=DIVISIONES,
        initial_center=initial_center,
        initial_zoom=6
    )