# ============================================================
#   BACKEND COMPLETO: LOGIN + SELECTOR + 3 CAPAS
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
# 2. CARGA DE EXCELS
# ============================================================
BASE_DIR = os.path.dirname(__file__)

# ---------------- Excel ISLAS (NO SE TOCA) -----------------
excel_islas = os.path.join(BASE_DIR, "data", "Mapa Geoespacial ATM (1) (1).xlsx")
raw_islas = pd.read_excel(excel_islas)

def normalize(s):
    s = str(s)
    s = unicodedata.normalize("NFKD", s)
    s = s.encode("ascii", "ignore").decode("utf-8")
    s = s.upper().strip()
    return re.sub(r"\s+", " ", s)

norm_islas = {normalize(c): c for c in raw_islas.columns}

def find_col(keys, mapper):
    for k in keys:
        for col_norm, col_real in mapper.items():
            if k in col_norm:
                return col_real
    return None

# columnas islas
COL_ATM = find_col(["ATM", "COD_ATM"], norm_islas)
COL_DEPT = find_col(["DEPARTAMENTO"], norm_islas)
COL_PROV = find_col(["PROVINCIA"], norm_islas)
COL_DIST = find_col(["DISTRITO"], norm_islas)
COL_LAT = find_col(["LATITUD"], norm_islas)
COL_LON = find_col(["LONGITUD"], norm_islas)
COL_TIPO = find_col(["TIPO"], norm_islas)
COL_UBIC = find_col(["UBICACION", "UBICACIÓN"], norm_islas)
PROM_COL = find_col(["PROMEDIO"], norm_islas)

if PROM_COL is None:
    raw_islas["PROM_FAKE"] = 0.0
    PROM_COL = "PROM_FAKE"

def clean_latlon(df, col_lat, col_lon):
    df[col_lat] = (
        df[col_lat]
        .astype(str)
        .str.replace(",", ".", regex=False)
        .str.replace(r"[^\d\.\-]", "", regex=True)
        .replace("", np.nan)
        .astype(float)
    )
    df[col_lon] = (
        df[col_lon]
        .astype(str)
        .str.replace(",", ".", regex=False)
        .str.replace(r"[^\d\.\-]", "", regex=True)
        .replace("", np.nan)
        .astype(float)
    )
    return df.dropna(subset=[col_lat, col_lon]).reset_index(drop=True)

df_islas = clean_latlon(raw_islas.copy(), COL_LAT, COL_LON)
df_islas[PROM_COL] = pd.to_numeric(df_islas[PROM_COL], errors="coerce").fillna(0)
df_islas[COL_UBIC] = df_islas[COL_UBIC].astype(str)

# ============================================================
# 2.1 OFICINAS.xlsx
# ============================================================
excel_ofi = os.path.join(BASE_DIR, "data", "OFICINAS.xlsx")
raw_ofi = pd.read_excel(excel_ofi)

# columnas fijas del usuario
col_ofi_code = "COD. OFIC."
col_ofi_name = "OFICINA"
col_ofi_div  = "DIVISION"
col_ofi_dept = "DEPARTAMENTO"
col_ofi_prov = "PROVINCIA"
col_ofi_dist = "DISTRITO"
col_ofi_lat  = "LATITUD"
col_ofi_lon  = "LONGITUD"
col_ofi_trx  = "TRX"

df_oficinas = pd.DataFrame()
df_oficinas[COL_ATM]  = raw_ofi[col_ofi_code].astype(str)
df_oficinas[COL_DEPT] = raw_ofi[col_ofi_dept].astype(str)
df_oficinas[COL_PROV] = raw_ofi[col_ofi_prov].astype(str)
df_oficinas[COL_DIST] = raw_ofi[col_ofi_dist].astype(str)
df_oficinas[COL_LAT]  = raw_ofi[col_ofi_lat]
df_oficinas[COL_LON]  = raw_ofi[col_ofi_lon]
df_oficinas[COL_DIV]  = raw_ofi[col_ofi_div].astype(str)
df_oficinas[COL_UBIC] = "OFICINA"
df_oficinas[COL_TIPO] = "OFICINA"

