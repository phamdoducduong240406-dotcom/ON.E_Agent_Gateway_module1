"""
Module 1 — Schema Definition
Enums (§4.1), FIELD_MAP, UNIT_CODES, field groups, Pydantic models.
"""

from __future__ import annotations
from typing import Optional
from pydantic import BaseModel, Field


# ── §4.1 Enums (closed sets — never let the model invent labels) ──────

VALUE_TAXONOMY = [
    "sustainable_materials", "recyclable_packaging", "repairability",
    "long_warranty", "local_manufacturing", "ethical_sourcing",
    "energy_efficiency", "carbon_disclosure",
]

USE_CASES = [
    "podcasting", "streaming", "vocal_recording", "instrument_recording",
    "field_recording", "video_calls", "gaming",
    # Monitor domain additions
    "office_work", "graphic_design", "video_editing", "programming",
]

SKILL_LEVELS = ["beginner", "intermediate", "pro"]

ENVIRONMENTS = ["home_untreated", "studio", "mobile", "office"]

RELATION_TYPES = ["required_with", "completes_outcome", "upgrade_of", "alternative_to"]

UNIT_CODES = {
    "hz": "HTZ", "khz": "KHZ",
    "inch": "INH", "in": "INH", "\"": "INH",
    "watt": "WTT", "w": "WTT", "watts": "WTT",
    "mm": "MMT",
    # Time
    "tháng": "MON", "thang": "MON", "months": "MON", "month": "MON",
    "ngày": "DAY", "ngay": "DAY", "days": "DAY", "day": "DAY",
    "năm": "ANN", "nam": "ANN", "year": "ANN", "years": "ANN",
    # Weight
    "kg": "KGM", "g": "GRM",
}


# ── Standard Fields ────────────────────────────────────────────────────
# Nhóm 1: Định danh (lấy trực tiếp từ PIM)
IDENTITY_FIELDS = ["sku", "name", "brand", "category"]

# Nhóm 2: Giao dịch (lấy trực tiếp)
TRANSACTION_FIELDS = ["price", "currency", "stock", "shipping_fee"]

# Nhóm 3: Kỹ thuật (cần LLM extract)
TECHNICAL_FIELDS = [
    # Audio domain (spec)
    "connection_type", "polar_pattern", "freq_response",
    "phantom_power", "sample_rate",
    # Monitor domain (existing catalog)
    "screen_size", "panel_type", "refresh_rate",
    "resolution", "ports", "power",
]

# Nhóm 4: Chính sách (cần LLM extract)
POLICY_FIELDS = [
    "warranty_months", "warranty_scope",
    "return_days", "exclusions",
]

# Nhóm 5: Outcomes (cần LLM extract)
OUTCOME_FIELDS = ["use_cases", "skill_level", "environment"]

# Tổng hợp
DIRECT_FIELDS = IDENTITY_FIELDS + TRANSACTION_FIELDS
LLM_FIELDS = TECHNICAL_FIELDS + POLICY_FIELDS + OUTCOME_FIELDS


