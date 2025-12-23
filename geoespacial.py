# ============================================================
#   BACKEND COMPLETO + LOGIN + SELECTOR
#   CAPAS: ISLAS (ATMs) + AGENTES + OFICINAS + INTEGRAL
#   ✅ + ZONAS RURAL / URBANA (ZONAS.xlsx) con BORDE NEÓN
#      - Rural: verde fosforescente
#      - Urbana: amarillo fosforescente
#      - Se actualiza con filtros y funciona en las 4 capas
#   ✅ + NODOS (NODOS1.xlsx) -> GLOBOS ROJOS GRANDES con letras blancas + brillo
#      - Se actualiza con filtros y funciona en las 4 capas (checkbox)
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
try:
    recomendaciones = pd.read_csv("data/recomendaciones.csv")
except Exception as e:
    print("⚠ No se pudo cargar recomendaciones.csv:", e)
    recomendaciones = pd.DataFrame()

# ============================================================
# NUEVO — Cargar base de clientes
# ============================================================
df_clientes = pd.read_csv("data/clientes_huanuco_v6.csv")
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
# HELPERS
# ============================================================
def normalize_col(s):
    s = str(s)
    s = unicodedata.normalize("NFKD", s)
    s = s.encode("ascii", "ignore").decode("utf-8")
    s = s.upper().strip()
    s = re.sub(r"[^A-Z0-9 ]+", " ", s)
    return re.sub(r"\s+", " ", s).strip()

def clean_str(x):
    return str(x).upper().strip() if pd.notnull(x) else ""

def to_num_series(s):
    return pd.to_numeric(s, errors="coerce").fillna(0.0)

def parse_percent_series(s):
    """
    Convierte series tipo '84.24%' o 0.8424 a un número 0..100.
    """
    if s is None:
        return pd.Series([0.0])
    ss = s.astype(str).str.replace(",", ".", regex=False)
    ss = ss.str.replace("%", "", regex=False)
    ss = ss.str.replace(r"[^\d\.\-]", "", regex=True)
    v = pd.to_numeric(ss, errors="coerce").fillna(0.0)
    # si viene como 0-1, lo pasamos a 0-100
    if len(v) and v.max() <= 1.0:
        v = v * 100.0
    return v

# ============================================================
# 2. CARGAR EXCEL PRINCIPAL (ISLAS / ATMs)
# ============================================================
BASE_DIR = os.path.dirname(__file__)
excel_main = os.path.join(BASE_DIR, "data", "Mapa Geoespacial ATM (1) (1).xlsx")
if not os.path.exists(excel_main):
    raise FileNotFoundError("No encontré archivo Excel de ATMs.")

raw = pd.read_excel(excel_main)
norm_map = {normalize_col(c): c for c in raw.columns}

def find_col(keys):
    for norm, orig in norm_map.items():
        for k in keys:
            if k in norm:
                return orig
    return None

COL_ATM  = find_col(["COD_ATM", "ATM"]) or "ATM"
COL_NAME = find_col(["NOMBRE", "CAJERO"]) or None
COL_DEPT = find_col(["DEPARTAMENTO"]) or "DEPARTAMENTO"
COL_PROV = find_col(["PROVINCIA"]) or "PROVINCIA"
COL_DIST = find_col(["DISTRITO"]) or "DISTRITO"
COL_LAT  = find_col(["LATITUD", "LAT"]) or "LATITUD"
COL_LON  = find_col(["LONGITUD", "LON"]) or "LONGITUD"
COL_DIV  = find_col(["DIVISION", "DIVISIÓN"]) or "DIVISIÓN"
COL_TIPO = find_col(["TIPO"]) or "TIPO"
COL_UBIC = find_col(["UBICACION", "UBICACIÓN", "UBICACION INTERNA"]) or "UBICACION_INTERNA"
PROM_COL = find_col(["PROMEDIO", "PROM"]) or None

if PROM_COL is None:
    raw["PROM_FAKE"] = 0.0
    PROM_COL = "PROM_FAKE"

for c in [COL_ATM, COL_DEPT, COL_PROV, COL_DIST, COL_LAT, COL_LON, COL_DIV, COL_TIPO, COL_UBIC, PROM_COL]:
    if c not in raw.columns:
        raw[c] = ""

df = raw.copy()

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

COLA_ID   = find_col_ag(["TERMINAL", "ID"]) or "TERMINAL"
COLA_COM  = find_col_ag(["COMERCIO"]) or "COMERCIO"
COLA_DEPT = find_col_ag(["DEPARTAMENTO"]) or "DEPARTAMENTO"
COLA_PROV = find_col_ag(["PROVINCIA"]) or "PROVINCIA"
COLA_DIST = find_col_ag(["DISTRITO"]) or "DISTRITO"
COLA_LAT  = find_col_ag(["LATITUD", "LAT"]) or "LATITUD"
COLA_LON  = find_col_ag(["LONGITUD", "LON"]) or "LONGITUD"
COLA_DIV  = find_col_ag(["DIVISION", "DIVISIÓN"]) or "DIVISION"
COLA_DIR  = find_col_ag(["DIRECCION", "DIRECCIÓN"]) or "DIRECCION"
COLA_CAPA = find_col_ag(["CAPA"]) or "CAPA"
COLA_TRX_OCT = find_col_ag(["TRXS OCTUBRE", "TRX OCTUBRE"]) or None
COLA_TRX_NOV = find_col_ag(["TRXS NOV", "TRXS NOVIEMBRE"]) or None
PROMA_COL = find_col_ag(["PROMEDIO", "PROM"]) or None

if PROMA_COL is None:
    raw_ag["PROM_FAKE"] = 0.0
    PROMA_COL = "PROM_FAKE"

raw_ag[COLA_LAT] = (
    raw_ag[COLA_LAT].astype(str)
    .str.replace(",", ".", regex=False)
    .str.replace(r"[^\d\.\-]", "", regex=True)
    .replace("", np.nan)
    .astype(float)
)
raw_ag[COLA_LON] = (
    raw_ag[COLA_LON].astype(str)
    .str.replace(",", ".", regex=False)
    .str.replace(r"[^\d\.\-]", "", regex=True)
    .replace("", np.nan)
    .astype(float)
)

df_agentes = raw_ag.dropna(subset=[COLA_LAT, COLA_LON]).reset_index(drop=True)
df_agentes[PROMA_COL] = pd.to_numeric(df_agentes[PROMA_COL], errors="coerce").fillna(0.0)
df_agentes[COLA_CAPA] = df_agentes[COLA_CAPA].astype(str).fillna("")

# ============================================================
# 2C. CARGAR EXCEL DE OFICINAS  ✅ (AHORA CON COLUMNAS NUEVAS)
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

COLF_ID   = find_col_of(["COD OFIC", "COD. OFIC", "COD_OFIC"]) or "COD OFIC."
COLF_NAME = find_col_of(["OFICINA"]) or "OFICINA"
COLF_DIV  = find_col_of(["DIVISION", "DIVISIÓN"]) or "DIVISION"
COLF_DEPT = find_col_of(["DEPARTAMENTO"]) or "DEPARTAMENTO"
COLF_PROV = find_col_of(["PROVINCIA"]) or "PROVINCIA"
COLF_DIST = find_col_of(["DISTRITO"]) or "DISTRITO"
COLF_LAT  = find_col_of(["LATITUD", "LAT"]) or "LATITUD"
COLF_LON  = find_col_of(["LONGITUD", "LON"]) or "LONGITUD"
COLF_TRX  = find_col_of(["TRX", "TRXS"]) or "TRX"

# ✅ NUEVAS COLUMNAS (PROMEDIOS)
COLF_EAS = find_col_of(["ESTRUCTURA AS", "ESTRUCTURA_AS"]) or "ESTRUCTURA AS"
COLF_EBP = find_col_of(["ESTRUCTURA EBP", "ESTRUCTURA_EBP"]) or "ESTRUCTURA EBP"
COLF_EAD = find_col_of(["ESTRUCTURA AD", "ESTRUCTURA_AD"]) or "ESTRUCTURA AD"
COLF_CLI = find_col_of(["CLIENTES UNICOS", "CLIENTES ÚNICOS", "CLIENTES_UNICOS"]) or "CLIENTES UNICOS"
COLF_TKT = find_col_of(["TOTAL_TICKETS", "TOTAL TICKETS"]) or "TOTAL_TICKETS"
COLF_RED = find_col_of(["RED LINES", "REDLINES", "RED_LINES"]) or "RED LINES"

for c in [COLF_EAS, COLF_EBP, COLF_EAD, COLF_CLI, COLF_TKT, COLF_RED]:
    if c not in raw_of.columns:
        raw_of[c] = 0

raw_of[COLF_LAT] = (
    raw_of[COLF_LAT].astype(str)
    .str.replace(",", ".", regex=False)
    .str.replace(r"[^\d\.\-]", "", regex=True)
    .replace("", np.nan)
    .astype(float)
)
raw_of[COLF_LON] = (
    raw_of[COLF_LON].astype(str)
    .str.replace(",", ".", regex=False)
    .str.replace(r"[^\d\.\-]", "", regex=True)
    .replace("", np.nan)
    .astype(float)
)

df_oficinas = raw_of.dropna(subset=[COLF_LAT, COLF_LON]).reset_index(drop=True)

df_oficinas[COLF_TRX] = pd.to_numeric(df_oficinas[COLF_TRX], errors="coerce").fillna(0.0)
df_oficinas[COLF_EAS] = pd.to_numeric(df_oficinas[COLF_EAS], errors="coerce").fillna(0.0)
df_oficinas[COLF_EBP] = pd.to_numeric(df_oficinas[COLF_EBP], errors="coerce").fillna(0.0)
df_oficinas[COLF_EAD] = pd.to_numeric(df_oficinas[COLF_EAD], errors="coerce").fillna(0.0)
df_oficinas[COLF_CLI] = pd.to_numeric(df_oficinas[COLF_CLI], errors="coerce").fillna(0.0)
df_oficinas[COLF_TKT] = pd.to_numeric(df_oficinas[COLF_TKT], errors="coerce").fillna(0.0)
df_oficinas[COLF_RED] = parse_percent_series(df_oficinas[COLF_RED])

# ============================================================
# 2D. CARGAR ZONAS (URBANA / RURAL) ✅ NUEVO (ZONAS.xlsx)
#   - Lee: DEP/PROV/DIST, UBIGEO DIST, CP, UBIGEO CP, TIPO, LAT, LON
#   - Devuelve polígonos "hull" por filtros para dibujar bordes neón
# ============================================================
excel_zonas_local = os.path.join(BASE_DIR, "data", "ZONAS.xlsx")
excel_zonas_alt = "/mnt/data/ZONAS.xlsx"  # por si lo tienes montado/temporal
excel_zonas = excel_zonas_local if os.path.exists(excel_zonas_local) else (excel_zonas_alt if os.path.exists(excel_zonas_alt) else "")

df_zonas = pd.DataFrame(columns=[
    "DEPARTAMENTO", "PROVINCIA", "DISTRITO",
    "UBIGEO_DIST", "CENTRO_POBLADO", "UBIGEO_CP",
    "TIPO_ZONA", "LATITUD", "LONGITUD"
])

