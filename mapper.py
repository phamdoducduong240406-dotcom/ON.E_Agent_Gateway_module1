"""
Module 1 — Mapper
Chuyển record nội bộ → JSON-LD Schema.org theo data contract mục 4.
Không gọi mạng.
"""

from __future__ import annotations

import csv
from pathlib import Path
from typing import Any

from config import RELATIONS_CSV_PATH
from schema import UNIT_CODES, TECHNICAL_FIELDS, POLICY_FIELDS


def _load_compat(path: str | Path) -> dict[str, list[str]]:
    """Load bảng compatibility từ CSV.
    Trả dict: sku → list[compatible_sku]."""
    compat: dict[str, list[str]] = {}
    path = Path(path)

    if not path.exists():
        print(f"  [mapper] WARNING: compat file not found: {path}")
        return compat

    with open(path, "r", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            sku_a = row.get("sku_a", "").strip()
            sku_b = row.get("sku_b", "").strip()
            if sku_a and sku_b:
                compat.setdefault(sku_a, []).append(sku_b)
                compat.setdefault(sku_b, []).append(sku_a)

    return compat


def _guess_unit_code(field_name: str, value: Any) -> str | None:
    """Suy đoán UN/CEFACT unit code từ tên field hoặc giá trị."""
    field_lower = field_name.lower()

    # Map field name → unit
    field_units = {
        "screen_size": "INH",
        "refresh_rate": "HTZ",
        "power": "WTT",
        "warranty_months": "MON",
        "return_days": "DAY",
    }

    if field_lower in field_units:
        return field_units[field_lower]

    # Try to find unit in value string
    if isinstance(value, str):
        value_lower = value.lower().strip()
        for unit_str, code in UNIT_CODES.items():
            if value_lower.endswith(unit_str):
                return code

    return None


def to_jsonld(
    record: dict[str, Any],
    compat_map: dict[str, list[str]] | None = None,
) -> dict[str, Any]:
    """Chuyển record nội bộ → JSON-LD Schema.org.

    Theo data contract mục 4:
    - @context, @type: "Product"
    - brand → {"@type": "Brand", "name": ...}
    - offers → {"@type": "Offer", ...}
    - additionalProperty → list PropertyValue với unitCode
    - policy → warranty, return, exclusions
    - compatible_with từ compat map
    - agent_text

    Args:
        record: Record đầy đủ (đã qua verify, compose)
        compat_map: Dict compat đã load, hoặc None

    Returns:
        Dict JSON-LD theo Schema.org
    """
    sku = record.get("sku", "unknown")
    specs = record.get("_extracted_specs", {})

    # ── Base structure ─────────────────────────────────────────────
    jsonld: dict[str, Any] = {
        "sku": sku,
        "@context": "https://schema.org",
        "@type": "Product",
        "name": record.get("name", ""),
        "brand": {
            "@type": "Brand",
            "name": record.get("brand", ""),
        },
        "category": record.get("category", ""),
    }

    # ── Offers ─────────────────────────────────────────────────────
    price = record.get("price")
    currency = record.get("currency", "AUD")
    stock = record.get("stock")

    if stock is not None and isinstance(stock, (int, float)):
        availability = (
            "https://schema.org/InStock" if stock > 0
            else "https://schema.org/OutOfStock"
        )
    else:
        availability = "https://schema.org/InStock"

    offers: dict[str, Any] = {
        "@type": "Offer",
        "priceCurrency": currency,
        "availability": availability,
    }
    if price is not None:
        offers["price"] = price
    if record.get("shipping_fee") is not None:
        offers["deliveryCharge"] = record["shipping_fee"]

    jsonld["offers"] = offers

    # ── Additional Properties (technical specs) ────────────────────
    additional_props: list[dict[str, Any]] = []

    for field_name in TECHNICAL_FIELDS:
        field_data = specs.get(field_name)
        if not field_data or not isinstance(field_data, dict):
            continue

        value = field_data.get("value")
        if value is None:
            continue

        prop: dict[str, Any] = {
            "@type": "PropertyValue",
            "name": field_name,
            "value": value,
            "confidence": field_data.get("confidence", "low"),
        }

        # Add source_span if available
        source_span = field_data.get("source_span")
        if source_span:
            prop["source_span"] = source_span

        # Add unit code
        unit_code = _guess_unit_code(field_name, value)
        if unit_code:
            prop["unitCode"] = unit_code

        additional_props.append(prop)

    if additional_props:
        jsonld["additionalProperty"] = additional_props

    # ── Policy ─────────────────────────────────────────────────────
    policy: dict[str, Any] = {}

    for field_name in POLICY_FIELDS:
        field_data = specs.get(field_name)
        if not field_data or not isinstance(field_data, dict):
            continue

        value = field_data.get("value")
        if value is None:
            continue

        if field_name == "exclusions":
            # Exclusions is a list
            if isinstance(value, list):
                policy["exclusions"] = value
            elif isinstance(value, str):
                # Split by common delimiters
                policy["exclusions"] = [
                    item.strip()
                    for item in value.replace(";", ",").split(",")
                    if item.strip()
                ]
        else:
            policy[field_name] = {
                "value": value,
                "confidence": field_data.get("confidence", "low"),
                "source_span": field_data.get("source_span"),
            }

    if policy:
        jsonld["policy"] = policy

    # ── Compatibility ──────────────────────────────────────────────
    if compat_map and sku in compat_map:
        jsonld["compatible_with"] = sorted(set(compat_map[sku]))

    # ── Agent text ─────────────────────────────────────────────────
    if "_agent_text" in record:
        jsonld["agent_text"] = record["_agent_text"]

    return jsonld


def map_all(
    records: list[dict[str, Any]],
    compat_path: str | Path | None = None,
) -> list[dict[str, Any]]:
    """Map tất cả records sang JSON-LD.

    Args:
        records: List records đã qua verify + compose
        compat_path: Đường dẫn compat.csv, mặc định từ config

    Returns:
        List các dict JSON-LD
    """
    if compat_path is None:
        compat_path = RELATIONS_CSV_PATH

    compat_map = _load_compat(compat_path)
    print(f"[mapper] Loaded {sum(len(v) for v in compat_map.values()) // 2} compat relations")

    products: list[dict[str, Any]] = []
    for record in records:
        jsonld = to_jsonld(record, compat_map)
        products.append(jsonld)

    print(f"[mapper] Mapped {len(products)} products to JSON-LD")
    return products


# ── CLI test ───────────────────────────────────────────────────────────
if __name__ == "__main__":
    import json
    from config import CATALOG_RAW_PATH
    from ingest import load_catalog

    records = load_catalog(CATALOG_RAW_PATH)

    # Fake some extracted specs for testing
    if records:
        records[0]["_extracted_specs"] = {
            "screen_size": {"value": "27 inch", "source_span": "27 inch", "confidence": "high"},
            "refresh_rate": {"value": 144, "source_span": "144Hz", "confidence": "high"},
            "panel_type": {"value": "IPS", "source_span": "Tấm nền IPS", "confidence": "high"},
            "warranty_months": {"value": 36, "source_span": "36 tháng", "confidence": "high"},
        }
        records[0]["_agent_text"] = "Test agent text"

        products = map_all(records[:3])
        print(json.dumps(products[0], ensure_ascii=False, indent=2))
