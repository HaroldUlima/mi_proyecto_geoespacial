# ============================================================
#   BACKEND COMPLETO + LOGIN + SELECTOR
#   CAPAS: ISLAS (ATMs) + AGENTES + OFICINAS
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
# FUNCIÓN DE NORMALIZACIÓN
# ============================================================
def normalize_col(s):
    s = str(s)
    s = unicodedata.normalize("NFKD", s)
    s = s.encode("ascii", "ignore").decode("utf-8")
    s = s.upper().strip()
    s = re.sub(r"[^A-Z0-9 ]+", " ", s)
    return re.sub(r"\s+", " ", s).strip()


def find_col(norm_map, keys):
    for norm, orig in norm_map.items():
        for k in keys:
            if k in norm:
                return orig
    return None


# ============================================================
# 2. CARGAR EXCEL PRINCIPAL (ISLAS / ATMs)
# ============================================================
BASE_DIR = os.path.dirname(__file__)
excel_main = os.path.join(BASE_DIR, "data", "Mapa Geoespacial ATM (1) (1).xlsx")

if not os.path.exists(excel_main):
    raise FileNotFoundError("No encontré archivo Excel de ATMs.")

raw = pd.read_excel(excel_main)

norm_map = {normalize_col(c): c for c in raw.columns}

COL_ATM = find_col(norm_map, ["COD_ATM", "ATM"]) or "ATM"
COL_NAME = find_col(norm_map, ["NOMBRE", "CAJERO"])
COL_DEPT = find_col(norm_map, ["DEPARTAMENTO"]) or "DEPARTAMENTO"
COL_PROV = find_col(norm_map, ["PROVINCIA"]) or "PROVINCIA"
COL_DIST = find_col(norm_map, ["DISTRITO"]) or "DISTRITO"
COL_LAT = find_col(norm_map, ["LATITUD", "LAT"]) or "LATITUD"
COL_LON = find_col(norm_map, ["LONGITUD", "LON"]) or "LONGITUD"
COL_DIV = find_col(norm_map, ["DIVISION", "DIVISIÓN"]) or "DIVISION"
COL_TIPO = find_col(norm_map, ["TIPO"]) or "TIPO"
COL_UBIC = find_col(norm_map, ["UBICACION", "UBICACIÓN"]) or "UBICACION"
PROM_COL = find_col(norm_map, ["PROMEDIO", "PROM"])

if PROM_COL is None:
    raw["PROM_FAKE"] = 0.0
    PROM_COL = "PROM_FAKE"

# asegurar columnas
for col in [COL_ATM, COL_DEPT, COL_PROV, COL_DIST, COL_LAT, COL_LON, COL_DIV, COL_TIPO, COL_UBIC, PROM_COL]:
    if col not in raw.columns:
        raw[col] = ""

df = raw.copy()

# limpiar coordenadas
df[COL_LAT] = (
    df[COL_LAT]
    .astype(str)
    .str.replace(",", ".", regex=False)
    .str.replace(r"[^\d.-]", "", regex=True)
    .replace("", np.nan)
    .astype(float)
)

df[COL_LON] = (
    df[COL_LON]
    .astype(str)
    .str.replace(",", ".", regex=False)
    .str.replace(r"[^\d.-]", "", regex=True)
    .replace("", np.nan)
    .astype(float)
)

df = df.dropna(subset=[COL_LAT, COL_LON]).reset_index(drop=True)
df[PROM_COL] = pd.to_numeric(df[PROM_COL], errors="coerce").fillna(0.0)


# ============================================================
# 2B. CARGAR EXCEL DE AGENTES
# ============================================================
excel_agentes = os.path.join(BASE_DIR, "data", "AGENTES.xlsx")
if not os.path.exists(excel_agentes):
    raise FileNotFoundError("No encontré Excel de AGENTES.xlsx.")

raw_ag = pd.read_excel(excel_agentes)
norm_map_ag = {normalize_col(c): c for c in raw_ag.columns}

