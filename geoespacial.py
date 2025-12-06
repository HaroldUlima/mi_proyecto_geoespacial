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
# 2. CARGA DEL EXCEL PRINCIPAL
# ============================================================
BASE_DIR = os.path.dirname(__file__)
excel_main = os.path.join(BASE_DIR, "data", "Mapa Geoespacial ATM (1) (1).xlsx")

if not os.path.exists(excel_main):
    raise FileNotFoundError("No encontré archivo Excel de ATMs.")

raw = pd.read_excel(excel_main)

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
    raw["PROM_SUM_FAKE"] = 0.0
    PROM_COL = "PROM_SUM_FAKE"

df = raw.copy()

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

# ============================================================
# 3. LISTAS PARA DROPDOWNS
# ============================================================
DEPARTAMENTOS = sorted(df[COL_DEPT].dropna().astype(str).unique().tolist())
PROVINCIAS_BY_DEPT = df.groupby(COL_DEPT)[COL_PROV].apply(lambda s: sorted(s.dropna().astype(str).unique())).to_dict()
DIST_BY_PROV = df.groupby(COL_PROV)[COL_DIST].apply(lambda s: sorted(s.dropna().astype(str).unique())).to_dict()
DIVISIONES = sorted(df[COL_DIV].dropna().astype(str).unique())

# ============================================================
# 4. LOGIN
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


LOGIN_TEMPLATE = """... (como ya lo tienes, NO SE MODIFICA) ..."""


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
# 5. SELECTOR DE CAPAS
# ============================================================
SELECTOR_TEMPLATE = """... (igual, no se modifica) ..."""


@app.route("/selector")
@login_required
def selector():
    return render_template_string(SELECTOR_TEMPLATE)


# ============================================================
# 6. MAPA
# ============================================================
@app.route("/mapa/<tipo>")
@login_required
def mapa_tipo(tipo):
    initial_center = df[[COL_LAT, COL_LON]].mean().tolist()
    return render_template_string(
        TEMPLATE_MAPA,
        tipo_mapa=tipo,
        departamentos=DEPARTAMENTOS,
        provincias_by_dept=PROVINCIAS_BY_DEPT,
        dist_by_prov=DIST_BY_PROV,
        divisiones=DIVISIONES,
        initial_center=initial_center,
        initial_zoom=6,
    )

# ============================================================
# 7. API /api/points — SUMA TOTAL, SIN POPUP
# ============================================================
@app.route("/api/points")
@login_required
def api_points():
    tipo = request.args.get("tipo", "")

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

    if dpto:
        dff = dff[dff[COL_DEPT] == dpto]
    if prov:
        dff = dff[dff[COL_PROV] == prov]
    if dist:
        dff = dff[dff[COL_DIST] == dist]
    if divi:
        dff = dff[dff[COL_DIV] == divi]

    # Solo islas tiene datos (como pediste)
    if tipo == "islas":
        dff_layer = dff
    else:
        dff_layer = dff.iloc[0:0]

    total_atms = len(dff_layer)

    # CAMBIO SOLICITADO: SUMA TOTAL (NO PROMEDIO)
    suma_total = float(dff_layer[PROM_COL].sum())

    total_ofi = int(dff_layer[COL_UBIC].str.contains("OFICINA", na=False).sum())
    total_isla = int(dff_layer[COL_UBIC].str.contains("ISLA", na=False).sum())

    total_disp = int(dff_layer[COL_TIPO].str.contains("DISPENSADOR", na=False).sum())
    total_mon = int(dff_layer[COL_TIPO].str.contains("MONEDERO", na=False).sum())
    total_rec = int(dff_layer[COL_TIPO].str.contains("RECICLADOR", na=False).sum())

    puntos = []
    for _, r in dff_layer.iterrows():
        puntos.append(
            {
                "lat": float(r[COL_LAT]),
                "lon": float(r[COL_LON]),
                "atm": str(r[COL_ATM]),
                "nombre": str(r.get(COL_NAME, "")),
                "promedio": float(r.get(PROM_COL, 0)),
                "division": str(r.get(COL_DIV, "")),
                "tipo": str(r.get(COL_TIPO, "")),
                "ubicacion": str(r.get(COL_UBIC, "")),
                "departamento": str(r.get(COL_DEPT, "")),
                "provincia": str(r.get(COL_PROV, "")),
                "distrito": str(r.get(COL_DIST, "")),
                "direccion": get_address(r[COL_LAT], r[COL_LON]),
            }
        )

    return jsonify(
        {
            "puntos": puntos,
            "total_atms": total_atms,
            "total_oficinas": total_ofi,
            "total_islas": total_isla,
            "total_disp": total_disp,
            "total_mon": total_mon,
            "total_rec": total_rec,
            "promedio_total": suma_total,   # ← SUMA TOTAL
        }
    )

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
.logout{
  position:absolute;
  right:20px;
  background:#1464A5;
  padding:8px 16px;
  color:white;
  border-radius:8px;
  text-decoration:none;
}