# ── FIELD_MAP ──────────────────────────────────────────────────────────
# Mapping tên field lộn xộn trong catalog thô → tên field chuẩn.
FIELD_MAP = {
    # ── §5.2 Required mappings ─────────────────────────────────────
    "item_code": "sku",
    "product_id": "sku",
    "sku_no": "sku",
    "title": "name",
    "product_name": "name",
    "mfr": "brand",
    "manufacturer": "brand",
    "long_desc": "description",
    "desc_html": "description",
    "warranty_blob": "warranty_raw",

    # ── Vietnamese variants ────────────────────────────────────────
    "tên sản phẩm": "name",
    "ten san pham": "name",
    "tên": "name",
    "ten": "name",
    "product name": "name",
    "tên sp": "name",
    "thương hiệu": "brand",
    "thuong hieu": "brand",
    "hãng": "brand",
    "hang": "brand",
    "brand_name": "brand",
    "nhãn hiệu": "brand",
    "mã sản phẩm": "sku",
    "ma san pham": "sku",
    "mã sp": "sku",
    "ma sp": "sku",
    "product_code": "sku",
    "danh mục": "category",
    "danh_muc": "category",
    "loại": "category",
    "loai": "category",
    "nhóm hàng": "category",
    "nhom hang": "category",
    "product_type": "category",

    # Price / transaction
    "giá": "price",
    "gia": "price",
    "giá bán": "price",
    "gia ban": "price",
    "đơn giá": "price",
    "don gia": "price",
    "price_aud": "price",
    "selling_price": "price",
    "đơn vị tiền": "currency",
    "don vi tien": "currency",
    "tồn kho": "stock",
    "ton kho": "stock",
    "inventory": "stock",
    "qty": "stock",
    "quantity": "stock",
    "số lượng": "stock",
    "phí vận chuyển": "shipping_fee",
    "phi van chuyen": "shipping_fee",
    "ship_fee": "shipping_fee",
    "shipping": "shipping_fee",
    "phí ship": "shipping_fee",

    # Technical specs
    "kích thước màn hình": "screen_size",
    "kich thuoc man hinh": "screen_size",
    "kích thước": "screen_size",
    "kich thuoc": "screen_size",
    "screen": "screen_size",
    "display_size": "screen_size",
    "màn hình": "screen_size",
    "man hinh": "screen_size",
    "loại tấm nền": "panel_type",
    "loai tam nen": "panel_type",
    "tấm nền": "panel_type",
    "tam nen": "panel_type",
    "panel": "panel_type",
    "display_type": "panel_type",
    "công nghệ màn hình": "panel_type",
    "tần số quét": "refresh_rate",
    "tan so quet": "refresh_rate",
    "tần số": "refresh_rate",
    "tan so": "refresh_rate",
    "hz": "refresh_rate",
    "refresh": "refresh_rate",
    "độ phân giải": "resolution",
    "do phan giai": "resolution",
    "phân giải": "resolution",
    "phan giai": "resolution",
    "cổng kết nối": "ports",
    "cong ket noi": "ports",
    "cổng": "ports",
    "cong": "ports",
    "kết nối": "ports",
    "ket noi": "ports",
    "connectivity": "ports",
    "interfaces": "ports",
    "i/o": "ports",
    "công suất": "power",
    "cong suat": "power",
    "nguồn": "power",
    "nguon": "power",
    "power_consumption": "power",
    "watt": "power",

    # Policy
    "bảo hành": "warranty_months",
    "bao hanh": "warranty_months",
    "thời gian bảo hành": "warranty_months",
    "warranty": "warranty_months",
    "phạm vi bảo hành": "warranty_scope",
    "pham vi bao hanh": "warranty_scope",
    "điều kiện bảo hành": "warranty_scope",
    "warranty_coverage": "warranty_scope",
    "đổi trả": "return_days",
    "doi tra": "return_days",
    "thời gian đổi trả": "return_days",
    "return_policy": "return_days",
    "return": "return_days",
    "ngoại trừ": "exclusions",
    "ngoai tru": "exclusions",
    "không bảo hành": "exclusions",
    "khong bao hanh": "exclusions",
    "exclusion": "exclusions",
    "loại trừ": "exclusions",

    # Description / text blobs
    "mô tả": "description",
    "mo ta": "description",
    "mô tả sản phẩm": "description",
    "mô tả chi tiết": "description",
    "chi tiết": "description",
    "chi tiet": "description",
    "product_description": "description",
    "desc": "description",
    "detail": "description",
    "thông tin chi tiết": "description",
    "thong tin chi tiet": "description",
    "thông số kỹ thuật": "specs_text",
    "thong so ky thuat": "specs_text",
    "thông số": "specs_text",
    "specifications": "specs_text",
    "specs": "specs_text",
    "chính sách": "warranty_raw",
    "chinh sach": "warranty_raw",
    "chính sách bảo hành": "warranty_raw",
    "policy": "warranty_raw",
    "policy_text": "warranty_raw",
}


# ── Pydantic Models for Structured Output ──────────────────────────────
class ExtractedField(BaseModel):
    """Một field đã extract, kèm source_span và note."""
    value: Optional[str | int | float | list[str]] = None
    source_span: Optional[str] = None
    note: Optional[str] = None


class ExtractedSpecs(BaseModel):
    """Schema cho structured output từ LLM extraction."""
    # Technical fields — audio domain
    connection_type: Optional[ExtractedField] = None
    polar_pattern: Optional[ExtractedField] = None
    freq_response: Optional[ExtractedField] = None
    phantom_power: Optional[ExtractedField] = None
    sample_rate: Optional[ExtractedField] = None
    # Technical fields — monitor domain
    screen_size: Optional[ExtractedField] = None
    panel_type: Optional[ExtractedField] = None
    refresh_rate: Optional[ExtractedField] = None
    resolution: Optional[ExtractedField] = None
    ports: Optional[ExtractedField] = None
    power: Optional[ExtractedField] = None
    # Policy fields
    warranty_months: Optional[ExtractedField] = None
    warranty_scope: Optional[ExtractedField] = None
    return_days: Optional[ExtractedField] = None
    exclusions: Optional[ExtractedField] = None
    # Outcome fields
    use_cases: Optional[ExtractedField] = None
    skill_level: Optional[ExtractedField] = None
    environment: Optional[ExtractedField] = None
    # Values
    values: Optional[list[ExtractedField]] = None