COLA_ID = find_col(norm_map_ag, ["TERMINAL", "ID"]) or "TERMINAL"
COLA_COM = find_col(norm_map_ag, ["COMERCIO"]) or "COMERCIO"
COLA_DEPT = find_col(norm_map_ag, ["DEPARTAMENTO"])
COLA_PROV = find_col(norm_map_ag, ["PROVINCIA"])
COLA_DIST = find_col(norm_map_ag, ["DISTRITO"])
COLA_LAT = find_col(norm_map_ag, ["LATITUD", "LAT"]) or "LATITUD"
COLA_LON = find_col(norm_map_ag, ["LONGITUD", "LON"]) or "LONGITUD"
COLA_DIV = find_col(norm_map_ag, ["DIVISION", "DIVISIÓN"]) or "DIVISION"
COLA_DIR = find_col(norm_map_ag, ["DIRECCION", "DIRECCIÓN"]) or "DIRECCION"
COLA_CAPA = find_col(norm_map_ag, ["CAPA"]) or "CAPA"
COLA_TRX_OCT = find_col(norm_map_ag, ["TRXS OCTUBRE", "TRX OCTUBRE"])
COLA_TRX_NOV = find_col(norm_map_ag, ["TRXS NOV", "TRXS NOVIEMBRE"])
PROMA_COL = find_col(norm_map_ag, ["PROMEDIO", "PROM"])

if PROMA_COL is None:
    raw_ag["PROM_FAKE"] = 0.0
    PROMA_COL = "PROM_FAKE"

# limpieza coordenadas agentes
raw_ag[COLA_LAT] = (
    raw_ag[COLA_LAT]
    .astype(str)
    .str.replace(",", ".", regex=False)
    .str.replace(r"[^\d.-]", "", regex=True)
    .replace("", np.nan)
    .astype(float)
)
raw_ag[COLA_LON] = (
    raw_ag[COLA_LON]
    .astype(str)
    .str.replace(",", ".", regex=False)
    .str.replace(r"[^\d.-]", "", regex=True)
    .replace("", np.nan)
    .astype(float)
)

df_agentes = raw_ag.dropna(subset=[COLA_LAT, COLA_LON]).reset_index(drop=True)
df_agentes[PROMA_COL] = pd.to_numeric(df_agentes[PROMA_COL], errors="coerce").fillna(0.0)


# ============================================================
# 2C. CARGAR EXCEL DE OFICINAS
# ============================================================
excel_oficinas = os.path.join(BASE_DIR, "data", "OFICINAS.xlsx")
if not os.path.exists(excel_oficinas):
    raise FileNotFoundError("No encontré Excel de OFICINAS.xlsx.")

raw_of = pd.read_excel(excel_oficinas)
norm_map_of = {normalize_col(c): c for c in raw_of.columns}

COLF_ID = find_col(norm_map_of, ["COD OFIC", "COD_OFIC"]) or "COD OFIC."
COLF_NAME = find_col(norm_map_of, ["OFICINA"]) or "OFICINA"
COLF_DIV = find_col(norm_map_of, ["DIVISION", "DIVISIÓN"]) or "DIVISION"
COLF_DEPT = find_col(norm_map_of, ["DEPARTAMENTO"])
COLF_PROV = find_col(norm_map_of, ["PROVINCIA"])
COLF_DIST = find_col(norm_map_of, ["DISTRITO"])
COLF_LAT = find_col(norm_map_of, ["LATITUD", "LAT"]) or "LATITUD"
COLF_LON = find_col(norm_map_of, ["LONGITUD", "LON"]) or "LONGITUD"
COLF_TRX = find_col(norm_map_of, ["TRX", "TRXS"]) or "TRX"

# limpiar coordenadas oficinas
raw_of[COLF_LAT] = (
    raw_of[COLF_LAT]
    .astype(str)
    .str.replace(",", ".", regex=False)
    .str.replace(r"[^\d.-]", "", regex=True)
    .replace("", np.nan)
    .astype(float)
)
raw_of[COLF_LON] = (
    raw_of[COLF_LON]
    .astype(str)
    .str.replace(",", ".", regex=False)
    .str.replace(r"[^\d.-]", "", regex=True)
    .replace("", np.nan)
    .astype(float)
)

df_oficinas = raw_of.dropna(subset=[COLF_LAT, COLF_LON]).reset_index(drop=True)
df_oficinas[COLF_TRX] = pd.to_numeric(df_oficinas[COLF_TRX], errors="coerce").fillna(0.0)


