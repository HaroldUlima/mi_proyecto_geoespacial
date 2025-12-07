# ============================================================
#   BACKEND COMPLETO + LOGIN + SELECTOR
#   CAPAS: ISLAS (ATMs) + AGENTES + OFICINAS
#   — NUEVA LÓGICA DINÁMICA DE FILTROS —
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
# 2. FUNCIÓN PARA NORMALIZAR NOMBRES DE COLUMNAS
# ============================================================
def normalize_col(s):
    s = str(s)
    s = unicodedata.normalize("NFKD", s)
    s = s.encode("ascii", "ignore").decode("utf-8")
    s = s.upper().strip()
    s = re.sub(r"[^A-Z0-9 ]+", " ", s)
    return re.sub(r"\s+", " ", s).strip()


# ============================================================
# 3. CARGA DE ARCHIVO PRINCIPAL (ISLAS / ATMs)
# ============================================================
BASE_DIR = os.path.dirname(__file__)
excel_main = os.path.join(BASE_DIR, "data", "Mapa Geoespacial ATM (1) (1).xlsx")

if not os.path.exists(excel_main):
    raise FileNotFoundError("No encontré archivo Excel de ATMs.")

raw = pd.read_excel(excel_main)

norm_map = {normalize_col(c): c for c in raw.columns}

def find_col(keys):
    for norm, orig in norm_map.items():
        for k in keys:
            if k in norm:
                return orig
    return None

# columnas
COL_ATM  = find_col(["COD_ATM", "ATM"]) or "ATM"
COL_NAME = find_col(["NOMBRE", "CAJERO"])
COL_DEPT = find_col(["DEPARTAMENTO"]) or "DEPARTAMENTO"
COL_PROV = find_col(["PROVINCIA"]) or "PROVINCIA"
COL_DIST = find_col(["DISTRITO"]) or "DISTRITO"
COL_LAT  = find_col(["LATITUD", "LAT"]) or "LATITUD"
COL_LON  = find_col(["LONGITUD","LON"]) or "LONGITUD"
COL_DIV  = find_col(["DIVISION","DIVISIÓN"]) or "DIVISION"
COL_TIPO = find_col(["TIPO"]) or "TIPO"
COL_UBIC = find_col(["UBICACION","UBICACIÓN"]) or "UBICACION_INTERNA"
PROM_COL = find_col(["PROMEDIO","PROM"])

# si no existe promedio se crea
if PROM_COL is None:
    raw["PROM_FAKE"] = 0.0
    PROM_COL = "PROM_FAKE"

# limpiar coordenadas
for col in [COL_LAT, COL_LON]:
    raw[col] = (
        raw[col].astype(str)
        .str.replace(",", ".", regex=False)
        .str.replace(r"[^\d\.\-]", "", regex=True)
        .replace("", np.nan)
        .astype(float)
    )

df = raw.dropna(subset=[COL_LAT, COL_LON]).reset_index(drop=True)
df[PROM_COL] = pd.to_numeric(df[PROM_COL], errors="coerce").fillna(0.0)


# ============================================================
# 4. CARGA DE AGENTES
# ============================================================
excel_agentes = os.path.join(BASE_DIR, "data", "AGENTES.xlsx")
if not os.path.exists(excel_agentes):
    raise FileNotFoundError("No encontré Excel AGENTES.xlsx")

raw_ag = pd.read_excel(excel_agentes)
norm_map_ag = {normalize_col(c): c for c in raw_ag.columns}

def find_col_ag(keys):
    for norm, orig in norm_map_ag.items():
        for k in keys:
            if k in norm:
                return orig
    return None

COLA_ID   = find_col_ag(["TERMINAL","ID"]) or "TERMINAL"
COLA_COM  = find_col_ag(["COMERCIO"]) or "COMERCIO"
COLA_DEPT = find_col_ag(["DEPARTAMENTO"]) or "DEPARTAMENTO"
COLA_PROV = find_col_ag(["PROVINCIA"]) or "PROVINCIA"
COLA_DIST = find_col_ag(["DISTRITO"]) or "DISTRITO"
COLA_LAT  = find_col_ag(["LATITUD","LAT"]) or "LATITUD"
COLA_LON  = find_col_ag(["LONGITUD","LON"]) or "LONGITUD"
COLA_DIV  = find_col_ag(["DIVISION","DIVISIÓN"]) or "DIVISION"
COLA_DIR  = find_col_ag(["DIRECCION","DIRECCIÓN"]) or "DIRECCION"
COLA_CAPA = find_col_ag(["CAPA"]) or "CAPA"
PROMA_COL = find_col_ag(["PROMEDIO","PROM"])

