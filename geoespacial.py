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

# TRX es promedio de transacciones (pero lo sumamos en resumen)
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
# 3. LISTAS PARA FILTROS — JERARQUÍA POR CADA CAPA
#    (SIN MEZCLAR ISLAS / AGENTES / OFICINAS)
# ============================================================

# --------- DEPARTAMENTOS POR CAPA ----------
DEPARTAMENTOS_ISLAS = sorted(df[COL_DEPT].dropna().astype(str).unique())
DEPARTAMENTOS_AGENTES = sorted(df_agentes[COLA_DEPT].dropna().astype(str).unique())
DEPARTAMENTOS_OFICINAS = sorted(df_oficinas[COLF_DEPT].dropna().astype(str).unique())

# --------- PROVINCIAS POR CAPA ----------
PROVINCIAS_ISLAS_BY_DEPT = {}
for d in DEPARTAMENTOS_ISLAS:
    provs = df[df[COL_DEPT] == d][COL_PROV].dropna().astype(str).unique().tolist()
    PROVINCIAS_ISLAS_BY_DEPT[d] = sorted(set(provs))

PROVINCIAS_AGENTES_BY_DEPT = {}
for d in DEPARTAMENTOS_AGENTES:
    provs = df_agentes[df_agentes[COLA_DEPT] == d][COLA_PROV].dropna().astype(str).unique().tolist()
    PROVINCIAS_AGENTES_BY_DEPT[d] = sorted(set(provs))

PROVINCIAS_OFICINAS_BY_DEPT = {}
for d in DEPARTAMENTOS_OFICINAS:
    provs = df_oficinas[df_oficinas[COLF_DEPT] == d][COLF_PROV].dropna().astype(str).unique().tolist()
    PROVINCIAS_OFICINAS_BY_DEPT[d] = sorted(set(provs))

# --------- DISTRITOS POR CAPA ----------
PROVS_ISLAS = sorted(df[COL_PROV].dropna().astype(str).unique())
DIST_ISLAS_BY_PROV = {}
for p in PROVS_ISLAS:
    dists = df[df[COL_PROV] == p][COL_DIST].dropna().astype(str).unique().tolist()
    DIST_ISLAS_BY_PROV[p] = sorted(set(dists))

PROVS_AGENTES = sorted(df_agentes[COLA_PROV].dropna().astype(str).unique())
DIST_AGENTES_BY_PROV = {}
for p in PROVS_AGENTES:
    dists = df_agentes[df_agentes[COLA_PROV] == p][COLA_DIST].dropna().astype(str).unique().tolist()
    DIST_AGENTES_BY_PROV[p] = sorted(set(dists))

PROVS_OFICINAS = sorted(df_oficinas[COLF_PROV].dropna().astype(str).unique())
DIST_OFICINAS_BY_PROV = {}
for p in PROVS_OFICINAS:
    dists = df_oficinas[df_oficinas[COLF_PROV] == p][COLF_DIST].dropna().astype(str).unique().tolist()
    DIST_OFICINAS_BY_PROV[p] = sorted(set(dists))

# --------- DIVISIONES POR CAPA ----------
# ISLAS
DIV_ISLAS_BY_DEPT = {}
for d in DEPARTAMENTOS_ISLAS:
    divs = df[df[COL_DEPT] == d][COL_DIV].dropna().astype(str).unique().tolist()
    DIV_ISLAS_BY_DEPT[d] = sorted(set(divs))

DIV_ISLAS_BY_PROV = {}
for p in PROVS_ISLAS:
    divs = df[df[COL_PROV] == p][COL_DIV].dropna().astype(str).unique().tolist()
    DIV_ISLAS_BY_PROV[p] = sorted(set(divs))

DISTS_ISLAS = sorted(df[COL_DIST].dropna().astype(str).unique())
DIV_ISLAS_BY_DIST = {}
for di in DISTS_ISLAS:
    divs = df[df[COL_DIST] == di][COL_DIV].dropna().astype(str).unique().tolist()
    DIV_ISLAS_BY_DIST[di] = sorted(set(divs))

