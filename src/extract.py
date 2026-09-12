"""
Module 1 — Extract
Gọi Gemini LLM để extract specs, policy, outcomes, values từ text thô.
Cache theo SKU + hash(raw_text + PROMPT_VERSION) — đổi prompt tự invalidate cache.
"""

from __future__ import annotations

import hashlib
import json
import re
import sys
import time
import traceback
from pathlib import Path
from typing import Any

if sys.platform == "win32" and hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

from config import (
    GEMINI_API_KEY,
    MODEL_NAME,
    FALLBACK_MODEL_NAME,
    TEMPERATURE,
    MAX_TOKENS,
    EXTRACTION_PROMPT,
    CACHE_DIR,
    MAX_RETRIES,
    RETRY_BASE_DELAY,
    PROMPT_VERSION,
)
from schema import ExtractedSpecs


def cache_key(sku: str, raw_text: str) -> str:
    """Tạo cache key = hash(raw_text + PROMPT_VERSION).
    Thay đổi prompt → tự động invalidate cache.

    Args:
        sku: SKU sản phẩm
        raw_text: Text thô cần extract

    Returns:
        Hash string
    """
    content = raw_text + PROMPT_VERSION
    return hashlib.sha256(content.encode("utf-8")).hexdigest()[:12]


def _get_cache_path(sku: str, raw_text: str) -> Path:
    """Đường dẫn cache file: CACHE_DIR/{sku}_{hash}.json"""
    safe_sku = re.sub(r'[^\w\-]', '_', sku)
    h = cache_key(sku, raw_text)
    return CACHE_DIR / f"{safe_sku}_{h}.json"


def _read_cache(sku: str, raw_text: str = "") -> dict[str, Any] | None:
    """Đọc cache cho SKU. Trả None nếu chưa có hoặc prompt đã đổi.

    Args:
        sku: SKU sản phẩm
        raw_text: Text thô (cần cho hash check). Nếu rỗng, tìm file cũ.
    """
    if raw_text:
        cache_path = _get_cache_path(sku, raw_text)
        if cache_path.exists():
            try:
                with open(cache_path, "r", encoding="utf-8") as f:
                    return json.load(f)
            except (json.JSONDecodeError, IOError):
                return None
    else:
        # Fallback: tìm bất kỳ cache file nào cho SKU này
        safe_sku = re.sub(r'[^\w\-]', '_', sku)
        for p in CACHE_DIR.glob(f"{safe_sku}*.json"):
            try:
                with open(p, "r", encoding="utf-8") as f:
                    return json.load(f)
            except (json.JSONDecodeError, IOError):
                continue
    return None


