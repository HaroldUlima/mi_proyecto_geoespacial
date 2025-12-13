# ============================================================
#   BACKEND COMPLETO + LOGIN + SELECTOR
#   CAPAS: ISLAS (ATMs) + AGENTES + OFICINAS + INTEGRAL
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

# ============================================
# RECOMENDACIONES – CARGA BÁSICA
# ============================================
import pandas as pd

try:
    recomendaciones = pd.read_csv("data/recomendaciones.csv")
except Exception as e:
    print("⚠ No se pudo cargar recomendaciones.csv:", e)
    recomendaciones = pd.DataFrame()

# ============================================================
# NUEVO — Cargar base de clientes
# ============================================================

df_clientes = pd.read_csv("data/clientes_huanuco_v6.csv")

# Filtrar solo filas válidas
df_clientes = df_clientes[
    df_clientes["latitud"].notnull() &
    df_clientes["longitud"].notnull()
]

SEGMENTOS_CLIENTES = sorted(df_clientes["segmento"].dropna().astype(str).unique().tolist())

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
# 2. CARGAR EXCEL PRINCIPAL (ISLAS / ATMs)
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


# ---------------- Detectar columnas principales (ISLAS) ----------------
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
for c in [
    COL_ATM,
    COL_DEPT,
    COL_PROV,
    COL_DIST,
    COL_LAT,
    COL_LON,
    COL_DIV,
    COL_TIPO,
    COL_UBIC,
    PROM_COL,
]:
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
# 2B. CARGAR EXCEL DE AGENTES
# ============================================================
excel_agentes = os.path.join(BASE_DIR, "data", "AGENTES.xlsx")
if not os.path.exists(excel_agentes):
    raise FileNotFoundError("No encontré Excel de AGENTES.xlsx.")

raw_ag = pd.read_excel(excel_agentes)

norm_map_ag = {normalize_col(c): c for c in raw_ag.columns}


def find_col_ag(keys):
    for norm, orig in norm_map_ag.items():
        for k in keys:
            if k in norm:
                return orig
    return None


COLA_ID = find_col_ag(["TERMINAL", "ID"]) or "TERMINAL"
COLA_COM = find_col_ag(["COMERCIO"]) or "COMERCIO"
COLA_DEPT = find_col_ag(["DEPARTAMENTO"]) or "DEPARTAMENTO"
COLA_PROV = find_col_ag(["PROVINCIA"]) or "PROVINCIA"
COLA_DIST = find_col_ag(["DISTRITO"]) or "DISTRITO"
COLA_LAT = find_col_ag(["LATITUD", "LAT"]) or "LATITUD"
COLA_LON = find_col_ag(["LONGITUD", "LON"]) or "LONGITUD"
COLA_DIV = find_col_ag(["DIVISION", "DIVISIÓN"]) or "DIVISION"
COLA_DIR = find_col_ag(["DIRECCION", "DIRECCIÓN"]) or "DIRECCION"
COLA_CAPA = find_col_ag(["CAPA"]) or "CAPA"
COLA_TRX_OCT = find_col_ag(["TRXS OCTUBRE", "TRX OCTUBRE"]) or None
COLA_TRX_NOV = find_col_ag(["TRXS NOV", "TRXS NOVIEMBRE"]) or None
PROMA_COL = find_col_ag(["PROMEDIO", "PROM"]) or None

# Si no hay promedio, creamos columna fake
if PROMA_COL is None:
    raw_ag["PROM_FAKE"] = 0.0
    PROMA_COL = "PROM_FAKE"

# Limpieza de coordenadas agentes
raw_ag[COLA_LAT] = (
    raw_ag[COLA_LAT]
    .astype(str)
    .str.replace(",", ".", regex=False)
    .str.replace(r"[^\d\.\-]", "", regex=True)
    .replace("", np.nan)
    .astype(float)
)
raw_ag[COLA_LON] = (
    raw_ag[COLA_LON]
    .astype(str)
    .str.replace(",", ".", regex=False)
    .str.replace(r"[^\d\.\-]", "", regex=True)
    .replace("", np.nan)
    .astype(float)
)

df_agentes = raw_ag.dropna(subset=[COLA_LAT, COLA_LON]).reset_index(drop=True)
df_agentes[PROMA_COL] = pd.to_numeric(df_agentes[PROMA_COL], errors="coerce").fillna(0.0)
df_agentes[COLA_CAPA] = df_agentes[COLA_CAPA].astype(str).fillna("")


# ============================================================
# 2C. CARGAR EXCEL DE OFICINAS
# ============================================================
excel_oficinas = os.path.join(BASE_DIR, "data", "OFICINAS.xlsx")
if not os.path.exists(excel_oficinas):
    raise FileNotFoundError("No encontré Excel de OFICINAS.xlsx.")

raw_of = pd.read_excel(excel_oficinas)

norm_map_of = {normalize_col(c): c for c in raw_of.columns}


def find_col_of(keys):
    for norm, orig in norm_map_of.items():
        for k in keys:
            if k in norm:
                return orig
    return None


COLF_ID = find_col_of(["COD OFIC", "COD. OFIC", "COD_OFIC"]) or "COD OFIC."
COLF_NAME = find_col_of(["OFICINA"]) or "OFICINA"
COLF_DIV = find_col_of(["DIVISION", "DIVISIÓN"]) or "DIVISION"
COLF_DEPT = find_col_of(["DEPARTAMENTO"]) or "DEPARTAMENTO"
COLF_PROV = find_col_of(["PROVINCIA"]) or "PROVINCIA"
COLF_DIST = find_col_of(["DISTRITO"]) or "DISTRITO"
COLF_LAT = find_col_of(["LATITUD", "LAT"]) or "LATITUD"
COLF_LON = find_col_of(["LONGITUD", "LON"]) or "LONGITUD"
COLF_TRX = find_col_of(["TRX", "TRXS"]) or "TRX"

raw_of[COLF_LAT] = (
    raw_of[COLF_LAT]
    .astype(str)
    .str.replace(",", ".", regex=False)
    .str.replace(r"[^\d\.\-]", "", regex=True)
    .replace("", np.nan)
    .astype(float)
)
raw_of[COLF_LON] = (
    raw_of[COLF_LON]
    .astype(str)
    .str.replace(",", ".", regex=False)
    .str.replace(r"[^\d\.\-]", "", regex=True)
    .replace("", np.nan)
    .astype(float)
)

df_oficinas = raw_of.dropna(subset=[COLF_LAT, COLF_LON]).reset_index(drop=True)
df_oficinas[COLF_TRX] = pd.to_numeric(df_oficinas[COLF_TRX], errors="coerce").fillna(0.0)


# ============================================================
# 3. JERARQUÍA TOTAL UNIFICADA (CLIENTES + TODOS LOS CANALES)
# ============================================================

# ---- Helper para limpiar texto ----
def clean_str(x):
    return str(x).upper().strip() if pd.notnull(x) else ""

# ---- 1. Unir TODOS los dataframes que tienen geografía ----
geo_frames = []

# ISLAS (df)
geo_frames.append(
    df[[COL_DEPT, COL_PROV, COL_DIST]].rename(
        columns={COL_DEPT: "departamento", COL_PROV: "provincia", COL_DIST: "distrito"}
    )
)

# AGENTES (df_agentes)
geo_frames.append(
    df_agentes[[COLA_DEPT, COLA_PROV, COLA_DIST]].rename(
        columns={
            COLA_DEPT: "departamento",
            COLA_PROV: "provincia",
            COLA_DIST: "distrito",
        }
    )
)

# OFICINAS (df_oficinas)
geo_frames.append(
    df_oficinas[[COLF_DEPT, COLF_PROV, COLF_DIST]].rename(
        columns={
            COLF_DEPT: "departamento",
            COLF_PROV: "provincia",
            COLF_DIST: "distrito",
        }
    )
)

# CLIENTES (df_clientes)
geo_frames.append(
    df_clientes[["departamento", "provincia", "distrito"]]
)

# ---- 2. Concatenar TODA la geografía ----
geo_all = pd.concat(geo_frames, ignore_index=True)

# ---- 3. Limpiar ----
geo_all["departamento"] = geo_all["departamento"].apply(clean_str)
geo_all["provincia"] = geo_all["provincia"].apply(clean_str)
geo_all["distrito"] = geo_all["distrito"].apply(clean_str)

geo_all = geo_all.dropna()

# ---- 4. Departamentos únicos ----
DEPARTAMENTOS = sorted(geo_all["departamento"].unique())

# ---- 5. Provincias por departamento ----
PROVINCIAS_BY_DEPT = {}
for dep in DEPARTAMENTOS:
    provs = geo_all.loc[geo_all["departamento"] == dep, "provincia"].unique().tolist()
    provs_clean = sorted([p for p in provs if p])
    PROVINCIAS_BY_DEPT[dep] = provs_clean

# ---- 6. Distritos por provincia ----
DIST_BY_PROV = {}
provincias_unicas = sorted(geo_all["provincia"].unique())

for prov in provincias_unicas:
    dists = geo_all.loc[geo_all["provincia"] == prov, "distrito"].unique().tolist()
    dists_clean = sorted([d for d in dists if d])
    DIST_BY_PROV[prov] = dists_clean

# ============================================================
# UNIFICACIÓN DE DIVISIONES (Islas + Oficinas + Agentes)
# ============================================================

div_frames = []

# ISLAS
div_frames.append(
    df[[COL_DEPT, COL_PROV, COL_DIST, COL_DIV]].rename(
        columns={
            COL_DEPT: "departamento",
            COL_PROV: "provincia",
            COL_DIST: "distrito",
            COL_DIV:  "division"
        }
    )
)

# AGENTES
div_frames.append(
    df_agentes[[COLA_DEPT, COLA_PROV, COLA_DIST, COLA_DIV]].rename(
        columns={
            COLA_DEPT: "departamento",
            COLA_PROV: "provincia",
            COLA_DIST: "distrito",
            COLA_DIV:  "division"
        }
    )
)

