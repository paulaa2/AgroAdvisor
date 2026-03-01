"""
Preprocessing script - SIN JOINS.
Prepara cada tabla individualmente con claves normalizadas para que
puedan cruzarse despues:

  Clave comun          Tablas que la comparten
  ─────────────────   ───────────────────────────────────────────────
  Area  (pais/region) yield, pesticides, rainfall, temp
  Year  (int)         yield, pesticides, rainfall, temp,
                      commodity_prices, smart_farming, water_footprints
  Item  (cultivo)     yield, crop_recommendation, smart_farming,
                      water_footprints, vegetables (ref)

Cambios aplicados tabla a tabla:
  1. Nombres de columna normalizados a Area / Year / Item.
  2. Nombres de pais unificados al estandar de yield.csv.
  3. Tipos correctos (Year como int, numericos como float).
  4. Columnas indice superfluas eliminadas.
  5. smart_farming: Year extraido de sowing_date; Item mapeado a estandar.
  6. water_footprints: sep=';', pivotado a
     (Year, region_name, item_raw, green_m3_per_ton, blue_m3_per_ton, grey_m3_per_ton).
  7. vegetables: duplicados eliminados, precio numerico,
     nutricion descompuesta en columnas.
"""

import os
import re

import pandas as pd

INPUT_DIR  = "BD"
OUTPUT_DIR = "BD/processed"
os.makedirs(OUTPUT_DIR, exist_ok=True)


# =============================================================
# Mapeos de nombres de pais al estandar de yield.csv
# =============================================================

TEMP_COUNTRY_MAP = {
    "Bolivia":                            "Bolivia (Plurinational State of)",
    "Bosnia And Herzegovina":             "Bosnia and Herzegovina",
    "Congo (Democratic Republic Of The)": "Democratic Republic of the Congo",
    "Czech Republic":                     "Czechia",
    "Cote D'Ivoire":                      "Cote d'Ivoire",
    "Guinea Bissau":                      "Guinea-Bissau",
    "Hong Kong":                          "China, Hong Kong SAR",
    "Iran":                               "Iran (Islamic Republic of)",
    "Laos":                               "Lao People's Democratic Republic",
    "Macedonia":                          "The former Yugoslav Republic of Macedonia",
    "Moldova":                            "Republic of Moldova",
    "Russia":                             "Russian Federation",
    "South Korea":                        "Republic of Korea",
    "Syria":                              "Syrian Arab Republic",
    "Taiwan":                             "China, Taiwan Province of",
    "Tanzania":                           "United Republic of Tanzania",
    "United States":                      "United States of America",
    "Venezuela":                          "Venezuela (Bolivarian Republic of)",
    "Vietnam":                            "Viet Nam",
}

RAINFALL_AREA_MAP = {
    "Bolivia":                        "Bolivia (Plurinational State of)",
    "Congo, Dem. Rep.":               "Democratic Republic of the Congo",
    "Congo, Rep.":                    "Congo",
    "Cote d'Ivoire":                  "Cote d'Ivoire",
    "Czech Republic":                 "Czechia",
    "Hong Kong SAR, China":           "China, Hong Kong SAR",
    "Iran":                           "Iran (Islamic Republic of)",
    "Kyrgyz Republic":                "Kyrgyzstan",
    "Lao PDR":                        "Lao People's Democratic Republic",
    "Macao SAR, China":               "China, Macao SAR",
    "Macedonia":                      "The former Yugoslav Republic of Macedonia",
    "Moldova":                        "Republic of Moldova",
    "North Korea":                    "Democratic People's Republic of Korea",
    "Russia":                         "Russian Federation",
    "Slovak Republic":                "Slovakia",
    "South Korea ":                   "Republic of Korea",
    "South Korea":                    "Republic of Korea",
    "St. Kitts and Nevis":            "Saint Kitts and Nevis",
    "St. Lucia":                      "Saint Lucia",
    "St. Vincent and the Grenadines": "Saint Vincent and the Grenadines",
    "Syria":                          "Syrian Arab Republic",
    "Tanzania":                       "United Republic of Tanzania",
    "United States":                  "United States of America",
    "Venezuela, RB":                  "Venezuela (Bolivarian Republic of)",
    "Vietnam":                        "Viet Nam",
}

