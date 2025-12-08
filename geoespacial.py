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

# Si no existe columna de promedio, crear una falsa
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

# Si no hay promedio, crear una falsa
if PROMA_COL is None:
    raw_ag["PROM_FAKE"] = 0.0
    PROMA_COL = "PROM_FAKE"

# Limpieza
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

# Limpieza
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
# 3. LISTAS PARA FILTROS — JERARQUÍA POR CAPA
# ============================================================

# --------- DEPARTAMENTOS ----------
DEPARTAMENTOS_ISLAS = sorted(df[COL_DEPT].dropna().astype(str).unique())
DEPARTAMENTOS_AGENTES = sorted(df_agentes[COLA_DEPT].dropna().astype(str).unique())
DEPARTAMENTOS_OFICINAS = sorted(df_oficinas[COLF_DEPT].dropna().astype(str).unique())

# --------- PROVINCIAS ----------
PROVINCIAS_ISLAS_BY_DEPT = {
    d: sorted(df[df[COL_DEPT] == d][COL_PROV].astype(str).unique())
    for d in DEPARTAMENTOS_ISLAS
}
PROVINCIAS_AGENTES_BY_DEPT = {
    d: sorted(df_agentes[df_agentes[COLA_DEPT] == d][COLA_PROV].astype(str).unique())
    for d in DEPARTAMENTOS_AGENTES
}
PROVINCIAS_OFICINAS_BY_DEPT = {
    d: sorted(df_oficinas[df_oficinas[COLF_DEPT] == d][COLF_PROV].astype(str).unique())
    for d in DEPARTAMENTOS_OFICINAS
}

# --------- DISTRITOS ----------
DIST_ISLAS_BY_PROV = {
    p: sorted(df[df[COL_PROV] == p][COL_DIST].astype(str).unique())
    for p in sorted(df[COL_PROV].astype(str).unique())
}
DIST_AGENTES_BY_PROV = {
    p: sorted(df_agentes[df_agentes[COLA_PROV] == p][COLA_DIST].astype(str).unique())
    for p in sorted(df_agentes[COLA_PROV].astype(str).unique())
}
DIST_OFICINAS_BY_PROV = {
    p: sorted(df_oficinas[df_oficinas[COLF_PROV] == p][COLF_DIST].astype(str).unique())
    for p in sorted(df_oficinas[COLF_PROV].astype(str).unique())
}

# --------- DIVISIONES ----------
DIVISIONES_ISLAS = sorted(df[COL_DIV].dropna().astype(str).unique())
DIVISIONES_AGENTES = sorted(df_agentes[COLA_DIV].dropna().astype(str).unique())
DIVISIONES_OFICINAS = sorted(df_oficinas[COLF_DIV].dropna().astype(str).unique())


