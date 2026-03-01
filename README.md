# AgroAdvisor

> **Agricultural Intelligence Platform** — HackUDC 2026  
> Powered by [Denodo AI SDK](https://www.denodo.com) · Built with FastAPI · LLM-driven data analysis

AgroAdvisor is an AI-powered agricultural consulting platform that connects natural language questions to a live Denodo Virtual DataPort (VDP) database. It delivers data-backed decisions on crop yields, climate impact, pesticide efficiency and commodity markets — for farmers, agribusinesses and policy-makers.

---

## Features

| Module | Description |
|---|---|
| **Consulta Libre** | Free-form NL chat. Queries the DB and replies with analysis + auto-generated charts |
| **Asesor de Cultivos** | Recommends crops by region based on yield, climate, soil and market profitability |
| **Análisis de Pesticidas** | Correlates pesticide usage with yield efficiency and detects diminishing returns |
| **Impacto Climático** | Temperature & rainfall correlation with crop yield trends |
| **Inteligencia de Mercado** | Commodity price evolution (coffee, tea, sugar, oil) and investment signals |
| **Informe Regional** | Full agricultural profile for any country: crops, climate, pesticides, market opportunities |
| **Auto Charts** | Every response automatically renders line, bar or radar charts from the underlying data |
| **PDF Export** | Download any analysis as a formatted A4 PDF report |

---

## Architecture

```
┌─────────────────────────────────────────────────────────────┐
│  Browser  (HTML + Chart.js + marked.js)                     │
│  static/  chat.js · render.js · charts.js · api.js          │
└────────────────────────┬────────────────────────────────────┘
                         │ HTTP
┌────────────────────────▼────────────────────────────────────┐
│  FastAPI app  (app.py)                                      │
│  core/                                                      │
│    config.py      constants & env loading                   │
│    prompts.py     LLM system instructions                   │
│    sdk_client.py  Denodo AI SDK HTTP client                 │
│    pipeline.py    3-phase reasoning pipeline                │
│    utils.py       helpers, MD table parser, chart extractor │
└────────────────────────┬────────────────────────────────────┘
                         │ HTTP (localhost:8008)
┌────────────────────────▼────────────────────────────────────┐
│  Denodo AI SDK  (Docker)                                    │
│    /answerDataQuestion     SQL generation + execution        │
│    /answerMetadataQuestion VectorDB schema discovery         │
│    /deepQuery              Multi-step reasoning agent        │
└────────────────────────┬────────────────────────────────────┘
                         │ VDP protocol
┌────────────────────────▼────────────────────────────────────┐
│  Denodo VDP  (Docker)   database: proba                     │
│    yield · crop · price_j_yield · yield_j_crop              │
└─────────────────────────────────────────────────────────────┘
```

### 3-Phase Query Pipeline

1. **Phase 0 — VectorDB** Semantic schema search via ChromaDB + embeddings
2. **Phase 1 — Metadata** Schema discovery via `answerMetadataQuestion`
3. **Phase 2 — Data** SQL generation & execution via `answerDataQuestion`

DeepQuery mode runs a thinking LLM that plans, executes multiple SQL queries iteratively and synthesizes a comprehensive report.

---

## Project Structure

```
AgroAdvisor/
├── app.py                  FastAPI application & routes
├── requirements.txt
├── docker-compose.yml      Denodo VDP + AI SDK containers
├── config/
│   ├── sdk_config.env      AI SDK configuration (LLM, embeddings, keys)
│   ├── chatbot_config.env  Chatbot UI configuration
│   └── denodo.lic          Denodo Express license
├── core/
│   ├── config.py           Constants & environment loading
│   ├── prompts.py          LLM system instructions
│   ├── pipeline.py         3-phase & DeepQuery pipelines
│   ├── sdk_client.py       Denodo AI SDK HTTP client
│   └── utils.py            Helpers, markdown table parser, chart extractor
├── static/
│   ├── main.js             UI shell, navigation, toasts
│   ├── chat.js             Chat panel & message loop
│   ├── render.js           Markdown, pipeline trace, result cards
│   ├── charts.js           Auto chart detection & Chart.js rendering
│   ├── api.js              Fetch helpers & PDF download
│   └── style.css           Design system
├── templates/
│   └── index.html          Single-page application shell
└── BD/
    └── ...                 Source CSV datasets & preprocessing scripts
```

---

## Getting Started

### Prerequisites

- [Docker Desktop](https://www.docker.com/products/docker-desktop/) (for Denodo VDP + AI SDK)
- Python 3.11+
- A Denodo Express license (`config/denodo.lic`)
- An LLM API key (Groq, Google AI Studio, OpenAI, etc.)

### 1 — Configure the LLM

Edit `config/sdk_config.env`:

```dotenv
LLM_PROVIDER = groq
LLM_MODEL    = llama-3.3-70b-versatile
GROQ_API_KEY = your_key_here

# DeepQuery thinking model (optional)
THINKING_LLM_PROVIDER = googleaistudio
THINKING_LLM_MODEL    = gemini-2.5-flash

# Embeddings (used for vector schema search)
EMBEDDINGS_PROVIDER = googleaistudio
EMBEDDINGS_MODEL    = gemini-embedding-001
GOOGLE_API_KEY      = your_key_here
```

Mirror the `LLM_PROVIDER` and `LLM_MODEL` in `config/chatbot_config.env`.

### 2 — Start Denodo + AI SDK

```bash
docker compose up -d
```

Wait ~60 s for VDP to initialise. The AI SDK will be available at `http://localhost:8008`.

### 3 — Sync metadata (first run)

Open `http://localhost:8000` in the browser and click **Sincronizar metadatos** in the sidebar — or call the endpoint directly:

```bash
curl http://localhost:8000/api/sync
```

### 4 — Start AgroAdvisor

```bash
pip install -r requirements.txt
python app.py
```

Then open **http://localhost:8000**.

---

## Database Schema

All data is served through Denodo VDP (database: `proba`).

| View | Key columns | Use for |
|---|---|---|
| `yield` | area, item, year, hg_ha_yield, avg_temp, average_rain_fall_mm_per_year, pesticides_tonnes | Historical crop output |
| `crop` | label, n, p, k, temperature, humidity, ph, rainfall | Ideal growing conditions |
| `yield_j_crop` | yield + crop joined | Climate & soil correlation |
| `price_j_yield` | yield + commodity prices | Market profitability |

Source CSV files are in `BD/` and were preprocessed with `BD/preprocess.py`.

---

## API Endpoints

| Method | Path | Description |
|---|---|---|
| `GET` | `/` | Web UI |
| `GET` | `/api/ask?question=&mode=` | Main chat (mode: `auto` \| `data` \| `metadata`) |
| `GET` | `/api/deep-query?question=` | DeepQuery — multi-step reasoning |
| `GET` | `/api/deep-query-stream?question=` | DeepQuery SSE stream |
| `GET` | `/api/crop-advisor?area=&conditions=` | Crop recommendation |
| `GET` | `/api/pesticide-analysis?area=` | Pesticide efficiency analysis |
| `GET` | `/api/climate-impact?area=` | Climate–yield correlation |
| `GET` | `/api/market-intelligence` | Commodity market analysis |
| `GET` | `/api/regional-report?area=` | Full country profile |
| `GET` | `/api/sync` | Sync Denodo metadata to VectorDB |
| `GET` | `/api/metadata?question=` | Direct schema question |
| `POST` | `/api/report` | Generate PDF from analysis results |
| `GET` | `/api/health` | Liveness check |

---

## Configuration Reference

### `config/sdk_config.env`

| Key | Description |
|---|---|
| `AI_SDK_HOST` / `AI_SDK_PORT` | SDK listening address (default `0.0.0.0:8008`) |
| `LLM_PROVIDER` | LLM provider (`groq`, `googleaistudio`, `openai`, `anthropic`, …) |
| `LLM_MODEL` | Model ID for SQL generation & chat |
| `LLM_TEMPERATURE` | Temperature (0.0 recommended for SQL) |
| `THINKING_LLM_PROVIDER` / `THINKING_LLM_MODEL` | Model for DeepQuery reasoning |
| `EMBEDDINGS_PROVIDER` / `EMBEDDINGS_MODEL` | Embeddings for VectorDB schema search |
| `GROQ_API_KEY` | Groq API key |
| `GOOGLE_API_KEY` | Google AI Studio API key |

### `core/config.py`

| Constant | Description |
|---|---|
| `AI_SDK_BASE_URL` | Denodo AI SDK URL (default `http://localhost:8008`) |
| `VDP_DATABASE` | Denodo database name (default `proba`) |
| `DENODO_USER` / `DENODO_PASS` | VDP credentials |

---

## Tech Stack

| Layer | Technology |
|---|---|
| Backend | Python 3.11 · FastAPI · httpx |
| Frontend | Vanilla JS · Chart.js 4 · marked.js |
| LLM Routing | Denodo AI SDK |
| Vector Search | ChromaDB + gemini-embedding-001 |
| Database | Denodo VDP (Virtual DataPort) |
| PDF | xhtml2pdf |
| Containers | Docker Compose |

---

## Team — HackUDC 2026

Built at **HackUDC 2026**, Universidade da Coruña.

- Paula Esteve Sabater
- Sergi Flores 
- Weihao Lin

---

## License

MIT — see [LICENSE](LICENSE).
