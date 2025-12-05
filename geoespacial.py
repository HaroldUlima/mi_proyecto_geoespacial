# geoespacial.py
import os
import re
import unicodedata
import json
import pandas as pd
import numpy as np
from flask import Flask, render_template_string, request, jsonify


# -------------------------
# Cache de direcciones precalculadas
# -------------------------
CACHE_FILE = "address_cache.json"
if os.path.exists(CACHE_FILE):
    with open(CACHE_FILE, "r", encoding="utf-8") as f:
        address_cache = json.load(f)
else:
    address_cache = {}

def get_address(lat, lon):
    # Clave con 6 decimales para consistencia con cache
    try:
        key = f"{float(lat):.6f},{float(lon):.6f}"
    except Exception:
        key = f"{lat},{lon}"
    return address_cache.get(key, "Dirección no encontrada")


# -------------------------
# Cargar Excel desde carpeta data/
# -------------------------
BASE_DIR = os.path.dirname(__file__)
excel_path = os.path.join(BASE_DIR, "data", "Mapa Geoespacial ATM (1) (1).xlsx")

if not os.path.exists(excel_path):
    raise FileNotFoundError(f"No encontré el archivo Excel en {excel_path}")

print("✅ Usando archivo Excel:", excel_path)


# -------------------------
# Normalizar columnas
# -------------------------
def normalize_col(s):
    s = str(s)
    s = unicodedata.normalize("NFKD", s)
    s = s.encode("ascii", "ignore").decode("utf-8")
    s = s.upper().strip()
    s = re.sub(r"[^A-Z0-9 ]+", " ", s)
    s = re.sub(r"\s+", " ", s).strip()
    return s

raw = pd.read_excel(excel_path)
norm_map = {normalize_col(c): c for c in raw.columns}

def find_col_by_keywords(keywords):
    for k in norm_map:
        for kw in keywords:
            if kw in k:
                return norm_map[k]
    return None


# Detectar columnas principales
COL_ATM = find_col_by_keywords(["ATM"]) or "ATM"
COL_NAME = find_col_by_keywords(["NOMBRE","CAJERO","NOMBRE CAJERO","NOMBRE_CAJERO"]) or None
COL_DEPT = find_col_by_keywords(["DEPARTAMENTO"]) or "DEPARTAMENTO"
COL_PROV = find_col_by_keywords(["PROVINCIA"]) or "PROVINCIA"
COL_DIST = find_col_by_keywords(["DISTRITO"]) or "DISTRITO"
COL_LAT = find_col_by_keywords(["LATITUD","LAT"]) or "LAT"
COL_LON = find_col_by_keywords(["LONGITUD","LON","LONG"]) or "LON"
PROM_COL = find_col_by_keywords(["PROMEDIO","PROM"]) or None
COL_DIV = find_col_by_keywords(["DIVISION","DIVISIÓN"]) or "DIVISION"
COL_TIPO = find_col_by_keywords(["TIPO"]) or "TIPO"
COL_UBIC = find_col_by_keywords(["UBICACION","UBICACIÓN","UBICACION_INTERNA","UBICACIÓN_INTERNA"]) or "UBICACION_INTERNA"
COL_DIR = find_col_by_keywords(["DIRECCION","DIRECCIÓN"]) or None

if COL_NAME:
    print("✅ Columna Nombre detectada:", COL_NAME)
else:
    print("⚠️ No se detectó columna de nombre. Se usará ATM.")


# Asegurar columnas
for c in [COL_ATM, COL_DEPT, COL_PROV, COL_DIST, COL_LAT, COL_LON, PROM_COL, COL_DIV, COL_TIPO, COL_UBIC]:
    if c and c not in raw.columns:
        if c in (COL_LAT, COL_LON):
            raise KeyError(f"Falta columna obligatoria: {c}")
        raw[c] = ""

if COL_DIR is None:
    raw["DIRECCION_API"] = ""
    COL_DIR = "DIRECCION_API"
else:
    raw[COL_DIR] = raw[COL_DIR].astype(str)

if PROM_COL is None:
    raw["PROMEDIO_FAKE"] = 0.0
    PROM_COL = "PROMEDIO_FAKE"


