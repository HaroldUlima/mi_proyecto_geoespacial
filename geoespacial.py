# ============================================================
#   BACKEND COMPLETO — CON CAPA ISLAS + CAPA AGENTES
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
# 2. CARGAR EXCEL PRINCIPAL — ATMs (ISLAS)
# ============================================================
BASE_DIR = os.path.dirname(__file__)
excel_islas = os.path.join(BASE_DIR, "data", "Mapa Geoespacial ATM (1) (1).xlsx")

if not os.path.exists(excel_islas):
    raise FileNotFoundError("No encontré Excel de ATMs.")

raw_islas = pd.read_excel(excel_islas)

# -------- NORMALIZADOR ----------
def normalize_col(s):
    s = str(s)
    s = unicodedata.normalize("NFKD", s)
    s = s.encode("ascii", "ignore").decode("utf-8")
    s = s.upper().strip()
    s = re.sub(r"[^A-Z0-9 ]+", " ", s)
    return re.sub(r"\s+", " ", s).strip()


norm_map_islas = {normalize_col(c): c for c in raw_islas.columns}


def find_col_islas(keys):
    for norm, orig in norm_map_islas.items():
        for k in keys:
            if k in norm:
                return orig
    return None


# ---------- Columnas ISLAS ----------
COLI_ATM = find_col_islas(["COD_ATM", "ATM"]) or "ATM"
COLI_NAME = find_col_islas(["NOMBRE", "CAJERO"]) or None
COLI_DEPT = find_col_islas(["DEPARTAMENTO"]) or "DEPARTAMENTO"
COLI_PROV = find_col_islas(["PROVINCIA"]) or "PROVINCIA"
COLI_DIST = find_col_islas(["DISTRITO"]) or "DISTRITO"
COLI_LAT = find_col_islas(["LATITUD"]) or "LATITUD"
COLI_LON = find_col_islas(["LONGITUD"]) or "LONGITUD"
COLI_DIV = find_col_islas(["DIVISION"]) or "DIVISIÓN"
COLI_TIPO = find_col_islas(["TIPO"]) or "TIPO"
COLI_UBIC = find_col_islas(["UBICACION"]) or "UBICACION_INTERNA"
PROMI_COL = find_col_islas(["PROMEDIO"]) or None

if PROMI_COL is None:
    raw_islas["PROM_FAKE"] = 0.0
    PROMI_COL = "PROM_FAKE"


# Limpiar coordenadas
def clean_coords(df, col):
    df[col] = (
        df[col].astype(str)
        .str.replace(",", ".", regex=False)
        .str.replace(r"[^\d\.\-]", "", regex=True)
        .replace("", np.nan)
        .astype(float)
    )


clean_coords(raw_islas, COLI_LAT)
clean_coords(raw_islas, COLI_LON)

raw_islas = raw_islas.dropna(subset=[COLI_LAT, COLI_LON]).reset_index(drop=True)
raw_islas[PROMI_COL] = pd.to_numeric(raw_islas[PROMI_COL], errors="coerce").fillna(0.0)

df_islas = raw_islas.copy()


# ============================================================
# 3. CARGAR AGENTES — NUEVO EXCEL
# ============================================================
excel_agentes = os.path.join(BASE_DIR, "data", "AGENTES.xlsx")

if not os.path.exists(excel_agentes):
    raise FileNotFoundError("No encontré Excel de Agentes.")

raw_ag = pd.read_excel(excel_agentes)

# Normalizar columnas
norm_map_ag = {normalize_col(c): c for c in raw_ag.columns}


def find_col_ag(keys):
    for norm, orig in norm_map_ag.items():
        for k in keys:
            if k in norm:
                return orig
    return None


COLA_ID = find_col_ag(["TERMINAL", "ID"]) or "TERMINAL"
COLA_COM = find_col_ag(["COMERCIO"]) or "COMERCIO"
COLA_DEPT = find_col_ag(["DEPARTAMENTO"]) or "DEPARTAMENTO"
COLA_PROV = find_col_ag(["PROVINCIA"]) or "PROVINCIA"
COLA_DIST = find_col_ag(["DISTRITO"]) or "DISTRITO"
COLA_LAT = find_col_ag(["LATITUD"]) or "LATITUD"
COLA_LON = find_col_ag(["LONGITUD"]) or "LONGITUD"
COLA_DIR = find_col_ag(["DIRECCION"]) or "DIRECCION"
COLA_DIV = None              # NO EXISTE DIVISIÓN EN AGENTES
COLA_TIPO = "AGENTE"         # FIJO
COLA_UBIC = "AGENTE"         # FIJO
PROMA_COL = find_col_ag(["PROMEDIO"]) or None

