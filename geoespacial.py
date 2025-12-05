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
# 2. CARGAR EXCEL PRINCIPAL
# ============================================================
BASE_DIR = os.path.dirname(__file__)
excel_main = os.path.join(BASE_DIR, "data", "Mapa Geoespacial ATM (1) (1).xlsx")

if not os.path.exists(excel_main):
    raise FileNotFoundError("No encontré archivo Excel de ATMs.")

raw = pd.read_excel(excel_main)

def normalize_col(s):
    s = str(s)
    s = unicodedata.normalize("NFKD", s).encode("ascii", "ignore").decode("utf-8")
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


# Detectar columnas
COL_ATM = find_col(["COD_ATM", "ATM"]) or "ATM"
COL_NAME = find_col(["NOMBRE", "CAJERO"])
COL_DEPT = find_col(["DEPARTAMENTO"]) or "DEPARTAMENTO"
COL_PROV = find_col(["PROVINCIA"]) or "PROVINCIA"
COL_DIST = find_col(["DISTRITO"]) or "DISTRITO"
COL_LAT = find_col(["LATITUD", "LAT"]) or "LATITUD"
COL_LON = find_col(["LONGITUD", "LON"]) or "LONGITUD"
COL_DIV = find_col(["DIVISION", "DIVISIÓN"]) or "DIVISIÓN"
COL_TIPO = find_col(["TIPO"]) or "TIPO"
COL_UBIC = find_col(["UBICACION", "UBICACIÓN", "UBICACION INTERNA"]) or "UBICACION_INTERNA"
PROM_COL = find_col(["PROMEDIO", "PROM"])

if PROM_COL is None:
    raw["PROM_FAKE"] = 0.0
    PROM_COL = "PROM_FAKE"

df = raw.copy()

# Corrige coordenadas
df[COL_LAT] = (df[COL_LAT].astype(str)
               .str.replace(",", ".", regex=False)
               .str.replace(r"[^\d\.\-]", "", regex=True)
               .replace("", np.nan).astype(float))

df[COL_LON] = (df[COL_LON].astype(str)
               .str.replace(",", ".", regex=False)
               .str.replace(r"[^\d\.\-]", "", regex=True)
               .replace("", np.nan).astype(float))

df = df.dropna(subset=[COL_LAT, COL_LON]).reset_index(drop=True)

df[PROM_COL] = pd.to_numeric(df[PROM_COL], errors="coerce").fillna(0.0)
df[COL_TIPO] = df[COL_TIPO].astype(str)
df[COL_UBIC] = df[COL_UBIC].astype(str)

# ============================================================
# 3. LISTAS JERÁRQUICAS PARA FILTROS
# ============================================================
DEPARTAMENTOS = sorted(df[COL_DEPT].dropna().unique().tolist())
PROVINCIAS_BY_DEPT = df.groupby(COL_DEPT)[COL_PROV].apply(lambda x: sorted(x.dropna().unique())).to_dict()
DIST_BY_PROV = df.groupby(COL_PROV)[COL_DIST].apply(lambda x: sorted(x.dropna().unique())).to_dict()
DIV_BY_DEPT = df.groupby(COL_DEPT)[COL_DIV].apply(lambda x: sorted(x.dropna().unique())).to_dict()
DIV_BY_PROV = df.groupby(COL_PROV)[COL_DIV].apply(lambda x: sorted(x.dropna().unique())).to_dict()
DIV_BY_DIST = df.groupby(COL_DIST)[COL_DIV].apply(lambda x: sorted(x.dropna().unique())).to_dict()
DIVISIONES = sorted(df[COL_DIV].dropna().unique())

# ============================================================
# 4. FLASK + LOGIN
# ============================================================
app = Flask(__name__)
app.secret_key = os.getenv("SECRET_KEY", "fallback_local")

APP_USER = os.getenv("APP_USERNAME")
APP_PASS = os.getenv("APP_PASSWORD")

LOGIN_TEMPLATE = """
<!DOCTYPE html>
<html>
<head>
<meta charset="utf-8">
<title>Acceso Seguro — BBVA</title>
<style>
body{
    margin:0;
    background:url('{{ url_for('static', filename='bbva.png') }}') center/cover no-repeat fixed;
    height:100vh;
    display:flex;
    justify-content:center;
    align-items:center;
    font-family:Arial;
}
.box{
    background:rgba(255,255,255,0.92);
    padding:32px;
    border-radius:12px;
    width:360px;
    box-shadow:0 10px 26px rgba(0,0,0,0.3);
}
input{width:100%; margin:8px 0; padding:10px; border-radius:8px;}
button{width:100%; padding:10px; background:#1464A5; color:white; border:none; border-radius:8px; font-weight:bold;}
</style>
</head>
<body>
<div class="box">
<h2>Iniciar Sesión</h2>
{% if error %}<p style="color:red">{{error}}</p>{% endif %}
<form method="post">
<input name="username" placeholder="Usuario" required>
<input name="password" type="password" placeholder="Contraseña" required>
<button>Ingresar</button>
</form>
</div>
</body>
</html>
"""