.topbar{
  padding:16px 20px;
}
.controls{
  background:white;
  padding:12px;
  border-radius:12px;
  display:flex;
  gap:12px;
  align-items:center;
  flex-wrap:wrap;
  box-shadow:0 4px 16px rgba(0,0,0,0.1);
}
select{
  padding:6px 10px;
  border:1px solid #d0d7e3;
  border-radius:8px;
}

.main{
  display:flex;
  gap:16px;
  padding:0 20px 20px;
}

#map{
  flex:1;
  height:74vh;
  border-radius:12px;
  box-shadow:0 8px 24px rgba(0,0,0,0.18);
}

.side{
  width:330px;
}

.side-card{
  background:white;
  padding:16px;
  border-radius:12px;
  box-shadow:0 4px 16px rgba(0,0,0,0.12);
  margin-bottom:12px;
}

.muted{
  color:var(--muted);
  font-size:14px;
}

#panelATM{
  white-space:pre-line;
  font-family:Consolas;
  border-left:4px solid var(--bbva-blue);
}

.btn-small{
  background:var(--bbva-blue);
  border:none;
  color:white;
  padding:6px 12px;
  border-radius:6px;
  margin-top:10px;
  cursor:pointer;
}

.hidden{display:none;}
</style>
</head>

<body>

<header>
  <h1>MAPA BBVA — {{ tipo_mapa|upper }}</h1>
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
      <select id="selProvincia"><option value="">-- Todas --</option></select>
    </label>

    <label>Distrito:
      <select id="selDistrito"><option value="">-- Todos --</option></select>
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

    <div class="muted">Mostrando <span id="infoCount">--</span> ATMs</div>
  </div>
</div>

<div class="main">

  <div id="map"></div>

  <div class="side">

    <!-- PANEL RESUMEN -->
    <div id="panelResumen" class="side-card">
      <div class="muted" style="font-weight:700;">Resumen — {{ tipo_mapa|upper }}</div>

      <!-- SOLO ESTA LINEA SE MANTIENE -->
      <div class="muted" style="margin-top:6px;">
        Promedio total: <span id="resPromedio">0</span>
      </div>

      <div class="muted" style="margin-top:6px;">Total: <span id="resTotal">0</span></div>
      <div class="muted">ATMs en oficinas: <span id="resOfi">0</span></div>
      <div class="muted">ATMs en islas: <span id="resIsla">0</span></div>

      <div class="muted" style="margin-top:6px;">Dispensador: <span id="resDisp">0</span></div>
      <div class="muted">Monedero: <span id="resMon">0</span></div>
      <div class="muted">Reciclador: <span id="resRec">0</span></div>

    </div>

    <!-- PANEL ATM -->
    <div id="panelATM" class="side-card hidden">
      <div style="font-weight:700; color:var(--bbva-blue); margin-bottom:8px;">
        Panel del ATM seleccionado
      </div>

      <div id="atmDetalle" style="font-size:13px;"></div>

      <button id="btnVolver" class="btn-small">VOLVER</button>
    </div>

  </div>
</div>

<script src="https://unpkg.com/leaflet@1.9.4/dist/leaflet.js"></script>
<script src="https://unpkg.com/leaflet.markercluster@1.5.3/dist/MarkerCluster.js"></script>
<script src="https://unpkg.com/leaflet.heat/dist/leaflet-heat.js"></script>

<script>
const PROV_BY_DEPT = {{ provincias_by_dept|tojson }};
const DIST_BY_PROV = {{ dist_by_prov|tojson }};
const TIPO_MAPA = "{{ tipo_mapa }}";

const INITIAL_CENTER = [{{ initial_center[0] }}, {{ initial_center[1] }}];
const INITIAL_ZOOM = {{ initial_zoom }};

const map = L.map('map').setView(INITIAL_CENTER, INITIAL_ZOOM);

