"""AgroAdvisor - Configuration & constants."""

import os
from pathlib import Path

# Load sdk_config.env
_SDK_ENV = Path(__file__).parent.parent / "config" / "sdk_config.env"
if _SDK_ENV.exists():
    for _line in _SDK_ENV.read_text(encoding="utf-8").splitlines():
        _line = _line.strip()
        if not _line or _line.startswith("#") or "=" not in _line:
            continue
        _k, _, _v = _line.partition("=")
        _k, _v = _k.strip(), _v.strip().strip('"').strip("'")
        if _k and _k not in os.environ:
            os.environ[_k] = _v

# Auth & connection
AI_SDK_BASE_URL = os.getenv("AI_SDK_BASE_URL", "http://localhost:8008")
DENODO_USER     = os.getenv("DENODO_USER", "admin")
DENODO_PASS     = os.getenv("DENODO_PASS", "admin")
AUTH            = (DENODO_USER, DENODO_PASS)

# Thinking LLM (Ollama)
THINKING_MODEL  = os.getenv("THINKING_LLM_MODEL", "llama3")
OLLAMA_BASE_URL = os.getenv("OLLAMA_HOST_URL", "http://localhost:11434")

VDP_DATABASE = "denodo"

# SDK endpoints
DATA_URL       = f"{AI_SDK_BASE_URL}/answerDataQuestion"
METADATA_URL   = f"{AI_SDK_BASE_URL}/answerMetadataQuestion"
DEEP_QUERY_URL = f"{AI_SDK_BASE_URL}/deepQuery"
GET_METADATA_URL   = f"{AI_SDK_BASE_URL}/getMetadata"
VECTOR_DB_INFO_URL = f"{AI_SDK_BASE_URL}/getVectorDBInfo"

# Timeouts (seconds)
TIMEOUT_DATA     = 240.0
TIMEOUT_METADATA = 120.0
TIMEOUT_VECTOR   = 60.0
TIMEOUT_DEEP     = 900.0

# ES->EN translations
AREA_TRANSLATIONS = {
    "brasil": "Brazil", "espana": "Spain", "alemania": "Germany",
    "francia": "France", "estados unidos": "United States of America",
    "reino unido": "United Kingdom", "paises bajos": "Netherlands",
    "japon": "Japan", "mexico": "Mexico", "peru": "Peru",
    "italia": "Italy", "rusia": "Russian Federation", "turquia": "Turkey",
    "egipto": "Egypt", "corea del sur": "Republic of Korea",
    "sudafrica": "South Africa", "nueva zelanda": "New Zealand",
    "china": "China", "india": "India", "argentina": "Argentina",
    "colombia": "Colombia", "australia": "Australia", "canada": "Canada",
    "polonia": "Poland", "ucrania": "Ukraine",
}

CROP_TRANSLATIONS = {
    "patatas": "Potatoes", "maiz": "Maize", "arroz": "Rice",
    "trigo": "Wheat", "yuca": "Cassava", "soja": "Soybeans",
    "cana de azucar": "Sugar cane", "cafe": "Coffee", "sorgo": "Sorghum",
    "cebada": "Barley", "algodon": "Cotton", "platano": "Plantains",
    "girasol": "Sunflower", "colza": "Rapeseed", "avena": "Oats",
    "naranja": "Oranges", "tomate": "Tomatoes", "cebolla": "Onions",
}