df_oficinas[PROM_COL] = pd.to_numeric(raw_ofi[col_ofi_trx], errors="coerce").fillna(0)
df_oficinas["NOMBRE"] = raw_ofi[col_ofi_name].astype(str)

df_oficinas = clean_latlon(df_oficinas, COL_LAT, COL_LON)

# ============================================================
# 2.2 AGENTES.xlsx
# ============================================================
excel_ag = os.path.join(BASE_DIR, "data", "AGENTES.xlsx")
raw_ag = pd.read_excel(excel_ag)

col_ag_terminal = "TERMINAL"
col_ag_nombre   = "COMERCIO"
col_ag_dept     = "DEPARTAMENTO"
col_ag_prov     = "PROVINCIA"
col_ag_dist     = "DISTRITO"
col_ag_lat      = "LATITUD"
col_ag_lon      = "LONGITUD"
col_ag_div      = "DIVISION"
col_ag_prom     = "PROMEDIO"

df_agentes = pd.DataFrame()
df_agentes[COL_ATM]  = raw_ag[col_ag_terminal].astype(str)
df_agentes[COL_DEPT] = raw_ag[col_ag_dept].astype(str)
df_agentes[COL_PROV] = raw_ag[col_ag_prov].astype(str)
df_agentes[COL_DIST] = raw_ag[col_ag_dist].astype(str)
df_agentes[COL_LAT]  = raw_ag[col_ag_lat]
df_agentes[COL_LON]  = raw_ag[col_ag_lon]
df_agentes[COL_DIV]  = raw_ag[col_ag_div].astype(str)

df_agentes[COL_UBIC] = "AGENTE"
df_agentes[COL_TIPO] = "AGENTE"

df_agentes[PROM_COL] = pd.to_numeric(raw_ag[col_ag_prom], errors="coerce").fillna(0)
df_agentes["NOMBRE"] = raw_ag[col_ag_nombre].astype(str)

df_agentes = clean_latlon(df_agentes, COL_LAT, COL_LON)

# ============================================================
# 3. FILTROS JERÁRQUICOS
# ============================================================
df_filtros = pd.concat(
    [
        df_islas[[COL_DEPT, COL_PROV, COL_DIST, COL_DIV]],
        df_oficinas[[COL_DEPT, COL_PROV, COL_DIST, COL_DIV]],
        df_agentes[[COL_DEPT, COL_PROV, COL_DIST, COL_DIV]],
    ],
    ignore_index=True,
)

DEPARTAMENTOS = sorted(df_filtros[COL_DEPT].dropna().unique())

PROVINCIAS_BY_DEPT = (
    df_filtros.groupby(COL_DEPT)[COL_PROV]
    .apply(lambda s: sorted(s.dropna().unique()))
    .to_dict()
)

DIST_BY_PROV = (
    df_filtros.groupby(COL_PROV)[COL_DIST]
    .apply(lambda s: sorted(s.dropna().unique()))
    .to_dict()
)

DIV_BY_DEPT = (
    df_filtros.groupby(COL_DEPT)[COL_DIV]
    .apply(lambda s: sorted(s.dropna().unique()))
    .to_dict()
)

DIV_BY_PROV = (
    df_filtros.groupby(COL_PROV)[COL_DIV]
    .apply(lambda s: sorted(s.dropna().unique()))
    .to_dict()
)

DIV_BY_DIST = (
    df_filtros.groupby(COL_DIST)[COL_DIV]
    .apply(lambda s: sorted(s.dropna().unique()))
    .to_dict()
)

DIVISIONES = sorted(df_filtros[COL_DIV].dropna().unique())


