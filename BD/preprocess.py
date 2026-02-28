"""
Preprocessing script: normaliza todas las tablas de BD/ para que sean
cruzables con JOIN sobre claves comunes (Area, Year, Item).

Cambios que aplica:
  1. Normaliza nombres de columna: Area, Year en todas las tablas.
  2. Unifica nombres de país/región al estándar de yield.csv.
  3. Extrae Year de la fecha en commodity_prices.
  4. Mapea label → Item en Crop_recommendation.
  5. Limpia columnas innecesarias y renombra valores.
  6. Guarda versiones procesadas en BD/processed/.
"""

import pandas as pd
import os

INPUT_DIR = "BD"
OUTPUT_DIR = "BD/processed"
os.makedirs(OUTPUT_DIR, exist_ok=True)

# =============================================================
# Mapeos de nombres de país hacia el estándar de yield.csv
# =============================================================

# temp.csv  →  yield.csv
TEMP_COUNTRY_MAP = {
    "Bolivia":                              "Bolivia (Plurinational State of)",
    "Bosnia And Herzegovina":               "Bosnia and Herzegovina",
    "Congo (Democratic Republic Of The)":   "Democratic Republic of the Congo",
    "Czech Republic":                       "Czechia",
    "Côte D'Ivoire":                        "Côte d'Ivoire",
    "Guinea Bissau":                        "Guinea-Bissau",
    "Hong Kong":                            "China, Hong Kong SAR",
    "Iran":                                 "Iran (Islamic Republic of)",
    "Laos":                                 "Lao People's Democratic Republic",
    "Macedonia":                            "The former Yugoslav Republic of Macedonia",
    "Moldova":                              "Republic of Moldova",
    "Russia":                               "Russian Federation",
    "South Korea":                          "Republic of Korea",
    "Syria":                                "Syrian Arab Republic",
    "Taiwan":                               "China, Taiwan Province of",
    "Tanzania":                             "United Republic of Tanzania",
    "United States":                        "United States of America",
    "Venezuela":                            "Venezuela (Bolivarian Republic of)",
    "Vietnam":                              "Viet Nam",
}

# rainfall.csv  →  yield.csv
RAINFALL_AREA_MAP = {
    "Bolivia":                  "Bolivia (Plurinational State of)",
    "Congo, Dem. Rep.":         "Democratic Republic of the Congo",
    "Congo, Rep.":              "Congo",
    "Cote d'Ivoire":            "Côte d'Ivoire",
    "Czech Republic":           "Czechia",
    "Hong Kong SAR, China":     "China, Hong Kong SAR",
    "Iran":                     "Iran (Islamic Republic of)",
    "Kyrgyz Republic":          "Kyrgyzstan",
    "Lao PDR":                  "Lao People's Democratic Republic",
    "Macao SAR, China":         "China, Macao SAR",
    "Macedonia":                "The former Yugoslav Republic of Macedonia",
    "Moldova":                  "Republic of Moldova",
    "North Korea":              "Democratic People's Republic of Korea",
    "Russia":                   "Russian Federation",
    "Slovak Republic":          "Slovakia",
    "South Korea ":             "Republic of Korea",   # trailing space in original
    "South Korea":              "Republic of Korea",
    "St. Kitts and Nevis":      "Saint Kitts and Nevis",
    "St. Lucia":                "Saint Lucia",
    "St. Vincent and the Grenadines": "Saint Vincent and the Grenadines",
    "Syria":                    "Syrian Arab Republic",
    "Tanzania":                 "United Republic of Tanzania",
    "United States":            "United States of America",
    "Venezuela, RB":            "Venezuela (Bolivarian Republic of)",
    "Vietnam":                  "Viet Nam",
}

# Crop_recommendation label → yield.csv Item
CROP_LABEL_TO_ITEM = {
    "rice":    "Rice, paddy",
    "maize":   "Maize",
}


# ========================================================
# 1. YIELD  (tabla principal de referencia)
# ========================================================
print("1. Procesando yield.csv ...")
yld = pd.read_csv(f"{INPUT_DIR}/yield.csv")

# Quedarnos solo con columnas útiles y renombrar Value
yld = yld[["Area", "Item", "Year", "Value"]].copy()
yld.rename(columns={"Value": "hg_ha_yield"}, inplace=True)

print(f"   {len(yld)} filas  |  {yld['Area'].nunique()} países  |  "
      f"{yld['Item'].nunique()} cultivos  |  "
      f"Años {yld['Year'].min()}-{yld['Year'].max()}")
yld.to_csv(f"{OUTPUT_DIR}/yield.csv", index=False)


# ========================================================
# 2. PESTICIDES
# ========================================================
print("2. Procesando pesticides.csv ...")
pest = pd.read_csv(f"{INPUT_DIR}/pesticides.csv")

# Quedarnos con Area, Year, Value; renombrar Value
pest = pest[["Area", "Year", "Value"]].copy()
pest.rename(columns={"Value": "pesticides_tonnes"}, inplace=True)

print(f"   {len(pest)} filas  |  {pest['Area'].nunique()} países  |  "
      f"Años {pest['Year'].min()}-{pest['Year'].max()}")
pest.to_csv(f"{OUTPUT_DIR}/pesticides.csv", index=False)


# ========================================================
# 3. RAINFALL
# ========================================================
print("3. Procesando rainfall.csv ...")
rain = pd.read_csv(f"{INPUT_DIR}/rainfall.csv")

# Corregir espacio en nombre de columna
rain.columns = [c.strip() for c in rain.columns]

# Normalizar nombres de país
rain["Area"] = rain["Area"].str.strip().replace(RAINFALL_AREA_MAP)

