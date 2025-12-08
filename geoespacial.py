# ============================================================
#   BACKEND COMPLETO + LOGIN + SELECTOR
#   CAPAS: ISLAS (ATMs) + AGENTES + OFICINAS
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
DIVISIONES_ISLAS = sorted(df[COL_DIV].dropna().astype(str).unique())
DIVISIONES_AGENTES = sorted(df_agentes[COLA_DIV].dropna().astype(str).unique())
DIVISIONES_OFICINAS = sorted(df_oficinas[COLF_DIV].dropna().astype(str).unique())

# ============================================================
# 3B. CREAR LISTAS COMBINADAS PARA CAPA INTEGRAL
# ============================================================

DEPARTAMENTOS_INTEGRAL = sorted(
    set(DEPARTAMENTOS_ISLAS)
    | set(DEPARTAMENTOS_AGENTES)
    | set(DEPARTAMENTOS_OFICINAS)
)

# Provincias por departamento
PROVINCIAS_INTEGRAL_BY_DEPT = {}
for d in DEPARTAMENTOS_INTEGRAL:
    provs = []
    provs += PROVINCIAS_ISLAS_BY_DEPT.get(d, [])
    provs += PROVINCIAS_AGENTES_BY_DEPT.get(d, [])
    provs += PROVINCIAS_OFICINAS_BY_DEPT.get(d, [])
    PROVINCIAS_INTEGRAL_BY_DEPT[d] = sorted(set(provs))

# Distritos por provincia
DIST_INTEGRAL_BY_PROV = {}
for p in set(PROVS_ISLAS) | set(PROVS_AGENTES) | set(PROVS_OFICINAS):
    dists = []
    dists += DIST_ISLAS_BY_PROV.get(p, [])
    dists += DIST_AGENTES_BY_PROV.get(p, [])
    dists += DIST_OFICINAS_BY_PROV.get(p, [])
    DIST_INTEGRAL_BY_PROV[p] = sorted(set(dists))

# Divisiones combinadas
DIVISIONES_INTEGRAL = sorted(
    set(DIVISIONES_ISLAS)
    | set(DIVISIONES_AGENTES)
    | set(DIVISIONES_OFICINAS)
)

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


