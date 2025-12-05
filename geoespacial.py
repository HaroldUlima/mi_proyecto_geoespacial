# =============================
#   PARTE 1 — BACKEND COMPLETO
# =============================
import os
import re
import unicodedata
import json
import pandas as pd
import numpy as np
from flask import Flask, render_template_string, request, jsonify, redirect, url_for, session
from functools import wraps

# -------------------------
# Cache de direcciones
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
    except:
        key = f"{lat},{lon}"
    return address_cache.get(key, "Dirección no encontrada")


# -------------------------
# Cargar Excel de ATMs
# -------------------------
BASE_DIR = os.path.dirname(__file__)
atm_excel = os.path.join(BASE_DIR, "data", "Mapa Geoespacial ATM (1) (1).xlsx")

if not os.path.exists(atm_excel):
    raise FileNotFoundError("No encontré el Excel de ATMs en /data/")

raw = pd.read_excel(atm_excel)

def normalize_col(s):
    s = unicodedata.normalize("NFKD", str(s))
    s = s.encode("ascii", "ignore").decode("utf-8")
    s = re.sub(r"[^A-Z0-9 ]+", " ", s.upper().strip())
    return re.sub(r"\s+"," ", s)

norm_map = {normalize_col(c): c for c in raw.columns}

def find_col_by_keywords(keys):
    for norm, orig in norm_map.items():
        for k in keys:
            if k in norm:
                return orig
    return None

# Detectar columnas
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
df[COL_LAT] = pd.to_numeric(df[COL_LAT], errors="coerce")
df[COL_LON] = pd.to_numeric(df[COL_LON], errors="coerce")
df = df.dropna(subset=[COL_LAT, COL_LON])

# -------------------------
# Precompute dropdowns
# -------------------------
DEPARTAMENTOS = sorted(df[COL_DEPT].unique())
PROVINCIAS_ALL = df.groupby(COL_DEPT)[COL_PROV].apply(lambda s: sorted(s.unique())).to_dict()
DISTRITOS_BY_PROV = df.groupby(COL_PROV)[COL_DIST].apply(lambda s: sorted(s.unique())).to_dict()
DIST_BY_DEPT = df.groupby(COL_DEPT)[COL_DIST].apply(lambda s: sorted(s.unique())).to_dict()

DIVISIONES = sorted(df[COL_DIV].dropna().unique())

DIV_BY_DEPT = df.groupby(COL_DEPT)[COL_DIV].apply(lambda s: sorted(s.dropna().unique())).to_dict()
DIV_BY_PROV = df.groupby(COL_PROV)[COL_DIV].apply(lambda s: sorted(s.dropna().unique())).to_dict()
DIV_BY_DIST = df.groupby(COL_DIST)[COL_DIV].apply(lambda s: sorted(s.dropna().unique())).to_dict()


# ================================================
#   FLASK + LOGIN + SELECTOR DE CAPAS
# ================================================
app = Flask(__name__)
app.secret_key = os.getenv("SECRET_KEY","123")

APP_USER = os.getenv("APP_USERNAME")
APP_PASS = os.getenv("APP_PASSWORD")

# ---- LOGIN ----
def login_required(f):
    @wraps(f)
    def wrap(*args, **kwargs):
        if session.get("user") != APP_USER:
            return redirect(url_for("login"))
        return f(*args, **kwargs)
    return wrap

LOGIN_TEMPLATE = """
<!DOCTYPE html><html><body style="display:flex;justify-content:center;align-items:center;height:100vh;font-family:sans-serif;">
<div style="padding:40px;background:white;border-radius:12px;box-shadow:0 0 12px rgba(0,0,0,0.2);">
<h2>Login</h2>
{% if error %}<div style="color:red">{{error}}</div>{% endif %}
<form method="post">
<input name="username" placeholder="Usuario"><br><br>
<input name="password" type="password" placeholder="Contraseña"><br><br>
<button>Ingresar</button>
</form>
</div></body></html>
"""

