# ============================================================
#   PARTE 1 / 2 — BACKEND COMPLETO + LOGIN + SELECTOR + 3 CAPAS
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
    try:
        key = f"{float(lat):.6f},{float(lon):.6f}"
    except Exception:
        key = f"{lat},{lon}"
    return address_cache.get(key, "Dirección no encontrada")


# ============================================================
# 2. NORMALIZADOR DE COLUMNAS
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
# 3. FUNCIÓN DE LIMPIEZA DE DATAFRAMES POR CAPA
# ============================================================
def load_layer_excel(path):
    """
    Lee un Excel, normaliza columnas, detecta campos clave
    y retorna un DataFrame limpio garantizando columnas:
    ATM, NOMBRE, DEPARTAMENTO, PROVINCIA, DISTRITO,
    LATITUD, LONGITUD, DIVISION, TIPO, UBICACION, PROMEDIO
    """

    if not os.path.exists(path):
        raise FileNotFoundError(f"No encontré el Excel: {path}")

    raw = pd.read_excel(path)

    # Mapa normalizado
    norm_map = {normalize_col(c): c for c in raw.columns}

    # Detección de columnas
    COL_ATM = find_col(norm_map, ["TERMINAL", "COD_ATM", "ATM"]) or list(raw.columns)[0]
    COL_NAME = find_col(norm_map, ["COMERCIO", "NOMBRE", "CAJERO"])
    COL_DEPT = find_col(norm_map, ["DEPARTAMENTO"])
    COL_PROV = find_col(norm_map, ["PROVINCIA"])
    COL_DIST = find_col(norm_map, ["DISTRITO"])

    COL_LAT  = find_col(norm_map, ["LATITUD", "LAT"])
    COL_LON  = find_col(norm_map, ["LONGITUD", "LON"])

    COL_DIV  = find_col(norm_map, ["DIVISION"])
    COL_TIPO = find_col(norm_map, ["TIPO"])
    COL_UBIC = find_col(norm_map, ["UBICACION"])

    COL_PROM = find_col(norm_map, ["PROM", "TRXS", "PROMEDIO"])

    # Crear columnas faltantes
    required = {
        "ATM": COL_ATM,
        "NOMBRE": COL_NAME,
        "DEPARTAMENTO": COL_DEPT,
        "PROVINCIA": COL_PROV,
        "DISTRITO": COL_DIST,
        "LAT": COL_LAT,
        "LON": COL_LON,
        "DIVISION": COL_DIV,
        "TIPO": COL_TIPO,
        "UBICACION": COL_UBIC,
        "PROMEDIO": COL_PROM
    }

    df = raw.copy()

    for new, old in required.items():
        if old is None or old not in df.columns:
            df[new] = ""
        else:
            df[new] = df[old]

    # Limpieza de coordenadas
    df["LAT"] = (
        df["LAT"].astype(str)
        .str.replace(",", ".", regex=False)
        .str.replace(r"[^\d\.\-]", "", regex=True)
        .replace("", np.nan)
    ).astype(float)

    df["LON"] = (
        df["LON"].astype(str)
        .str.replace(",", ".", regex=False)
        .str.replace(r"[^\d\.\-]", "", regex=True)
        .replace("", np.nan)
    ).astype(float)

    df = df.dropna(subset=["LAT", "LON"]).reset_index(drop=True)

    # Promedio numérico
    df["PROMEDIO"] = pd.to_numeric(df["PROMEDIO"], errors="coerce").fillna(0.0)

    # Uniformizar strings
    for c in ["ATM", "NOMBRE", "DEPARTAMENTO", "PROVINCIA", "DISTRITO",
              "DIVISION", "TIPO", "UBICACION"]:
        df[c] = df[c].astype(str).fillna("")

    return df


# ============================================================
# 4. CARGA DE LOS 3 EXCELS (ISLAS / OFICINAS / AGENTES)
# ============================================================
BASE_DIR = os.path.dirname(__file__)

df_islas = load_layer_excel(os.path.join(BASE_DIR, "data", "Mapa Geoespacial ATM (1) (1).xlsx"))
df_oficinas = load_layer_excel(os.path.join(BASE_DIR, "data", "OFICINAS.xlsx"))
df_agentes = load_layer_excel(os.path.join(BASE_DIR, "data", "AGENTES.xlsx"))