# ============================================================
# 5. SELECTOR DE CAPAS — NUEVA CARD “INTEGRAL”
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

  <!-- NUEVA CARD INTEGRAL -->
  <div class="card" onclick="location.href='/mapa/integral'">
    <img src="{{ url_for('static', filename='integral.png') }}" alt="Integral">
    <div class="card-title"><span class="icon">🌎</span>Integral</div>
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
# 7. API /api/points — INCLUYE CAPA INTEGRAL
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

    # ========================================================
    # 🟦 CAPA INTEGRAL — ATMs + AGENTES + OFICINAS
    # ========================================================
    if tipo_mapa == "integral":

        puntos = []
        suma_total_global = 0
        total_atms = 0
        total_agentes = 0
        total_oficinas = 0

        # =======================
        # 1) ISLAS / ATMs
        # =======================
        dff = df.copy()
        dff[COL_DEPT] = dff[COL_DEPT].astype(str).str.upper().str.strip()
        dff[COL_PROV] = dff[COL_PROV].astype(str).str.upper().str.strip()
        dff[COL_DIST] = dff[COL_DIST].astype(str).str.upper().str.strip()
        dff[COL_DIV]  = dff[COL_DIV].astype(str).str.upper().str.strip()
        dff[COL_UBIC] = dff[COL_UBIC].astype(str).str.upper().str.strip()
        dff[COL_TIPO] = dff[COL_TIPO].astype(str).str.upper().str.strip()

        if dpto: dff = dff[dff[COL_DEPT] == dpto]
        if prov: dff = dff[dff[COL_PROV] == prov]
        if dist: dff = dff[dff[COL_DIST] == dist]
        if divi: dff = dff[dff[COL_DIV] == divi]

        if tipo_atm:
            dff = dff[dff[COL_TIPO].str.contains(tipo_atm, na=False)]
        if ubic_atm:
            dff = dff[dff[COL_UBIC].str.contains(ubic_atm, na=False)]

        for _, r in dff.iterrows():
            pt = {
                "lat": float(r[COL_LAT]),
                "lon": float(r[COL_LON]),
                "atm": str(r.get(COL_ATM, "")),
                "nombre": str(r.get(COL_NAME, "")),
                "promedio": float(r.get(PROM_COL, 0.0)),
                "division": str(r.get(COL_DIV, "")),
                "tipo": str(r.get(COL_TIPO, "")),
                "ubicacion": str(r.get(COL_UBIC, "")),
                "departamento": str(r.get(COL_DEPT, "")),
                "provincia": str(r.get(COL_PROV, "")),
                "distrito": str(r.get(COL_DIST, "")),
                "direccion": get_address(r[COL_LAT], r[COL_LON]),
                "canal": "ATM",
            }
            puntos.append(pt)

        total_atms = len(dff)
        suma_total_global += float(dff[PROM_COL].sum())

        # =======================
        # 2) AGENTES
        # =======================
        dfa = df_agentes.copy()
        dfa[COLA_DEPT] = dfa[COLA_DEPT].astype(str).str.upper().str.strip()
        dfa[COLA_PROV] = dfa[COLA_PROV].astype(str).str.upper().str.strip()
        dfa[COLA_DIST] = dfa[COLA_DIST].astype(str).str.upper().str.strip()
        dfa[COLA_DIV]  = dfa[COLA_DIV].astype(str).str.upper().str.strip()

        if dpto: dfa = dfa[dfa[COLA_DEPT] == dpto]
        if prov: dfa = dfa[dfa[COLA_PROV] == prov]
        if dist: dfa = dfa[dfa[COLA_DIST] == dist]
        if divi: dfa = dfa[dfa[COLA_DIV] == divi]

        for _, r in dfa.iterrows():
            pt = {
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
                "canal": "AGENTE",
            }
            puntos.append(pt)

        total_agentes = len(dfa)
        suma_total_global += float(dfa[PROMA_COL].sum())

        # =======================
        # 3) OFICINAS
        # =======================
        dfo = df_oficinas.copy()
        dfo[COLF_DEPT] = dfo[COLF_DEPT].astype(str).str.upper().str.strip()
        dfo[COLF_PROV] = dfo[COLF_PROV].astype(str).str.upper().str.strip()
        dfo[COLF_DIST] = dfo[COLF_DIST].astype(str).str.upper().str.strip()
        dfo[COLF_DIV]  = dfo[COLF_DIV].astype(str).str.upper().str.strip()

        if dpto: dfo = dfo[dfo[COLF_DEPT] == dpto]
        if prov: dfo = dfo[dfo[COLF_PROV] == prov]
        if dist: dfo = dfo[dfo[COLF_DIST] == dist]
        if divi: dfo = dfo[dfo[COLF_DIV] == divi]

        for _, r in dfo.iterrows():
            pt = {
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
                "canal": "OFICINA",
            }
            puntos.append(pt)

        total_oficinas = len(dfo)
        suma_total_global += float(dfo[COLF_TRX].sum())

        # =======================
        # RESPUESTA FINAL INTEGRAL
        # =======================
        return jsonify({
            "puntos": puntos,
            "total_atms": total_atms,
            "total_agentes": total_agentes,
            "total_oficinas": total_oficinas,
            "suma_total": suma_total_global,
        })
    

    # ============================================================
# 8. TEMPLATE MAPA — FRONTEND COMPLETO (CON CAPA INTEGRAL)
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
  {% elif tipo_mapa == 'integral' %}
    INTEGRAL
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

/* Panel detalle */
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

</style>
</head>

<body>

<header>
<h1>
  {% if tipo_mapa == 'islas' %}
    Mapa BBVA — ATMs
  {% elif tipo_mapa == 'integral' %}
    Mapa BBVA — Integral
  {% else %}
    Mapa BBVA — {{ tipo_mapa|upper }}
  {% endif %}