DIVISIONES_ISLAS = sorted(df[COL_DIV].dropna().astype(str).unique())

# AGENTES
DIV_AGENTES_BY_DEPT = {}
for d in DEPARTAMENTOS_AGENTES:
    divs = df_agentes[df_agentes[COLA_DEPT] == d][COLA_DIV].dropna().astype(str).unique().tolist()
    DIV_AGENTES_BY_DEPT[d] = sorted(set(divs))

DIV_AGENTES_BY_PROV = {}
for p in PROVS_AGENTES:
    divs = df_agentes[df_agentes[COLA_PROV] == p][COLA_DIV].dropna().astype(str).unique().tolist()
    DIV_AGENTES_BY_PROV[p] = sorted(set(divs))

DISTS_AGENTES = sorted(df_agentes[COLA_DIST].dropna().astype(str).unique())
DIV_AGENTES_BY_DIST = {}
for di in DISTS_AGENTES:
    divs = df_agentes[df_agentes[COLA_DIST] == di][COLA_DIV].dropna().astype(str).unique().tolist()
    DIV_AGENTES_BY_DIST[di] = sorted(set(divs))

DIVISIONES_AGENTES = sorted(df_agentes[COLA_DIV].dropna().astype(str).unique())

# OFICINAS
DIV_OFICINAS_BY_DEPT = {}
for d in DEPARTAMENTOS_OFICINAS:
    divs = df_oficinas[df_oficinas[COLF_DEPT] == d][COLF_DIV].dropna().astype(str).unique().tolist()
    DIV_OFICINAS_BY_DEPT[d] = sorted(set(divs))

DIV_OFICINAS_BY_PROV = {}
for p in PROVS_OFICINAS:
    divs = df_oficinas[df_oficinas[COLF_PROV] == p][COLF_DIV].dropna().astype(str).unique().tolist()
    DIV_OFICINAS_BY_PROV[p] = sorted(set(divs))

DISTS_OFICINAS = sorted(df_oficinas[COLF_DIST].dropna().astype(str).unique())
DIV_OFICINAS_BY_DIST = {}
for di in DISTS_OFICINAS:
    divs = df_oficinas[df_oficinas[COLF_DIST] == di][COLF_DIV].dropna().astype(str).unique().tolist()
    DIV_OFICINAS_BY_DIST[di] = sorted(set(divs))

DIVISIONES_OFICINAS = sorted(df_oficinas[COLF_DIV].dropna().astype(str).unique())


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
    <div class="card-title"><span class="icon">🌐</span>ATMs</div>
  </div>

  <div class="card" onclick="location.href='/mapa/agentes'">
    <img src="{{ url_for('static', filename='agente.png') }}" alt="Agentes BBVA">
    <div class="card-title"><span class="icon">🧍</span>Agentes</div>
  </div>

  <div class="card" onclick="location.href='/mapa/integral'">
    <img src="{{ url_for('static', filename='integral.png') }}" alt="Mapa Integral BBVA">
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