@app.route("/login", methods=["GET","POST"])
def login():
    if request.method=="POST":
        u = request.form.get("username")
        p = request.form.get("password")
        if u==APP_USER and p==APP_PASS:
            session["user"]=u
            return redirect("/selector")
        return render_template_string(LOGIN_TEMPLATE, error="Credenciales incorrectas")
    return render_template_string(LOGIN_TEMPLATE)

# ---- SELECTOR DE CAPAS ----
SELECTOR_TEMPLATE = """
<!DOCTYPE html>
<html><body style="font-family:sans-serif;background:#eef3f9;padding:40px;">
<h1 style="text-align:center;">Seleccione la capa</h1>

<div style="display:flex;justify-content:center;gap:40px;margin-top:50px;">

<div onclick="location.href='/mapa/oficinas'"
     style="cursor:pointer;width:250px;height:250px;background:white;border-radius:16px;
            box-shadow:0 0 12px rgba(0,0,0,0.15);display:flex;align-items:center;justify-content:center;font-size:24px;">
  🏦 Oficinas
</div>

<div onclick="location.href='/mapa/islas'"
     style="cursor:pointer;width:250px;height:250px;background:white;border-radius:16px;
            box-shadow:0 0 12px rgba(0,0,0,0.15);display:flex;align-items:center;justify-content:center;font-size:24px;">
  🌐 Islas
</div>

<div onclick="location.href='/mapa/agentes'"
     style="cursor:pointer;width:250px;height:250px;background:white;border-radius:16px;
            box-shadow:0 0 12px rgba(0,0,0,0.15);display:flex;align-items:center;justify-content:center;font-size:24px;">
  🧍 Agentes
</div>

</div>
</body></html>
"""

@app.route("/selector")
@login_required
def selector():
    return render_template_string(SELECTOR_TEMPLATE)


# -------------------------
# RUTA DEL MAPA POR CAPA
# -------------------------
@app.route("/mapa/<tipo>")
@login_required
def mapa_tipo(tipo):
    if tipo not in ["oficinas","islas","agentes"]:
        return "No existe esa capa", 404

    return render_template_string(
        TEMPLATE_MAPA,
        tipo_mapa=tipo,
        departamentos=DEPARTAMENTOS,
        provincias_all=PROVINCIAS_ALL,
        distritos_by_prov=DISTRITOS_BY_PROV,
        dist_by_dept=DIST_BY_DEPT,
        divisiones=DIVISIONES,
        div_by_dept=DIV_BY_DEPT,
        div_by_prov=DIV_BY_PROV,
        div_by_dist=DIV_BY_DIST,
        initial_center=df[[COL_LAT,COL_LON]].mean().tolist(),
        initial_zoom=6
    )