# ============================================================
# 5. FILTROS JERÁRQUICOS UNIFICADOS (UNION DE LAS 3 CAPAS)
# ============================================================
df_union = pd.concat([df_islas, df_oficinas, df_agentes], ignore_index=True)

DEPARTAMENTOS = sorted(df_union["DEPARTAMENTO"].unique())

PROVINCIAS_BY_DEPT = (
    df_union.groupby("DEPARTAMENTO")["PROVINCIA"]
    .apply(lambda s: sorted(s.unique()))
    .to_dict()
)
DIST_BY_PROV = (
    df_union.groupby("PROVINCIA")["DISTRITO"]
    .apply(lambda s: sorted(s.unique()))
    .to_dict()
)
DIV_BY_DEPT = (
    df_union.groupby("DEPARTAMENTO")["DIVISION"]
    .apply(lambda s: sorted(s.unique()))
    .to_dict()
)
DIV_BY_PROV = (
    df_union.groupby("PROVINCIA")["DIVISION"]
    .apply(lambda s: sorted(s.unique()))
    .to_dict()
)
DIV_BY_DIST = (
    df_union.groupby("DISTRITO")["DIVISION"]
    .apply(lambda s: sorted(s.unique()))
    .to_dict()
)

DIVISIONES = sorted(df_union["DIVISION"].unique())


# ============================================================
# 6. FLASK + LOGIN
# ============================================================
app = Flask(__name__)
app.secret_key = os.getenv("SECRET_KEY", "fallback_local")

APP_USER = os.getenv("APP_USERNAME")
APP_PASS = os.getenv("APP_PASSWORD")

LOGIN_TEMPLATE = """... (igual que tu versión original) ..."""

def login_required(f):
    @wraps(f)
    def wrapper(*args, **kwargs):
        if session.get("user") != APP_USER:
            return redirect(url_for("login"))
        return f(*args, **kwargs)
    return wrapper


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
# 7. SELECTOR DE CAPA
# ============================================================
SELECTOR_TEMPLATE = """... (igual que tu versión original) ..."""

@app.route("/selector")
@login_required
def selector():
    return render_template_string(SELECTOR_TEMPLATE)


# ============================================================
# 8. RUTA MAPA (ENVÍA FILTROS + CAPA SELECCIONADA)
# ============================================================
@app.route("/mapa/<tipo>")
@login_required
def mapa_tipo(tipo):
    if tipo not in ["islas", "oficinas", "agentes"]:
        return "Capa no existe", 404

    initial_center = df_union[["LAT", "LON"]].mean().tolist()

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
# 9. API /api/points — USA "tipo" (A)
# ============================================================
@app.route("/api/points")
@login_required
def api_points():
    tipo = request.args.get("tipo", "").lower()

    # Elegir dataframe correcto
    if tipo == "islas":
        df = df_islas.copy()
    elif tipo == "oficinas":
        df = df_oficinas.copy()
    elif tipo == "agentes":
        df = df_agentes.copy()
    else:
        return jsonify({"puntos": []})

    # Filtros
    dpto = request.args.get("departamento", "").upper().strip()
    prov = request.args.get("provincia", "").upper().strip()
    dist = request.args.get("distrito", "").upper().strip()
    divi = request.args.get("division", "").upper().strip()

    if dpto:
        df = df[df["DEPARTAMENTO"] == dpto]
    if prov:
        df = df[df["PROVINCIA"] == prov]
    if dist:
        df = df[df["DISTRITO"] == dist]
    if divi:
        df = df[df["DIVISION"] == divi]

    # Resumen
    total = len(df)
    promedio = float(df["PROMEDIO"].mean()) if total > 0 else 0.0

    total_ofi = int(df["UBICACION"].str.contains("OFICINA", na=False).sum())
    total_isla= int(df["UBICACION"].str.contains("ISLA", na=False).sum())
    total_ag  = int(df["UBICACION"].str.contains("AGENTE", na=False).sum())

    # Puntos
    puntos = []
    for _, r in df.iterrows():
        puntos.append({
            "lat": float(r["LAT"]),
            "lon": float(r["LON"]),
            "atm": r["ATM"],
            "nombre": r["NOMBRE"],
            "division": r["DIVISION"],
            "tipo": r["TIPO"],
            "ubicacion": r["UBICACION"],
            "departamento": r["DEPARTAMENTO"],
            "provincia": r["PROVINCIA"],
            "distrito": r["DISTRITO"],
            "promedio": float(r["PROMEDIO"]),
            "direccion": get_address(r["LAT"], r["LON"])
        })

    return jsonify({
        "puntos": puntos,
        "total_atms": total,
        "promedio_total": promedio,
        "total_oficinas": total_ofi,
        "total_islas": total_isla,
        "total_agentes": total_ag
    })