def _write_cache(sku: str, raw_text: str, data: dict[str, Any]) -> None:
    """Ghi cache cho SKU. ensure_ascii=False vì catalog có tiếng Việt."""
    cache_path = _get_cache_path(sku, raw_text)
    with open(cache_path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def _strip_markdown_fences(text: str) -> str:
    """Loại bỏ markdown code fences nếu có.
    §5.4 Rule 2: Luôn strip ```json ... ``` trước khi parse.
    Models vẫn emit fences kể cả khi bật structured output."""
    text = text.strip()
    # Remove ```json ... ``` or ``` ... ```
    pattern = r'^```(?:json)?\s*\n?(.*?)\n?\s*```$'
    match = re.match(pattern, text, re.DOTALL)
    if match:
        return match.group(1).strip()
    return text


def _parse_llm_response(response_text: str) -> dict[str, Any]:
    """Parse LLM response thành dict. Xử lý cả structured output và raw JSON."""
    cleaned = _strip_markdown_fences(response_text)
    try:
        return json.loads(cleaned)
    except json.JSONDecodeError:
        # Try to find JSON object in the response
        match = re.search(r'\{.*\}', cleaned, re.DOTALL)
        if match:
            return json.loads(match.group())
        raise ValueError(f"Cannot parse LLM response as JSON: {cleaned[:200]}...")


def _normalise_extracted(raw_specs: dict[str, Any]) -> dict[str, Any]:
    """Chuẩn hoá output từ LLM thành format thống nhất.
    Mỗi field có: value, source_span, note (optional)."""
    normalised: dict[str, Any] = {}

    for field_name, field_data in raw_specs.items():
        if field_data is None:
            continue

        if isinstance(field_data, dict):
            normalised[field_name] = {
                "value": field_data.get("value"),
                "source_span": field_data.get("source_span"),
                "note": field_data.get("note"),
            }
        elif isinstance(field_data, list):
            # Handle list fields (e.g., values)
            normalised[field_name] = field_data
        else:
            # LLM trả về value thô — wrap lại
            normalised[field_name] = {
                "value": field_data,
                "source_span": None,
                "note": "LLM returned raw value without source_span",
            }

    return normalised


def build_prompt(raw_text: str) -> str:
    """Build extraction prompt từ raw text.

    Args:
        raw_text: Text thô cần extract

    Returns:
        Prompt đầy đủ cho LLM
    """
    return EXTRACTION_PROMPT.format(text=raw_text)


def call_llm(raw_text: str, model: str | None = None) -> dict[str, Any]:
    """Gọi LLM để extract specs từ raw text.

    Args:
        raw_text: Text thô
        model: Tên model Gemini cần gọi (nếu None, dùng MODEL_NAME)

    Returns:
        Dict specs đã extract

    Raises:
        Exception nếu tất cả retry fail
    """
    from google import genai

    client = genai.Client(api_key=GEMINI_API_KEY)
    prompt = build_prompt(raw_text)
    selected_model = model or MODEL_NAME

    response = client.models.generate_content(
        model=selected_model,
        contents=prompt,
        config={
            "temperature": TEMPERATURE,
            "max_output_tokens": MAX_TOKENS,
            "response_mime_type": "application/json",
            "response_schema": ExtractedSpecs,
        },
    )

    # Parse response
    if response.parsed:
        raw_specs = response.parsed.model_dump(exclude_none=True)
    else:
        raw_specs = _parse_llm_response(response.text)

    return _normalise_extracted(raw_specs)


def extract_with_cache(record: dict[str, Any]) -> dict[str, Any]:
    """Extract specs cho một record, có cache và fallback model.

    §5.4 Rules:
    - Cache mỗi response, key = sku + hash(raw_text + PROMPT_VERSION)
    - Resumable: cached SKUs skip network call
    - Wrap trong try/except — one bad SKU logs and continues
    - Auto fallback model nếu primary model gặp 429 quota hoặc lỗi mạng

    Args:
        record: Record đã qua ingest, có _raw_text

    Returns:
        Dict các specs đã extract
    """
    sku = record.get("sku", "unknown")
    raw_text = record.get("_raw_text", "")

    # 1. Check cache first
    cached = _read_cache(sku, raw_text)
    if cached is not None:
        print(f"  [extract] {sku}: cache hit")
        return cached

    # 2. Skip if no text to extract from
    if not raw_text:
        print(f"  [extract] {sku}: no text to extract, skipping LLM")
        return {}

    # 3. Call LLM with retry & fallback
    models_to_try = [MODEL_NAME]
    if FALLBACK_MODEL_NAME and FALLBACK_MODEL_NAME != MODEL_NAME:
        models_to_try.append(FALLBACK_MODEL_NAME)

    last_error = None
    for attempt in range(MAX_RETRIES):
        model_to_use = models_to_try[min(attempt, len(models_to_try) - 1)]
        try:
            specs = call_llm(raw_text, model=model_to_use)

            # Cache result
            _write_cache(sku, raw_text, specs)
            print(f"  [extract] {sku}: extracted {len(specs)} fields via {model_to_use} (attempt {attempt + 1})")
            return specs

        except Exception as e:
            last_error = e
            delay = RETRY_BASE_DELAY * (2 ** attempt)
            print(f"  [extract] {sku}: attempt {attempt + 1} failed ({model_to_use}): {e}")
            if attempt < MAX_RETRIES - 1:
                print(f"  [extract] Retrying in {delay}s...")
                time.sleep(delay)

    # All retries exhausted — log and continue, never kill the run
    print(f"  [extract] {sku}: FAILED after {MAX_RETRIES} attempts: {last_error}")
    traceback.print_exc()
    return {}


def extract_all(records: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Extract specs cho tất cả records.

    §5.4 Rule 4: Resumable — on restart, cached SKUs skip network call.

    Args:
        records: List records từ ingest

    Returns:
        Cùng list records, mỗi record thêm field '_extracted_specs'
    """
    total = len(records)
    success = 0
    cached = 0

    for i, record in enumerate(records, 1):
        sku = record.get("sku", "unknown")
        print(f"[extract] Processing {i}/{total}: {sku}")

        # Check if already cached (for counting)
        raw_text = record.get("_raw_text", "")
        was_cached = _read_cache(sku, raw_text) is not None

        specs = extract_with_cache(record)
        record["_extracted_specs"] = specs

        if specs:
            success += 1
            if was_cached:
                cached += 1
            else:
                time.sleep(1)  # small pause to avoid rate limit spikes on free tier

    print(f"\n[extract] Summary: {success}/{total} extracted ({cached} from cache)")
    return records


# ── CLI test ───────────────────────────────────────────────────────────
if __name__ == "__main__":
    from config import CATALOG_RAW_PATH
    from ingest import ingest

    records = ingest(CATALOG_RAW_PATH)

    # Test with first record only
    if records:
        sample = records[0]
        print(f"\nExtracting specs for: {sample['sku']}")
        specs = extract_with_cache(sample)
        print(json.dumps(specs, ensure_ascii=False, indent=2))
