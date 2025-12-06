# ============================================================
#   BACKEND BBVA GEOESPACIAL — COMPLETO Y FUNCIONAL
#   ✔ Departamento → Provincia → Distrito → División
#   ✔ API incluye filtro division
#   ✔ Precompute jerárquico correcto
# ============================================================

import os
import re
import unicodedata
import json
import pandas as pd
import numpy as np
from flask import Flask, render_template_string, request, jsonify, redirect, url_for, session
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
    except:
        key = f"{lat},{lon}"
    return address_cache.get(key, "Dirección no encontrada")


# ============================================================
# 2. CARGAR EXCEL
# ============================================================
BASE_DIR = os.path.dirname(__file__)
excel_path = os.path.join(BASE_DIR, "data", "Mapa Geoespacial ATM (1) (1).xlsx")

if not os.path.exists(excel_path):
    raise FileNotFoundError("NO SE ENCONTRÓ EL EXCEL")

raw = pd.read_excel(excel_path)

# ============================================================
# 3. NORMALIZACIÓN DE COLUMNAS
# ============================================================
def normalize_col(s):
    s = str(s)
    s = unicodedata.normalize("NFKD", s)
    s = s.encode("ascii", "ignore").decode("utf-8")
    s = s.upper().strip()
    s = re.sub(r"[^A-Z0-9 ]+", " ", s)
    s = re.sub(r"\s+", " ", s)
    return s

norm_map = {normalize_col(c): c for c in raw.columns}

def find_col(keys):
    for norm, orig in norm_map.items():
        for k in keys:
            if k in norm:
                return orig
    return None

COL_ATM  = find_col(["ATM"]) or "ATM"
COL_NAME = find_col(["NOMBRE","CAJERO"]) or None
COL_DEPT = find_col(["DEPARTAMENTO"]) or "DEPARTAMENTO"
COL_PROV = find_col(["PROVINCIA"]) or "PROVINCIA"
COL_DIST = find_col(["DISTRITO"]) or "DISTRITO"
COL_DIV  = find_col(["DIVISION"]) or "DIVISION"
COL_LAT  = find_col(["LAT"]) or "LATITUD"
COL_LON  = find_col(["LON","LONG"]) or "LONGITUD"
COL_TIPO = find_col(["TIPO"]) or "TIPO"
COL_UBIC = find_col(["UBIC"]) or "UBICACION_INTERNA"
PROM_COL = find_col(["PROM"]) or None
COL_DIR  = find_col(["DIRECCION"]) or None

if PROM_COL is None:
    raw["PROM_FAKE"] = 0
    PROM_COL = "PROM_FAKE"

# Limpieza coords
df = raw.copy()
df[COL_LAT] = (
    df[COL_LAT].astype(str)
    .str.replace(",", ".", regex=False)
    .str.replace(r"[^\d\.\-]", "", regex=True)
)
df[COL_LON] = (
    df[COL_LON].astype(str)
    .str.replace(",", ".", regex=False)
    .str.replace(r"[^\d\.\-]", "", regex=True)
)
df[COL_LAT] = pd.to_numeric(df[COL_LAT], errors="coerce")
df[COL_LON] = pd.to_numeric(df[COL_LON], errors="coerce")
df = df.dropna(subset=[COL_LAT,COL_LON]).reset_index(drop=True)
df[PROM_COL] = pd.to_numeric(df[PROM_COL], errors="coerce").fillna(0)

# ============================================================
# 4. PRECOMPUTO JERÁRQUICO → FUNDAMENTAL
# ============================================================

# DEPARTAMENTOS
DEPARTAMENTOS = sorted(df[COL_DEPT].dropna().astype(str).unique())

# PROVINCIAS POR DEPTO
PROV_BY_DEPT = (
    df.groupby(COL_DEPT)[COL_PROV]
    .apply(lambda x: sorted(x.dropna().unique()))
    .to_dict()
)

# DISTRITOS POR PROVINCIA
DIST_BY_PROV = (
    df.groupby(COL_PROV)[COL_DIST]
    .apply(lambda x: sorted(x.dropna().unique()))
    .to_dict()
)

# DIVISION POR DISTRITO
DIV_BY_DIST = (
    df.groupby(COL_DIST)[COL_DIV]
    .apply(lambda x: sorted(x.dropna().unique()))
    .to_dict()
)

# DIVISION POR PROVINCIA
DIV_BY_PROV = (
    df.groupby(COL_PROV)[COL_DIV]
    .apply(lambda x: sorted(x.dropna().unique()))
    .to_dict()
)