if excel_zonas:
    try:
        raw_z = pd.read_excel(excel_zonas)

        # columnas esperadas
        for c in [
            "DEPARTAMENTO","PROVINCIA","DISTRITO","UBIGEO DEL DISTRITO",
            "NOMBRE DEL CENTRO POBLADO","UBIGEO DEL CENTRO POBLADO",
            "TIPO DE CENTRO POBLADO","LATITUD","LONGITUD"
        ]:
            if c not in raw_z.columns:
                raw_z[c] = ""

        raw_z["DEPARTAMENTO"] = raw_z["DEPARTAMENTO"].apply(clean_str)
        raw_z["PROVINCIA"] = raw_z["PROVINCIA"].apply(clean_str)
        raw_z["DISTRITO"] = raw_z["DISTRITO"].apply(clean_str)

        raw_z["UBIGEO_DIST"] = raw_z["UBIGEO DEL DISTRITO"].astype(str).str.replace(r"\.0$", "", regex=True).str.strip()
        raw_z["UBIGEO_CP"]   = raw_z["UBIGEO DEL CENTRO POBLADO"].astype(str).str.replace(r"\.0$", "", regex=True).str.strip()

        raw_z["CENTRO_POBLADO"] = raw_z["NOMBRE DEL CENTRO POBLADO"].astype(str).str.upper().str.strip()
        raw_z["TIPO_ZONA"] = raw_z["TIPO DE CENTRO POBLADO"].astype(str).str.upper().str.strip()

        raw_z["LATITUD"] = (
            raw_z["LATITUD"].astype(str)
            .str.replace(",", ".", regex=False)
            .str.replace(r"[^\d\.\-]", "", regex=True)
            .replace("", np.nan)
            .astype(float)
        )
        raw_z["LONGITUD"] = (
            raw_z["LONGITUD"].astype(str)
            .str.replace(",", ".", regex=False)
            .str.replace(r"[^\d\.\-]", "", regex=True)
            .replace("", np.nan)
            .astype(float)
        )

        df_zonas = raw_z.dropna(subset=["LATITUD", "LONGITUD"]).reset_index(drop=True)
        df_zonas = df_zonas[[
            "DEPARTAMENTO","PROVINCIA","DISTRITO",
            "UBIGEO_DIST","CENTRO_POBLADO","UBIGEO_CP",
            "TIPO_ZONA","LATITUD","LONGITUD"
        ]].copy()

        print(f"✅ ZONAS.xlsx cargado: {len(df_zonas)} filas ({excel_zonas})")
    except Exception as e:
        print("⚠ No se pudo cargar ZONAS.xlsx:", e)
else:
    print("⚠ No existe ZONAS.xlsx (bordes rural/urbano desactivados).")

# Cache en memoria para no recalcular hull cada vez
ZONAS_HULL_CACHE = {}

def _convex_hull_xy(points_xy):
    """
    Monotonic chain convex hull.
    points_xy: iterable de (x=lon, y=lat)
    return: lista de (x,y) en orden del hull
    """
    pts = sorted(set(points_xy))
    if len(pts) <= 1:
        return pts

    def cross(o, a, b):
        return (a[0]-o[0])*(b[1]-o[1]) - (a[1]-o[1])*(b[0]-o[0])

    lower = []
    for p in pts:
        while len(lower) >= 2 and cross(lower[-2], lower[-1], p) <= 0:
            lower.pop()
        lower.append(p)

    upper = []
    for p in reversed(pts):
        while len(upper) >= 2 and cross(upper[-2], upper[-1], p) <= 0:
            upper.pop()
        upper.append(p)

    return lower[:-1] + upper[:-1]

def _rect_from_points(points_xy, pad_min=0.01):
    xs = [p[0] for p in points_xy]
    ys = [p[1] for p in points_xy]
    minx, maxx = min(xs), max(xs)
    miny, maxy = min(ys), max(ys)

    if minx == maxx and miny == maxy:
        padx = pady = pad_min
    else:
        padx = max(pad_min, (maxx - minx) * 0.05)
        pady = max(pad_min, (maxy - miny) * 0.05)

    minx -= padx; maxx += padx
    miny -= pady; maxy += pady
    return [(minx, miny), (maxx, miny), (maxx, maxy), (minx, maxy)]

def _zona_polygon_latlon(dff):
    """
    Devuelve polígono como lista [[lat,lon], ...]
    """
    if dff is None or dff.empty:
        return []

    pts_xy = list(zip(dff["LONGITUD"].astype(float).tolist(), dff["LATITUD"].astype(float).tolist()))
    if len(pts_xy) < 3:
        rect = _rect_from_points(pts_xy) if len(pts_xy) > 0 else []
        return [[y, x] for (x, y) in rect]

    hull = _convex_hull_xy(pts_xy)
    if len(hull) < 3:
        rect = _rect_from_points(pts_xy)
        return [[y, x] for (x, y) in rect]

    return [[y, x] for (x, y) in hull]

# ============================================================
# 2E. CARGAR NODOS (NODOS1.xlsx) ✅ NUEVO
#   - columnas esperadas (flexible): UBIGEO, DEPARTAMENTO, PROVINCIA, DISTRITO, NOMBRE, LATITUD, LONGITUD
#   - se usa para globos rojos con texto en el mapa (4 capas)
# ============================================================
excel_nodos_local = os.path.join(BASE_DIR, "data", "NODOS1.xlsx")
excel_nodos_alt = "/mnt/data/NODOS1.xlsx"
excel_nodos = excel_nodos_local if os.path.exists(excel_nodos_local) else (excel_nodos_alt if os.path.exists(excel_nodos_alt) else "")

df_nodos = pd.DataFrame(columns=["UBIGEO","DEPARTAMENTO","PROVINCIA","DISTRITO","NOMBRE","LATITUD","LONGITUD"])

if excel_nodos:
    try:
        raw_n = pd.read_excel(excel_nodos)
        norm_map_n = {normalize_col(c): c for c in raw_n.columns}

        def find_col_n(keys):
            for norm, orig in norm_map_n.items():
                for k in keys:
                    if k in norm:
                        return orig
            return None

        COLN_UBI = find_col_n(["UBIGEO"]) or "UBIGEO"
        COLN_DEP = find_col_n(["DEPARTAMENTO"]) or "DEPARTAMENTO"
        COLN_PRO = find_col_n(["PROVINCIA"]) or "PROVINCIA"
        COLN_DIS = find_col_n(["DISTRITO"]) or "DISTRITO"
        COLN_NOM = find_col_n(["NOMBRE"]) or "NOMBRE"
        COLN_LAT = find_col_n(["LATITUD", "LAT"]) or "LATITUD"
        COLN_LON = find_col_n(["LONGITUD", "LON"]) or "LONGITUD"

        for c in [COLN_UBI, COLN_DEP, COLN_PRO, COLN_DIS, COLN_NOM, COLN_LAT, COLN_LON]:
            if c not in raw_n.columns:
                raw_n[c] = ""

        raw_n[COLN_DEP] = raw_n[COLN_DEP].apply(clean_str)
        raw_n[COLN_PRO] = raw_n[COLN_PRO].apply(clean_str)
        raw_n[COLN_DIS] = raw_n[COLN_DIS].apply(clean_str)

        raw_n[COLN_UBI] = (
            raw_n[COLN_UBI].astype(str)
            .str.replace(r"\.0$", "", regex=True)
            .str.strip()
        )
        raw_n[COLN_NOM] = raw_n[COLN_NOM].astype(str).str.strip()

        raw_n[COLN_LAT] = (
            raw_n[COLN_LAT].astype(str)
            .str.replace(",", ".", regex=False)
            .str.replace(r"[^\d\.\-]", "", regex=True)
            .replace("", np.nan)
            .astype(float)
        )
        raw_n[COLN_LON] = (
            raw_n[COLN_LON].astype(str)
            .str.replace(",", ".", regex=False)
            .str.replace(r"[^\d\.\-]", "", regex=True)
            .replace("", np.nan)
            .astype(float)
        )

        df_nodos = raw_n.dropna(subset=[COLN_LAT, COLN_LON]).copy()

        df_nodos = df_nodos.rename(columns={
            COLN_UBI: "UBIGEO",
            COLN_DEP: "DEPARTAMENTO",
            COLN_PRO: "PROVINCIA",
            COLN_DIS: "DISTRITO",
            COLN_NOM: "NOMBRE",
            COLN_LAT: "LATITUD",
            COLN_LON: "LONGITUD",
        })

        df_nodos = df_nodos[["UBIGEO","DEPARTAMENTO","PROVINCIA","DISTRITO","NOMBRE","LATITUD","LONGITUD"]].copy()
        print(f"✅ NODOS1.xlsx cargado: {len(df_nodos)} filas ({excel_nodos})")
    except Exception as e:
        print("⚠ No se pudo cargar NODOS1.xlsx:", e)
else:
    print("⚠ No existe NODOS1.xlsx (globos rojos desactivados).")

# ============================================================
# 3. JERARQUÍA TOTAL UNIFICADA (CLIENTES + TODOS LOS CANALES + NODOS)
# ============================================================
geo_frames = []
geo_frames.append(
    df[[COL_DEPT, COL_PROV, COL_DIST]].rename(
        columns={COL_DEPT: "departamento", COL_PROV: "provincia", COL_DIST: "distrito"}
    )
)
geo_frames.append(
    df_agentes[[COLA_DEPT, COLA_PROV, COLA_DIST]].rename(
        columns={COLA_DEPT: "departamento", COLA_PROV: "provincia", COLA_DIST: "distrito"}
    )
)
geo_frames.append(
    df_oficinas[[COLF_DEPT, COLF_PROV, COLF_DIST]].rename(
        columns={COLF_DEPT: "departamento", COLF_PROV: "provincia", COLF_DIST: "distrito"}
    )
)
geo_frames.append(df_clientes[["departamento", "provincia", "distrito"]])

# ✅ NODOS para que también entren en filtros Dep/Prov/Dist
if df_nodos is not None and not df_nodos.empty:
    geo_frames.append(
        df_nodos[["DEPARTAMENTO","PROVINCIA","DISTRITO"]].rename(
            columns={"DEPARTAMENTO":"departamento","PROVINCIA":"provincia","DISTRITO":"distrito"}
        )
    )

geo_all = pd.concat(geo_frames, ignore_index=True)
geo_all["departamento"] = geo_all["departamento"].apply(clean_str)
geo_all["provincia"] = geo_all["provincia"].apply(clean_str)
geo_all["distrito"] = geo_all["distrito"].apply(clean_str)
geo_all = geo_all.dropna()

DEPARTAMENTOS = sorted(geo_all["departamento"].unique())

PROVINCIAS_BY_DEPT = {}
for dep in DEPARTAMENTOS:
    provs = geo_all.loc[geo_all["departamento"] == dep, "provincia"].unique().tolist()
    PROVINCIAS_BY_DEPT[dep] = sorted([p for p in provs if p])

DIST_BY_PROV = {}
provincias_unicas = sorted(geo_all["provincia"].unique())
for prov in provincias_unicas:
    dists = geo_all.loc[geo_all["provincia"] == prov, "distrito"].unique().tolist()
    DIST_BY_PROV[prov] = sorted([d for d in dists if d])

# ============================================================
# UNIFICACIÓN DE DIVISIONES (Islas + Oficinas + Agentes)
# ============================================================
div_frames = []
div_frames.append(
    df[[COL_DEPT, COL_PROV, COL_DIST, COL_DIV]].rename(
        columns={COL_DEPT: "departamento", COL_PROV: "provincia", COL_DIST: "distrito", COL_DIV: "division"}
    )
)
div_frames.append(
    df_agentes[[COLA_DEPT, COLA_PROV, COLA_DIST, COLA_DIV]].rename(
        columns={COLA_DEPT: "departamento", COLA_PROV: "provincia", COLA_DIST: "distrito", COLA_DIV: "division"}
    )
)
div_frames.append(
    df_oficinas[[COLF_DEPT, COLF_PROV, COLF_DIST, COLF_DIV]].rename(
        columns={COLF_DEPT: "departamento", COLF_PROV: "provincia", COLF_DIST: "distrito", COLF_DIV: "division"}
    )
)

div_all = pd.concat(div_frames, ignore_index=True)
div_all["departamento"] = div_all["departamento"].apply(clean_str)
div_all["provincia"] = div_all["provincia"].apply(clean_str)
div_all["distrito"] = div_all["distrito"].apply(clean_str)
div_all["division"] = div_all["division"].apply(clean_str)

DIVISIONES = sorted(div_all["division"].dropna().unique())

