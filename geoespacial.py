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

# ---------------- Normalizador de columnas -------------------
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


# ---------------- Detectar columnas ---------------------------
COL_ATM = find_col(["COD_ATM", "ATM"]) or "ATM"
COL_NAME = find_col(["NOMBRE", "CAJERO"]) or None
COL_DEPT = find_col(["DEPARTAMENTO"]) or "DEPARTAMENTO"
COL_PROV = find_col(["PROVINCIA"]) or "PROVINCIA"
COL_DIST = find_col(["DISTRITO"]) or "DISTRITO"
COL_LAT = find_col(["LATITUD", "LAT"]) or "LATITUD"
COL_LON = find_col(["LONGITUD", "LON"]) or "LONGITUD"
COL_DIV = find_col(["DIVISION", "DIVISIÓN"]) or "DIVISIÓN"
COL_TIPO = find_col(["TIPO"]) or "TIPO"
COL_UBIC = find_col(["UBICACION", "UBICACIÓN", "UBICACION INTERNA"]) or "UBICACION_INTERNA"
PROM_COL = find_col(["PROMEDIO", "PROM"]) or None

if PROM_COL is None:
    raw["PROM_FAKE"] = 0.0
    PROM_COL = "PROM_FAKE"

for c in [COL_ATM, COL_DEPT, COL_PROV, COL_DIST, COL_LAT, COL_LON, COL_DIV, COL_TIPO, COL_UBIC, PROM_COL]:
    if c not in raw.columns:
        raw[c] = ""

df = raw.copy()

# Limpieza de coordenadas
df[COL_LAT] = (
    df[COL_LAT].astype(str)
    .str.replace(",", ".", regex=False)
    .str.replace(r"[^\d\.\-]", "", regex=True)
    .replace("", np.nan)
    .astype(float)
)
df[COL_LON] = (
    df[COL_LON].astype(str)
    .str.replace(",", ".", regex=False)
    .str.replace(r"[^\d\.\-]", "", regex=True)
    .replace("", np.nan)
    .astype(float)
)

df = df.dropna(subset=[COL_LAT, COL_LON]).reset_index(drop=True)
df[PROM_COL] = pd.to_numeric(df[PROM_COL], errors="coerce").fillna(0.0)
df[COL_TIPO] = df[COL_TIPO].astype(str).fillna("")
df[COL_UBIC] = df[COL_UBIC].astype(str).fillna("")

# ============================================================
# 3. LISTAS PARA FILTROS
# ============================================================
DEPARTAMENTOS = sorted(df[COL_DEPT].dropna().astype(str).unique().tolist())

PROVINCIAS_BY_DEPT = (
    df.groupby(COL_DEPT)[COL_PROV]
    .apply(lambda s: sorted(s.dropna().astype(str).unique()))
    .to_dict()
)

DIST_BY_PROV = (
    df.groupby(COL_PROV)[COL_DIST]
    .apply(lambda s: sorted(s.dropna().astype(str).unique()))
    .to_dict()
)

DIVISIONES = sorted(df[COL_DIV].dropna().astype(str).unique())


# ============================================================
# 4. FLASK + LOGIN
# ============================================================
app = Flask(__name__)
app.secret_key = os.getenv("SECRET_KEY", "fallback_local")

APP_USER = os.getenv("APP_USERNAME")
APP_PASS = os.getenv("APP_PASSWORD")


def login_required(f):
    @wraps(f)
    def wrapped(*args, **kwargs):
        if session.get("user") != APP_USER:
            return redirect(url_for("login"))
        return f(*args, **kwargs)

    return wrapped


