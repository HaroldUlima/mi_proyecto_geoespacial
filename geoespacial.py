# ======================================
#   GEOESPACIAL BBVA — VERSION FINAL
# ======================================

import os
import re
import unicodedata
import json
import pandas as pd
import numpy as np
from flask import Flask, render_template_string, request, jsonify, redirect, url_for, session
from functools import wraps

# --------------------------------------
# 1. CACHE DE DIRECCIONES
# --------------------------------------
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


# --------------------------------------
# 2. CARGAR EXCEL ORIGINAL
# --------------------------------------
BASE_DIR = os.path.dirname(__file__)
excel_path = os.path.join(BASE_DIR, "data", "Mapa Geoespacial ATM (1) (1).xlsx")

if not os.path.exists(excel_path):
    raise FileNotFoundError(f"No encontré archivo Excel en: {excel_path}")

raw = pd.read_excel(excel_path)

def normalize_col(s):
    s = str(s)
    s = unicodedata.normalize("NFKD", s)
    s = s.encode("ascii", "ignore").decode("utf-8")
    s = s.upper().strip()
    s = re.sub(r"[^A-Z0-9 ]+", " ", s)
    return re.sub(r"\s+", " ", s).strip()

norm_map = {normalize_col(c): c for c in raw.columns}

def find_col_by_keywords(keywords):
    for norm, orig in norm_map.items():
        for kw in keywords:
            if kw in norm:
                return orig
    return None

# Columnas
COL_ATM  = find_col_by_keywords(["ATM"]) or "ATM"
COL_NAME = find_col_by_keywords(["NOMBRE","CAJERO"]) or None
COL_DEPT = find_col_by_keywords(["DEPARTAMENTO"])
COL_PROV = find_col_by_keywords(["PROVINCIA"])
COL_DIST = find_col_by_keywords(["DISTRITO"])
COL_LAT  = find_col_by_keywords(["LAT"])
COL_LON  = find_col_by_keywords(["LON"])
COL_DIV  = find_col_by_keywords(["DIVISION"])
COL_TIPO = find_col_by_keywords(["TIPO"])
COL_UBIC = find_col_by_keywords(["UBICACION"])
PROM_COL = find_col_by_keywords(["PROM"]) or None

df = raw.copy()

# Limpieza coordenadas
df[COL_LAT] = pd.to_numeric(df[COL_LAT], errors="coerce")
df[COL_LON] = pd.to_numeric(df[COL_LON], errors="coerce")
df = df.dropna(subset=[COL_LAT, COL_LON])

# Listas
DEPARTAMENTOS = sorted(df[COL_DEPT].astype(str).unique())
PROVINCIAS_ALL = df.groupby(COL_DEPT)[COL_PROV].apply(lambda s: sorted(s.astype(str).unique())).to_dict()
DISTRITOS_BY_PROV = df.groupby(COL_PROV)[COL_DIST].apply(lambda s: sorted(s.astype(str).unique())).to_dict()
DIST_BY_DEPT      = df.groupby(COL_DEPT)[COL_DIST].apply(lambda s: sorted(s.astype(str).unique())).to_dict()
DIVISIONES = sorted(df[COL_DIV].dropna().astype(str).unique())


# --------------------------------------
# 3. FLASK + LOGIN
# --------------------------------------
app = Flask(__name__)
app.secret_key = os.getenv("SECRET_KEY", "fallback_local")

APP_USER = os.getenv("APP_USERNAME")
APP_PASS = os.getenv("APP_PASSWORD")