if PROMA_COL is None:
    raw_ag["PROM_FAKE"] = 0.0
    PROMA_COL = "PROM_FAKE"

for col in [COLA_LAT, COLA_LON]:
    raw_ag[col] = (
        raw_ag[col].astype(str)
        .str.replace(",", ".", regex=False)
        .str.replace(r"[^\d\.\-]", "", regex=True)
        .replace("", np.nan)
        .astype(float)
    )

df_agentes = raw_ag.dropna(subset=[COLA_LAT, COLA_LON]).reset_index(drop=True)
df_agentes[PROMA_COL] = pd.to_numeric(df_agentes[PROMA_COL], errors="coerce").fillna(0.0)


# ============================================================
# 5. CARGA DE OFICINAS
# ============================================================
excel_ofi = os.path.join(BASE_DIR, "data", "OFICINAS.xlsx")
if not os.path.exists(excel_ofi):
    raise FileNotFoundError("No encontré Excel OFICINAS.xlsx")

raw_of = pd.read_excel(excel_ofi)
norm_map_of = {normalize_col(c): c for c in raw_of.columns}

def find_col_of(keys):
    for norm, orig in norm_map_of.items():
        for k in keys:
            if k in norm:
                return orig
    return None

COLF_ID   = find_col_of(["COD OFIC"]) or "COD OFIC."
COLF_NAME = find_col_of(["OFICINA"]) or "OFICINA"
COLF_DIV  = find_col_of(["DIVISION","DIVISIÓN"]) or "DIVISION"
COLF_DEPT = find_col_of(["DEPARTAMENTO"]) or "DEPARTAMENTO"
COLF_PROV = find_col_of(["PROVINCIA"]) or "PROVINCIA"
COLF_DIST = find_col_of(["DISTRITO"]) or "DISTRITO"
COLF_LAT  = find_col_of(["LATITUD","LAT"]) or "LATITUD"
COLF_LON  = find_col_of(["LONGITUD","LON"]) or "LONGITUD"
COLF_TRX  = find_col_of(["TRX","TRXS"]) or "TRX"

for col in [COLF_LAT, COLF_LON]:
    raw_of[col] = (
        raw_of[col].astype(str)
        .str.replace(",", ".", regex=False)
        .str.replace(r"[^\d\.\-]", "", regex=True)
        .replace("", np.nan)
        .astype(float)
    )

df_oficinas = raw_of.dropna(subset=[COLF_LAT, COLF_LON]).reset_index(drop=True)
df_oficinas[COLF_TRX] = pd.to_numeric(df_oficinas[COLF_TRX], errors="coerce").fillna(0.0)


# ============================================================
# 6. APIs NUEVAS DINÁMICAS DE FILTRO
# ============================================================

app = Flask(__name__)
app.secret_key = "bbva_demo"

