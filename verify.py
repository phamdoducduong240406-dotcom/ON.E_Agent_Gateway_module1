"""
Module 1 — Verify
Đối chiếu source_span với text gốc → gán confidence.
Không gọi mạng.

§5.5 NFC là bắt buộc: tiếng Việt có hai cách mã hoá dấu,
thiếu NFC thì mọi field tiếng Việt bị flag low một cách oan uổng.
"""

from __future__ import annotations

import re
import unicodedata
from typing import Any


def norm(s: str) -> str:
    """Chuẩn hoá text cho so sánh: NFC → lowercase → collapse whitespace.

    §5.5: NFC là bắt buộc. Vietnamese diacritics có composed vs decomposed forms
    trông giống nhau nhưng fail `in` comparison.

    Args:
        s: Text cần chuẩn hoá

    Returns:
        Text đã NFC + lowercase + single-space
    """
    if not s:
        return ""
    s = unicodedata.normalize("NFC", s)
    s = s.lower()
    s = " ".join(s.split())
    return s


def verify_fields(fields: list[dict[str, Any]], raw_text: str) -> list[dict[str, Any]]:
    """Đối chiếu danh sách fields (dạng list of dicts) với raw_text.

    §5.5 Rules:
    1. norm(source_span) in norm(raw_text) → confidence = "high"
    2. Otherwise → confidence = "low", source_span = None
    3. Never delete a low-confidence field — flag it and keep it

    Args:
        fields: List of {value, source_span, note, ...}
        raw_text: Text gốc

    Returns:
        Same list with confidence added to each field
    """
    normalised_text = norm(raw_text)
    verified: list[dict[str, Any]] = []

    for field_data in fields:
        if not isinstance(field_data, dict):
            field_data = {"value": field_data, "source_span": None}

        value = field_data.get("value")
        if value is None:
            continue

        v = dict(field_data)  # copy

        source_span = v.get("source_span")
        if source_span and isinstance(source_span, str):
            normalised_span = norm(source_span)
            if normalised_span and normalised_span in normalised_text:
                v["confidence"] = "high"
            else:
                v["confidence"] = "low"
                v["source_span"] = None
                if not v.get("note"):
                    v["note"] = "source_span not found in raw text"
        else:
            v["confidence"] = "low"
            v["source_span"] = None
            if not v.get("note"):
                v["note"] = "no source_span provided"

        verified.append(v)

    return verified


def _verify_dict_fields(
    specs: dict[str, Any],
    raw_text: str,
) -> dict[str, Any]:
    """Đối chiếu source_span của dict fields (mỗi key → {value, source_span}).

    Args:
        specs: Dict field_name → {value, source_span, note}
        raw_text: Text gốc

    Returns:
        Same dict với confidence added
    """
    normalised_text = norm(raw_text)
    verified: dict[str, Any] = {}

    for field_name, field_data in specs.items():
        if not isinstance(field_data, dict):
            field_data = {"value": field_data, "source_span": None}

        value = field_data.get("value")
        if value is None:
            continue

        verified_field = dict(field_data)
        source_span = verified_field.get("source_span")

        if source_span and isinstance(source_span, str):
            normalised_span = norm(source_span)
            if normalised_span and normalised_span in normalised_text:
                verified_field["confidence"] = "high"
            else:
                verified_field["confidence"] = "low"
                verified_field["source_span"] = None
                if not verified_field.get("note"):
                    verified_field["note"] = "source_span not found in raw text"
        else:
            verified_field["confidence"] = "low"
            verified_field["source_span"] = None
            if not verified_field.get("note"):
                verified_field["note"] = "no source_span provided"

        verified[field_name] = verified_field

    return verified


def verify_record(rec: dict[str, Any]) -> dict[str, Any]:
    """Verify tất cả extracted specs trong một record.

    §5.5 Rule 4: Apply to specs, policy, outcomes, values alike.

    Args:
        rec: Record có '_extracted_specs' và '_raw_text'

    Returns:
        Cùng record, '_extracted_specs' đã được gán confidence
    """
    specs = rec.get("_extracted_specs", {})
    raw_text = rec.get("_raw_text", "")

    if specs and raw_text:
        # Verify tất cả dict fields (specs, policy, outcomes)
        verified = _verify_dict_fields(specs, raw_text)

        # Verify values list nếu có
        if "values" in specs and isinstance(specs["values"], list):
            verified["values"] = verify_fields(specs["values"], raw_text)

        rec["_extracted_specs"] = verified

    return rec


def verify_all(records: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Verify tất cả records đã extract.

    Args:
        records: List records đã có '_extracted_specs' từ extract step

    Returns:
        Cùng list records, '_extracted_specs' đã được gán confidence
    """
    total = len(records)
    high_count = 0
    low_count = 0

    for i, record in enumerate(records, 1):
        sku = record.get("sku", "unknown")
        specs = record.get("_extracted_specs", {})

        if specs:
            verify_record(record)
            verified = record.get("_extracted_specs", {})

            # Count confidence
            for field_name, field_data in verified.items():
                if isinstance(field_data, dict):
                    if field_data.get("confidence") == "high":
                        high_count += 1
                    else:
                        low_count += 1
                elif isinstance(field_data, list):
                    for item in field_data:
                        if isinstance(item, dict):
                            if item.get("confidence") == "high":
                                high_count += 1
                            else:
                                low_count += 1

            print(f"  [verify] {sku}: verified {len(verified)} fields")
        else:
            print(f"  [verify] {sku}: no specs to verify")

    total_fields = high_count + low_count
    if total_fields > 0:
        pct = high_count / total_fields * 100
        print(f"\n[verify] Summary: {high_count}/{total_fields} fields high confidence ({pct:.1f}%)")
        print(f"[verify] {low_count} fields flagged as low confidence")
    else:
        print("\n[verify] No fields to verify")

    return records


# ── CLI test ───────────────────────────────────────────────────────────
if __name__ == "__main__":
    import json

    # Test case 1: span found in text → high
    specs1 = {
        "refresh_rate": {
            "value": 144,
            "source_span": "tần số quét 144Hz",
        },
        "panel_type": {
            "value": "IPS",
            "source_span": "Tấm nền IPS",
        },
    }
    text1 = "Tấm nền IPS cho góc nhìn rộng, tần số quét 144Hz mượt mà"
    result1 = _verify_dict_fields(specs1, text1)
    print("Test 1 (should be high):")
    print(json.dumps(result1, ensure_ascii=False, indent=2))

    # Test case 2: fabricated field → low (§5.5 Acceptance test)
    specs2 = {
        "resolution": {
            "value": "3840x2160",
            "source_span": "totally not in the text",
        },
    }
    text2 = "Màn hình độ phân giải cao cho trải nghiệm tuyệt vời"
    result2 = _verify_dict_fields(specs2, text2)
    print("\nTest 2 (fabricated → should be low):")
    print(json.dumps(result2, ensure_ascii=False, indent=2))
    assert result2["resolution"]["confidence"] == "low"
    assert result2["resolution"]["source_span"] is None
    print("✓ Acceptance: fabricated field correctly flagged low")

    # Test case 3: Vietnamese NFC normalisation
    specs3 = {
        "warranty_months": {
            "value": 36,
            "source_span": "bảo hành 36 tháng",
        },
    }
    text3 = "Sản phẩm được bảo hành 36 tháng chính hãng"
    result3 = _verify_dict_fields(specs3, text3)
    print("\nTest 3 (NFC test, should be high):")
    print(json.dumps(result3, ensure_ascii=False, indent=2))
