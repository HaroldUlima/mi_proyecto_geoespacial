# ============================================================
#   PARTE 1 / 2  —  BACKEND COMPLETO (SIN TEMPLATE)
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
# 2. LECTURA ÚNICA DEL EXCEL PRINCIPAL (1974 ATMs)
# ============================================================
BASE_DIR = os.path.dirname(__file__)
excel_main = os.path.join(BASE_DIR, "data", "Mapa Geoespacial ATM (1) (1).xlsx")

if not os.path.exists(excel_main):
    raise FileNotFoundError("No encontré archivo Excel principal de ATMs.")

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
COL_ATM  = find_col(["COD ATM","ATM"]) or "ATM"
COL_NAME = find_col(["NOMBRE","CAJERO"]) or None
COL_DIV  = find_col(["DIVISION"]) or "DIVISION"
COL_UBIC = find_col(["UBICACION"]) or "UBICACION INTERNA"
COL_TIPO = find_col(["TIPO"]) or "TIPO"
COL_DEPT = find_col(["DEPARTAMENTO"]) or "DEPARTAMENTO"
COL_PROV = find_col(["PROVINCIA"]) or "PROVINCIA"
COL_DIST = find_col(["DISTRITO"]) or "DISTRITO"
COL_LAT  = find_col(["LAT"]) or "LATITUD"
COL_LON  = find_col(["LON"]) or "LONGITUD"
PROM_COL = find_col(["PROM"]) or None

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
    df[COL_LAT].astype(str).str.replace(",", ".", regex=False)
                 .str.replace(r"[^\d\.\-]", "", regex=True)
                 .replace("", np.nan).astype(float)
)
df[COL_LON] = (
    df[COL_LON].astype(str).str.replace(",", ".", regex=False)
                 .str.replace(r"[^\d\.\-]", "", regex=True)
                 .replace("", np.nan).astype(float)
)

df = df.dropna(subset=[COL_LAT, COL_LON]).reset_index(drop=True)
df[PROM_COL] = pd.to_numeric(df[PROM_COL], errors="coerce").fillna(0.0)

# ============================================================
# 3. LISTAS PARA FILTROS
# ============================================================
DEPARTAMENTOS = sorted(df[COL_DEPT].dropna().astype(str).unique().tolist())

PROVINCIAS_BY_DEPT = (
    df.groupby(COL_DEPT)[COL_PROV]
      .apply(lambda s: sorted(s.dropna().unique()))
      .to_dict()
)

DIST_BY_PROV = (
    df.groupby(COL_PROV)[COL_DIST]
      .apply(lambda s: sorted(s.dropna().unique()))
      .to_dict()
)

DIVISIONES = sorted(df[COL_DIV].dropna().astype(str).unique())

# ============================================================
# 4. FLASK + LOGIN
# ============================================================
app = Flask(__name__)
app.secret_key = os.getenv("SECRET_KEY", "fallback_local")

APP_USER = os.getenv("APP_USERNAME", "admin")
APP_PASS = os.getenv("APP_PASSWORD", "123")

@app.after_request
def add_header(resp):
    resp.headers["Cache-Control"] = "no-store, no-cache, must-revalidate, max-age=0"
    resp.headers["Pragma"] = "no-cache"
    resp.headers["Expires"] = "0"
    return resp

# ---------- Template login ---------
LOGIN_TEMPLATE = """
<!DOCTYPE html>
<html>
<head><meta charset="utf-8"><title>Login</title></head>
<body>
  <form method="post">
      <h3>Acceso</h3>
      <input name="username" placeholder="Usuario"><br><br>
      <input name="password" type="password" placeholder="Contraseña"><br><br>
      <button type="submit">Entrar</button>
  </form>
  {% if error %}<p style='color:red;'>{{error}}</p>{% endif %}
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

@app.route("/login", methods=["GET","POST"])
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
# 5. SELECTOR
# ============================================================
SELECTOR_TEMPLATE = """
<!DOCTYPE html>
<html>
<head><meta charset="utf-8"><title>Selector</title></head>
<body>
  <h1>Seleccionar Capa</h1>
  <button onclick="location.href='/mapa/islas'">Capa ISLAS (Unificado)</button>