# ============================================================
# 4. FLASK + LOGIN
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
    background:url('{{ url_for('static', filename='bbva.png') }}')
               no-repeat center center fixed;
    background-size:cover;
    font-family:Arial,Helvetica,sans-serif;
}
.box{
    background:rgba(255,255,255,0.88);
    padding:30px 35px;
    border-radius:12px;
    box-shadow:0 8px 30px rgba(0,0,0,0.3);
    width:360px;
    text-align:center;
}
h2{color:#1464A5; margin:0 0 15px 0;}
input{
    width:100%; padding:10px; margin:8px 0;
    border-radius:8px; border:1px solid #ddd;
}
button{
    width:100%; padding:10px;
    background:#1464A5; color:white;
    border:none; border-radius:8px;
    font-weight:600; cursor:pointer;
}
.error{color:#c0392b; font-size:14px; margin-bottom:8px;}
.small{font-size:13px; color:#6b7a8a; margin-top:8px;}
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
SELECTOR_TEMPLATE = """
<!DOCTYPE html>
<html>
<head>
<meta charset="utf-8">
<title>Selector de Capas — BBVA</title>
<meta name="viewport" content="width=device-width, initial-scale=1">
<style>
body{
    margin:0; padding:40px 20px;
    font-family:Arial,Helvetica,sans-serif;
    background:#eef4fb;
}
h1{
    text-align:center;
    color:#072146;
}
.grid{
    margin-top:40px;
    display:flex;
    justify-content:center;
    gap:40px;
    flex-wrap:wrap;
}
.card{
    width:320px; height:260px;
    background:white;
    border-radius:20px;
    box-shadow:0 8px 26px rgba(0,0,0,0.15);
    cursor:pointer;
    display:flex;
    flex-direction:column;
    align-items:center;
    justify-content:flex-start;
    padding:16px 14px;
    transition:transform .18s ease, box-shadow .18s ease;
}
.card:hover{
    transform:translateY(-4px) scale(1.02);
    box-shadow:0 12px 32px rgba(0,0,0,0.25);
}
.card img{
    width:100%;
    height:170px;
    object-fit:cover;
    border-radius:14px;
}
.card-title{
    margin-top:12px;
    font-size:18px;
    font-weight:700;
    color:#072146;
    display:flex;
    align-items:center;
    gap:8px;
}
.card-title span.icon{
    font-size:22px;
}
</style>
</head>
<body>

<h1>Seleccione la capa</h1>

<div class="grid">

  <div class="card" onclick="location.href='/mapa/oficinas'">
    <img src="{{ url_for('static', filename='oficina.png') }}" alt="Oficinas BBVA">
    <div class="card-title"><span class="icon">🏦</span>Oficinas</div>
  </div>

  <div class="card" onclick="location.href='/mapa/islas'">
    <img src="{{ url_for('static', filename='isla.png') }}" alt="Islas BBVA">
    <div class="card-title"><span class="icon">🌐</span>Islas</div>
  </div>

  <div class="card" onclick="location.href='/mapa/agentes'">
    <img src="{{ url_for('static', filename='agente.png') }}" alt="Agentes BBVA">
    <div class="card-title"><span class="icon">🧍</span>Agentes</div>
  </div>

</div>

</body>
</html>
"""

@app.route("/selector")
@login_required
def selector():
    return render_template_string(SELECTOR_TEMPLATE)

# ============================================================
# 6. RUTA /mapa/<tipo>
# ============================================================
@app.route("/mapa/<tipo>")
@login_required
def mapa_tipo(tipo):
    if tipo not in ["oficinas", "islas", "agentes"]:
        return "No existe esa capa", 404

    if tipo == "oficinas" and not df_oficinas.empty:
        df_center = df_oficinas
    elif tipo == "agentes" and not df_agentes.empty:
        df_center = df_agentes
    else:
        df_center = df_islas

    initial_center = df_center[[COL_LAT, COL_LON]].mean().tolist()

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
# 7. API /api/points  (3 CAPAS)
# ============================================================
@app.route("/api/points")
@login_required
def api_points():
    tipo_mapa = request.args.get("tipo", "").lower()

    # Elegimos el dataframe según capa
    if tipo_mapa == "oficinas":
        dff = df_oficinas.copy()
    elif tipo_mapa == "agentes":
        dff = df_agentes.copy()
    else:  # islas
        dff = df_islas.copy()

    dpto = request.args.get("departamento", "").upper().strip()
    prov = request.args.get("provincia", "").upper().strip()
    dist = request.args.get("distrito", "").upper().strip()
    divi = request.args.get("division", "").upper().strip()

    # Normalizar texto
    for col in [COL_DEPT, COL_PROV, COL_DIST, COL_DIV, COL_UBIC, COL_TIPO]:
        if col in dff.columns:
            dff[col] = dff[col].astype(str).str.upper().str.strip()

    # Filtros jerárquicos
    if dpto and COL_DEPT in dff.columns:
        dff = dff[dff[COL_DEPT] == dpto]
    if prov and COL_PROV in dff.columns:
        dff = dff[dff[COL_PROV] == prov]
    if dist and COL_DIST in dff.columns:
        dff = dff[dff[COL_DIST] == dist]
    if divi and COL_DIV in dff.columns:
        dff = dff[dff[COL_DIV] == divi]

    dff_layer = dff

    # ---- Resumen ----
    total_atms = int(len(dff_layer))
    if total_atms > 0 and PROM_COL in dff_layer.columns:
        promedio_total = float(dff_layer[PROM_COL].mean())
    else:
        promedio_total = 0.0

    total_oficinas = (
        int(dff_layer[COL_UBIC].str.contains("OFICINA", na=False).sum())
        if COL_UBIC in dff_layer.columns
        else 0
    )
    total_islas = (
        int(dff_layer[COL_UBIC].str.contains("ISLA", na=False).sum())
        if COL_UBIC in dff_layer.columns
        else 0
    )

    total_disp = (
        int(dff_layer[COL_TIPO].str.contains("DISPENSADOR", na=False).sum())
        if COL_TIPO in dff_layer.columns
        else 0
    )
    total_mon = (
        int(dff_layer[COL_TIPO].str.contains("MONEDERO", na=False).sum())
        if COL_TIPO in dff_layer.columns
        else 0
    )
    total_rec = (
        int(dff_layer[COL_TIPO].str.contains("RECICLADOR", na=False).sum())
        if COL_TIPO in dff_layer.columns
        else 0
    )

    # ---- Construcción de puntos ----
    puntos = []
    for _, r in dff_layer.iterrows():
        # nombre según capa
        if "NOMBRE" in r.index and str(r.get("NOMBRE", "")).strip():
            nombre = str(r.get("NOMBRE", "")).strip()
        else:
            nombre = str(r.get(COL_ATM, ""))

        lat_v = float(r[COL_LAT])
        lon_v = float(r[COL_LON])

        puntos.append(
            {
                "lat": lat_v,
                "lon": lon_v,
                "atm": str(r.get(COL_ATM, "")),
                "nombre": nombre,
                "promedio": float(r.get(PROM_COL, 0.0))
                if PROM_COL in r.index
                else 0.0,
                "division": str(r.get(COL_DIV, "")),
                "tipo": str(r.get(COL_TIPO, "")),
                "ubicacion": str(r.get(COL_UBIC, "")),
                "departamento": str(r.get(COL_DEPT, "")),
                "provincia": str(r.get(COL_PROV, "")),
                "distrito": str(r.get(COL_DIST, "")),
                "direccion": get_address(lat_v, lon_v),
            }
        )

    return jsonify(
        {
            "puntos": puntos,
            "total_atms": total_atms,
            "total_oficinas": total_oficinas,
            "total_islas": total_islas,
            "total_disp": total_disp,
            "total_mon": total_mon,
            "total_rec": total_rec,
            "promedio_total": promedio_total,
        }
    )

# ============================================================
# 8. TEMPLATE MAPA (MISMO DISEÑO, SIN POPUP EXTRA)
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
<script src="https://unpkg.com/leaflet.markercluster@1.5.3/dist/MarkerCluster.js"></script>
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
  panelResumenTitulo.textContent = "Resumen — Islas";
  resTituloBloque.textContent    = "ATMs totales (capa islas)";
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