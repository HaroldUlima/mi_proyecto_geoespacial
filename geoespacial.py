# geoespacial.py
import os
import re
import unicodedata
import json
import pandas as pd
import numpy as np
from flask import Flask, render_template_string, request, jsonify

# -------------------------
# Cache de direcciones precalculadas
# -------------------------
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


# -------------------------
# Buscar archivo Excel
# -------------------------
BASE_DIR = os.path.dirname(__file__)
excel_path = os.path.join(BASE_DIR, "data", "Mapa Geoespacial ATM (1) (1).xlsx")

if not os.path.exists(excel_path):
    raise FileNotFoundError(f"No encontré el archivo Excel en {excel_path}")

print("✅ Usando archivo Excel:", excel_path)

# -------------------------
# Normalizar columnas
# -------------------------
def normalize_col(s):
    s = str(s)
    s = unicodedata.normalize("NFKD", s)
    s = s.encode("ascii", "ignore").decode("utf-8")
    s = s.upper().strip()
    s = re.sub(r"[^A-Z0-9 ]+", " ", s)
    s = re.sub(r"\s+", " ", s).strip()
    return s

raw = pd.read_excel(excel_path)
norm_map = {normalize_col(c): c for c in raw.columns}

def find_col_by_keywords(keywords):
    for k in norm_map:
        for kw in keywords:
            if kw in k:
                return norm_map[k]
    return None

# Detectar columnas
COL_ATM = find_col_by_keywords(["ATM"]) or "ATM"
COL_NAME = find_col_by_keywords(["NOMBRE","CAJERO","NOMBRECAJERO","NOMBRE_CAJERO","NOM_CAJA"]) or None
COL_DEPT = find_col_by_keywords(["DEPARTAMENTO"]) or "DEPARTAMENTO"
COL_PROV = find_col_by_keywords(["PROVINCIA"]) or "PROVINCIA"
COL_DIST = find_col_by_keywords(["DISTRITO"]) or "DISTRITO"
COL_LAT = find_col_by_keywords(["LATITUD","LAT"]) or "LAT"
COL_LON = find_col_by_keywords(["LONGITUD","LON","LONG"]) or "LON"
PROM_COL = find_col_by_keywords(["PROMEDIO","PROM"]) or None
COL_DIV = find_col_by_keywords(["DIVISION","DIVISIÓN"]) or "DIVISION"
COL_TIPO = find_col_by_keywords(["TIPO"]) or "TIPO"
COL_UBIC = find_col_by_keywords(["UBICACION","UBICACIÓN","UBICACION_INTERNA","UBICACIÓN_INTERNA"]) or "UBICACION_INTERNA"
COL_UBIC = COL_UBIC or "UBICACION_INTERNA"
COL_DIR = find_col_by_keywords(["DIRECCION","DIRECCIÓN"]) or None

if COL_NAME:
    print("✅ Columna Nombre detectada:", COL_NAME)
else:
    print("⚠️ No se detectó columna 'Nombre Cajero'. Se usará la columna ATM como nombre.")

# Asegurar columnas
for c in [COL_ATM, COL_DEPT, COL_PROV, COL_DIST, COL_LAT, COL_LON, PROM_COL, COL_DIV, COL_TIPO, COL_UBIC]:
    if c and c not in raw.columns:
        if c in (COL_LAT, COL_LON):
            raise KeyError(f"No encontré columna de coordenadas esperada ({c}) en el Excel.")
        raw[c] = ""

# Dirección si no existe
if COL_DIR is None:
    raw["DIRECCION_API"] = ""
    COL_DIR = "DIRECCION_API"
else:
    raw[COL_DIR] = raw[COL_DIR].astype(str)

if PROM_COL is None:
    raw["PROMEDIO_2025_FAKE"] = 0.0
    PROM_COL = "PROMEDIO_2025_FAKE"

