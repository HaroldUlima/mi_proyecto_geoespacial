# ============================================================
#   PARTE 1 / 2 — BACKEND COMPLETO + LOGIN + SELECTOR + API
# ============================================================

import os
import re
import unicodedata
import json
import pandas as pd
import numpy as np
from flask import (
    Flask, render_template_string, request,
    jsonify, redirect, url_for, session
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
    """Devuelve la dirección desde la cache usando lat/lon."""
    try:
        key = f"{float(lat):.6f},{float(lon):.6f}"
    except Exception:
        key = f"{lat},{lon}"
    return address_cache.get(key, "Dirección no encontrada")


# ============================================================
# 2. CARGAR EXCEL PRINCIPAL (OFICINAS + ISLAS)
# ============================================================
BASE_DIR = os.path.dirname(__file__)
excel_main = os.path.join(BASE_DIR, "data", "Mapa Geoespacial ATM (1) (1).xlsx")

if not os.path.exists(excel_main):
    raise FileNotFoundError(f"No encontré archivo Excel en: {excel_main}")

raw = pd.read_excel(excel_main)

# Normalizador de nombres de columnas
def normalize_col(s):
    s = str(s)
    s = unicodedata.normalize("NFKD", s)
    s = s.encode("ascii", "ignore").decode("utf-8")
    s = s.upper().strip()
    s = re.sub(r"[^A-Z0-9 ]+", " ", s)
    return re.sub(r"\s+", " ", s).strip()

norm_map = {normalize_col(c): c for c in raw.columns}

def find_col(keys):
    for n, o in norm_map.items():
        for k in keys:
            if k in n:
                return o
    return None

# Detectar columnas principales
COL_ATM  = find_col(["ATM"]) or "ATM"
COL_NAME = find_col(["NOMBRE", "CAJERO", "NOMBRECAJERO"]) or None
COL_DEPT = find_col(["DEPARTAMENTO"]) or "DEPARTAMENTO"
COL_PROV = find_col(["PROVINCIA"]) or "PROVINCIA"
COL_DIST = find_col(["DISTRITO"]) or "DISTRITO"
COL_LAT  = find_col(["LATITUD", "LAT"]) or "LAT"
COL_LON  = find_col(["LONGITUD", "LON", "LONG"]) or "LON"
COL_DIV  = find_col(["DIVISION", "DIVISIÓN"]) or "DIVISION"
COL_TIPO = find_col(["TIPO"]) or "TIPO"
COL_UBIC = find_col(["UBICACION", "UBICACIÓN", "UBICACION_INTERNA"]) or "UBICACION_INTERNA"
PROM_COL = find_col(["PROMEDIO", "PROM"]) or None

if PROM_COL is None:
    raw["PROM_FAKE"] = 0.0
    PROM_COL = "PROM_FAKE"

# Garantizar columnas (excepto coord)
for c in [COL_ATM, COL_DEPT, COL_PROV, COL_DIST, COL_DIV, COL_TIPO, COL_UBIC]:
    if c not in raw.columns:
        raw[c] = ""

df = raw.copy()

# Limpieza coordenadas
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


# ============================================================
# 3. LISTAS PARA FILTROS — JERARQUÍA COMPLETA
# ============================================================
DEPARTAMENTOS = sorted(df[COL_DEPT].dropna().astype(str).unique().tolist())

PROVINCIAS_BY_DEPT = df.groupby(COL_DEPT)[COL_PROV].apply(
    lambda s: sorted(s.dropna().astype(str).unique())
).to_dict()

DIST_BY_PROV = df.groupby(COL_PROV)[COL_DIST].apply(
    lambda s: sorted(s.dropna().astype(str).unique())
).to_dict()

# División jerárquica
DIV_BY_DEPT = df.groupby(COL_DEPT)[COL_DIV].apply(
    lambda s: sorted(s.dropna().astype(str).unique())
).to_dict()

DIV_BY_PROV = df.groupby(COL_PROV)[COL_DIV].apply(
    lambda s: sorted(s.dropna().astype(str).unique())
).to_dict()

DIV_BY_DIST = df.groupby(COL_DIST)[COL_DIV].apply(
    lambda s: sorted(s.dropna().astype(str).unique())
).to_dict()

DIVISIONES = sorted(df[COL_DIV].dropna().astype(str).unique())


# ============================================================
# 4. FLASK + LOGIN BBVA
# ============================================================
app = Flask(__name__)
app.secret_key = os.getenv("SECRET_KEY", "fallback_local")

APP_USER = os.getenv("APP_USERNAME")
APP_PASS = os.getenv("APP_PASSWORD")

# Evitar caché (por seguridad al hacer logout)
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
    background: url('{{ url_for('static', filename='bbva.png') }}')
                no-repeat center center fixed;
    background-size: cover;
    font-family: Arial, Helvetica, sans-serif;
}
.box{
    background: rgba(255,255,255,0.85);
    padding: 30px 35px;
    border-radius: 12px;
    box-shadow: 0 8px 30px rgba(0,0,0,0.3);
    width: 360px; text-align:center;
}
h2{ color:#1464A5; margin-top:0; margin-bottom:15px; }
input{
    width:100%; padding:10px; margin:8px 0;
    border:1px solid #ddd; border-radius:8px;
}
button{
    background:#1464A5; color:white; border:none;
    padding:10px; border-radius:8px; width:100%;
    cursor:pointer; font-weight:600;
}
.error{color:#c0392b;margin-bottom:8px;font-size:14px;}
.small{font-size:13px;color:#6b7a8a;margin-top:8px;}
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

@app.route("/login", methods=["GET","POST"])
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

@app.route("/")
def home():
    if session.get("user") == APP_USER:
        return redirect(url_for("selector"))
    return redirect(url_for("login"))


# ============================================================
# 5. SELECTOR DE CAPAS
# ============================================================
SELECTOR_TEMPLATE = """
<!DOCTYPE html>
<html>
<head>
<meta charset="utf-8">
<title>Selector de Capas</title>
<style>
body{
    font-family:Arial, Helvetica, sans-serif;
    background:#eef3f9;
    padding:40px;
}
h1{text-align:center;}
.grid{
    display:flex;
    gap:40px;
    justify-content:center;
    margin-top:40px;
}
.box{
    width:260px; height:260px;
    background:white; border-radius:18px;
    box-shadow:0 0 14px rgba(0,0,0,0.15);
    display:flex; justify-content:center; align-items:center;
    font-size:28px; cursor:pointer; transition:.2s;
}
.box:hover{ transform:scale(1.05); }
</style>
</head>
<body>

<h1>Seleccione la capa</h1>

<div class="grid">
  <div class="box" onclick="location.href='/mapa/oficinas'">🏦 Oficinas</div>
  <div class="box" onclick="location.href='/mapa/islas'">🌐 Islas</div>
  <div class="box" onclick="location.href='/mapa/agentes'">🧍 Agentes</div>
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

    return render_template_string(
        TEMPLATE_MAPA,          # se define en PARTE 2
        tipo_mapa=tipo,
        departamentos=DEPARTAMENTOS,
        provincias_by_dept=PROVINCIAS_BY_DEPT,
        dist_by_prov=DIST_BY_PROV,
        div_by_dept=DIV_BY_DEPT,
        div_by_prov=DIV_BY_PROV,
        div_by_dist=DIV_BY_DIST,
        divisiones=DIVISIONES,
        initial_center=df[[COL_LAT, COL_LON]].mean().tolist(),
        initial_zoom=6
    )


# ============================================================
# 7. API /api/points — Filtrado jerárquico + por capa
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
    dff[COL_DIV]  = dff[COL_DIV].astype(str).str.upper().str.strip()
    dff[COL_UBIC] = dff[COL_UBIC].astype(str).str.upper().str.strip()

    # Filtrar por capa (ubicación interna)
    if tipo_mapa == "oficinas":
        dff = dff[dff[COL_UBIC].str.contains("OFICINA", na=False)]
    elif tipo_mapa == "islas":
        dff = dff[dff[COL_UBIC].str.contains("ISLA", na=False)]
    elif tipo_mapa == "agentes":
        dff = dff[dff[COL_UBIC].str.contains("AGENTE", na=False)]  # hoy quedará vacío

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
        nombre = str(r.get(COL_NAME)) if COL_NAME else str(r.get(COL_ATM))

        lat_v = float(r[COL_LAT])
        lon_v = float(r[COL_LON])

        puntos.append({
            "lat": lat_v,
            "lon": lon_v,
            "atm": str(r[COL_ATM]),
            "nombre": nombre,
            "promedio": float(r[PROM_COL]),
            "division": str(r[COL_DIV]),
            "tipo": str(r[COL_TIPO]),
            "ubicacion": str(r[COL_UBIC]),
            "departamento": str(r[COL_DEPT]),
            "provincia": str(r[COL_PROV]),
            "distrito": str(r[COL_DIST]),
            "direccion": get_address(lat_v, lon_v)
        })

    return jsonify(puntos)


# ============================================================
#  PARTE 2 / 2 — TEMPLATE MAPA COMPLETO + PANEL DERECHO BBVA
# ============================================================

TEMPLATE_MAPA = """
<!doctype html>
<html>
<head>
<meta charset="utf-8">
<title>Mapa — {{ tipo_mapa.capitalize() }}</title>
<meta name="viewport" content="width=device-width, initial-scale=1.0">

<!-- Leaflet -->
<link rel="stylesheet" href="https://unpkg.com/leaflet@1.9.4/dist/leaflet.css"/>
<link rel="stylesheet" href="https://unpkg.com/leaflet.markercluster@1.5.3/dist/MarkerCluster.css"/>
<link rel="stylesheet" href="https://unpkg.com/leaflet.markercluster@1.5.3/dist/MarkerCluster.Default.css"/>

<style>
/* ----------- GENERAL ----------- */
:root { 
  --bbva-blue: #1464A5; 
  --bbva-dark: #072146; 
  --muted: #6b7a8a; 
  --card: #ffffff;
}
html,body{
  margin:0; padding:0;
  height:100%; 
  font-family: Inter, 'Segoe UI', Tahoma, Arial, sans-serif;
  background:#eef3f9;
  color:var(--bbva-dark);
}

/* ----------- HEADER ----------- */
header{
  background:#003366; 
  color:white;
  padding:14px 20px;
  display:flex;
  align-items:center;
  justify-content:center;
  position:relative;
}
.logout-btn{
  position:absolute; 
  right:20px;
  background:#1464A5;
  padding:8px 16px;
  border-radius:8px;
  text-decoration:none;
  color:white;
  font-weight:600;
}

/* ----------- CONTROLS ----------- */
.controls{
  background:white;
  padding:12px;
  margin:12px 20px;
  border-radius:12px;
  box-shadow:0 6px 14px rgba(0,0,0,0.15);
  display:flex;
  gap:12px;
  flex-wrap:wrap;
}
label{ font-size:14px; color:var(--muted); }
select{
  padding:8px 10px;
  border:1px solid #e0e6ef;
  border-radius:8px;
  font-size:14px;
  min-width:160px;
}
#map { 
  height:78vh; 
  flex:1;
  border-radius:12px;
  box-shadow:0 6px 20px rgba(0,0,0,0.12);
}

/* ----------- LAYOUT ----------- */
.main{
  display:flex;
  gap:16px;
  padding:0 20px 20px 20px;
}

/* ----------- PANEL DERECHO ----------- */
.side{
  width:330px;
}

/* Caja para capa */
.card{
  background:white;
  padding:14px;
  border-radius:12px;
  box-shadow:0 4px 12px rgba(0,0,0,0.1);
  margin-bottom:14px;
}

/* Caja para ATM seleccionado */
.card-atm{
  background:white;
  padding:20px;
  border-radius:14px;
  box-shadow:0 4px 20px rgba(0,0,0,0.18);
  margin-bottom:14px;
  font-size:15px;
}

.card-atm pre{
  white-space:pre-wrap;
  font-size:15px;
  line-height:1.35;
  color:#072146;
  font-weight:500;
}

.btnvolver{
  background:#1464A5;
  padding:8px 14px;
  display:inline-block;
  margin-top:10px;
  border-radius:6px;
  color:white;
  cursor:pointer;
  font-size:14px;
}

</style>

</head>
<body>

<!-- HEADER -->
<header>
  <h2>Mapa BBVA — {{ tipo_mapa.upper() }}</h2>
  <a class="logout-btn" href="/logout">Cerrar sesión</a>
</header>

<!-- CONTROLES -->
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

  <label><input type="checkbox" id="chkHeat" checked> Heatmap</label>

  <div style="flex:1"></div>

  <div style="font-weight:bold;">Mostrando <span id="infoCount">--</span> ATMs</div>
</div>

<!-- MAIN LAYOUT -->
<div class="main">

  <!-- MAPA -->
  <div id="map"></div>

  <!-- PANEL DERECHO -->
  <div class="side">

    <!-- PANEL DE CAPA (por defecto visible) -->
    <div id="panelCapa" class="card">
      <h3 style="margin-top:0;">Resumen — {{ tipo_mapa|capitalize }}</h3>
      <div>Promedio total: <b><span id="promTotal">0</span></b></div>
      <hr>

      <div><b>ATMs en {{ tipo_mapa }}</b></div>
      <div>Total: <b><span id="totalAtms">0</span></b></div>
      <div>Dispensador: <b><span id="disp">0</span></b></div>
      <div>Monedero: <b><span id="mon">0</span></b></div>
      <div>Reciclador: <b><span id="rec">0</span></b></div>

      <hr>
      <h4>Leyenda</h4>
      <div>🔴 ATM ≥ 4</div>
      <div>🟢 ATM ≤ 3</div>
      <div>🏦 Oficina</div>
      <div>🌐 Isla</div>
    </div>

    <!-- PANEL ATM SELECCIONADO (oculto por defecto) -->
    <div id="panelATM" class="card-atm" style="display:none;">
      <pre id="atmDetails"></pre>
      <div class="btnvolver" onclick="volverPanel()">VOLVER</div>
    </div>

  </div>
</div>

<!-- JS Leaflet -->
<script src="https://unpkg.com/leaflet@1.9.4/dist/leaflet.js"></script>
<script src="https://unpkg.com/leaflet.markercluster@1.5.3/dist/leaflet.markercluster.js"></script>
<script src="https://unpkg.com/leaflet.heat/dist/leaflet-heat.js"></script>

<script>
// =====================================================
// VARIABLES
// =====================================================
const PROV_BY_DEPT = {{ provincias_by_dept|tojson }};
const DIST_BY_PROV = {{ dist_by_prov|tojson }};

const TIPO = "{{ tipo_mapa }}";

let markersLayer = L.markerClusterGroup({ chunkedLoading:true });
let heatLayer = L.heatLayer([], {radius:25, blur:20});

const map = L.map('map').setView(
  [{{ initial_center[0] }}, {{ initial_center[1] }}],
  {{ initial_zoom }}
);

L.tileLayer('https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png',{
  maxZoom:19
}).addTo(map);

markersLayer.addTo(map);
heatLayer.addTo(map);


// =====================================================
// POBLAR PROVINCIAS
// =====================================================
selDepartamento.onchange = ()=>{
  const dept = selDepartamento.value;
  selProvincia.innerHTML = '<option value="">-- Todas --</option>';
  selDistrito.innerHTML = '<option value="">-- Todos --</option>';

  if(PROV_BY_DEPT[dept]){
    PROV_BY_DEPT[dept].forEach(p=>{
      selProvincia.innerHTML += `<option value="${p}">${p}</option>`;
    });
  }
  fetchAndRender();
};

selProvincia.onchange = ()=>{
  const prov = selProvincia.value;
  selDistrito.innerHTML = '<option value="">-- Todos --</option>';

  if(DIST_BY_PROV[prov]){
    DIST_BY_PROV[prov].forEach(d=>{
      selDistrito.innerHTML += `<option value="${d}">${d}</option>`;
    });
  }
  fetchAndRender();
};

selDistrito.onchange = fetchAndRender;
selDivision.onchange = fetchAndRender;
chkHeat.onchange = fetchAndRender;


// =====================================================
// ICONOS CUSTOM
// =====================================================
function iconFor(p){
  // Oficina
  if(p.ubicacion.includes("OFICINA")){
    return L.divIcon({
      html:"<div style='font-size:32px;'>🏦</div>",
      iconSize:[32,32], iconAnchor:[16,32]
    });
  }
  // Isla
  if(p.ubicacion.includes("ISLA")){
    return L.divIcon({
      html:"<div style='font-size:32px;color:deepskyblue;'>🌐</div>",
      iconSize:[32,32], iconAnchor:[16,32]
    });
  }
  // Normal ATM
  const color = p.promedio >= 4 ? "red" : "green";
  return L.divIcon({
    html:`<div style="width:14px;height:14px;border-radius:50%;background:${color};border:2px solid white;"></div>`,
    iconSize:[14,14], iconAnchor:[7,7]
  });
}


// =====================================================
// MOSTRAR PANEL ATM
// =====================================================
function showATMPanel(p){
  document.getElementById("panelCapa").style.display="none";
  document.getElementById("panelATM").style.display="block";

  const txt = 
`______________
 ATM ${p.atm}
______________

• Nombre: ${p.nombre}
• Dirección: ${p.direccion}
• División: ${p.division}
• Tipo: ${p.tipo}
• Ubicación: ${p.ubicacion}

• Dpto/Prov/Dist:
  ${p.departamento} / ${p.provincia} / ${p.distrito}

______________
Promedio: ${p.promedio}
______________`;

  document.getElementById("atmDetails").textContent = txt;
}

function volverPanel(){
  document.getElementById("panelATM").style.display="none";
  document.getElementById("panelCapa").style.display="block";
}


// =====================================================
// FETCH + RENDER
// =====================================================
async function fetchAndRender(){
  const params = new URLSearchParams();
  params.append("tipo", TIPO);
  if(selDepartamento.value) params.append("departamento", selDepartamento.value);
  if(selProvincia.value) params.append("provincia", selProvincia.value);
  if(selDistrito.value) params.append("distrito", selDistrito.value);
  if(selDivision.value) params.append("division", selDivision.value);

  const res = await fetch("/api/points?" + params.toString());
  const data = await res.json();

  markersLayer.clearLayers();
  heatLayer.setLatLngs([]);

  let heatPts = [];
  let bounds = [];

  // Conteo para panel de capa
  let total=0, disp=0, mon=0, rec=0;
  let sumProm=0;

  data.forEach(p=>{
    total++;
    sumProm += p.promedio;

    // Conteo por tipo
    const t = p.tipo.toUpperCase();
    if(t.includes("DISP")) disp++;
    if(t.includes("MON"))  mon++;
    if(t.includes("REC"))  rec++;

    // Marker
    const m = L.marker([p.lat,p.lon], {icon:iconFor(p)})
      .on("click", ()=> showATMPanel(p));

    markersLayer.addLayer(m);
    heatPts.push([p.lat,p.lon, Math.max(1,p.promedio)]);
    bounds.push([p.lat,p.lon]);
  });

  if(bounds.length===1) map.setView(bounds[0], 14);
  else if(bounds.length > 1) map.fitBounds(bounds, {padding:[20,20]});

  heatLayer.setLatLngs(heatPts);

  if(chkHeat.checked) heatLayer.addTo(map);
  else map.removeLayer(heatLayer);

  // Actualizar panel capa
  infoCount.textContent = total;
  promTotal.textContent = Math.round(sumProm);
  totalAtms.textContent = total;
  disp.textContent = disp;
  mon.textContent = mon;
  rec.textContent = rec;

  // Volver panel si estaba viendo un ATM
  volverPanel();
}

// Inicial
fetchAndRender();

</script>
</body>
</html>
"""