# DIVISION POR DEPTO
DIV_BY_DEPT = (
    df.groupby(COL_DEPT)[COL_DIV]
    .apply(lambda x: sorted(x.dropna().unique()))
    .to_dict()
)

# TODAS LAS DIVISIONES
DIV_ALL = sorted(df[COL_DIV].dropna().unique())

# ============================================================
# 5. FLASK + LOGIN
# ============================================================
app = Flask(__name__)
app.secret_key = os.getenv("SECRET_KEY","123")

APP_USER = os.getenv("APP_USERNAME","admin")
APP_PASS = os.getenv("APP_PASSWORD","123")

def login_required(f):
    @wraps(f)
    def wrapper(*a,**k):
        if session.get("user")!=APP_USER:
            return redirect("/login")
        return f(*a,**k)
    return wrapper

@app.route("/login",methods=["GET","POST"])
def login():
    if request.method=="POST":
        u=request.form.get("username")
        p=request.form.get("password")
        if u==APP_USER and p==APP_PASS:
            session["user"]=u
            return redirect("/")
    return "<form method='post'><input name='username'><input type='password' name='password'><button>OK</button></form>"

@app.route("/logout")
def logout():
    session.clear()
    return redirect("/login")

# ============================================================
# 6. API DE PUNTOS — AHORA CON FILTRO DIVISION
# ============================================================
@app.route("/api/points")
@login_required
def api_points():
    dept = request.args.get("departamento","").strip().upper()
    prov = request.args.get("provincia","").strip().upper()
    dist = request.args.get("distrito","").strip().upper()
    div  = request.args.get("division","").strip().upper()

    df2 = df.copy()

    df2[COL_DEPT] = df2[COL_DEPT].astype(str).str.upper()
    df2[COL_PROV] = df2[COL_PROV].astype(str).str.upper()
    df2[COL_DIST] = df2[COL_DIST].astype(str).str.upper()
    df2[COL_DIV]  = df2[COL_DIV].astype(str).str.upper()

    if dept:
        df2 = df2[df2[COL_DEPT]==dept]
    if prov:
        df2 = df2[df2[COL_PROV]==prov]
    if dist:
        df2 = df2[df2[COL_DIST]==dist]
    if div:
        df2 = df2[df2[COL_DIV]==div]

    out=[]
    for _,r in df2.iterrows():
        nombre = str(r.get(COL_NAME,"")).strip() or str(r.get(COL_ATM))

        out.append({
            "lat":float(r[COL_LAT]),
            "lon":float(r[COL_LON]),
            "atm":str(r.get(COL_ATM,"")),
            "nombre":nombre,
            "promedio":float(r.get(PROM_COL,0)),
            "division":str(r.get(COL_DIV,"")),
            "tipo":str(r.get(COL_TIPO,"")),
            "ubicacion":str(r.get(COL_UBIC,"")),
            "departamento":str(r.get(COL_DEPT,"")),
            "provincia":str(r.get(COL_PROV,"")),
            "distrito":str(r.get(COL_DIST,"")),
            "direccion":get_address(r[COL_LAT],r[COL_LON])
        })
    return jsonify(out)

