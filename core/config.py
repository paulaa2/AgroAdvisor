"""
AgroAdvisor – Configuration & constants
All environment-dependent values and shared constants live here.
"""

import os

# ─── Auth & connection ──────────────────────────────────────────────────────
AI_SDK_BASE_URL: str = os.getenv("AI_SDK_BASE_URL", "http://localhost:8008")
DENODO_USER: str     = os.getenv("DENODO_USER", "admin")
DENODO_PASS: str     = os.getenv("DENODO_PASS", "admin")
AUTH: tuple[str, str] = (DENODO_USER, DENODO_PASS)

VDP_DATABASE: str = "proba"

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
