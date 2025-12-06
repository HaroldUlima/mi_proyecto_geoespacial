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

# ---------------- Normalizador de nombres de columna -----------
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


# ---------------- Detectar columnas principales ----------------
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

# Si no existe columna de promedio, creamos una falsa
if PROM_COL is None:
    raw["PROM_FAKE"] = 0.0
    PROM_COL = "PROM_FAKE"

# Asegurar columnas mínimas
for c in [COL_ATM, COL_DEPT, COL_PROV, COL_DIST, COL_LAT, COL_LON, COL_DIV, COL_TIPO, COL_UBIC, PROM_COL]:
    if c not in raw.columns:
        raw[c] = ""

df = raw.copy()

# Limpieza de coordenadas
df[COL_LAT] = (
    df[COL_LAT]
    .astype(str)
    .str.replace(",", ".", regex=False)
    .str.replace(r"[^\d\.\-]", "", regex=True)
    .replace("", np.nan)
    .astype(float)
)
df[COL_LON] = (
    df[COL_LON]
    .astype(str)
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
# 3. LISTAS PARA FILTROS — JERARQUÍA COMPLETA
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

DIV_BY_DEPT = (
    df.groupby(COL_DEPT)[COL_DIV]
    .apply(lambda s: sorted(s.dropna().astype(str).unique()))
    .to_dict()
)
DIV_BY_PROV = (
    df.groupby(COL_PROV)[COL_DIV]
    .apply(lambda s: sorted(s.dropna().astype(str).unique()))
    .to_dict()
)
DIV_BY_DIST = (
    df.groupby(COL_DIST)[COL_DIV]
    .apply(lambda s: sorted(s.dropna().astype(str).unique()))
    .to_dict()
)

DIVISIONES = sorted(df[COL_DIV].dropna().astype(str).unique())


# ============================================================
# 4. FLASK + LOGIN (con imagen bbva.png)
# ============================================================
app = Flask(__name__)
app.secret_key = os.getenv("SECRET_KEY", "fallback_local")

APP_USER = os.getenv("APP_USERNAME")
APP_PASS = os.getenv("APP_PASSWORD")

if not APP_USER or not APP_PASS:
    print("⚠️ APP_USERNAME / APP_PASSWORD no configurados en Render.")


@app.after_request
def add_header(resp):
    resp.headers["Cache-Control"] = "no-store, no-cache, must-revalidate, max-age=0"
    resp.headers["Pragma"] = "no-cache"
    resp.headers["Expires"] = "0"
    return resp


LOGIN_TEMPLATE = """
<!DOCTYPE html>
<html>
<head>
<meta charset="utf-8">
<title>Acceso Seguro — BBVA</title>
<meta name="viewport" content="width=device-width, initial-scale=1">
<style>
body{
    margin:0; padding:0; height:100vh; width:100%;
    display:flex; align-items:center; justify-content:center;
    background:url('{{ url_for('static', filename='bbva.png') }}')
               no-repeat center center fixed;
    background-size:cover;
    font-family:Arial,Helvetica,sans-serif;
}
.box{
    background:rgba(255,255,255,0.88);
    padding:30px 35px;
    border-radius:12px;
    box-shadow:0 8px 30px rgba(0,0,0,0.3);
    width:360px;
    text-align:center;
}
h2{color:#1464A5; margin:0 0 15px 0;}
input{
    width:100%; padding:10px; margin:8px 0;
    border-radius:8px; border:1px solid #ddd;
}
button{
    width:100%; padding:10px;
    background:#1464A5; color:white;
    border:none; border-radius:8px;
    font-weight:600; cursor:pointer;
}
.error{color:#c0392b; font-size:14px; margin-bottom:8px;}
.small{font-size:13px; color:#6b7a8a; margin-top:8px;}
</style>
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
    <div class="small">Acceso restringido — Solo personal autorizado</div>
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
        u = request.form.get("username")
        p = request.form.get("password")
        if u == APP_USER and p == APP_PASS:
            session.clear()
            session["user"] = u
            return redirect(url_for("selector"))
        return render_template_string(LOGIN_TEMPLATE, error="Credenciales incorrectas")
    return render_template_string(LOGIN_TEMPLATE)


@app.route("/logout")
def logout():
    session.clear()
    resp = redirect(url_for("login"))
    resp.set_cookie("session", "", expires=0)
    return resp


# ============================================================
# 5. SELECTOR DE CAPAS (con tus imágenes)
# ============================================================
SELECTOR_TEMPLATE = """
<!DOCTYPE html>
<html>
<head>
<meta charset="utf-8">
<title>Selector de Capas — BBVA</title>
<meta name="viewport" content="width=device-width, initial-scale=1">
<style>
body{
    margin:0; padding:40px 20px;
    font-family:Arial,Helvetica,sans-serif;
    background:#eef4fb;
}
h1{
    text-align:center;
    color:#072146;
}
.grid{
    margin-top:40px;
    display:flex;
    justify-content:center;
    gap:40px;
    flex-wrap:wrap;
}
.card{
    width:320px; height:260px;
    background:white;
    border-radius:20px;
    box-shadow:0 8px 26px rgba(0,0,0,0.15);
    cursor:pointer;
    display:flex;
    flex-direction:column;
    align-items:center;
    justify-content:flex-start;
    padding:16px 14px;
    transition:transform .18s ease, box-shadow .18s ease;
}
.card:hover{
    transform:translateY(-4px) scale(1.02);
    box-shadow:0 12px 32px rgba(0,0,0,0.25);
}
.card img{
    width:100%;
    height:170px;
    object-fit:cover;
    border-radius:14px;
}
.card-title{
    margin-top:12px;
    font-size:18px;
    font-weight:700;
    color:#072146;
    display:flex;
    align-items:center;
    gap:8px;
}
.card-title span.icon{
    font-size:22px;
}
</style>
</head>
<body>

<h1>Seleccione la capa</h1>

<div class="grid">

  <div class="card" onclick="location.href='/mapa/oficinas'">
    <img src="{{ url_for('static', filename='oficina.png') }}" alt="Oficinas BBVA">
    <div class="card-title"><span class="icon">🏦</span>Oficinas</div>
  </div>

  <div class="card" onclick="location.href='/mapa/islas'">
    <img src="{{ url_for('static', filename='isla.png') }}" alt="Islas BBVA">
    <div class="card-title"><span class="icon">🌐</span>Islas</div>
  </div>

  <div class="card" onclick="location.href='/mapa/agentes'">
    <img src="{{ url_for('static', filename='agente.png') }}" alt="Agentes BBVA">
    <div class="card-title"><span class="icon">🧍</span>Agentes</div>
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
# 6. RUTA DEL MAPA POR CAPA
# ============================================================
@app.route("/mapa/<tipo>")
@login_required
def mapa_tipo(tipo):
    if tipo not in ["oficinas", "islas", "agentes"]:
        return "No existe esa capa", 404

    initial_center = df[[COL_LAT, COL_LON]].mean().tolist()
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
        initial_center=initial_center,
        initial_zoom=6,
    )


