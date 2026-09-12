"""
Module 1 — Compose
Ghép agent_text từ field high confidence theo thứ tự §5.6.
Không gọi mạng.

TUYỆT ĐỐI KHÔNG ghép mô tả marketing gốc.
"immersive", "buttery-smooth" → noise → defeats the whole pipeline.
"""

from __future__ import annotations

from typing import Any

from schema import TECHNICAL_FIELDS, POLICY_FIELDS, OUTCOME_FIELDS, VALUE_TAXONOMY


def _format_field_value(field_name: str, field_data: dict[str, Any]) -> str | None:
    """Format một field thành dạng đọc được."""
    value = field_data.get("value")
    if value is None:
        return None

    # Map field name to readable label
    labels = {
        # Technical — monitor
        "screen_size": "Kích thước",
        "panel_type": "Tấm nền",
        "refresh_rate": "Tần số quét",
        "resolution": "Độ phân giải",
        "ports": "Cổng kết nối",
        "power": "Công suất",
        # Technical — audio
        "connection_type": "Kết nối",
        "polar_pattern": "Polar pattern",
        "freq_response": "Tần số đáp ứng",
        "phantom_power": "Phantom power",
        "sample_rate": "Sample rate",
        # Policy
        "warranty_months": "Bảo hành",
        "warranty_scope": "Phạm vi bảo hành",
        "return_days": "Đổi trả",
        "exclusions": "Loại trừ",
        # Outcomes
        "use_cases": "Phù hợp cho",
        "skill_level": "Trình độ",
        "environment": "Môi trường",
    }

    label = labels.get(field_name, field_name)

    # Format value
    if isinstance(value, list):
        val_str = ", ".join(str(v) for v in value)
    else:
        val_str = str(value)

    # Add units where appropriate
    unit_suffixes = {
        "refresh_rate": "Hz",
        "power": "W",
        "warranty_months": " tháng",
        "return_days": " ngày",
    }

    suffix = unit_suffixes.get(field_name, "")
    if suffix and not val_str.lower().endswith(suffix.lower().strip()):
        val_str += suffix

    return f"{label}: {val_str}"


def _get_high_confidence_fields(
    specs: dict[str, Any],
    field_names: list[str],
) -> list[str]:
    """Lấy formatted strings cho các field high confidence.

    §5.6 Rule 1: Include ONLY confidence == "high" entries.
    """
    parts: list[str] = []
    for field_name in field_names:
        field_data = specs.get(field_name)
        if not field_data or not isinstance(field_data, dict):
            continue
        if field_data.get("confidence") != "high":
            continue
        formatted = _format_field_value(field_name, field_data)
        if formatted:
            parts.append(formatted)
    return parts