if PROMA_COL is None:
    raw_ag["PROM_FAKE"] = 0.0
    PROMA_COL = "PROM_FAKE"

# Limpiar coords
clean_coords(raw_ag, COLA_LAT)
clean_coords(raw_ag, COLA_LON)

df_agentes = raw_ag.dropna(subset=[COLA_LAT, COLA_LON]).reset_index(drop=True)
df_agentes[PROMA_COL] = pd.to_numeric(df_agentes[PROMA_COL], errors="coerce").fillna(0.0)


# ============================================================
# 4. LISTAS JERÁRQUICAS PARA ISLAS Y AGENTES
# ============================================================
DEPARTAMENTOS = sorted(
    list(set(df_islas[COLI_DEPT].astype(str)) | set(df_agentes[COLA_DEPT].astype(str)))
)

PROVINCIAS_BY_DEPT = {}
for d in DEPARTAMENTOS:
    provs = []
    provs += df_islas[df_islas[COLI_DEPT] == d][COLI_PROV].astype(str).tolist()
    provs += df_agentes[df_agentes[COLA_DEPT] == d][COLA_PROV].astype(str).tolist()
    PROVINCIAS_BY_DEPT[d] = sorted(list(set(provs)))

DIST_BY_PROV = {}
for p in set(df_islas[COLI_PROV]) | set(df_agentes[COLA_PROV]):
    dists = []
    dists += df_islas[df_islas[COLI_PROV] == p][COLI_DIST].astype(str).tolist()
    dists += df_agentes[df_agentes[COLA_PROV] == p][COLA_DIST].astype(str).tolist()
    DIST_BY_PROV[p] = sorted(list(set(dists)))

# Divisiones solo pertenecen a ATMs
DIV_BY_DEPT = df_islas.groupby(COLI_DEPT)[COLI_DIV].apply(
    lambda x: sorted(x.dropna().unique().tolist())
).to_dict()

DIV_BY_PROV = df_islas.groupby(COLI_PROV)[COLI_DIV].apply(
    lambda x: sorted(x.dropna().unique().tolist())
).to_dict()

DIV_BY_DIST = df_islas.groupby(COLI_DIST)[COLI_DIV].apply(
    lambda x: sorted(x.dropna().unique().tolist())
).to_dict()

DIVISIONES = sorted(df_islas[COLI_DIV].dropna().unique().tolist())


# ============================================================
# 5. FLASK + LOGIN
# ============================================================
app = Flask(__name__)
app.secret_key = os.getenv("SECRET_KEY", "fallback_local")

APP_USER = os.getenv("APP_USERNAME")
APP_PASS = os.getenv("APP_PASSWORD")

if not APP_USER or not APP_PASS:
    print("⚠️ APP_USERNAME / APP_PASSWORD no configurados en Render.")


def login_required(f):
    @wraps(f)
    def wrapped(*args, **kwargs):
        if session.get("user") != APP_USER:
            return redirect(url_for("login"))
        return f(*args, **kwargs)

    return wrapped


# ============================================================
# 6. SELECTOR — MISMO QUE TIENES
# ============================================================

# (Tu SELECTOR_TEMPLATE se mantiene igual…)
# No lo dupliqué aquí por espacio.


