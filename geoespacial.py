# ============================================================
#   BACKEND COMPLETO — PARTE 1 / 4
#   Carga de 3 excels (islas, oficinas, agentes)
#   Login + Selector de capas
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
# 2. FUNCIÓN AUXILIAR PARA NORMALIZAR NOMBRES DE COLUMNA
# ============================================================
def normalize_col(s):
    s = str(s)
    s = unicodedata.normalize("NFKD", s)
    s = s.encode("ascii", "ignore").decode("utf-8")
    s = s.upper().strip()
    s = re.sub(r"[^A-Z0-9 ]+", " ", s)
    return re.sub(r"\s+", " ", s).strip()


def detect_cols(df):
    """Detecta columnas estándar en cualquiera de los 3 excels."""
    norm_map = {normalize_col(c): c for c in df.columns}

    def find_col(keys):
        for norm, orig in norm_map.items():
            for k in keys:
                if k in norm:
                    return orig
        return None

    COL_TERMINAL = find_col(["TERMINAL", "ATM", "CAJERO"])
    COL_COMERCIO = find_col(["COMERCIO"])
    COL_REGION = find_col(["REGION"])
    COL_DEPT = find_col(["DEPARTAMENTO"])
    COL_PROV = find_col(["PROVINCIA"])
    COL_DIST = find_col(["DISTRITO"])
    COL_DIR = find_col(["DIRECCION", "DIRECCIÓN"])
    COL_LAT = find_col(["LATITUD", "LAT"])
    COL_LON = find_col(["LONGITUD", "LON"])
    COL_ESTADO = find_col(["ESTADO"])
    COL_INSTAL = find_col(["INSTALADO"])
    COL_CODOF = find_col(["COD OF"])
    COL_OFICINA = find_col(["OFICINA"])
    COL_DIV = find_col(["DIVISION", "DIVISIÓN"])
    COL_CAPA = find_col(["CAPA"])
    COL_TRX_OCT = find_col(["TRXS OCTUBRE"])
    COL_TRX_NOV = find_col(["TRXS NOV"])
    COL_PROM = find_col(["PROMEDIO", "PROM"])

    return {
        "TERMINAL": COL_TERMINAL,
        "COMERCIO": COL_COMERCIO,
        "REGION": COL_REGION,
        "DEPARTAMENTO": COL_DEPT,
        "PROVINCIA": COL_PROV,
        "DISTRITO": COL_DIST,
        "DIRECCION": COL_DIR,
        "LAT": COL_LAT,
        "LON": COL_LON,
        "ESTADO": COL_ESTADO,
        "INSTALADO": COL_INSTAL,
        "COD_OF": COL_CODOF,
        "OFICINA": COL_OFICINA,
        "DIVISION": COL_DIV,
        "CAPA": COL_CAPA,
        "TRX_OCT": COL_TRX_OCT,
        "TRX_NOV": COL_TRX_NOV,
        "PROMEDIO": COL_PROM,
    }


def clean_df(df, cols):
    """Limpia, normaliza y retorna DF listo para usar mapas."""
    lat_col = cols["LAT"]
    lon_col = cols["LON"]
    prom_col = cols["PROMEDIO"]

    df[lat_col] = (
        df[lat_col]
        .astype(str)
        .str.replace(",", ".", regex=False)
        .str.replace(r"[^\d\.\-]", "", regex=True)
        .replace("", np.nan)
        .astype(float)
    )
    df[lon_col] = (
        df[lon_col]
        .astype(str)
        .str.replace(",", ".", regex=False)
        .str.replace(r"[^\d\.\-]", "", regex=True)
        .replace("", np.nan)
        .astype(float)
    )

    df = df.dropna(subset=[lat_col, lon_col]).reset_index(drop=True)

    if prom_col is not None:
        df[prom_col] = pd.to_numeric(df[prom_col], errors="coerce").fillna(0.0)
    else:
        df["PROM_FAKE"] = 0.0
        cols["PROMEDIO"] = "PROM_FAKE"

    for c in ["DEPARTAMENTO", "PROVINCIA", "DISTRITO", "DIVISION"]:
        col = cols[c]
        if col:
            df[col] = df[col].astype(str).str.upper().str.strip()

    return df