# LOGIN TEMPLATE
LOGIN_TEMPLATE = """
<!DOCTYPE html>
<html>
<head>
<meta charset="utf-8">
<title>Acceso Seguro — BBVA</title>
<style>
body{
    margin:0; padding:0; height:100vh;
    display:flex; justify-content:center; align-items:center;
    background:url('{{ url_for('static', filename='bbva.png') }}') center/cover;
    font-family:Arial;
}
.box{
    background:rgba(255,255,255,0.85);
    padding:30px;
    border-radius:12px;
    width:340px;
    text-align:center;
    box-shadow:0 8px 22px rgba(0,0,0,0.3);
}
input{width:100%;padding:10px;margin:8px 0;border-radius:8px;border:1px solid #ccc;}
button{
    width:100%;padding:10px;border:none;border-radius:8px;
    background:#1464A5;color:white;font-weight:bold;
}
.error{color:red;font-size:14px;margin-bottom:4px;}
</style>
</head>
<body>
<div class="box">
  <h2 style="color:#1464A5">Iniciar sesión</h2>
  {% if error %}<div class="error">{{error}}</div>{% endif %}
  <form method="POST">
    <input name="username" placeholder="Usuario" required>
    <input name="password" type="password" placeholder="Contraseña" required>
    <button>Ingresar</button>
  </form>
</div>
</body>
</html>
"""

def login_required(f):
    @wraps(f)
    def wrapper(*args, **kwargs):
        if session.get("user") != APP_USER:
            return redirect(url_for("login"))
        return f(*args, **kwargs)
    return wrapper


@app.route("/login", methods=["GET","POST"])
def login():
    if request.method == "POST":
        u = request.form.get("username")
        p = request.form.get("password")

        if u == APP_USER and p == APP_PASS:
            session["user"] = u
            return redirect("/selector")

        return render_template_string(LOGIN_TEMPLATE, error="Credenciales Incorrectas")

    return render_template_string(LOGIN_TEMPLATE)


@app.route("/logout")
def logout():
    session.clear()
    return redirect("/login")


# --------------------------------------
# 4. SELECTOR DE CAPAS
# --------------------------------------
SELECTOR_TEMPLATE = """
<!DOCTYPE html>
<html>
<head>
<title>Selector de Capas</title>
<style>
body{font-family:Arial;background:#eef3f9;text-align:center;padding:40px;}
.container{display:flex;justify-content:center;gap:40px;margin-top:50px;}
.card{
    width:240px;height:240px;background:white;border-radius:16px;
    box-shadow:0 4px 14px rgba(0,0,0,0.15);
    display:flex;justify-content:center;align-items:center;
    font-size:26px;font-weight:bold;cursor:pointer;
}
</style>
</head>
<body>

<h1>Seleccione la capa</h1>

<div class="container">
    <div class="card" onclick="location.href='/mapa/oficinas'">🏦 Oficinas</div>
    <div class="card" onclick="location.href='/mapa/islas'">🌐 Islas</div>
    <div class="card" onclick="location.href='/mapa/agentes'">🧍 Agentes</div>
</div>

</body>
</html>
"""

@app.route("/selector")
@login_required
def selector():
    return render_template_string(SELECTOR_TEMPLATE)


@app.route("/")
def home():
    if session.get("user") == APP_USER:
        return redirect("/selector")
    return redirect("/login")