# OFICINAS
div_frames.append(
    df_oficinas[[COLF_DEPT, COLF_PROV, COLF_DIST, COLF_DIV]].rename(
        columns={
            COLF_DEPT: "departamento",
            COLF_PROV: "provincia",
            COLF_DIST: "distrito",
            COLF_DIV:  "division"
        }
    )
)

# CONCATENAR
div_all = pd.concat(div_frames, ignore_index=True)

# LIMPIAR
div_all["departamento"] = div_all["departamento"].apply(clean_str)
div_all["provincia"]    = div_all["provincia"].apply(clean_str)
div_all["distrito"]     = div_all["distrito"].apply(clean_str)
div_all["division"]     = div_all["division"].apply(clean_str)

# LISTA TOTAL DE DIVISIONES
DIVISIONES = sorted(div_all["division"].dropna().unique())

# POR DEPARTAMENTO
DIVISIONES_BY_DEPT = {}
for dep in DEPARTAMENTOS:
    divs = div_all.loc[div_all["departamento"] == dep, "division"].dropna().unique().tolist()
    DIVISIONES_BY_DEPT[dep] = sorted(set(divs))

# POR PROVINCIA
DIVISIONES_BY_PROV = {}
for prov in PROVINCIAS_BY_DEPT.values():
    for p in prov:
        divs = div_all.loc[div_all["provincia"] == p, "division"].dropna().unique().tolist()
        DIVISIONES_BY_PROV[p] = sorted(set(divs))

# POR DISTRITO
DIVISIONES_BY_DIST = {}
for prov, dists in DIST_BY_PROV.items():
    for d in dists:
        divs = div_all.loc[div_all["distrito"] == d, "division"].dropna().unique().tolist()
        DIVISIONES_BY_DIST[d] = sorted(set(divs))



# ============================================================
# 4. FLASK + LOGIN
# ============================================================
app = Flask(__name__)
app.secret_key = os.getenv("SECRET_KEY", "fallback_local")

APP_USER = os.getenv("APP_USERNAME","adminbbva") #CAMBIOS
APP_PASS = os.getenv("APP_PASSWORD","clave123") #CAMBIOS

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
    <div class="card-title"><span class="icon">🌐</span>ATMs</div>
  </div>

  <div class="card" onclick="location.href='/mapa/agentes'">
    <img src="{{ url_for('static', filename='agente.png') }}" alt="Agentes BBVA">
    <div class="card-title"><span class="icon">🧍</span>Agentes</div>
  </div>

  <div class="card" onclick="location.href='/mapa/integral'">
    <img src="{{ url_for('static', filename='banco.png') }}" alt="Mapa Integral BBVA">
    <div class="card-title"><span class="icon">🗺️</span>Integral</div>
  </div>

</div>