# ============================================================
# 3. LISTAS PARA FILTROS — JERARQUÍA COMPLETA
# ============================================================
DEPARTAMENTOS = sorted(
    set(df[COL_DEPT].dropna().astype(str))
    | set(df_agentes[COLA_DEPT].dropna().astype(str))
    | set(df_oficinas[COLF_DEPT].dropna().astype(str))
)

PROVINCIAS_BY_DEPT = {}
for d in DEPARTAMENTOS:
    provs = []
    provs += df[df[COL_DEPT] == d][COL_PROV].dropna().astype(str).tolist()
    provs += df_agentes[df_agentes[COLA_DEPT] == d][COLA_PROV].dropna().astype(str).tolist()
    provs += df_oficinas[df_oficinas[COLF_DEPT] == d][COLF_PROV].dropna().astype(str).tolist()
    PROVINCIAS_BY_DEPT[d] = sorted(set(provs))

all_provs = set(df[COL_PROV].dropna().astype(str)) \
          | set(df_agentes[COLA_PROV].dropna().astype(str)) \
          | set(df_oficinas[COLF_PROV].dropna().astype(str))

DIST_BY_PROV = {}
for p in all_provs:
    dists = []
    dists += df[df[COL_PROV] == p][COL_DIST].dropna().astype(str).tolist()
    dists += df_agentes[df_agentes[COLA_PROV] == p][COLA_DIST].dropna().astype(str).tolist()
    dists += df_oficinas[df_oficinas[COLF_PROV] == p][COLF_DIST].dropna().astype(str).tolist()
    DIST_BY_PROV[p] = sorted(set(dists))

all_dists = set(df[COL_DIST].dropna().astype(str)) \
          | set(df_agentes[COLA_DIST].dropna().astype(str)) \
          | set(df_oficinas[COLF_DIST].dropna().astype(str))

DIV_BY_DIST = {}
for di in all_dists:
    divs = []
    divs += df[df[COL_DIST] == di][COL_DIV].dropna().astype(str).tolist()
    divs += df_agentes[df_agentes[COLA_DIST] == di][COLA_DIV].dropna().astype(str).tolist()
    divs += df_oficinas[df_oficinas[COLF_DIST] == di][COLF_DIV].dropna().astype(str).tolist()
    DIV_BY_DIST[di] = sorted(set(divs))

DIVISIONES = sorted(
    set(df[COL_DIV].dropna().astype(str))
    | set(df_agentes[COLA_DIV].dropna().astype(str))
    | set(df_oficinas[COLF_DIV].dropna().astype(str))
)


# ============================================================
# LOGIN + SELECTOR
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


LOGIN_TEMPLATE = """
<!DOCTYPE html>
<html>
<head><meta charset='utf-8'><title>Login</title></head>
<body>
<form method="post">
  <input name="username" placeholder="Usuario">
  <input name="password" type="password" placeholder="Contraseña">
  <button>Entrar</button>
</form>
{{ error }}
</body>
</html>
"""


@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        if request.form.get("username") == APP_USER and request.form.get("password") == APP_PASS:
            session["user"] = APP_USER
            return redirect(url_for("selector"))
        return render_template_string(LOGIN_TEMPLATE, error="Credenciales incorrectas")
    return render_template_string(LOGIN_TEMPLATE)


@app.route("/logout")
def logout():
    session.clear()
    return redirect(url_for("login"))


# ============================================================
# SELECTOR DE CAPAS
# ============================================================
SELECTOR_TEMPLATE = """
<!DOCTYPE html>
<html>
<head><meta charset='utf-8'><title>Selector</title></head>
<body>
<h1>Selecciona capa</h1>
<ul>
  <li><a href="/mapa/islas">Islas (ATMs)</a></li>
  <li><a href="/mapa/oficinas">Oficinas</a></li>
  <li><a href="/mapa/agentes">Agentes</a></li>
</ul>
</body>
</html>
"""


@app.route("/selector")
@login_required
def selector():
    return render_template_string(SELECTOR_TEMPLATE)