DIVISIONES_BY_DEPT = {}
for dep in DEPARTAMENTOS:
    divs = div_all.loc[div_all["departamento"] == dep, "division"].dropna().unique().tolist()
    DIVISIONES_BY_DEPT[dep] = sorted(set(divs))

DIVISIONES_BY_PROV = {}
for dep, prov_list in PROVINCIAS_BY_DEPT.items():
    for p in prov_list:
        divs = div_all.loc[div_all["provincia"] == p, "division"].dropna().unique().tolist()
        DIVISIONES_BY_PROV[p] = sorted(set(divs))

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

APP_USER = os.getenv("APP_USERNAME", "adminbbva")
APP_PASS = os.getenv("APP_PASSWORD", "clave123")

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
      background:url('{{ url_for('static', filename='bbva.png') }}') no-repeat center center fixed;
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
      width:100%;
      padding:10px;
      margin:8px 0;
      border-radius:8px;
      border:1px solid #ddd;
    }
    button{
      width:100%;
      padding:10px;
      background:#1464A5;
      color:white;
      border:none;
      border-radius:8px;
      font-weight:600;
      cursor:pointer;
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
    body{ margin:0; padding:40px 20px; font-family:Arial,Helvetica,sans-serif; background:#eef4fb; }
    h1{ text-align:center; color:#072146; }
    .grid{ margin-top:40px; display:flex; justify-content:center; gap:40px; flex-wrap:wrap; }
    .card{
      width:320px; height:260px; background:white; border-radius:20px;
      box-shadow:0 8px 26px rgba(0,0,0,0.15);
      cursor:pointer;
      display:flex; flex-direction:column; align-items:center; justify-content:flex-start;
      padding:16px 14px;
      transition:transform .18s ease, box-shadow .18s ease;
    }
    .card:hover{ transform:translateY(-4px) scale(1.02); box-shadow:0 12px 32px rgba(0,0,0,0.25); }
    .card img{ width:100%; height:170px; object-fit:cover; border-radius:14px; }
    .card-title{ margin-top:12px; font-size:18px; font-weight:700; color:#072146; display:flex; align-items:center; gap:8px; }
    .card-title span.icon{ font-size:22px; }
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
# ✅ API ZONAS — /api/zonas (RURAL / URBANA)
#   - Devuelve hull por filtros (departamento/provincia/distrito)
# ============================================================
@app.route("/api/zonas")
@login_required
def api_zonas():
    dpto = request.args.get("departamento", "").upper().strip()
    prov = request.args.get("provincia", "").upper().strip()
    dist = request.args.get("distrito", "").upper().strip()

    def build_for(tipo_key):
        cache_key = (dpto, prov, dist, tipo_key)
        if cache_key in ZONAS_HULL_CACHE:
            return ZONAS_HULL_CACHE[cache_key]

        dff = df_zonas
        if dpto: dff = dff[dff["DEPARTAMENTO"] == dpto]
        if prov: dff = dff[dff["PROVINCIA"] == prov]
        if dist: dff = dff[dff["DISTRITO"] == dist]

        dff_t = dff[dff["TIPO_ZONA"].astype(str).str.contains(tipo_key, na=False)]
        poly = _zona_polygon_latlon(dff_t)
        out = {"count": int(len(dff_t)), "poly": poly}
        ZONAS_HULL_CACHE[cache_key] = out
        return out

    # URBAN cubre URBANO / URBANA
    rural = build_for("RURAL")
    urban = build_for("URBAN")

    return jsonify({"rural": rural, "urbano": urban})

# ============================================================
# ✅ API NODOS — /api/nodos (globos rojos)
#   - Devuelve nodos filtrados por departamento/provincia/distrito
# ============================================================
@app.route("/api/nodos")
@login_required
def api_nodos():
    dpto = request.args.get("departamento", "").upper().strip()
    prov = request.args.get("provincia", "").upper().strip()
    dist = request.args.get("distrito", "").upper().strip()

    if df_nodos is None or df_nodos.empty:
        return jsonify({"total": 0, "nodos": []})

    dff = df_nodos.copy()
    dff["DEPARTAMENTO"] = dff["DEPARTAMENTO"].astype(str).str.upper().str.strip()
    dff["PROVINCIA"] = dff["PROVINCIA"].astype(str).str.upper().str.strip()
    dff["DISTRITO"] = dff["DISTRITO"].astype(str).str.upper().str.strip()

    if dpto: dff = dff[dff["DEPARTAMENTO"] == dpto]
    if prov: dff = dff[dff["PROVINCIA"] == prov]
    if dist: dff = dff[dff["DISTRITO"] == dist]

    nodos = []
    for _, r in dff.iterrows():
        nodos.append({
            "ubigeo": str(r.get("UBIGEO","")).strip(),
            "departamento": str(r.get("DEPARTAMENTO","")).strip(),
            "provincia": str(r.get("PROVINCIA","")).strip(),
            "distrito": str(r.get("DISTRITO","")).strip(),
            "nombre": str(r.get("NOMBRE","")).strip(),
            "lat": float(r.get("LATITUD", 0.0)),
            "lon": float(r.get("LONGITUD", 0.0)),
        })

    return jsonify({"total": len(nodos), "nodos": nodos})

# ============================================================
# 6. RUTAS MAPA
# ============================================================
@app.route("/mapa/integral")
@login_required
def mapa_integral():
    initial_center = df[[COL_LAT, COL_LON]].mean().tolist()
    return render_template_string(
        TEMPLATE_MAPA,
        tipo_mapa="integral",
        departamentos=DEPARTAMENTOS,
        provincias_by_dept=PROVINCIAS_BY_DEPT,
        dist_by_prov=DIST_BY_PROV,
        div_by_dept=DIVISIONES_BY_DEPT,
        div_by_prov=DIVISIONES_BY_PROV,
        div_by_dist=DIVISIONES_BY_DIST,
        divisiones=DIVISIONES,
        segment_list=SEGMENTOS_CLIENTES,
        initial_center=initial_center,
        initial_zoom=6,
    )

@app.route("/mapa/<tipo>")
@login_required
def mapa_tipo(tipo):
    if tipo not in ["oficinas", "islas", "agentes"]:
        return "No existe esa capa", 404
    initial_center = df[[COL_LAT, COL_LON]].mean().tolist()
    return render_template_string(
        TEMPLATE_MAPA,
        tipo_mapa=tipo,
        departamentos=DEPARTAMENTOS,
        provincias_by_dept=PROVINCIAS_BY_DEPT,
        dist_by_prov=DIST_BY_PROV,
        div_by_dept=DIVISIONES_BY_DEPT,
        div_by_prov=DIVISIONES_BY_PROV,
        div_by_dist=DIVISIONES_BY_DIST,
        divisiones=DIVISIONES,
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

        if dpto: dff = dff[dff[COL_DEPT] == dpto]
        if prov: dff = dff[dff[COL_PROV] == prov]
        if dist: dff = dff[dff[COL_DIST] == dist]
        if divi: dff = dff[dff[COL_DIV] == divi]
        if tipo_atm: dff = dff[dff[COL_TIPO].str.contains(tipo_atm, na=False)]
        if ubic_atm: dff = dff[dff[COL_UBIC].str.contains(ubic_atm, na=False)]

        total_atms = int(len(dff))
        suma_total = float(dff[PROM_COL].sum()) if total_atms > 0 else 0.0

        total_oficinas = int(dff[COL_UBIC].str.contains("OFICINA", na=False).sum())
        total_islas = int(dff[COL_UBIC].str.contains("ISLA", na=False).sum())
        total_disp = int(dff[COL_TIPO].str.contains("DISPENSADOR", na=False).sum())
        total_mon = int(dff[COL_TIPO].str.contains("MONEDERO", na=False).sum())
        total_rec = int(dff[COL_TIPO].str.contains("RECICLADOR", na=False).sum())

        puntos = []
        for _, r in dff.iterrows():
            nombre = ""
            if COL_NAME and COL_NAME in r.index:
                nombre = str(r.get(COL_NAME, "")).strip()
            if not nombre:
                nombre = str(r.get(COL_ATM, ""))

            lat_v = float(r[COL_LAT])
            lon_v = float(r[COL_LON])
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
                "capa": "",
            })

        return jsonify({
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
        })

    # ---------------------- CAPA AGENTES ----------------------
    if tipo_mapa == "agentes":
        dff = df_agentes.copy()
        dff[COLA_DEPT] = dff[COLA_DEPT].astype(str).str.upper().str.strip()
        dff[COLA_PROV] = dff[COLA_PROV].astype(str).str.upper().str.strip()
        dff[COLA_DIST] = dff[COLA_DIST].astype(str).str.upper().str.strip()
        dff[COLA_DIV] = dff[COLA_DIV].astype(str).str.upper().str.strip()
        dff[COLA_CAPA] = dff[COLA_CAPA].astype(str).str.upper().str.strip()

        if dpto: dff = dff[dff[COLA_DEPT] == dpto]
        if prov: dff = dff[dff[COLA_PROV] == prov]
        if dist: dff = dff[dff[COLA_DIST] == dist]
        if divi: dff = dff[dff[COLA_DIV] == divi]

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
                "trxs_oct": float(r.get(COLA_TRX_OCT, 0.0)) if COLA_TRX_OCT else 0.0,
                "trxs_nov": float(r.get(COLA_TRX_NOV, 0.0)) if COLA_TRX_NOV else 0.0,
            })

        return jsonify({
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
        })

    # ---------------------- CAPA OFICINAS ✅ (CON PROMEDIOS NUEVOS) ----------------------
    if tipo_mapa == "oficinas":
        dff = df_oficinas.copy()
        dff[COLF_DEPT] = dff[COLF_DEPT].astype(str).str.upper().str.strip()
        dff[COLF_PROV] = dff[COLF_PROV].astype(str).str.upper().str.strip()
        dff[COLF_DIST] = dff[COLF_DIST].astype(str).str.upper().str.strip()
        dff[COLF_DIV] = dff[COLF_DIV].astype(str).str.upper().str.strip()

        if dpto: dff = dff[dff[COLF_DEPT] == dpto]
        if prov: dff = dff[dff[COLF_PROV] == prov]
        if dist: dff = dff[dff[COLF_DIST] == dist]
        if divi: dff = dff[dff[COLF_DIV] == divi]

        total_oficinas = int(len(dff))
        suma_total = float(dff[COLF_TRX].sum()) if total_oficinas > 0 else 0.0

        prom_eas = float(dff[COLF_EAS].mean()) if total_oficinas > 0 else 0.0
        prom_ebp = float(dff[COLF_EBP].mean()) if total_oficinas > 0 else 0.0
        prom_ead = float(dff[COLF_EAD].mean()) if total_oficinas > 0 else 0.0
        prom_cli = float(dff[COLF_CLI].mean()) if total_oficinas > 0 else 0.0
        prom_tkt = float(dff[COLF_TKT].mean()) if total_oficinas > 0 else 0.0
        prom_red = float(dff[COLF_RED].mean()) if total_oficinas > 0 else 0.0  # 0..100

        puntos = []
        for _, r in dff.iterrows():
            puntos.append({
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
                "capa": "",
                "estructura_as": float(r.get(COLF_EAS, 0.0)),
                "estructura_ebp": float(r.get(COLF_EBP, 0.0)),
                "estructura_ad": float(r.get(COLF_EAD, 0.0)),
                "clientes_unicos": int(r.get(COLF_CLI, 0)),
                "total_tickets": int(r.get(COLF_TKT, 0)),
                "red_lines": float(r.get(COLF_RED, 0.0)),
            })

        return jsonify({
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

            "prom_estructura_as": prom_eas,
            "prom_estructura_ebp": prom_ebp,
            "prom_estructura_ad": prom_ead,
            "prom_clientes_unicos": prom_cli,
            "prom_total_tickets": prom_tkt,
            "prom_redlines": prom_red,
        })

    return jsonify({
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
    })

# ============================================================
# ENDPOINT DE CLIENTES CON MUESTREO DINÁMICO
# ============================================================
@app.route("/api/clientes")
@login_required
def api_clientes():
    zoom_str = request.args.get("zoom", "10")
    try:
        zoom = int(float(zoom_str))
    except:
        zoom = 10

    dpto = request.args.get("departamento", "").upper().strip()
    prov = request.args.get("provincia", "").upper().strip()
    dist = request.args.get("distrito", "").upper().strip()
    seg = request.args.get("segmento", "").upper().strip()

    dff = df_clientes.copy()
    if dpto: dff = dff[dff["departamento"].str.upper() == dpto]
    if prov: dff = dff[dff["provincia"].str.upper() == prov]
    if dist: dff = dff[dff["distrito"].str.upper() == dist]
    if seg:  dff = dff[dff["segmento"].astype(str).str.upper() == seg]

    if dff.empty:
        return jsonify([])

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

    puntos = [{"lat": float(r.latitud), "lon": float(r.longitud)} for _, r in df_sample.iterrows()]
    return jsonify(puntos)

# ============================================================
# API — RESUMEN DE CLIENTES VISIBLE SEGÚN FILTROS
# ============================================================
@app.route("/api/resumen_clientes")
@login_required
def api_resumen_clientes():
    dpto = request.args.get("departamento", "").upper().strip()
    prov = request.args.get("provincia", "").upper().strip()
    dist = request.args.get("distrito", "").upper().strip()
    segmento = request.args.get("segmento", "").upper().strip()

    dff = df_clientes.copy()
    if dpto: dff = dff[dff["departamento"].str.upper() == dpto]
    if prov: dff = dff[dff["provincia"].str.upper() == prov]
    if dist: dff = dff[dff["distrito"].str.upper() == dist]
    if segmento: dff = dff[dff["segmento"].astype(str).str.upper() == segmento]

    if dff.empty:
        return jsonify({
            "total": 0, "digital_pct": 0, "edad_prom": 0,
            "ingreso_prom": 0, "deuda_prom": 0, "top_segmento": "—"
        })

    total = len(dff)
    digital_pct = round(100 * dff["flag_digital"].mean(), 1) if "flag_digital" in dff.columns else 0
    edad_prom = round(dff["edad"].mean(), 1) if "edad" in dff.columns else 0
    ingreso_prom = round(dff["ingresos"].mean(), 2) if "ingresos" in dff.columns else 0
    deuda_prom = round(dff["deuda"].mean(), 2) if "deuda" in dff.columns else 0
    top_segmento = dff["segmento"].value_counts().idxmax() if "segmento" in dff.columns else "—"

    return jsonify({
        "total": total,
        "digital_pct": digital_pct,
        "edad_prom": edad_prom,
        "ingreso_prom": ingreso_prom,
        "deuda_prom": deuda_prom,
        "top_segmento": top_segmento
    })

# ============================================================
# API INTEGRAL /api/points_integral — 3 CAPAS
# ✅ AHORA DEVUELVE PROMEDIOS DE OFICINAS PARA EL PANEL
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
    dfA[COL_DIV]  = dfA[COL_DIV].astype(str).str.upper().str.strip()
    dfA[COL_UBIC] = dfA[COL_UBIC].astype(str).str.upper().str.strip()
    dfA[COL_TIPO] = dfA[COL_TIPO].astype(str).str.upper().str.strip()

    if dpto: dfA = dfA[dfA[COL_DEPT] == dpto]
    if prov: dfA = dfA[dfA[COL_PROV] == prov]
    if dist: dfA = dfA[dfA[COL_DIST] == dist]
    if divi: dfA = dfA[dfA[COL_DIV] == divi]

    puntos_atm = []
    suma_atm = float(dfA[PROM_COL].sum())
    for _, r in dfA.iterrows():
        lat = float(r[COL_LAT]); lon = float(r[COL_LON])
        nombre = str(r.get(COL_NAME, r.get(COL_ATM, "")))
        puntos_atm.append({
            "tipo_canal": "ATM",
            "lat": lat, "lon": lon,
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
        })

    # ------------ OFICINAS ------------
    dfO = df_oficinas.copy()
    dfO[COLF_DEPT] = dfO[COLF_DEPT].astype(str).str.upper().str.strip()
    dfO[COLF_PROV] = dfO[COLF_PROV].astype(str).str.upper().str.strip()
    dfO[COLF_DIST] = dfO[COLF_DIST].astype(str).str.upper().str.strip()
    dfO[COLF_DIV]  = dfO[COLF_DIV].astype(str).str.upper().str.strip()

    if dpto: dfO = dfO[dfO[COLF_DEPT] == dpto]
    if prov: dfO = dfO[dfO[COLF_PROV] == prov]
    if dist: dfO = dfO[dfO[COLF_DIST] == dist]
    if divi: dfO = dfO[dfO[COLF_DIV] == divi]

    puntos_of = []
    suma_of = float(dfO[COLF_TRX].sum())

    total_of = int(len(dfO))
    prom_of_eas = float(dfO[COLF_EAS].mean()) if total_of > 0 else 0.0
    prom_of_ebp = float(dfO[COLF_EBP].mean()) if total_of > 0 else 0.0
    prom_of_ead = float(dfO[COLF_EAD].mean()) if total_of > 0 else 0.0
    prom_of_cli = float(dfO[COLF_CLI].mean()) if total_of > 0 else 0.0
    prom_of_tkt = float(dfO[COLF_TKT].mean()) if total_of > 0 else 0.0
    prom_of_red = float(dfO[COLF_RED].mean()) if total_of > 0 else 0.0  # 0..100

    for _, r in dfO.iterrows():
        puntos_of.append({
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
            "estructura_as": float(r.get(COLF_EAS, 0.0)),
            "estructura_ebp": float(r.get(COLF_EBP, 0.0)),
            "estructura_ad": float(r.get(COLF_EAD, 0.0)),
            "clientes_unicos": int(r.get(COLF_CLI, 0)),
            "total_tickets": int(r.get(COLF_TKT, 0)),
            "red_lines": float(r.get(COLF_RED, 0.0)),
        })

    # ------------ AGENTES ------------
    dfG = df_agentes.copy()
    dfG[COLA_DEPT] = dfG[COLA_DEPT].astype(str).str.upper().str.strip()
    dfG[COLA_PROV] = dfG[COLA_PROV].astype(str).str.upper().str.strip()
    dfG[COLA_DIST] = dfG[COLA_DIST].astype(str).str.upper().str.strip()
    dfG[COLA_DIV]  = dfG[COLA_DIV].astype(str).str.upper().str.strip()
    dfG[COLA_CAPA] = dfG[COLA_CAPA].astype(str).str.upper().str.strip()

    if dpto: dfG = dfG[dfG[COLA_DEPT] == dpto]
    if prov: dfG = dfG[dfG[COLA_PROV] == prov]
    if dist: dfG = dfG[dfG[COLA_DIST] == dist]
    if divi: dfG = dfG[dfG[COLA_DIV] == divi]

    puntos_ag = []
    suma_ag = float(dfG[PROMA_COL].sum())
    for _, r in dfG.iterrows():
        puntos_ag.append({
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
        })

    return jsonify({
        "atms": puntos_atm,
        "oficinas": puntos_of,
        "agentes": puntos_ag,
        "suma_atms": suma_atm,
        "suma_oficinas": suma_of,
        "suma_agentes": suma_ag,
        "total_atms": len(puntos_atm),
        "total_oficinas": len(puntos_of),
        "total_agentes": len(puntos_ag),

        "prom_ofi_estructura_as": prom_of_eas,
        "prom_ofi_estructura_ebp": prom_of_ebp,
        "prom_ofi_estructura_ad": prom_of_ead,
        "prom_ofi_clientes_unicos": prom_of_cli,
        "prom_ofi_total_tickets": prom_of_tkt,
        "prom_ofi_redlines": prom_of_red,
    })

# ============================================================
# 8. TEMPLATE MAPA — FRONTEND COMPLETO
# ✅ + PROMEDIOS EN PANEL OFICINAS (OFICINAS + INTEGRAL)
# ✅ + ÍCONOS MÁS GRANDES EN MAPA + LEYENDAS MÁS GRANDES
# ✅ + CHECKBOX ZONAS RURAL/URBANA + BORDES NEÓN (4 CAPAS)
# ✅ + CHECKBOX NODOS + GLOBOS ROJOS GRANDES (4 CAPAS)
# ============================================================
TEMPLATE_MAPA = """\
<!doctype html>
<html>
<head>
  <meta charset="utf-8">
  <title>Mapa BBVA — {% if tipo_mapa == 'islas' %} ATMs {% else %} {{ tipo_mapa|upper }} {% endif %}</title>
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <link rel='stylesheet' href='https://unpkg.com/leaflet@1.9.4/dist/leaflet.css'/>
  <link rel="stylesheet" href="https://unpkg.com/leaflet.markercluster@1.5.3/dist/MarkerCluster.css"/>
  <link rel="stylesheet" href="https://unpkg.com/leaflet.markercluster@1.5.3/dist/MarkerCluster.Default.css"/>
  <style>
    :root{
      --bbva-blue:#1464A5;
      --bbva-dark:#072146;
      --muted:#6b7a8a;
      --card:#ffffff;
      --neon-blue:#1E6CFF;
    }
    html,body{ margin:0; padding:0; height:100%; font-family:Inter,Arial,Helvetica,sans-serif; background:#eef4fb; }
    header{
      background:#003366; color:white; height:70px;
      display:flex; align-items:center; justify-content:center;
      position:relative; box-shadow:0 6px 18px rgba(0,0,0,0.25);
    }
    header h1{ margin:0; font-size:1.9rem; }
    .logout{
      position:absolute; right:20px;
      background:#1464A5; color:white;
      padding:8px 16px; border-radius:8px;
      text-decoration:none; font-weight:600;
    }
    .topbar{ padding:16px 20px 8px 20px; }
    .controls{
      background:white; padding:12px; border-radius:12px;
      box-shadow:0 4px 16px rgba(0,0,0,0.12);
      display:flex; gap:12px; align-items:center; flex-wrap:wrap;
    }
    .controls label{ font-size:13px; color:var(--muted); display:flex; align-items:center; gap:6px; }
    select{ padding:6px 10px; border-radius:8px; border:1px solid #d0d7e3; }
    input[type="checkbox"]{ transform:scale(1.05); }
    .main{ display:flex; padding:0 20px 20px 20px; gap:18px; }
    #map{ flex:1; height:74vh; border-radius:12px; overflow:hidden; box-shadow:0 8px 24px rgba(0,0,0,0.18); }
    .side{ width:360px; display:flex; flex-direction:column; gap:12px; }
    .side-card{ background:white; border-radius:12px; padding:14px 16px; box-shadow:0 6px 22px rgba(0,0,0,0.12); font-size:13px; }
    .side-title{ font-weight:800; margin-bottom:6px; display:flex; align-items:center; gap:8px; }
    .muted{ color:var(--muted); font-size:12px; }
    .brand-card{ padding:10px; }
    .brand-card img{ width:100%; height:120px; object-fit:cover; border-radius:10px; display:block; }
    .legend{ margin-top:10px; }
    .legend .legend-item{ display:flex; align-items:center; gap:12px; margin-top:8px; }
    .legend .legend-item img{
      width:70px; height:70px; object-fit:contain;
      background:#fff; border:1px solid #e6eef8; border-radius:14px;
      padding:6px; box-shadow:0 3px 10px rgba(0,0,0,0.10);
    }
    .legend .legend-item .lbl{ color:var(--muted); font-size:12px; }
    .icon-reco { font-size: 30px; color: #ffcc00; text-shadow: 0 0 4px black; }
    .side-card-atm{
      font-family:"Consolas","Fira Code",monospace;
      white-space:pre-line; line-height:1.35;
      border-left:4px solid var(--bbva-blue);
      position:relative;
    }
    .side-card-atm h3{ margin:0 0 6px 0; font-size:14px; }
    .btn-small{
      display:inline-block; margin-top:8px;
      padding:4px 10px; border-radius:6px;
      border:none; background:var(--bbva-blue);
      color:white; font-size:12px; cursor:pointer;
    }
    @keyframes panelGlow{
      0%{box-shadow:0 0 0 rgba(20,100,165,0.0);}
      50%{box-shadow:0 0 18px rgba(20,100,165,0.55);}
      100%{box-shadow:0 0 0 rgba(20,100,165,0.0);}
    }
    .side-card-atm.glow{ animation:panelGlow 2.2s ease-in-out infinite; }
    .hidden{ display:none; }
    .leaflet-popup-content-wrapper{ border-radius:12px; box-shadow:0 6px 20px rgba(0,0,0,0.25); }

    .division-neon{
      filter: drop-shadow(0 0 10px rgba(30,108,255,0.95))
              drop-shadow(0 0 22px rgba(30,108,255,0.70))
              drop-shadow(0 0 38px rgba(30,108,255,0.40));
    }

    /* ======================================================
       ✅ ZONAS RURAL/URBANA (borde neón)
       ====================================================== */
    .zone-box{
      padding:6px 10px;
      border-radius:12px;
      border:1px solid #d0d7e3;
      background:#f7fbff;
      box-shadow:0 3px 10px rgba(0,0,0,0.06);
      display:flex; align-items:center; gap:10px;
    }
    .zone-swatch{
      width:18px; height:18px;
      border-radius:6px;
      border:1px solid rgba(0,0,0,0.18);
      box-shadow:0 0 10px rgba(255,255,255,0.45);
      flex:0 0 auto;
    }
    .zone-swatch.rural{ background:#00FF66; box-shadow:0 0 12px rgba(0,255,102,0.9); }
    .zone-swatch.urban{ background:#D6FF00; box-shadow:0 0 12px rgba(214,255,0,0.9); }

    .zone-neon-rural{
      filter: drop-shadow(0 0 10px rgba(0,255,102,0.95))
              drop-shadow(0 0 22px rgba(0,255,102,0.70))
              drop-shadow(0 0 38px rgba(0,255,102,0.40));
    }
    .zone-neon-urban{
      filter: drop-shadow(0 0 10px rgba(214,255,0,0.95))
              drop-shadow(0 0 22px rgba(214,255,0,0.70))
              drop-shadow(0 0 38px rgba(214,255,0,0.40));
    }

    /* ======================================================
       ✅ NODOS — Globos rojos grandes con texto blanco + brillo
       ====================================================== */
    .leaflet-div-icon.nodo-icon{ background:transparent; border:none; }
    .nodo-balloon{
      position:relative;
      display:inline-block;
      max-width:280px;
      padding:12px 16px;
      background: radial-gradient(circle at 30% 25%, #ff9a9a 0%, #ff2a2a 35%, #b80000 100%);
      color:#fff;
      font-weight:900;
      font-size:14px;
      line-height:1.15;
      border-radius:20px;
      border:2px solid rgba(255,255,255,0.92);
      text-shadow: 0 1px 2px rgba(0,0,0,0.55);
      box-shadow: 0 0 18px rgba(255,0,0,0.85), 0 0 44px rgba(255,70,0,0.60);
      animation:nodoPulse 1.7s ease-in-out infinite;
    }
    .nodo-balloon:after{
      content:"";
      position:absolute;
      left:50%;
      bottom:-12px;
      transform:translateX(-50%);
      width:0;height:0;
      border-left:12px solid transparent;
      border-right:12px solid transparent;
      border-top:14px solid #ff2a2a;
      filter: drop-shadow(0 0 12px rgba(255,0,0,0.95));
    }
    @keyframes nodoPulse{
      0%{ box-shadow:0 0 14px rgba(255,0,0,0.60), 0 0 34px rgba(255,80,0,0.35); transform:scale(1.00); }
      50%{ box-shadow:0 0 26px rgba(255,0,0,0.98), 0 0 68px rgba(255,80,0,0.78); transform:scale(1.03); }
      100%{ box-shadow:0 0 14px rgba(255,0,0,0.60), 0 0 34px rgba(255,80,0,0.35); transform:scale(1.00); }
    }
  </style>
</head>
<body>
  <header>
    <h1>Mapa BBVA — {% if tipo_mapa == 'islas' %} ATMs {% else %} {{ tipo_mapa|upper }} {% endif %}</h1>
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

      <label>Segmento:
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
      <label style="margin-left:8px;">Canales:
        <span style="display:flex; gap:10px; margin-left:6px;">
          <label style="gap:4px;"><input type="checkbox" id="chkShowATMs" checked> ATMs</label>
          <label style="gap:4px;"><input type="checkbox" id="chkShowOficinas" checked> Oficinas</label>
          <label style="gap:4px;"><input type="checkbox" id="chkShowAgentes" checked> Agentes</label>
        </span>
      </label>
      {% endif %}

      <label style="margin-left:16px;"><input type="checkbox" id="chkHeat" checked> Heatmap</label>
      <label style="margin-left:16px;"><input type="checkbox" id="chkHeatClientes"> Heatmap Clientes</label>
      <label style="margin-left:16px;"><input type="checkbox" id="chkReco"> Recomendaciones</label>

      <!-- ✅ NODOS (globos rojos) -->
      <label style="margin-left:16px;"><input type="checkbox" id="chkNodos" checked> Globos (NODOS)</label>

      <!-- ✅ ZONAS (aplica a las 4 capas) -->
      <div class="zone-box" style="margin-left:16px;">
        <span style="color:var(--muted); font-size:13px; font-weight:700;">Zonas:</span>
        <label style="gap:4px; margin:0;"><input type="checkbox" id="chkZonaRural"> Rural</label>
        <label style="gap:4px; margin:0;"><input type="checkbox" id="chkZonaUrbana"> Urbana</label>
      </div>

      <div style="flex:1"></div>
      <div style="font-size:13px; color:var(--muted);">
        Mostrando <span id="infoCount">--</span> {% if tipo_mapa == 'integral' %} puntos {% else %} registros {% endif %}
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

      <!-- ✅ PANEL ZONAS (siempre visible) -->
      <div id="panelZonasLegend" class="side-card">
        <div class="side-title">🗺️ Zonas (Rural / Urbana)</div>
        <div class="muted">Bordes neón por filtros (Departamento / Provincia / Distrito). Funciona en las 4 capas.</div>

        <div class="legend">
          <div style="font-weight:700;">Leyenda</div>

          <div class="legend-item">
            <div class="zone-swatch rural"></div>
            <div class="lbl">Rural — verde fosforescente (<span id="zonaRuralCount">0</span>)</div>
          </div>

          <div class="legend-item">
            <div class="zone-swatch urban"></div>
            <div class="lbl">Urbana — amarillo fosforescente (<span id="zonaUrbanCount">0</span>)</div>
          </div>
        </div>
      </div>

      <div id="panelATMResumen" class="side-card {% if tipo_mapa != 'integral' and tipo_mapa != 'islas' %}hidden{% endif %}">
        <div class="side-title">🌐 Panel ATMs</div>
        {% if tipo_mapa == 'integral' %}
          <div class="muted">Se actualiza con filtros y solo cuenta si ATMs está activado.</div>
        {% else %}
          <div class="muted">Se actualiza con filtros (solo ATMs).</div>
        {% endif %}
        <div style="margin-top:8px;"><b>Total ATMs:</b> <span id="resAtmTotal">0</span></div>
        <div class="muted" style="margin-top:4px;"><b>Suma TRX:</b> <span id="resAtmSuma">0</span></div>

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
            <img src="{{ url_for('static', filename='atm_oficina1.png') }}" alt="ATM Oficina">
            <div class="lbl">ATM en Oficina</div>
          </div>
          <div class="legend-item">
            <img src="{{ url_for('static', filename='atm_isla1.png') }}" alt="ATM Isla">
            <div class="lbl">ATM en Isla</div>
          </div>
        </div>
      </div>

      <!-- ✅ PANEL OFICINAS -->
      <div id="panelOfiResumen" class="side-card {% if tipo_mapa != 'integral' and tipo_mapa != 'oficinas' %}hidden{% endif %}">
        <div class="side-title">🏦 Panel Oficinas</div>
        {% if tipo_mapa == 'integral' %}
          <div class="muted">Se actualiza con filtros y solo cuenta si Oficinas está activado.</div>
        {% else %}
          <div class="muted">Se actualiza con filtros (solo Oficinas).</div>
        {% endif %}

        <div style="margin-top:8px;"><b>Total Oficinas:</b> <span id="resOfiTotal">0</span></div>
        <div class="muted" style="margin-top:4px;"><b>Suma TRX:</b> <span id="resOfiSuma">0</span></div>

        <div class="muted" style="margin-top:6px;"><b>Prom. ESTRUCTURA AS:</b> <span id="resOfiPromEAS">0</span></div>
        <div class="muted"><b>Prom. ESTRUCTURA EBP:</b> <span id="resOfiPromEBP">0</span></div>
        <div class="muted"><b>Prom. ESTRUCTURA AD:</b> <span id="resOfiPromEAD">0</span></div>
        <div class="muted"><b>Prom. Clientes únicos:</b> <span id="resOfiPromCLI">0</span></div>
        <div class="muted"><b>Prom. Total tickets:</b> <span id="resOfiPromTKT">0</span></div>
        <div class="muted"><b>Prom. Red Lines:</b> <span id="resOfiPromRED">0%</span></div>

        <div class="legend">
          <div style="font-weight:700;">Leyenda</div>
          <div class="legend-item">
            <img src="{{ url_for('static', filename='oficina1.png') }}" alt="Oficina">
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
        <div style="margin-top:8px;"><b>Total Agentes:</b> <span id="resAgTotal">0</span></div>
        <div class="muted" style="margin-top:4px;"><b>Suma TRX:</b> <span id="resAgSuma">0</span></div>

        <div style="margin-top:10px; font-weight:700;">Capas</div>
        <div class="muted">A1: <span id="resAgA1">0</span></div>
        <div class="muted">A2: <span id="resAgA2">0</span></div>
        <div class="muted">A3: <span id="resAgA3">0</span></div>
        <div class="muted">B : <span id="resAgB">0</span></div>
        <div class="muted">C : <span id="resAgC">0</span></div>

        <div class="legend">
          <div style="font-weight:700;">Leyenda</div>
          <div class="legend-item">
            <img src="{{ url_for('static', filename='agente1.png') }}" alt="Agente">
            <div class="lbl">Agente</div>
          </div>
        </div>
      </div>

      <div id="panelClientes" class="side-card hidden">
        <div class="side-title">Clientes visibles</div>
        <div class="muted">Total clientes: <span id="cliTotal">0</span></div>
        <div class="muted">% digitales: <span id="cliDigital">0%</span></div>
        <div class="muted">Edad promedio: <span id="cliEdad">0</span></div>
        <div class="muted">Ingreso promedio: <span id="cliIngreso">0</span></div>
        <div class="muted">Deuda promedio: <span id="cliDeuda">0</span></div>
        <div class="muted">Top segmento: <span id="cliTopSeg">—</span></div>
      </div>

      <div id="panelATM" class="side-card side-card-atm hidden">
        <h3 id="panelATMTitle">Panel del punto seleccionado</h3>
        <div id="atmDetalle" style="font-size:12px;"></div>
        <button id="btnVolver" class="btn-small">VOLVER</button>
      </div>

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

    const TIPO_MAPA = "{{ tipo_mapa }}";
    const INITIAL_CENTER = [{{ initial_center[0] }}, {{ initial_center[1] }}];
    const INITIAL_ZOOM = {{ initial_zoom }};

    const ICON_ATM_OFICINA_URL = "{{ url_for('static', filename='atm_oficina1.png') }}";
    const ICON_ATM_ISLA_URL    = "{{ url_for('static', filename='atm_isla1.png') }}";
    const ICON_OFICINA_URL     = "{{ url_for('static', filename='oficina1.png') }}";
    const ICON_AGENTE_URL      = "{{ url_for('static', filename='agente1.png') }}";

    const ICON_SIZE = 72;
    const ICON_ANCH = ICON_SIZE / 2;
    const POP_ANCH  = -ICON_ANCH;

    const ICON_ATM_OFICINA = L.icon({ iconUrl: ICON_ATM_OFICINA_URL, iconSize:[ICON_SIZE,ICON_SIZE], iconAnchor:[ICON_ANCH,ICON_ANCH], popupAnchor:[0,POP_ANCH] });
    const ICON_ATM_ISLA    = L.icon({ iconUrl: ICON_ATM_ISLA_URL,    iconSize:[ICON_SIZE,ICON_SIZE], iconAnchor:[ICON_ANCH,ICON_ANCH], popupAnchor:[0,POP_ANCH] });
    const ICON_OFICINA     = L.icon({ iconUrl: ICON_OFICINA_URL,     iconSize:[ICON_SIZE,ICON_SIZE], iconAnchor:[ICON_ANCH,ICON_ANCH], popupAnchor:[0,POP_ANCH] });
    const ICON_AGENTE      = L.icon({ iconUrl: ICON_AGENTE_URL,      iconSize:[ICON_SIZE,ICON_SIZE], iconAnchor:[ICON_ANCH,ICON_ANCH], popupAnchor:[0,POP_ANCH] });

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

    const map = L.map('map').setView(INITIAL_CENTER, INITIAL_ZOOM);
    L.tileLayer('https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png',{ maxZoom:19 }).addTo(map);

    // ✅ Pane para zonas (debajo de markers, encima del mapa)
    map.createPane('zonesPane');
    map.getPane('zonesPane').style.zIndex = 380;

    // ✅ Pane para NODOS (globos rojos arriba de todo)
    map.createPane('nodosPane');
    map.getPane('nodosPane').style.zIndex = 760;

    const markers = L.markerClusterGroup({chunkedLoading:true});
    const heat = L.heatLayer([], {radius:28, blur:22});
    const markersReco = L.layerGroup();
    const heatClientes = L.heatLayer([], { radius: 7, blur: 6, maxZoom: 18, minOpacity: 0.04 });

    // ✅ Layer NODOS (globos)
    const nodosLayer = L.layerGroup().addTo(map);

    markers.addTo(map);
    heat.addTo(map);

    const selDep = document.getElementById("selDepartamento");
    const selProv = document.getElementById("selProvincia");
    const selDist = document.getElementById("selDistrito");
    const selDiv = document.getElementById("selDivision");
    const chkHeat = document.getElementById("chkHeat");
    const chkHeatClientes = document.getElementById("chkHeatClientes");
    const panelClientes = document.getElementById("panelClientes");
    const infoBox = document.getElementById("infoCount");
    const selTipoATM = document.getElementById("selTipoATM");
    const selUbicATM = document.getElementById("selUbicacionATM");
    const selSegmento = document.getElementById("selSegmento");
    const chkReco = document.getElementById("chkReco");

    // ✅ checkboxes zonas
    const chkZonaRural  = document.getElementById("chkZonaRural");
    const chkZonaUrbana = document.getElementById("chkZonaUrbana");

    // ✅ checkbox nodos
    const chkNodos = document.getElementById("chkNodos");

    const fmt2 = (v)=> (Number(v||0)).toFixed(2);
    const fmt0 = (v)=> String(Math.round(Number(v||0)));
    const fmtPct = (v)=> `${(Number(v||0)).toFixed(2)}%`;

    // ======================================================
    // ✅ NODOS — Globos rojos (fetch + render)
    // ======================================================
    function escHtml(s){
      return String(s||"").replace(/[&<>"']/g, (c)=>({
        "&":"&amp;","<":"&lt;",">":"&gt;","\\"":"&quot;","'":"&#039;"
      }[c]));
    }

    function nodoIcon(nombre){
      return L.divIcon({
        className: "nodo-icon",
        html: `<div class="nodo-balloon">${escHtml(nombre)}</div>`,
        iconSize: [300, 90],
        iconAnchor: [150, 90],
      });
    }

    async function fetchNodos(){
      try{
        nodosLayer.clearLayers();
        if(!chkNodos || !chkNodos.checked) return;

        const d = selDep.value, p = selProv.value, di = selDist.value;
        const qs = `departamento=${encodeURIComponent(d)}&provincia=${encodeURIComponent(p)}&distrito=${encodeURIComponent(di)}`;

        const res = await fetch(`/api/nodos?${qs}`);
        const js = await res.json();
        const arr = js.nodos || [];

        arr.forEach(n=>{
          const m = L.marker([n.lat, n.lon], {
            pane: "nodosPane",
            icon: nodoIcon(n.nombre),
            zIndexOffset: 6000
          });
          m.bindPopup(`<b>${escHtml(n.nombre)}</b><br>${escHtml(n.departamento)} / ${escHtml(n.provincia)} / ${escHtml(n.distrito)}`);
          nodosLayer.addLayer(m);
        });
      }catch(err){
        console.error("Error cargando NODOS:", err);
      }
    }

    // ======================================================
    // ✅ BORDE NEÓN POR DIVISIÓN (se mantiene)
    // ======================================================
    let divisionBorderLayer = null;
    function clearDivisionBorder(){
      if(divisionBorderLayer){
        try { map.removeLayer(divisionBorderLayer); } catch(e){}
        divisionBorderLayer = null;
      }
    }
    function convexHullLatLng(latlngs){
      if(!latlngs || latlngs.length <= 2) return latlngs || [];
      const uniq = new Map();
      latlngs.forEach(ll=>{
        const k = ll.lat.toFixed(6) + "," + ll.lng.toFixed(6);
        uniq.set(k, ll);
      });
      const pts = Array.from(uniq.values()).map(ll => ({x: ll.lng, y: ll.lat}));
      if(pts.length <= 2) return pts.map(p => L.latLng(p.y, p.x));
      pts.sort((a,b) => (a.x === b.x) ? (a.y - b.y) : (a.x - b.x));
      const cross = (o,a,b) => (a.x - o.x)*(b.y - o.y) - (a.y - o.y)*(b.x - o.x);
      const lower = [];
      for(const p of pts){
        while(lower.length >= 2 && cross(lower[lower.length-2], lower[lower.length-1], p) <= 0) lower.pop();
        lower.push(p);
      }
      const upper = [];
      for(let i=pts.length-1; i>=0; i--){
        const p = pts[i];
        while(upper.length >= 2 && cross(upper[upper.length-2], upper[upper.length-1], p) <= 0) upper.pop();
        upper.push(p);
      }
      upper.pop(); lower.pop();
      const hull = lower.concat(upper);
      return hull.map(p => L.latLng(p.y, p.x));
    }
    function rectFromLatLngs(latlngs){
      const b = L.latLngBounds(latlngs);
      const sw = b.getSouthWest();
      const ne = b.getNorthEast();
      return [ sw, L.latLng(sw.lat, ne.lng), ne, L.latLng(ne.lat, sw.lng) ];
    }
    function drawDivisionBorder(latlngs){
      clearDivisionBorder();
      if(!latlngs || latlngs.length === 0) return;
      const glow = L.polygon(latlngs, {
        color: "#1E6CFF", weight: 18, opacity: 0.22, fill: false,
        lineCap: "round", lineJoin: "round", interactive: false, className: "division-neon"
      });
      const main = L.polygon(latlngs, {
        color: "#1E6CFF", weight: 9, opacity: 0.98, fill: false,
        lineCap: "round", lineJoin: "round", interactive: false, className: "division-neon"
      });
      divisionBorderLayer = L.layerGroup([glow, main]).addTo(map);
      try { glow.bringToFront(); main.bringToFront(); } catch(e){}
    }
    function updateDivisionBorderFromPoints(latlngs){
      const dv = (selDiv && selDiv.value) ? String(selDiv.value).trim() : "";
      if(!dv){ clearDivisionBorder(); return; }
      if(!latlngs || latlngs.length === 0){ clearDivisionBorder(); return; }
      let outline = [];
      if(latlngs.length < 3){
        outline = rectFromLatLngs(latlngs);
      }else{
        outline = convexHullLatLng(latlngs);
        if(!outline || outline.length < 3){
          outline = rectFromLatLngs(latlngs);
        }
      }
      drawDivisionBorder(outline);
    }

    // ======================================================
    // ✅ ZONAS RURAL / URBANA (bordes neón desde backend)
    // ======================================================
    let zonaRuralLayer = null;
    let zonaUrbanLayer = null;

    function clearZonaRural(){
      if(zonaRuralLayer){ try{ map.removeLayer(zonaRuralLayer); }catch(e){} zonaRuralLayer=null; }
    }
    function clearZonaUrban(){
      if(zonaUrbanLayer){ try{ map.removeLayer(zonaUrbanLayer); }catch(e){} zonaUrbanLayer=null; }
    }

    function drawZona(polyLatLng, color, className){
      if(!polyLatLng || polyLatLng.length < 3) return null;

      const glow = L.polygon(polyLatLng, {
        pane: "zonesPane",
        color: color, weight: 18, opacity: 0.22, fill: false,
        lineCap: "round", lineJoin: "round",
        interactive: false,
        className: className
      });

      const main = L.polygon(polyLatLng, {
        pane: "zonesPane",
        color: color, weight: 9, opacity: 0.98, fill: false,
        lineCap: "round", lineJoin: "round",
        interactive: false,
        className: className
      });

      const grp = L.layerGroup([glow, main]).addTo(map);
      try { glow.bringToFront(); main.bringToFront(); } catch(e){}
      return grp;
    }

    async function fetchZonasBorders(){
      const showR = (chkZonaRural && chkZonaRural.checked);
      const showU = (chkZonaUrbana && chkZonaUrbana.checked);

      if(!showR) clearZonaRural();
      if(!showU) clearZonaUrban();

      const ruralCountEl = document.getElementById("zonaRuralCount");
      const urbanCountEl = document.getElementById("zonaUrbanCount");
      if(!showR && ruralCountEl) ruralCountEl.textContent = "0";
      if(!showU && urbanCountEl) urbanCountEl.textContent = "0";

      if(!showR && !showU) return;

      try{
        const d = selDep.value, p = selProv.value, di = selDist.value;
        const qs = `departamento=${encodeURIComponent(d)}&provincia=${encodeURIComponent(p)}&distrito=${encodeURIComponent(di)}`;
        const res = await fetch(`/api/zonas?${qs}`);
        const js = await res.json();

        const rural = js.rural || {};
        const urbano = js.urbano || {};

        if(ruralCountEl) ruralCountEl.textContent = String(rural.count ?? 0);
        if(urbanCountEl) urbanCountEl.textContent = String(urbano.count ?? 0);

        if(showR){
          clearZonaRural();
          zonaRuralLayer = drawZona(rural.poly || [], "#00FF66", "zone-neon-rural");
        }
        if(showU){
          clearZonaUrban();
          zonaUrbanLayer = drawZona(urbano.poly || [], "#D6FF00", "zone-neon-urban");
        }
      }catch(err){
        console.error("Error cargando zonas:", err);
      }
    }

    // ======================================================
    // COMBOS DEP/PROV/DIST/DIV
    // ======================================================
    function updateProvincias(){
      const d = selDep.value;
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
      const p = selProv.value;
      selDist.innerHTML = '<option value="">-- Todos --</option>';
      if(p && DIST_BY_PROV[p]){
        DIST_BY_PROV[p].forEach(d => {
          selDist.innerHTML += `<option value="${d}">${d}</option>`;
        });
      }
      updateDivisiones();
    }
    function updateDivisiones(){
      const d = selDep.value;
      const p = selProv.value;
      const di = selDist.value;
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
      ({{ divisiones|tojson }}).forEach(v => selDiv.innerHTML += `<option value="${v}">${v}</option>`);
    }

    // ======================================================
    // PANEL DETALLE (se mantiene)
    // ======================================================
    const panelATM = document.getElementById("panelATM");
    const atmDetalle = document.getElementById("atmDetalle");
    const btnVolver = document.getElementById("btnVolver");

    const panelReco = document.getElementById("panelReco");
    const recoDetalle = document.getElementById("recoDetalle");
    const btnRecoVolver = document.getElementById("btnRecoVolver");

    const panelATMResumen = document.getElementById("panelATMResumen");
    const panelOfiResumen = document.getElementById("panelOfiResumen");
    const panelAgResumen = document.getElementById("panelAgResumen");

    function hideResumenPanels(){
      if(panelATMResumen) panelATMResumen.classList.add("hidden");
      if(panelOfiResumen) panelOfiResumen.classList.add("hidden");
      if(panelAgResumen) panelAgResumen.classList.add("hidden");
    }

    function syncSinglePanelsVisibility(){
      if(TIPO_MAPA === "integral"){ syncIntegralPanelsVisibility(); return; }
      if(panelATMResumen) panelATMResumen.classList.toggle("hidden", TIPO_MAPA !== "islas");
      if(panelOfiResumen) panelOfiResumen.classList.toggle("hidden", TIPO_MAPA !== "oficinas");
      if(panelAgResumen) panelAgResumen.classList.toggle("hidden", TIPO_MAPA !== "agentes");
    }

    function showResumenPanels(){
      if(TIPO_MAPA === "integral"){ syncIntegralPanelsVisibility(); }
      else { syncSinglePanelsVisibility(); }
    }

    function showRecoPanel(r){
      if (!r) return;
      const txt =
`___________ RECOMENDACIÓN ___________
Canal sugerido: ${String(r.canal||"").toUpperCase()}
Clientes afectados: ${r.clientes_afectados}
Departamento: ${r.departamento}
Provincia: ${r.provincia}
Distrito: ${r.distrito}
Edad promedio: ${Number(r.edad_prom||0).toFixed(1)}
Ingreso promedio: S/ ${Number(r.ingreso_prom||0).toFixed(2)}
% Digitales: ${(Number(r.pct_digital||0) * 100).toFixed(1)}%
Perfil dominante: ${r.perfil_top}
Diagnóstico: ${String(r.diagnostico||"").replace(/\\[|\\]|'/g,"")}
Coordenadas: lat: ${r.lat} lon: ${r.lon}
_____________________________________`;
      recoDetalle.textContent = txt;
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
          texto =
`_____________________ AGENTE ${pt.atm} _____________________
• Comercio: ${pt.nombre}
• Dirección: ${pt.direccion}
• División: ${pt.division}
• Capa: ${pt.capa || ""}
• Tipo: ${pt.tipo}
• Ubicación: ${pt.ubicacion}
• Ubicación Geográfica: ${lineaUbic}
• Trxs Octubre: ${pt.trxs_oct ?? 0}
• Trxs Noviembre: ${pt.trxs_nov ?? 0}
_____________________ Promedio: ${pt.promedio} _____________________`;
        } else if(canal === "OFICINA"){
          texto =
`_____________________ OFICINA ${pt.atm} _____________________
• Nombre: ${pt.nombre}
• Dirección: ${pt.direccion}
• División: ${pt.division}
• Ubicación Geográfica: ${lineaUbic}

——— Métricas de la Oficina ———
• TRX: ${pt.promedio}
• Estructura AS: ${fmt2(pt.estructura_as)}
• Estructura EBP: ${fmt2(pt.estructura_ebp)}
• Estructura AD: ${fmt2(pt.estructura_ad)}
• Clientes únicos: ${fmt0(pt.clientes_unicos)}
• Total tickets: ${fmt0(pt.total_tickets)}
• Red Lines: ${fmtPct(pt.red_lines)}
_________________________________________`;
        } else {
          texto =
`_____________________ ATM ${pt.atm} _____________________
• Nombre: ${pt.nombre}
• Dirección: ${pt.direccion}
• División: ${pt.division}
• Tipo: ${pt.tipo}
• Ubicación: ${pt.ubicacion}
• Ubicación Geográfica: ${lineaUbic}
_____________________ Promedio: ${pt.promedio} _____________________`;
        }
      } else if(TIPO_MAPA === "agentes"){
        texto =
`_____________________ AGENTE ${pt.atm} _____________________
• Comercio: ${pt.nombre}
• Dirección: ${pt.direccion}
• División: ${pt.division}
• Capa: ${pt.capa}
• Tipo: ${pt.tipo}
• Ubicación: ${pt.ubicacion}
• Ubicación Geográfica: ${lineaUbic}
• Trxs Octubre: ${pt.trxs_oct ?? 0}
• Trxs Noviembre: ${pt.trxs_nov ?? 0}
_____________________ Promedio: ${pt.promedio} _____________________`;
      } else if(TIPO_MAPA === "oficinas"){
        texto =
`_____________________ OFICINA ${pt.atm} _____________________
• Nombre: ${pt.nombre}
• Dirección: ${pt.direccion}
• División: ${pt.division}
• Ubicación Geográfica: ${lineaUbic}

——— Métricas de la Oficina ———
• TRX: ${pt.promedio}
• Estructura AS: ${fmt2(pt.estructura_as)}
• Estructura EBP: ${fmt2(pt.estructura_ebp)}
• Estructura AD: ${fmt2(pt.estructura_ad)}
• Clientes únicos: ${fmt0(pt.clientes_unicos)}
• Total tickets: ${fmt0(pt.total_tickets)}
• Red Lines: ${fmtPct(pt.red_lines)}
_________________________________________`;
      } else {
        texto =
`_____________________ ATM ${pt.atm} _____________________
• Nombre: ${pt.nombre}
• Dirección: ${pt.direccion}
• División: ${pt.division}
• Tipo: ${pt.tipo}
• Ubicación: ${pt.ubicacion}
• Ubicación Geográfica: ${lineaUbic}
_____________________ Promedio: ${pt.promedio} _____________________`;
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
      showResumenPanels();
    };

    // ======================================================
    // CLIENTES
    // ======================================================
    async function fetchClientes(){
      try {
        const zoom = map.getZoom();
        const d = selDep.value, p = selProv.value, di = selDist.value, seg = selSegmento.value;
        const qs = `zoom=${zoom}&departamento=${encodeURIComponent(d)}&provincia=${encodeURIComponent(p)}&distrito=${encodeURIComponent(di)}&segmento=${encodeURIComponent(seg)}`;
        const res = await fetch(`/api/clientes?${qs}`);
        const data = await res.json();
        heatClientes.setLatLngs(data.map(c => [c.lat, c.lon, 1]));
        if (!map.hasLayer(heatClientes)) map.addLayer(heatClientes);
      } catch (err){
        console.error("Error cargando clientes:", err);
      }
    }

    async function fetchResumenClientes(){
      const d = selDep.value, p = selProv.value, di = selDist.value, seg = selSegmento.value;
      const qs = `departamento=${encodeURIComponent(d)}&provincia=${encodeURIComponent(p)}&distrito=${encodeURIComponent(di)}&segmento=${encodeURIComponent(seg)}`;
      const res = await fetch(`/api/resumen_clientes?${qs}`);
      const js = await res.json();
      document.getElementById("cliTotal").textContent = js.total;
      document.getElementById("cliDigital").textContent = js.digital_pct + "%";
      document.getElementById("cliEdad").textContent = js.edad_prom;
      document.getElementById("cliIngreso").textContent = js.ingreso_prom;
      document.getElementById("cliDeuda").textContent = js.deuda_prom;
      document.getElementById("cliTopSeg").textContent = js.top_segmento;
    }

    async function cargarRecomendaciones(){
      try {
        const res = await fetch("/api/recomendaciones");
        const data = await res.json();
        markersReco.clearLayers();
        data.forEach(r => {
          const m = L.marker([r.lat, r.lon], {
            icon: L.divIcon({ className: "icon-reco", html: "⚡", iconSize: [36, 36], iconAnchor: [18, 18] }),
            zIndexOffset: 2000
          });
          m.on("click", () => showRecoPanel(r));
          markersReco.addLayer(m);
        });
        if (chkReco.checked){
          markersReco.addTo(map);
        }
      } catch(err){
        console.error("Error cargando recomendaciones:", err);
      }
    }

    // ======================================================
    // CAPAS NORMALES (NO integral)
    // ======================================================
    async function fetchPoints(){
      if(TIPO_MAPA === "integral") return;

      const d = selDep.value, p = selProv.value, di = selDist.value, dv = selDiv.value;
      const t_atm = selTipoATM ? selTipoATM.value : "";
      const u_atm = selUbicATM ? selUbicATM.value : "";

      const qs = `tipo=${TIPO_MAPA}&departamento=${encodeURIComponent(d)}&provincia=${encodeURIComponent(p)}&distrito=${encodeURIComponent(di)}&division=${encodeURIComponent(dv)}&tipo_atm=${encodeURIComponent(t_atm)}&ubic_atm=${encodeURIComponent(u_atm)}`;

      infoBox.textContent = "...";
      panelATM.classList.add("hidden");

      const res = await fetch(`/api/points?${qs}`);
      const data = await res.json();
      const pts = data.puntos || [];

      infoBox.textContent = data.total_atms ?? pts.length;

      markers.clearLayers();
      heat.setLatLngs([]);

      let heatPts = [];
      let bounds = [];

      pts.forEach(pt => {
        const icon = getIcon(pt);
        const m = L.marker([pt.lat, pt.lon], {icon, zIndexOffset: 1200});
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

      updateDivisionBorderFromPoints(bounds.map(b => L.latLng(b[0], b[1])));

      if(TIPO_MAPA === "islas"){
        document.getElementById("resAtmTotal").textContent = data.total_atms || 0;
        document.getElementById("resAtmSuma").textContent = Math.round(data.suma_total || 0);
        document.getElementById("resAtmEnOfi").textContent = data.total_oficinas || 0;
        document.getElementById("resAtmEnIsla").textContent = data.total_islas || 0;
        document.getElementById("resAtmDisp").textContent = data.total_disp || 0;
        document.getElementById("resAtmMon").textContent = data.total_mon || 0;
        document.getElementById("resAtmRec").textContent = data.total_rec || 0;
      }

      if(TIPO_MAPA === "oficinas"){
        document.getElementById("resOfiTotal").textContent = data.total_oficinas || 0;
        document.getElementById("resOfiSuma").textContent = Math.round(data.suma_total || 0);
        document.getElementById("resOfiPromEAS").textContent = fmt2(data.prom_estructura_as);
        document.getElementById("resOfiPromEBP").textContent = fmt2(data.prom_estructura_ebp);
        document.getElementById("resOfiPromEAD").textContent = fmt2(data.prom_estructura_ad);
        document.getElementById("resOfiPromCLI").textContent = fmt0(data.prom_clientes_unicos);
        document.getElementById("resOfiPromTKT").textContent = fmt0(data.prom_total_tickets);
        document.getElementById("resOfiPromRED").textContent = fmtPct(data.prom_redlines);
      }

      if(TIPO_MAPA === "agentes"){
        document.getElementById("resAgTotal").textContent = data.total_agentes || 0;
        document.getElementById("resAgSuma").textContent = Math.round(data.suma_total || 0);
        document.getElementById("resAgA1").textContent = data.total_capa_A1 || 0;
        document.getElementById("resAgA2").textContent = data.total_capa_A2 || 0;
        document.getElementById("resAgA3").textContent = data.total_capa_A3 || 0;
        document.getElementById("resAgB").textContent = data.total_capa_B || 0;
        document.getElementById("resAgC").textContent = data.total_capa_C || 0;
      }

      syncSinglePanelsVisibility();

      if (chkReco.checked){
        cargarRecomendaciones();
        if (!map.hasLayer(markersReco)) markersReco.addTo(map);
      } else {
        if (map.hasLayer(markersReco)) map.removeLayer(markersReco);
      }

      // ✅ ZONAS (si está activado)
      await fetchZonasBorders();

      // ✅ NODOS (globos rojos)
      await fetchNodos();
    }

    // ======================================================
    // INTEGRAL
    // ======================================================
    const chkATMs = document.getElementById("chkShowATMs");
    const chkOficinas = document.getElementById("chkShowOficinas");
    const chkAgentes = document.getElementById("chkShowAgentes");

    function syncIntegralPanelsVisibility(){
      if(TIPO_MAPA !== "integral") return;
      if(panelATMResumen) panelATMResumen.classList.toggle("hidden", !(chkATMs && chkATMs.checked));
      if(panelOfiResumen) panelOfiResumen.classList.toggle("hidden", !(chkOficinas && chkOficinas.checked));
      if(panelAgResumen)  panelAgResumen.classList.toggle("hidden", !(chkAgentes && chkAgentes.checked));
    }

    async function fetchIntegral(){
      if(TIPO_MAPA !== "integral") return;

      const d = selDep.value, p = selProv.value, di = selDist.value, dv = selDiv.value;
      const qs = `departamento=${encodeURIComponent(d)}&provincia=${encodeURIComponent(p)}&distrito=${encodeURIComponent(di)}&division=${encodeURIComponent(dv)}`;

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
          const m = L.marker([pt.lat, pt.lon], {icon, zIndexOffset: 1100});
          m.on("click",()=>showATMPanel(pt));
          markers.addLayer(m);
          heatPts.push([pt.lat, pt.lon, Math.max(1, pt.promedio || 1)]);
          bounds.push([pt.lat, pt.lon]);
        });
      }

      if(showOfi){
        (data.oficinas || []).forEach(pt=>{
          const m = L.marker([pt.lat, pt.lon], {icon:ICON_OFICINA, zIndexOffset: 1400});
          m.on("click",()=>showATMPanel(pt));
          markers.addLayer(m);
          bounds.push([pt.lat, pt.lon]);
        });
      }

      if(showAg){
        (data.agentes || []).forEach(pt=>{
          const m = L.marker([pt.lat, pt.lon], {icon:ICON_AGENTE, zIndexOffset: 1200});
          m.on("click",()=>showATMPanel(pt));
          markers.addLayer(m);
          bounds.push([pt.lat, pt.lon]);
        });
      }

      heat.setLatLngs(heatPts);

      if(bounds.length === 1) map.setView(bounds[0], 16);
      else if(bounds.length > 1) map.fitBounds(bounds, {padding:[20,20]});
      else map.setView(INITIAL_CENTER, INITIAL_ZOOM);

      if(chkHeat.checked){
        if(!map.hasLayer(heat)) heat.addTo(map);
      }else{
        if(map.hasLayer(heat)) map.removeLayer(heat);
      }

      updateDivisionBorderFromPoints(bounds.map(b => L.latLng(b[0], b[1])));

      // --- Panel ATMs ---
      let atm_total = (data.total_atms || 0);
      let atm_suma  = (data.suma_atms || 0);
      let atm_ofi=0, atm_isla=0, atm_disp=0, atm_mon=0, atm_rec=0;
      (data.atms || []).forEach(pt=>{
        const u = (pt.ubicacion || "").toUpperCase();
        const t = (pt.tipo || "").toUpperCase();
        if(u.includes("OFICINA")) atm_ofi++; else atm_isla++;
        if(t.includes("DISPENSADOR")) atm_disp++;
        if(t.includes("MONEDERO")) atm_mon++;
        if(t.includes("RECICLADOR")) atm_rec++;
      });

      document.getElementById("resAtmTotal").textContent = showATMs ? atm_total : 0;
      document.getElementById("resAtmSuma").textContent  = showATMs ? Math.round(atm_suma) : 0;
      document.getElementById("resAtmEnOfi").textContent = showATMs ? atm_ofi : 0;
      document.getElementById("resAtmEnIsla").textContent= showATMs ? atm_isla : 0;
      document.getElementById("resAtmDisp").textContent  = showATMs ? atm_disp : 0;
      document.getElementById("resAtmMon").textContent   = showATMs ? atm_mon : 0;
      document.getElementById("resAtmRec").textContent   = showATMs ? atm_rec : 0;

      // --- Panel Oficinas ---
      const ofi_total = (data.total_oficinas || 0);
      const ofi_suma  = (data.suma_oficinas || 0);

      document.getElementById("resOfiTotal").textContent = showOfi ? ofi_total : 0;
      document.getElementById("resOfiSuma").textContent  = showOfi ? Math.round(ofi_suma) : 0;

      document.getElementById("resOfiPromEAS").textContent = showOfi ? fmt2(data.prom_ofi_estructura_as) : "0.00";
      document.getElementById("resOfiPromEBP").textContent = showOfi ? fmt2(data.prom_ofi_estructura_ebp) : "0.00";
      document.getElementById("resOfiPromEAD").textContent = showOfi ? fmt2(data.prom_ofi_estructura_ad) : "0.00";
      document.getElementById("resOfiPromCLI").textContent = showOfi ? fmt0(data.prom_ofi_clientes_unicos) : "0";
      document.getElementById("resOfiPromTKT").textContent = showOfi ? fmt0(data.prom_ofi_total_tickets) : "0";
      document.getElementById("resOfiPromRED").textContent = showOfi ? fmtPct(data.prom_ofi_redlines) : "0%";

      // --- Panel Agentes ---
      const ag_total = (data.total_agentes || 0);
      const ag_suma  = (data.suma_agentes || 0);

      let a1=0,a2=0,a3=0,b=0,c=0;
      (data.agentes || []).forEach(pt=>{
        const capa = (pt.capa || "").toUpperCase().trim();
        if(capa === "A1") a1++;
        else if(capa === "A2") a2++;
        else if(capa === "A3") a3++;
        else if(capa === "B") b++;
        else if(capa === "C") c++;
      });

      document.getElementById("resAgTotal").textContent = showAg ? ag_total : 0;
      document.getElementById("resAgSuma").textContent  = showAg ? Math.round(ag_suma) : 0;
      document.getElementById("resAgA1").textContent    = showAg ? a1 : 0;
      document.getElementById("resAgA2").textContent    = showAg ? a2 : 0;
      document.getElementById("resAgA3").textContent    = showAg ? a3 : 0;
      document.getElementById("resAgB").textContent     = showAg ? b : 0;
      document.getElementById("resAgC").textContent     = showAg ? c : 0;

      const visibleCount = (showATMs ? atm_total : 0) + (showOfi ? ofi_total : 0) + (showAg ? ag_total : 0);
      infoBox.textContent = visibleCount;

      syncIntegralPanelsVisibility();

      // ✅ ZONAS (si está activado)
      await fetchZonasBorders();

      // ✅ NODOS (globos rojos)
      await fetchNodos();
    }

    // ======================================================
    // EVENTOS
    // ======================================================
    if(TIPO_MAPA === "integral"){
      selDep.onchange = ()=>{ updateProvincias(); fetchIntegral(); if (chkHeatClientes.checked) fetchResumenClientes(); };
      selProv.onchange= ()=>{ updateDistritos(); fetchIntegral(); if (chkHeatClientes.checked) fetchResumenClientes(); };
      selDist.onchange= ()=>{ updateDivisiones(); fetchIntegral(); if (chkHeatClientes.checked) fetchResumenClientes(); };
      selDiv.onchange = ()=> fetchIntegral();
      selSegmento.onchange = ()=>{ if (chkHeatClientes.checked){ fetchClientes(); fetchResumenClientes(); } };

      if(chkATMs) chkATMs.onchange = ()=> fetchIntegral();
      if(chkOficinas) chkOficinas.onchange = ()=> fetchIntegral();
      if(chkAgentes) chkAgentes.onchange = ()=> fetchIntegral();

      chkHeat.onchange = ()=>{
        if (chkHeat.checked){
          chkHeatClientes.checked = false;
          panelClientes.classList.add("hidden");
          heatClientes.setLatLngs([]);
          if (map.hasLayer(heatClientes)) map.removeLayer(heatClientes);
          fetchIntegral();
        } else {
          heat.setLatLngs([]);
          if (map.hasLayer(heat)) map.removeLayer(heat);
          if (chkHeatClientes.checked) fetchClientes();
        }
      };

      chkReco.onchange = ()=>{
        if (chkReco.checked){
          cargarRecomendaciones();
          if(!map.hasLayer(markersReco)) markersReco.addTo(map);
        } else {
          if(map.hasLayer(markersReco)) map.removeLayer(markersReco);
        }
      };

      chkHeatClientes.onchange = ()=>{
        if (chkHeatClientes.checked){
          panelClientes.classList.remove("hidden");
          fetchResumenClientes();
          chkHeat.checked = false;
          heat.setLatLngs([]);
          if (map.hasLayer(heat)) map.removeLayer(heat);
          fetchClientes();
        } else {
          panelClientes.classList.add("hidden");
          heatClientes.setLatLngs([]);
          if (map.hasLayer(heatClientes)) map.removeLayer(heatClientes);
        }
      };

    } else {
      selDep.onchange = ()=>{ updateProvincias(); fetchPoints(); if (chkHeatClientes.checked) fetchResumenClientes(); };
      selProv.onchange= ()=>{ updateDistritos(); fetchPoints(); if (chkHeatClientes.checked) fetchResumenClientes(); };
      selDist.onchange= ()=>{ updateDivisiones(); fetchPoints(); if (chkHeatClientes.checked) fetchResumenClientes(); };
      selDiv.onchange = ()=> fetchPoints();
      selSegmento.onchange = ()=>{ if (chkHeatClientes.checked){ fetchClientes(); fetchResumenClientes(); } };

      if (selTipoATM) selTipoATM.onchange = ()=> fetchPoints();
      if (selUbicATM) selUbicATM.onchange = ()=> fetchPoints();

      chkHeat.onchange = ()=>{
        if (chkHeat.checked){
          chkHeatClientes.checked = false;
          panelClientes.classList.add("hidden");
          heatClientes.setLatLngs([]);
          if (map.hasLayer(heatClientes)) map.removeLayer(heatClientes);
          fetchPoints();
        } else {
          heat.setLatLngs([]);
          if (map.hasLayer(heat)) map.removeLayer(heat);
          if (chkHeatClientes.checked) fetchClientes();
        }
      };

      chkHeatClientes.onchange = ()=>{
        if (chkHeatClientes.checked){
          panelClientes.classList.remove("hidden");
          fetchResumenClientes();
          chkHeat.checked = false;
          heat.setLatLngs([]);
          if (map.hasLayer(heat)) map.removeLayer(heat);
          fetchClientes();
        } else {
          panelClientes.classList.add("hidden");
          heatClientes.setLatLngs([]);
          if (map.hasLayer(heatClientes)) map.removeLayer(heatClientes);
        }
      };

      chkReco.onchange = ()=>{
        if (chkReco.checked){
          cargarRecomendaciones();
          if (!map.hasLayer(markersReco)) markersReco.addTo(map);
        } else {
          if (map.hasLayer(markersReco)) map.removeLayer(markersReco);
        }
      };
    }

    // ✅ Eventos ZONAS (no recarga puntos, solo dibuja/quita bordes)
    if(chkZonaRural)  chkZonaRural.onchange  = ()=> fetchZonasBorders();
    if(chkZonaUrbana) chkZonaUrbana.onchange = ()=> fetchZonasBorders();

    // ✅ Evento NODOS (prender/apagar globos)
    if(chkNodos) chkNodos.onchange = ()=> fetchNodos();

    // Inicializar
    updateProvincias();
    if(TIPO_MAPA === "integral"){
      syncIntegralPanelsVisibility();
      fetchIntegral();
    } else {
      syncSinglePanelsVisibility();
      fetchPoints();
    }

    map.on("zoomend", ()=>{ if (chkHeatClientes.checked) fetchClientes(); });
  </script>
</body>
</html>
"""

if __name__ == "__main__":
    app.run(debug=True)