# ============================================================
# 4. LOGIN + SELECTOR
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
# 6. RUTA DEL MAPA POR CAPA
# ============================================================
@app.route("/mapa/<tipo>")
@login_required
def mapa_tipo(tipo):
    if tipo not in ["oficinas", "islas", "agentes"]:
        return "No existe esa capa", 404

    initial_center = df[[COL_LAT, COL_LON]].mean().tolist()

    # Elegir listas según la capa (sin mezclar)
    if tipo == "islas":
        departamentos = DEPARTAMENTOS_ISLAS
        provincias_by_dept = PROVINCIAS_ISLAS_BY_DEPT
        dist_by_prov = DIST_ISLAS_BY_PROV
        divisiones = DIVISIONES_ISLAS

        div_by_dept = {
            d: sorted(df[df[COL_DEPT] == d][COL_DIV].astype(str).unique())
            for d in DEPARTAMENTOS_ISLAS
        }
        div_by_prov = {
            p: sorted(df[df[COL_PROV] == p][COL_DIV].astype(str).unique())
            for p in sorted(df[COL_PROV].astype(str).unique())
        }
        div_by_dist = {
            di: sorted(df[df[COL_DIST] == di][COL_DIV].astype(str).unique())
            for di in sorted(df[COL_DIST].astype(str).unique())
        }

    elif tipo == "agentes":
        departamentos = DEPARTAMENTOS_AGENTES
        provincias_by_dept = PROVINCIAS_AGENTES_BY_DEPT
        dist_by_prov = DIST_AGENTES_BY_PROV
        divisiones = DIVISIONES_AGENTES

        div_by_dept = {
            d: sorted(df_agentes[df_agentes[COLA_DEPT] == d][COLA_DIV].astype(str).unique())
            for d in DEPARTAMENTOS_AGENTES
        }
        div_by_prov = {
            p: sorted(df_agentes[df_agentes[COLA_PROV] == p][COLA_DIV].astype(str).unique())
            for p in sorted(df_agentes[COLA_PROV].astype(str).unique())
        }
        div_by_dist = {
            di: sorted(df_agentes[df_agentes[COLA_DIST] == di][COLA_DIV].astype(str).unique())
            for di in sorted(df_agentes[COLA_DIST].astype(str).unique())
        }

    else:  # oficinas
        departamentos = DEPARTAMENTOS_OFICINAS
        provincias_by_dept = PROVINCIAS_OFICINAS_BY_DEPT
        dist_by_prov = DIST_OFICINAS_BY_PROV
        divisiones = DIVISIONES_OFICINAS

        div_by_dept = {
            d: sorted(df_oficinas[df_oficinas[COLF_DEPT] == d][COLF_DIV].astype(str).unique())
            for d in DEPARTAMENTOS_OFICINAS
        }
        div_by_prov = {
            p: sorted(df_oficinas[df_oficinas[COLF_PROV] == p][COLF_DIV].astype(str).unique())
            for p in sorted(df_oficinas[COLF_PROV].astype(str).unique())
        }
        div_by_dist = {
            di: sorted(df_oficinas[df_oficinas[COLF_DIST] == di][COLF_DIV].astype(str).unique())
            for di in sorted(df_oficinas[COLF_DIST].astype(str).unique())
        }

    return render_template_string(
        TEMPLATE_MAPA,
        tipo_mapa=tipo,
        departamentos=departamentos,
        provincias_by_dept=provincias_by_dept,
        dist_by_prov=dist_by_prov,
        divisiones=divisiones,
        div_by_dept=div_by_dept,
        div_by_prov=div_by_prov,
        div_by_dist=div_by_dist,
        initial_center=initial_center,
        initial_zoom=6,
    )


# ============================================================
# 7. API /api/points — 3 CAPAS + TOTAL DE TRANSACCIONES
# ============================================================
@app.route("/api/points")
@login_required
def api_points():
    tipo_mapa = request.args.get("tipo", "").lower()

    dpto = request.args.get("departamento", "").upper().strip()
    prov = request.args.get("provincia", "").upper().strip()
    dist = request.args.get("distrito", "").upper().strip()
    divi = request.args.get("division", "").upper().strip()

    # ============================================================
    # CAPA ISLAS (ATMs)
    # ============================================================
    if tipo_mapa == "islas":
        dff = df.copy()

        for col in [COL_DEPT, COL_PROV, COL_DIST, COL_DIV, COL_TIPO, COL_UBIC]:
            dff[col] = dff[col].astype(str).str.upper().str.strip()

        if dpto:
            dff = dff[dff[COL_DEPT] == dpto]
        if prov:
            dff = dff[dff[COL_PROV] == prov]
        if dist:
            dff = dff[dff[COL_DIST] == dist]
        if divi:
            dff = dff[dff[COL_DIV] == divi]

        total_atms = len(dff)
        total_trx = float(dff[PROM_COL].sum()) if total_atms > 0 else 0.0

        total_oficinas = int(dff[COL_UBIC].str.contains("OFICINA", na=False).sum())
        total_islas = int(dff[COL_UBIC].str.contains("ISLA", na=False).sum())

        total_disp = int(dff[COL_TIPO].str.contains("DISPENSADOR", na=False).sum())
        total_mon = int(dff[COL_TIPO].str.contains("MONEDERO", na=False).sum())
        total_rec = int(dff[COL_TIPO].str.contains("RECICLADOR", na=False).sum())

        puntos = []
        for _, r in dff.iterrows():
            lat_v = float(r[COL_LAT])
            lon_v = float(r[COL_LON])
            nombre = str(r.get(COL_NAME)) if COL_NAME else str(r.get(COL_ATM, ""))

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
                }
            )

        return jsonify(
            {
                "puntos": puntos,
                "total_atms": total_atms,
                "total_trx": total_trx,
                "total_oficinas": total_oficinas,
                "total_islas": total_islas,
                "total_disp": total_disp,
                "total_mon": total_mon,
                "total_rec": total_rec,
            }
        )

    # ============================================================
    # CAPA AGENTES
    # ============================================================
    if tipo_mapa == "agentes":
        dff = df_agentes.copy()

        for col in [COLA_DEPT, COLA_PROV, COLA_DIST, COLA_DIV, COLA_CAPA]:
            dff[col] = dff[col].astype(str).str.upper().str.strip()

        if dpto:
            dff = dff[dff[COLA_DEPT] == dpto]
        if prov:
            dff = dff[dff[COLA_PROV] == prov]
        if dist:
            dff = dff[dff[COLA_DIST] == dist]
        if divi:
            dff = dff[dff[COLA_DIV] == divi]

        total_agentes = len(dff)
        total_trx = float(dff[PROMA_COL].sum()) if total_agentes > 0 else 0.0

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
                    "trxs_oct": float(r.get(COLA_TRX_OCT, 0.0)) if COLA_TRX_OCT else 0.0,
                    "trxs_nov": float(r.get(COLA_TRX_NOV, 0.0)) if COLA_TRX_NOV else 0.0,
                }
            )

        return jsonify(
            {
                "puntos": puntos,
                "total_agentes": total_agentes,
                "total_trx": total_trx,
                "total_capa_A1": total_capa_A1,
                "total_capa_A2": total_capa_A2,
                "total_capa_A3": total_capa_A3,
                "total_capa_B": total_capa_B,
                "total_capa_C": total_capa_C,
            }
        )

    # ============================================================
    # CAPA OFICINAS
    # ============================================================
    if tipo_mapa == "oficinas":
        dff = df_oficinas.copy()

        for col in [COLF_DEPT, COLF_PROV, COLF_DIST, COLF_DIV]:
            dff[col] = dff[col].astype(str).str.upper().str.strip()

        if dpto:
            dff = dff[dff[COLF_DEPT] == dpto]
        if prov:
            dff = dff[dff[COLF_PROV] == prov]
        if dist:
            dff = dff[dff[COLF_DIST] == dist]
        if divi:
            dff = dff[dff[COLF_DIV] == divi]

        total_oficinas = len(dff)
        total_trx = float(dff[COLF_TRX].sum()) if total_oficinas > 0 else 0.0

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
                    "direccion": "No disponible",
                }
            )

        return jsonify(
            {
                "puntos": puntos,
                "total_oficinas": total_oficinas,
                "total_trx": total_trx,
            }
        )

    return jsonify({"puntos": [], "total_trx": 0})