# ============================================================
# RUTA MAPA
# ============================================================
@app.route("/mapa/<tipo>")
@login_required
def mapa_tipo(tipo):
    if tipo not in ["islas", "oficinas", "agentes"]:
        return "Capa inválida", 404

    initial_center = df[[COL_LAT, COL_LON]].mean().tolist()

    return render_template_string(
        TEMPLATE_MAPA,
        tipo_mapa=tipo,
        departamentos=DEPARTAMENTOS,
        provincias_by_dept=PROVINCIAS_BY_DEPT,
        dist_by_prov=DIST_BY_PROV,
        div_by_dist=DIV_BY_DIST,
        divisiones=DIVISIONES,
        initial_center=initial_center,
        initial_zoom=6
    )


# ============================================================
# API POINTS — FILTRADO JERÁRQUICO CORREGIDO
# ============================================================
@app.route("/api/points")
@login_required
def api_points():

    tipo = request.args.get("tipo", "")
    dpto = request.args.get("departamento", "").upper().strip()
    prov = request.args.get("provincia", "").upper().strip()
    dist = request.args.get("distrito", "").upper().strip()
    div  = request.args.get("division", "").upper().strip()

    # ---------------------------------------
    # CAPA ISLAS
    # ---------------------------------------
    if tipo == "islas":
        dff = df.copy()
        dff[COL_DEPT] = dff[COL_DEPT].str.upper().str.strip()
        dff[COL_PROV] = dff[COL_PROV].str.upper().str.strip()
        dff[COL_DIST] = dff[COL_DIST].str.upper().str.strip()
        dff[COL_DIV]  = dff[COL_DIV].str.upper().str.strip()

        if dpto:
            dff = dff[dff[COL_DEPT] == dpto]
        if prov:
            dff = dff[dff[COL_PROV] == prov]
        if dist:
            dff = dff[dff[COL_DIST] == dist]
        if div:
            dff = dff[dff[COL_DIV] == div]

        puntos = []
        for _, r in dff.iterrows():
            puntos.append({
                "lat": float(r[COL_LAT]),
                "lon": float(r[COL_LON]),
                "atm": str(r[COL_ATM]),
                "nombre": str(r.get(COL_NAME, r[COL_ATM])),
                "promedio": float(r[PROM_COL]),
                "division": str(r[COL_DIV]),
                "tipo": str(r[COL_TIPO]),
                "ubicacion": str(r[COL_UBIC]),
                "departamento": str(r[COL_DEPT]),
                "provincia": str(r[COL_PROV]),
                "distrito": str(r[COL_DIST]),
                "direccion": get_address(r[COL_LAT], r[COL_LON])
            })

        return jsonify({
            "puntos": puntos,
            "total_atms": len(puntos),
            "promedio_total": float(dff[PROM_COL].mean()) if len(puntos) else 0
        })

    # ---------------------------------------
    # CAPA AGENTES
    # ---------------------------------------
    if tipo == "agentes":
        dff = df_agentes.copy()
        dff[COLA_DEPT] = dff[COLA_DEPT].str.upper().str.strip()
        dff[COLA_PROV] = dff[COLA_PROV].str.upper().str.strip()
        dff[COLA_DIST] = dff[COLA_DIST].str.upper().str.strip()
        dff[COLA_DIV]  = dff[COLA_DIV].str.upper().str.strip()

        if dpto:
            dff = dff[dff[COLA_DEPT] == dpto]
        if prov:
            dff = dff[dff[COLA_PROV] == prov]
        if dist:
            dff = dff[dff[COLA_DIST] == dist]
        if div:
            dff = dff[dff[COLA_DIV] == div]

        puntos = []
        for _, r in dff.iterrows():
            puntos.append({
                "lat": float(r[COLA_LAT]),
                "lon": float(r[COLA_LON]),
                "atm": str(r[COLA_ID]),
                "nombre": str(r[COLA_COM]),
                "division": str(r[COLA_DIV]),
                "departamento": str(r[COLA_DEPT]),
                "provincia": str(r[COLA_PROV]),
                "distrito": str(r[COLA_DIST]),
                "direccion": str(r.get(COLA_DIR, "")),
                "promedio": float(r[PROMA_COL]),
                "tipo": "AGENTE",
                "ubicacion": "AGENTE"
            })

        return jsonify({
            "puntos": puntos,
            "total_atms": len(puntos),
            "promedio_total": float(dff[PROMA_COL].mean()) if len(puntos) else 0
        })

    # ---------------------------------------
    # CAPA OFICINAS
    # ---------------------------------------
    if tipo == "oficinas":
        dff = df_oficinas.copy()

        dff[COLF_DEPT] = dff[COLF_DEPT].str.upper().str.strip()
        dff[COLF_PROV] = dff[COLF_PROV].str.upper().str.strip()
        dff[COLF_DIST] = dff[COLF_DIST].str.upper().str.strip()
        dff[COLF_DIV]  = dff[COLF_DIV].str.upper().str.strip()

        if dpto:
            dff = dff[dff[COLF_DEPT] == dpto]
        if prov:
            dff = dff[dff[COLF_PROV] == prov]
        if dist:
            dff = dff[dff[COLF_DIST] == dist]
        if div:
            dff = dff[dff[COLF_DIV] == div]

        puntos = []
        for _, r in dff.iterrows():
            puntos.append({
                "lat": float(r[COLF_LAT]),
                "lon": float(r[COLF_LON]),
                "atm": str(r[COLF_ID]),
                "nombre": str(r[COLF_NAME]),
                "division": str(r[COLF_DIV]),
                "departamento": str(r[COLF_DEPT]),
                "provincia": str(r[COLF_PROV]),
                "distrito": str(r[COLF_DIST]),
                "direccion": "No disponible",
                "promedio": float(r[COLF_TRX]),
                "tipo": "OFICINA",
                "ubicacion": "OFICINA"
            })

        return jsonify({
            "puntos": puntos,
            "total_atms": len(puntos),
            "promedio_total": float(dff[COLF_TRX].mean()) if len(puntos) else 0
        })

    return jsonify({"puntos": []})


    # ============================================================
