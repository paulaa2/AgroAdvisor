"""
AgroAdvisor – Configuration & constants
All environment-dependent values and shared constants live here.
"""

import os
from pathlib import Path

# ─── Load sdk_config.env into os.environ (so getenv picks up Denodo SDK keys) ─
_SDK_ENV = Path(__file__).parent.parent / "config" / "sdk_config.env"
if _SDK_ENV.exists():
    for _line in _SDK_ENV.read_text(encoding="utf-8").splitlines():
        _line = _line.strip()
        if not _line or _line.startswith("#") or "=" not in _line:
            continue
        _k, _, _v = _line.partition("=")
        _k = _k.strip()
        _v = _v.strip().strip('"').strip("'")
        if _k and _k not in os.environ:
            os.environ[_k] = _v

# ─── Auth & connection ──────────────────────────────────────────────────────
AI_SDK_BASE_URL: str = os.getenv("AI_SDK_BASE_URL", "http://localhost:8008")
DENODO_USER: str     = os.getenv("DENODO_USER", "admin")
DENODO_PASS: str     = os.getenv("DENODO_PASS", "admin")
AUTH: tuple[str, str] = (DENODO_USER, DENODO_PASS)

# ─── Thinking LLM — called directly by think_interpret() via Ollama API ───────
THINKING_MODEL: str  = os.getenv("THINKING_LLM_MODEL", "llama3")
OLLAMA_BASE_URL: str = os.getenv("OLLAMA_HOST_URL", "http://localhost:11434")

VDP_DATABASE: str = "denodo"

REQUIRED_VIEWS: list[str] = [
    "yield",
    "crop",
    "price_j_yield",
    "yield_j_crop",
]

GET_METADATA_URL:    str = f"{AI_SDK_BASE_URL}/getMetadata"
VECTOR_DB_INFO_URL:  str = f"{AI_SDK_BASE_URL}/getVectorDBInfo"
ANSWER_QUESTION_URL: str = f"{AI_SDK_BASE_URL}/answerQuestion"        # auto-mode
DATA_URL:            str = f"{AI_SDK_BASE_URL}/answerDataQuestion"    # explicit SQL
METADATA_URL:        str = f"{AI_SDK_BASE_URL}/answerMetadataQuestion" # schema / VectorDB
DEEP_QUERY_URL:      str = f"{AI_SDK_BASE_URL}/deepQuery"

TIMEOUT_DATA:     float = 240
TIMEOUT_METADATA: float = 120
TIMEOUT_VECTOR:   float = 60
TIMEOUT_DEEP:     float = 900

AREA_TRANSLATIONS: dict[str, str] = {
    "brasil":          "Brazil",
    "españa":          "Spain",
    "alemania":        "Germany",
    "francia":         "France",
    "estados unidos":  "United States of America",
    "reino unido":     "United Kingdom",
    "países bajos":    "Netherlands",
    "japón":           "Japan",
    "méxico":          "Mexico",
    "perú":            "Peru",
    "italia":          "Italy",
    "rusia":           "Russian Federation",
    "turquía":         "Turkey",
    "egipto":          "Egypt",
    "corea del sur":   "Republic of Korea",
    "sudáfrica":       "South Africa",
    "nueva zelanda":   "New Zealand",
    "china":           "China",
    "india":           "India",
    "argentina":       "Argentina",
    "colombia":        "Colombia",
    "australia":       "Australia",
    "canadá":          "Canada",
    "polonia":         "Poland",
    "ucrania":         "Ukraine",
}

REPORT_LABELS: dict[str, str] = {
    "crop_advisor":        "Asesor de Cultivos",
    "pesticide_analysis":  "Análisis de Pesticidas",
    "climate_impact":      "Impacto Climático",
    "market_intelligence": "Inteligencia de Mercado",
    "regional_report":     "Informe Regional",
}