# ============================================================
# 8. TEMPLATE MAPA — FRONTEND COMPLETO (ACTUALIZADO)
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

/* Panel seleccionado */
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

/* Glow suave */
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
.popup-title{
  font-size:14px;
  font-weight:bold;
  color:var(--bbva-blue);
  margin-bottom:4px;
}
.popup-row{
  margin:2px 0;
  font-size:12px;
}

/* Iconos personalizados */
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
      Mostrando <span id="infoCount">--</span> puntos
    </div>
  </div>
</div>

<div class="main">
  <div id="map"></div>

  <div class="side">
    <!-- PANEL RESUMEN -->
    <div id="panelResumen" class="side-card">
      <div class="side-title" id="panelResumenTitulo">Resumen</div>

      <!-- Campo principal actualizado -->
      <div class="muted">Total de transacciones:</div>
      <div style="margin-top:4px;">
        <b>Total de transacciones:</b> <span id="resTotalTrx">0</span>
      </div>

      <!-- Bloque ISLAS -->
      <div id="bloqueIslasOfi">
        <div style="margin-top:6px; font-weight:600;" id="resTituloBloque">ATMs totales</div>
        <div class="muted" style="margin-top:2px;">Total ATMs: <span id="resTotal">0</span></div>
        <div class="muted">ATMs en oficinas: <span id="resOfi">0</span></div>
        <div class="muted">ATMs en islas: <span id="resIsla">0</span></div>

        <div class="muted" style="margin-top:6px;">Dispensador: <span id="resDisp">0</span></div>
        <div class="muted">Monedero: <span id="resMon">0</span></div>
        <div class="muted">Reciclador: <span id="resRec">0</span></div>
      </div>

      <!-- Bloque OFICINAS -->
      <div id="bloqueOficinas" class="hidden" style="margin-top:8px;">
        <div class="muted">
          Cantidad total de oficinas: <span id="resOficinasCount">0</span>
        </div>
      </div>

      <!-- Bloque AGENTES -->
      <div id="bloqueAgentes" class="hidden" style="margin-top:8px;">
        <div style="font-weight:600;">Agentes totales: <span id="resAgentesTotal">0</span></div>
        <div class="muted" style="margin-top:4px;">Capa A1: <span id="resCapaA1">0</span></div>
        <div class="muted">Capa A2: <span id="resCapaA2">0</span></div>
        <div class="muted">Capa A3: <span id="resCapaA3">0</span></div>
        <div class="muted">Capa B : <span id="resCapaB">0</span></div>
        <div class="muted">Capa C : <span id="resCapaC">0</span></div>
      </div>

      <div style="margin-top:10px; font-weight:600;">Leyenda</div>
      <div class="muted" id="legendBox"></div>
    </div>

    <!-- PANEL DETALLE -->
    <div id="panelATM" class="side-card side-card-atm hidden">
      <h3 id="panelATMTitle">Panel de Detalle</h3>
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