# ============================================================
#   FIN PARTE 1
# ============================================================


# ============================================================
#   PARTE 2 / 2 — TEMPLATE MAPA COMPLETO (HTML + JS)
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

/* LAYOUT */
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
.side-title{
  font-weight:700;
  margin-bottom:4px;
}
.muted{
  color:var(--muted);
  font-size:12px;
}

/* PANEL ATM */
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
.hidden{ display:none; }

/* POPUP */
.leaflet-popup-content-wrapper{
  border-radius:12px;
  box-shadow:0 6px 20px rgba(0,0,0,0.25);
}
.popup-row{
  margin:2px 0;
  font-size:12px;
}

/* ICONOS */
.icon-oficina div{
  font-size:32px;
}
.icon-isla div{
  font-size:32px;
  color:deepskyblue;
}
.icon-agente div{
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

    <label style="margin-left:10px;">
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
      <div class="side-title">Resumen ({{ tipo_mapa }})</div>

      <div><b>Promedio total:</b> <span id="resPromedio">0</span></div>

      <div style="margin-top:6px;"><b>Total ATMs:</b> <span id="resTotal">0</span></div>

      <div class="muted">Oficinas: <span id="resOfi">0</span></div>
      <div class="muted">Islas: <span id="resIsla">0</span></div>
      <div class="muted">Agentes: <span id="resAgen">0</span></div>
    </div>

    <!-- PANEL DETALLE ATM -->
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
const TIPO_MAPA = "{{ tipo_mapa }}";

const PROV_BY_DEPT = {{ provincias_by_dept|tojson }};
const DIST_BY_PROV = {{ dist_by_prov|tojson }};
const DIV_BY_DEPT  = {{ div_by_dept|tojson }};
const DIV_BY_PROV  = {{ div_by_prov|tojson }};
const DIV_BY_DIST  = {{ div_by_dist|tojson }};
const ALL_DIV      = {{ divisiones|tojson }};

const INITIAL_CENTER = [{{ initial_center[0] }}, {{ initial_center[1] }}];
const INITIAL_ZOOM   = {{ initial_zoom }};

// MAPA
const map = L.map('map').setView(INITIAL_CENTER, INITIAL_ZOOM);
L.tileLayer('https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png', {maxZoom:19}).addTo(map);

const cluster = L.markerClusterGroup({ chunkedLoading:true });
cluster.addTo(map);

const heat = L.heatLayer([], {radius:27, blur:22});
heat.addTo(map);

// ELEMENTOS
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

// RESUMEN
const resProm  = document.getElementById("resPromedio");
const resTotal = document.getElementById("resTotal");
const resOfi   = document.getElementById("resOfi");
const resIsla  = document.getElementById("resIsla");
const resAgen  = document.getElementById("resAgen");


// FILTROS DEPENDIENTES
function updateProvincias(){
  selProv.innerHTML = '<option value="">-- Todas --</option>';
  const d = selDep.value;
  if(PROV_BY_DEPT[d]){
    PROV_BY_DEPT[d].forEach(p => selProv.innerHTML += `<option>${p}</option>`);
  }
  updateDistritos();
  updateDivisiones();
}
function updateDistritos(){
  selDist.innerHTML = '<option value="">-- Todos --</option>';
  const p = selProv.value;
  if(DIST_BY_PROV[p]){
    DIST_BY_PROV[p].forEach(d => selDist.innerHTML += `<option>${d}</option>`);
  }
  updateDivisiones();
}
function updateDivisiones(){
  selDiv.innerHTML = '<option value="">-- Todas --</option>';
  const d  = selDep.value;
  const p  = selProv.value;
  const di = selDist.value;

  if(DIV_BY_DIST[di]) return DIV_BY_DIST[di].forEach(v=>selDiv.innerHTML+=`<option>${v}</option>`);
  if(DIV_BY_PROV[p])  return DIV_BY_PROV[p].forEach(v=>selDiv.innerHTML+=`<option>${v}</option>`);
  if(DIV_BY_DEPT[d])  return DIV_BY_DEPT[d].forEach(v=>selDiv.innerHTML+=`<option>${v}</option>`);

  ALL_DIV.forEach(v => selDiv.innerHTML+=`<option>${v}</option>`);
}

selDep.onchange  = ()=>{ updateProvincias(); fetchPoints(); };
selProv.onchange = ()=>{ updateDistritos(); fetchPoints(); };
selDist.onchange = ()=>{ updateDivisiones(); fetchPoints(); };
selDiv.onchange  = ()=> fetchPoints();


// ICONOS
function getIcon(pt){
  const ubic = (pt.ubicacion||"").toUpperCase();

  if(ubic.includes("OFICINA")){
    return L.divIcon({className:"icon-oficina", html:"<div>🏦</div>", iconSize:[32,32], iconAnchor:[16,16]});
  }
  if(ubic.includes("ISLA")){
    return L.divIcon({className:"icon-isla", html:"<div>🌐</div>", iconSize:[32,32], iconAnchor:[16,16]});
  }
  if(ubic.includes("AGENTE")){
    return L.divIcon({className:"icon-agente", html:"<div>🧍</div>", iconSize:[28,28], iconAnchor:[14,14]});
  }
  const color = (pt.promedio>=4 ? "red":"green");
  return L.divIcon({className:"icon-round", html:`<div style='background:${color};'></div>`});
}


// PANEL DETALLE
function showATM(pt){
  atmDetalle.textContent = `
ATM: ${pt.atm}
Nombre: ${pt.nombre}
Dirección: ${pt.direccion}
División: ${pt.division}
Tipo: ${pt.tipo}
Ubicación: ${pt.ubicacion}

Departamento: ${pt.departamento}
Provincia: ${pt.provincia}
Distrito: ${pt.distrito}

Promedio: ${pt.promedio}
  `;
  panelResumen.classList.add("hidden");
  panelATM.classList.remove("hidden");
}
btnVolver.onclick = ()=>{
  panelATM.classList.add("hidden");
  panelResumen.classList.remove("hidden");
};


// FETCH POINTS
async function fetchPoints(){
  const qs = `tipo=${TIPO_MAPA}&departamento=${selDep.value}&provincia=${selProv.value}&distrito=${selDist.value}&division=${selDiv.value}`;

  panelATM.classList.add("hidden");
  panelResumen.classList.remove("hidden");

  const res = await fetch(`/api/points?${qs}`);
  const data = await res.json();

  const pts = data.puntos || [];

  infoBox.textContent = pts.length;
  cluster.clearLayers();
  heat.setLatLngs([]);

  let bounds=[];

  pts.forEach(pt=>{
    const m = L.marker([pt.lat, pt.lon], {icon:getIcon(pt)});
    m.on("click", ()=> showATM(pt));
    cluster.addLayer(m);
    bounds.push([pt.lat, pt.lon]);
  });

  if(bounds.length===1) map.setView(bounds[0], 15);
  else if(bounds.length>1) map.fitBounds(bounds, {padding:[20,20]});
  else map.setView(INITIAL_CENTER, INITIAL_ZOOM);

  // heatmap
  if(chkHeat.checked){
    heat.setLatLngs(pts.map(pt=>[pt.lat, pt.lon, Math.max(1, pt.promedio)]));
    if(!map.hasLayer(heat)) heat.addTo(map);
  }else{
    if(map.hasLayer(heat)) map.removeLayer(heat);
  }

  // resumen
  resProm.textContent  = Math.round(data.promedio_total||0);
  resTotal.textContent = data.total_atms||0;
  resOfi.textContent   = data.total_oficinas||0;
  resIsla.textContent  = data.total_islas||0;
  resAgen.textContent  = data.total_agentes||0;
}

updateProvincias();
fetchPoints();
</script>

</body>
</html>
"""