L.tileLayer('https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png',{maxZoom:19}).addTo(map);

const markers = L.markerClusterGroup();
const heat = L.heatLayer([], {radius:28, blur:22});

markers.addTo(map);
heat.addTo(map);

// ---------------- ICONOS ----------------
function getIcon(pt){
  const ub = (pt.ubicacion || "").toUpperCase();

  if(ub.includes("OFICINA"))
    return L.divIcon({html:"<div>🏦</div>", className:"", iconSize:[32,32]});

  if(ub.includes("ISLA"))
    return L.divIcon({html:"<div style='color:deepskyblue;'>🌐</div>", className:"", iconSize:[32,32]});

  return L.divIcon({
    html:`<div style='background:${pt.promedio>=4?"red":"green"};width:14px;height:14px;border-radius:50%;'></div>`,
    className:"",
    iconSize:[14,14]
  });
}

// ---------------- PANEL ATM ----------------
function showATMPanel(pt){
  const txt = `
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

  document.getElementById("atmDetalle").textContent = txt;

  document.getElementById("panelResumen").classList.add("hidden");
  document.getElementById("panelATM").classList.remove("hidden");
}

document.getElementById("btnVolver").onclick = () => {
  document.getElementById("panelATM").classList.add("hidden");
  document.getElementById("panelResumen").classList.remove("hidden");
};

// ---------------- FILTROS ----------------
const selDep  = document.getElementById("selDepartamento");
const selProv = document.getElementById("selProvincia");
const selDist = document.getElementById("selDistrito");
const selDiv  = document.getElementById("selDivision");
const chkHeat = document.getElementById("chkHeat");

function updateProvincias(){
  const d = selDep.value;
  selProv.innerHTML = '<option value="">-- Todas --</option>';

  if(d && PROV_BY_DEPT[d]){
    PROV_BY_DEPT[d].forEach(p => selProv.innerHTML += `<option value="${p}">${p}</option>`);
  }
  updateDistritos();
}

function updateDistritos(){
  selDist.innerHTML='<option value="">-- Todos --</option>';
  const p = selProv.value;
  if(p && DIST_BY_PROV[p])
    DIST_BY_PROV[p].forEach(d => selDist.innerHTML += `<option value="${d}">${d}</option>`);
}

selDep.onchange  = ()=>{updateProvincias(); fetchPoints();};
selProv.onchange = ()=>{updateDistritos(); fetchPoints();};
selDist.onchange = fetchPoints;
selDiv.onchange  = fetchPoints;

// ---------------- FETCH ----------------
async function fetchPoints(){
  const q = `tipo=${TIPO_MAPA}&departamento=${selDep.value}&provincia=${selProv.value}&distrito=${selDist.value}&division=${selDiv.value}`;

  const res = await fetch(`/api/points?${q}`);
  const data = await res.json();

  // limpiar
  markers.clearLayers();
  heat.setLatLngs([]);

  const pts = data.puntos || [];
  const bounds = [];

  pts.forEach(pt=>{
    const icon = getIcon(pt);

    // SIN POPUP
    const m = L.marker([pt.lat, pt.lon], {icon});
    m.on("click", ()=>showATMPanel(pt));
    markers.addLayer(m);

    heat.addLatLng([pt.lat, pt.lon, Math.max(1, pt.promedio)]);
    bounds.push([pt.lat, pt.lon]);
  });

  if(bounds.length>1) map.fitBounds(bounds,{padding:[20,20]});
  else if(bounds.length==1) map.setView(bounds[0],16);
  else map.setView(INITIAL_CENTER, INITIAL_ZOOM);

  if(chkHeat.checked) heat.addTo(map);
  else map.removeLayer(heat);

  // PANEL RESUMEN
  document.getElementById("resPromedio").textContent = data.promedio_total || 0;
  document.getElementById("resTotal").textContent = data.total_atms || 0;
  document.getElementById("resOfi").textContent = data.total_oficinas || 0;
  document.getElementById("resIsla").textContent = data.total_islas || 0;
  document.getElementById("resDisp").textContent = data.total_disp || 0;
  document.getElementById("resMon").textContent  = data.total_mon || 0;
  document.getElementById("resRec").textContent  = data.total_rec || 0;

  document.getElementById("infoCount").textContent = data.total_atms;
}

updateProvincias();
fetchPoints();
</script>

</body>
</html>
"""