# ============================================================
# 7. API /api/points — AHORA CON CAPA AGENTES
# ============================================================
@app.route("/api/points")
@login_required
def api_points():

    tipo_mapa = request.args.get("tipo", "").lower()
    dpto = request.args.get("departamento", "").upper().strip()
    prov = request.args.get("provincia", "").upper().strip()
    dist = request.args.get("distrito", "").upper().strip()
    divi = request.args.get("division", "").upper().strip()

    # -------------------- CAPA ISLAS --------------------
    if tipo_mapa == "islas":
        dff = df_islas.copy()

        dff[COLI_DEPT] = dff[COLI_DEPT].astype(str).str.upper().str.strip()
        dff[COLI_PROV] = dff[COLI_PROV].astype(str).str.upper().str.strip()
        dff[COLI_DIST] = dff[COLI_DIST].astype(str).str.upper().str.strip()
        dff[COLI_DIV]  = dff[COLI_DIV].astype(str).str.upper().str.strip()

        if dpto:
            dff = dff[dff[COLI_DEPT] == dpto]
        if prov:
            dff = dff[dff[COLI_PROV] == prov]
        if dist:
            dff = dff[dff[COLI_DIST] == dist]
        if divi:
            dff = dff[dff[COLI_DIV] == divi]

        dff_layer = dff

        puntos = []
        for _, r in dff_layer.iterrows():
            puntos.append({
                "lat": float(r[COLI_LAT]),
                "lon": float(r[COLI_LON]),
                "atm": str(r[COLI_ATM]),
                "nombre": str(r.get(COLI_NAME, "")),
                "promedio": float(r[PROMI_COL]),
                "division": str(r.get(COLI_DIV, "")),
                "tipo": str(r.get(COLI_TIPO, "")),
                "ubicacion": str(r.get(COLI_UBIC, "")),
                "departamento": str(r.get(COLI_DEPT, "")),
                "provincia": str(r.get(COLI_PROV, "")),
                "distrito": str(r.get(COLI_DIST, "")),
                "direccion": get_address(r[COLI_LAT], r[COLI_LON]),
            })

        return jsonify({
            "puntos": puntos,
            "total_atms": len(puntos),
            "total_oficinas": 0,
            "total_islas": len(puntos),
            "total_disp": 0,
            "total_mon": 0,
            "total_rec": 0,
            "promedio_total": float(dff_layer[PROMI_COL].mean()) if len(dff_layer)>0 else 0
        })

    # -------------------- CAPA AGENTES --------------------
    if tipo_mapa == "agentes":
        dff = df_agentes.copy()

        dff[COLA_DEPT] = dff[COLA_DEPT].astype(str).str.upper().str.strip()
        dff[COLA_PROV] = dff[COLA_PROV].astype(str).str.upper().str.strip()
        dff[COLA_DIST] = dff[COLA_DIST].astype(str).str.upper().str.strip()

        if dpto:
            dff = dff[dff[COLA_DEPT] == dpto]
        if prov:
            dff = dff[dff[COLA_PROV] == prov]
        if dist:
            dff = dff[dff[COLA_DIST] == dist]

        puntos = []
        for _, r in dff.iterrows():
            puntos.append({
                "lat": float(r[COLA_LAT]),
                "lon": float(r[COLA_LON]),
                "atm": str(r.get(COLA_ID, "")),
                "nombre": str(r.get(COLA_COM, "")),
                "promedio": float(r[PROMA_COL]),
                "division": "",
                "tipo": "AGENTE",
                "ubicacion": "AGENTE",
                "departamento": str(r.get(COLA_DEPT, "")),
                "provincia": str(r.get(COLA_PROV, "")),
                "distrito": str(r.get(COLA_DIST, "")),
                "direccion": str(r.get(COLA_DIR, "")),
            })

        return jsonify({
            "puntos": puntos,
            "total_atms": len(puntos),
            "total_oficinas": 0,
            "total_islas": 0,
            "total_disp": 0,
            "total_mon": 0,
            "total_rec": 0,
            "promedio_total": float(dff[PROMA_COL].mean()) if len(dff)>0 else 0
        })

    return jsonify({"puntos": []})


    # ============================================================