</body>
</html>
"""


@app.route("/selector")
@login_required
def selector():
    return render_template_string(SELECTOR_TEMPLATE)


@app.route("/api/recomendaciones")
@login_required
def api_recomendaciones():
    return jsonify(recomendaciones.to_dict(orient="records"))

# ============================================================
# 6B. RUTA MAPA INTEGRAL (OFICINAS + ATMs + AGENTES)
# ============================================================
@app.route("/mapa/integral")
@login_required
def mapa_integral():

    # Centro inicial igual a otras vistas
    initial_center = df[[COL_LAT, COL_LON]].mean().tolist()

    return render_template_string(
        TEMPLATE_MAPA,
        
        tipo_mapa="integral",

        # 🔵 JERARQUÍA TOTAL UNIFICADA
        departamentos=DEPARTAMENTOS,
        provincias_by_dept=PROVINCIAS_BY_DEPT,
        dist_by_prov=DIST_BY_PROV,

        # 🔵 DIVISIONES UNIFICADAS
        div_by_dept=DIVISIONES_BY_DEPT,
        div_by_prov=DIVISIONES_BY_PROV,
        div_by_dist=DIVISIONES_BY_DIST,
        divisiones=DIVISIONES,

        segment_list=SEGMENTOS_CLIENTES,              # 👈 NUEVO

        # Mapa
        initial_center=initial_center,
        initial_zoom=6,
    )


# ============================================================
# 6. RUTA DEL MAPA POR CAPA
# ============================================================
@app.route("/mapa/<tipo>")
@login_required
def mapa_tipo(tipo):

    # Tipos válidos
    if tipo not in ["oficinas", "islas", "agentes"]:
        return "No existe esa capa", 404

    # Centro inicial del mapa basado en ATMs (o puedes usar oficinas/agentes)
    initial_center = df[[COL_LAT, COL_LON]].mean().tolist()

    # ================================
    # USAR SIEMPRE LA JERARQUÍA UNIFICADA
    # ================================
    departamentos      = DEPARTAMENTOS
    provincias_by_dept = PROVINCIAS_BY_DEPT
    dist_by_prov       = DIST_BY_PROV

    # ================================
    # DIVISIONES TAMBIÉN UNIFICADAS
    # ================================
    div_by_dept = DIVISIONES_BY_DEPT
    div_by_prov = DIVISIONES_BY_PROV
    div_by_dist = DIVISIONES_BY_DIST
    divisiones  = DIVISIONES

    return render_template_string(
        TEMPLATE_MAPA,
        tipo_mapa=tipo,

        # JERARQUÍA TOTAL
        departamentos=departamentos,
        provincias_by_dept=provincias_by_dept,
        dist_by_prov=dist_by_prov,

        # DIVISIONES
        div_by_dept=div_by_dept,
        div_by_prov=div_by_prov,
        div_by_dist=div_by_dist,
        divisiones=divisiones,

        segment_list=SEGMENTOS_CLIENTES, 

        initial_center=initial_center,
        initial_zoom=6,
    )



# ============================================================
# 7. API /api/points — ISLAS + AGENTES + OFICINAS
# ============================================================
@app.route("/api/points")
@login_required
def api_points():
    tipo_mapa = request.args.get("tipo", "").lower()

    dpto = request.args.get("departamento", "").upper().strip()
    prov = request.args.get("provincia", "").upper().strip()
    dist = request.args.get("distrito", "").upper().strip()
    divi = request.args.get("division", "").upper().strip()

    tipo_atm = request.args.get("tipo_atm", "").upper().strip()
    ubic_atm = request.args.get("ubic_atm", "").upper().strip()

    # ---------------------- CAPA ISLAS (ATMs) ----------------------
    if tipo_mapa == "islas":
        dff = df.copy()

        dff[COL_DEPT] = dff[COL_DEPT].astype(str).str.upper().str.strip()
        dff[COL_PROV] = dff[COL_PROV].astype(str).str.upper().str.strip()
        dff[COL_DIST] = dff[COL_DIST].astype(str).str.upper().str.strip()
        dff[COL_DIV] = dff[COL_DIV].astype(str).str.upper().str.strip()
        dff[COL_UBIC] = dff[COL_UBIC].astype(str).str.upper().str.strip()
        dff[COL_TIPO] = dff[COL_TIPO].astype(str).str.upper().str.strip()

        if dpto:
            dff = dff[dff[COL_DEPT] == dpto]
        if prov:
            dff = dff[dff[COL_PROV] == prov]
        if dist:
            dff = dff[dff[COL_DIST] == dist]
        if divi:
            dff = dff[dff[COL_DIV] == divi]

        if tipo_atm:
            dff = dff[dff[COL_TIPO].str.contains(tipo_atm, na=False)]

        if ubic_atm:
            dff = dff[dff[COL_UBIC].str.contains(ubic_atm, na=False)]

        dff_layer = dff

        total_atms = int(len(dff_layer))
        suma_total = float(dff_layer[PROM_COL].sum()) if total_atms > 0 else 0.0

        total_oficinas = int(dff_layer[COL_UBIC].str.contains("OFICINA", na=False).sum())
        total_islas = int(dff_layer[COL_UBIC].str.contains("ISLA", na=False).sum())

        total_disp = int(dff_layer[COL_TIPO].str.contains("DISPENSADOR", na=False).sum())
        total_mon = int(dff_layer[COL_TIPO].str.contains("MONEDERO", na=False).sum())
        total_rec = int(dff_layer[COL_TIPO].str.contains("RECICLADOR", na=False).sum())

        puntos = []
        for _, r in dff_layer.iterrows():
            nombre = ""
            if COL_NAME and COL_NAME in r.index:
                nombre = str(r.get(COL_NAME, "")).strip()
            if not nombre:
                nombre = str(r.get(COL_ATM, ""))

            lat_v = float(r[COL_LAT])
            lon_v = float(r[COL_LON])

            puntos.append(
                {
                    "lat": lat_v,
                    "lon": lon_v,
                    "atm": str(r.get(COL_ATM, "")),
                    "nombre": nombre,
                    "promedio": float(r.get(PROM_COL, 0.0)),
                    "division": str(r.get(COL_DIV, "")),
                    "tipo": str(r.get(COL_TIPO, "")),
                    "ubicacion": str(r.get(COL_UBIC, "")),
                    "departamento": str(r.get(COL_DEPT, "")),
                    "provincia": str(r.get(COL_PROV, "")),
                    "distrito": str(r.get(COL_DIST, "")),
                    "direccion": get_address(lat_v, lon_v),
                    "capa": "",
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
                "suma_total": suma_total,
                "total_agentes": 0,
                "total_capa_A1": 0,
                "total_capa_A2": 0,
                "total_capa_A3": 0,
                "total_capa_B": 0,
                "total_capa_C": 0,
            }
        )

    # ---------------------- CAPA AGENTES ----------------------
    if tipo_mapa == "agentes":
        dff = df_agentes.copy()

        dff[COLA_DEPT] = dff[COLA_DEPT].astype(str).str.upper().str.strip()
        dff[COLA_PROV] = dff[COLA_PROV].astype(str).str.upper().str.strip()
        dff[COLA_DIST] = dff[COLA_DIST].astype(str).str.upper().str.strip()
        dff[COLA_DIV] = dff[COLA_DIV].astype(str).str.upper().str.strip()
        dff[COLA_CAPA] = dff[COLA_CAPA].astype(str).str.upper().str.strip()

        if dpto:
            dff = dff[dff[COLA_DEPT] == dpto]
        if prov:
            dff = dff[dff[COLA_PROV] == prov]
        if dist:
            dff = dff[dff[COLA_DIST] == dist]
        if divi:
            dff = dff[dff[COLA_DIV] == divi]

        total_agentes = int(len(dff))
        suma_total = float(dff[PROMA_COL].sum()) if total_agentes > 0 else 0.0

        capa_series = dff[COLA_CAPA].str.upper().fillna("")
        total_capa_A1 = int((capa_series == "A1").sum())
        total_capa_A2 = int((capa_series == "A2").sum())
        total_capa_A3 = int((capa_series == "A3").sum())
        total_capa_B = int((capa_series == "B").sum())
        total_capa_C = int((capa_series == "C").sum())

        puntos = []
        for _, r in dff.iterrows():
            lat_v = float(r[COLA_LAT])
            lon_v = float(r[COLA_LON])

            trxs_oct = float(r.get(COLA_TRX_OCT, 0.0)) if COLA_TRX_OCT else 0.0
            trxs_nov = float(r.get(COLA_TRX_NOV, 0.0)) if COLA_TRX_NOV else 0.0

            puntos.append(
                {
                    "lat": lat_v,
                    "lon": lon_v,
                    "atm": str(r.get(COLA_ID, "")),
                    "nombre": str(r.get(COLA_COM, "")),
                    "promedio": float(r.get(PROMA_COL, 0.0)),
                    "division": str(r.get(COLA_DIV, "")),
                    "tipo": "AGENTE",
                    "ubicacion": "AGENTE",
                    "departamento": str(r.get(COLA_DEPT, "")),
                    "provincia": str(r.get(COLA_PROV, "")),
                    "distrito": str(r.get(COLA_DIST, "")),
                    "direccion": str(r.get(COLA_DIR, "")),
                    "capa": str(r.get(COLA_CAPA, "")),
                    "trxs_oct": trxs_oct,
                    "trxs_nov": trxs_nov,
                }
            )

        return jsonify(
            {
                "puntos": puntos,
                "total_atms": total_agentes,
                "total_oficinas": 0,
                "total_islas": 0,
                "total_disp": 0,
                "total_mon": 0,
                "total_rec": 0,
                "suma_total": suma_total,
                "total_agentes": total_agentes,
                "total_capa_A1": total_capa_A1,
                "total_capa_A2": total_capa_A2,
                "total_capa_A3": total_capa_A3,
                "total_capa_B": total_capa_B,
                "total_capa_C": total_capa_C,
            }
        )

    # ---------------------- CAPA OFICINAS ----------------------
    if tipo_mapa == "oficinas":
        dff = df_oficinas.copy()

        dff[COLF_DEPT] = dff[COLF_DEPT].astype(str).str.upper().str.strip()
        dff[COLF_PROV] = dff[COLF_PROV].astype(str).str.upper().str.strip()
        dff[COLF_DIST] = dff[COLF_DIST].astype(str).str.upper().str.strip()
        dff[COLF_DIV] = dff[COLF_DIV].astype(str).str.upper().str.strip()

        if dpto:
            dff = dff[dff[COLF_DEPT] == dpto]
        if prov:
            dff = dff[dff[COLF_PROV] == prov]
        if dist:
            dff = dff[dff[COLF_DIST] == dist]
        if divi:
            dff = dff[dff[COLF_DIV] == divi]

        total_oficinas = int(len(dff))
        suma_total = float(dff[COLF_TRX].sum()) if total_oficinas > 0 else 0.0

        puntos = []
        for _, r in dff.iterrows():
            lat_v = float(r[COLF_LAT])
            lon_v = float(r[COLF_LON])

            puntos.append(
                {
                    "lat": lat_v,
                    "lon": lon_v,
                    "atm": str(r.get(COLF_ID, "")),
                    "nombre": str(r.get(COLF_NAME, "")),
                    "promedio": float(r.get(COLF_TRX, 0.0)),
                    "division": str(r.get(COLF_DIV, "")),
                    "tipo": "OFICINA",
                    "ubicacion": "OFICINA",
                    "departamento": str(r.get(COLF_DEPT, "")),
                    "provincia": str(r.get(COLF_PROV, "")),
                    "distrito": str(r.get(COLF_DIST, "")),
                    "direccion": "No disponible (a incorporar)",
                    "capa": "",
                }
            )

        return jsonify(
            {
                "puntos": puntos,
                "total_atms": total_oficinas,
                "total_oficinas": total_oficinas,
                "total_islas": 0,
                "total_disp": 0,
                "total_mon": 0,
                "total_rec": 0,
                "suma_total": suma_total,
                "total_agentes": 0,
                "total_capa_A1": 0,
                "total_capa_A2": 0,
                "total_capa_A3": 0,
                "total_capa_B": 0,
                "total_capa_C": 0,
            }
        )

    return jsonify(
        {
            "puntos": [],
            "total_atms": 0,
            "total_oficinas": 0,
            "total_islas": 0,
            "total_disp": 0,
            "total_mon": 0,
            "total_rec": 0,
            "suma_total": 0.0,
            "total_agentes": 0,
            "total_capa_A1": 0,
            "total_capa_A2": 0,
            "total_capa_A3": 0,
            "total_capa_B": 0,
            "total_capa_C": 0,
        }
    )

# ============================================================
# NUEVO — ENDPOINT DE CLIENTES CON MUESTREO DINÁMICO @login_required
# ============================================================
@app.route("/api/clientes")
@login_required
def api_clientes():
    # Zoom (para definir cuánto muestreamos)
    zoom_str = request.args.get("zoom", "10")
    try:
        zoom = int(float(zoom_str))
    except:
        zoom = 10

    # --- Filtros geográficos desde los combos ---
    dpto = request.args.get("departamento", "").upper().strip()
    prov = request.args.get("provincia", "").upper().strip()
    dist = request.args.get("distrito", "").upper().strip()

    dff = df_clientes.copy()

    if dpto:
        dff = dff[dff["departamento"].str.upper() == dpto]
    if prov:
        dff = dff[dff["provincia"].str.upper() == prov]
    if dist:
        dff = dff[dff["distrito"].str.upper() == dist]

    # Si no quedan clientes, devolvemos lista vacía
    if dff.empty:
        return jsonify([])

    # --- Muestreo dinámico según zoom (igual que en el backup) ---
    if zoom <= 5:
        sample_size = 1000
    elif zoom <= 9:
        sample_size = 3000
    elif zoom <= 13:
        sample_size = 7000
    else:
        sample_size = 12000

    sample_size = min(sample_size, len(dff))

    df_sample = dff.sample(sample_size, replace=False, random_state=None)

    puntos = [
        {"lat": float(r.latitud), "lon": float(r.longitud)}
        for _, r in df_sample.iterrows()
    ]

    return jsonify(puntos)

# ============================================================
# API — RESUMEN DE CLIENTES VISIBLE SEGÚN FILTROS
# ============================================================

@app.route("/api/resumen_clientes")
@login_required
def api_resumen_clientes():

    # ---- Leer filtros ----
    dpto = request.args.get("departamento", "").upper().strip()
    prov = request.args.get("provincia", "").upper().strip()
    dist = request.args.get("distrito", "").upper().strip()
    segmento = request.args.get("segmento", "").upper().strip()

    # ---- Filtrar base ----
    dff = df_clientes.copy()

    if dpto:
        dff = dff[dff["departamento"].str.upper() == dpto]
    if prov:
        dff = dff[dff["provincia"].str.upper() == prov]
    if dist:
        dff = dff[dff["distrito"].str.upper() == dist]
    if segmento:
      dff = dff[dff["segmento"].str.upper() == segmento]

    # Si no hay clientes en la zona → retorno vacío
    if dff.empty:
        return jsonify({
            "total": 0,
            "digital_pct": 0,
            "edad_prom": 0,
            "ingreso_prom": 0,
            "deuda_prom": 0,
            "top_segmento": "—"
        })

    # ---- Estadísticas ----
    total = len(dff)

    digital_pct = round(
        100 * dff["flag_digital"].mean(), 1
    ) if "flag_digital" in dff.columns else 0

    edad_prom = round(
        dff["edad"].mean(), 1
    ) if "edad" in dff.columns else 0

    ingreso_prom = round(
        dff["ingresos"].mean(), 2
    ) if "ingresos" in dff.columns else 0

    deuda_prom = round(
        dff["deuda"].mean(), 2
    ) if "deuda" in dff.columns else 0

    # Top segmento
    if "segmento" in dff.columns:
        top_segmento = (
            dff["segmento"]
            .value_counts()
            .idxmax()
        )
    else:
        top_segmento = "—"

    return jsonify({
        "total": total,
        "digital_pct": digital_pct,
        "edad_prom": edad_prom,
        "ingreso_prom": ingreso_prom,
        "deuda_prom": deuda_prom,
        "top_segmento": top_segmento
    })



# ============================================================
# 7B. API INTEGRAL /api/points_integral — 3 CAPAS
# ============================================================
@app.route("/api/points_integral")
@login_required
def api_points_integral():
    dpto = request.args.get("departamento", "").upper().strip()
    prov = request.args.get("provincia", "").upper().strip()
    dist = request.args.get("distrito", "").upper().strip()
    divi = request.args.get("division", "").upper().strip()

    # ------------ ATMs ------------
    dfA = df.copy()
    dfA[COL_DEPT] = dfA[COL_DEPT].astype(str).str.upper().str.strip()
    dfA[COL_PROV] = dfA[COL_PROV].astype(str).str.upper().str.strip()
    dfA[COL_DIST] = dfA[COL_DIST].astype(str).str.upper().str.strip()
    dfA[COL_DIV] = dfA[COL_DIV].astype(str).str.upper().str.strip()
    dfA[COL_UBIC] = dfA[COL_UBIC].astype(str).str.upper().str.strip()
    dfA[COL_TIPO] = dfA[COL_TIPO].astype(str).str.upper().str.strip()

    if dpto:
        dfA = dfA[dfA[COL_DEPT] == dpto]
    if prov:
        dfA = dfA[dfA[COL_PROV] == prov]
    if dist:
        dfA = dfA[dfA[COL_DIST] == dist]
    if divi:
        dfA = dfA[dfA[COL_DIV] == divi]

    puntos_atm = []
    suma_atm = float(dfA[PROM_COL].sum())
    for _, r in dfA.iterrows():
        lat = float(r[COL_LAT])
        lon = float(r[COL_LON])
        nombre = str(r.get(COL_NAME, r.get(COL_ATM, "")))
        puntos_atm.append(
            {
                "tipo_canal": "ATM",
                "lat": lat,
                "lon": lon,
                "atm": str(r.get(COL_ATM, "")),
                "nombre": nombre,
                "promedio": float(r.get(PROM_COL, 0.0)),
                "division": str(r.get(COL_DIV, "")),
                "tipo": str(r.get(COL_TIPO, "")),
                "ubicacion": str(r.get(COL_UBIC, "")),
                "departamento": str(r.get(COL_DEPT, "")),
                "provincia": str(r.get(COL_PROV, "")),
                "distrito": str(r.get(COL_DIST, "")),
                "direccion": get_address(lat, lon),
            }
        )

    # ------------ OFICINAS ------------
    dfO = df_oficinas.copy()
    dfO[COLF_DEPT] = dfO[COLF_DEPT].astype(str).str.upper().str.strip()
    dfO[COLF_PROV] = dfO[COLF_PROV].astype(str).str.upper().str.strip()
    dfO[COLF_DIST] = dfO[COLF_DIST].astype(str).str.upper().str.strip()
    dfO[COLF_DIV] = dfO[COLF_DIV].astype(str).str.upper().str.strip()

    if dpto:
        dfO = dfO[dfO[COLF_DEPT] == dpto]
    if prov:
        dfO = dfO[dfO[COLF_PROV] == prov]
    if dist:
        dfO = dfO[dfO[COLF_DIST] == dist]
    if divi:
        dfO = dfO[dfO[COLF_DIV] == divi]

    puntos_of = []
    suma_of = float(dfO[COLF_TRX].sum())
    for _, r in dfO.iterrows():
        puntos_of.append(
            {
                "tipo_canal": "OFICINA",
                "lat": float(r[COLF_LAT]),
                "lon": float(r[COLF_LON]),
                "atm": str(r.get(COLF_ID, "")),
                "nombre": str(r.get(COLF_NAME, "")),
                "promedio": float(r.get(COLF_TRX, 0.0)),
                "division": str(r.get(COLF_DIV, "")),
                "tipo": "OFICINA",
                "ubicacion": "OFICINA",
                "departamento": str(r.get(COLF_DEPT, "")),
                "provincia": str(r.get(COLF_PROV, "")),
                "distrito": str(r.get(COLF_DIST, "")),
                "direccion": "No disponible (a incorporar)",
            }
        )

    # ------------ AGENTES ------------
    dfG = df_agentes.copy()
    dfG[COLA_DEPT] = dfG[COLA_DEPT].astype(str).str.upper().str.strip()
    dfG[COLA_PROV] = dfG[COLA_PROV].astype(str).str.upper().str.strip()
    dfG[COLA_DIST] = dfG[COLA_DIST].astype(str).str.upper().str.strip()
    dfG[COLA_DIV] = dfG[COLA_DIV].astype(str).str.upper().str.strip()
    dfG[COLA_CAPA] = dfG[COLA_CAPA].astype(str).str.upper().str.strip()

    if dpto:
        dfG = dfG[dfG[COLA_DEPT] == dpto]
    if prov:
        dfG = dfG[dfG[COLA_PROV] == prov]
    if dist:
        dfG = dfG[dfG[COLA_DIST] == dist]
    if divi:
        dfG = dfG[dfG[COLA_DIV] == divi]

    puntos_ag = []
    suma_ag = float(dfG[PROMA_COL].sum())
    for _, r in dfG.iterrows():
        puntos_ag.append(
            {
                "tipo_canal": "AGENTE",
                "lat": float(r[COLA_LAT]),
                "lon": float(r[COLA_LON]),
                "atm": str(r.get(COLA_ID, "")),
                "nombre": str(r.get(COLA_COM, "")),
                "promedio": float(r.get(PROMA_COL, 0.0)),
                "division": str(r.get(COLA_DIV, "")),
                "tipo": "AGENTE",
                "ubicacion": "AGENTE",
                "departamento": str(r.get(COLA_DEPT, "")),
                "provincia": str(r.get(COLA_PROV, "")),
                "distrito": str(r.get(COLA_DIST, "")),
                "direccion": str(r.get(COLA_DIR, "")),
                "capa": str(r.get(COLA_CAPA, "")),
                "trxs_oct": float(r.get(COLA_TRX_OCT, 0.0)) if COLA_TRX_OCT else 0.0,
                "trxs_nov": float(r.get(COLA_TRX_NOV, 0.0)) if COLA_TRX_NOV else 0.0,
            }
        )

    return jsonify(
        {
            "atms": puntos_atm,
            "oficinas": puntos_of,
            "agentes": puntos_ag,
            "suma_atms": suma_atm,
            "suma_oficinas": suma_of,
            "suma_agentes": suma_ag,
            "total_atms": len(puntos_atm),
            "total_oficinas": len(puntos_of),
            "total_agentes": len(puntos_ag),
        }
    )


# ============================================================
# 8. TEMPLATE MAPA — FRONTEND COMPLETO
#   ✅ CAMBIO CLAVE:
#   - OFICINAS y AGENTES (NO integral) usan la MISMA VENTANA
#     que el integral (mismos IDs y misma lógica).
# ============================================================
TEMPLATE_MAPA = """
<!doctype html>
<html>
<head>
<meta charset="utf-8">