# ---------------- LOGIN TEMPLATE -----------------------------
LOGIN_TEMPLATE = """
<!DOCTYPE html>
<html>
<head>
<meta charset="utf-8">
<title>Acceso Seguro — BBVA</title>
<style>
body{
    margin:0; padding:0; height:100vh; width:100%;
    display:flex; align-items:center; justify-content:center;
    background:url('{{ url_for('static', filename='bbva.png') }}') no-repeat center center fixed;
    background-size:cover;
    font-family:Arial;
}
.box{
    background:rgba(255,255,255,0.88);
    padding:30px;
    border-radius:12px;
    width:360px;
    text-align:center;
}
</style>
</head>
<body>
<div class="box">
  <h2>Inicia sesión</h2>
  {% if error %}<div style='color:red;'>{{ error }}</div>{% endif %}
  <form method="post">
    <input name="username" placeholder="Usuario" required>
    <input name="password" type="password" placeholder="Contraseña" required>
    <button type="submit">Entrar</button>
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
            session["user"] = u
            return redirect(url_for("selector"))
        return render_template_string(LOGIN_TEMPLATE, error="Credenciales incorrectas")
    return render_template_string(LOGIN_TEMPLATE)


@app.route("/logout")
def logout():
    session.clear()
    return redirect(url_for("login"))


# ============================================================
# 5. SELECTOR DE CAPAS (IMÁGENES MÁS GRANDES)
# ============================================================
SELECTOR_TEMPLATE = """
<!DOCTYPE html>
<html>
<head>
<meta charset="utf-8">
<title>Selector de Capas — BBVA</title>
<style>
body{ background:#eef4fb; padding:40px; text-align:center; font-family:Arial; }
.grid{ display:flex; justify-content:center; gap:40px; margin-top:40px; }

.card{
    width:380px;
    height:300px;
    background:white;
    border-radius:20px;
    box-shadow:0 8px 26px rgba(0,0,0,0.15);
    cursor:pointer;
    padding:14px;
    transition:0.2s;
}
.card:hover{ transform:scale(1.03); }

.card img{
    width:100%;
    height:210px;
    object-fit:cover;
    border-radius:14px;
}
.card-title{
    margin-top:12px;
    font-weight:bold;
    font-size:20px;
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
# 6. MAPA POR CAPA
# ============================================================
@app.route("/mapa/<tipo>")
@login_required
def mapa_tipo(tipo):
    if tipo not in ["oficinas", "islas", "agentes"]:
        return "No existe esa capa", 404

    center = df[[COL_LAT, COL_LON]].mean().tolist()
    return render_template_string(
        TEMPLATE_MAPA,
        tipo_mapa=tipo,
        departamentos=DEPARTAMENTOS,
        provincias_by_dept=PROVINCIAS_BY_DEPT,
        dist_by_prov=DIST_BY_PROV,
        divisiones=DIVISIONES,
        initial_center=center,
        initial_zoom=6,
    )


# ============================================================
# 7. API POINTS
# ============================================================
@app.route("/api/points")
@login_required
def api_points():
    tipo = request.args.get("tipo", "")
    dpto = request.args.get("departamento", "").upper().strip()
    prov = request.args.get("provincia", "").upper().strip()
    dist = request.args.get("distrito", "").upper().strip()

    dff = df.copy()
    dff[COL_DEPT] = dff[COL_DEPT].str.upper()
    dff[COL_PROV] = dff[COL_PROV].str.upper()
    dff[COL_DIST] = dff[COL_DIST].str.upper()

    # Filtro por capa
    if tipo == "oficinas":
        dff = dff[dff[COL_UBIC].str.contains("OFICINA")]
    elif tipo == "islas":
        dff = dff[dff[COL_UBIC].str.contains("ISLA")]
    elif tipo == "agentes":
        dff = dff[dff[COL_UBIC].str.contains("AGENTE")]

    # Filtros geográficos
    if dpto:
        dff = dff[dff[COL_DEPT] == dpto]
    if prov:
        dff = dff[dff[COL_PROV] == prov]
    if dist:
        dff = dff[dff[COL_DIST] == dist]

    puntos = []
    for _, r in dff.iterrows():
        puntos.append({
            "lat": float(r[COL_LAT]),
            "lon": float(r[COL_LON]),
            "atm": str(r[COL_ATM]),
            "nombre": str(r.get(COL_NAME) or r.get(COL_ATM)),
            "promedio": float(r[PROM_COL]),
            "tipo": str(r[COL_TIPO]),
            "ubicacion": str(r[COL_UBIC]),
            "departamento": str(r[COL_DEPT]),
            "provincia": str(r[COL_PROV]),
            "distrito": str(r[COL_DIST]),
            "direccion": get_address(r[COL_LAT], r[COL_LON]),
        })

    return jsonify(puntos)


TEMPLATE_MAPA = """
<!doctype html>
<html>
<head>
<meta charset="utf-8">
<title>Mapa BBVA — {{ tipo_mapa|upper }}</title>

<link rel="stylesheet" href="https://unpkg.com/leaflet@1.9.4/dist/leaflet.css"/>
<link rel="stylesheet" href="https://unpkg.com/leaflet.markercluster@1.5.3/dist/MarkerCluster.css"/>

<style>
body{ margin:0; font-family:Arial; background:#eef4fb; }
header{
    background:#003366; color:white; padding:18px;
    text-align:center; font-size:22px; font-weight:bold;
}
#map{ height:76vh; flex:1; border-radius:12px; }

.main{ display:flex; padding:20px; gap:20px; }

.side{
    width:330px;
}
.side-card{
    background:white;
    padding:14px;
    border-radius:12px;
    box-shadow:0 6px 20px rgba(0,0,0,0.12);
    margin-bottom:12px;
}

#panelATM{ display:none; }

</style>
</head>

<body>

<header>Mapa BBVA — {{ tipo_mapa|upper }}</header>

<div class="main">

  <div id="map"></div>

  <div class="side">

    <div id="panelResumen" class="side-card">
        <h3>Resumen</h3>
        Total: <span id="resTotal">0</span><br>
        Dispensador: <span id="resDisp">0</span><br>
        Monedero: <span id="resMon">0</span><br>
        Reciclador: <span id="resRec">0</span><br>
    </div>

    <div id="panelATM" class="side-card">
        <h3>Panel del ATM</h3>
        <pre id="atmDetalle"></pre>
        <button onclick="volver()">VOLVER</button>
    </div>

  </div>
</div>

<script src="https://unpkg.com/leaflet@1.9.4/dist/leaflet.js"></script>
<script src="https://unpkg.com/leaflet.markercluster@1.5.3/dist/leaflet.markercluster.js"></script>

<script>

const map = L.map('map').setView([{{ initial_center[0] }}, {{ initial_center[1] }}], {{ initial_zoom }});
L.tileLayer('https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png').addTo(map);

const markers = L.markerClusterGroup();
markers.addTo(map);

function volver(){
    document.getElementById("panelATM").style.display = "none";
    document.getElementById("panelResumen").style.display = "block";
}

function showATM(pt){
    const t = `
ATM ${pt.atm}

Nombre: ${pt.nombre}
Dirección: ${pt.direccion}
Tipo: ${pt.tipo}
Ubicación: ${pt.ubicacion}

Dpto/Prov/Dist:
${pt.departamento} / ${pt.provincia} / ${pt.distrito}

Promedio: ${pt.promedio}
`;
    document.getElementById("atmDetalle").textContent = t;
    document.getElementById("panelResumen").style.display = "none";
    document.getElementById("panelATM").style.display = "block";
}

async function load(){
    const res = await fetch("/api/points?tipo={{ tipo_mapa }}");
    const data = await res.json();

    let cTotal=0, cDisp=0, cMon=0, cRec=0;

    data.forEach(pt => {
        cTotal++;

        const tipo = pt.tipo.toUpperCase();
        if(tipo.includes("DISP")) cDisp++;
        if(tipo.includes("MON"))  cMon++;
        if(tipo.includes("REC"))  cRec++;

        const icon = L.divIcon({html:"<div style='font-size:28px'>🏧</div>"});

        const m = L.marker([pt.lat, pt.lon], {icon});
        m.on("click", ()=> showATM(pt));
        markers.addLayer(m);
    });

    document.getElementById("resTotal").textContent = cTotal;
    document.getElementById("resDisp").textContent  = cDisp;
    document.getElementById("resMon").textContent   = cMon;
    document.getElementById("resRec").textContent   = cRec;
}

load();

</script>
</body>
</html>
"""