@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        if request.form["username"] == APP_USER and request.form["password"] == APP_PASS:
            session["user"] = APP_USER
            return redirect("/selector")
        return render_template_string(LOGIN_TEMPLATE, error="Credenciales incorrectas")
    return render_template_string(LOGIN_TEMPLATE)


@app.route("/logout")
def logout():
    session.clear()
    return redirect("/login")


# ============================================================
# 5. SELECTOR DE CAPAS (IMÁGENES GRANDES)
# ============================================================
SELECTOR_TEMPLATE = """
<!DOCTYPE html>
<html>
<head>
<meta charset="utf-8">
<title>Selector de Capas — BBVA</title>
<style>
body{
  background:#eef4fb;
  padding:40px;
  text-align:center;
  font-family:Arial;
}
.grid{
  margin-top:40px;
  display:flex;
  gap:40px;
  justify-content:center;
}
.card{
  width:560px;
  height:520px;
  background:white;
  border-radius:20px;
  padding:16px;
  cursor:pointer;
  box-shadow:0 8px 22px rgba(0,0,0,0.2);
  transition:0.2s;
}
.card:hover{ transform:scale(1.05); }
.card img{
  width:100%; height:230px; object-fit:cover;
  border-radius:14px;
}
.card-title{
  margin-top:10px;
  font-size:20px;
  font-weight:bold;
  color:#072146;
}
</style>
</head>
<body>
<h1>Seleccione la capa</h1>
<div class="grid">

<div class="card" onclick="location.href='/mapa/oficinas'">
<img src="{{ url_for('static', filename='oficina.png') }}">
<div class="card-title">🏦 Oficinas</div>
</div>

<div class="card" onclick="location.href='/mapa/islas'">
<img src="{{ url_for('static', filename='isla.png') }}">
<div class="card-title">🌐 Islas</div>
</div>

<div class="card" onclick="location.href='/mapa/agentes'">
<img src="{{ url_for('static', filename='agente.png') }}">
<div class="card-title">🧍 Agentes</div>
</div>

</div>
</body>
</html>
"""

@app.route("/selector")
def selector():
    return render_template_string(SELECTOR_TEMPLATE)


# ============================================================
# 6. RUTA DEL MAPA POR CAPA
# ============================================================
@app.route("/mapa/<tipo>")
def mapa_tipo(tipo):
    if tipo not in ["oficinas", "islas", "agentes"]:
        return "No existe esa capa", 404

    center = df[[COL_LAT, COL_LON]].mean().tolist()
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
        initial_center=center,
        initial_zoom=6,
    )


# ============================================================
# 7. API /api/points — Filtrado completo
# ============================================================
@app.route("/api/points")
def api_points():
    tipo = request.args.get("tipo", "").lower()
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

    # Filtrado por tipo
    if tipo == "oficinas":
        dff = dff[dff[COL_UBIC].str.contains("OFICINA", na=False)]
    elif tipo == "islas":
        dff = dff[dff[COL_UBIC].str.contains("ISLA", na=False)]
    elif tipo == "agentes":
        dff = dff[dff[COL_UBIC].str.contains("AGENTE", na=False)]

    # Filtros jerárquicos
    if dpto: dff = dff[dff[COL_DEPT] == dpto]
    if prov: dff = dff[dff[COL_PROV] == prov]
    if dist: dff = dff[dff[COL_DIST] == dist]
    if divi: dff = dff[dff[COL_DIV] == divi]

    puntos = []
    for _, r in dff.iterrows():
        nombre = str(r.get(COL_NAME, "")) or str(r.get(COL_ATM, ""))

        puntos.append({
            "lat": float(r[COL_LAT]),
            "lon": float(r[COL_LON]),
            "atm": str(r.get(COL_ATM, "")),
            "nombre": nombre,
            "promedio": float(r.get(PROM_COL, 0.0)),
            "division": str(r.get(COL_DIV, "")),
            "tipo": str(r.get(COL_TIPO, "")),
            "ubicacion": str(r.get(COL_UBIC, "")),
            "departamento": str(r.get(COL_DEPT, "")),
            "provincia": str(r.get(COL_PROV, "")),
            "distrito": str(r.get(COL_DIST, "")),
            "direccion": get_address(float(r[COL_LAT]), float(r[COL_LON])),
        })

    return jsonify(puntos)