# ============================================================
# 6. RUTA DEL MAPA POR CAPA
# ============================================================
@app.route("/mapa/<tipo>")
@login_required
def mapa_tipo(tipo):
    if tipo not in ["oficinas", "islas", "agentes"]:
        return "No existe esa capa", 404

    initial_center = df[[COL_LAT, COL_LON]].mean().tolist()

    # Elegir listas SEGÚN LA CAPA (sin mezclar)
    if tipo == "islas":
        departamentos = DEPARTAMENTOS_ISLAS
        provincias_by_dept = PROVINCIAS_ISLAS_BY_DEPT
        dist_by_prov = DIST_ISLAS_BY_PROV
        div_by_dept = DIV_ISLAS_BY_DEPT
        div_by_prov = DIV_ISLAS_BY_PROV
        div_by_dist = DIV_ISLAS_BY_DIST
        divisiones = DIVISIONES_ISLAS
    elif tipo == "agentes":
        departamentos = DEPARTAMENTOS_AGENTES
        provincias_by_dept = PROVINCIAS_AGENTES_BY_DEPT
        dist_by_prov = DIST_AGENTES_BY_PROV
        div_by_dept = DIV_AGENTES_BY_DEPT
        div_by_prov = DIV_AGENTES_BY_PROV
        div_by_dist = DIV_AGENTES_BY_DIST
        divisiones = DIVISIONES_AGENTES
    else:  # oficinas
        departamentos = DEPARTAMENTOS_OFICINAS
        provincias_by_dept = PROVINCIAS_OFICINAS_BY_DEPT
        dist_by_prov = DIST_OFICINAS_BY_PROV
        div_by_dept = DIV_OFICINAS_BY_DEPT
        div_by_prov = DIV_OFICINAS_BY_PROV
        div_by_dist = DIV_OFICINAS_BY_DIST
        divisiones = DIVISIONES_OFICINAS

    return render_template_string(
        TEMPLATE_MAPA,
        tipo_mapa=tipo,
        departamentos=departamentos,
        provincias_by_dept=provincias_by_dept,
        dist_by_prov=dist_by_prov,
        div_by_dept=div_by_dept,
        div_by_prov=div_by_prov,
        div_by_dist=div_by_dist,
        divisiones=divisiones,
        initial_center=initial_center,
        initial_zoom=6,
    )


# ============================================================
# 6B. RUTA MAPA INTEGRAL (OFICINAS + ATMs + AGENTES)
# ============================================================
@app.route("/mapa/integral")
@login_required
def mapa_integral():
    initial_center = df[[COL_LAT, COL_LON]].mean().tolist()

    # Para integral usamos las listas de ISLAS (las más completas)
    return render_template_string(
        TEMPLATE_MAPA,
        tipo_mapa="integral",
        departamentos=DEPARTAMENTOS_ISLAS,
        provincias_by_dept=PROVINCIAS_ISLAS_BY_DEPT,
        dist_by_prov=DIST_ISLAS_BY_PROV,
        div_by_dept=DIV_ISLAS_BY_DEPT,
        div_by_prov=DIV_ISLAS_BY_PROV,
        div_by_dist=DIV_ISLAS_BY_DIST,
        divisiones=DIVISIONES_ISLAS,
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

    # 🔵 NUEVOS FILTROS SOLO PARA CAPA ISLAS (ATMs)
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

        # 🔵 Filtro por Tipo de ATM (DISPENSADOR / MONEDERO / RECICLADOR)
        if tipo_atm:
            dff = dff[dff[COL_TIPO].str.contains(tipo_atm, na=False)]

        # 🔵 Filtro por Ubicación ATM (OFICINA / ISLA)
        if ubic_atm:
            dff = dff[dff[COL_UBIC].str.contains(ubic_atm, na=False)]

        dff_layer = dff

        total_atms = int(len(dff_layer))
        # 🔵 SUMA TOTAL DE TRANSACCIONES
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
        # 🔵 SUMA TOTAL DE TRANSACCIONES
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
        # 🔵 SUMA TOTAL DE TRX
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

    # Capa desconocida
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

/* PANEL FLOTANTE INDIVIDUAL */
.panel-floating{
  position:absolute;
  right:20px;
  width:320px;
  background:white;
  border-radius:12px;
  padding:14px 16px;
  box-shadow:0 8px 26px rgba(0,0,0,0.20);
  font-size:13px;
  z-index:9999;
  display:none;
}

.panel-title{
  font-weight:700;
  margin-bottom:6px;
  font-size:15px;
  color:#072146;
}

.panel-section{
  margin-top:6px;
  padding:8px 0;
  border-top:1px solid #d0d7e3;
}

#panelATMdetalle{
  white-space:pre-line;
  font-family:"Consolas","Fira Code",monospace;
  font-size:12px;
}

