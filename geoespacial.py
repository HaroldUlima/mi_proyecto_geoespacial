# ============================================================
#   PARTE 1 / 2  —  BACKEND COMPLETO + LOGIN + SELECTOR
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
# 2. CARGAR EXCEL PRINCIPAL (OFICINAS + ISLAS)
# ============================================================
BASE_DIR = os.path.dirname(__file__)
excel_main = os.path.join(BASE_DIR, "data", "Mapa Geoespacial ATM (1) (1).xlsx")

if not os.path.exists(excel_main):
    raise FileNotFoundError("No encontré archivo Excel de ATMs.")

raw = pd.read_excel(excel_main)

# Normalizador
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

# Detectar columnas
COL_ATM  = find_col(["ATM"]) or "ATM"
COL_NAME = find_col(["NOMBRE", "CAJERO"]) or None
COL_DEPT = find_col(["DEPARTAMENTO"]) or "DEPARTAMENTO"
COL_PROV = find_col(["PROVINCIA"]) or "PROVINCIA"
COL_DIST = find_col(["DISTRITO"]) or "DISTRITO"
COL_LAT  = find_col(["LAT"]) or "LAT"
COL_LON  = find_col(["LON"]) or "LON"
COL_DIV  = find_col(["DIVISION"]) or "DIVISION"
COL_TIPO = find_col(["TIPO"]) or "TIPO"
COL_UBIC = find_col(["UBICACION","UBICACION_INTERNA"]) or "UBICACION_INTERNA"
PROM_COL = find_col(["PROMEDIO","PROM"]) or None

if PROM_COL is None:
    raw["PROM_FAKE"] = 0.0
    PROM_COL = "PROM_FAKE"

for c in [COL_ATM, COL_DEPT, COL_PROV, COL_DIST, COL_LAT, COL_LON, COL_DIV, COL_TIPO, COL_UBIC]:
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
    lambda s: sorted(s.dropna().unique())
).to_dict()

DIST_BY_PROV = df.groupby(COL_PROV)[COL_DIST].apply(
    lambda s: sorted(s.dropna().unique())
).to_dict()

# División jerárquica
DIV_BY_DEPT = df.groupby(COL_DEPT)[COL_DIV].apply(
    lambda s: sorted(s.dropna().unique())
).to_dict()

DIV_BY_PROV = df.groupby(COL_PROV)[COL_DIV].apply(
    lambda s: sorted(s.dropna().unique())
).to_dict()

DIV_BY_DIST = df.groupby(COL_DIST)[COL_DIV].apply(
    lambda s: sorted(s.dropna().unique())
).to_dict()

DIVISIONES = sorted(df[COL_DIV].dropna().unique())


# ============================================================
# 4. FLASK + LOGIN BBVA (imagen de fondo)
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
    font-family:Arial; background:#eef3f9;
    padding:40px;
}
.box{
    width:260px; height:260px;
    background:white; border-radius:18px;
    box-shadow:0 0 14px rgba(0,0,0,0.15);
    display:flex; justify-content:center; align-items:center;
    font-size:28px; cursor:pointer; transition:.2s;
}
.box:hover{ transform:scale(1.05); }
.grid{
    display:flex; gap:40px; justify-content:center; margin-top:40px;
}
h1{text-align:center;}
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
    if tipo not in ["oficinas","islas","agentes"]:
        return "No existe esa capa", 404

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
        initial_center=df[[COL_LAT, COL_LON]].mean().tolist(),
        initial_zoom=6
    )


# ============================================================
# 7. API /api/points — Filtrado jerárquico completo
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

    # Filtrar por capa
    if tipo_mapa == "oficinas":
        dff = dff[dff[COL_UBIC].str.contains("OFICINA")]
    elif tipo_mapa == "islas":
        dff = dff[dff[COL_UBIC].str.contains("ISLA")]
    elif tipo_mapa == "agentes":
        dff = dff[dff[COL_UBIC].str.contains("AGENTE")]  # Actualmente quedará vacío

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

        nombre = str(r.get(COL_NAME)) if COL_NAME else str(r[COL_ATM])

        puntos.append({
            "lat": float(r[COL_LAT]),
            "lon": float(r[COL_LON]),
            "atm": str(r[COL_ATM]),
            "nombre": nombre,
            "promedio": float(r[PROM_COL]),
            "division": str(r[COL_DIV]),
            "tipo": str(r[COL_TIPO]),
            "ubicacion": str(r[COL_UBIC]),
            "departamento": str(r[COL_DEPT]),
            "provincia": str(r[COL_PROV]),
            "distrito": str(r[COL_DIST]),
            "direccion": get_address(r[COL_LAT], r[COL_LON])
        })

    return jsonify(puntos)