# ============================================================
# 8. TEMPLATE DEL MAPA COMPLETO
# ============================================================

TEMPLATE_MAPA = """
<!doctype html>
<html>
<head>
<meta charset="utf-8">
<title>Mapa BBVA — {{ tipo_mapa|upper }}</title>

<link rel="stylesheet" href="https://unpkg.com/leaflet@1.9.4/dist/leaflet.css"/>
<link rel="stylesheet" href="https://unpkg.com/leaflet.markercluster@1.5.3/dist/MarkerCluster.css"/>
<link rel="stylesheet" href="https://unpkg.com/leaflet.markercluster@1.5.3/dist/MarkerCluster.Default.css"/>

<style>
body{
    margin:0;
    font-family:Arial;
    background:#eef4fb;
}
header{
    background:#003366;
    color:white;
    height:70px;
    display:flex;
    justify-content:center;
    align-items:center;
    position:relative;
}
.logout{
    position:absolute;
    right:20px;
    background:#1464A5;
    padding:8px 16px;
    border-radius:8px;
    color:white;
    text-decoration:none;
    font-weight:bold;
}
.topbar{
    padding:16px 20px;
}
.controls{
    background:white;
    padding:12px;
    border-radius:12px;
    box-shadow:0 4px 16px rgba(0,0,0,0.15);
    display:flex;
    flex-wrap:wrap;
    gap:12px;
}
select{
    padding:6px 10px;
    border-radius:8px;
}
.main{
    display:flex;
    padding:20px;
    gap:20px;
}
#map{
    flex:1;
    height:75vh;
    border-radius:12px;
    box-shadow:0 8px 24px rgba(0,0,0,0.25);
}
.side{
    width:360px;
}

/* PANEL ESTÁTICO */
#panelResumen{
    background:white;
    border-radius:12px;
    padding:20px;
    box-shadow:0 8px 24px rgba(0,0,0,0.2);
    margin-bottom:15px;
}

/* PANEL ATM */
.side-card-atm{
    background:white;
    border-left:6px solid #1464A5;
    padding:20px;
    border-radius:12px;
    white-space:pre-line;
    box-shadow:0 8px 22px rgba(0,0,0,0.2);
}
.hidden{display:none;}
.btn{
    margin-top:10px;
    padding:6px 14px;
    background:#1464A5;
    color:white;
    border:none;
    border-radius:8px;
    cursor:pointer;
}

</style>
</head>

<body>

<header>
  <h2>Mapa BBVA — {{ tipo_mapa|upper }}</h2>
  <a class="logout" href="/logout">Cerrar sesión</a>
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

<label><input type="checkbox" id="chkHeat" checked> Heatmap</label>

</div>
</div>

<div class="main">
<div id="map"></div>

<div class="side">

<!-- PANEL ESTÁTICO DE RESUMEN -->
<div id="panelResumen">
  <h3>Resumen General</h3>
  <b>Promedio total:</b> <span id="resPromedio">0</span><br><br>
  <b>Total ATMs:</b> <span id="resTotal">0</span><br>
  <b>Dispensador:</b> <span id="resDisp">0</span><br>
  <b>Monedero:</b> <span id="resMon">0</span><br>
  <b>Reciclador:</b> <span id="resRec">0</span><br>
</div>

<!-- PANEL ATM -->
<div id="panelATM" class="side-card-atm hidden">
  <h3>ATM Seleccionado</h3>
  <div id="atmDetalle"></div>
  <button class="btn" id="btnVolver">Volver</button>
</div>

</div>
</div>

<script src="https://unpkg.com/leaflet@1.9.4/dist/leaflet.js"></script>
<script src="https://unpkg.com/leaflet.markercluster@1.5.3/dist/leaflet.markercluster.js"></script>
<script src="https://unpkg.com/leaflet.heat/dist/leaflet-heat.js"></script>

<script>

const TIPO_MAPA = "{{ tipo_mapa }}";
const PROV_BY_DEPT = {{ provincias_by_dept|tojson }};
const DIST_BY_PROV = {{ dist_by_prov|tojson }};

const map = L.map('map').setView(
    [{{ initial_center[0] }}, {{ initial_center[1] }}],
    {{ initial_zoom }}
);
L.tileLayer('https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png',{maxZoom:19}).addTo(map);

const markers = L.markerClusterGroup();
map.addLayer(markers);

const heat = L.heatLayer([], {radius:25, blur:20});
map.addLayer(heat);

const selDep=document.getElementById("selDepartamento");
const selProv=document.getElementById("selProvincia");
const selDist=document.getElementById("selDistrito");
const selDiv=document.getElementById("selDivision");
const chkHeat=document.getElementById("chkHeat");

const panelResumen=document.getElementById("panelResumen");
const panelATM=document.getElementById("panelATM");
const atmDetalle=document.getElementById("atmDetalle");
const btnVolver=document.getElementById("btnVolver");

/* =============================
   PANEL ATM
=============================*/
function showPanel(pt){
    atmDetalle.textContent=
`ATM ${pt.atm}

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

btnVolver.onclick=()=>{
    panelATM.classList.add("hidden");
    panelResumen.classList.remove("hidden");
};

/* =============================
   CARGA PROVINCIAS Y DISTRITOS
=============================*/
selDep.onchange=()=>{
    selProv.innerHTML='<option value="">-- Todas --</option>';
    if(PROV_BY_DEPT[selDep.value]){
        PROV_BY_DEPT[selDep.value].forEach(p=>{
            selProv.innerHTML+=`<option>${p}</option>`;
        });
    }
    loadDistritos();
    fetchPoints();
};
selProv.onchange=()=>{
    loadDistritos();
    fetchPoints();
};
selDist.onchange=fetchPoints;
selDiv.onchange=fetchPoints;
chkHeat.onchange=fetchPoints;

function loadDistritos(){
    selDist.innerHTML='<option value="">-- Todos --</option>';
    if(DIST_BY_PROV[selProv.value]){
        DIST_BY_PROV[selProv.value].forEach(d=>{
            selDist.innerHTML+=`<option>${d}</option>`;
        });
    }
}

/* =============================
   ÍCONOS
=============================*/
function getIcon(pt){
    const u=(pt.ubicacion||"").toUpperCase();
    if(u.includes("OFICINA"))
        return L.divIcon({html:"<div style='font-size:30px'>🏦</div>"});
    if(u.includes("ISLA"))
        return L.divIcon({html:"<div style='font-size:30px;color:deepskyblue'>🌐</div>"});
    if(u.includes("AGENTE"))
        return L.divIcon({html:"<div style='font-size:30px'>🧍</div>"});

    const color=(pt.promedio>=4)?"red":"green";
    return L.divIcon({html:`<div style='width:14px;height:14px;background:${color};border-radius:50%'></div>`});
}

/* =============================
   FETCH DE PUNTOS + RESUMEN
=============================*/
async function fetchPoints(){

    const qs=
      "tipo="+TIPO_MAPA+
      "&departamento="+encodeURIComponent(selDep.value)+
      "&provincia="+encodeURIComponent(selProv.value)+
      "&distrito="+encodeURIComponent(selDist.value)+
      "&division="+encodeURIComponent(selDiv.value);

    const res=await fetch("/api/points?"+qs);
    const data=await res.json();

    markers.clearLayers();
    heat.setLatLngs([]);

    let total=0, disp=0, mon=0, rec=0;
    let sumProm=0;
    let bounds=[];

    data.forEach(pt=>{
        total++;
        sumProm+=pt.promedio || 0;

        if(pt.tipo.includes("DISP")) disp++;
        if(pt.tipo.includes("MON")) mon++;
        if(pt.tipo.includes("REC")) rec++;

        const icon=getIcon(pt);
        const m=L.marker([pt.lat, pt.lon], {icon});
        m.on("click",()=>showPanel(pt));
        markers.addLayer(m);

        heat.addLatLng([pt.lat, pt.lon, Math.max(pt.promedio,1)]);
        bounds.push([pt.lat, pt.lon]);
    });

    document.getElementById("resTotal").textContent=total;
    document.getElementById("resPromedio").textContent=sumProm.toFixed(2);
    document.getElementById("resDisp").textContent=disp;
    document.getElementById("resMon").textContent=mon;
    document.getElementById("resRec").textContent=rec;

    if(bounds.length===1) map.setView(bounds[0],14);
    else if(bounds.length>1) map.fitBounds(bounds,{padding:[20,20]});

    if(chkHeat.checked){
        if(!map.hasLayer(heat)) map.addLayer(heat);
    } else {
        if(map.hasLayer(heat)) map.removeLayer(heat);
    }
}

loadDistritos();
fetchPoints();

</script>

</body>
</html>
"""