# ============================================================
# 7. API /api/points — Filtrado jerárquico completo
# ============================================================
@app.route("/api/points")
@login_required
def api_points():
    tipo_mapa = request.args.get("tipo", "").lower()

    dpto = request.args.get("departamento", "").upper().strip()
    prov = request.args.get("provincia", "").upper().strip()
    dist = request.args.get("distrito", "").upper().strip()
    divi = request.args.get("division", "").upper().strip()

    dff = df.copy()

    dff[COL_DEPT] = dff[COL_DEPT].astype(str).str.upper().str.strip()
    dff[COL_PROV] = dff[COL_PROV].astype(str).str.upper().str.strip()
    dff[COL_DIST] = dff[COL_DIST].astype(str).str.upper().str.strip()
    dff[COL_DIV] = dff[COL_DIV].astype(str).str.upper().str.strip()
    dff[COL_UBIC] = dff[COL_UBIC].astype(str).str.upper().str.strip()
    dff[COL_TIPO] = dff[COL_TIPO].astype(str)

    # Filtrar por capa
    if tipo_mapa == "oficinas":
        dff = dff[dff[COL_UBIC].str.contains("OFICINA", na=False)]
    elif tipo_mapa == "islas":
        dff = dff[dff[COL_UBIC].str.contains("ISLA", na=False)]
    elif tipo_mapa == "agentes":
        dff = dff[dff[COL_UBIC].str.contains("AGENTE", na=False)]

    # Filtros jerárquicos
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
        nombre = ""
        if COL_NAME and COL_NAME in r.index:
            nombre = str(r.get(COL_NAME, "")).strip()
        if not nombre:
            nombre = str(r.get(COL_ATM, ""))

        lat_v = float(r[COL_LAT])
        lon_v = float(r[COL_LON])

        puntos.append(
            {
                "lat": lat_v,
                "lon": lon_v,
                "atm": str(r.get(COL_ATM, "")),
                "nombre": nombre,
                "promedio": float(r.get(PROM_COL, 0.0)),
                "division": str(r.get(COL_DIV, "")),
                "tipo": str(r.get(COL_TIPO, "")),
                "ubicacion": str(r.get(COL_UBIC, "")),
                "departamento": str(r.get(COL_DEPT, "")),
                "provincia": str(r.get(COL_PROV, "")),
                "distrito": str(r.get(COL_DIST, "")),
                "direccion": get_address(lat_v, lon_v),
            }
        )

    return jsonify(puntos)