# ============================================================
# 3. CARGA DE LOS 3 EXCELS (ISLAS, OFICINAS, AGENTES)
# ============================================================
BASE_DIR = os.path.dirname(__file__)

path_islas = os.path.join(BASE_DIR, "data", "Mapa Geoespacial ATM (1) (1).xlsx")
path_oficinas = os.path.join(BASE_DIR, "data", "OFICINAS.xlsx")
path_agentes = os.path.join(BASE_DIR, "data", "AGENTES.xlsx")

if not os.path.exists(path_islas):
    raise FileNotFoundError("No encontré el Excel de ISLAS")
if not os.path.exists(path_oficinas):
    raise FileNotFoundError("No encontré el Excel de OFICINAS")
if not os.path.exists(path_agentes):
    raise FileNotFoundError("No encontré el Excel de AGENTES")


df_islas_raw = pd.read_excel(path_islas)
df_oficinas_raw = pd.read_excel(path_oficinas)
df_agentes_raw = pd.read_excel(path_agentes)

cols_islas = detect_cols(df_islas_raw)
cols_oficinas = detect_cols(df_oficinas_raw)
cols_agentes = detect_cols(df_agentes_raw)

df_islas = clean_df(df_islas_raw.copy(), cols_islas)
df_oficinas = clean_df(df_oficinas_raw.copy(), cols_oficinas)
df_agentes = clean_df(df_agentes_raw.copy(), cols_agentes)


# ============================================================
# 4. LOGIN Y SELECTOR DE CAPAS
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


# ---------------- LOGIN TEMPLATE ----------------
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
    <img src="{{ url_for('static', filename='oficina.png') }}">
    <div class="card-title"><span class="icon">🏢</span>Oficinas</div>
  </div>

  <div class="card" onclick="location.href='/mapa/islas'">
    <img src="{{ url_for('static', filename='isla.png') }}">
    <div class="card-title"><span class="icon">🌐</span>Islas</div>
  </div>

  <div class="card" onclick="location.href='/mapa/agentes'">
    <img src="{{ url_for('static', filename='agente.png') }}">
    <div class="card-title"><span class="icon">🧑‍💼</span>Agentes</div>
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
# 6. RUTA DEL MAPA — CARGA DE TEMPLATE MAPA
# ============================================================
@app.route("/mapa/<tipo>")
@login_required
def mapa_tipo(tipo):
    if tipo not in ["islas", "oficinas", "agentes"]:
        return "No existe esa capa", 404

    # Construimos combos desde ISLAS (EL MÁS COMPLETO)
    # → Esto asegura que todos tengan filtros completos
    df_all = df_islas  # sólo para filtros (no para puntos)

    col_dept = cols_islas["DEPARTAMENTO"]
    col_prov = cols_islas["PROVINCIA"]
    col_dist = cols_islas["DISTRITO"]
    col_div = cols_islas["DIVISION"]

    departamentos = sorted(df_all[col_dept].dropna().unique().tolist())
    provincias_by_dept = (
        df_all.groupby(col_dept)[col_prov]
        .apply(lambda s: sorted(s.dropna().unique()))
        .to_dict()
    )
    dist_by_prov = (
        df_all.groupby(col_prov)[col_dist]
        .apply(lambda s: sorted(s.dropna().unique()))
        .to_dict()
    )
    div_by_dept = (
        df_all.groupby(col_dept)[col_div]
        .apply(lambda s: sorted(s.dropna().unique()))
        .to_dict()
    )
    div_by_prov = (
        df_all.groupby(col_prov)[col_div]
        .apply(lambda s: sorted(s.dropna().unique()))
        .to_dict()
    )
    div_by_dist = (
        df_all.groupby(col_dist)[col_div]
        .apply(lambda s: sorted(s.dropna().unique()))
        .to_dict()
    )

    # Centro inicial del mapa
    lat0 = df_all[cols_islas["LAT"]].mean()
    lon0 = df_all[cols_islas["LON"]].mean()

    return render_template_string(
        TEMPLATE_MAPA,
        tipo_mapa=tipo,
        departamentos=departamentos,
        provincias_by_dept=provincias_by_dept,
        dist_by_prov=dist_by_prov,
        div_by_dept=div_by_dept,
        div_by_prov=div_by_prov,
        div_by_dist=div_by_dist,
        divisiones=sorted(df_all[col_div].dropna().unique().tolist()),
        initial_center=[lat0, lon0],
        initial_zoom=6,
    )