<title>
  Mapa BBVA —
  {% if tipo_mapa == 'islas' %}
    ATMs
  {% else %}
    {{ tipo_mapa|upper }}
  {% endif %}
</title>

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
  width:360px;
  display:flex;
  flex-direction:column;
  gap:12px;
}
.side-card{
  background:white;
  border-radius:12px;
  padding:14px 16px;
  box-shadow:0 6px 22px rgba(0,0,0,0.12);
  font-size:13px;
}
.side-title{
  font-weight:800;
  margin-bottom:6px;
  display:flex;
  align-items:center;
  gap:8px;
}
.muted{
  color:var(--muted);
  font-size:12px;
}

.brand-card{
  padding:10px;
}
.brand-card img{
  width:100%;
  height:120px;
  object-fit:cover;
  border-radius:10px;
  display:block;
}

.legend{
  margin-top:10px;
}
.legend .legend-item{
  display:flex;
  align-items:center;
  gap:10px;
  margin-top:6px;
}
.legend .legend-item img{
  width:28px;
  height:28px;
  object-fit:contain;
  background:#fff;
  border:1px solid #e6eef8;
  border-radius:8px;
  padding:3px;
  box-shadow:0 2px 8px rgba(0,0,0,0.06);
}
.legend .legend-item .lbl{
  color:var(--muted);
  font-size:12px;
}
.icon-reco {
    font-size: 22px;
    color: #ffcc00;
    text-shadow: 0 0 4px black;
}

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
@keyframes panelGlow{
  0%{box-shadow:0 0 0 rgba(20,100,165,0.0);}
  50%{box-shadow:0 0 18px rgba(20,100,165,0.55);}
  100%{box-shadow:0 0 0 rgba(20,100,165,0.0);}
}
.side-card-atm.glow{
  animation:panelGlow 2.2s ease-in-out infinite;
}
.hidden{ display:none; }

.leaflet-popup-content-wrapper{
  border-radius:12px;
  box-shadow:0 6px 20px rgba(0,0,0,0.25);
}
</style>
</head>

<body>

<header>
  <h1>
    Mapa BBVA —
    {% if tipo_mapa == 'islas' %}
      ATMs
    {% else %}
      {{ tipo_mapa|upper }}
    {% endif %}
  </h1>
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

    <label>
      Segmento:
      <select id="selSegmento">
        <option value="">-- Todos --</option>
        {% for seg in segment_list %}
            <option value="{{ seg }}">{{ seg }}</option>
        {% endfor %}
      </select>
    </label>


    {% if tipo_mapa == 'islas' %}
      <label>Tipo ATM:
        <select id="selTipoATM">
          <option value="">-- Todos --</option>
          <option value="DISPENSADOR">Dispensador</option>
          <option value="MONEDERO">Monedero</option>
          <option value="RECICLADOR">Reciclador</option>
        </select>
      </label>

      <label>Ubicación:
        <select id="selUbicacionATM">
          <option value="">-- Todas --</option>
          <option value="OFICINA">Oficina</option>
          <option value="ISLA">Isla</option>
        </select>
      </label>
    {% endif %}

    {% if tipo_mapa == 'integral' %}
      <label style="margin-left:8px;">
        Canales:
        <span style="display:flex; gap:10px; margin-left:6px;">
          <label style="gap:4px;"><input type="checkbox" id="chkShowATMs" checked> ATMs</label>
          <label style="gap:4px;"><input type="checkbox" id="chkShowOficinas" checked> Oficinas</label>
          <label style="gap:4px;"><input type="checkbox" id="chkShowAgentes" checked> Agentes</label>
        </span>
      </label>
    {% endif %}

    <label style="margin-left:16px;">
      <input type="checkbox" id="chkHeat" checked> Heatmap
    </label>

    <!-- ========================================================= -->
    <!-- NUEVO — Checkbox para el Heatmap de Clientes -->
    <!-- ========================================================= -->
    <label style="margin-left:16px;">  <!-- NUEVO -->
      <input type="checkbox" id="chkHeatClientes"> Heatmap Clientes <!-- NUEVO -->
    </label> <!-- NUEVO -->

    <label style="margin-left:16px;">
      <input type="checkbox" id="chkReco"> Recomendaciones
    </label>



    <div style="flex:1"></div>

    <div style="font-size:13px; color:var(--muted);">
      Mostrando <span id="infoCount">--</span>
      {% if tipo_mapa == 'integral' %} puntos {% else %} registros {% endif %}
    </div>

  </div>