# Mapeo crop label/type  ->  Item estandar de yield.csv
CROP_LABEL_TO_ITEM = {
    # Crop_recommendation.csv (minusculas)
    "rice":     "Rice, paddy",
    "maize":    "Maize",
    # Smart_Farming_Crop_Yield_2024.csv (Title Case)
    "Rice":     "Rice, paddy",
    "Maize":    "Maize",
    "Wheat":    "Wheat",
    "Soybean":  "Soybeans",
    "Cotton":   "Seed cotton",
}


# ----------------------------------------------------------
# Utilidad: carga condicional (salta si no existe el fichero)
# ----------------------------------------------------------
def _load(filename, **kwargs):
    path = os.path.join(INPUT_DIR, filename)
    if not os.path.exists(path):
        print(f"   [SKIP] {filename} no encontrado en {INPUT_DIR}/")
        return None
    return pd.read_csv(path, **kwargs)


# ========================================================
# 1. YIELD  -- claves: Area, Item, Year
# ========================================================
print("1. Procesando yield.csv ...")
yld = _load("yield.csv")
if yld is not None:
    yld = yld[["Area", "Item", "Year", "Value"]].copy()
    yld.rename(columns={"Value": "hg_ha_yield"}, inplace=True)
    yld["Year"] = yld["Year"].astype(int)
    yld.to_csv(f"{OUTPUT_DIR}/yield.csv", index=False)
    print(f"   {len(yld):,} filas | {yld['Area'].nunique()} paises"
          f" | {yld['Item'].nunique()} cultivos"
          f" | anos {yld['Year'].min()}-{yld['Year'].max()}")
    print(f"   JOIN keys: Area, Item, Year")


# ========================================================
# 2. PESTICIDES  -- claves: Area, Year
# ========================================================
print("2. Procesando pesticides.csv ...")
pest = _load("pesticides.csv")
if pest is not None:
    pest = pest[["Area", "Year", "Value"]].copy()
    pest.rename(columns={"Value": "pesticides_tonnes"}, inplace=True)
    pest["Year"] = pest["Year"].astype(int)
    pest.to_csv(f"{OUTPUT_DIR}/pesticides.csv", index=False)
    print(f"   {len(pest):,} filas | {pest['Area'].nunique()} paises"
          f" | anos {pest['Year'].min()}-{pest['Year'].max()}")
    print(f"   JOIN keys: Area, Year")


# ========================================================
# 3. RAINFALL  -- claves: Area, Year
# ========================================================
print("3. Procesando rainfall.csv ...")
rain = _load("rainfall.csv")
if rain is not None:
    rain.columns = [c.strip() for c in rain.columns]
    rain["Area"] = rain["Area"].str.strip().replace(RAINFALL_AREA_MAP)
    rain["Year"] = rain["Year"].astype(int)
    rain.to_csv(f"{OUTPUT_DIR}/rainfall.csv", index=False)
    print(f"   {len(rain):,} filas | {rain['Area'].nunique()} paises"
          f" | anos {rain['Year'].min()}-{rain['Year'].max()}")
    print(f"   JOIN keys: Area, Year")


# ========================================================
# 4. TEMP  -- claves: Area, Year
# ========================================================
print("4. Procesando temp.csv ...")
temp = _load("temp.csv")
if temp is not None:
    temp.rename(columns={"country": "Area", "year": "Year"}, inplace=True)
    temp["Area"] = temp["Area"].str.strip().replace(TEMP_COUNTRY_MAP)
    temp["Year"] = temp["Year"].astype(int)
    temp.to_csv(f"{OUTPUT_DIR}/temp.csv", index=False)
    print(f"   {len(temp):,} filas | {temp['Area'].nunique()} paises"
          f" | anos {temp['Year'].min()}-{temp['Year'].max()}")
    print(f"   JOIN keys: Area, Year")


# ========================================================
# 5. COMMODITY PRICES  -- clave: Year
#    Dos salidas: mensual (con date) y anual (media por Year)
# ========================================================
print("5. Procesando commodity_prices.csv ...")
cp = _load("commodity_prices.csv")
if cp is not None:
    if "Unnamed: 0" in cp.columns:
        cp.drop(columns=["Unnamed: 0"], inplace=True)
    cp["date"] = pd.to_datetime(cp["date"])
    cp["Year"] = cp["date"].dt.year.astype(int)
    cp_yearly = (
        cp.drop(columns=["date"])
        .groupby("Year")
        .mean(numeric_only=True)
        .reset_index()
    )
    cp.to_csv(f"{OUTPUT_DIR}/commodity_prices_monthly.csv", index=False)
    cp_yearly.to_csv(f"{OUTPUT_DIR}/commodity_prices.csv", index=False)
    print(f"   {len(cp):,} filas mensuales -> {len(cp_yearly)} anuales"
          f" | anos {cp_yearly['Year'].min()}-{cp_yearly['Year'].max()}")
    print(f"   JOIN keys: Year")