const ICON_OFICINA_URL = "{{ url_for('static', filename='oficina.png') }}";
const ICON_ISLA_URL    = "{{ url_for('static', filename='isla.png') }}";
const ICON_AGENTE_URL  = "{{ url_for('static', filename='agente.png') }}";

const ICON_OFICINA = L.icon({iconUrl:ICON_OFICINA_URL,iconSize:[40,40],iconAnchor:[20,20],popupAnchor:[0,-20]});
const ICON_ISLA    = L.icon({iconUrl:ICON_ISLA_URL,iconSize:[40,40],iconAnchor:[20,20],popupAnchor:[0,-20]});
const ICON_AGENTE  = L.icon({iconUrl:ICON_AGENTE_URL,iconSize:[40,40],iconAnchor:[20,20],popupAnchor:[0,-20]});

const map = L.map('map').setView(INITIAL_CENTER, INITIAL_ZOOM);
L.tileLayer('https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png',{maxZoom:19}).addTo(map);

const markers = L.markerClusterGroup({chunkedLoading:true});
const heat    = L.heatLayer([], {radius:28, blur:22});
markers.addTo(map);
heat.addTo(map);

const selDep  = document.getElementById("selDepartamento");
const selProv = document.getElementById("selProvincia");
const selDist = document.getElementById("selDistrito");
const selDiv  = document.getElementById("selDivision");
const chkHeat = document.getElementById("chkHeat");
const infoBox = document.getElementById("infoCount");

// Panel resumen
const panelResumen       = document.getElementById("panelResumen");
const resTotalTrx        = document.getElementById("resTotalTrx");

// bloques
const bloqueIslasOfi     = document.getElementById("bloqueIslasOfi");
const bloqueOficinas     = document.getElementById("bloqueOficinas");
const bloqueAgentes      = document.getElementById("bloqueAgentes");

const resTotal           = document.getElementById("resTotal");
const resOfi             = document.getElementById("resOfi");
const resIsla            = document.getElementById("resIsla");
const resDisp            = document.getElementById("resDisp");
const resMon             = document.getElementById("resMon");
const resRec             = document.getElementById("resRec");

const resOficinasCount   = document.getElementById("resOficinasCount");

const resAgentesTotal    = document.getElementById("resAgentesTotal");
const resCapaA1          = document.getElementById("resCapaA1");
const resCapaA2          = document.getElementById("resCapaA2");
const resCapaA3          = document.getElementById("resCapaA3");
const resCapaB           = document.getElementById("resCapaB");
const resCapaC           = document.getElementById("resCapaC");

// Panel detalle
const panelATM      = document.getElementById("panelATM");
const atmDetalle    = document.getElementById("atmDetalle");
const btnVolver     = document.getElementById("btnVolver");

// Config inicial
if(TIPO_MAPA === "oficinas"){
  bloqueIslasOfi.classList.add("hidden");
  bloqueAgentes.classList.add("hidden");
  bloqueOficinas.classList.remove("hidden");
}
else if(TIPO_MAPA === "agentes"){
  bloqueIslasOfi.classList.add("hidden");
  bloqueOficinas.classList.add("hidden");
  bloqueAgentes.classList.remove("hidden");
}
else {
  bloqueIslasOfi.classList.remove("hidden");
  bloqueOficinas.classList.add("hidden");
  bloqueAgentes.classList.add("hidden");
}

// combos dependientes
function updateProvincias(){
  let d = selDep.value;
  selProv.innerHTML = '<option value="">-- Todas --</option>';
  if(d && PROV_BY_DEPT[d]){
    PROV_BY_DEPT[d].forEach(p => selProv.innerHTML += `<option value="${p}">${p}</option>`);
  }
  updateDistritos();
  updateDivisiones();
}

function updateDistritos(){
  let p = selProv.value;
  selDist.innerHTML = '<option value="">-- Todos --</option>';
  if(p && DIST_BY_PROV[p]){
    DIST_BY_PROV[p].forEach(d => selDist.innerHTML += `<option value="${d}">${d}</option>`);
  }
  updateDivisiones();
}

