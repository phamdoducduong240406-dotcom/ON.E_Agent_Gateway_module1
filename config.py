"""
Module 1 — Configuration
Hằng số, đường dẫn, tên model, tham số LLM và embedding.
"""

import os
from pathlib import Path
from dotenv import load_dotenv

load_dotenv()

# ── Paths ──────────────────────────────────────────────────────────────
BASE_DIR = Path(__file__).resolve().parent
DATA_DIR = BASE_DIR / "data"
CACHE_DIR = DATA_DIR / "cache"
OUTPUT_DIR = BASE_DIR / "output"

# Ensure directories exist
CACHE_DIR.mkdir(parents=True, exist_ok=True)
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

# ── LLM Configuration ─────────────────────────────────────────────────
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "")
MODEL_NAME = "gemini-3.5-flash-lite"
FALLBACK_MODEL_NAME = "gemini-3.5-flash"
TEMPERATURE = 0
MAX_TOKENS = 8192
PROMPT_VERSION = "v2"

# ── Embedding Configuration ───────────────────────────────────────────
EMBED_MODEL = "BAAI/bge-m3"

# ── Retrieval Settings ────────────────────────────────────────────────
TOP_K_SEMANTIC = 20   # retrieve wide, filter after
TOP_K_RETURN = 3

# ── Pipeline Settings ─────────────────────────────────────────────────
MAX_RETRIES = 3
RETRY_BASE_DELAY = 2  # seconds, exponential backoff

# ── File Paths ─────────────────────────────────────────────────────────
CATALOG_RAW_PATH = DATA_DIR / "catalog_raw.json"
GOLDEN_QUERIES_PATH = DATA_DIR / "golden_queries.json"
RELATIONS_CSV_PATH = DATA_DIR / "relations.csv"
COMPAT_CSV_PATH = RELATIONS_CSV_PATH  # backward compat
OUT_PATH = OUTPUT_DIR / "catalog_standardized.json"
OUTPUT_PATH = OUT_PATH  # backward compat

# ── Extraction Prompt (§6 — verbatim) ─────────────────────────────────
EXTRACTION_PROMPT = """You are a product data extraction system for an agentic-commerce catalogue.
Extract structured data from the raw product text below.

RULES:
1. For every field you extract, you MUST return "source_span": the exact
   substring, copied character for character, from the input text.
2. If a value is not stated explicitly and you had to infer it, set
   "source_span" to null and explain briefly in "note".
3. Never invent a value that has no basis in the text. Omit the field instead.
4. Do not normalise units inside source_span. Copy it raw.
5. Input may be Vietnamese or English. Field names in English; textual values
   stay in the original language.
6. For "values": use ONLY the labels in VALUE_TAXONOMY. Do not create new labels.
   A vague marketing phrase that names no specific practice must be returned
   with source_span null.
7. For "use_cases", "skill_level", "environment": use ONLY the allowed enums.

TECHNICAL FIELDS: connection_type, polar_pattern, freq_response,
                  phantom_power, sample_rate, ports,
                  screen_size, panel_type, refresh_rate, resolution, power
POLICY FIELDS:    warranty_months, warranty_scope, return_days, exclusions
OUTCOME FIELDS:   use_cases, skill_level, environment
VALUE_TAXONOMY:   sustainable_materials, recyclable_packaging, repairability,
                  long_warranty, local_manufacturing, ethical_sourcing,
                  energy_efficiency, carbon_disclosure

RAW TEXT:
{text}

Return JSON only. No markdown fences, no explanation."""