# Table catalogue for Phase 0 ranking
TABLE_CATALOGUE = {
    "yield": {
        "description": "Historical crop yield by country and year.",
        "columns": "area, item, year, hg_ha_yield, average_rain_fall_mm_per_year, pesticides_tonnes, avg_temp",
        "join_keys": "area, item, year",
        "use_for": "crop yield trends, country ranking, historical output",
        "keywords": [
            "yield", "rendimiento", "produccion", "output", "harvest", "cosecha",
            "crop", "cultivo", "country", "pais", "historical",
        ],
        "denodo": True,
    },
    "crop": {
        "description": "Ideal growing conditions per crop (N, P, K, pH, temperature, humidity, rainfall).",
        "columns": "label, n, p, k, temperature, humidity, ph, rainfall",
        "join_keys": "label",
        "use_for": "ideal soil and climate conditions, crop recommendation",
        "keywords": [
            "conditions", "condiciones", "soil", "suelo", "ph", "nutrients", "nutrientes",
            "ideal", "recommendation", "humidity", "humedad",
        ],
        "denodo": True,
    },
    "yield_j_crop": {
        "description": "Crop yield joined with ideal growing conditions.",
        "columns": "area, item, year, hg_ha_yield, pesticides_tonnes, average_rain_fall_mm_per_year, avg_temp, n, p, k, ph, humidity",
        "join_keys": "area, item, year",
        "use_for": "actual vs ideal conditions, climate impact, soil efficiency",
        "keywords": [
            "yield", "conditions", "soil", "climate", "clima", "nutrientes", "suelo",
            "temperatura", "temperature", "comparison", "efficiency",
        ],
        "denodo": True,
    },
    "price_j_yield": {
        "description": "Commodity prices joined with crop yield data.",
        "columns": "area, item, year, hg_ha_yield, coffee_arabica, coffee_robustas, tea_columbo, tea_kolkata, tea_mombasa, sugar_eu, sugar_us, sugar_world, oil_brent, oil_dubai",
        "join_keys": "area, item, year",
        "use_for": "market profitability, price vs yield, investment decisions",
        "keywords": [
            "price", "precio", "market", "mercado", "profit", "rentabilidad",
            "commodity", "coffee", "cafe", "tea", "sugar", "azucar",
            "oil", "petroleo", "investment", "inversion",
        ],
        "denodo": True,
    },
    "smart_farming": {
        "description": "Precision farming sensor data (2024): NDVI, disease, soil moisture.",
        "columns": "farm_id, region, crop_type, Item, Year, soil_moisture_pct, soil_pH, temperature_C, rainfall_mm, humidity_pct, pesticide_usage_ml, yield_kg_per_hectare, NDVI_index, crop_disease_status, irrigation_type, fertilizer_type",
        "join_keys": "Item, Year",
        "use_for": "precision agriculture, IoT sensors, disease detection",
        "keywords": ["sensor", "iot", "precision", "smart", "ndvi", "disease", "irrigation", "riego"],
        "denodo": False,
    },
    "water_footprints": {
        "description": "Water footprint per crop per tonne: green, blue and grey water.",
        "columns": "Year, region_name, region_iso, item_raw, green_m3_per_ton, blue_m3_per_ton, grey_m3_per_ton",
        "join_keys": "Year, item_raw",
        "use_for": "water sustainability, environmental impact",
        "keywords": ["water", "agua", "footprint", "huella hidrica", "sustainability", "sostenibilidad"],
        "denodo": False,
    },
    "vegetables": {
        "description": "Reference catalogue of 117 vegetables: nutrition, price, season.",
        "columns": "vegetable_id, name, scientific_name, category, color, season, origin, availability, shelf_life_days, storage_requirements, growing_conditions, health_benefits, common_varieties, price_per_kg, kcal_per_100g, protein_g_per_100g, fiber_g_per_100g",
        "join_keys": "name",
        "use_for": "vegetable info, nutritional analysis, seasonal pricing",
        "keywords": ["vegetable", "verdura", "nutrition", "nutricion", "price", "precio", "season", "temporada"],
        "denodo": False,
    },
    "pesticides": {
        "description": "Pesticide usage in tonnes by country and year.",
        "columns": "area, year, pesticides_tonnes",
        "join_keys": "area, year",
        "use_for": "pesticide trends, environmental monitoring",
        "keywords": ["pesticide", "pesticida", "plaguicida", "fitosanitario"],
        "denodo": False,
    },
    "commodity_prices": {
        "description": "Annual average commodity prices: coffee, tea, sugar, oil.",
        "columns": "year, coffee_arabica, coffee_robustas, tea_columbo, tea_kolkata, tea_mombasa, sugar_eu, sugar_us, sugar_world, oil_brent, oil_dubai",
        "join_keys": "year",
        "use_for": "price trends, commodity market analysis",
        "keywords": ["price", "precio", "coffee", "cafe", "tea", "sugar", "azucar", "oil", "petroleo", "commodity"],
        "denodo": False,
    },
}