# ============================================================
# 8. TEMPLATE MAPA — VIENE EN LA PARTE 2
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
header h1{
  margin:0;
  font-size:1.9rem;
}
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

/* CONTROLES SUPERIORES */
.topbar{
  padding:16px 20px 8px 20px;
}
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
.controls label{
  font-size:13px;
  color:var(--muted);
  display:flex;
  align-items:center;
  gap:6px;
}
select{
  padding:6px 10px;
  border-radius:8px;
  border:1px solid #d0d7e3;
}
input[type="checkbox"]{
  transform:scale(1.05);
}

/* LAYOUT PRINCIPAL */
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
.side{
  width:330px;
}
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
.muted{
  color:var(--muted);
  font-size:12px;
}

/* Panel ATM seleccionado */
.side-card-atm{
  font-family:"Consolas","Fira Code",monospace;
  white-space:pre-line;
  line-height:1.35;
  border-left:4px solid var(--bbva-blue);
  position:relative;
}
.side-card-atm h3{
  margin:0 0 6px 0;
  font-size:14px;
}
.btn-small{
  display:inline-block;
  margin-top:8px;
  padding:4px 10px;
  border-radius:6px;
  border:none;
  background:var(--bbva-blue);
  color:white;
  font-size:12px;
  cursor:pointer;
}

/* Glow suave cuando hay ATM seleccionado */
@keyframes panelGlow{
  0%{box-shadow:0 0 0 rgba(20,100,165,0.0);}
  50%{box-shadow:0 0 18px rgba(20,100,165,0.55);}
  100%{box-shadow:0 0 0 rgba(20,100,165,0.0);}
}
.side-card-atm.glow{
  animation:panelGlow 2.2s ease-in-out infinite;
}

/* Ocultar */
.hidden{ display:none; }

/* Popup Leaflet */
.leaflet-popup-content-wrapper{
  border-radius:12px;
  box-shadow:0 6px 20px rgba(0,0,0,0.25);
}
.popup-title{
  font-size:14px;
  font-weight:bold;
  color:var(--bbva-blue);
  margin-bottom:4px;
}
.popup-row{
  margin:2px 0;
  font-size:12px;
}