</div>

<div class="main">
  <div id="map"></div>

  <div class="side">

    {% if tipo_mapa == 'integral' %}
      <div class="side-card brand-card">
        <img src="{{ url_for('static', filename='banco.png') }}" alt="BBVA">
      </div>
    {% endif %}

    <!-- ============================================================
         ✅ SIEMPRE EXISTEN LOS 3 PANELES (MISMOS IDs)
         - Integral: se controlan por checkbox
         - No integral: se muestra SOLO el panel de su capa
       ============================================================ -->

    <div id="panelATMResumen" class="side-card {% if tipo_mapa != 'integral' and tipo_mapa != 'islas' %}hidden{% endif %}">
      <div class="side-title">🌐 Panel ATMs</div>
      {% if tipo_mapa == 'integral' %}
        <div class="muted">Se actualiza con filtros y solo cuenta si ATMs está activado.</div>
      {% else %}
        <div class="muted">Se actualiza con filtros (solo ATMs).</div>
      {% endif %}

      <div style="margin-top:8px;">
        <b>Total ATMs:</b> <span id="resAtmTotal">0</span>
      </div>
      <div class="muted" style="margin-top:4px;">
        <b>Suma TRX:</b> <span id="resAtmSuma">0</span>
      </div>

      <div style="margin-top:10px; font-weight:700;">Distribución</div>
      <div class="muted">ATMs en oficina: <span id="resAtmEnOfi">0</span></div>
      <div class="muted">ATMs en isla: <span id="resAtmEnIsla">0</span></div>

      <div style="margin-top:10px; font-weight:700;">Tipos</div>
      <div class="muted">Dispensador: <span id="resAtmDisp">0</span></div>
      <div class="muted">Monedero: <span id="resAtmMon">0</span></div>
      <div class="muted">Reciclador: <span id="resAtmRec">0</span></div>

      <div class="legend">
        <div style="font-weight:700;">Leyenda</div>
        <div class="legend-item">
          <img src="{{ url_for('static', filename='atm_oficina.png') }}" alt="ATM Oficina">
          <div class="lbl">ATM en Oficina</div>
        </div>
        <div class="legend-item">
          <img src="{{ url_for('static', filename='atm_isla.png') }}" alt="ATM Isla">
          <div class="lbl">ATM en Isla</div>
        </div>
      </div>
    </div>

    <div id="panelOfiResumen" class="side-card {% if tipo_mapa != 'integral' and tipo_mapa != 'oficinas' %}hidden{% endif %}">
      <div class="side-title">🏦 Panel Oficinas</div>
      {% if tipo_mapa == 'integral' %}
        <div class="muted">Se actualiza con filtros y solo cuenta si Oficinas está activado.</div>
      {% else %}
        <div class="muted">Se actualiza con filtros (solo Oficinas).</div>
      {% endif %}

      <div style="margin-top:8px;">
        <b>Total Oficinas:</b> <span id="resOfiTotal">0</span>
      </div>
      <div class="muted" style="margin-top:4px;">
        <b>Suma TRX:</b> <span id="resOfiSuma">0</span>
      </div>

      <div class="legend">
        <div style="font-weight:700;">Leyenda</div>
        <div class="legend-item">
          <img src="{{ url_for('static', filename='oficina.png') }}" alt="Oficina">
          <div class="lbl">Oficina</div>
        </div>
      </div>
    </div>

    <div id="panelAgResumen" class="side-card {% if tipo_mapa != 'integral' and tipo_mapa != 'agentes' %}hidden{% endif %}">
      <div class="side-title">🧍 Panel Agentes</div>
      {% if tipo_mapa == 'integral' %}
        <div class="muted">Se actualiza con filtros y solo cuenta si Agentes está activado.</div>
      {% else %}
        <div class="muted">Se actualiza con filtros (solo Agentes).</div>
      {% endif %}

      <div style="margin-top:8px;">
        <b>Total Agentes:</b> <span id="resAgTotal">0</span>
      </div>
      <div class="muted" style="margin-top:4px;">
        <b>Suma TRX:</b> <span id="resAgSuma">0</span>
      </div>

      <div style="margin-top:10px; font-weight:700;">Capas</div>
      <div class="muted">A1: <span id="resAgA1">0</span></div>
      <div class="muted">A2: <span id="resAgA2">0</span></div>
      <div class="muted">A3: <span id="resAgA3">0</span></div>
      <div class="muted">B : <span id="resAgB">0</span></div>
      <div class="muted">C : <span id="resAgC">0</span></div>

      <div class="legend">
        <div style="font-weight:700;">Leyenda</div>
        <div class="legend-item">
          <img src="{{ url_for('static', filename='agente.png') }}" alt="Agente">
          <div class="lbl">Agente</div>
        </div>
      </div>
    </div>

    <!-- PANEL RESUMEN CLIENTES -->
    <div id="panelClientes" class="side-card hidden">
      <div class="side-title">Clientes visibles</div>
      <div class="muted">Total clientes: <span id="cliTotal">0</span></div>
      <div class="muted">% digitales: <span id="cliDigital">0%</span></div>
      <div class="muted">Edad promedio: <span id="cliEdad">0</span></div>
      <div class="muted">Ingreso promedio: <span id="cliIngreso">0</span></div>
      <div class="muted">Deuda promedio: <span id="cliDeuda">0</span></div>
      <div class="muted">Top segmento: <span id="cliTopSeg">—</span></div>
    </div>


    <!-- PANEL DETALLE (clic en un punto) -->
    <div id="panelATM" class="side-card side-card-atm hidden">
      <h3 id="panelATMTitle">Panel del punto seleccionado</h3>
      <div id="atmDetalle" style="font-size:12px;"></div>
      <button id="btnVolver" class="btn-small">VOLVER</button>
    </div>

    <!-- PANEL DETALLE RECOMENDACIÓN — NUEVO -->
    <div id="panelReco" class="side-card side-card-atm hidden">
        <h3 id="recoTitle">Recomendación</h3>

        <div id="recoDetalle" style="font-size:12px; white-space:pre-line;"></div>

        <button id="btnRecoVolver" class="btn-small">VOLVER</button>
    </div>


  </div>
</div>


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
const INITIAL_CENTER = [{{ initial_center[0] }}, {{ initial_center[1] }}];
const INITIAL_ZOOM   = {{ initial_zoom }};

// ======================================================
//  ICONOS SEPARADOS POR CAPA
// ======================================================
const ICON_ATM_OFICINA_URL = "{{ url_for('static', filename='atm_oficina.png') }}";
const ICON_ATM_ISLA_URL    = "{{ url_for('static', filename='atm_isla.png') }}";
const ICON_OFICINA_URL     = "{{ url_for('static', filename='oficina.png') }}";
const ICON_AGENTE_URL      = "{{ url_for('static', filename='agente.png') }}";

const ICON_ATM_OFICINA = L.icon({ iconUrl: ICON_ATM_OFICINA_URL, iconSize:[40,40], iconAnchor:[20,20], popupAnchor:[0,-20] });
const ICON_ATM_ISLA    = L.icon({ iconUrl: ICON_ATM_ISLA_URL,    iconSize:[40,40], iconAnchor:[20,20], popupAnchor:[0,-20] });
const ICON_OFICINA     = L.icon({ iconUrl: ICON_OFICINA_URL,     iconSize:[40,40], iconAnchor:[20,20], popupAnchor:[0,-20] });
const ICON_AGENTE      = L.icon({ iconUrl: ICON_AGENTE_URL,      iconSize:[40,40], iconAnchor:[20,20], popupAnchor:[0,-20] });

function getIcon(pt){
  const ubic = (pt.ubicacion || "").toUpperCase();
  if (TIPO_MAPA === "agentes") return ICON_AGENTE;
  if (TIPO_MAPA === "oficinas") return ICON_OFICINA;
  if (TIPO_MAPA === "islas"){
    if (ubic.includes("OFICINA")) return ICON_ATM_OFICINA;
    if (ubic.includes("ISLA")) return ICON_ATM_ISLA;
    return ICON_ATM_ISLA;
  }
  return ICON_ATM_ISLA;
}

// ======================================================
// MAPA
// ======================================================
const map = L.map('map').setView(INITIAL_CENTER, INITIAL_ZOOM);
L.tileLayer('https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png',{ maxZoom:19 }).addTo(map);

// Capas base
const markers      = L.markerClusterGroup({chunkedLoading:true});
const heat         = L.heatLayer([], {radius:28, blur:22});

// ============================================
// Capa de Recomendaciones (simple) – NUEVO
// ============================================
const markersReco = L.layerGroup();

// ================================================================
// NUEVO — capa de heatmap para CLIENTES
// Suavizamos radio, blur e intensidad para no saturar el mapa
// ================================================================
const heatClientes = L.heatLayer(
  [],
  { 
    radius: 7,     // más pequeño que ATMs
    blur: 6,
    maxZoom: 18,
    minOpacity: 0.04
  }
); // NUEVO

markers.addTo(map);
heat.addTo(map);
// heatClientes se agrega dinámicamente en fetchClientes() // NUEVO