# ============================================================
# 7. RUTA PRINCIPAL
# ============================================================
@app.route("/")
@login_required
def index():
    initial_center = df[[COL_LAT,COL_LON]].mean().tolist()
    return render_template_string(
        TEMPLATE_MAPA,
        tipo_mapa="oficinas",
        departamentos=DEPARTAMENTOS,
        provincias_by_dept=PROV_BY_DEPT,
        dist_by_prov=DIST_BY_PROV,
        div_by_dist=DIV_BY_DIST,
        div_by_prov=DIV_BY_PROV,
        div_by_dept=DIV_BY_DEPT,
        divisiones=DIV_ALL,
        initial_center=initial_center,
        initial_zoom=6
    )


    TEMPLATE_MAPA = """
<!doctype html>
<html>
<head>
<meta charset="utf-8">
<title>Mapa BBVA — ATMs</title>
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

/* Iconos personalizados */
.icon-bank div{
  font-size:30px;
}
.icon-isla div{
  font-size:30px;
  color:deepskyblue;
}
.icon-agent div{
  font-size:30px;
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
  <h1>Mapa BBVA — ATMs</h1>
  <a href="/logout" class="logout">Cerrar sesión</a>
</header>

<div class="topbar">
  <div class="controls">

    <!-- Filtros -->
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

    <label>D
      istrito:
      <select id="selDistrito">
        <option value="">-- Todos --</option>
      </select>
    </label>

    <label>División:
      <select id="selDivision">
        <option value="">-- Todas --</option>
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
      <div class="side-title">Resumen General</div>
      <div class="muted">Promedio total:</div>
      <div><b><span id="resPromedio">0</span></b></div>
      <div style="margin-top:6px; font-weight:600;">Totales</div>
      <div class="muted">Total ATMs: <span id="resTotal">0</span></div>
      <div class="muted">Dispensadores: <span id="resDisp">0</span></div>
      <div class="muted">Monederos: <span id="resMon">0</span></div>
      <div class="muted">Recicladores: <span id="resRec">0</span></div>

      <div style="margin-top:12px; font-weight:600;">Leyenda</div>
      <div class="muted">
        <div>🔴 ATM ≥ 4</div>
        <div>🟢 ATM ≤ 3</div>
        <div id="leyendaUbic"></div>
      </div>
    </div>

    <!-- PANEL ATM -->
    <div id="panelATM" class="side-card side-card-atm hidden">
      <h3>ATM Seleccionado</h3>
      <div id="atmDetalle"></div>
      <button id="btnVolver" class="btn-small">VOLVER</button>
    </div>

  </div>
</div>

<script src="https://unpkg.com/leaflet@1.9.4/dist/leaflet.js"></script>
<script src="https://unpkg.com/leaflet.markercluster@1.5.3/dist/MarkerCluster.js"></script>
<script src="https://unpkg.com/leaflet.heat/dist/leaflet-heat.js"></script>

<script>
/* ------------------ DATOS PRECALCULADOS DESDE PYTHON ------------------ */
const PROV_BY_DEPT = {{ provincias_by_dept|tojson }};
const DIST_BY_PROV = {{ dist_by_prov|tojson }};
const DIV_BY_DIST  = {{ div_by_dist|tojson }};
const DIV_BY_PROV  = {{ div_by_prov|tojson }};
const DIV_BY_DEPT  = {{ div_by_dept|tojson }};
const DIV_ALL      = {{ divisiones|tojson }};

const INITIAL_CENTER = [{{ initial_center[0] }}, {{ initial_center[1] }}];
const INITIAL_ZOOM   = {{ initial_zoom }};

/* ------------------ MAPA ------------------ */
const map = L.map("map").setView(INITIAL_CENTER, INITIAL_ZOOM);
L.tileLayer("https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png", {maxZoom:19}).addTo(map);

const markers = L.markerClusterGroup({chunkedLoading:true});
const heat    = L.heatLayer([], {radius:26, blur:20});
markers.addTo(map);
heat.addTo(map);

/* ------------------ DOM ------------------ */
const selDep  = document.getElementById("selDepartamento");
const selProv = document.getElementById("selProvincia");
const selDist = document.getElementById("selDistrito");
const selDiv  = document.getElementById("selDivision");
const chkHeat = document.getElementById("chkHeat");

const infoBox = document.getElementById("infoCount");

const resPromedio = document.getElementById("resPromedio");
const resTotal    = document.getElementById("resTotal");
const resDisp     = document.getElementById("resDisp");
const resMon      = document.getElementById("resMon");
const resRec      = document.getElementById("resRec");

const panelATM    = document.getElementById("panelATM");
const panelResumen = document.getElementById("panelResumen");
const atmDetalle  = document.getElementById("atmDetalle");
const btnVolver   = document.getElementById("btnVolver");

const leyendaUbic = document.getElementById("leyendaUbic");

/* ------------------ LEYENDA SEGÚN UBICACIÓN ------------------ */
leyendaUbic.innerHTML = "🏦 Oficina<br>🌐 Isla<br>🧍 Agente";

/* ------------------ COMBOS DEPENDIENTES ------------------ */
function updateProvincias(){
  const d = selDep.value;
  selProv.innerHTML = '<option value="">-- Todas --</option>';

  if(d && PROV_BY_DEPT[d]){
    PROV_BY_DEPT[d].forEach(v=>{
      selProv.innerHTML += `<option value="${v}">${v}</option>`;
    });
  }

  updateDistritos();
  updateDivisiones();
}

function updateDistritos(){
  const p = selProv.value;

  selDist.innerHTML = '<option value="">-- Todos --</option>';

  if(p && DIST_BY_PROV[p]){
    DIST_BY_PROV[p].forEach(v=>{
      selDist.innerHTML += `<option value="${v}">${v}</option>`;
    });
  }

  updateDivisiones();
}

function updateDivisiones(){
  const d  = selDep.value;
  const p  = selProv.value;
  const di = selDist.value;

  selDiv.innerHTML = '<option value="">-- Todas --</option>';

  let lista = [];

  if(di && DIV_BY_DIST[di]) lista = DIV_BY_DIST[di];
  else if(p && DIV_BY_PROV[p]) lista = DIV_BY_PROV[p];
  else if(d && DIV_BY_DEPT[d]) lista = DIV_BY_DEPT[d];
  else lista = DIV_ALL;

  lista.forEach(e=>{
    selDiv.innerHTML += `<option value="${e}">${e}</option>`;
  });
}

/* ------------------ ICONOS ------------------ */
function getIcon(pt){
  const ubic = (pt.ubicacion||"").toUpperCase();

  if(ubic.includes("OFICINA")){
    return L.divIcon({className:"icon-bank",html:"<div>🏦</div>",iconSize:[32,32],iconAnchor:[16,16]});
  }
  if(ubic.includes("ISLA")){
    return L.divIcon({className:"icon-isla",html:"<div>🌐</div>",iconSize:[32,32],iconAnchor:[16,16]});
  }
  if(ubic.includes("AGENTE")){
    return L.divIcon({className:"icon-agent",html:"<div>🧍</div>",iconSize:[32,32],iconAnchor:[16,16]});
  }

  const color = (pt.promedio||0)>=4 ? "red":"green";
  return L.divIcon({
    className:"icon-round",
    html:`<div style="background:${color};"></div>`,
    iconSize:[14,14],
    iconAnchor:[7,7]
  });
}

/* ------------------ PANEL ATM ------------------ */
function showATM(pt){
  panelResumen.classList.add("hidden");
  panelATM.classList.remove("hidden");
  panelATM.classList.add("glow");

  atmDetalle.textContent = `
ATM ${pt.atm}
_____________________
Nombre: ${pt.nombre}
Dirección: ${pt.direccion}
División: ${pt.division}
Tipo: ${pt.tipo}
Ubicación: ${pt.ubicacion}
_____________________
${pt.departamento} / ${pt.provincia} / ${pt.distrito}
_____________________
Promedio: ${pt.promedio}
`;
}

btnVolver.onclick = ()=>{
  panelATM.classList.add("hidden");
  panelATM.classList.remove("glow");
  panelResumen.classList.remove("hidden");
};

/* ------------------ FETCH Y RENDER ------------------ */
async function fetchPoints(){
  const qs = 
    `departamento=${encodeURIComponent(selDep.value)}&`+
    `provincia=${encodeURIComponent(selProv.value)}&`+
    `distrito=${encodeURIComponent(selDist.value)}&`+
    `division=${encodeURIComponent(selDiv.value)}`;

  infoBox.textContent = "...";

  const res = await fetch(`/api/points?${qs}`);
  const data = await res.json();

  markers.clearLayers();
  heat.setLatLngs([]);

  let bounds=[];
  let heatPts=[];
  let sum=0, total=0;
  let disp=0, mon=0, rec=0;

  data.forEach(pt=>{
    total++;
    sum += pt.promedio||0;

    const tipo = (pt.tipo||"").toUpperCase();
    if(tipo.includes("DISPENSADOR")) disp++;
    if(tipo.includes("MONEDERO"))    mon++;
    if(tipo.includes("RECICLADOR"))  rec++;

    const marker = L.marker([pt.lat,pt.lon],{icon:getIcon(pt)})
      .bindPopup(`<b>${pt.nombre}</b><br>${pt.direccion}<br>${pt.division}`)
      .on("click", ()=>showATM(pt));

    markers.addLayer(marker);

    heatPts.push([pt.lat,pt.lon,Math.max(1,pt.promedio||1)]);
    bounds.push([pt.lat,pt.lon]);
  });

  heat.setLatLngs(heatPts);

  infoBox.textContent = total;
  resTotal.textContent = total;
  resPromedio.textContent = total? Math.round(sum):0;
  resDisp.textContent = disp;
  resMon.textContent = mon;
  resRec.textContent = rec;

  if(bounds.length===1) map.setView(bounds[0],15);
  else if(bounds.length>1) map.fitBounds(bounds,{padding:[20,20]});
  else map.setView(INITIAL_CENTER,INITIAL_ZOOM);

  if(chkHeat.checked){
    if(!map.hasLayer(heat)) heat.addTo(map);
  }else{
    if(map.hasLayer(heat)) map.removeLayer(heat);
  }
}

/* ------------------ EVENTOS ------------------ */
selDep.onchange = ()=>{ updateProvincias(); fetchPoints(); };
selProv.onchange= ()=>{ updateDistritos();  fetchPoints(); };
selDist.onchange= ()=>{ updateDivisiones(); fetchPoints(); };
selDiv.onchange = ()=> fetchPoints();

chkHeat.onchange= fetchPoints;

/* ------------------ INICIAL ------------------ */
updateProvincias();
updateDivisiones();
fetchPoints();
</script>

</body>
</html>
"""