print(f"   {len(rain)} filas  |  {rain['Area'].nunique()} países  |  "
      f"Años {rain['Year'].min()}-{rain['Year'].max()}")
rain.to_csv(f"{OUTPUT_DIR}/rainfall.csv", index=False)


# ========================================================
# 4. TEMP
# ========================================================
print("4. Procesando temp.csv ...")
temp = pd.read_csv(f"{INPUT_DIR}/temp.csv")

# Renombrar columnas para consistencia
temp.rename(columns={"country": "Area", "year": "Year"}, inplace=True)

# Normalizar nombres de país
temp["Area"] = temp["Area"].str.strip().replace(TEMP_COUNTRY_MAP)

print(f"   {len(temp)} filas  |  {temp['Area'].nunique()} países  |  "
      f"Años {int(temp['Year'].min())}-{int(temp['Year'].max())}")
temp.to_csv(f"{OUTPUT_DIR}/temp.csv", index=False)


# ========================================================
# 5. COMMODITY PRICES
# ========================================================
print("5. Procesando commodity_prices.csv ...")
cp = pd.read_csv(f"{INPUT_DIR}/commodity_prices.csv")

# Eliminar columna índice innecesaria
if "Unnamed: 0" in cp.columns:
    cp.drop(columns=["Unnamed: 0"], inplace=True)

# Extraer Year para poder hacer join por año
cp["date"] = pd.to_datetime(cp["date"])
cp["Year"] = cp["date"].dt.year

# Crear versión anualizada (media de cada commodity por año)
cp_yearly = cp.drop(columns=["date"]).groupby("Year").mean().reset_index()

print(f"   {len(cp)} filas mensuales → {len(cp_yearly)} filas anuales  |  "
      f"Años {cp_yearly['Year'].min()}-{cp_yearly['Year'].max()}")
cp.to_csv(f"{OUTPUT_DIR}/commodity_prices_monthly.csv", index=False)
cp_yearly.to_csv(f"{OUTPUT_DIR}/commodity_prices.csv", index=False)


# ========================================================
# 6. CROP RECOMMENDATION
# ========================================================
print("6. Procesando Crop_recommendation.csv ...")
crop = pd.read_csv(f"{INPUT_DIR}/Crop_recommendation.csv")

# Añadir columna Item mapeada al estándar de yield
crop["Item"] = crop["label"].map(CROP_LABEL_TO_ITEM)

print(f"   {len(crop)} filas  |  {crop['label'].nunique()} cultivos  |  "
      f"Mapeados a yield: {crop['Item'].notna().sum()} filas "
      f"({sorted(CROP_LABEL_TO_ITEM.keys())})")
crop.to_csv(f"{OUTPUT_DIR}/crop_recommendation.csv", index=False)


# ========================================================
# 7. YIELD_DF  (ya pre-unido — solo limpieza)
# ========================================================
print("7. Procesando yield_df.csv ...")
ydf = pd.read_csv(f"{INPUT_DIR}/yield_df.csv")

# Eliminar columna índice innecesaria
if "Unnamed: 0" in ydf.columns:
    ydf.drop(columns=["Unnamed: 0"], inplace=True)

print(f"   {len(ydf)} filas  |  {ydf['Area'].nunique()} países  |  "
      f"Años {ydf['Year'].min()}-{ydf['Year'].max()}")
ydf.to_csv(f"{OUTPUT_DIR}/yield_df.csv", index=False)


# ========================================================
# 8. VERIFICACIÓN DE JOINS
# ========================================================
print("\n" + "=" * 60)
print("VERIFICACIÓN DE JOINS")
print("=" * 60)

# Join yield + pesticides on (Area, Year)
merged = yld.merge(pest, on=["Area", "Year"], how="inner")
print(f"yield ⟕ pesticides       (Area, Year)     → {len(merged):>6} filas")

# Join yield + rainfall on (Area, Year)
merged = yld.merge(rain, on=["Area", "Year"], how="inner")
print(f"yield ⟕ rainfall         (Area, Year)     → {len(merged):>6} filas")

# Join yield + temp on (Area, Year)
merged = yld.merge(temp, on=["Area", "Year"], how="inner")
print(f"yield ⟕ temp             (Area, Year)     → {len(merged):>6} filas")

# Join yield + commodity_prices on (Year)
merged = yld.merge(cp_yearly, on=["Year"], how="inner")
print(f"yield ⟕ commodity_prices (Year)           → {len(merged):>6} filas")

# Join yield + crop_recommendation on (Item)
merged = yld.merge(crop.dropna(subset=["Item"]), on=["Item"], how="inner")
print(f"yield ⟕ crop_recommend.  (Item)           → {len(merged):>6} filas")

# Full master join
master = (
    yld
    .merge(pest, on=["Area", "Year"], how="left")
    .merge(rain, on=["Area", "Year"], how="left")
    .merge(temp, on=["Area", "Year"], how="left")
    .merge(cp_yearly, on=["Year"], how="left")
)
print(f"\nMaster join (left) completo:               → {len(master):>6} filas")
print(f"  Con pesticidas: {master['pesticides_tonnes'].notna().sum()}")
print(f"  Con lluvia:     {master['average_rain_fall_mm_per_year'].notna().sum()}")
print(f"  Con temperatura:{master['avg_temp'].notna().sum()}")
print(f"  Con commodity:  {master['oil_brent'].notna().sum()}")
master.to_csv(f"{OUTPUT_DIR}/master.csv", index=False)

print("\n" + "=" * 60)
print(f"Archivos guardados en {OUTPUT_DIR}/")
print("=" * 60)
for f in sorted(os.listdir(OUTPUT_DIR)):
    sz = os.path.getsize(f"{OUTPUT_DIR}/{f}")
    print(f"  {f:<40} {sz/1024:>8.1f} KB")