/* Posiciones verticales de las ventanas cuando varias están activas */
#panelATMs   { top:120px; }
#panelOficinas { top:330px; }
#panelAgentes  { top:540px; }

/* MAPA */
#map{
  height:82vh;
  margin:20px;
  border-radius:12px;
  box-shadow:0 8px 24px rgba(0,0,0,0.18);
}

/* Controles superiores */
.topbar{
  padding:16px 20px 6px 20px;
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
      <label style="margin-left:10px;">
        <span style="color:#072146; font-weight:600;">Canales:</span>
        <span style="display:flex; gap:10px; margin-left:6px;">
          <label><input type="checkbox" id="chkATMs" checked> ATMs</label>
          <label><input type="checkbox" id="chkOficinas" checked> Oficinas</label>
          <label><input type="checkbox" id="chkAgentes" checked> Agentes</label>
        </span>
      </label>
    {% endif %}

    <label style="margin-left:20px;">
      <input type="checkbox" id="chkHeat" checked> Heatmap
    </label>

    <div style="flex:1"></div>

    <div style="font-size:13px; color:var(--muted);">
      Mostrando <span id="infoCount">--</span> puntos
    </div>

  </div>
</div>


<!-- MAPA -->
<div id="map"></div>


<!-- =========================== -->
<!-- PANELS FLOATING INDIVIDUALES -->
<!-- =========================== -->

<!-- PANEL ATMs -->
<div id="panelATMs" class="panel-floating">
  <div class="panel-title">ATMs</div>
  <div class="panel-section">Total: <b><span id="atmTotal">0</span></b></div>
  <div class="panel-section">
    Oficina: <span id="atmOficina">0</span><br>
    Isla: <span id="atmIsla">0</span>
  </div>
  <div class="panel-section">
    Dispensador: <span id="atmDisp">0</span><br>
    Monedero: <span id="atmMon">0</span><br>
    Reciclador: <span id="atmRec">0</span>
  </div>
  <div class="panel-section">
    <b>Suma TRX:</b> <span id="atmSuma">0</span>
  </div>
</div>

<!-- PANEL OFICINAS -->
<div id="panelOficinas" class="panel-floating">
  <div class="panel-title">Oficinas</div>
  <div class="panel-section">Cantidad total: <b><span id="ofiTotal">0</span></b></div>
  <div class="panel-section"><b>Suma TRX:</b> <span id="ofiSuma">0</span></div>
</div>

<!-- PANEL AGENTES -->
<div id="panelAgentes" class="panel-floating">
  <div class="panel-title">Agentes</div>
  <div class="panel-section">
    Total: <b><span id="agTotal">0</span></b>
  </div>
  <div class="panel-section">
    A1: <span id="agA1">0</span><br>
    A2: <span id="agA2">0</span><br>
    A3: <span id="agA3">0</span><br>
    B : <span id="agB">0</span><br>
    C : <span id="agC">0</span>
  </div>
  <div class="panel-section">
    <b>Suma TRX:</b> <span id="agSuma">0</span>
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


// ======================================================
// ÍCONOS
// ======================================================

const ICON_ATM_OFICINA = L.icon({
  iconUrl: "{{ url_for('static', filename='atm_oficina.png') }}",
  iconSize: [40,40],
  iconAnchor:[20,20],
  popupAnchor:[0,-18]
});
const ICON_ATM_ISLA = L.icon({
  iconUrl: "{{ url_for('static', filename='atm_isla.png') }}",
  iconSize: [40,40],
  iconAnchor:[20,20],
  popupAnchor:[0,-18]
});
const ICON_OFICINA = L.icon({
  iconUrl: "{{ url_for('static', filename='oficina.png') }}",
  iconSize: [40,40],
  iconAnchor:[20,20],
  popupAnchor:[0,-18]
});
const ICON_AGENTE = L.icon({
  iconUrl: "{{ url_for('static', filename='agente.png') }}",
  iconSize: [40,40],
  iconAnchor:[20,20],
  popupAnchor:[0,-18]
});


function getIcon(pt){
  const ubic = (pt.ubicacion || "").toUpperCase();

  if(TIPO_MAPA === "agentes") return ICON_AGENTE;
  if(TIPO_MAPA === "oficinas") return ICON_OFICINA;

  if(TIPO_MAPA === "islas"){
    if(ubic.includes("OFICINA")) return ICON_ATM_OFICINA;
    if(ubic.includes("ISLA"))    return ICON_ATM_ISLA;
    return ICON_ATM_ISLA;
  }

  // En integral se usará directo según canal
  return ICON_ATM_ISLA;
}


// ======================================================
// MAPA
// ======================================================

const map = L.map("map").setView(INITIAL_CENTER, INITIAL_ZOOM);
L.tileLayer("https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png",{maxZoom:19}).addTo(map);

const markers = L.markerClusterGroup({ chunkedLoading:true });
const heat    = L.heatLayer([], { radius:28, blur:22 });

markers.addTo(map);
heat.addTo(map);


// ======================================================
// COMBOS DEPENDIENTES
// ======================================================

const selDep  = document.getElementById("selDepartamento");
const selProv = document.getElementById("selProvincia");
const selDist = document.getElementById("selDistrito");
const selDiv  = document.getElementById("selDivision");

const selTipoATM = document.getElementById("selTipoATM");
const selUbicATM = document.getElementById("selUbicacionATM");

function updateProvincias(){
  let d = selDep.value;
  selProv.innerHTML = '<option value="">-- Todas --</option>';
  if(d && PROV_BY_DEPT[d]){
    PROV_BY_DEPT[d].forEach(p=>{
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
    DIST_BY_PROV[p].forEach(x=>{
      selDist.innerHTML += `<option value="${x}">${x}</option>`;
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
    DIV_BY_DIST[di].forEach(x=> selDiv.innerHTML += `<option value="${x}">${x}</option>`);
    return;
  }
  if(p && DIV_BY_PROV[p]){
    DIV_BY_PROV[p].forEach(x=> selDiv.innerHTML += `<option value="${x}">${x}</option>`);
    return;
  }
  if(d && DIV_BY_DEPT[d]){
    DIV_BY_DEPT[d].forEach(x=> selDiv.innerHTML += `<option value="${x}">${x}</option>`);
    return;
  }

  {{ divisiones|tojson }}.forEach(x=> selDiv.innerHTML += `<option value="${x}">${x}</option>`);
}

// ======================================================
// PANEL DETALLE (FLotante independiente)
// ======================================================

const panelATMs      = document.getElementById("panelATMs");
const panelOficinas  = document.getElementById("panelOficinas");
const panelAgentes   = document.getElementById("panelAgentes");

// Panel detalle:
const panelATMdetalle = document.getElementById("panelATMdetalle") || null;

// (Creamos dinámicamente el panel de detalle)
let panelDetalle = document.createElement("div");
panelDetalle.id = "panelDetalle";
panelDetalle.className = "panel-floating";
panelDetalle.style.top = "750px";  // debajo de los 3 paneles
panelDetalle.style.display = "none";
panelDetalle.innerHTML = `
  <div class="panel-title">Detalle del Punto</div>
  <pre id="detalleTexto" style="white-space:pre-line; font-size:12px;"></pre>
  <button id="btnCerrarDetalle" style="
      margin-top:10px;
      padding:6px 12px;
      background:#1464A5;
      color:white;
      border:none;
      border-radius:8px;
      cursor:pointer;
    ">Cerrar</button>
`;
document.body.appendChild(panelDetalle);

const detalleTexto = document.getElementById("detalleTexto");
const btnCerrarDetalle = document.getElementById("btnCerrarDetalle");

btnCerrarDetalle.onclick = () => {
  panelDetalle.style.display = "none";
};


// ======================================================
// FUNCIÓN showDetalle(pt) — Cuando clickeas un marcador
// ======================================================

function showDetalle(pt){
  let titulo = "";
  let texto  = "";
  let geo = `${pt.departamento} / ${pt.provincia} / ${pt.distrito}`;

  if(pt.tipo_canal === "AGENTE" || TIPO_MAPA === "agentes"){
    titulo = `AGENTE ${pt.atm}`;
    texto = `
Comercio: ${pt.nombre}
Capa: ${pt.capa}
División: ${pt.division}
Dirección: ${pt.direccion}

Ubicación:
${geo}

Trxs Octubre: ${pt.trxs_oct ?? 0}
Trxs Noviembre: ${pt.trxs_nov ?? 0}

Promedio: ${pt.promedio}
`;

  } else if(pt.tipo_canal === "OFICINA" || TIPO_MAPA === "oficinas"){
    titulo = `OFICINA ${pt.atm}`;
    texto = `
Nombre: ${pt.nombre}
División: ${pt.division}

Ubicación:
${geo}

Promedio TRX: ${pt.promedio}
`;

  } else {
    // ATM
    titulo = `ATM ${pt.atm}`;
    texto = `
Nombre: ${pt.nombre}
Tipo: ${pt.tipo}
Ubicación ATM: ${pt.ubicacion}
División: ${pt.division}
Dirección: ${pt.direccion}

Ubicación:
${geo}

Promedio TRX: ${pt.promedio}
`;
  }

  panelDetalle.querySelector(".panel-title").textContent = titulo;
  detalleTexto.textContent = texto;
  panelDetalle.style.display = "block";
}




// ======================================================
// FETCH + RENDER PARA CAPAS INDIVIDUALES (NO INTEGRAL)
// ======================================================

async function fetchPoints(){
  if(TIPO_MAPA === "integral") return; // integral usa su propio fetch

  const d  = selDep.value;
  const p  = selProv.value;
  const di = selDist.value;
  const dv = selDiv.value;

  const tipo_atm = selTipoATM ? selTipoATM.value : "";
  const ubic_atm = selUbicATM ? selUbicATM.value : "";

  const qs =
    `tipo=${encodeURIComponent(TIPO_MAPA)}` +
    `&departamento=${encodeURIComponent(d)}` +
    `&provincia=${encodeURIComponent(p)}` +
    `&distrito=${encodeURIComponent(di)}` +
    `&division=${encodeURIComponent(dv)}` +
    `&tipo_atm=${encodeURIComponent(tipo_atm)}` +
    `&ubic_atm=${encodeURIComponent(ubic_atm)}`;

  const res = await fetch(`/api/points?${qs}`);
  const data = await res.json();

  const pts = data.puntos || [];

  // Actualiza contador superior
  document.getElementById("infoCount").textContent = pts.length;

  // Limpiar capas
  markers.clearLayers();
  heat.setLatLngs([]);

  let bounds = [];
  let heatPts = [];

  pts.forEach(pt => {
    const icon = getIcon(pt);
    const m = L.marker([pt.lat, pt.lon], {icon});

    m.on("click", ()=> showDetalle(pt));   // 🟦 PANEL DETALLE FLOTANTE

    markers.addLayer(m);

    heatPts.push([pt.lat, pt.lon, Math.max(1, pt.promedio || 1)]);
    bounds.push([pt.lat, pt.lon]);
  });

  heat.setLatLngs(heatPts);

  // Ajuste de vista
  if(bounds.length === 1){
    map.setView(bounds[0], 16);
  } else if(bounds.length > 1){
    map.fitBounds(bounds, {padding:[20,20]});
  } else {
    map.setView(INITIAL_CENTER, INITIAL_ZOOM);
  }

  // Heatmap ON/OFF
  if(document.getElementById("chkHeat").checked){
    if(!map.hasLayer(heat)) heat.addTo(map);
  } else {
    if(map.hasLayer(heat)) map.removeLayer(heat);
  }

  // ==================================================
  //  ACTUALIZACIÓN DE LOS PANELES FLOTANTES SEGÚN CAPA
  // ==================================================

  if(TIPO_MAPA === "islas"){
    // Mostrar solo panel ATMs
    panelATMs.style.display = "block";
    panelOficinas.style.display = "none";
    panelAgentes.style.display = "none";

    atmTotal.textContent   = data.total_atms;
    atmOficina.textContent = data.total_oficinas;
    atmIsla.textContent    = data.total_islas;
    atmDisp.textContent    = data.total_disp;
    atmMon.textContent     = data.total_mon;
    atmRec.textContent     = data.total_rec;
    atmSuma.textContent    = Math.round(data.suma_total);

  } else if(TIPO_MAPA === "oficinas"){
    panelATMs.style.display = "none";
    panelOficinas.style.display = "block";
    panelAgentes.style.display = "none";

    ofiTotal.textContent = data.total_oficinas;
    ofiSuma.textContent  = Math.round(data.suma_total);

  } else if(TIPO_MAPA === "agentes"){
    panelATMs.style.display = "none";
    panelOficinas.style.display = "none";
    panelAgentes.style.display = "block";

    agTotal.textContent = data.total_agentes;
    agA1.textContent    = data.total_capa_A1;
    agA2.textContent    = data.total_capa_A2;
    agA3.textContent    = data.total_capa_A3;
    agB.textContent     = data.total_capa_B;
    agC.textContent     = data.total_capa_C;
    agSuma.textContent  = Math.round(data.suma_total);
  }
}


// ======================================================
// FETCH + RENDER MODO INTEGRAL (3 CAPAS A LA VEZ)
// ======================================================

const chkATMs     = document.getElementById("chkATMs");
const chkOficinas = document.getElementById("chkOficinas");
const chkAgentes  = document.getElementById("chkAgentes");

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

  const res = await fetch(`/api/points_integral?${qs}`);
  const data = await res.json();

  markers.clearLayers();
  heat.setLatLngs([]);

  let bounds = [];
  let heatPts = [];

  // =======================
  //        ATMs
  // =======================
  if(chkATMs.checked){
    (data.atms || []).forEach(pt=>{
      const icon = pt.ubicacion.includes("OFICINA") ? ICON_ATM_OFICINA : ICON_ATM_ISLA;
      const m = L.marker([pt.lat, pt.lon], {icon});
      m.on("click", ()=> showDetalle(pt));
      markers.addLayer(m);

      heatPts.push([pt.lat, pt.lon, Math.max(1, pt.promedio || 1)]);
      bounds.push([pt.lat, pt.lon]);
    });
  }

  // =======================
  //       OFICINAS
  // =======================
  if(chkOficinas.checked){
    (data.oficinas || []).forEach(pt=>{
      const m = L.marker([pt.lat, pt.lon], {icon: ICON_OFICINA});
      m.on("click", ()=> showDetalle(pt));
      markers.addLayer(m);
      bounds.push([pt.lat, pt.lon]);
    });
  }

  // =======================
  //        AGENTES
  // =======================
  if(chkAgentes.checked){
    (data.agentes || []).forEach(pt=>{
      const m = L.marker([pt.lat, pt.lon], {icon: ICON_AGENTE});
      m.on("click", ()=> showDetalle(pt));
      markers.addLayer(m);
      bounds.push([pt.lat, pt.lon]);
    });
  }

  heat.setLatLngs(heatPts);


  // Ajustar vista
  if(bounds.length === 1){
    map.setView(bounds[0], 16);
  } else if(bounds.length > 1){
    map.fitBounds(bounds, {padding:[20,20]});
  } else {
    map.setView(INITIAL_CENTER, INITIAL_ZOOM);
  }


  // ==================================================
  // PANEL FLOTANTE — MOSTRAR SEGÚN CHECKBOX
  // ==================================================

  // PANEL ATMs
  if(chkATMs.checked){
    panelATMs.style.display = "block";
    atmTotal.textContent = data.total_atms;
    atmOficina.textContent = data.atms.filter(x=>x.ubicacion.includes("OFICINA")).length;
    atmIsla.textContent    = data.atms.filter(x=>x.ubicacion.includes("ISLA")).length;
    atmDisp.textContent    = data.atms.filter(x=>x.tipo.includes("DISP")).length;
    atmMon.textContent     = data.atms.filter(x=>x.tipo.includes("MON")).length;
    atmRec.textContent     = data.atms.filter(x=>x.tipo.includes("REC")).length;
    atmSuma.textContent    = Math.round(data.suma_atms);
  } else {
    panelATMs.style.display = "none";
  }

  // PANEL OFICINAS
  if(chkOficinas.checked){
    panelOficinas.style.display = "block";
    ofiTotal.textContent = data.total_oficinas;
    ofiSuma.textContent  = Math.round(data.suma_oficinas);
  } else {
    panelOficinas.style.display = "none";
  }

  // PANEL AGENTES
  if(chkAgentes.checked){
    panelAgentes.style.display = "block";
    agTotal.textContent = data.total_agentes;
    agA1.textContent = data.agentes.filter(x=>x.capa==="A1").length;
    agA2.textContent = data.agentes.filter(x=>x.capa==="A2").length;
    agA3.textContent = data.agentes.filter(x=>x.capa==="A3").length;
    agB.textContent  = data.agentes.filter(x=>x.capa==="B").length;
    agC.textContent  = data.agentes.filter(x=>x.capa==="C").length;
    agSuma.textContent = Math.round(data.suma_agentes);
  } else {
    panelAgentes.style.display = "none";
  }

  // Actualizar contador superior
  document.getElementById("infoCount").textContent =
      (chkATMs.checked     ? data.total_atms     : 0) +
      (chkOficinas.checked ? data.total_oficinas : 0) +
      (chkAgentes.checked  ? data.total_agentes  : 0);
}


// ======================================================
// EVENTOS (INTEGRAL vs NORMAL)
// ======================================================

if(TIPO_MAPA === "integral"){

  selDep.onchange  = ()=>{ updateProvincias(); fetchIntegral(); };
  selProv.onchange = ()=>{ updateDistritos(); fetchIntegral(); };
  selDist.onchange = ()=>{ updateDivisiones(); fetchIntegral(); };
  selDiv.onchange  = ()=> fetchIntegral();

  chkATMs.onchange     = ()=> fetchIntegral();
  chkOficinas.onchange = ()=> fetchIntegral();
  chkAgentes.onchange  = ()=> fetchIntegral();

  document.getElementById("chkHeat").onchange = ()=>{
    if(chkHeat.checked){
      if(!map.hasLayer(heat)) heat.addTo(map);
    } else {
      if(map.hasLayer(heat)) map.removeLayer(heat);
    }
  };

  // Primera carga integral
  updateProvincias();
  fetchIntegral();

} else {

  // Capas individuales
  selDep.onchange  = ()=>{ updateProvincias(); fetchPoints(); };
  selProv.onchange = ()=>{ updateDistritos(); fetchPoints(); };
  selDist.onchange = ()=>{ updateDivisiones(); fetchPoints(); };
  selDiv.onchange  = ()=> fetchPoints();

  if(selTipoATM) selTipoATM.onchange = ()=> fetchPoints();
  if(selUbicATM) selUbicATM.onchange = ()=> fetchPoints();

  document.getElementById("chkHeat").onchange = ()=>{
    if(chkHeat.checked){
      if(!map.hasLayer(heat)) heat.addTo(map);
    } else {
      if(map.hasLayer(heat)) map.removeLayer(heat);
    }
  };

  // Primera carga normal
  updateProvincias();
  fetchPoints();
}

</script>

</body>
</html>
"""

if __name__ == "__main__":
    app.run(debug=True)