</h1>

<a href="/logout" class="logout">Cerrar sesión</a>
</header>

<div class="topbar">
  <div class="controls">

    <!-- FILTROS UNIVERSALES -->
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

    <!-- DIVISIONES SI APLICA -->
    {% if tipo_mapa != 'integral' %}
    <label>División:
      <select id="selDivision">
        <option value="">-- Todas --</option>
        {% for dv in divisiones %}
        <option value="{{dv}}">{{dv}}</option>
        {% endfor %}
      </select>
    </label>
    {% endif %}

    <!-- FILTROS SOLO PARA ATMs -->
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

    <!-- CONTROLES ESPECÍFICOS DE CAPA INTEGRAL -->
    {% if tipo_mapa == 'integral' %}
      <label>Mostrar ATMs <input type="checkbox" id="chkATM" checked></label>
      <label>Mostrar Agentes <input type="checkbox" id="chkAgente" checked></label>
      <label>Mostrar Oficinas <input type="checkbox" id="chkOficina" checked></label>
    {% endif %}

    <label style="margin-left:16px;">
      <input type="checkbox" id="chkHeat" checked> Heatmap
    </label>

    <div style="flex:1"></div>

    <div style="font-size:13px; color:var(--muted);">
      Mostrando <span id="infoCount">--</span> elementos
    </div>
  </div>
</div>

<div class="main">
  <div id="map"></div>

  <div class="side">
    <!-- PANEL RESUMEN -->
    <div id="panelResumen" class="side-card">
      <div class="side-title">Resumen</div>

      <div><b>Suma total de transacciones:</b> <span id="resSuma">0</span></div>

      <!-- BLOQUE INTEGRAL -->
      {% if tipo_mapa == 'integral' %}
        <div class="muted" style="margin-top:6px;">ATMs: <span id="resATMs">0</span></div>
        <div class="muted">Agentes: <span id="resAgentes">0</span></div>
        <div class="muted">Oficinas: <span id="resOficinas">0</span></div>
      {% endif %}

      <!-- BLOQUE EXISTENTE PARA ISLAS -->
      {% if tipo_mapa == 'islas' %}
        <div class="muted">ATMs totales: <span id="resTotal">0</span></div>
        <div class="muted">ATMs en oficinas: <span id="resOfi">0</span></div>
        <div class="muted">ATMs en islas: <span id="resIsla">0</span></div>
        <div class="muted">Dispensador: <span id="resDisp">0</span></div>
        <div class="muted">Monedero: <span id="resMon">0</span></div>
        <div class="muted">Reciclador: <span id="resRec">0</span></div>
      {% endif %}

      {% if tipo_mapa == 'agentes' %}
        <div class="muted">Agentes: <span id="resAgentesTotal">0</span></div>
      {% endif %}

      {% if tipo_mapa == 'oficinas' %}
        <div class="muted">Oficinas: <span id="resOficinasCount">0</span></div>
      {% endif %}
    </div>

    <!-- PANEL DETALLE -->
    <div id="panelDetalle" class="side-card side-card-atm hidden">
      <h3 id="panelDetalleTitle">Detalle</h3>
      <div id="detalleContenido" style="font-size:12px;"></div>
      <button id="btnVolver" class="btn-small">VOLVER</button>
    </div>

  </div>
</div>

<script src="https://unpkg.com/leaflet@1.9.4/dist/leaflet.js"></script>
<script src="https://unpkg.com/leaflet.markercluster@1.5.3/dist/MarkerCluster.js"></script>
<script src="https://unpkg.com/leaflet.heat/dist/leaflet-heat.js"></script>

<script>



const TIPO_MAPA = "{{ tipo_mapa }}";
const INITIAL_CENTER = [{{ initial_center[0] }}, {{ initial_center[1] }}];
const INITIAL_ZOOM   = {{ initial_zoom }};