# -------------------------
# Limpieza coordenadas
# -------------------------
df = raw.copy()
df[COL_LAT] = df[COL_LAT].astype(str).str.replace(",", ".", regex=False).str.replace(r"[^\d\.\-]", "", regex=True).replace("", np.nan).astype(float)
df[COL_LON] = df[COL_LON].astype(str).str.replace(",", ".", regex=False).str.replace(r"[^\d\.\-]", "", regex=True).replace("", np.nan).astype(float)

df = df.dropna(subset=[COL_LAT, COL_LON]).reset_index(drop=True)
df[PROM_COL] = pd.to_numeric(df[PROM_COL], errors="coerce").fillna(0.0)

print(f"📊 Registros válidos: {len(df)}")


# -------------------------
# Precompute combos
# -------------------------
DEPARTAMENTOS = sorted(df[COL_DEPT].dropna().astype(str).unique().tolist())
PROVINCIAS_ALL = df.groupby(COL_DEPT)[COL_PROV].apply(lambda s: sorted(s.dropna().astype(str).unique().tolist())).to_dict()
DISTRITOS_BY_PROV = df.groupby(COL_PROV)[COL_DIST].apply(lambda s: sorted(s.dropna().astype(str).unique().tolist())).to_dict()
DIST_BY_DEPT = df.groupby(COL_DEPT)[COL_DIST].apply(lambda s: sorted(s.dropna().astype(str).unique().tolist())).to_dict()

# 🔥 Nuevo: lista de divisiones
DIVISIONES = sorted(df[COL_DIV].dropna().astype(str).unique().tolist())


# -------------------------
# Flask
# -------------------------
from functools import wraps
from flask import Flask, redirect, url_for, session

app = Flask(__name__)

# Evitar caché después de logout
@app.after_request
def add_header(response):
    response.headers["Cache-Control"] = "no-store, no-cache, must-revalidate, max-age=0"
    response.headers["Pragma"] = "no-cache"
    response.headers["Expires"] = "0"
    return response

# Seguridad: login
app.secret_key = os.getenv("SECRET_KEY", "fallback_local")

APP_USER = os.getenv("APP_USERNAME")
APP_PASS = os.getenv("APP_PASSWORD")

if not APP_USER or not APP_PASS:
    print("⚠️ APP_USERNAME o APP_PASSWORD no configurados en Render")


# -------------------------
# Template Login
# -------------------------
LOGIN_TEMPLATE = """
<!DOCTYPE html>
<html>
<head>
    <meta charset="utf-8">
    <title>Acceso Seguro — BBVA</title>
    <meta name="viewport" content="width=device-width, initial-scale=1">
    <style>
        body{
            margin:0;
            padding:0;
            height:100vh;
            width:100%;
            display:flex;
            align-items:center;
            justify-content:center;
            background: url('{{ url_for('static', filename='bbva.png') }}') no-repeat center center fixed;
            background-size: cover;
            font-family: Arial, Helvetica, sans-serif;
        }
        .box{
            background: rgba(255,255,255,0.85);
            padding: 30px 35px;
            border-radius: 12px;
            box-shadow: 0 8px 30px rgba(0,0,0,0.3);
            width: 360px;
            text-align: center;
        }
        h2{
            color:#1464A5;
            margin-top:0;
            margin-bottom:15px;
        }
        input{
            width:100%;
            padding:10px;
            margin:8px 0;
            border:1px solid #ddd;
            border-radius:8px;
        }
        button{
            background:#1464A5;
            color:white;
            border:none;
            padding:10px;
            border-radius:8px;
            width:100%;
            cursor:pointer;
            font-weight:600;
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


# -------------------------
# Login Required Decorator
# -------------------------
def login_required(f):
    @wraps(f)
    def wrapped(*args, **kwargs):
        if session.get("user") != APP_USER:
            return redirect(url_for("login"))
        return f(*args, **kwargs)
    return wrapped


# -------------------------
# Login Route
# -------------------------
from flask import render_template_string, request

@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        u = request.form.get("username", "")
        p = request.form.get("password", "")
        if u == APP_USER and p == APP_PASS:
            session.clear()
            session["user"] = u
            session.permanent = False
            return redirect(url_for("index"))
        return render_template_string(LOGIN_TEMPLATE, error="Usuario o contraseña incorrectos")
    return render_template_string(LOGIN_TEMPLATE)


# -------------------------
# Logout Route
# -------------------------
@app.route("/logout")
def logout():
    session.clear()
    resp = redirect(url_for("login"))
    resp.set_cookie("session", "", expires=0)
    return resp


# -------------------------
# Template HTML/JS (Dashboard BBVA)
# -------------------------

TEMPLATE = """
<!doctype html>
<html>
<head>
<meta charset="utf-8">
<title>Dashboard Geoespacial — ATMs</title>
<meta name="viewport" content="width=device-width, initial-scale=1.0">