# ============================================================
# 8. IMPORTAMOS TEMPLATE MAPA (PARTE 2)
# ============================================================
#  → Viene en el siguiente mensaje como PARTE 2
# ============================================================





# ============================================================
#   PARTE 2 / 2  —  TEMPLATE DEL MAPA COMPLETO
# ============================================================

TEMPLATE_MAPA = """
<!doctype html>
<html>
<head>
<meta charset="utf-8">
<title>Mapa — {{ tipo_mapa|upper }}</title>

<link rel="stylesheet" href="https://unpkg.com/leaflet@1.9.4/dist/leaflet.css"/>
<link rel="stylesheet" href="https://unpkg.com/leaflet.markercluster@1.5.3/dist/MarkerCluster.css"/>
<link rel="stylesheet" href="https://unpkg.com/leaflet.markercluster@1.5.3/dist/MarkerCluster.Default.css"/>

<style>
body{
    margin:0;
    font-family:Arial, Helvetica, sans-serif;
    background:#eef3f9;
}
header{
    background:#003366;
    color:white;
    height:70px;
    display:flex;
    align-items:center;
    justify-content:center;
    position:relative;
}
header h1{
    font-size:2rem;
    margin:0;
}
.logout{
    position:absolute;
    right:20px;
    background:#1464A5;
    color:white;
    padding:8px 16px;
    border-radius:8px;
    text-decoration:none;
    font-weight:bold;
}

/* Controles */
.controls{
    background:white;
    padding:14px;
    margin:20px;
    border-radius:12px;
    box-shadow:0 4px 14px rgba(0,0,0,0.1);
    display:flex;
    gap:12px;
    align-items:center;
    flex-wrap:wrap;
}
.controls label{
    font-weight:bold;
    font-size:14px;
}
select{
    padding:6px 10px;
    border-radius:6px;
    border:1px solid #ccc;
}

#map{
    margin:20px;
    height:78vh;
    border-radius:12px;
    overflow:hidden;
    box-shadow:0 8px 20px rgba(0,0,0,0.15);
}

/* Popup estilo BBVA */
.leaflet-popup-content-wrapper{
    border-radius:12px;
    box-shadow:0 6px 20px rgba(0,0,0,0.25);
}
.popup-title{
    font-size:15px;
    font-weight:bold;
    color:#1464A5;
    margin-bottom:6px;
}
.popup-row{
    margin:2px 0;
}

/* Iconos personalizados */
.icon-bank div{
    font-size:32px;
}
.icon-isla div{
    font-size:32px;
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
  <h1>Mapa — {{ tipo_mapa|upper }}</h1>
  <a href="/logout" class="logout">Cerrar sesión</a>
</header>

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

  <label style="margin-left:20px;">
    <input type="checkbox" id="chkHeat" checked> Heatmap
  </label>

  <span style="margin-left:20px; font-weight:bold;">
    Total: <span id="infoCount">--</span> ATMs
  </span>

</div>

<div id="map"></div>

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

const map = L.map('map').setView(
    [{{ initial_center[0] }}, {{ initial_center[1] }}],
    {{ initial_zoom }}
);

L.tileLayer('https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png').addTo(map);

const markers = L.markerClusterGroup({ chunkedLoading:true });
const heat = L.heatLayer([], {radius:28, blur:22});
markers.addTo(map);
heat.addTo(map);


// =======================================
//  POPULAR COMBOS JERÁRQUICOS
// =======================================
const selDep  = document.getElementById("selDepartamento");
const selProv = document.getElementById("selProvincia");
const selDist = document.getElementById("selDistrito");
const selDiv  = document.getElementById("selDivision");
const chkHeat = document.getElementById("chkHeat");
const infoBox = document.getElementById("infoCount");

function updateProvincias() {
    let d = selDep.value;
    selProv.innerHTML = '<option value="">-- Todas --</option>';
    if (d && PROV_BY_DEPT[d]) {
        PROV_BY_DEPT[d].forEach(p=>{
            selProv.innerHTML += `<option value="${p}">${p}</option>`;
        });
    }
    updateDistritos();
}

function updateDistritos() {
    let p = selProv.value;
    let d = selDep.value;
    selDist.innerHTML = '<option value="">-- Todos --</option>';
    if (p && DIST_BY_PROV[p]) {
        DIST_BY_PROV[p].forEach(x=>{
            selDist.innerHTML += `<option value="${x}">${x}</option>`;
        });
    } else if (d && PROV_BY_DEPT[d]) {
        // fallback
    }
}

selDep.onchange  = ()=>{ updateProvincias(); fetchPoints(); };
selProv.onchange = ()=>{ updateDistritos(); fetchPoints(); };
selDist.onchange = ()=> fetchPoints();
selDiv.onchange  = ()=> fetchPoints();
chkHeat.onchange = ()=> fetchPoints();


// =======================================
//  FUNCIÓN PRINCIPAL
// =======================================
async function fetchPoints(){

    const d  = selDep.value;
    const p  = selProv.value;
    const di = selDist.value;
    const dv = selDiv.value;

    const qs = `tipo=${TIPO_MAPA}&departamento=${d}&provincia=${p}&distrito=${di}&division=${dv}`;
    const res = await fetch(`/api/points?${qs}`);
    const data = await res.json();

    infoBox.innerText = data.length;

    markers.clearLayers();
    heat.setLatLngs([]);

    let heatPts = [];
    let bounds = [];

    data.forEach(pt=>{
        let icon;

        // Icono por tipo de capa
        if(pt.ubicacion.includes("OFICINA")){
            icon = L.divIcon({
                className:"icon-bank",
                html:"<div>🏦</div>",
                iconSize:[32,32],
                iconAnchor:[16,16]
            });
        }
        else if(pt.ubicacion.includes("ISLA")){
            icon = L.divIcon({
                className:"icon-isla",
                html:"<div>🌐</div>",
                iconSize:[32,32],
                iconAnchor:[16,16]
            });
        }
        else{
            let col = pt.promedio >= 4 ? "red":"green";
            icon = L.divIcon({
                className:"icon-round",
                html:`<div style="background:${col};"></div>`,
                iconSize:[14,14],
                iconAnchor:[7,7]
            });
        }

        const popup = `
            <div class='popup-title'>${pt.nombre}</div>
            <div class='popup-row'><b>ATM:</b> ${pt.atm}</div>
            <div class='popup-row'><b>División:</b> ${pt.division}</div>
            <div class='popup-row'><b>Tipo:</b> ${pt.tipo}</div>
            <div class='popup-row'><b>Ubicación:</b> ${pt.ubicacion}</div>
            <div class='popup-row'><b>Departamento:</b> ${pt.departamento}</div>
            <div class='popup-row'><b>Provincia:</b> ${pt.provincia}</div>
            <div class='popup-row'><b>Distrito:</b> ${pt.distrito}</div>
            <div class='popup-row'><b>Promedio:</b> ${pt.promedio}</div>
            <div class='popup-row'><b>Dirección:</b> ${pt.direccion}</div>
        `;

        const m = L.marker([pt.lat, pt.lon], {icon:icon}).bindPopup(popup);
        markers.addLayer(m);

        heatPts.push([pt.lat, pt.lon, Math.max(1, pt.promedio)]);
        bounds.push([pt.lat, pt.lon]);
    });

    heat.setLatLngs(heatPts);

    if(bounds.length===1) map.setView(bounds[0], 15);
    else if(bounds.length>1) map.fitBounds(bounds, {padding:[20,20]});

    if(!chkHeat.checked){
        map.removeLayer(heat);
    } else {
        heat.addTo(map);
    }
}

// inicial
fetchPoints();

</script>

</body>
</html>
"""