# ─── Table catalogue for Phase-0 ranking ─────────────────────────────────────
# Each entry describes one queryable table/view.
# "denodo": True  → can be queried via answerDataQuestion (VDP views)
# "denodo": False → local CSV / reference data, used only for context
TABLE_CATALOGUE: dict[str, dict] = {
    "yield": {
        "description": "Historical crop yield by country and year. Main table.",
        "columns": "area, item, year, hg_ha_yield, average_rain_fall_mm_per_year, pesticides_tonnes, avg_temp",
        "join_keys": "area, item, year",
        "use_for": "crop yield trends, country ranking, historical output",
        "keywords": [
            "yield", "rendimiento", "producción", "output", "harvest", "cosecha",
            "hg/ha", "hg_ha", "crop", "cultivo", "country", "país", "historical", "histórico",
        ],
        "denodo": True,
    },
    "crop": {
        "description": "Ideal growing conditions for each crop (N, P, K, pH, temperature, humidity, rainfall).",
        "columns": "label, n, p, k, temperature, humidity, ph, rainfall",
        "join_keys": "label",
        "use_for": "ideal soil and climate conditions, crop recommendation",
        "keywords": [
            "conditions", "condiciones", "soil", "suelo", "ph", "nutrients", "nutrientes",
            "ideal", "recomendación", "recommendation", "humidity", "humedad",
            "nitrogen", "nitrógeno", "potassium", "potasio", "phosphorus", "fósforo",
        ],
        "denodo": True,
    },
    "yield_j_crop": {
        "description": "Crop yield joined with ideal growing conditions. Best for climate/soil vs yield correlation.",
        "columns": "area, item, year, hg_ha_yield, pesticides_tonnes, average_rain_fall_mm_per_year, avg_temp, n, p, k, ph, humidity",
        "join_keys": "area, item, year",
        "use_for": "actual vs ideal conditions, climate impact, soil efficiency analysis",
        "keywords": [
            "yield", "conditions", "soil", "climate", "clima", "nutrientes", "suelo",
            "temperatura", "temperature", "comparison", "comparación", "efficiency", "eficiencia",
            "actual", "real", "optimal", "óptimo",
        ],
        "denodo": True,
    },
    "price_j_yield": {
        "description": "Commodity prices (coffee, tea, sugar, oil) joined with crop yield data.",
        "columns": "area, item, year, hg_ha_yield, coffee_arabica, coffee_robustas, tea_columbo, tea_kolkata, tea_mombasa, sugar_eu, sugar_us, sugar_world, oil_brent, oil_dubai",
        "join_keys": "area, item, year",
        "use_for": "market profitability, price vs yield, investment decisions by crop",
        "keywords": [
            "price", "precio", "market", "mercado", "profit", "rentabilidad",
            "commodity", "coffee", "cafe", "café", "tea", "sugar", "azúcar", "azucar",
            "oil", "petróleo", "petroleo", "investment", "inversión", "inversion", "value", "valor",
        ],
        "denodo": True,
    },
    "smart_farming": {
        "description": "Precision farming sensor data (2024): NDVI, disease status, soil moisture, irrigation.",
        "columns": "farm_id, region, crop_type, Item, Year, soil_moisture_pct, soil_pH, temperature_C, rainfall_mm, humidity_pct, pesticide_usage_ml, yield_kg_per_hectare, NDVI_index, crop_disease_status, irrigation_type, fertilizer_type",
        "join_keys": "Item, Year",
        "use_for": "precision agriculture, IoT sensors, disease detection, irrigation efficiency",
        "keywords": [
            "sensor", "iot", "precision", "smart", "ndvi", "disease", "enfermedad",
            "irrigation", "riego", "fertilizer", "abono", "moisture", "humedad suelo",
            "2024", "modern", "drone", "satellite", "salud del cultivo",
        ],
        "denodo": False,
    },
    "water_footprints": {
        "description": "Water footprint per crop per tonne: green, blue and grey water usage by region.",
        "columns": "Year, region_name, region_iso, item_raw, green_m3_per_ton, blue_m3_per_ton, grey_m3_per_ton",
        "join_keys": "Year, item_raw",
        "use_for": "water sustainability, environmental impact, water efficiency by crop",
        "keywords": [
            "water", "agua", "footprint", "huella hídrica", "huella hidrica",
            "sustainability", "sostenibilidad", "sostenible",
            "green water", "blue water", "grey water", "consumption", "consumo",
            "environment", "medioambiente", "m3", "litre", "litro",
        ],
        "denodo": False,
    },
    "vegetables": {
        "description": "Reference catalogue of 117 vegetables: nutrition, price per kg, season, shelf life.",
        "columns": "vegetable_id, name, scientific_name, category, color, season, origin, availability, shelf_life_days, storage_requirements, growing_conditions, health_benefits, common_varieties, price_per_kg, kcal_per_100g, protein_g_per_100g, fiber_g_per_100g",
        "join_keys": "name",
        "use_for": "vegetable info, nutritional analysis, seasonal pricing, shelf life",
        "keywords": [
            "vegetable", "vegetal", "verdura", "nutrition", "nutrición",
            "price", "precio", "season", "temporada", "health", "salud",
            "diet", "dieta", "fiber", "fibra", "calories", "calorías",
            "shelf life", "vida útil", "storage", "almacenamiento",
        ],
        "denodo": False,
    },
    "pesticides": {
        "description": "Pesticide usage in tonnes by country and year (standalone table).",
        "columns": "area, year, pesticides_tonnes",
        "join_keys": "area, year",
        "use_for": "pesticide trends, environmental monitoring by country",
        "keywords": [
            "pesticide", "pesticida", "plaguicida", "fitosanitario",
            "tonne", "tonelada", "usage", "uso", "chemical", "químico",
        ],
        "denodo": False,
    },
    "commodity_prices": {
        "description": "Annual average commodity prices: coffee, tea, sugar, oil.",
        "columns": "year, coffee_arabica, coffee_robustas, tea_columbo, tea_kolkata, tea_mombasa, sugar_eu, sugar_us, sugar_world, oil_brent, oil_dubai",
        "join_keys": "year",
        "use_for": "price trends, commodity market analysis independent of yield",
        "keywords": [
            "price", "precio", "coffee", "café", "tea", "sugar", "azúcar",
            "oil", "petróleo", "market", "mercado", "commodity", "annual", "anual",
        ],
        "denodo": False,
    },
}