@app.route("/api/filter-data")
def filter_data():
    tipo = request.args.get("tipo", "")
    dpto = request.args.get("departamento", "").upper()
    prov = request.args.get("provincia", "").upper()

    if tipo == "islas":
        data = df
        cDEPT, cPROV, cDIST, cDIV = COL_DEPT, COL_PROV, COL_DIST, COL_DIV

    elif tipo == "agentes":
        data = df_agentes
        cDEPT, cPROV, cDIST, cDIV = COLA_DEPT, COLA_PROV, COLA_DIST, COLA_DIV

    elif tipo == "oficinas":
        data = df_oficinas
        cDEPT, cPROV, cDIST, cDIV = COLF_DEPT, COLF_PROV, COLF_DIST, COLF_DIV

    else:
        return jsonify({"provincias":[],"distritos":[],"divisiones":[]})

    data = data.copy()
    data[cDEPT] = data[cDEPT].astype(str).str.upper()
    data[cPROV] = data[cPROV].astype(str).str.upper()
    data[cDIST] = data[cDIST].astype(str).str.upper()
    data[cDIV]  = data[cDIV].astype(str).str.upper()

    if dpto:
        data = data[data[cDEPT] == dpto]

    provincias = sorted(data[cPROV].dropna().unique().tolist())

    if prov:
        data = data[data[cPROV] == prov]

    distritos = sorted(data[cDIST].dropna().unique().tolist())
    divisiones = sorted(data[cDIV].dropna().unique().tolist())

    return jsonify({
        "provincias": provincias,
        "distritos": distritos,
        "divisiones": divisiones
    })



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
  margin:0; padding:0; height:100%;
  font-family:Inter,Arial,Helvetica,sans-serif;
  background:#eef4fb;
}
header{
  background:#003366;
  color:white; height:70px;
  display:flex; align-items:center;
  justify-content:center;
  box-shadow:0 6px 18px rgba(0,0,0,0.25);
}
header h1{ margin:0; font-size:1.9rem; }
.logout{
  position:absolute; right:20px;
  background:#1464A5; color:white;
  padding:8px 16px; border-radius:8px;
  text-decoration:none; font-weight:600;
}
.topbar{ padding:16px 20px 8px; }
.controls{
  background:white; padding:12px;
  border-radius:12px;
  box-shadow:0 4px 16px rgba(0,0,0,0.12);
  display:flex; gap:12px; align-items:center; flex-wrap:wrap;
}
select{ padding:6px 10px; border-radius:8px; border:1px solid #d0d7e3; }
.main{ display:flex; padding:0 20px 20px; gap:18px; }
#map{
  flex:1; height:74vh; border-radius:12px;
  box-shadow:0 8px 24px rgba(0,0,0,0.18);
}
.side{ width:330px; }
.side-card{
  background:white; border-radius:12px;
  padding:14px 16px;
  box-shadow:0 6px 22px rgba(0,0,0,0.12);
  margin-bottom:12px;
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
      </select>
    </label>

    <label><input type="checkbox" id="chkHeat" checked> Heatmap</label>

    <div style="flex:1"></div>
    <div style="font-size:13px; color:#6b7a8a;">
      Mostrando <span id="infoCount">--</span> puntos
    </div>
  </div>
</div>

<div class="main">
  <div id="map"></div>

  <div class="side">
    <div id="panelResumen" class="side-card">
      <h3>Resumen</h3>
      <div>Promedio total: <b id="resPromedio">0</b></div>
      <div id="extraInfo"></div>
    </div>

    <div id="panelATM" class="side-card hidden">
      <h3>Detalle</h3>
      <pre id="atmDetalle" style="font-size:12px;"></pre>
      <button id="btnVolver">VOLVER</button>
    </div>
  </div>
</div>

<script src="https://unpkg.com/leaflet@1.9.4/dist/leaflet.js"></script>
<script src="https://unpkg.com/leaflet.markercluster@1.5.3/dist/leaflet.markercluster.js"></script>
<script src="https://unpkg.com/leaflet.heat/dist/leaflet-heat.js"></script>

<script>
const TIPO_MAPA = "{{ tipo_mapa }}";
const INITIAL_CENTER = [{{ initial_center[0] }}, {{ initial_center[1] }}];
const INITIAL_ZOOM = {{ initial_zoom }};

// ===============================
// MAPA
// ===============================
const map = L.map("map").setView(INITIAL_CENTER, INITIAL_ZOOM);
L.tileLayer("https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png",{maxZoom:19}).addTo(map);

const markers = L.markerClusterGroup();
const heat = L.heatLayer([], {radius:28, blur:22});
map.addLayer(markers);
map.addLayer(heat);

// ===============================
// SELECTORES
// ===============================
const selDep  = document.getElementById("selDepartamento");
const selProv = document.getElementById("selProvincia");
const selDist = document.getElementById("selDistrito");
const selDiv  = document.getElementById("selDivision");
const chkHeat = document.getElementById("chkHeat");

// ===============================
// FUNCIONES NUEVAS DINÁMICAS
// ===============================

async function loadFilterData(){
  const d = selDep.value;
  const p = selProv.value;

  const res = await fetch(`/api/filter-data?tipo=${TIPO_MAPA}&departamento=${d}&provincia=${p}`);
  const data = await res.json();

  // provincias
  selProv.innerHTML = `<option value="">-- Todas --</option>`;
  data.provincias.forEach(x=>{
    selProv.innerHTML += `<option value="${x}">${x}</option>`;
  });

  // distritos
  selDist.innerHTML = `<option value="">-- Todos --</option>`;
  data.distritos.forEach(x=>{
    selDist.innerHTML += `<option value="${x}">${x}</option>`;
  });

  // divisiones
  selDiv.innerHTML = `<option value="">-- Todas --</option>`;
  data.divisiones.forEach(x=>{
    selDiv.innerHTML += `<option value="${x}">${x}</option>`;
  });
}


// ===============================
// FETCH MAP POINTS
// ===============================
async function loadPoints(){
  const d  = selDep.value;
  const p  = selProv.value;
  const di = selDist.value;
  const dv = selDiv.value;

  const url = `/api/points?tipo=${TIPO_MAPA}&departamento=${d}&provincia=${p}&distrito=${di}&division=${dv}`;
  const res = await fetch(url);
  const data = await res.json();

  const pts = data.puntos || [];
  document.getElementById("infoCount").textContent = pts.length;

  markers.clearLayers();
  heat.setLatLngs([]);

  let heatPts = [];

  pts.forEach(pt => {
    const m = L.marker([pt.lat, pt.lon]);
    m.on("click", ()=>showDetail(pt));
    markers.addLayer(m);

    heatPts.push([pt.lat, pt.lon, Math.max(1, pt.promedio || 1)]);
  });

  heat.setLatLngs(heatPts);

  // resumen
  document.getElementById("resPromedio").textContent =
    Math.round(data.promedio_total || 0);

  let extra = "";
  if(TIPO_MAPA === "islas"){
    extra = `
      ATMs: ${data.total_atms}<br>
      Oficinas: ${data.total_oficinas}<br>
      Islas: ${data.total_islas}<br>
      Dispensador: ${data.total_disp}<br>
      Monedero: ${data.total_mon}<br>
      Reciclador: ${data.total_rec}
    `;
  }
  if(TIPO_MAPA === "oficinas"){
    extra = `
      Total oficinas: ${data.total_oficinas}<br>
      Promedio TRX: ${Math.round(data.promedio_total)}
    `;
  }
  if(TIPO_MAPA === "agentes"){
    extra = `
      Total agentes: ${data.total_agentes}<br>
      A1: ${data.total_capa_A1}<br>
      A2: ${data.total_capa_A2}<br>
      A3: ${data.total_capa_A3}<br>
      B: ${data.total_capa_B}<br>
      C: ${data.total_capa_C}
    `;
  }

  document.getElementById("extraInfo").innerHTML = extra;
}


// ===============================
// PANEL DETALLE
// ===============================
function showDetail(pt){
  const pr = document.getElementById("panelResumen");
  const pa = document.getElementById("panelATM");

  pr.classList.add("hidden");
  pa.classList.remove("hidden");

  document.getElementById("atmDetalle").textContent = JSON.stringify(pt, null, 2);
}

document.getElementById("btnVolver").onclick = ()=>{
  document.getElementById("panelATM").classList.add("hidden");
  document.getElementById("panelResumen").classList.remove("hidden");
};


// ===============================
// EVENTOS
// ===============================
selDep.onchange  = async ()=>{ await loadFilterData(); loadPoints(); };
selProv.onchange = async ()=>{ await loadFilterData(); loadPoints(); };
selDist.onchange = async ()=> loadPoints();
selDiv.onchange  = async ()=> loadPoints();
chkHeat.onchange = ()=> chkHeat.checked ? heat.addTo(map) : map.removeLayer(heat);

// ===============================
// INICIO
// ===============================
loadFilterData();
loadPoints();
</script>

</body>
</html>
"""