/* Iconos personalizados */
.icon-bank div{
  font-size:30px;
}
.icon-isla div{
  font-size:30px;
  color:deepskyblue;
}
.icon-round div{
  width:14px;
  height:14px;
  border-radius:50%;
  border:2px solid white;
}
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
      <select id="selProvincia">
        <option value="">-- Todas --</option>
      </select>
    </label>

    <label>Distrito:
      <select id="selDistrito">
        <option value="">-- Todos --</option>
      </select>
    </label>

    <label>División:
      <select id="selDivision">
        <option value="">-- Todas --</option>
        {% for dv in divisiones %}
        <option value="{{dv}}">{{dv}}</option>
        {% endfor %}
      </select>
    </label>

    <label style="margin-left:16px;">
      <input type="checkbox" id="chkHeat" checked> Heatmap
    </label>

    <div style="flex:1"></div>

    <div style="font-size:13px; color:var(--muted);">
      Mostrando <span id="infoCount">--</span> ATMs
    </div>
  </div>
</div>

<div class="main">
  <div id="map"></div>

  <div class="side">
    <!-- PANEL RESUMEN -->
    <div id="panelResumen" class="side-card">
      <div class="side-title" id="panelResumenTitulo">Resumen</div>
      <div class="muted" id="panelResumenSub">Promedio total:</div>
      <div style="margin-top:4px;">
        <b>Promedio total:</b> <span id="resPromedio">0</span>
      </div>
      <div style="margin-top:6px; font-weight:600;" id="resTituloBloque">ATMs en oficinas</div>
      <div class="muted" style="margin-top:2px;">Total: <span id="resTotal">0</span></div>
      <div class="muted">Dispensador: <span id="resDisp">0</span></div>
      <div class="muted">Monedero: <span id="resMon">0</span></div>
      <div class="muted">Reciclador: <span id="resRec">0</span></div>

      <div style="margin-top:10px; font-weight:600;">Leyenda</div>
      <div class="muted">
        <div>🔴 ATM ≥ 4</div>
        <div>🟢 ATM ≤ 3</div>
        <div>🏦 Oficina</div>
        <div>🌐 Isla</div>
        <div>🧍 Agente</div>
      </div>
    </div>

    <!-- PANEL ATM SELECCIONADO -->
    <div id="panelATM" class="side-card side-card-atm hidden">
      <h3>Panel del ATM seleccionado</h3>
      <div id="atmDetalle" style="font-size:12px; margin-top:4px;"></div>
      <button id="btnVolver" class="btn-small">VOLVER</button>
    </div>
  </div>
</div>

<script src="https://unpkg.com/leaflet@1.9.4/dist/leaflet.js"></script>
<script src="https://unpkg.com/leaflet.markercluster@1.5.3/dist/leaflet.markercluster.js"></script>
<script src="https://unpkg.com/leaflet.heat/dist/leaflet-heat.js"></script>

<script>
const PROV_BY_DEPT = {{ provincias_by_dept|tojson }};
const DIST_BY_PROV = {{ dist_by_prov|tojson }};
const DIV_BY_DEPT  = {{ div_by_dept|tojson }};
const DIV_BY_PROV  = {{ div_by_prov|tojson }};
const DIV_BY_DIST  = {{ div_by_dist|tojson }};
const TIPO_MAPA    = "{{ tipo_mapa }}";
const INITIAL_CENTER = [{{ initial_center[0] }}, {{ initial_center[1] }}];
const INITIAL_ZOOM   = {{ initial_zoom }};

const map = L.map('map').setView(INITIAL_CENTER, INITIAL_ZOOM);
L.tileLayer('https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png',
  { maxZoom:19 }).addTo(map);

const markers = L.markerClusterGroup({chunkedLoading:true});
const heat    = L.heatLayer([], {radius:28, blur:22});
markers.addTo(map);
heat.addTo(map);

// Combos
const selDep  = document.getElementById("selDepartamento");
const selProv = document.getElementById("selProvincia");
const selDist = document.getElementById("selDistrito");
const selDiv  = document.getElementById("selDivision");
const chkHeat = document.getElementById("chkHeat");
const infoBox = document.getElementById("infoCount");

// Panel resumen
const panelResumen      = document.getElementById("panelResumen");
const panelResumenTitulo= document.getElementById("panelResumenTitulo");
const panelResumenSub   = document.getElementById("panelResumenSub");
const resPromedio       = document.getElementById("resPromedio");
const resTituloBloque   = document.getElementById("resTituloBloque");
const resTotal          = document.getElementById("resTotal");
const resDisp           = document.getElementById("resDisp");
const resMon            = document.getElementById("resMon");
const resRec            = document.getElementById("resRec");

