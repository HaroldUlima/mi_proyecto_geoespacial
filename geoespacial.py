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

if PROM_COL is None:
    raw["PROM_FAKE"] = 0.0
    PROM_COL = "PROM_FAKE"

for c in [
    COL_ATM, COL_DEPT, COL_PROV, COL_DIST, COL_LAT, COL_LON,
    COL_DIV, COL_TIPO, COL_UBIC, PROM_COL,
]:
    if c not in raw.columns:
        raw[c] = ""

df = raw.copy()

df[COL_LAT] = (
    df[COL_LAT].astype(str).str.replace(",", ".", regex=False)
    .str.replace(r"[^\d\.\-]", "", regex=True).replace("", np.nan).astype(float)
)

df[COL_LON] = (
    df[COL_LON].astype(str).str.replace(",", ".", regex=False)
    .str.replace(r"[^\d\.\-]", "", regex=True).replace("", np.nan).astype(float)
)

df = df.dropna(subset=[COL_LAT, COL_LON]).reset_index(drop=True)
df[PROM_COL] = pd.to_numeric(df[PROM_COL], errors="coerce").fillna(0.0)

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
COLA_TRX_OCT = find_col_ag(["TRXS OCTUBRE", "TRX OCTUBRE"])
COLA_TRX_NOV = find_col_ag(["TRXS NOV", "TRXS NOVIEMBRE"])
PROMA_COL = find_col_ag(["PROMEDIO", "PROM"])

if PROMA_COL is None:
    raw_ag["PROM_FAKE"] = 0.0
    PROMA_COL = "PROM_FAKE"

raw_ag[COLA_LAT] = (
    raw_ag[COLA_LAT].astype(str).str.replace(",", ".", regex=False)
    .str.replace(r"[^\d\.\-]", "", regex=True).replace("", np.nan).astype(float)
)

raw_ag[COLA_LON] = (
    raw_ag[COLA_LON].astype(str).str.replace(",", ".", regex=False)
    .str.replace(r"[^\d\.\-]", "", regex=True).replace("", np.nan).astype(float)
)

df_agentes = raw_ag.dropna(subset=[COLA_LAT, COLA_LON]).reset_index(drop=True)
df_agentes[PROMA_COL] = pd.to_numeric(df_agentes[PROMA_COL], errors="coerce").fillna(0.0)

# ============================================================
# 2C. CARGAR EXCEL DE OFICINAS
# ============================================================
excel_oficinas = os.path.join(BASE_DIR, "data", "OFICINAS.xlsx")
if not os.path.exists(excel_oficinas):
    raise FileNotFoundError("No encontré Excel de OFICINAS.")

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
    raw_of[COLF_LAT].astype(str).str.replace(",", ".", regex=False)
    .str.replace(r"[^\d\.\-]", "", regex=True).replace("", np.nan).astype(float)
)

raw_of[COLF_LON] = (
    raw_of[COLF_LON].astype(str).str.replace(",", ".", regex=False)
    .str.replace(r"[^\d\.\-]", "", regex=True).replace("", np.nan).astype(float)
)

df_oficinas = raw_of.dropna(subset=[COLF_LAT, COLF_LON]).reset_index(drop=True)
df_oficinas[COLF_TRX] = pd.to_numeric(df_oficinas[COLF_TRX], errors="coerce").fillna(0.0)

# ============================================================
# 3. LISTAS PARA FILTROS (SIN CAMBIOS)
# ============================================================

