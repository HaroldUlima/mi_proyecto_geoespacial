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
# 4. FLASK + LOGIN (BBVA)
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

# ============================================================
# 9. EJECUCIÓN DEL SERVIDOR (REQUIRED FOR RENDER)
# ============================================================

if __name__ == '__main__':
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port)