# 8. TEMPLATE MAPA — PARTE 2
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

      <div style="margin-top:6px; font-weight:600;" id="resTituloBloque">ATMs totales</div>
      <div class="muted" style="margin-top:2px;">Total: <span id="resTotal">0</span></div>
      <div class="muted">ATMs en oficinas: <span id="resOfi">0</span></div>
      <div class="muted">ATMs en islas: <span id="resIsla">0</span></div>

      <div class="muted" style="margin-top:6px;">Dispensador: <span id="resDisp">0</span></div>
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
const resPromedio       = document.getElementById("resPromedio");
const resTituloBloque   = document.getElementById("resTituloBloque");
const resTotal          = document.getElementById("resTotal");
const resOfi            = document.getElementById("resOfi");
const resIsla           = document.getElementById("resIsla");
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
  resTituloBloque.textContent    = "ATMs totales (capa oficinas)";
} else if(TIPO_MAPA === "islas"){
  panelResumenTitulo.textContent = "Resumen — Islas (Oficinas + Islas)";
  resTituloBloque.textContent    = "ATMs totales (unificado)";
} else if(TIPO_MAPA === "agentes"){
  panelResumenTitulo.textContent = "Resumen — Agentes";
  resTituloBloque.textContent    = "ATMs totales (agentes)";
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
  updateDivisiones();
}

function updateDistritos(){
  let p = selProv.value;
  selDist.innerHTML = '<option value="">-- Todos --</option>';
  if(p && DIST_BY_PROV[p]){
    DIST_BY_PROV[p].forEach(d => {
      selDist.innerHTML += `<option value="${d}">${d}</option>`;
    });
  }
  updateDivisiones();
}

function updateDivisiones(){
  let d  = selDep.value;
  let p  = selProv.value;
  let di = selDist.value;

  selDiv.innerHTML = '<option value="">-- Todas --</option>';

  if(di && DIV_BY_DIST[di]){
    DIV_BY_DIST[di].forEach(v => selDiv.innerHTML += `<option value="${v}">${v}</option>`);
    return;
  }
  if(p && DIV_BY_PROV[p]){
    DIV_BY_PROV[p].forEach(v => selDiv.innerHTML += `<option value="${v}">${v}</option>`);
    return;
  }
  if(d && DIV_BY_DEPT[d]){
    DIV_BY_DEPT[d].forEach(v => selDiv.innerHTML += `<option value="${v}">${v}</option>`);
    return;
  }

  {{ divisiones|tojson }}.forEach(v => selDiv.innerHTML += `<option value="${v}">${v}</option>`);
}

// eventos combos
selDep.onchange  = ()=>{ updateProvincias(); fetchPoints(); };
selProv.onchange = ()=>{ updateDistritos(); fetchPoints(); };
selDist.onchange = ()=>{ updateDivisiones(); fetchPoints(); };
selDiv.onchange  = ()=> fetchPoints();

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

btnVolver.addEventListener("click", () => {
  panelATM.classList.add("hidden");
  panelATM.classList.remove("glow");
  panelResumen.classList.remove("hidden");
});

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

  const pts = data.puntos || [];

  infoBox.textContent = data.total_atms ?? pts.length;
  markers.clearLayers();
  heat.setLatLngs([]);

  let heatPts = [];
  let bounds  = [];

  pts.forEach(pt => {
    const icon = getIcon(pt);
    const popup = `
      
      <div class="popup-row"><b>ATM:</b> ${pt.atm}</div>
      <div class="popup-row"><b>Dirección:</b> ${pt.direccion}</div>
      <div class="popup-row"><b>División:</b> ${pt.division}</div>
      <div class="popup-row"><b>Tipo:</b> ${pt.tipo}</div>
      <div class="popup-row"><b>Ubicación:</b> ${pt.ubicacion}</div>
      <div class="popup-row"><b>Depto/Prov/Dist:</b> ${pt.departamento} / ${pt.provincia} / ${pt.distrito}</div>
      <div class="popup-row"><b>Promedio:</b> ${pt.promedio}</div>
    `;

    const m = L.marker([pt.lat, pt.lon], {icon});
    
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

  // Actualizar resumen con datos del backend
  const prom = data.promedio_total || 0;
  resPromedio.textContent = Math.round(prom).toString();

  resTotal.textContent = (data.total_atms || 0).toString();
  resOfi.textContent   = (data.total_oficinas || 0).toString();
  resIsla.textContent  = (data.total_islas || 0).toString();

  resDisp.textContent  = (data.total_disp || 0).toString();
  resMon.textContent   = (data.total_mon  || 0).toString();
  resRec.textContent   = (data.total_rec  || 0).toString();
}

// Inicial
updateProvincias();
fetchPoints();
</script>

</body>
</html>
"""