// Panel ATM
const panelATM   = document.getElementById("panelATM");
const atmDetalle = document.getElementById("atmDetalle");
const btnVolver  = document.getElementById("btnVolver");

// Títulos según capa
if(TIPO_MAPA === "oficinas"){
  panelResumenTitulo.textContent = "Resumen — Oficinas";
  resTituloBloque.textContent    = "ATMs en oficinas";
} else if(TIPO_MAPA === "islas"){
  panelResumenTitulo.textContent = "Resumen — Islas";
  resTituloBloque.textContent    = "ATMs en islas";
} else if(TIPO_MAPA === "agentes"){
  panelResumenTitulo.textContent = "Resumen — Agentes";
  resTituloBloque.textContent    = "ATMs en agentes";
}

// ------------------- combos dependientes --------------------
function updateProvincias(){
  let d = selDep.value;
  selProv.innerHTML = '<option value="">-- Todas --</option>';
  if(d && PROV_BY_DEPT[d]){
    PROV_BY_DEPT[d].forEach(p => {
      selProv.innerHTML += `<option value="${p}">${p}</option>`;
    });
  }
  updateDistritos();
}

function updateDistritos(){
  let p = selProv.value;
  selDist.innerHTML = '<option value="">-- Todos --</option>';
  if(p && DIST_BY_PROV[p]){
    DIST_BY_PROV[p].forEach(x => {
      selDist.innerHTML += `<option value="${x}">${x}</option>`;
    });
  }
}

selDep.onchange  = ()=>{ updateProvincias(); fetchPoints(); };
selProv.onchange = ()=>{ updateDistritos(); fetchPoints(); };
selDist.onchange = ()=> fetchPoints();
selDiv.onchange  = ()=> fetchPoints();
chkHeat.onchange = ()=> fetchPoints();

btnVolver.onclick = ()=>{
  panelATM.classList.add("hidden");
  panelATM.classList.remove("glow");
  panelResumen.classList.remove("hidden");
};

// ------------------- Iconos ----------------------
function getIcon(pt){
  const ubic = (pt.ubicacion || "").toUpperCase();
  if(ubic.includes("OFICINA")){
    return L.divIcon({
      className:"icon-bank",
      html:"<div>🏦</div>",
      iconSize:[32,32],
      iconAnchor:[16,16]
    });
  }
  if(ubic.includes("ISLA")){
    return L.divIcon({
      className:"icon-isla",
      html:"<div>🌐</div>",
      iconSize:[32,32],
      iconAnchor:[16,16]
    });
  }
  if(ubic.includes("AGENTE")){
    return L.divIcon({
      className:"icon-bank",
      html:"<div>🧍</div>",
      iconSize:[30,30],
      iconAnchor:[15,15]
    });
  }
  const color = (pt.promedio || 0) >= 4 ? "red" : "green";
  return L.divIcon({
    className:"icon-round",
    html:`<div style="background:${color};"></div>`,
    iconSize:[14,14],
    iconAnchor:[7,7]
  });
}

// ---------------- Panel ATM seleccionado ----------
function showATMPanel(pt){
  const lineaUbic = `${pt.departamento} / ${pt.provincia} / ${pt.distrito}`;

  const texto = `
_____________________
 ATM ${pt.atm}
_____________________

• Nombre: ${pt.nombre}
• Dirección: ${pt.direccion}
• División: ${pt.division}
• Tipo: ${pt.tipo}
• Ubicación: ${pt.ubicacion}

• Dpto/Prov/Dist:
  ${lineaUbic}

_____________________
Promedio: ${pt.promedio}
_____________________
`;

  atmDetalle.textContent = texto;
  panelResumen.classList.add("hidden");
  panelATM.classList.remove("hidden");
  panelATM.classList.add("glow");
}