# ============================================================
# 7. API PRINCIPAL — /api/points (las 3 capas)
# ============================================================
@app.route("/api/points")
@login_required
def api_points():
    tipo = request.args.get("tipo", "").lower()

    # -------- Filtros --------
    f_dept = request.args.get("departamento", "").upper().strip()
    f_prov = request.args.get("provincia", "").upper().strip()
    f_dist = request.args.get("distrito", "").upper().strip()
    f_div = request.args.get("division", "").upper().strip()

    # -------- Dataset por capa --------
    if tipo == "islas":
        df = df_islas
        cols = cols_islas
    elif tipo == "oficinas":
        df = df_oficinas
        cols = cols_oficinas
    elif tipo == "agentes":
        df = df_agentes
        cols = cols_agentes
    else:
        return jsonify({"puntos": []})

    # -------- Normalización --------
    for key in ["DEPARTAMENTO", "PROVINCIA", "DISTRITO", "DIVISION"]:
        col = cols[key]
        if col:
            df[col] = df[col].astype(str).str.upper().str.strip()

    # -------- Filtros jerárquicos --------
    if f_dept:
        df = df[df[cols["DEPARTAMENTO"]] == f_dept]
    if f_prov:
        df = df[df[cols["PROVINCIA"]] == f_prov]
    if f_dist:
        df = df[df[cols["DISTRITO"]] == f_dist]
    if f_div:
        df = df[df[cols["DIVISION"]] == f_div]

    # -------- Construcción del resumen --------
    total_items = len(df)
    prom_total = float(df[cols["PROMEDIO"]].mean()) if total_items > 0 else 0.0

    # Conteos comunes
    total_disp = df[cols["CAPA"]].astype(str).str.contains("DISP", case=False, na=False).sum()
    total_mon = df[cols["CAPA"]].astype(str).str.contains("MON", case=False, na=False).sum()
    total_rec = df[cols["CAPA"]].astype(str).str.contains("REC", case=False, na=False).sum()

    # Conteos especiales por tipo
    total_oficinas = 0
    total_islas = 0

    if tipo == "islas":
        col_oficina = cols["OFICINA"]
        if col_oficina:
            total_oficinas = df[col_oficina].astype(str).str.contains("OF", na=False).sum()
        total_islas = total_items - total_oficinas

    capa_A1 = capa_A2 = capa_A3 = capa_B = capa_C = 0
    if tipo == "agentes":
        capa_A1 = df[cols["CAPA"]].astype(str).str.contains("A1", na=False).sum()
        capa_A2 = df[cols["CAPA"]].astype(str).str.contains("A2", na=False).sum()
        capa_A3 = df[cols["CAPA"]].astype(str).str.contains("A3", na=False).sum()
        capa_B  = df[cols["CAPA"]].astype(str).str.contains("B",  na=False).sum()
        capa_C  = df[cols["CAPA"]].astype(str).str.contains("C",  na=False).sum()

    # -------- Construcción de puntos --------
    puntos = []

    for _, r in df.iterrows():
        punto = {
            "lat": float(r[cols["LAT"]]),
            "lon": float(r[cols["LON"]]),
            "atm": str(r[cols["TERMINAL"]]),
            "nombre": str(r.get(cols["COMERCIO"], "")),
            "promedio": float(r[cols["PROMEDIO"]]),
            "division": str(r.get(cols["DIVISION"], "")),
            "tipo": str(r.get(cols["CAPA"], "")),
            "direccion": str(r.get(cols["DIRECCION"], "")),
            "departamento": str(r.get(cols["DEPARTAMENTO"], "")),
            "provincia": str(r.get(cols["PROVINCIA"], "")),
            "distrito": str(r.get(cols["DISTRITO"], "")),
        }

        # Dirección en cache si no existe en excel
        if punto["direccion"] == "":
            punto["direccion"] = get_address(punto["lat"], punto["lon"])

        puntos.append(punto)

    # -------- Respuesta --------
    return jsonify(
        {
            "puntos": puntos,
            "total": total_items,
            "promedio_total": prom_total,

            # islas
            "total_oficinas": int(total_oficinas),
            "total_islas": int(total_islas),

            # agentes
            "capa_A1": int(capa_A1),
            "capa_A2": int(capa_A2),
            "capa_A3": int(capa_A3),
            "capa_B": int(capa_B),
            "capa_C": int(capa_C),

            # tipos de dispositivos comunes
            "total_disp": int(total_disp),
            "total_mon": int(total_mon),
            "total_rec": int(total_rec),
        }
    )


    # ============================================================