<link rel="stylesheet" href="https://unpkg.com/leaflet@1.9.4/dist/leaflet.css"/>
<link rel="stylesheet" href="https://unpkg.com/leaflet.markercluster@1.5.3/dist/MarkerCluster.css"/>
<link rel="stylesheet" href="https://unpkg.com/leaflet.markercluster@1.5.3/dist/MarkerCluster.Default.css"/>

<style>
:root { --bbva-blue: #1464A5; --bbva-dark: #072146; --card: #ffffff; --muted: #6b7a8a; }
html,body { height:100%; margin:0; font-family: Inter, 'Segoe UI', Tahoma, Arial, sans-serif; background: #eef4fb; color:var(--bbva-dark); }

header{
  background:#003366;
  color:white;
  padding:14px 20px;
  display:flex;
  align-items:center;
  position:relative;
  height:70px;
}
header h1{ flex:1; text-align:center; font-size:2.3rem; margin:0; }

.topbar{ padding:16px 20px; display:flex; align-items:center; gap:16px; }
.controls{
  display:flex; gap:10px; align-items:center; flex-wrap:wrap;
  background:var(--card); padding:12px; border-radius:12px;
  box-shadow:0 6px 18px rgba(10,30,70,0.06);
  width:100%;
}
.controls label{ font-size:13px; color:var(--muted); display:flex; gap:8px; align-items:center; }
select{ padding:8px 10px; border-radius:8px; border:1px solid #e6eef8; }

.main{ display:flex; gap:18px; padding:0 20px 20px 20px; }

#map{
  flex:1;
  height:74vh;
  border-radius:12px;
  box-shadow:0 10px 30px rgba(12,35,75,0.08);
  border:1px solid rgba(10,30,60,0.04);
}

.side{ width:320px; }
.card{
  background:white; padding:14px; border-radius:12px;
  box-shadow:0 6px 20px rgba(10,30,75,0.06); margin-bottom:12px;
}

</style>
</head>

<body>

<header>
  <h1>Mapa de ATMs — BBVA</h1>
  <a href="/logout" style="color:white; text-decoration:none;
     background:#1464A5; padding:8px 16px; border-radius:8px;
     font-weight:600; font-size:16px; position:absolute; right:20px;">
     Cerrar sesión
  </a>
</header>

<div class="topbar">
  <div class="controls">

    <!-- EXISTENTES -->
    <label>Departamento:
      <select id="selDepartamento">
        <option value="">-- Todos --</option>
        {% for d in departamentos %}<option value="{{d}}">{{d}}</option>{% endfor %}
      </select>
    </label>

    <label>Provincia:
      <select id="selProvincia"><option value="">-- Todas --</option></select>
    </label>

    <label>Distrito:
      <select id="selDistrito"><option value="">-- Todos --</option></select>
    </label>

    <!-- 🔵 NUEVO FILTRO DE DIVISIÓN -->
    <label>División:
      <select id="selDivision"><option value="">-- Todas --</option></select>
    </label>
    <!-- 🔵 FIN NUEVO -->

    <label style="margin-left:10px;">
      <input type="checkbox" id="chkHeat" checked> Mostrar Heatmap
    </label>

    <div style="flex:1"></div>
    <div class="muted">Mostrando <span id="infoCount">--</span> ATMs</div>

  </div>
</div>

<script>
const PROVINCIAS_ALL = {{ provincias_all|tojson }};
const DISTRITOS_BY_PROV = {{ distritos_by_prov|tojson }};
const DIST_BY_DEPT = {{ dist_by_dept|tojson }};
const DIVISIONES = {{ divisiones|tojson }};   <!-- NUEVO -->

const INITIAL_CENTER = [{{ initial_center[0] }}, {{ initial_center[1] }}];
const INITIAL_ZOOM = {{ initial_zoom }};

const map = L.map('map').setView(INITIAL_CENTER, INITIAL_ZOOM);
L.tileLayer('https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png',{
  maxZoom: 19,
  attribution: '&copy; OpenStreetMap contributors'
}).addTo(map);

const markersLayer = L.markerClusterGroup({ chunkedLoading:true });
const heatLayer = L.heatLayer([], {radius:25, blur:20, maxZoom:17});
markersLayer.addTo(map);
heatLayer.addTo(map);

const selDept = document.getElementById('selDepartamento');
const selProv = document.getElementById('selProvincia');
const selDist = document.getElementById('selDistrito');
const selDiv = document.getElementById('selDivision');   // NUEVO

const chkHeat = document.getElementById('chkHeat');
const infoSpan = document.getElementById('infoCount');
const promTotalEl = document.getElementById('promTotal');

const oficinaTotalEl = document.getElementById('oficinaTotal');
const oficinaDispEl = document.getElementById('oficinaDisp');
const oficinaMonEl = document.getElementById('oficinaMon');
const oficinaRecEl = document.getElementById('oficinaRec');

const islaTotalEl = document.getElementById('islaTotal');
const islaDispEl = document.getElementById('islaDisp');
const islaMonEl = document.getElementById('islaMon');
const islaRecEl = document.getElementById('islaRec');


/* -------------------------
   FUNCIONES SELECTORES
-------------------------- */

function populateProvincias(dept){
  selProv.innerHTML = '<option value="">-- Todas --</option>';
  if (dept && PROVINCIAS_ALL[dept]){
    PROVINCIAS_ALL[dept].forEach(p=>{
      selProv.innerHTML += `<option value="${p}">${p}</option>`;
    });
  }
  populateDistritos(dept, "");
}

function populateDistritos(dept, prov){
  selDist.innerHTML = '<option value="">-- Todos --</option>';

  if (prov && DISTRITOS_BY_PROV[prov]){
    DISTRITOS_BY_PROV[prov].forEach(d=>{
      selDist.innerHTML += `<option value="${d}">${d}</option>`;
    });

  } else if (dept && DIST_BY_DEPT[dept]){
    DIST_BY_DEPT[dept].forEach(d=>{
      selDist.innerHTML += `<option value="${d}">${d}</option>`;
    });
  }
}

/* -------------------------
   NUEVO: Filtro División
-------------------------- */

function populateDivisiones(){
  selDiv.innerHTML = '<option value="">-- Todas --</option>';
  DIVISIONES.forEach(div=>{
    selDiv.innerHTML += `<option value="${div}">${div}</option>`;
  });
}


/* -------------------------
    ÍCONOS
-------------------------- */

function determineHeatColor(points){
  if(points.length===0) return "green";
  return points.length >= 4 ? "red" : "green";
}

function getCustomIcon(ubicacion, promedio){
  const up = (ubicacion || "").toUpperCase();

  if(up.includes("OFICINA")){
    return L.divIcon({
      html: "<div style='font-size:35px;'>🏦</div>",
      iconSize:[35,35], iconAnchor:[18,18]
    });
  }

  if(up.includes("ISLA")){
    return L.divIcon({
      html: "<div style='font-size:35px; color:deepskyblue;'>🌐</div>",
      iconSize:[35,35], iconAnchor:[18,18]
    });
  }

  let color = (promedio >= 4) ? "red" : "green";
  return L.divIcon({
    html:`<div style="background:${color}; width:14px; height:14px;
                     border-radius:50%; border:2px solid white;"></div>`,
    iconSize:[14,14], iconAnchor:[7,7]
  });
}


/* -------------------------
   PETICIÓN API + RENDER
-------------------------- */

async function fetchAndRender(){

  const params = new URLSearchParams();

  if(selDept.value) params.append('departamento', selDept.value);
  if(selProv.value) params.append('provincia', selProv.value);
  if(selDist.value) params.append('distrito', selDist.value);
  if(selDiv.value) params.append('division', selDiv.value);  // NUEVO

  infoSpan.textContent = '...';

  try{
    const res = await fetch('/api/points?' + params.toString());
    const data = await res.json();

    markersLayer.clearLayers();
    heatLayer.setLatLngs([]);

    let markersToAdd = [];
    let heatPoints = [];
    let sumProm = 0;

    let oficinaTotal=0, oficinaDisp=0, oficinaMon=0, oficinaRec=0;
    let islaTotal=0, islaDisp=0, islaMon=0, islaRec=0;

    const bounds = [];

    data.forEach(item=>{

      const popup = `
        <div class="popup-card">
          <div><b>Nombre:</b> ${item.nombre}</div>
          <div><b>ATM:</b> ${item.atm}</div>
          <div><b>Dirección:</b> ${item.direccion}</div>
          <hr>
          <div><b>División:</b> ${item.division}</div>
          <div><b>Tipo:</b> ${item.tipo}</div>
          <div><b>Ubicación:</b> ${item.ubicacion}</div>
          <hr>
          <div><b>Promedio:</b> ${item.promedio}</div>
        </div>
      `;

      const icon = getCustomIcon(item.ubicacion, item.promedio);
      const m = L.marker([item.lat, item.lon], {icon}).bindPopup(popup);

      markersToAdd.push(m);
      heatPoints.push([item.lat, item.lon, Math.max(1, item.promedio || 1)]);
      sumProm += item.promedio || 0;

      bounds.push([item.lat, item.lon]);

      const tipo = (item.tipo||"").toUpperCase();
      const ubic = (item.ubicacion||"").toUpperCase();

      if(ubic.includes("OFICINA")){
        oficinaTotal++;
        if(tipo.includes("DISPENSADOR")) oficinaDisp++;
        if(tipo.includes("MONEDERO")) oficinaMon++;
        if(tipo.includes("RECICLADOR")) oficinaRec++;
      }
      if(ubic.includes("ISLA")){
        islaTotal++;
        if(tipo.includes("DISPENSADOR")) islaDisp++;
        if(tipo.includes("MONEDERO")) islaMon++;
        if(tipo.includes("RECICLADOR")) islaRec++;
      }
    });

    if(markersToAdd.length>0) markersLayer.addLayers(markersToAdd);

    if(bounds.length===1) map.setView(bounds[0], 14);
    else if(bounds.length>1) map.fitBounds(bounds, {padding:[30,30]});
    else map.setView(INITIAL_CENTER, INITIAL_ZOOM);

    let gradient = determineHeatColor(data)==="red"
      ? {0.1:'pink',0.3:'red',0.6:'darkred'}
      : {0.1:'lightgreen',0.3:'green',0.6:'darkgreen'};

    heatLayer.setOptions({gradient});
    heatLayer.setLatLngs(heatPoints);

    if(chkHeat.checked){
      if(!map.hasLayer(heatLayer)) map.addLayer(heatLayer);
    } else {
      if(map.hasLayer(heatLayer)) map.removeLayer(heatLayer);
    }

    infoSpan.textContent = data.length.toLocaleString();
    promTotalEl.textContent = Math.round(sumProm).toLocaleString();

    oficinaTotalEl.textContent = oficinaTotal;
    oficinaDispEl.textContent = oficinaDisp;
    oficinaMonEl.textContent = oficinaMon;
    oficinaRecEl.textContent = oficinaRec;

    islaTotalEl.textContent = islaTotal;
    islaDispEl.textContent = islaDisp;
    islaMonEl.textContent = islaMon;
    islaRecEl.textContent = islaRec;

  }catch(e){
    console.error(e);
    infoSpan.textContent = "Error";
  }
}


/* -------------------------
   EVENTOS
-------------------------- */

selDept.addEventListener('change', ()=>{
  populateProvincias(selDept.value);
  populateDistritos(selDept.value, selProv.value);
  fetchAndRender();
});

selProv.addEventListener('change', ()=>{
  populateDistritos(selDept.value, selProv.value);
  fetchAndRender();
});

selDist.addEventListener('change', fetchAndRender);
selDiv.addEventListener('change', fetchAndRender);   // NUEVO
chkHeat.addEventListener('change', fetchAndRender);


/* -------------------------
   INICIALIZAR
-------------------------- */
populateProvincias("");
populateDistritos("", "");
populateDivisiones();   // NUEVO
fetchAndRender();

</script>
</body>
</html>
"""

# -------------------------
# API de puntos
# -------------------------
@app.route("/api/points")
@login_required
def api_points():

    departamento = request.args.get("departamento", "").strip().upper()
    provincia     = request.args.get("provincia", "").strip().upper()
    distrito      = request.args.get("distrito", "").strip().upper()
    division      = request.args.get("division", "").strip().upper()   # NUEVO

    df_filtered = df.copy()

    # Normalizar columnas para filtrado
    df_filtered[COL_DEPT] = df_filtered[COL_DEPT].astype(str).str.upper().str.strip()
    df_filtered[COL_PROV] = df_filtered[COL_PROV].astype(str).str.upper().str.strip()
    df_filtered[COL_DIST] = df_filtered[COL_DIST].astype(str).str.upper().str.strip()
    df_filtered[COL_DIV]  = df_filtered[COL_DIV].astype(str).str.upper().str.strip()   # NUEVO

    # -------------------------
    # Aplicar filtros
    # -------------------------
    if departamento:
        df_filtered = df_filtered[df_filtered[COL_DEPT] == departamento]

    if provincia:
        df_filtered = df_filtered[df_filtered[COL_PROV] == provincia]

    if distrito:
        df_filtered = df_filtered[df_filtered[COL_DIST] == distrito]

    if division:                          # NUEVO
        df_filtered = df_filtered[df_filtered[COL_DIV] == division]

    # -------------------------
    # Construir respuesta
    # -------------------------
    points = []

    for _, r in df_filtered.iterrows():

        nombre_val = ""
        if COL_NAME and COL_NAME in r.index:
            nombre_val = str(r.get(COL_NAME, "")).strip()

        if not nombre_val:
            nombre_val = str(r.get(COL_ATM, ""))

        lat_v = float(r[COL_LAT])
        lon_v = float(r[COL_LON])

        points.append({
            "lat": lat_v,
            "lon": lon_v,
            "atm": str(r.get(COL_ATM, "")),
            "nombre": nombre_val,
            "promedio": float(r.get(PROM_COL, 0.0)),
            "division": str(r.get(COL_DIV, "")),        # NUEVO
            "tipo": str(r.get(COL_TIPO, "")),
            "ubicacion": str(r.get(COL_UBIC, "")),
            "provincia": str(r.get(COL_PROV, "")),
            "distrito": str(r.get(COL_DIST, "")),
            "departamento": str(r.get(COL_DEPT, "")),
            "direccion": get_address(lat_v, lon_v)     # Cache de dirección
        })

    return jsonify(points)

# ----------------------------------------
# Lista de divisiones para el nuevo filtro
# ----------------------------------------
DIVISIONES = sorted(
    df[COL_DIV].dropna().astype(str).unique().tolist()
)

# -------------------------
# Página principal
# -------------------------
@app.route("/")
@login_required
def index():

    initial_center = df[[COL_LAT, COL_LON]].mean().tolist() if not df.empty else [-9.19, -75.0152]
    initial_zoom = 6

    return render_template_string(
        TEMPLATE,
        departamentos = DEPARTAMENTOS,
        provincias_all = PROVINCIAS_ALL,
        distritos_by_prov = DISTRITOS_BY_PROV,
        dist_by_dept = DIST_BY_DEPT,

        divisiones = DIVISIONES,   # 🔵 NUEVO: lista enviada al template

        initial_center = initial_center,
        initial_zoom = initial_zoom
    )

# FIN DEL ARCHIVO
# -----------------------------------------
# (Si deseas ejecutarlo localmente descomenta)
# -----------------------------------------
# if __name__ == "__main__":
#     app.run(host="0.0.0.0", port=5000, debug=True)