// ------------------- FETCH + RENDER ----------------
async function fetchPoints(){
  const d  = selDep.value;
  const p  = selProv.value;
  const di = selDist.value;
  const dv = selDiv.value;

  const qs = `tipo=${TIPO_MAPA}&departamento=${encodeURIComponent(d)}&provincia=${encodeURIComponent(p)}&distrito=${encodeURIComponent(di)}&division=${encodeURIComponent(dv)}`;
  infoBox.textContent = "...";

  // Siempre, al cambiar filtros, volvemos al panel resumen
  panelATM.classList.add("hidden");
  panelATM.classList.remove("glow");
  panelResumen.classList.remove("hidden");

  const res = await fetch(`/api/points?${qs}`);
  const data = await res.json();

  infoBox.textContent = data.length;
  markers.clearLayers();
  heat.setLatLngs([]);

  let heatPts = [];
  let bounds  = [];
  let sumProm = 0;

  let cTotal = 0, cDisp = 0, cMon = 0, cRec = 0;

  data.forEach(pt => {
    cTotal++;
    sumProm += (pt.promedio || 0);

    const tipoUpper = (pt.tipo || "").toString().toUpperCase();
    if(tipoUpper.includes("DISPENSADOR")) cDisp++;
    if(tipoUpper.includes("MONEDERO"))    cMon++;
    if(tipoUpper.includes("RECICLADOR"))  cRec++;

    const icon = getIcon(pt);
    const popup = `
      <div class="popup-title">${pt.nombre}</div>
      <div class="popup-row"><b>ATM:</b> ${pt.atm}</div>
      <div class="popup-row"><b>Dirección:</b> ${pt.direccion}</div>
      <div class="popup-row"><b>División:</b> ${pt.division}</div>
      <div class="popup-row"><b>Tipo:</b> ${pt.tipo}</div>
      <div class="popup-row"><b>Ubicación:</b> ${pt.ubicacion}</div>
      <div class="popup-row"><b>Depto/Prov/Dist:</b> ${pt.departamento} / ${pt.provincia} / ${pt.distrito}</div>
      <div class="popup-row"><b>Promedio:</b> ${pt.promedio}</div>
    `;
    const m = L.marker([pt.lat, pt.lon], {icon}).bindPopup(popup);
    m.on("click", () => showATMPanel(pt));
    markers.addLayer(m);

    heatPts.push([pt.lat, pt.lon, Math.max(1, pt.promedio || 1)]);
    bounds.push([pt.lat, pt.lon]);
  });

  heat.setLatLngs(heatPts);

  if(bounds.length === 1){
    map.setView(bounds[0], 16);
  }else if(bounds.length > 1){
    map.fitBounds(bounds, {padding:[20,20]});
  }else{
    map.setView(INITIAL_CENTER, INITIAL_ZOOM);
  }

  if(chkHeat.checked){
    if(!map.hasLayer(heat)) heat.addTo(map);
  }else{
    if(map.hasLayer(heat)) map.removeLayer(heat);
  }

  // Actualizar resumen
  if(cTotal > 0){
    const prom = Math.round(sumProm);
    resPromedio.textContent = prom.toString();
  }else{
    resPromedio.textContent = "0";
  }
  resTotal.textContent = cTotal.toString();
  resDisp.textContent  = cDisp.toString();
  resMon.textContent   = cMon.toString();
  resRec.textContent   = cRec.toString();
}

// Inicial
updateProvincias();
fetchPoints();
</script>

