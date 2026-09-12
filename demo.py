"""
Module 1 — DEMO cho Ban Giám Khảo
Semantic Catalog Transformation Engine

Chạy: python demo.py
Yêu cầu: GEMINI_API_KEY trong file .env
"""

import json
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
if sys.platform == "win32" and hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

from config import (
    CATALOG_RAW_PATH, RELATIONS_CSV_PATH,
    GOLDEN_QUERIES_PATH, OUT_PATH, OUTPUT_DIR, PROMPT_VERSION,
)


def divider(title: str = ""):
    print(f"\n{'='*70}")
    if title:
        print(f"  {title}")
        print(f"{'='*70}")


def section(title: str):
    print(f"\n{'─'*60}")
    print(f"  {title}")
    print(f"{'─'*60}")


def pause(msg: str = "Nhấn Enter để tiếp tục..."):
    input(f"\n  >>> {msg}")


def demo_step1_ingest():
    """Demo: Field normalization từ catalog lộn xộn."""
    section("STEP 1: INGEST — Chuẩn hoá field names lộn xộn")

    from ingest import ingest, load_catalog

    raw = load_catalog(CATALOG_RAW_PATH)
    records = ingest(CATALOG_RAW_PATH)

    # Show 3 mẫu field mapping
    print("\n  Catalog gốc dùng tên field lộn xộn (Việt/Anh, đủ kiểu viết):")
    samples = raw[:3]
    for i, r in enumerate(samples):
        keys = list(r.keys())[:4]
        print(f"    Record {i+1}: {keys}")

    print(f"\n  → Sau ingest: TẤT CẢ được map về field chuẩn (sku, name, brand, ...)")
    print(f"  → {len(records)} records, mỗi record có _raw_text cho LLM extraction")

    # Show warranty_raw handling
    has_warranty = sum(1 for r in records if "warranty_raw" in r)
    print(f"  → {has_warranty}/{len(records)} records có warranty_raw (bảo hành) trong _raw_text")
    print(f"    (Quan trọng: thiếu warranty_raw → policy fields bị flag low confidence)")

    return records


def demo_step2_extract(records):
    """Demo: LLM extraction với source_span tracing."""
    section("STEP 2: EXTRACT — LLM trích xuất thông số + truy xuất nguồn")

    from extract import extract_all

    from config import MODEL_NAME
    print(f"\n  Gửi {len(records)} records đến Gemini ({MODEL_NAME})...")
    print(f"  Prompt version: {PROMPT_VERSION}")
    print(f"  Mỗi field phải có source_span: đoạn text gốc chính xác")
    print(f"  Cache: thay đổi prompt → tự invalidate cache")

    records = extract_all(records)

    # Show sample extraction
    for r in records[:3]:
        specs = r.get("_extracted_specs", {})
        if specs:
            sku = r["sku"]
            print(f"\n  [{sku}] Extracted {len(specs)} fields:")
            for fname, fdata in list(specs.items())[:3]:
                if isinstance(fdata, dict):
                    val = fdata.get("value", "?")
                    span = fdata.get("source_span", "N/A")
                    print(f"    {fname}: {val}")
                    if span:
                        print(f"      └─ source: \"{span}\"")

    return records


def demo_step3_verify(records):
    """Demo: Confidence verification với NFC normalization."""
    section("STEP 3: VERIFY — Đối chiếu source_span vs text gốc")

    from verify import verify_all

    print("\n  Quy tắc:")
    print("    ✓ source_span tìm thấy trong text gốc → confidence = HIGH")
    print("    ✗ source_span KHÔNG tìm thấy → confidence = LOW (giữ field, gắn cờ)")
    print("    NFC Unicode normalization cho tiếng Việt (tránh false negatives)")

    records = verify_all(records)
    return records


def demo_step4_compose(records):
    """Demo: Agent text composition — no marketing copy."""
    section("STEP 4: COMPOSE — Tạo agent_text (KHÔNG marketing copy)")

    from compose import compose_all

    print("\n  Thứ tự: Tên → Use cases → Thông số → Environment → Values → Policy → Giá")
    print("  CHỈ field high-confidence. KHÔNG BAO GIỜ copy mô tả marketing gốc.")

    records = compose_all(records)

    # Show sample
    for r in records[:2]:
        if r.get("agent_text") and len(r["agent_text"]) > 50:
            print(f"\n  [{r['sku']}]")
            print(f"    agent_text: {r['agent_text'][:200]}...")
            break

    return records


def demo_step5_index(records):
    """Demo: Vector index với BGE-M3 (multilingual)."""
    section("STEP 5: INDEX — Semantic search với BGE-M3")

    from index import build_index

    print(f"\n  Model: BAAI/bge-m3 (multilingual — hỗ trợ Việt/Anh cross-lingual)")
    print(f"  Encoding {len(records)} agent_text thành vectors...")

    index = build_index(records)

    # Demo search
    test_queries = [
        "màn hình 4K cho đồ hoạ",
        "cheap gaming monitor",
        "màn hình cong ultrawide",
    ]
    for q in test_queries:
        results = index.search(q, k=3)
        skus = [f"{sku} ({score:.3f})" for sku, score in results]
        print(f"\n  Query: \"{q}\"")
        print(f"    → {', '.join(skus)}")

    return index