# 8. TEMPLATE MAPA — FRONTEND COMPLETO CORREGIDO
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
.side-card-atm{
  border-left:4px solid var(--bbva-blue);
  white-space:pre-line;
  font-family:"Consolas","Fira Code",monospace;
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

    <label>
      <input type="checkbox" id="chkHeat" checked> Heatmap
    </label>

    <div style="flex:1"></div>

    <div style="font-size:13px; color:var(--muted);">
      Mostrando <span id="infoCount">--</span>
    </div>
  </div>
</div>

<div class="main">
  <div id="map"></div>

  <div class="side">

    <div id="panelResumen" class="side-card">
      <h3 id="panelResumenTitulo">Resumen</h3>

      <div><b>Promedio total:</b> <span id="resPromedio">0</span></div>

      <div id="bloqueIslasOfi">
        <div>Total ATMs: <span id="resTotal">0</span></div>
        <div>En oficinas: <span id="resOfi">0</span></div>
        <div>En islas: <span id="resIsla">0</span></div>
      </div>

      <div id="bloqueOficinas" class="hidden">
        <div>Cantidad total de oficinas: <span id="resOficinasCount">0</span></div>
        <div>Total del promedio TRX: <span id="resOficinasProm">0</span></div>
      </div>

      <div id="bloqueAgentes" class="hidden">
        <div>Total agentes: <span id="resAgentesTotal">0</span></div>
      </div>

    </div>

    <div id="panelATM" class="side-card side-card-atm hidden">
      <h3 id="panelATMTitle">Detalle</h3>
      <div id="atmDetalle"></div>
      <button id="btnVolver">VOLVER</button>
    </div>

  </div>
</div>

<script src="https://unpkg.com/leaflet@1.9.4/dist/leaflet.js"></script>
<script src="https://unpkg.com/leaflet.markercluster@1.5.3/dist/markercluster.js"></script>
<script src="https://unpkg.com/leaflet.heat/dist/leaflet-heat.js"></script>

<script>
// =====================
//   MAPA
// =====================
const map = L.map('map').setView([{{ initial_center[0] }}, {{ initial_center[1] }}], {{ initial_zoom }});
L.tileLayer('https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png', { maxZoom:19 }).addTo(map);

const markers = L.markerClusterGroup();
const heat = L.heatLayer([], {radius:28, blur:22});
markers.addTo(map);
heat.addTo(map);

// =====================
//   DATA DE FILTROS
// =====================
const PROV_BY_DEPT = {{ provincias_by_dept|tojson }};
const DIST_BY_PROV = {{ dist_by_prov|tojson }};
const DIV_BY_DIST  = {{ div_by_dist|tojson }};
const TODAS_DIVS   = {{ divisiones|tojson }};
const TIPO_MAPA    = "{{ tipo_mapa }}";

// =====================
//   CONTROLES
// =====================
const selDep  = document.getElementById("selDepartamento");
const selProv = document.getElementById("selProvincia");
const selDist = document.getElementById("selDistrito");
const selDiv  = document.getElementById("selDivision");

// =====================
//   FILTROS JERÁRQUICOS CORREGIDOS
// =====================
function updateProvincias() {
  let d = selDep.value;
  selProv.innerHTML = '<option value="">-- Todas --</option>';

  if (d && PROV_BY_DEPT[d]) {
    PROV_BY_DEPT[d].forEach(p => {
      selProv.innerHTML += `<option value="${p}">${p}</option>`;
    });
  }

  updateDistritos();
}

function updateDistritos() {
  let p = selProv.value;
  selDist.innerHTML = '<option value="">-- Todos --</option>';

  if (p && DIST_BY_PROV[p]) {
    DIST_BY_PROV[p].forEach(d => {
      selDist.innerHTML += `<option value="${d}">${d}</option>`;
    });
  }

  updateDivisiones();
}

function updateDivisiones() {
  let di = selDist.value;

  selDiv.innerHTML = '<option value="">-- Todas --</option>';

  // Nivel más específico: distrito
  if (di && DIV_BY_DIST[di]) {
    DIV_BY_DIST[di].forEach(v => selDiv.innerHTML += `<option value="${v}">${v}</option>`);
    return;
  }

  // Si no hay distrito, mostramos TODAS las divisiones
  TODAS_DIVS.forEach(v => selDiv.innerHTML += `<option value="${v}">${v}</option>`);
}

// =====================
//   EVENTOS
// =====================
selDep.onchange  = () => { updateProvincias(); fetchPoints(); };
selProv.onchange = () => { updateDistritos(); fetchPoints(); };
selDist.onchange = () => { updateDivisiones(); fetchPoints(); };
selDiv.onchange  = fetchPoints;

// =====================
//   FETCH POINTS
// =====================
async function fetchPoints(){
  const qs = `tipo=${TIPO_MAPA}&departamento=${selDep.value}&provincia=${selProv.value}&distrito=${selDist.value}&division=${selDiv.value}`;

  const res = await fetch(`/api/points?${qs}`);
  const data = await res.json();

  const pts = data.puntos || [];

  markers.clearLayers();
  heat.setLatLngs([]);

  let heatPts = [];
  let bounds  = [];

  pts.forEach(pt => {
    let m = L.marker([pt.lat, pt.lon]);
    m.on("click", ()=> showPanel(pt));
    markers.addLayer(m);

    heatPts.push([pt.lat, pt.lon, pt.promedio || 1]);
    bounds.push([pt.lat, pt.lon]);
  });

  heat.setLatLngs(heatPts);

  if(bounds.length > 1) map.fitBounds(bounds, {padding:[20,20]});
  else if(bounds.length == 1) map.setView(bounds[0], 16);

  document.getElementById("infoCount").innerText = pts.length;

  document.getElementById("resPromedio").innerText = Math.round(data.promedio_total || 0);

  if(TIPO_MAPA === "oficinas"){
    document.getElementById("bloqueOficinas").classList.remove("hidden");
    document.getElementById("resOficinasCount").innerText = pts.length;
    document.getElementById("resOficinasProm").innerText  = Math.round(data.promedio_total || 0);
  }
}

// =====================
//   PANEL DETALLE
// =====================
function showPanel(pt){
  const detalle =
`
ATM: ${pt.atm}
Nombre: ${pt.nombre}
Dept/Prov/Dist: ${pt.departamento} / ${pt.provincia} / ${pt.distrito}
Dirección: ${pt.direccion}
Promedio: ${pt.promedio}
`;

  document.getElementById("atmDetalle").innerText = detalle;
  document.getElementById("panelATM").classList.remove("hidden");
  document.getElementById("panelResumen").classList.add("hidden");
}

document.getElementById("btnVolver").onclick = () => {
  document.getElementById("panelATM").classList.add("hidden");
  document.getElementById("panelResumen").classList.remove("hidden");
};

// iniciar
updateProvincias();
fetchPoints();

</script>

</body>
</html>
"""