# ========================================================
# 6. CROP RECOMMENDATION  -- clave: Item
# ========================================================
print("6. Procesando Crop_recommendation.csv ...")
crop = _load("Crop_recommendation.csv")
if crop is not None:
    crop["Item"] = crop["label"].map(CROP_LABEL_TO_ITEM)
    crop.to_csv(f"{OUTPUT_DIR}/crop_recommendation.csv", index=False)
    mapped = crop["Item"].notna().sum()
    print(f"   {len(crop):,} filas | {crop['label'].nunique()} cultivos"
          f" | Item mapeado: {mapped} filas")
    print(f"   JOIN keys: Item")


# ========================================================
# 7. YIELD_DF  -- claves: Area, Item, Year
# ========================================================
print("7. Procesando yield_df.csv ...")
ydf = _load("yield_df.csv")
if ydf is not None:
    if "Unnamed: 0" in ydf.columns:
        ydf.drop(columns=["Unnamed: 0"], inplace=True)
    ydf["Year"] = ydf["Year"].astype(int)
    ydf.to_csv(f"{OUTPUT_DIR}/yield_df.csv", index=False)
    print(f"   {len(ydf):,} filas | {ydf['Area'].nunique()} paises"
          f" | anos {ydf['Year'].min()}-{ydf['Year'].max()}")
    print(f"   JOIN keys: Area, Item, Year")


# ========================================================
# 8. SMART FARMING 2024  -- claves: Item, Year
#    crop_type  -> Item  (estandar yield.csv via CROP_LABEL_TO_ITEM)
#    sowing_date -> Year (int)
# ========================================================
print("8. Procesando Smart_Farming_Crop_Yield_2024.csv ...")
sf = _load("Smart_Farming_Crop_Yield_2024.csv")
if sf is not None:
    sf["Item"] = sf["crop_type"].map(CROP_LABEL_TO_ITEM)
    sf["Year"] = pd.to_datetime(sf["sowing_date"]).dt.year.astype(int)
    sf["sowing_date"]  = pd.to_datetime(sf["sowing_date"])
    sf["harvest_date"] = pd.to_datetime(sf["harvest_date"])
    sf.to_csv(f"{OUTPUT_DIR}/smart_farming.csv", index=False)
    mapped_sf = sf["Item"].notna().sum()
    print(f"   {len(sf):,} filas | {sf['crop_type'].nunique()} cultivos"
          f" | Item mapeado: {mapped_sf} filas | ano(s): {sorted(sf['Year'].unique())}")
    print(f"   JOIN keys: Item, Year  (region != Area estandar)")


# ========================================================
# 9. WATER FOOTPRINTS  -- claves: Year, item_raw
#    Delimitado por ';'. Pivotado: una fila por
#    (Year, region_name, region_iso, item_raw)
#    con columnas green_m3_per_ton, blue_m3_per_ton, grey_m3_per_ton.
# ========================================================
print("9. Procesando water-footprints-of-crops-and-derived-crop-products.csv ...")
wf = _load(
    "water-footprints-of-crops-and-derived-crop-products.csv",
    sep=";",
    encoding="utf-8-sig",
)
if wf is not None:
    wf.rename(columns={
        "DATE":                      "Year",
        "INDICATOR_NAME":            "item_raw",
        "REGION_NAME":               "region_name",
        "REGION_REGIONID":           "region_iso",
        "VALUE":                     "value_m3_per_ton",
        "WATER_FOOTPRINT_TYPE_NAME": "wf_type",
    }, inplace=True)
    wf["Year"] = wf["Year"].astype(int)
    wf["wf_type"] = wf["wf_type"].str.strip().str.lower()

    wf_pivot = (
        wf[["Year", "region_name", "region_iso", "item_raw",
            "wf_type", "value_m3_per_ton"]]
        .pivot_table(
            index=["Year", "region_name", "region_iso", "item_raw"],
            columns="wf_type",
            values="value_m3_per_ton",
            aggfunc="mean",
        )
        .reset_index()
    )
    wf_pivot.columns.name = None
    wf_pivot.rename(
        columns={c: f"{c}_m3_per_ton"
                 for c in wf_pivot.columns
                 if c not in ["Year", "region_name", "region_iso", "item_raw"]},
        inplace=True,
    )
    wf_pivot.to_csv(f"{OUTPUT_DIR}/water_footprints.csv", index=False)
    print(f"   {len(wf):,} filas raw -> {len(wf_pivot):,} pivotadas"
          f" | anos {wf_pivot['Year'].min()}-{wf_pivot['Year'].max()}")
    print(f"   JOIN keys: Year, item_raw  (cruzar con Item via mapeo manual)")