# 8. TEMPLATE MAPA — PARTE 3 / 4
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
}

html,body{
  margin:0; padding:0; height:100%;
  font-family:Inter,Arial,Helvetica,sans-serif;
  background:#eef4fb;
}

/* HEADER */
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
  position:absolute; right:20px;
  background:#1464A5;
  color:white;
  padding:8px 16px;
  border-radius:8px;
  text-decoration:none;
  font-weight:600;
}

/* TOPBAR */
.topbar{ padding:16px 20px 8px 20px; }
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
  flex-direction:column;
}
select{
  padding:6px 10px;
  border-radius:8px;
  border:1px solid #d0d7e3;
}
input[type="checkbox"]{
  transform:scale(1.05);
}

/* MAIN LAYOUT */
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

/* RIGHT PANEL */
.side{ width:330px; }

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

/* Selected ATM Panel */
.side-card-atm{
  font-family:"Consolas","Fira Code",monospace;
  white-space:pre-line;
  line-height:1.35;
  border-left:4px solid var(--bbva-blue);
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

/* ICONS */
.icon-isla div{
  font-size:28px;
  color:deepskyblue;
}
.icon-oficina div{
  font-size:28px;
  color:#1464A5;
}
.icon-agente div{
  font-size:28px;
  color:#0f8a0f;
}
.icon-round div{
  width:14px; height:14px;
  border-radius:50%;
  border:2px solid white;
}

/* POPUP */
.leaflet-popup-content-wrapper{
  border-radius:12px;
  box-shadow:0 6px 20px rgba(0,0,0,0.25);
}
.popup-row{
  margin:3px 0;
  font-size:12px;
}
.popup-title{
  font-size:14px;
  font-weight:bold;
  color:var(--bbva-blue);
  margin-bottom:6px;
}
</style>

</head>
<body>

<header>
  <h1>MAPA BBVA — {{ tipo_mapa|upper }}</h1>
  <a href="/logout" class="logout">Cerrar sesión</a>
</header>

<div class="topbar">
  <div class="controls">

    <label>Departamento
      <select id="selDepartamento">
        <option value="">-- Todos --</option>
        {% for d in departamentos %}
        <option value="{{d}}">{{d}}</option>
        {% endfor %}
      </select>
    </label>

    <label>Provincia
      <select id="selProvincia">
        <option value="">-- Todas --</option>
      </select>
    </label>

    <label>Distrito
      <select id="selDistrito">
        <option value="">-- Todos --</option>
      </select>
    </label>

    <label>División
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
      Mostrando <span id="infoCount">--</span> registros
    </div>

  </div>
</div>

<!-- MAIN -->
<div class="main">
  <div id="map"></div>

  <div class="side">

    <!-- PANEL RESUMEN -->
    <div id="panelResumen" class="side-card">
      <div class="side-title" id="resTitulo">Resumen</div>

      <div class="muted">Promedio total: <b><span id="resPromedio">0</span></b></div>

      <div id="bloqueIslas" class="hidden" style="margin-top:10px;">
        <div class="muted">Total oficinas: <span id="resOf">0</span></div>
        <div class="muted">Total islas: <span id="resIs">0</span></div>
      </div>

      <div id="bloqueAgentes" class="hidden" style="margin-top:10px;">
        <div class="muted">Agentes total: <span id="resCant">0</span></div>
        <div class="muted">Capa A1: <span id="resA1">0</span></div>
        <div class="muted">Capa A2: <span id="resA2">0</span></div>
        <div class="muted">Capa A3: <span id="resA3">0</span></div>
        <div class="muted">Capa B: <span id="resB">0</span></div>
        <div class="muted">Capa C: <span id="resC">0</span></div>
      </div>

      <div id="bloqueTips" class="hidden" style="margin-top:10px;">
        <div class="muted">Dispensadores: <span id="resDisp">0</span></div>
        <div class="muted">Monederos: <span id="resMon">0</span></div>
        <div class="muted">Recicladores: <span id="resRec">0</span></div>
      </div>

    </div>

    <!-- PANEL DETALLE -->
    <div id="panelATM" class="side-card side-card-atm hidden">
      <h3 id="panelTitulo">Detalle</h3>
      <div id="atmDetalle" style="font-size:12px; margin-top:4px;"></div>
      <button id="btnVolver" class="btn-small">VOLVER</button>
    </div>

  </div>
</div>

<script src="https://unpkg.com/leaflet@1.9.4/dist/leaflet.js"></script>
<script src="https://unpkg.com/leaflet.markercluster@1.5.3/dist/MarkerCluster.js"></script>
<script src="https://unpkg.com/leaflet.heat/dist/leaflet-heat.js"></script>

<script>
/* =====================================
   VARIABLES TEMPLATE → JS
===================================== */
const TIPO = "{{ tipo_mapa }}";
const PROV_DEPT = {{ provincias_by_dept|tojson }};
const DIST_PROV = {{ dist_by_prov|tojson }};
const DIV_DEPT = {{ div_by_dept|tojson }};
const DIV_PROV = {{ div_by_prov|tojson }};
const DIV_DIST = {{ div_by_dist|tojson }};
const TODAS_DIV = {{ divisiones|tojson }};
const CENTER = [{{ initial_center[0] }}, {{ initial_center[1] }}];
const ZOOM = {{ initial_zoom }};

/* =====================================
   MAPA LEAFLET
===================================== */
const map = L.map("map").setView(CENTER, ZOOM);
L.tileLayer("https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png",{maxZoom:19}).addTo(map);

const markers = L.markerClusterGroup({ chunkedLoading:true });
const heat = L.heatLayer([], {radius:28, blur:22});
markers.addTo(map);
heat.addTo(map);

/* =====================================
   CONTROLES
===================================== */
const selDep = document.getElementById("selDepartamento");
const selProv = document.getElementById("selProvincia");
const selDist = document.getElementById("selDistrito");
const selDiv  = document.getElementById("selDivision");
const chkHeat = document.getElementById("chkHeat");
const infoCount = document.getElementById("infoCount");

/* Side panels */
const panelResumen = document.getElementById("panelResumen");
const panelATM = document.getElementById("panelATM");
const atmDetalle = document.getElementById("atmDetalle");
const panelTitulo = document.getElementById("panelTitulo");
const btnVolver = document.getElementById("btnVolver");

/* Contenido del resumen */
const resProm = document.getElementById("resPromedio");
const resOf = document.getElementById("resOf");
const resIs = document.getElementById("resIs");
const resCant = document.getElementById("resCant");
const resA1 = document.getElementById("resA1");
const resA2 = document.getElementById("resA2");
const resA3 = document.getElementById("resA3");
const resB  = document.getElementById("resB");
const resC  = document.getElementById("resC");
const resDisp = document.getElementById("resDisp");
const resMon  = document.getElementById("resMon");
const resRec  = document.getElementById("resRec");

/* BLOQUES */
const blqIslas = document.getElementById("bloqueIslas");
const blqAgentes = document.getElementById("bloqueAgentes");
const blqTips = document.getElementById("bloqueTips");


// Mostrar bloques correctos según capa
if (TIPO === "islas") {
  blqIslas.classList.remove("hidden");
  blqTips.classList.remove("hidden");
} else if (TIPO === "oficinas") {
  blqTips.classList.remove("hidden");
} else if (TIPO === "agentes") {
  blqAgentes.classList.remove("hidden");
}


/* =====================================
   COMBOS DEPENDIENTES
===================================== */
function updateProvincias(){
  let d = selDep.value;
  selProv.innerHTML = '<option value="">-- Todas --</option>';
  if(d && PROV_DEPT[d]){
    PROV_DEPT[d].forEach(p => {
      selProv.innerHTML += `<option value="${p}">${p}</option>`;
    });
  }
  updateDistritos();
  updateDivisiones();
}
function updateDistritos(){
  let p = selProv.value;
  selDist.innerHTML = '<option value="">-- Todos --</option>';
  if(p && DIST_PROV[p]){
    DIST_PROV[p].forEach(d => {
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

  if(di && DIV_DIST[di]){
    DIV_DIST[di].forEach(v => selDiv.innerHTML += `<option value="${v}">${v}</option>`);
    return;
  }
  if(p && DIV_PROV[p]){
    DIV_PROV[p].forEach(v => selDiv.innerHTML += `<option value="${v}">${v}</option>`);
    return;
  }
  if(d && DIV_DEPT[d]){
    DIV_DEPT[d].forEach(v => selDiv.innerHTML += `<option value="${v}">${v}</option>`);
    return;
  }
  TODAS_DIV.forEach(v => selDiv.innerHTML += `<option value="${v}">${v}</option>`);
}

selDep.onchange  = ()=>{ updateProvincias(); fetchPoints(); };
selProv.onchange = ()=>{ updateDistritos(); fetchPoints(); };
selDist.onchange = ()=>{ updateDivisiones(); fetchPoints(); };
selDiv.onchange  = ()=> fetchPoints();


/* =====================================
   ICONS
===================================== */
function getIcon(pt){
  if(TIPO === "islas"){
    return L.divIcon({
      className:"icon-isla",
      html:"<div>🌐</div>",
      iconSize:[30,30], iconAnchor:[15,15]
    });
  }
  if(TIPO === "oficinas"){
    return L.divIcon({
      className:"icon-oficina",
      html:"<div>🏢</div>",
      iconSize:[30,30], iconAnchor:[15,15]
    });
  }
  if(TIPO === "agentes"){
    return L.divIcon({
      className:"icon-agente",
      html:"<div>🧑‍💼</div>",
      iconSize:[30,30], iconAnchor:[15,15]
    });
  }
}


/* =====================================
   PANEL SELECCIONADO
===================================== */
function showPanel(pt){
  let titulo = "";
  if(TIPO === "islas") titulo = "Panel de una isla seleccionada";
  if(TIPO === "oficinas") titulo = "Panel de una oficina seleccionada";
  if(TIPO === "agentes") titulo = "Panel de un agente seleccionado";

  panelTitulo.textContent = titulo;

  const texto =
`
ATM / TERMINAL: ${pt.atm}
Nombre / Comercio: ${pt.nombre}

Dirección: ${pt.direccion}

División: ${pt.division}
Capa/Tipo: ${pt.tipo}

Ubicación:
${pt.departamento} / ${pt.provincia} / ${pt.distrito}

Promedio: ${pt.promedio}
`;
  atmDetalle.textContent = texto;

  panelResumen.classList.add("hidden");
  panelATM.classList.remove("hidden");
}

btnVolver.onclick = ()=>{
  panelATM.classList.add("hidden");
  panelResumen.classList.remove("hidden");
};


/* =====================================
   FETCH POINTS + RENDER
===================================== */
async function fetchPoints(){
  const d  = selDep.value;
  const p  = selProv.value;
  const di = selDist.value;
  const dv = selDiv.value;

  const query =
    `tipo=${TIPO}&departamento=${encodeURIComponent(d)}&provincia=${encodeURIComponent(p)}&distrito=${encodeURIComponent(di)}&division=${encodeURIComponent(dv)}`;

  panelATM.classList.add("hidden");
  panelResumen.classList.remove("hidden");

  const res = await fetch(`/api/points?${query}`);
  const data = await res.json();

  const pts = data.puntos || [];
  infoCount.textContent = pts.length;

  /* limpiar */
  markers.clearLayers();
  heat.setLatLngs([]);

  let heatPts = [];
  let bounds = [];

  pts.forEach(pt => {
    const icon = getIcon(pt);

    const popup = `
      <div class="popup-title">${pt.nombre}</div>
      <div class="popup-row"><b>ATM:</b> ${pt.atm}</div>
      <div class="popup-row"><b>Dirección:</b> ${pt.direccion}</div>
      <div class="popup-row"><b>División:</b> ${pt.division}</div>
      <div class="popup-row"><b>Capa:</b> ${pt.tipo}</div>
      <div class="popup-row"><b>Ubicación:</b> ${pt.departamento} / ${pt.provincia} / ${pt.distrito}</div>
      <div class="popup-row"><b>Promedio:</b> ${pt.promedio}</div>
    `;

    const m = L.marker([pt.lat, pt.lon], {icon}).bindPopup(popup);
    m.on("click", ()=> showPanel(pt));
    markers.addLayer(m);

    heatPts.push([pt.lat, pt.lon, Math.max(1, pt.promedio || 1)]);
    bounds.push([pt.lat, pt.lon]);
  });

  heat.setLatLngs(heatPts);

  if(bounds.length === 1){
    map.setView(bounds[0], 16);
  } else if(bounds.length > 1){
    map.fitBounds(bounds, {padding:[20,20]});
  } else {
    map.setView(CENTER, ZOOM);
  }

  if(chkHeat.checked){
    if(!map.hasLayer(heat)) heat.addTo(map);
  } else {
    if(map.hasLayer(heat)) map.removeLayer(heat);
  }

  /* Resumen dinámico */
  resProm.textContent = Math.round(data.promedio_total || 0);

  if(TIPO === "islas"){
    resOf.textContent = data.total_oficinas;
    resIs.textContent = data.total_islas;
    resDisp.textContent = data.total_disp;
    resMon.textContent = data.total_mon;
    resRec.textContent = data.total_rec;
  }

  if(TIPO === "oficinas"){
    resDisp.textContent = data.total_disp;
    resMon.textContent = data.total_mon;
    resRec.textContent = data.total_rec;
  }

  if(TIPO === "agentes"){
    resCant.textContent = data.total;
    resA1.textContent = data.capa_A1;
    resA2.textContent = data.capa_A2;
    resA3.textContent = data.capa_A3;
    resB.textContent  = data.capa_B;
    resC.textContent  = data.capa_C;
  }

}

/* primera carga */
updateProvincias();
fetchPoints();
</script>

</body>
</html>
"""