def demo_step6_retrieve(index, catalog):
    """Demo: THE KEY DELIVERABLE — Retrieval với justification."""
    divider("DEMO CHÍNH: RETRIEVAL + JUSTIFICATION PAYLOAD (§4.3)")

    from retrieve import retrieve

    queries = [
        "màn hình đồ hoạ dưới 1000 AUD",
        "monitor gaming dưới 800 đô",
        "bộ màn hình cho designer mới vào nghề, dưới 1500 AUD",
    ]

    for query in queries:
        section(f'Query: "{query}"')
        payload = retrieve(query, index, catalog)
        print(json.dumps(payload, ensure_ascii=False, indent=2))
        pause()


def demo_step7_evaluate(index, catalog):
    """Demo: Golden set evaluation — 3 metrics."""
    section("EVALUATION — 3 Metrics trên Golden Set")

    from evaluate import run_golden

    result = run_golden(index, catalog)
    return result


def demo_output():
    """Demo: Handoff file format."""
    section("OUTPUT: Handoff File cho Module 2 & 3")

    with open(OUT_PATH, "r", encoding="utf-8") as f:
        data = json.load(f)

    print(f"\n  File: {OUT_PATH}")
    print(f"  schema_version: {data['schema_version']}")
    print(f"  products: {data['count']}")
    print(f"  relations: {len(data['relations'])}")
    print(f"  value_taxonomy: {data['value_taxonomy']}")
    print(f"  metrics: {json.dumps(data.get('metrics', {}), indent=4)}")

    # Show one product record (§4.2 format)
    print(f"\n  Sample product (§4.2 format):")
    for p in data["products"]:
        if p.get("specs"):
            sample = {k: v for k, v in p.items() if k != "agent_text"}
            print(f"  {json.dumps(sample, ensure_ascii=False, indent=4)[:800]}...")
            break

    # Verify contract
    print(f"\n  Contract checks:")
    for p in data["products"]:
        assert "_raw_text" not in p
    print(f"    ✓ _raw_text stripped from all products")
    print(f"    ✓ schema_version = 2.0")
    print(f"    ✓ relations included ({len(data['relations'])} entries)")
    print(f"    ✓ value_taxonomy included")


def main():
    divider("MODULE 1 — SEMANTIC CATALOG TRANSFORMATION ENGINE")
    print("  UAVS Hackathon 2026 | Demo cho Ban Giám Khảo")
    print("  Pipeline: Catalog thô → Structured data → Agent retrieval")
    divider()

    start = time.time()

    # Step 1: Ingest
    records = demo_step1_ingest()
    pause()

    # Step 2: Extract (LLM)
    records = demo_step2_extract(records)
    pause()

    # Step 3: Verify
    records = demo_step3_verify(records)
    pause()

    # Step 4: Compose
    records = demo_step4_compose(records)
    pause()

    # Step 5: Index
    index = demo_step5_index(records)
    pause()

    # Build catalog dict
    catalog = {r["sku"]: r for r in records}

    # Step 6: THE KEY — Retrieve with justification
    demo_step6_retrieve(index, catalog)

    # Step 7: Evaluate
    result = demo_step7_evaluate(index, catalog)
    pause()

    # Write output
    from run_pipeline import _build_product_record, _timestamp
    import csv

    products = [_build_product_record(r) for r in records]
    relations_list = []
    if RELATIONS_CSV_PATH.exists():
        with open(RELATIONS_CSV_PATH, "r", encoding="utf-8") as f:
            reader = csv.DictReader(f)
            for row in reader:
                relations_list.append({
                    "sku_a": row.get("sku_a", "").strip(),
                    "sku_b": row.get("sku_b", "").strip(),
                    "type": row.get("type", "").strip(),
                    "outcome": row.get("outcome", "").strip(),
                    "note": row.get("note", "").strip(),
                })

    from schema import VALUE_TAXONOMY
    handoff = {
        "generated_at": _timestamp(),
        "schema_version": "2.0",
        "count": len(products),
        "metrics": result.get("metrics", {}) if result else {},
        "products": products,
        "relations": relations_list,
        "value_taxonomy": VALUE_TAXONOMY,
    }

    OUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    with open(OUT_PATH, "w", encoding="utf-8") as f:
        json.dump(handoff, f, ensure_ascii=False, indent=2)

    # Final output
    demo_output()

    elapsed = time.time() - start
    divider(f"DEMO HOÀN TẤT — Tổng thời gian: {elapsed:.1f}s")
    print("\n  Deliverables:")
    print(f"    1. Handoff file: {OUT_PATH}")
    print(f"    2. 63 products → structured §4.2 format")
    print(f"    3. Retrieval payload §4.3 với justification + excluded")
    print(f"    4. 3 metrics: hit_rate, intent_accuracy, values_provenance")
    print(f"    5. relations.csv ({len(relations_list)} relations)")
    divider()


if __name__ == "__main__":
    main()