# --------------------------------------
# 5. API PARA MAPA (FILTRA POR TIPO)
# --------------------------------------
@app.route("/api/points")
@login_required
def api_points():

    departamento = request.args.get("departamento", "").upper().strip()
    provincia    = request.args.get("provincia", "").upper().strip()
    distrito     = request.args.get("distrito", "").upper().strip()
    division     = request.args.get("division", "").upper().strip()
    tipo_query   = request.args.get("tipo", "").lower().strip()

    df_f = df.copy()

    df_f[COL_DEPT] = df_f[COL_DEPT].astype(str).str.upper().str.strip()
    df_f[COL_PROV] = df_f[COL_PROV].astype(str).str.upper().str.strip()
    df_f[COL_DIST] = df_f[COL_DIST].astype(str).str.upper().str.strip()
    df_f[COL_DIV]  = df_f[COL_DIV].astype(str).str.upper().str.strip()
    df_f[COL_UBIC] = df_f[COL_UBIC].astype(str).str.upper().str.strip()
    df_f[COL_TIPO] = df_f[COL_TIPO].astype(str).str.upper().str.strip()

    # Filtro por capa
    if tipo_query == "oficinas":
        df_f = df_f[df_f[COL_UBIC].str.contains("OFICINA")]

    elif tipo_query == "islas":
        df_f = df_f[df_f[COL_UBIC].str.contains("ISLA")]

    elif tipo_query == "agentes":
        df_f = df_f[df_f[COL_TIPO].str.contains("AGENTE")]

    # Jerarquía original
    if departamento:
        df_f = df_f[df_f[COL_DEPT] == departamento]
    if provincia:
        df_f = df_f[df_f[COL_PROV] == provincia]
    if distrito:
        df_f = df_f[df_f[COL_DIST] == distrito]
    if division:
        df_f = df_f[df_f[COL_DIV] == division]

    points = []
    for _, r in df_f.iterrows():
        nombre = str(r.get(COL_NAME)) if COL_NAME else str(r.get(COL_ATM))

        points.append({
            "lat": float(r[COL_LAT]),
            "lon": float(r[COL_LON]),
            "atm": str(r.get(COL_ATM)),
            "nombre": nombre,
            "promedio": float(r.get(PROM_COL, 0)),
            "division": str(r.get(COL_DIV)),
            "tipo": str(r.get(COL_TIPO)),
            "ubicacion": str(r.get(COL_UBIC)),
            "departamento": str(r.get(COL_DEPT)),
            "provincia": str(r.get(COL_PROV)),
            "distrito": str(r.get(COL_DIST)),
            "direccion": get_address(r[COL_LAT], r[COL_LON])
        })

    return jsonify(points)


# --------------------------------------
# 6. MAPA COMPLETO (EL MISMO QUE EL ORIGINAL)
# --------------------------------------
@app.route("/mapa/<tipo>")
@login_required
def mapa_tipo(tipo):

    if tipo not in ["oficinas", "islas", "agentes"]:
        return "Tipo no válido", 404

    return render_template_string(
        TEMPLATE_MAPA,
        tipo=tipo,
        departamentos=DEPARTAMENTOS,
        provincias_all=PROVINCIAS_ALL,
        distritos_by_prov=DISTRITOS_BY_PROV,
        dist_by_dept=DIST_BY_DEPT,
        divisiones=DIVISIONES,
        initial_center=df[[COL_LAT,COL_LON]].mean().tolist(),
        initial_zoom=6
    )


# --------------------------------------
# TEMPLATE MAPA — EL MISMO DEL ORIGINAL
# --------------------------------------