# ... (ESTA SECCIÓN CONTINÚA IGUAL — NO SE MODIFICA NADA)

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

        total_atms = int(len(dff))
        promedio_total = float(dff[PROM_COL].mean()) if total_atms > 0 else 0.0
        total_oficinas = int(dff[COL_UBIC].str.contains("OFICINA", na=False).sum())
        total_islas = int(dff[COL_UBIC].str.contains("ISLA", na=False).sum())
        total_disp = int(dff[COL_TIPO].str.contains("DISPENSADOR", na=False).sum())
        total_mon = int(dff[COL_TIPO].str.contains("MONEDERO", na=False).sum())
        total_rec = int(dff[COL_TIPO].str.contains("RECICLADOR", na=False).sum())

        puntos = []
        for _, r in dff.iterrows():
            lat_v = float(r[COL_LAT])
            lon_v = float(r[COL_LON])

            nombre = str(r.get(COL_NAME, "")).strip() or str(r.get(COL_ATM, ""))

            puntos.append({
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
            })

        return jsonify({
            "puntos": puntos,
            "total_atms": total_atms,
            "total_oficinas": total_oficinas,
            "total_islas": total_islas,
            "total_disp": total_disp,
            "total_mon": total_mon,
            "total_rec": total_rec,
            "promedio_total": promedio_total,
            "total_agentes": 0,
            "total_capa_A1": 0,
            "total_capa_A2": 0,
            "total_capa_A3": 0,
            "total_capa_B": 0,
            "total_capa_C": 0,
        })

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
        promedio_total = float(dff[PROMA_COL].mean()) if total_agentes > 0 else 0.0

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

            puntos.append({
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
                "trxs_oct": float(r.get(COLA_TRX_OCT, 0.0)) if COLA_TRX_OCT else 0,
                "trxs_nov": float(r.get(COLA_TRX_NOV, 0.0)) if COLA_TRX_NOV else 0,
            })

        return jsonify({
            "puntos": puntos,
            "total_atms": total_agentes,
            "total_oficinas": 0,
            "total_islas": 0,
            "total_disp": 0,
            "total_mon": 0,
            "total_rec": 0,
            "promedio_total": promedio_total,
            "total_agentes": total_agentes,
            "total_capa_A1": total_capa_A1,
            "total_capa_A2": total_capa_A2,
            "total_capa_A3": total_capa_A3,
            "total_capa_B": total_capa_B,
            "total_capa_C": total_capa_C,
        })

    # ---------------------- CAPA OFICINAS (⚠️ SUMA TRX) ----------------------
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

        # NUEVO: SUMA TOTAL DE TRX
        suma_trx = float(dff[COLF_TRX].sum())

        puntos = []
        for _, r in dff.iterrows():
            lat_v = float(r[COLF_LAT])
            lon_v = float(r[COLF_LON])

            puntos.append({
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
            })

        return jsonify({
            "puntos": puntos,
            "total_atms": total_oficinas,
            "total_oficinas": total_oficinas,
            "total_islas": 0,
            "total_disp": 0,
            "total_mon": 0,
            "total_rec": 0,
            "promedio_total": suma_trx,   # ← Enviamos SUMA TRX en este campo
            "suma_trx": suma_trx,         # ← Campo adicional
            "total_agentes": 0,
            "total_capa_A1": 0,
            "total_capa_A2": 0,
            "total_capa_A3": 0,
            "total_capa_B": 0,
            "total_capa_C": 0,
        })

    # fallback
    return jsonify({
        "puntos": [],
        "total_atms": 0,
        "total_oficinas": 0,
        "total_islas": 0,
        "total_disp": 0,
        "total_mon": 0,
        "total_rec": 0,
        "promedio_total": 0.0,
    })

# ============================================================
# 8. TEMPLATE MAPA — FRONTEND COMPLETO
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
/* … (todo tu CSS se mantiene igual) … */
</style>
</head>

<body>
<header>
  <h1>Mapa BBVA — {{ tipo_mapa|upper }}</h1>
  <a href="/logout" class="logout">Cerrar sesión</a>
</header>

<!-- … CONTROLES … -->

<div class="side">

  <!-- PANEL RESUMEN -->
  <div id="panelResumen" class="side-card">

    <div class="side-title" id="panelResumenTitulo">Resumen</div>

    <div class="muted" id="panelResumenSub">
      {% if tipo_mapa == 'oficinas' %}
      Suma total de TRX:
      {% else %}
      Promedio total:
      {% endif %}
    </div>

    <div style="margin-top:4px;">
      <b>
        {% if tipo_mapa == 'oficinas' %}
        Suma total de TRX:
        {% else %}
        Promedio total:
        {% endif %}
      </b>
      <span id="resPromedio">0</span>
    </div>

    <!-- BLOQUE OFICINAS -->
    <div id="bloqueOficinas" class="hidden" style="margin-top:8px;">
      <div class="muted" style="margin-top:2px;">
        Cantidad total de oficinas: <span id="resOficinasCount">0</span>
      </div>
      <div class="muted" style="margin-top:4px;">
        Suma total de TRX: <span id="resOficinasProm">0</span>
      </div>
    </div>

    <!-- LEYENDA ACTUALIZADA (ICONOS REALES) -->
    <div style="margin-top:10px; font-weight:600;">Leyenda</div>
    <div class="muted" id="legendBox">
      {% if tipo_mapa == 'oficinas' %}
        <img src="{{ url_for('static', filename='oficina.png') }}" width="30"> Oficina
      {% elif tipo_mapa == 'islas' %}
        <img src="{{ url_for('static', filename='oficina.png') }}" width="30"> Oficina<br>
        <img src="{{ url_for('static', filename='isla.png') }}" width="30"> Isla
      {% elif tipo_mapa == 'agentes' %}
        <img src="{{ url_for('static', filename='agente.png') }}" width="30"> Agente
      {% endif %}
    </div>

  </div>

  <!-- PANEL SELECCION (sin cambios) -->
  <div id="panelATM" class="side-card side-card-atm hidden">
    <h3 id="panelATMTitle">Panel seleccionado</h3>
    <div id="atmDetalle"></div>
    <button id="btnVolver" class="btn-small">VOLVER</button>
  </div>

</div>

<script>

/* … TU JS COMPLETO SE MANTIENE IGUAL … */

/* -------- CAMBIOS PARA SUMA TRX -------- */
async function fetchPoints(){
  /* … código normal … */

  const data = await res.json();

  // Para oficinas → usamos suma_trx
  if (TIPO_MAPA === "oficinas"){
    const suma = data.suma_trx || 0;
    resPromedio.textContent = Math.round(suma).toString();
    resOficinasProm.textContent = Math.round(suma).toString();
    resOficinasCount.textContent = (data.total_oficinas || 0).toString();
  }
  else {
    // Islas y agentes sin modificar
    resPromedio.textContent = Math.round(data.promedio_total || 0).toString();
  }

  /* … resto del JS sin tocar … */
}

</script>
</body>
</html>
"""

if __name__ == "__main__":
    app.run(debug=True)