# ============================================
#   PARTE 2 — TEMPLATE DEL MAPA
# ============================================
TEMPLATE_MAPA = """
<!doctype html>
<html>
<head>
<meta charset="utf-8">
<title>Mapa — {{ tipo_mapa|capitalize }}</title>

<style>
body{margin:0;font-family:Arial;background:#f3f6fb;}
#map{height:90vh;margin:20px;border-radius:12px;box-shadow:0 0 12px rgba(0,0,0,0.15);}
.controls{padding:10px;margin:20px;background:white;border-radius:12px;box-shadow:0 0 8px rgba(0,0,0,0.15);}
</style>

<link rel="stylesheet" href="https://unpkg.com/leaflet@1.9.4/dist/leaflet.css"/>
</head>

<body>

<h1 style="text-align:center;margin-top:20px;">Mapa — {{ tipo_mapa|upper }}</h1>
<div class="controls">

<label>Departamento:
<select id="selDepartamento">
<option value="">-- Todos --</option>
{% for d in departamentos %}
<option value="{{d}}">{{d}}</option>
{% endfor %}
</select></label>

<label style="margin-left:10px;">Provincia:
<select id="selProvincia"><option value="">-- Todas --</option></select>
</label>

<label style="margin-left:10px;">Distrito:
<select id="selDistrito"><option value="">-- Todos --</option></select>
</label>

<label style="margin-left:10px;">División:
<select id="selDivision">
<option value="">-- Todas --</option>
{% for dv in divisiones %}
<option value="{{dv}}">{{dv}}</option>
{% endfor %}
</select>
</label>

<label style="margin-left:20px;">
<input type="checkbox" id="chkHeat" checked> Heatmap
</label>

<span style="margin-left:30px;font-weight:bold;">Mostrando <span id="infoCount">--</span> ATMs</span>

</div>

<div id="map"></div>

<script src="https://unpkg.com/leaflet@1.9.4/dist/leaflet.js"></script>

<script>
// ======================
// DROPDOWNS
// ======================
const PROVINCIAS_ALL   = {{ provincias_all|tojson }};
const DISTRITOS_BY_PROV = {{ distritos_by_prov|tojson }};
const DIST_BY_DEPT      = {{ dist_by_dept|tojson }};
const DIV_BY_DEPT       = {{ div_by_dept|tojson }};
const DIV_BY_PROV       = {{ div_by_prov|tojson }};
const DIV_BY_DIST       = {{ div_by_dist|tojson }};
const TIPO_MAPA         = "{{ tipo_mapa }}";

const map = L.map('map').setView([{{ initial_center[0] }},{{ initial_center[1] }}], {{ initial_zoom }});
L.tileLayer('https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png').addTo(map);

const markers = L.layerGroup().addTo(map);

async function fetchAndRender(){
    const dep = selDepartamento.value;
    const prov = selProvincia.value;
    const dis = selDistrito.value;
    const div = selDivision.value;

    const url = `/api/points?tipo=${TIPO_MAPA}&departamento=${dep}&provincia=${prov}&distrito=${dis}&division=${div}`;

    const res = await fetch(url);
    const data = await res.json();

    markers.clearLayers();

    data.forEach(p=>{
        let iconHtml = p.ubicacion.includes("OFICINA") ? "🏦" : (p.ubicacion.includes("ISLA") ? "🌐" : "•");

        let marker = L.marker([p.lat, p.lon]).bindPopup(`
            <b>${p.nombre}</b><br>
            ATM: ${p.atm}<br>
            División: ${p.division}<br>
            Tipo: ${p.tipo}<br>
            Ubicación: ${p.ubicacion}<br>
            Dirección: ${p.direccion}
        `);
        markers.addLayer(marker);
    });

    document.getElementById("infoCount").innerText = data.length;
}

selDepartamento.onchange = ()=>{ fetchAndRender() };
selProvincia.onchange    = ()=>{ fetchAndRender() };
selDistrito.onchange     = ()=>{ fetchAndRender() };
selDivision.onchange     = ()=>{ fetchAndRender() };

fetchAndRender();
</script>

</body>
</html>
"""

# ==========================
# API de puntos por capa
# ==========================
@app.route("/api/points")
@login_required
def api_points():
    tipo = request.args.get("tipo")

    departamento = request.args.get("departamento","").upper()
    provincia    = request.args.get("provincia","").upper()
    distrito     = request.args.get("distrito","").upper()
    division     = request.args.get("division","").upper()

    df_f = df.copy()

    # Filtrar capa
    if tipo=="oficinas":
        df_f = df_f[df_f[COL_UBIC].str.contains("OFICINA", case=False)]
    elif tipo=="islas":
        df_f = df_f[df_f[COL_UBIC].str.contains("ISLA", case=False)]
    elif tipo=="agentes":
        df_f = df_f.iloc[0:0]  # vacío por ahora

    # Filtros generales
    if departamento:
        df_f = df_f[df_f[COL_DEPT]==departamento]
    if provincia:
        df_f = df_f[df_f[COL_PROV]==provincia]
    if distrito:
        df_f = df_f[df_f[COL_DIST]==distrito]
    if division:
        df_f = df_f[df_f[COL_DIV]==division]

    pts=[]
    for _,r in df_f.iterrows():
        pts.append({
            "lat":float(r[COL_LAT]),
            "lon":float(r[COL_LON]),
            "atm":str(r[COL_ATM]),
            "nombre":str(r.get(COL_NAME,r[COL_ATM])),
            "division":str(r[COL_DIV]),
            "tipo":str(r[COL_TIPO]),
            "ubicacion":str(r[COL_UBIC]),
            "direccion":get_address(r[COL_LAT], r[COL_LON])
        })

    return jsonify(pts)