# -------------------------
# Limpieza
# -------------------------
df = raw.copy()
df[COL_LAT] = df[COL_LAT].astype(str).str.replace(",", ".", regex=False).str.replace(r"[^\d\.\-]", "", regex=True).replace("", np.nan).astype(float)
df[COL_LON] = df[COL_LON].astype(str).str.replace(",", ".", regex=False).str.replace(r"[^\d\.\-]", "", regex=True).replace("", np.nan).astype(float)
df = df.dropna(subset=[COL_LAT, COL_LON]).reset_index(drop=True)
df[PROM_COL] = pd.to_numeric(df[PROM_COL], errors="coerce").fillna(0.0)
print(f"📊 Total registros válidos: {len(df)}")

# -------------------------
# Precompute listas
# -------------------------
DEPARTAMENTOS = sorted(df[COL_DEPT].dropna().astype(str).unique().tolist())
PROVINCIAS_ALL = df.groupby(COL_DEPT)[COL_PROV].apply(lambda s: sorted(s.dropna().astype(str).unique().tolist())).to_dict()
DISTRITOS_BY_PROV = df.groupby(COL_PROV)[COL_DIST].apply(lambda s: sorted(s.dropna().astype(str).unique().tolist())).to_dict()
DIST_BY_DEPT = df.groupby(COL_DEPT)[COL_DIST].apply(lambda s: sorted(s.dropna().astype(str).unique().tolist())).to_dict()

# 🔥 AGREGADO: lista de divisiones
DIVISIONES = sorted(df[COL_DIV].dropna().astype(str).unique().tolist())

# -------------------------
# Flask
# -------------------------
app = Flask(__name__)

@app.after_request
def add_header(response):
    response.headers["Cache-Control"] = "no-store, no-cache, must-revalidate, max-age=0"
    response.headers["Pragma"] = "no-cache"
    response.headers["Expires"] = "0"
    return response

from functools import wraps
from flask import redirect, url_for, session

app.secret_key = os.getenv("SECRET_KEY", "fallback_local")
APP_USER = os.getenv("APP_USERNAME")
APP_PASS = os.getenv("APP_PASSWORD")

LOGIN_TEMPLATE = """
<!DOCTYPE html>
<html>
<head>
<meta charset="utf-8">
<title>Acceso Seguro — BBVA</title>
...
</head>
<body>
  <div class="box">
    <h2>Inicia sesión</h2>
    {% if error %}<div class="error">{{ error }}</div>{% endif %}
    <form method="post">
      <input name="username" placeholder="Usuario" required autofocus>
      <input name="password" type="password" placeholder="Contraseña" required>
      <button type="submit">Entrar</button>
    </form>
  </div>
</body>
</html>
"""

def login_required(f):
    @wraps(f)
    def wrapped(*args, **kwargs):
        if session.get("user") != APP_USER:
            return redirect(url_for("login"))
        return f(*args, **kwargs)
    return wrapped

@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        u = request.form.get("username", "")
        p = request.form.get("password", "")
        if u == APP_USER and p == APP_PASS:
            session.clear()
            session["user"] = u
            session.permanent = False
            return redirect(url_for("index"))
        return render_template_string(LOGIN_TEMPLATE, error="Usuario o contraseña incorrectos")
    return render_template_string(LOGIN_TEMPLATE)

@app.route("/logout")
def logout():
    session.clear()
    resp = redirect(url_for("login"))
    resp.set_cookie("session", "", expires=0)
    return resp