// ======================================================
// COMBOS
// ======================================================
const selDep  = document.getElementById("selDepartamento");
const selProv = document.getElementById("selProvincia");
const selDist = document.getElementById("selDistrito");
const selDiv  = document.getElementById("selDivision");
const chkHeat = document.getElementById("chkHeat");
const chkHeatClientes = document.getElementById("chkHeatClientes"); // NUEVO
const panelClientes    = document.getElementById("panelClientes"); // NUEVO
const infoBox = document.getElementById("infoCount");

const selTipoATM = document.getElementById("selTipoATM");
const selUbicATM = document.getElementById("selUbicacionATM");

function updateProvincias(){
  let d = selDep.value;
  selProv.innerHTML = '<option value="">-- Todas --</option>';
  if(d && PROV_BY_DEPT[d]){
    PROV_BY_DEPT[d].forEach(p => { selProv.innerHTML += `<option value="${p}">${p}</option>`; });
  }
  updateDistritos();
  updateDivisiones();
}
function updateDistritos(){
  let p = selProv.value;
  selDist.innerHTML = '<option value="">-- Todos --</option>';
  if(p && DIST_BY_PROV[p]){
    DIST_BY_PROV[p].forEach(d => { selDist.innerHTML += `<option value="${d}">${d}</option>`; });
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

// ======================================================
// PANEL DETALLE
// ======================================================
const panelATM      = document.getElementById("panelATM");
const panelATMTitle = document.getElementById("panelATMTitle");
const atmDetalle    = document.getElementById("atmDetalle");
const btnVolver     = document.getElementById("btnVolver");

// Panel Recomendación — NUEVO
const panelReco     = document.getElementById("panelReco");
const recoDetalle   = document.getElementById("recoDetalle");
const btnRecoVolver = document.getElementById("btnRecoVolver");


const panelATMResumen = document.getElementById("panelATMResumen");
const panelOfiResumen = document.getElementById("panelOfiResumen");
const panelAgResumen  = document.getElementById("panelAgResumen");

function hideResumenPanels(){
  if(panelATMResumen) panelATMResumen.classList.add("hidden");
  if(panelOfiResumen) panelOfiResumen.classList.add("hidden");
  if(panelAgResumen)  panelAgResumen.classList.add("hidden");
}

function syncSinglePanelsVisibility(){
  if(TIPO_MAPA === "integral"){
    syncIntegralPanelsVisibility();
    return;
  }
  if(panelATMResumen) panelATMResumen.classList.toggle("hidden", TIPO_MAPA !== "islas");
  if(panelOfiResumen) panelOfiResumen.classList.toggle("hidden", TIPO_MAPA !== "oficinas");
  if(panelAgResumen)  panelAgResumen.classList.toggle("hidden", TIPO_MAPA !== "agentes");
}

function showResumenPanels(){
  if(TIPO_MAPA === "integral"){
    syncIntegralPanelsVisibility();
  } else {
    syncSinglePanelsVisibility();
  }
}

function showRecoPanel(r){

    if (!r){
        console.error("❌ showRecoPanel recibió r = undefined");
        return;
    }

    let txt = `
___________ RECOMENDACIÓN ___________

Canal sugerido: ${r.canal.toUpperCase()}
Clientes afectados: ${r.clientes_afectados}

Departamento: ${r.departamento}
Provincia: ${r.provincia}
Distrito: ${r.distrito}

Edad promedio: ${r.edad_prom.toFixed(1)}
Ingreso promedio: S/ ${r.ingreso_prom.toFixed(2)}
% Digitales: ${(r.pct_digital * 100).toFixed(1)}%

Perfil dominante: ${r.perfil_top}

Diagnóstico:
${r.diagnostico.replace(/\\[|\\]|'/g,"")}

Coordenadas:
  lat: ${r.lat}
  lon: ${r.lon}
______________________________________
`;

    document.getElementById("recoDetalle").textContent = txt;

    hideResumenPanels();
    panelATM.classList.add("hidden");

    panelReco.classList.remove("hidden");
    panelReco.classList.add("glow");
}



function showATMPanel(pt){
  const lineaUbic = `${pt.departamento} / ${pt.provincia} / ${pt.distrito}`;
  let texto = "";

  if(TIPO_MAPA === "integral"){
    const canal = (pt.tipo_canal || "").toUpperCase();
    if(canal === "AGENTE"){
      texto = `
_____________________
 AGENTE ${pt.atm}
_____________________

• Comercio: ${pt.nombre}
• Dirección: ${pt.direccion}
• División: ${pt.division}
• Capa: ${pt.capa || ""}
• Tipo: ${pt.tipo}
• Ubicación: ${pt.ubicacion}

• Ubicación Geográfica:
  ${lineaUbic}

• Trxs Octubre: ${pt.trxs_oct ?? 0}
• Trxs Noviembre: ${pt.trxs_nov ?? 0}

_____________________
Promedio: ${pt.promedio}
_____________________
`;
    } else if(canal === "OFICINA"){
      texto = `
_____________________
 OFICINA ${pt.atm}
_____________________

• Nombre: ${pt.nombre}
• Dirección: ${pt.direccion}
• División: ${pt.division}

• Ubicación Geográfica:
  ${lineaUbic}

_____________________
Promedio TRX: ${pt.promedio}
_____________________
`;
    } else {
      texto = `
_____________________
 ATM ${pt.atm}
_____________________

• Nombre: ${pt.nombre}
• Dirección: ${pt.direccion}
• División: ${pt.division}
• Tipo: ${pt.tipo}
• Ubicación: ${pt.ubicacion}

• Ubicación Geográfica:
  ${lineaUbic}

_____________________
Promedio: ${pt.promedio}
_____________________
`;
    }

  } else if(TIPO_MAPA === "agentes"){
    texto = `
_____________________
 AGENTE ${pt.atm}
_____________________

• Comercio: ${pt.nombre}
• Dirección: ${pt.direccion}
• División: ${pt.division}
• Capa: ${pt.capa}
• Tipo: ${pt.tipo}
• Ubicación: ${pt.ubicacion}

• Ubicación Geográfica:
  ${lineaUbic}

• Trxs Octubre: ${pt.trxs_oct ?? 0}
• Trxs Noviembre: ${pt.trxs_nov ?? 0}

_____________________
Promedio: ${pt.promedio}
_____________________
`;

  } else if(TIPO_MAPA === "oficinas"){
    texto = `
_____________________
 OFICINA ${pt.atm}
_____________________

• Nombre: ${pt.nombre}
• Dirección: ${pt.direccion}
• División: ${pt.division}

• Ubicación Geográfica:
  ${lineaUbic}

_____________________
Promedio TRX: ${pt.promedio}
_____________________
`;

  } else { // islas
    texto = `
_____________________
 ATM ${pt.atm}
_____________________

• Nombre: ${pt.nombre}
• Dirección: ${pt.direccion}
• División: ${pt.division}
• Tipo: ${pt.tipo}
• Ubicación: ${pt.ubicacion}

• Ubicación Geográfica:
  ${lineaUbic}

_____________________
Promedio: ${pt.promedio}
_____________________
`;
  }

  atmDetalle.textContent = texto;

  hideResumenPanels();
  panelATM.classList.remove("hidden");
  panelATM.classList.add("glow");
}

btnVolver.addEventListener("click", () => {
  panelATM.classList.add("hidden");
  panelATM.classList.remove("glow");
  showResumenPanels();
});

btnRecoVolver.onclick = () => {
    panelReco.classList.add("hidden");
    panelReco.classList.remove("glow");

    // Restaurar paneles según la vista activa
    if (TIPO_MAPA === "integral"){
        syncIntegralPanelsVisibility();
    } else {
        syncSinglePanelsVisibility();
    }
};


// ======================================================================
// NUEVO — Función para cargar heatmap de CLIENTES
// ======================================================================
async function fetchClientes(){
  try {
     const zoom = map.getZoom();

    const d  = selDep.value;
    const p  = selProv.value;
    const di = selDist.value;
    const seg = selSegmento.value;     // <--- NUEVO

    const qs =
        `zoom=${zoom}`
        + `&departamento=${encodeURIComponent(d)}`
        + `&provincia=${encodeURIComponent(p)}`
        + `&distrito=${encodeURIComponent(di)}`
        + `&segmento=${encodeURIComponent(seg)}`;  // <--- NUEVO

    const res = await fetch(`/api/clientes?${qs}`);
    const data = await res.json();

    heatClientes.setLatLngs(data.map(c => [c.lat, c.lon, 1]));

    if (!map.hasLayer(heatClientes)){
        map.addLayer(heatClientes);
    }
  } catch (err){
    console.error("Error cargando clientes:", err);
  }
}

// ============================================
// RESUMEN DE CLIENTES — CORREGIDO
// ============================================
async function fetchResumenClientes(){

    const d  = selDep.value;
    const p  = selProv.value;
    const di = selDist.value;
    const seg = selSegmento.value;   // <-- OBLIGATORIO NUEVO

    const qs =
        `departamento=${encodeURIComponent(d)}`
        + `&provincia=${encodeURIComponent(p)}`
        + `&distrito=${encodeURIComponent(di)}`
        + `&segmento=${encodeURIComponent(seg)}`;   // <-- OBLIGATORIO NUEVO

    const res = await fetch(`/api/resumen_clientes?${qs}`);
    const js  = await res.json();

    document.getElementById("cliTotal").textContent   = js.total;
    document.getElementById("cliDigital").textContent = js.digital_pct + "%";
    document.getElementById("cliEdad").textContent    = js.edad_prom;
    document.getElementById("cliIngreso").textContent = js.ingreso_prom;
    document.getElementById("cliDeuda").textContent   = js.deuda_prom;
    document.getElementById("cliTopSeg").textContent  = js.top_segmento;
}


async function cargarRecomendaciones(){
    try {
        const res = await fetch("/api/recomendaciones");
        const data = await res.json();

        // limpiar capa
        markersReco.clearLayers();

        data.forEach(r => {
            const m = L.marker([r.lat, r.lon], {
                icon: L.divIcon({
                    className: "icon-reco",
                    html: "⚡",
                    iconSize: [24, 24],
                    iconAnchor: [12, 12]
                })
            });

            // 👈 NUEVO — ABRIR PANEL AL CLIC
            m.on("click", () => showRecoPanel(r));

            markersReco.addLayer(m);
        });

        // agregar al mapa si el checkbox está activo
        if (chkReco.checked){
            markersReco.addTo(map);
        }

    } catch(err){
        console.error("Error cargando recomendaciones:", err);
    }
}




// ======================================================
// CAPAS NORMALES (NO integral) — AHORA ACTUALIZA LOS MISMOS IDs
// ======================================================
async function fetchPoints(){
  if(TIPO_MAPA === "integral") return;

  const d  = selDep.value;
  const p  = selProv.value;
  const di = selDist.value;
  const dv = selDiv.value;

  const t_atm = selTipoATM ? selTipoATM.value : "";
  const u_atm = selUbicATM ? selUbicATM.value : "";

  const qs =
    `tipo=${TIPO_MAPA}` +
    `&departamento=${encodeURIComponent(d)}` +
    `&provincia=${encodeURIComponent(p)}` +
    `&distrito=${encodeURIComponent(di)}` +
    `&division=${encodeURIComponent(dv)}` +
    `&tipo_atm=${encodeURIComponent(t_atm)}` +
    `&ubic_atm=${encodeURIComponent(u_atm)}`;

  infoBox.textContent = "...";
  panelATM.classList.add("hidden");

  const res = await fetch(`/api/points?${qs}`);
  const data = await res.json();
  const pts = data.puntos || [];

  // contador superior
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

    // solo tiene sentido heat con "promedio" (igual sirve para todas)
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
  } else {
    if(map.hasLayer(heat)) map.removeLayer(heat);
  }

  // ✅ Actualizar panel correcto (mismos IDs que integral)
  if(TIPO_MAPA === "islas"){
    const elAtmTotal = document.getElementById("resAtmTotal");
    const elAtmSuma  = document.getElementById("resAtmSuma");
    const elAtmOfi   = document.getElementById("resAtmEnOfi");
    const elAtmIsla  = document.getElementById("resAtmEnIsla");
    const elAtmDisp  = document.getElementById("resAtmDisp");
    const elAtmMon   = document.getElementById("resAtmMon");
    const elAtmRec   = document.getElementById("resAtmRec");

    if(elAtmTotal) elAtmTotal.textContent = data.total_atms || 0;
    if(elAtmSuma)  elAtmSuma.textContent  = Math.round(data.suma_total || 0);
    if(elAtmOfi)   elAtmOfi.textContent   = data.total_oficinas || 0;
    if(elAtmIsla)  elAtmIsla.textContent  = data.total_islas || 0;
    if(elAtmDisp)  elAtmDisp.textContent  = data.total_disp || 0;
    if(elAtmMon)   elAtmMon.textContent   = data.total_mon  || 0;
    if(elAtmRec)   elAtmRec.textContent   = data.total_rec  || 0;
  }

  // ================================================================
  // NUEVO — Exclusividad inicial: si clientes está activo al cargar,
  // apagamos el heatmap de ATMs
  // ================================================================
  if (chkHeatClientes && chkHeatClientes.checked) {     // NUEVO
      chkHeat.checked = false;                          // NUEVO
  }                                                      // NUEVO


  if(TIPO_MAPA === "oficinas"){
    const elOfiTotal = document.getElementById("resOfiTotal");
    const elOfiSuma  = document.getElementById("resOfiSuma");
    if(elOfiTotal) elOfiTotal.textContent = data.total_oficinas || 0;
    if(elOfiSuma)  elOfiSuma.textContent  = Math.round(data.suma_total || 0);
  }

  if(TIPO_MAPA === "agentes"){
    const elAgTotal = document.getElementById("resAgTotal");
    const elAgSuma  = document.getElementById("resAgSuma");
    const elA1 = document.getElementById("resAgA1");
    const elA2 = document.getElementById("resAgA2");
    const elA3 = document.getElementById("resAgA3");
    const elB  = document.getElementById("resAgB");
    const elC  = document.getElementById("resAgC");

    if(elAgTotal) elAgTotal.textContent = data.total_agentes || 0;
    if(elAgSuma)  elAgSuma.textContent  = Math.round(data.suma_total || 0);

    if(elA1) elA1.textContent = data.total_capa_A1 || 0;
    if(elA2) elA2.textContent = data.total_capa_A2 || 0;
    if(elA3) elA3.textContent = data.total_capa_A3 || 0;
    if(elB)  elB.textContent  = data.total_capa_B  || 0;
    if(elC)  elC.textContent  = data.total_capa_C  || 0;
  }

  // asegurar visibilidad correcta al volver
  syncSinglePanelsVisibility();

  // =====================================
  // NUEVO — Recargar recomendaciones
  // =====================================
  if (chkReco.checked){
      cargarRecomendaciones();

      if (!map.hasLayer(markersReco)){
          markersReco.addTo(map);
      }
  } else {
      if (map.hasLayer(markersReco)){
          map.removeLayer(markersReco);
      }
  }


}

// ======================================================
// INTEGRAL
// ======================================================
const chkATMs     = document.getElementById("chkShowATMs");
const chkOficinas = document.getElementById("chkShowOficinas");
const chkAgentes  = document.getElementById("chkShowAgentes");

function syncIntegralPanelsVisibility(){
  if(TIPO_MAPA !== "integral") return;

  if(panelATMResumen) panelATMResumen.classList.toggle("hidden", !(chkATMs && chkATMs.checked));
  if(panelOfiResumen) panelOfiResumen.classList.toggle("hidden", !(chkOficinas && chkOficinas.checked));
  if(panelAgResumen)  panelAgResumen.classList.toggle("hidden", !(chkAgentes && chkAgentes.checked));
}

async function fetchIntegral(){
  if(TIPO_MAPA !== "integral") return;

  const d  = selDep.value;
  const p  = selProv.value;
  const di = selDist.value;
  const dv = selDiv.value;

  const qs =
    `departamento=${encodeURIComponent(d)}` +
    `&provincia=${encodeURIComponent(p)}` +
    `&distrito=${encodeURIComponent(di)}` +
    `&division=${encodeURIComponent(dv)}`;

  infoBox.textContent = "...";
  panelATM.classList.add("hidden");

  const res = await fetch(`/api/points_integral?${qs}`);
  const data = await res.json();

  markers.clearLayers();
  heat.setLatLngs([]);

  let bounds = [];
  let heatPts = [];

  const showATMs = !chkATMs || chkATMs.checked;
  const showOfi  = !chkOficinas || chkOficinas.checked;
  const showAg   = !chkAgentes || chkAgentes.checked;

  if(showATMs){
    (data.atms || []).forEach(pt=>{
      const ubic = (pt.ubicacion || "").toUpperCase();
      const icon = ubic.includes("OFICINA") ? ICON_ATM_OFICINA : ICON_ATM_ISLA;
      const m = L.marker([pt.lat, pt.lon], {icon});
      m.on("click",()=>showATMPanel(pt));
      markers.addLayer(m);

      heatPts.push([pt.lat, pt.lon, Math.max(1, pt.promedio || 1)]);
      bounds.push([pt.lat, pt.lon]);
    });
  }

  if(showOfi){
    (data.oficinas || []).forEach(pt=>{
      const m = L.marker([pt.lat, pt.lon], {icon:ICON_OFICINA});
      m.on("click",()=>showATMPanel(pt));
      markers.addLayer(m);
      bounds.push([pt.lat, pt.lon]);
    });
  }

  if(showAg){
    (data.agentes || []).forEach(pt=>{
      const m = L.marker([pt.lat, pt.lon], {icon:ICON_AGENTE});
      m.on("click",()=>showATMPanel(pt));
      markers.addLayer(m);
      bounds.push([pt.lat, pt.lon]);
    });
  }

  heat.setLatLngs(heatPts);

  if(bounds.length === 1){
    map.setView(bounds[0], 16);
  } else if(bounds.length > 1){
    map.fitBounds(bounds, {padding:[20,20]});
  } else {
    map.setView(INITIAL_CENTER, INITIAL_ZOOM);
  }

  if(chkHeat.checked){
    if(!map.hasLayer(heat)) heat.addTo(map);
  } else {
    if(map.hasLayer(heat)) map.removeLayer(heat);
  }

  // ====== actualizar 3 paneles ======
  const elAtmTotal = document.getElementById("resAtmTotal");
  const elAtmSuma  = document.getElementById("resAtmSuma");
  const elAtmOfi   = document.getElementById("resAtmEnOfi");
  const elAtmIsla  = document.getElementById("resAtmEnIsla");
  const elAtmDisp  = document.getElementById("resAtmDisp");
  const elAtmMon   = document.getElementById("resAtmMon");
  const elAtmRec   = document.getElementById("resAtmRec");

  let atm_total = (data.total_atms || 0);
  let atm_suma  = (data.suma_atms || 0);

  let atm_ofi = 0, atm_isla = 0, atm_disp = 0, atm_mon = 0, atm_rec = 0;
  (data.atms || []).forEach(pt=>{
    const u = (pt.ubicacion || "").toUpperCase();
    const t = (pt.tipo || "").toUpperCase();
    if(u.includes("OFICINA")) atm_ofi++;
    else if(u.includes("ISLA")) atm_isla++;
    else atm_isla++;

    if(t.includes("DISPENSADOR")) atm_disp++;
    if(t.includes("MONEDERO")) atm_mon++;
    if(t.includes("RECICLADOR")) atm_rec++;
  });

  if(elAtmTotal) elAtmTotal.textContent = showATMs ? atm_total : 0;
  if(elAtmSuma)  elAtmSuma.textContent  = showATMs ? Math.round(atm_suma) : 0;
  if(elAtmOfi)   elAtmOfi.textContent   = showATMs ? atm_ofi : 0;
  if(elAtmIsla)  elAtmIsla.textContent  = showATMs ? atm_isla : 0;
  if(elAtmDisp)  elAtmDisp.textContent  = showATMs ? atm_disp : 0;
  if(elAtmMon)   elAtmMon.textContent   = showATMs ? atm_mon : 0;
  if(elAtmRec)   elAtmRec.textContent   = showATMs ? atm_rec : 0;

  const elOfiTotal = document.getElementById("resOfiTotal");
  const elOfiSuma  = document.getElementById("resOfiSuma");
  const ofi_total  = (data.total_oficinas || 0);
  const ofi_suma   = (data.suma_oficinas || 0);

  if(elOfiTotal) elOfiTotal.textContent = showOfi ? ofi_total : 0;
  if(elOfiSuma)  elOfiSuma.textContent  = showOfi ? Math.round(ofi_suma) : 0;

  const elAgTotal = document.getElementById("resAgTotal");
  const elAgSuma  = document.getElementById("resAgSuma");
  const elA1 = document.getElementById("resAgA1");
  const elA2 = document.getElementById("resAgA2");
  const elA3 = document.getElementById("resAgA3");
  const elB  = document.getElementById("resAgB");
  const elC  = document.getElementById("resAgC");

  const ag_total = (data.total_agentes || 0);
  const ag_suma  = (data.suma_agentes || 0);

  let a1=0,a2=0,a3=0,b=0,c=0;
  (data.agentes || []).forEach(pt=>{
    const capa = (pt.capa || "").toUpperCase().trim();
    if(capa === "A1") a1++;
    else if(capa === "A2") a2++;
    else if(capa === "A3") a3++;
    else if(capa === "B")  b++;
    else if(capa === "C")  c++;
  });

  if(elAgTotal) elAgTotal.textContent = showAg ? ag_total : 0;
  if(elAgSuma)  elAgSuma.textContent  = showAg ? Math.round(ag_suma) : 0;

  if(elA1) elA1.textContent = showAg ? a1 : 0;
  if(elA2) elA2.textContent = showAg ? a2 : 0;
  if(elA3) elA3.textContent = showAg ? a3 : 0;
  if(elB)  elB.textContent  = showAg ? b  : 0;
  if(elC)  elC.textContent  = showAg ? c  : 0;

  const visibleCount =
    (showATMs ? atm_total : 0) +
    (showOfi  ? ofi_total : 0) +
    (showAg   ? ag_total : 0);

  infoBox.textContent = visibleCount;

  syncIntegralPanelsVisibility();
}

// ======================================================
// EVENTOS
// ======================================================
if(TIPO_MAPA === "integral"){
  selDep.onchange  = ()=>{ updateProvincias(); fetchIntegral(); if (chkHeatClientes.checked) fetchResumenClientes();};
  selProv.onchange = ()=>{ updateDistritos(); fetchIntegral(); if (chkHeatClientes.checked) fetchResumenClientes();};
  selDist.onchange = ()=>{ updateDivisiones(); fetchIntegral(); if (chkHeatClientes.checked) fetchResumenClientes();};
  selDiv.onchange  = ()=> fetchIntegral();

  // ============================================
  // Filtro de segmento — actualiza HEATMAP + PANEL
  // ============================================
  selSegmento.onchange = () => {
      if (chkHeatClientes.checked){
          fetchClientes();          // Actualiza heatmap de clientes
          fetchResumenClientes();   // Actualiza panel de resumen
      }
  };


  if(chkATMs)     chkATMs.onchange     = ()=> fetchIntegral();
  if(chkOficinas) chkOficinas.onchange = ()=> fetchIntegral();
  if(chkAgentes)  chkAgentes.onchange  = ()=> fetchIntegral();

  // ======================================================================
  // MOD — Exclusividad ATMs vs Clientes + control visual completo
  // ======================================================================
  chkHeat.onchange = ()=>{

      if (chkHeat.checked){

          // 🔹 Si se enciende el heatmap de ATMs, apagar el heatmap de clientes
          chkHeatClientes.checked = false;                     // NUEVO

          // Limpiar heatmap de clientes
          heatClientes.setLatLngs([]);                         // NUEVO
          if (map.hasLayer(heatClientes)) map.removeLayer(heatClientes);  // NUEVO

          // Encender ATMs
          //if (!map.hasLayer(heat)) map.addLayer(heat); //LO DEJAMOS PORSI
          fetchPoints(); 

      } else {

          // Apagar ATMs
          heat.setLatLngs([]);
          if (map.hasLayer(heat)) map.removeLayer(heat);

          // Si clientes está marcado, volver a activar su heatmap
          if (chkHeatClientes.checked){                        // NUEVO
              fetchClientes();                                 // NUEVO
          }
      }
  };

  chkReco.onchange = () => {
    if (chkReco.checked){
        cargarRecomendaciones();
        markersReco.addTo(map);
    } else {
        map.removeLayer(markersReco);
    }
  };


  // ============================================================
  // NUEVO — Handler unificado para Heatmap Clientes
  // ============================================================
  chkHeatClientes.onchange = () => {

      if (chkHeatClientes.checked){

          // --- Mostrar panel clientes ---
          panelClientes.classList.remove("hidden");
          fetchResumenClientes();    // muestra el panel informativo

          // --- Exclusividad: desactiva Heatmap de ATMs ---
          chkHeat.checked = false;
          heat.setLatLngs([]);
          if (map.hasLayer(heat)) map.removeLayer(heat);

          // --- Cargar heatmap de clientes ---
          fetchClientes();

      } else {

          // Ocultar panel clientes
          panelClientes.classList.add("hidden");

          // Eliminar capa heatClientes
          heatClientes.setLatLngs([]);
          if (map.hasLayer(heatClientes)) map.removeLayer(heatClientes);
      }
  };



} else {
  selDep.onchange  = ()=>{ updateProvincias(); fetchPoints(); if (chkHeatClientes.checked) fetchResumenClientes();};
  selProv.onchange = ()=>{ updateDistritos(); fetchPoints(); if (chkHeatClientes.checked) fetchResumenClientes();};
  selDist.onchange = ()=>{ updateDivisiones(); fetchPoints(); if (chkHeatClientes.checked) fetchResumenClientes();};
  selDiv.onchange  = ()=> fetchPoints();

  // ============================================
  // Filtro de segmento — actualiza HEATMAP + PANEL
  // ============================================
  selSegmento.onchange = () => {
      if (chkHeatClientes.checked){
          fetchClientes();          // Actualiza heatmap de clientes
          fetchResumenClientes();   // Actualiza panel de resumen
      }
  };


  if (selTipoATM)  selTipoATM.onchange  = () => fetchPoints();
  if (selUbicATM)  selUbicATM.onchange  = () => fetchPoints();

  // ======================================================================
  // MOD — Exclusividad ATMs vs Clientes + control visual completo
  // ======================================================================
  chkHeat.onchange = ()=>{

      if (chkHeat.checked){

          // 🔹 Si se enciende el heatmap de ATMs, apagar el heatmap de clientes
          chkHeatClientes.checked = false;                     // NUEVO

          // Limpiar heatmap de clientes
          heatClientes.setLatLngs([]);                         // NUEVO
          if (map.hasLayer(heatClientes)) map.removeLayer(heatClientes);  // NUEVO

          // Encender ATMs
          //if (!map.hasLayer(heat)) map.addLayer(heat); //LO DEJAMOS PORSI
          fetchPoints(); 

      } else {

          // Apagar ATMs
          heat.setLatLngs([]);
          if (map.hasLayer(heat)) map.removeLayer(heat);

          // Si clientes está marcado, volver a activar su heatmap
          if (chkHeatClientes.checked){                        // NUEVO
              fetchClientes();                                 // NUEVO
          }
      }
  };

  // ============================================================
  // NUEVO — Handler unificado para Heatmap Clientes
  // ============================================================
  chkHeatClientes.onchange = () => {

      if (chkHeatClientes.checked){

          // --- Mostrar panel clientes ---
          panelClientes.classList.remove("hidden");
          fetchResumenClientes();    // muestra el panel informativo

          // --- Exclusividad: desactiva Heatmap de ATMs ---
          chkHeat.checked = false;
          heat.setLatLngs([]);
          if (map.hasLayer(heat)) map.removeLayer(heat);

          // --- Cargar heatmap de clientes ---
          fetchClientes();

      } else {

          // Ocultar panel clientes
          panelClientes.classList.add("hidden");

          // Eliminar capa heatClientes
          heatClientes.setLatLngs([]);
          if (map.hasLayer(heatClientes)) map.removeLayer(heatClientes);
      }
  };


}

// =============================================================
// Handler UNIVERSAL para capa de Recomendaciones (⚡)
// Funciona para TODAS las vistas (ATM, Agentes, Oficinas, Integral)
// =============================================================
chkReco.onchange = () => {

    if (chkReco.checked){
        // Recargar datos
        cargarRecomendaciones();

        // Asegurar que la capa se dibuje
        if (!map.hasLayer(markersReco)){
            markersReco.addTo(map);
        }
    } else {
        // Eliminar la capa
        if (map.hasLayer(markersReco)){
            map.removeLayer(markersReco);
        }
    }
};


// Inicializar combos y render
updateProvincias();
if(TIPO_MAPA === "integral"){
  syncIntegralPanelsVisibility();
  fetchIntegral();
} else {
  syncSinglePanelsVisibility();
  fetchPoints();
}

// ======================================================================
// NUEVO — Recargar heatmap de CLIENTES cuando se hace zoom (si está activo)
// ======================================================================
map.on("zoomend", ()=>{       
  if (chkHeatClientes.checked){
    fetchClientes();
  }
});

// ======================================================================
// NUEVO — Si Clientes viene activado al cargar, pintarlo
// ======================================================================
if (chkHeatClientes.checked){             // NUEVO
    fetchClientes();                      // NUEVO
}

</script>

</body>
</html>
"""


if __name__ == "__main__":
    app.run(debug=True)


    