const PROV_BY_DEPT = {{ provincias_by_dept|tojson }};
const DIST_BY_PROV = {{ dist_by_prov|tojson }};
const DIVISIONES = {{ divisiones|tojson }};

// ======================================================
// ICONOS
// ======================================================
const ICON_ATM_OFICINA = L.icon({
  iconUrl: "{{ url_for('static', filename='atm_oficina.png') }}",
  iconSize: [40,40], iconAnchor:[20,20], popupAnchor:[0,-20]
});

const ICON_ATM_ISLA = L.icon({
  iconUrl: "{{ url_for('static', filename='atm_isla.png') }}",
  iconSize: [40,40], iconAnchor:[20,20], popupAnchor:[0,-20]
});

const ICON_OFICINA = L.icon({
  iconUrl: "{{ url_for('static', filename='oficina.png') }}",
  iconSize: [40,40], iconAnchor:[20,20], popupAnchor:[0,-20]
});

const ICON_AGENTE = L.icon({
  iconUrl: "{{ url_for('static', filename='agente.png') }}",
  iconSize: [40,40], iconAnchor:[20,20], popupAnchor:[0,-20]
});

// ======================================================
//  MAPA
// ======================================================
const map = L.map("map").setView(INITIAL_CENTER, INITIAL_ZOOM);
L.tileLayer('https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png',{maxZoom:19}).addTo(map);

const clusterATMs = L.markerClusterGroup({chunkedLoading:true});
const clusterAgentes = L.markerClusterGroup({chunkedLoading:true});
const clusterOficinas = L.markerClusterGroup({chunkedLoading:true});

const heat = L.heatLayer([], {radius:28, blur:22});

// ======================================================
// CONTROLES
// ======================================================
const selDep  = document.getElementById("selDepartamento");
const selProv = document.getElementById("selProvincia");
const selDist = document.getElementById("selDistrito");
const selDiv  = document.getElementById("selDivision");

const chkHeat = document.getElementById("chkHeat");

const chkATM     = document.getElementById("chkATM");
const chkAgente  = document.getElementById("chkAgente");
const chkOficina = document.getElementById("chkOficina");

// ======================================================
//  FUNCIONES DE COMBOS
// ======================================================
function updateProvincias(){
  let d = selDep.value;
  selProv.innerHTML = `<option value="">-- Todas --</option>`;
  if(d && PROV_BY_DEPT[d]){
    PROV_BY_DEPT[d].forEach(p => selProv.innerHTML += `<option value="${p}">${p}</option>`);
  }
  updateDistritos();
}

function updateDistritos(){
  let p = selProv.value;
  selDist.innerHTML = `<option value="">-- Todos --</option>`;
  if(p && DIST_BY_PROV[p]){
    DIST_BY_PROV[p].forEach(r => selDist.innerHTML += `<option value="${r}">${r}</option>`);
  }
}

selDep.onchange  = ()=>{ updateProvincias(); fetchPoints(); };
selProv.onchange = ()=>{ updateDistritos(); fetchPoints(); };
selDist.onchange = ()=> fetchPoints();
if(selDiv) selDiv.onchange = ()=> fetchPoints();

if(chkATM)     chkATM.onchange     = ()=> fetchPoints();
if(chkAgente)  chkAgente.onchange  = ()=> fetchPoints();
if(chkOficina) chkOficina.onchange = ()=> fetchPoints();

// ======================================================
// PANEL DETALLE
// ======================================================
const panelResumen = document.getElementById("panelResumen");
const panelDetalle = document.getElementById("panelDetalle");
const detalleContenido = document.getElementById("detalleContenido");
const btnVolver = document.getElementById("btnVolver");

btnVolver.onclick = () => {
  panelDetalle.classList.add("hidden");
  panelResumen.classList.remove("hidden");
};