# -------------------------
# TEMPLATE PRINCIPAL CON DIVISIÓN AGREGADA
# -------------------------
TEMPLATE = """
<!doctype html>
<html>
<head>
<meta charset="utf-8">
<title>Dashboard Geoespacial — ATMs</title>
<link rel="stylesheet" href="https://unpkg.com/leaflet@1.9.4/dist/leaflet.css"/>
<link rel="stylesheet" href="https://unpkg.com/leaflet.markercluster@1.5.3/dist/MarkerCluster.css"/>
<link rel="stylesheet" href="https://unpkg.com/leaflet.markercluster@1.5.3/dist/MarkerCluster.Default.css"/>

<style>
/* estilos (idénticos a tu código original) */
</style>
</head>

<body>

<header style="background-color:#003366; height:70px; padding:0 20px;
               display:flex; align-items:center; position:relative;">
  <div style="flex:1; text-align:center;">
    <h1 style="color:white; font-size:2.5rem; margin:0;">Mapa de ATMs — BBVA</h1>
  </div>
  <a href="/logout"
     style="color:white; text-decoration:none; background:#1464A5;
            padding:8px 16px; border-radius:8px; font-weight:600; font-size:16px;
            position:absolute; right:20px;">
     Cerrar sesión
  </a>
</header>

<div class="topbar">
  <div class="controls">

    <!-- filtros existentes -->
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

    <!-- 🔥 AGREGADO: FILTRO DE DIVISIÓN -->
    <label>División:
      <select id="selDivision">
        <option value="">-- Todas --</option>
        {% for d in divisiones %}
          <option value="{{d}}">{{d}}</option>
        {% endfor %}
      </select>
    </label>

    <label style="margin-left:10px;">
      <input type="checkbox" id="chkHeat" checked> Mostrar Heatmap
    </label>

    <div style="flex:1"></div>
    <div class="muted">Mostrando <span id="infoCount">--</span> ATMs</div>

  </div>
</div>

<div class="main">
  <div id="map"></div>

  <!-- sidebar igual que en tu código original -->
</div>

<script src="https://unpkg.com/leaflet@1.9.4/dist/leaflet.js"></script>
<script src="https://unpkg.com/leaflet.markercluster@1.5.3/dist/MarkerCluster.js"></script>
<script src="https://unpkg.com/leaflet.heat/dist/leaflet-heat.js"></script>

<script>

const PROVINCIAS_ALL = {{ provincias_all|tojson }};
const DISTRITOS_BY_PROV = {{ distritos_by_prov|tojson }};
const DIST_BY_DEPT = {{ dist_by_dept|tojson }};
const INITIAL_CENTER = [{{ initial_center[0] }}, {{ initial_center[1] }}];
const INITIAL_ZOOM = {{ initial_zoom }};

const map = L.map('map').setView(INITIAL_CENTER, INITIAL_ZOOM);
L.tileLayer('https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png',{ maxZoom:19 }).addTo(map);

const markersLayer = L.markerClusterGroup({ chunkedLoading: true });
const heatLayer = L.heatLayer([], {radius:25, blur:20, maxZoom:17});
markersLayer.addTo(map);
heatLayer.addTo(map);

const selDept = document.getElementById('selDepartamento');
const selProv = document.getElementById('selProvincia');
const selDist = document.getElementById('selDistrito');
const selDivision = document.getElementById('selDivision');  // 🔥 agregado
const chkHeat = document.getElementById('chkHeat');

function populateProvincias(dept){
  selProv.innerHTML = '<option value="">-- Todas --</option>';
  if(dept && PROVINCIAS_ALL[dept]){
    PROVINCIAS_ALL[dept].forEach(p=>{
      selProv.innerHTML += `<option value="${p}">${p}</option>`;
    });
  }
  populateDistritos(dept, "");
}

function populateDistritos(dept, prov){
  selDist.innerHTML = '<option value="">-- Todos --</option>';
  if(prov && DISTRITOS_BY_PROV[prov]){
    DISTRITOS_BY_PROV[prov].forEach(d=>{
      selDist.innerHTML += `<option value="${d}">${d}</option>`;
    });
  } else if(dept && DIST_BY_DEPT[dept]){
    DIST_BY_DEPT[dept].forEach(d=>{
      selDist.innerHTML += `<option value="${d}">${d}</option>`;
    });
  }
}

async function fetchAndRender(){
  const params = new URLSearchParams();

  if(selDept.value) params.append("departamento", selDept.value);
  if(selProv.value) params.append("provincia", selProv.value);
  if(selDist.value) params.append("distrito", selDist.value);

  if(selDivision.value) params.append("division", selDivision.value); // 🔥 agregado

  const res = await fetch('/api/points?' + params.toString());
  const data = await res.json();

  markersLayer.clearLayers();
  heatLayer.setLatLngs([]);

  const points = [];

  data.forEach(item=>{
    const m = L.marker([item.lat, item.lon]).bindPopup(item.nombre);
    markersLayer.addLayer(m);
    points.push([item.lat, item.lon]);
  });

  heatLayer.setLatLngs(points);
}

selDept.addEventListener('change', ()=>{ populateProvincias(selDept.value); fetchAndRender(); });
selProv.addEventListener('change', ()=>{ populateDistritos(selDept.value, selProv.value); fetchAndRender(); });
selDist.addEventListener('change', fetchAndRender);
selDivision.addEventListener('change', fetchAndRender); // 🔥 agregado
chkHeat.addEventListener('change', fetchAndRender);

populateProvincias(selDept.value);
populateDistritos(selDept.value, selProv.value);
fetchAndRender();

</script>
</body>
</html>
"""