</body>
</html>
"""

@app.route("/selector")
@login_required
def selector():
    return render_template_string(SELECTOR_TEMPLATE)

# ============================================================
# 6. RUTA PRINCIPAL DEL MAPA (ISLAS = TODO UNIFICADO)
# ============================================================
@app.route("/mapa/islas")
@login_required
def mapa_islas():
    initial_center = df[[COL_LAT, COL_LON]].mean().tolist()
    return render_template_string(
        TEMPLATE_MAPA,
        tipo_mapa="islas",
        departamentos=DEPARTAMENTOS,
        provincias_by_dept=PROVINCIAS_BY_DEPT,
        dist_by_prov=DIST_BY_PROV,
        divisiones=DIVISIONES,
        initial_center=initial_center,
        initial_zoom=6,
    )

# ============================================================
# 7. API DE PUNTOS (UNIFICADO)
# ============================================================
@app.route("/api/points")
@login_required
def api_points():

    dpto = request.args.get("departamento", "").upper().strip()
    prov = request.args.get("provincia", "").upper().strip()
    dist = request.args.get("distrito", "").upper().strip()

    dff = df.copy()
    dff[COL_DEPT] = dff[COL_DEPT].str.upper().str.strip()
    dff[COL_PROV] = dff[COL_PROV].str.upper().str.strip()
    dff[COL_DIST] = dff[COL_DIST].str.upper().str.strip()
    dff[COL_UBIC] = dff[COL_UBIC].str.upper().str.strip()
    dff[COL_TIPO] = dff[COL_TIPO].astype(str).str.upper()

    # Filtros
    if dpto:
        dff = dff[dff[COL_DEPT] == dpto]
    if prov:
        dff = dff[dff[COL_PROV] == prov]
    if dist:
        dff = dff[dff[COL_DIST] == dist]

    # ---------------------------
    # CÁLCULOS PANEL ESTÁTICO
    # ---------------------------
    total_oficinas = df[df[COL_UBIC].str.contains("OFICINA", na=False)].shape[0]
    total_islas    = df[df[COL_UBIC].str.contains("ISLA",    na=False)].shape[0]

    total_disp = df[df[COL_TIPO].str.contains("DISPENSADOR", na=False)].shape[0]
    total_mon  = df[df[COL_TIPO].str.contains("MONEDERO",    na=False)].shape[0]
    total_rec  = df[df[COL_TIPO].str.contains("RECICLADOR",  na=False)].shape[0]

    promedio_total = float(df[PROM_COL].mean())

    puntos = []
    for _, r in dff.iterrows():
        nombre = str(r.get(COL_NAME, r.get(COL_ATM, "")))
        puntos.append({
            "lat": float(r[COL_LAT]),
            "lon": float(r[COL_LON]),
            "atm": str(r.get(COL_ATM, "")),
            "nombre": nombre,
            "division": str(r.get(COL_DIV, "")),
            "tipo": str(r.get(COL_TIPO, "")),
            "ubicacion": str(r.get(COL_UBIC, "")),
            "departamento": str(r.get(COL_DEPT, "")),
            "provincia": str(r.get(COL_PROV, "")),
            "distrito": str(r.get(COL_DIST, "")),
            "promedio": float(r.get(PROM_COL, 0)),
            "direccion": get_address(float(r[COL_LAT]), float(r[COL_LON])),
        })

    return jsonify({
        "puntos": puntos,
        "total_oficinas": total_oficinas,
        "total_islas": total_islas,
        "total_disp": total_disp,
        "total_mon": total_mon,
        "total_rec": total_rec,
        "promedio_total": promedio_total
    })

# ============================================================
# 8. TEMPLATE_MAPA (PARTE 2)
# ============================================================



TEMPLATE_MAPA = """
<!doctype html>
<html>
<head>
<meta charset="utf-8">
<title>Mapa BBVA — ISLAS (UNIFICADO)</title>
<meta name="viewport" content="width=device-width, initial-scale=1.0">

<link rel="stylesheet" href="https://unpkg.com/leaflet@1.9.4/dist/leaflet.css"/>
<link rel="stylesheet" href="https://unpkg.com/leaflet.markercluster@1.5.3/dist/MarkerCluster.css"/>
<link rel="stylesheet" href="https://unpkg.com/leaflet.markercluster@1.5.3/dist/MarkerCluster.Default.css"/>

<style>
:root{
  --bbva-blue:#1464A5;
  --muted:#6b7a8a;
}
html,body{
  margin:0; padding:0; height:100%;
  font-family:Arial,Helvetica,sans-serif;
  background:#eef4fb;
}
header{
  background:#003366; color:white;
  height:60px; display:flex; align-items:center; justify-content:center;
  position:relative;
}
header h1{margin:0; font-size:1.7rem;}