TEMPLATE_MAPA = """
<!DOCTYPE html>
<html>
<head>
<meta charset="utf-8">
<title>Mapa — {{ tipo.upper() }}</title>
<link rel="stylesheet" href="https://unpkg.com/leaflet@1.9.4/dist/leaflet.css"/>
<link rel="stylesheet" href="https://unpkg.com/leaflet.markercluster/dist/MarkerCluster.css"/>
<link rel="stylesheet" href="https://unpkg.com/leaflet.markercluster/dist/MarkerCluster.Default.css"/>

<style>
body{margin:0;background:#eef3f9;font-family:Arial;}
header{
    background:#003366;color:white;padding:18px;text-align:center;font-size:22px;
}
.controls{
    background:white;margin:20px;padding:12px;border-radius:12px;
    box-shadow:0 6px 16px rgba(0,0,0,0.1);
    display:flex;flex-wrap:wrap;gap:12px;
}
select{padding:8px;border-radius:8px;border:1px solid #ccc;}
#map{height:80vh;margin:20px;border-radius:14px;
    box-shadow:0 8px 18px rgba(0,0,0,0.2);}
</style>
</head>

<body>

<header>MAPA — {{ tipo.upper() }}</header>

<div class="controls">

<label>Departamento:
<select id="selDepartamento">
<option value="">-- Todos --</option>
{% for d in departamentos %}
<option value="{{d}}">{{d}}</option>
{% endfor %}
</select></label>

<label>Provincia:
<select id="selProvincia"><option value="">-- Todas --</option></select>
</label>

<label>Distrito:
<select id="selDistrito"><option value="">-- Todos --</option></select>
</label>

<label>División:
<select id="selDivision"><option value="">-- Todas --</option>
{% for dv in divisiones %}
<option value="{{dv}}">{{dv}}</option>
{% endfor %}
</select></label>

<label><input type="checkbox" id="chkHeat" checked> Heatmap</label>

<span style="font-weight:bold;margin-left:20px;">
Mostrando <span id="infoCount">--</span> ATMs
</span>

</div>

<div id="map"></div>

<script src="https://unpkg.com/leaflet@1.9.4/dist/leaflet.js"></script>
<script src="https://unpkg.com/leaflet.markercluster/dist/leaflet.markercluster.js"></script>
<script src="https://unpkg.com/leaflet.heat/dist/leaflet-heat.js"></script>

<script>

const PROVINCIAS_ALL = {{ provincias_all|tojson }};
const DISTRITOS_BY_PROV = {{ distritos_by_prov|tojson }};
const DIST_BY_DEPT = {{ dist_by_dept|tojson }};
const TIPO = "{{ tipo }}";

const map = L.map('map').setView([{{ initial_center[0] }}, {{ initial_center[1] }}], {{ initial_zoom }});
L.tileLayer('https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png',{maxZoom:19}).addTo(map);

const markersLayer = L.markerClusterGroup();
markersLayer.addTo(map);

const heatLayer = L.heatLayer([], {radius:25, blur:20});
heatLayer.addTo(map);

const selDept = document.getElementById('selDepartamento');
const selProv = document.getElementById('selProvincia');
const selDist = document.getElementById('selDistrito');
const selDiv  = document.getElementById('selDivision');
const chkHeat = document.getElementById('chkHeat');
const infoCount = document.getElementById('infoCount');

function populateProvincias(dept){
    selProv.innerHTML = "<option value=''>-- Todas --</option>";
    if(dept && PROVINCIAS_ALL[dept]){
        PROVINCIAS_ALL[dept].forEach(p=>{
            selProv.innerHTML += `<option value="${p}">${p}</option>`;
        });
    }
    populateDistritos(dept, "");
}
function populateDistritos(dept, prov){
    selDist.innerHTML = "<option value=''>-- Todos --</option>";
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
    if(selDiv.value)  params.append("division", selDiv.value);

    params.append("tipo", TIPO);

    const res = await fetch("/api/points?" + params.toString());
    const data = await res.json();

    markersLayer.clearLayers();
    heatLayer.setLatLngs([]);

    const bounds = [];
    const heat = [];

    data.forEach(pt=>{
        const iconHtml = pt.ubicacion.includes("OFICINA") ? "🏦"
                      : pt.ubicacion.includes("ISLA") ? "🌐"
                      : "📌";

        const icon = L.divIcon({html:`<div style="font-size:28px;">${iconHtml}</div>`});
        const marker = L.marker([pt.lat, pt.lon], {icon})
            .bindPopup(`
                <b>${pt.nombre}</b><br>
                ATM: ${pt.atm}<br>
                Ubicación: ${pt.ubicacion}<br>
                Tipo: ${pt.tipo}<br>
                División: ${pt.division}<br>
                Dirección: ${pt.direccion}
            `);

        markersLayer.addLayer(marker);

        bounds.push([pt.lat, pt.lon]);
        heat.push([pt.lat, pt.lon, 1]);
    });

    if(bounds.length > 0) map.fitBounds(bounds);
    heatLayer.setLatLngs(heat);

    if(!chkHeat.checked) map.removeLayer(heatLayer);
    else if(!map.hasLayer(heatLayer)) map.addLayer(heatLayer);

    infoCount.textContent = data.length;
}

selDept.onchange = ()=>{ populateProvincias(selDept.value); fetchAndRender(); };
selProv.onchange = ()=>{ populateDistritos(selDept.value, selProv.value); fetchAndRender(); };
selDist.onchange = fetchAndRender;
selDiv.onchange  = fetchAndRender;
chkHeat.onchange = fetchAndRender;

populateProvincias("");
populateDistritos("", "");
fetchAndRender();

</script>

</body>
</html>
"""

# FIN DEL ARCHIVO