</body>
</html>
"""

# ============================================================
# 8. TEMPLATE MAPA — POPUP ELIMINADO
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
header h1{
  margin:0;
  font-size:1.9rem;
}
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

/* CONTROLES SUPERIORES */
.topbar{
  padding:16px 20px 8px 20px;
}
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
.controls label{
  font-size:13px;
  color:var(--muted);
  display:flex;
  align-items:center;
  gap:6px;
}
select{
  padding:6px 10px;
  border-radius:8px;
  border:1px solid #d0d7e3;
}
input[type="checkbox"]{
  transform:scale(1.05);
}

/* LAYOUT PRINCIPAL */
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
.side{
  width:330px;
}
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
.muted{
  color:var(--muted);
  font-size:12px;
}

/* Panel ATM seleccionado */
.side-card-atm{
  font-family:"Consolas","Fira Code",monospace;
  white-space:pre-line;
  line-height:1.35;
  border-left:4px solid var(--bbva-blue);
  position:relative;
}
.side-card-atm h3{
  margin:0 0 6px 0;
  font-size:14px;
}
.btn-small{
  display:inline-block;
  margin-top:8px;
  padding:4px 10px;
  border-radius:6px;
  border:none;
  background:var(--bbva-blue);
  color:white;
  font-size:12px;
  cursor:pointer;
}

/* Glow suave */
@keyframes panelGlow{
  0%{box-shadow:0 0 0 rgba(20,100,165,0.0);}
  50%{box-shadow:0 0 18px rgba(20,100,165,0.55);}
  100%{box-shadow:0 0 0 rgba(20,100,165,0.0);}
}
.side-card-atm.glow{
  animation:panelGlow 2.2s ease-in-out infinite;
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
      <select id="selProvincia">
        <option value="">-- Todas --</option>
      </select>
    </label>

    <label>Distrito:
      <select id="selDistrito">
        <option value="">-- Todos --</option>
      </select>
    </label>

    <label>División:
      <select id="selDivision">
        <option value="">-- Todas --</option>
        {% for dv in divisiones %}
        <option value="{{dv}}">{{dv}}</option>
        {% endfor %}
      </select>
    </label>

    <label style="margin-left:16px;">
      <input type="checkbox" id="chkHeat" checked> Heatmap
    </label>

    <div style="flex:1"></div>

    <div style="font-size:13px; color:var(--muted);">
      Mostrando <span id="infoCount">--</span> ATMs
    </div>
  </div>
</div>

<div class="main">
  <div id="map"></div>

  <div class="side">
    <!-- PANEL RESUMEN -->
    <div id="panelResumen" class="side-card">
      <div class="side-title" id="panelResumenTitulo">Resumen</div>
      <div class="muted" id="panelResumenSub">Promedio total:</div>
      <div style="margin-top:4px;">
        <b>Promedio total:</b> <span id="resPromedio">0</span>
      </div>
      <div style="margin-top:6px; font-weight:600;" id="resTituloBloque">ATMs</div>
      <div class="muted" style="margin-top:2px;">Total: <span id="resTotal">0</span></div>
      <div class="muted">Dispensador: <span id="resDisp">0</span></div>
      <div class="muted">Monedero: <span id="resMon">0</span></div>
      <div class="muted">Reciclador: <span id="resRec">0</span></div>

      <div style="margin-top:10px; font-weight:600;">Leyenda</div>
      <div class="muted">
        <div>🔴 ATM ≥ 4</div>
        <div>🟢 ATM ≤ 3</div>
        <div>🏦 Oficina</div>
        <div>🌐 Isla</div>
        <div>🧍 Agente</div>
      </div>
    </div>

    <!-- PANEL ATM SELECCIONADO -->
    <div id="panelATM" class="side-card side-card-atm hidden">
      <h3>Panel del ATM seleccionado</h3>
      <div id="atmDetalle" style="font-size:12px; margin-top:4px;"></div>
      <button id="btnVolver" class="btn-small">VOLVER</button>
    </div>
  </div>
</div>

<script src="https://unpkg.com/leaflet@1.9.4/dist/leaflet.js"></script>
<script src="https://unpkg.com/leaflet.markercluster@1.5.3/dist/markercluster.js"></script>
<script src="https://unpkg.com/leaflet.heat/dist/leaflet-heat.js"></script>

<script>
const PROV_BY_DEPT = {{ provincias_by_dept|tojson }};
const DIST_BY_PROV = {{ dist_by_prov|tojson }};
const TIPO_MAPA    = "{{ tipo_mapa }}";
const INITIAL_CENTER = [{{ initial_center[0] }}, {{ initial_center[1] }}];
const INITIAL_ZOOM   = {{ initial_zoom }};

const map = L.map('map').setView(INITIAL_CENTER, INITIAL_ZOOM);
L.tileLayer('https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png',{ maxZoom:19 }).addTo(map);

const markers = L.markerClusterGroup({chunkedLoading:true});
const heat    = L.heatLayer([], {radius:28, blur:22});
markers.addTo(map);
heat.addTo(map);

// Combos y panel
const selDep  = document.getElementById("selDepartamento");
const selProv = document.getElementById("selProvincia");
const selDist = document.getElementById("selDistrito");
const selDiv  = document.getElementById("selDivision");
const chkHeat = document.getElementById("chkHeat");
const infoBox = document.getElementById("infoCount");

const panelResumen = document.getElementById("panelResumen");
const panelATM     = document.getElementById("panelATM");
const atmDetalle   = document.getElementById("atmDetalle");
const btnVolver    = document.getElementById("btnVolver");

btnVolver.onclick = ()=>{
  panelATM.classList.add("hidden");
  panelATM.classList.remove("glow");
  panelResumen.classList.remove("hidden");
};

// ------- SIN POPUP ---------
function getIcon(pt){
  const ubic = (pt.ubicacion || "").toUpperCase();

  if(ubic.includes("OFICINA")){
    return L.divIcon({ className:"", html:"<div>🏦</div>", iconSize:[32,32], iconAnchor:[16,16] });
  }
  if(ubic.includes("ISLA")){
    return L.divIcon({ className:"", html:"<div>🌐</div>", iconSize:[32,32], iconAnchor:[16,16] });
  }
  if(ubic.includes("AGENTE")){
    return L.divIcon({ className:"", html:"<div>🧍</div>", iconSize:[30,30], iconAnchor:[15,15] });
  }

  const color = (pt.promedio || 0) >= 4 ? "red" : "green";
  return L.divIcon({
    className:"icon-round",
    html:`<div style="width:14px;height:14px;border-radius:50%;background:${color};border:2px solid white"></div>`,
    iconSize:[14,14],
    iconAnchor:[7,7]
  });
}

function showATMPanel(pt){
  const texto = `
_____________________
 ATM ${pt.atm}
_____________________

• Nombre: ${pt.nombre}
• Dirección: ${pt.direccion}
• División: ${pt.division}
• Tipo: ${pt.tipo}
• Ubicación: ${pt.ubicacion}

• Dpto/Prov/Dist:
  ${pt.departamento} / ${pt.provincia} / ${pt.distrito}

_____________________
Promedio: ${pt.promedio}
_____________________
`;
  atmDetalle.textContent = texto;
  panelResumen.classList.add("hidden");
  panelATM.classList.remove("hidden");
  panelATM.classList.add("glow");
}

// -------- FILTRADO + RENDER --------
async function fetchPoints(){
  const qs = `tipo=${TIPO_MAPA}&departamento=${selDep.value}&provincia=${selProv.value}&distrito=${selDist.value}&division=${selDiv.value}`;
  const res = await fetch('/api/points?' + qs);
  const data = await res.json();

  infoBox.textContent = data.length;
  markers.clearLayers();
  heat.setLatLngs([]);

  let heatPts = [];
  let bounds  = [];

  data.forEach(pt=>{
    const icon = getIcon(pt);

    // ❌ popup eliminado
    const m = L.marker([pt.lat, pt.lon], {icon});
    m.on("click", ()=> showATMPanel(pt));
    markers.addLayer(m);

    heatPts.push([pt.lat, pt.lon, Math.max(1, pt.promedio || 1)]);
    bounds.push([pt.lat, pt.lon]);
  });

  heat.setLatLngs(heatPts);

  if(bounds.length === 1) map.setView(bounds[0], 16);
  else if(bounds.length > 1) map.fitBounds(bounds, {padding:[20,20]});
  else map.setView(INITIAL_CENTER, INITIAL_ZOOM);
}

selDep.onchange  = ()=>{ fetchPoints(); };
selProv.onchange = ()=>{ fetchPoints(); };
selDist.onchange = ()=> fetchPoints();
selDiv.onchange  = ()=> fetchPoints();
chkHeat.onchange = ()=> fetchPoints();

fetchPoints();
</script>

</body>
</html>
"""