def build_agent_text(rec: dict[str, Any]) -> str:
    """Ghép agent_text theo thứ tự §5.6:
    1. name
    2. use_cases + skill_level (outcomes trước specs — §5.6 Rule 3)
    3. specs (high confidence only)
    4. environment
    5. values (high confidence only)
    6. policy
    7. price + stock

    §5.6 Rule 2: NEVER include original marketing description.

    Args:
        rec: Record đã qua verify

    Returns:
        Chuỗi agent_text
    """
    specs = rec.get("_extracted_specs", {})
    parts: list[str] = []

    # ── 1. Name ────────────────────────────────────────────────────
    name = rec.get("name", "")
    brand = rec.get("brand", "")
    category = rec.get("category", "")
    if name:
        name_parts = [name]
        if brand:
            name_parts.append(f"({brand})")
        if category:
            name_parts.append(f"- {category}")
        parts.append(" ".join(name_parts))

    # ── 2. Outcomes first: use_cases + skill_level ─────────────────
    # §5.6 Rule 3: Outcomes before specs — agent queries are phrased
    # in purpose language, not spec language.
    outcome_parts: list[str] = []
    for field_name in ["use_cases", "skill_level"]:
        field_data = specs.get(field_name)
        if field_data and isinstance(field_data, dict):
            if field_data.get("confidence") == "high":
                formatted = _format_field_value(field_name, field_data)
                if formatted:
                    outcome_parts.append(formatted)
    if outcome_parts:
        parts.append(". ".join(outcome_parts) + ".")

    # ── 3. Technical specs ─────────────────────────────────────────
    tech_parts = _get_high_confidence_fields(specs, TECHNICAL_FIELDS)
    if tech_parts:
        parts.append("Thông số: " + ". ".join(tech_parts) + ".")

    # ── 4. Environment ─────────────────────────────────────────────
    env_data = specs.get("environment")
    if env_data and isinstance(env_data, dict) and env_data.get("confidence") == "high":
        formatted = _format_field_value("environment", env_data)
        if formatted:
            parts.append(formatted + ".")

    # ── 5. Values (high confidence only) ───────────────────────────
    values = specs.get("values", [])
    if isinstance(values, list):
        value_parts = []
        for v in values:
            if isinstance(v, dict) and v.get("confidence") == "high":
                claim = v.get("claim") or v.get("value", "")
                if claim:
                    value_parts.append(claim)
        if value_parts:
            parts.append("Giá trị: " + ", ".join(value_parts) + ".")

    # ── 6. Policy ──────────────────────────────────────────────────
    policy_parts = _get_high_confidence_fields(specs, POLICY_FIELDS)
    if policy_parts:
        parts.append("Chính sách: " + ". ".join(policy_parts) + ".")

    # ── 7. Price + stock ───────────────────────────────────────────
    price = rec.get("price")
    currency = rec.get("currency", "AUD")
    stock = rec.get("stock")

    price_parts: list[str] = []
    if price is not None:
        price_parts.append(f"Giá: {price} {currency}")
    if stock is not None:
        status = "Còn hàng" if stock > 0 else "Hết hàng"
        price_parts.append(status)
    if price_parts:
        parts.append(". ".join(price_parts) + ".")

    return " ".join(parts)


def compose_all(records: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Compose agent_text cho tất cả records.

    Args:
        records: List records đã qua verify

    Returns:
        Cùng list records, mỗi record thêm 'agent_text'
    """
    for record in records:
        text = build_agent_text(record)
        record["agent_text"] = text

    # Stats
    avg_len = sum(len(r.get("agent_text", "")) for r in records) / max(len(records), 1)
    print(f"[compose] Composed agent_text for {len(records)} records")
    print(f"[compose] Average length: {avg_len:.0f} chars")

    return records


# ── CLI test ───────────────────────────────────────────────────────────
if __name__ == "__main__":
    from config import CATALOG_RAW_PATH
    from ingest import ingest

    records = ingest(CATALOG_RAW_PATH)

    # Fake extracted specs
    if records:
        records[0]["_extracted_specs"] = {
            "screen_size": {"value": "27 inch", "source_span": "27 inch", "confidence": "high"},
            "panel_type": {"value": "IPS", "source_span": "Tấm nền IPS", "confidence": "high"},
            "refresh_rate": {"value": 144, "source_span": "144Hz", "confidence": "high"},
            "resolution": {"value": "3840x2160", "source_span": "3840x2160", "confidence": "high"},
            "ports": {"value": "2x HDMI 2.1, 1x DisplayPort 1.4, 1x USB-C 65W", "source_span": "2x HDMI 2.1, 1x DisplayPort 1.4 và 1x USB-C", "confidence": "high"},
            "power": {"value": "45W", "source_span": "45W", "confidence": "high"},
            "warranty_months": {"value": 36, "source_span": "36 tháng", "confidence": "high"},
            "return_days": {"value": 14, "source_span": "14 ngày", "confidence": "high"},
            "exclusions": {"value": ["rơi vỡ", "vào nước", "tự ý tháo máy"], "source_span": None, "confidence": "low"},
            "use_cases": {"value": ["office_work", "graphic_design"], "source_span": None, "confidence": "low"},
        }

        text = build_agent_text(records[0])
        print("Agent text:")
        print(text)

        # §5.6 Acceptance: no substring > 8 words from description in agent_text
        desc = records[0].get("description", "")
        if desc:
            words = desc.split()
            for i in range(len(words) - 8):
                substr = " ".join(words[i:i+9])
                assert substr not in text, f"Marketing copy leaked: '{substr}'"
            print("\n✓ Acceptance: no marketing copy leaked into agent_text")