function showDetalle(pt){
  panelResumen.classList.add("hidden");
  panelDetalle.classList.remove("hidden");

  let texto = "";

  if(pt.canal === "ATM"){
    texto = `
ATM ${pt.atm}
Nombre: ${pt.nombre}
Tipo: ${pt.tipo}
Ubicación: ${pt.ubicacion}
Departamento: ${pt.departamento}
Provincia: ${pt.provincia}
Distrito: ${pt.distrito}
División: ${pt.division}
Promedio: ${pt.promedio}
`;
  }

  if(pt.canal === "AGENTE"){
    texto = `
AGENTE ${pt.atm}
Comercio: ${pt.nombre}
Departamento: ${pt.departamento}
Provincia: ${pt.provincia}
Distrito: ${pt.distrito}
División: ${pt.division}
Capa: ${pt.capa}
Promedio: ${pt.promedio}
`;
  }

  if(pt.canal === "OFICINA"){
    texto = `
OFICINA ${pt.atm}
Nombre: ${pt.nombre}
Departamento: ${pt.departamento}
Provincia: ${pt.provincia}
Distrito: ${pt.distrito}
División: ${pt.division}
Promedio TRX: ${pt.promedio}
`;
  }

  detalleContenido.textContent = texto;
}

// ======================================================
// FETCH PRINCIPAL — CAPA INTEGRAL
// ======================================================
async function fetchPoints(){
  const d  = selDep.value;
  const p  = selProv.value;
  const di = selDist.value;
  const dv = selDiv ? selDiv.value : "";

  const qs =
    `tipo=${TIPO_MAPA}` +
    `&departamento=${encodeURIComponent(d)}` +
    `&provincia=${encodeURIComponent(p)}` +
    `&distrito=${encodeURIComponent(di)}` +
    `&division=${encodeURIComponent(dv)}`;

  const res = await fetch(`/api/points?${qs}`);
  const data = await res.json();

  // limpiar mapa
  clusterATMs.clearLayers();
  clusterAgentes.clearLayers();
  clusterOficinas.clearLayers();
  heat.setLatLngs([]);

  let heatPts = [];
  let bounds = [];

  data.puntos.forEach(pt => {

    // aplicar checkboxes
    if(pt.canal === "ATM" && chkATM && !chkATM.checked) return;
    if(pt.canal === "AGENTE" && chkAgente && !chkAgente.checked) return;
    if(pt.canal === "OFICINA" && chkOficina && !chkOficina.checked) return;

    let icon;
    if(pt.canal === "ATM"){
      if((pt.ubicacion || "").includes("OFICINA")) icon = ICON_ATM_OFICINA;
      else icon = ICON_ATM_ISLA;
    }
    else if(pt.canal === "AGENTE") icon = ICON_AGENTE;
    else if(pt.canal === "OFICINA") icon = ICON_OFICINA;

    const marker = L.marker([pt.lat, pt.lon], {icon});
    marker.on("click", ()=> showDetalle(pt));

    if(pt.canal === "ATM") clusterATMs.addLayer(marker);
    if(pt.canal === "AGENTE") clusterAgentes.addLayer(marker);
    if(pt.canal === "OFICINA") clusterOficinas.addLayer(marker);

    heatPts.push([pt.lat, pt.lon, Math.max(1, pt.promedio || 1)]);
    bounds.push([pt.lat, pt.lon]);
  });

  clusterATMs.addTo(map);
  clusterAgentes.addTo(map);
  clusterOficinas.addTo(map);

  heat.setLatLngs(heatPts);
  if(chkHeat.checked){ heat.addTo(map); }
  else{ map.removeLayer(heat); }

  // auto zoom
  if(bounds.length === 1){ map.setView(bounds[0], 16); }
  else if(bounds.length > 1){ map.fitBounds(bounds, {padding:[20,20]}); }

  // resumen
  if(TIPO_MAPA === "integral"){
    document.getElementById("resATMs").textContent = data.total_atms;
    document.getElementById("resAgentes").textContent = data.total_agentes;
    document.getElementById("resOficinas").textContent = data.total_oficinas;
  }

  document.getElementById("resSuma").textContent = Math.round(data.suma_total || 0);
}

updateProvincias();
fetchPoints();
</script>

</body>
</html>
"""