# ========================================================
# 10. VEGETABLES  -- clave de referencia: name
#     Sin join keys temporales; es tabla de referencia de cultivos.
# ========================================================
print("10. Procesando vegetables Dataset.csv ...")
veg_raw = _load("vegetables Dataset.csv")
if veg_raw is not None:
    veg = veg_raw.copy()

    before = len(veg)
    veg = veg.drop_duplicates(subset=["Name"], keep="first").copy()
    print(f"   Duplicados eliminados: {before - len(veg)}")

    veg.drop(columns=["Vegetable ID"], inplace=True)
    veg.insert(0, "vegetable_id", range(1, len(veg) + 1))

    veg["price_per_kg"] = (
        veg["Price (per kg)"]
        .astype(str)
        .str.replace("$", "", regex=False)
        .str.strip()
        .astype(float)
    )
    veg.drop(columns=["Price (per kg)"], inplace=True)

    def _parse_nutrition(val):
        kcal = protein = fiber = None
        m = re.search(r"([\d.]+)\s*kcal", str(val))
        if m:
            kcal = float(m.group(1))
        m = re.search(r"([\d.]+)g\s*protein", str(val))
        if m:
            protein = float(m.group(1))
        m = re.search(r"([\d.]+)g\s*fiber", str(val))
        if m:
            fiber = float(m.group(1))
        return kcal, protein, fiber

    veg[["kcal_per_100g", "protein_g_per_100g", "fiber_g_per_100g"]] = pd.DataFrame(
        veg["Nutritional Value (per 100g)"].apply(_parse_nutrition).tolist(),
        index=veg.index,
    )
    veg.drop(columns=["Nutritional Value (per 100g)"], inplace=True)

    veg.columns = (
        veg.columns
        .str.strip()
        .str.lower()
        .str.replace(r"[\s/\(\)]+", "_", regex=True)
        .str.replace(r"_+", "_", regex=True)
        .str.strip("_")
    )
    veg = veg.sort_values("vegetable_id").reset_index(drop=True)
    veg.to_csv(f"{OUTPUT_DIR}/vegetables.csv", index=False)
    print(f"   {len(veg)} vegetales | columnas: {list(veg.columns)}")
    print(f"   JOIN keys: name  (cruzar con Item de otras tablas via mapeo manual)")


# ========================================================
# RESUMEN FINAL
# ========================================================
KEY_DOCS = {
    "yield.csv":                     "Area, Item, Year",
    "pesticides.csv":                "Area, Year",
    "rainfall.csv":                  "Area, Year",
    "temp.csv":                      "Area, Year",
    "commodity_prices.csv":          "Year",
    "commodity_prices_monthly.csv":  "Year (+ date)",
    "crop_recommendation.csv":       "Item",
    "yield_df.csv":                  "Area, Item, Year",
    "smart_farming.csv":             "Item, Year",
    "water_footprints.csv":          "Year, item_raw",
    "vegetables.csv":                "name",
    "market_researcher_dataset.csv": "(external)",
}
print("\n" + "=" * 65)
print(f"TABLAS GUARDADAS EN {OUTPUT_DIR}")
print("=" * 65)
print(f"  {'Archivo':<44} {'KB':>6}   JOIN keys")
print(f"  {'-'*44} {'-'*6}   {'-'*22}")
for fname in sorted(os.listdir(OUTPUT_DIR)):
    fpath = os.path.join(OUTPUT_DIR, fname)
    size_kb = os.path.getsize(fpath) / 1024
    keys = KEY_DOCS.get(fname, "")
    print(f"  {fname:<44} {size_kb:>6.1f}   {keys}")
