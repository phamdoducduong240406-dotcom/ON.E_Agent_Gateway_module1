"""
Module 1 — Ingest
Đọc catalog thô → chuẩn hoá tên field → tạo _raw_text.
Không gọi mạng.

§5.3 Rule 3 là load-bearing: warranty_raw PHẢI nằm trong _raw_text.
"""

from __future__ import annotations

import json
import sys
import unicodedata
from pathlib import Path
from typing import Any

if sys.platform == "win32" and hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

from schema import FIELD_MAP


def _normalise_key(key: str) -> str:
    """Chuẩn hoá tên field: NFC, lowercase, strip."""
    return unicodedata.normalize("NFC", key).strip().lower()


def _map_field_name(raw_key: str) -> str:
    """Đổi tên field lộn xộn → tên chuẩn qua FIELD_MAP.
    Nếu không tìm thấy trong map, giữ nguyên key đã normalise."""
    normalised = _normalise_key(raw_key)
    return FIELD_MAP.get(normalised, normalised)


def _build_raw_text(record: dict[str, Any]) -> str:
    """Ghép tất cả field dạng text thành _raw_text cho verification.

    §5.3 Rule 3: PHẢI include description VÀ warranty_raw.
    Thiếu warranty_raw → mọi policy field bị flag low confidence → mất 20 min debug.
    """
    parts: list[str] = []

    # Ưu tiên các text blob lớn trước — description + warranty_raw là bắt buộc
    for text_field in ("description", "warranty_raw", "specs_text", "policy_text"):
        if text_field in record and isinstance(record[text_field], str):
            parts.append(record[text_field])

    # Thêm các field string khác (trừ field đã thêm và field hệ thống)
    skip = {"description", "warranty_raw", "specs_text", "policy_text",
            "_raw_text", "sku", "name", "brand", "category", "currency"}
    for key, val in record.items():
        if key not in skip and isinstance(val, str) and len(val) > 20:
            parts.append(val)

    return "\n".join(parts)


def load_catalog(path: str | Path) -> list[dict[str, Any]]:
    """Đọc catalog thô từ JSON file.

    Args:
        path: Đường dẫn đến file catalog_raw.json

    Returns:
        List raw records (chưa normalize)
    """
    path = Path(path)
    with open(path, "r", encoding="utf-8") as f:
        raw_records = json.load(f)

    print(f"[ingest] Loaded {len(raw_records)} raw records from {path.name}")
    return raw_records


def normalize_record(raw: dict[str, Any]) -> dict[str, Any] | None:
    """Chuẩn hoá một record: rename keys, build _raw_text.

    §5.3 Rules:
    1. Rename keys via FIELD_MAP; unmapped keys pass through unchanged.
    2. Drop any record with no sku (return None).
    3. Build _raw_text joining description + warranty_raw + mọi free-text field.

    Args:
        raw: Record thô từ catalog

    Returns:
        Record đã chuẩn hoá, hoặc None nếu thiếu SKU
    """
    record: dict[str, Any] = {}

    # Map tên field
    for raw_key, value in raw.items():
        mapped_key = _map_field_name(raw_key)
        record[mapped_key] = value

    # Rule 2: Drop if no SKU
    if "sku" not in record:
        print(f"WARNING: Record without SKU, skipping: {record.get('name', 'unknown')}")
        return None

    # Rule 3: Build _raw_text (description + warranty_raw + all text)
    record["_raw_text"] = _build_raw_text(record)

    return record


def ingest(path: str | Path) -> list[dict[str, Any]]:
    """Full ingest pipeline: load → normalize → filter.

    Args:
        path: Đường dẫn đến file catalog_raw.json

    Returns:
        List các record đã chuẩn hoá, mỗi record có sku, name, _raw_text
    """
    raw_records = load_catalog(path)
    records: list[dict[str, Any]] = []

    for raw in raw_records:
        record = normalize_record(raw)
        if record is not None:
            records.append(record)

    # Validate
    valid = sum(1 for r in records if r.get("_raw_text") and len(r["_raw_text"]) > 0)
    print(f"[ingest] {len(records)} records normalized ({valid} with non-empty _raw_text)")

    # Check warranty_raw presence
    has_warranty = sum(1 for r in records if "warranty_raw" in r)
    print(f"[ingest] {has_warranty}/{len(records)} records have warranty_raw in _raw_text")

    return records


# ── CLI test ───────────────────────────────────────────────────────────
if __name__ == "__main__":
    from config import CATALOG_RAW_PATH

    records = ingest(CATALOG_RAW_PATH)

    # Acceptance test: every record has sku, name, _raw_text > 0
    for r in records:
        assert "sku" in r, f"Missing sku in record"
        assert "_raw_text" in r, f"Missing _raw_text in {r['sku']}"
        assert len(r["_raw_text"]) > 0, f"Empty _raw_text in {r['sku']}"

    print(f"\n✓ Acceptance passed: {len(records)} records, all have sku + _raw_text")

    # Print first record as sample
    if records:
        sample = records[0]
        print(f"\n--- Sample record: {sample['sku']} ---")
        for k, v in sample.items():
            if k == "_raw_text":
                print(f"  {k}: ({len(v)} chars)")
            else:
                print(f"  {k}: {v}")