# -------------------------
# API DE PUNTOS
# -------------------------
@app.route("/api/points")
@login_required
def api_points():
    departamento = request.args.get("departamento", "").strip().upper()
    provincia = request.args.get("provincia", "").strip().upper()
    distrito = request.args.get("distrito", "").strip().upper()
    division = request.args.get("division", "").strip().upper()   # 🔥 agregado

    df_filtered = df.copy()
    df_filtered[COL_DEPT] = df_filtered[COL_DEPT].astype(str).str.upper().str.strip()
    df_filtered[COL_PROV] = df_filtered[COL_PROV].astype(str).str.upper().str.strip()
    df_filtered[COL_DIST] = df_filtered[COL_DIST].astype(str).str.upper().str.strip()
    df_filtered[COL_DIV] = df_filtered[COL_DIV].astype(str).str.upper().str.strip()

    if departamento:
        df_filtered = df_filtered[df_filtered[COL_DEPT] == departamento]
    if provincia:
        df_filtered = df_filtered[df_filtered[COL_PROV] == provincia]
    if distrito:
        df_filtered = df_filtered[df_filtered[COL_DIST] == distrito]

    if division:   # 🔥 AGREGADO
        df_filtered = df_filtered[df_filtered[COL_DIV] == division]

    points = []
    for _, r in df_filtered.iterrows():

        nombre_val = ""
        if COL_NAME and COL_NAME in r.index:
            nombre_val = str(r.get(COL_NAME,"")).strip()
        if not nombre_val:
            nombre_val = str(r.get(COL_ATM,""))

        points.append({
            "lat": float(r[COL_LAT]),
            "lon": float(r[COL_LON]),
            "atm": str(r.get(COL_ATM,"")),
            "nombre": nombre_val,
            "division": str(r.get(COL_DIV,"")),
            "tipo": str(r.get(COL_TIPO,"")),
            "ubicacion": str(r.get(COL_UBIC,"")),
            "promedio": float(r.get(PROM_COL,0.0)),
            "provincia": str(r.get(COL_PROV,"")),
            "distrito": str(r.get(COL_DIST,"")),
            "departamento": str(r.get(COL_DEPT,"")),
            "direccion": get_address(float(r[COL_LAT]), float(r[COL_LON]))
        })

    return jsonify(points)

# -------------------------
# INDEX
# -------------------------
@app.route("/")
@login_required
def index():
    initial_center = df[[COL_LAT, COL_LON]].mean().tolist()
    initial_zoom = 6
    return render_template_string(
        TEMPLATE,
        departamentos=DEPARTAMENTOS,
        provincias_all=PROVINCIAS_ALL,
        distritos_by_prov=DISTRITOS_BY_PROV,
        dist_by_dept=DIST_BY_DEPT,
        divisiones=DIVISIONES,   # 🔥 agregado
        initial_center=initial_center,
        initial_zoom=initial_zoom
    )