function updateDivisiones(){
  let d = selDep.value;
  let p = selProv.value;
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

selDep.onchange  = ()=>{ updateProvincias(); fetchPoints(); };
selProv.onchange = ()=>{ updateDistritos(); fetchPoints(); };
selDist.onchange = ()=>{ updateDivisiones(); fetchPoints(); };
selDiv.onchange  = ()=> fetchPoints();

// iconos
function getIcon(pt){
  const ubic = (pt.ubicacion || "").toUpperCase();

  if (TIPO_MAPA === "agentes") return ICON_AGENTE;
  if (ubic.includes("OFICINA")) return ICON_OFICINA;
  if (ubic.includes("ISLA"))    return ICON_ISLA;
  if (ubic.includes("AGENTE"))  return ICON_AGENTE;

  if (TIPO_MAPA === "oficinas") return ICON_OFICINA;
  if (TIPO_MAPA === "islas")    return ICON_ISLA;

  return ICON_ISLA;
}

// detalle
function showATMPanel(pt){
  const linea = `${pt.departamento} / ${pt.provincia} / ${pt.distrito}`;
  let texto = "";

  if(TIPO_MAPA === "agentes"){
    texto = `
AGENTE ${pt.atm}

• Comercio: ${pt.nombre}
• Dirección: ${pt.direccion}
• División: ${pt.division}
• Capa: ${pt.capa}

• Ubicación:
  ${linea}

• Promedio: ${pt.promedio}
• TRX Oct: ${pt.trxs_oct}
• TRX Nov: ${pt.trxs_nov}
`;
  }
  else if(TIPO_MAPA === "oficinas"){
    texto = `
OFICINA ${pt.atm}

• Nombre: ${pt.nombre}
• División: ${pt.division}

• Ubicación:
  ${linea}

• Promedio TRX: ${pt.promedio}
`;
  }
  else{
    texto = `
ATM ${pt.atm}

• Nombre: ${pt.nombre}
• Dirección: ${pt.direccion}
• División: ${pt.division}
• Tipo: ${pt.tipo}

• Ubicación:
  ${linea}

• Promedio: ${pt.promedio}
`;
  }

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

// fetch
async function fetchPoints(){
  const d  = selDep.value;
  const p  = selProv.value;
  const di = selDist.value;
  const dv = selDiv.value;

  const qs = `tipo=${TIPO_MAPA}&departamento=${encodeURIComponent(d)}&provincia=${encodeURIComponent(p)}&distrito=${encodeURIComponent(di)}&division=${encodeURIComponent(dv)}`;
    
  panelATM.classList.add("hidden");
  panelResumen.classList.remove("hidden");

  const res = await fetch(`/api/points?${qs}`);
  const data = await res.json();

  const pts = data.puntos || [];

  infoBox.textContent = pts.length;
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

  if(bounds.length === 1) map.setView(bounds[0], 16);
  else if(bounds.length > 1) map.fitBounds(bounds, {padding:[20,20]});
  else map.setView(INITIAL_CENTER, INITIAL_ZOOM);

  if(chkHeat.checked){
    if(!map.hasLayer(heat)) heat.addTo(map);
  }else{
    if(map.hasLayer(heat)) map.removeLayer(heat);
  }

  // *** NUEVO *** Total transacciones
  resTotalTrx.textContent = Math.round(data.total_trx || 0);

  if(TIPO_MAPA === "agentes"){
    resAgentesTotal.textContent = data.total_agentes || 0;
    resCapaA1.textContent = data.total_capa_A1 || 0;
    resCapaA2.textContent = data.total_capa_A2 || 0;
    resCapaA3.textContent = data.total_capa_A3 || 0;
    resCapaB.textContent  = data.total_capa_B  || 0;
    resCapaC.textContent  = data.total_capa_C  || 0;
  }
  else if(TIPO_MAPA === "oficinas"){
    resOficinasCount.textContent = data.total_oficinas || 0;
  }
  else{
    resTotal.textContent = data.total_atms || 0;
    resOfi.textContent   = data.total_oficinas || 0;
    resIsla.textContent  = data.total_islas || 0;
    resDisp.textContent  = data.total_disp || 0;
    resMon.textContent   = data.total_mon  || 0;
    resRec.textContent   = data.total_rec  || 0;
  }
}

updateProvincias();
fetchPoints();
</script>

</body>
</html>
"""

# ============================================================
# 9. INICIO DEL SERVIDOR
# ============================================================

if __name__ == "__main__":
    # En local usamos debug=True
    # En Render, automáticamente ignora debug y usa el puerto asignado
    app.run(
        host="0.0.0.0",
        port=int(os.environ.get("PORT", 5000)),
        debug=True
    )


    