.main{
  display:flex; padding:10px; gap:12px;
}
#map{
  flex:1; height:78vh;
  border-radius:12px;
  box-shadow:0 4px 18px rgba(0,0,0,0.15);
}
.side{
  width:300px;
}
.card{
  background:white; padding:14px;
  border-radius:12px;
  box-shadow:0 3px 14px rgba(0,0,0,0.12);
  margin-bottom:12px;
}
.hidden{ display:none; }

.btn{
  padding:6px 12px;
  background:#1464A5;
  border-radius:8px;
  color:white;
  border:none;
  cursor:pointer;
}

</style>
</head>

<body>

<header>
  <h1>Mapa BBVA — ISLAS (UNIFICADO)</h1>
</header>

<div class="main">

  <!-- MAPA -->
  <div id="map"></div>

  <!-- PANEL -->
  <div class="side">

    <!-- PANEL RESUMEN -->
    <div id="panelResumen" class="card">
      <h3>Resumen</h3>

      <p>Promedio total: <b><span id="resProm"></span></b></p>
      <p>Total ATMs en Oficinas: <b><span id="resOfi"></span></b></p>
      <p>Total ATMs en Islas: <b><span id="resIsla"></span></b></p>

      <p>Dispensador: <b><span id="resDisp"></span></b></p>
      <p>Monedero: <b><span id="resMon"></span></b></p>
      <p>Reciclador: <b><span id="resRec"></span></b></p>
    </div>

    <!-- PANEL ATM DETALLE -->
    <div id="panelATM" class="card hidden">
      <pre id="atmDetalle"></pre>
      <button class="btn" id="btnVolver">VOLVER</button>
    </div>

  </div>
</div>

<script src="https://unpkg.com/leaflet@1.9.4/dist/leaflet.js"></script>
<script src="https://unpkg.com/leaflet.markercluster@1.5.3/dist/markercluster.js"></script>
<script src="https://unpkg.com/leaflet.heat/dist/leaflet-heat.js"></script>

<script>
const INITIAL_CENTER = [{{ initial_center[0] }}, {{ initial_center[1] }}];
const INITIAL_ZOOM   = {{ initial_zoom }};

const map = L.map('map').setView(INITIAL_CENTER, INITIAL_ZOOM);
L.tileLayer('https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png',{maxZoom:19}).addTo(map);

const markers = L.markerClusterGroup({chunkedLoading:true});
markers.addTo(map);

/* PANEL */
const panelResumen = document.getElementById("panelResumen");
const panelATM     = document.getElementById("panelATM");
const atmDetalle   = document.getElementById("atmDetalle");
document.getElementById("btnVolver").onclick = ()=>{
    panelATM.classList.add("hidden");
    panelResumen.classList.remove("hidden");
};

/* RESUMEN SPANS */
const resProm = document.getElementById("resProm");
const resOfi  = document.getElementById("resOfi");
const resIsla = document.getElementById("resIsla");
const resDisp = document.getElementById("resDisp");
const resMon  = document.getElementById("resMon");
const resRec  = document.getElementById("resRec");

/* ICONOS */
function getIcon(pt){
    const ubic = (pt.ubicacion||"");
    if(ubic.includes("OFICINA")) return L.divIcon({html:"🏦",iconSize:[30,30]});
    if(ubic.includes("ISLA"))    return L.divIcon({html:"🌐",iconSize:[30,30]});
    return L.divIcon({html:"•",iconSize:[8,8]});
}

/* MOSTRAR DETALLE */
function showATM(pt){
    atmDetalle.textContent =
`ATM ${pt.atm}
Nombre: ${pt.nombre}
Ubicación: ${pt.ubicacion}
Tipo: ${pt.tipo}
Division: ${pt.division}

${pt.departamento} / ${pt.provincia} / ${pt.distrito}

Promedio: ${pt.promedio}
Dirección: ${pt.direccion}`;
    panelResumen.classList.add("hidden");
    panelATM.classList.remove("hidden");
}

/* FETCH */
async function loadPoints(){
    const res = await fetch("/api/points");
    const data = await res.json();

    markers.clearLayers();

    data.puntos.forEach(pt=>{
        const m = L.marker([pt.lat,pt.lon],{icon:getIcon(pt)});
        m.on("click",()=>showATM(pt));
        markers.addLayer(m);
    });

    resProm.textContent = Math.round(data.promedio_total);
    resOfi.textContent  = data.total_oficinas;
    resIsla.textContent = data.total_islas;
    resDisp.textContent = data.total_disp;
    resMon.textContent  = data.total_mon;
    resRec.textContent  = data.total_rec;
}

loadPoints();
</script>

</body>
</html>
"""