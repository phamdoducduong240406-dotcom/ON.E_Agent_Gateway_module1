"""
Module 1 — Run Pipeline
§5.11: ingest → extract_all → verify → compose → index.build → evaluate → write handoff.

Handoff file: schema_version "2.0", products (§4.2), relations, value_taxonomy.
Strip _raw_text from products before writing.
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

# Add module1 to path
sys.path.insert(0, str(Path(__file__).resolve().parent))
if sys.platform == "win32" and hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

from config import (
    CATALOG_RAW_PATH,
    GOLDEN_QUERIES_PATH,
    RELATIONS_CSV_PATH,
    OUT_PATH,
    OUTPUT_DIR,
    OUTPUT_PATH,
    PROMPT_VERSION,
)
from schema import VALUE_TAXONOMY, RELATION_TYPES


def _timestamp() -> str:
    """ISO 8601 timestamp."""
    return datetime.now(timezone.utc).isoformat()


def _elapsed(start: float) -> str:
    """Format elapsed time."""
    secs = time.time() - start
    if secs < 60:
        return f"{secs:.1f}s"
    mins = int(secs // 60)
    remaining = secs % 60
    return f"{mins}m {remaining:.1f}s"


def _build_product_record(rec: dict[str, Any]) -> dict[str, Any]:
    """Build §4.2 standardized product record from internal record.

    Strips _raw_text and internal fields.
    """
    specs = rec.get("_extracted_specs", {})

    # Build specs list
    spec_list: list[dict[str, Any]] = []
    from schema import TECHNICAL_FIELDS
    for field_name in TECHNICAL_FIELDS:
        field_data = specs.get(field_name)
        if field_data and isinstance(field_data, dict) and field_data.get("value") is not None:
            spec_list.append({
                "name": field_name,
                "value": field_data["value"],
                "unit": None,
                "confidence": field_data.get("confidence", "low"),
                "source_span": field_data.get("source_span"),
            })

    # Build policy
    policy: dict[str, Any] = {}
    from schema import POLICY_FIELDS
    for field_name in POLICY_FIELDS:
        field_data = specs.get(field_name)
        if field_data and isinstance(field_data, dict) and field_data.get("value") is not None:
            if field_name == "exclusions":
                policy["exclusions"] = field_data["value"] if isinstance(field_data["value"], list) else [field_data["value"]]
            else:
                policy[field_name] = {
                    "value": field_data["value"],
                    "confidence": field_data.get("confidence", "low"),
                    "source_span": field_data.get("source_span"),
                }

    # Build outcomes
    outcomes: dict[str, Any] = {}
    from schema import OUTCOME_FIELDS
    for field_name in OUTCOME_FIELDS:
        field_data = specs.get(field_name)
        if field_data and isinstance(field_data, dict) and field_data.get("value") is not None:
            outcomes[field_name] = {
                "value": field_data["value"],
                "confidence": field_data.get("confidence", "low"),
                "source_span": field_data.get("source_span"),
            }
            if field_data.get("note"):
                outcomes[field_name]["note"] = field_data["note"]

    # Build values
    value_list: list[dict[str, Any]] = []
    raw_values = specs.get("values", [])
    if isinstance(raw_values, list):
        for v in raw_values:
            if isinstance(v, dict) and v.get("value"):
                value_list.append({
                    "claim": v.get("claim") or v.get("value", ""),
                    "confidence": v.get("confidence", "low"),
                    "source_span": v.get("source_span"),
                })

    # Assemble §4.2 product record
    product: dict[str, Any] = {
        "sku": rec.get("sku", ""),
        "name": rec.get("name", ""),
        "brand": rec.get("brand", ""),
        "category": rec.get("category", ""),
        "price": rec.get("price"),
        "currency": rec.get("currency", "AUD"),
        "stock": rec.get("stock"),
        "specs": spec_list,
        "policy": policy,
        "outcomes": outcomes,
        "values": value_list,
        "agent_text": rec.get("agent_text", ""),
        # _raw_text is STRIPPED — internal only
    }

    return product


def run_pipeline(
    skip_extract: bool = False,
    skip_eval: bool = False,
) -> None:
    """Chạy toàn bộ pipeline.

    §5.11 Order: ingest → extract_all → verify → compose → index.build → evaluate → write handoff.

    Args:
        skip_extract: Bỏ qua bước extract (dùng cache)
        skip_eval: Bỏ qua bước evaluate
    """
    pipeline_start = time.time()

    print("=" * 70)
    print("  MODULE 1 — SEMANTIC CATALOG TRANSFORMATION ENGINE")
    print(f"  Started at: {_timestamp()}")
    print(f"  Prompt version: {PROMPT_VERSION}")
    print("=" * 70)

    # ── Step 1: Ingest ─────────────────────────────────────────────
    print("\n" + "─" * 50)
    print("  STEP 1/6: INGEST")
    print("─" * 50)
    step_start = time.time()

    from ingest import ingest
    records = ingest(CATALOG_RAW_PATH)
    print(f"  ⏱ {_elapsed(step_start)}")

    if not records:
        print("ERROR: No records loaded. Aborting.")
        return

    # ── Step 2: Extract ────────────────────────────────────────────
    print("\n" + "─" * 50)
    print("  STEP 2/6: EXTRACT (LLM)")
    print("─" * 50)
    step_start = time.time()

    if skip_extract:
        print("  [SKIPPED] Using cache")
        from extract import _read_cache
        for record in records:
            sku = record.get("sku", "")
            raw_text = record.get("_raw_text", "")
            cached = _read_cache(sku, raw_text)
            record["_extracted_specs"] = cached or {}
    else:
        from extract import extract_all
        records = extract_all(records)

    print(f"  ⏱ {_elapsed(step_start)}")

    # ── Step 3: Verify ─────────────────────────────────────────────
    print("\n" + "─" * 50)
    print("  STEP 3/6: VERIFY")
    print("─" * 50)
    step_start = time.time()

    from verify import verify_all
    records = verify_all(records)
    print(f"  ⏱ {_elapsed(step_start)}")

    # ── Step 4: Compose ────────────────────────────────────────────
    print("\n" + "─" * 50)
    print("  STEP 4/6: COMPOSE")
    print("─" * 50)
    step_start = time.time()

    from compose import compose_all
    records = compose_all(records)
    print(f"  ⏱ {_elapsed(step_start)}")

    # ── Step 5: Index ──────────────────────────────────────────────
    print("\n" + "─" * 50)
    print("  STEP 5/6: INDEX (Embedding)")
    print("─" * 50)
    step_start = time.time()

    from index import build_index
    search_index = build_index(records)
    print(f"  ⏱ {_elapsed(step_start)}")

    # ── Build catalog dict for retrieval ───────────────────────────
    catalog: dict[str, dict[str, Any]] = {}
    for rec in records:
        catalog[rec.get("sku", "")] = rec

    # ── Step 6: Evaluate ───────────────────────────────────────────
    eval_result = None
    if not skip_eval:
        print("\n" + "─" * 50)
        print("  STEP 6/6: EVALUATE")
        print("─" * 50)
        step_start = time.time()

        from evaluate import run_golden
        eval_result = run_golden(search_index, catalog)
        print(f"  ⏱ {_elapsed(step_start)}")
    else:
        print("\n  STEP 6/6: EVALUATE [SKIPPED]")

    # ── Output: Handoff file ───────────────────────────────────────
    print("\n" + "─" * 50)
    print("  OUTPUT: Generating handoff file")
    print("─" * 50)

    # Build §4.2 product records (strip _raw_text)
    products = [_build_product_record(rec) for rec in records]

    # Load relations for handoff
    import csv
    relations_list: list[dict[str, str]] = []
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

    # Build metrics
    metrics: dict[str, Any] = {}
    if eval_result:
        metrics = eval_result.get("metrics", {})

    # §5.11 Handoff file structure
    handoff = {
        "generated_at": _timestamp(),
        "schema_version": "2.0",
        "count": len(products),
        "metrics": metrics,
        "products": products,
        "relations": relations_list,
        "value_taxonomy": VALUE_TAXONOMY,
    }

    # Write handoff file
    OUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    with open(OUT_PATH, "w", encoding="utf-8") as f:
        json.dump(handoff, f, ensure_ascii=False, indent=2)
    print(f"  ✓ Written to: {OUT_PATH}")

    print(f"  ✓ Products: {len(products)}")
    print(f"  ✓ Relations: {len(relations_list)}")
    print(f"  ✓ Schema version: 2.0")

    if eval_result:
        m = eval_result.get("metrics", {})
        print(f"  ✓ retrieval_hit_rate_top3: {m.get('retrieval_hit_rate_top3', 'N/A')}")
        if m.get("intent_accuracy") is not None:
            print(f"  ✓ intent_accuracy: {m.get('intent_accuracy')}")
        print(f"  ✓ values_provenance_rate: {m.get('values_provenance_rate', 'N/A')}")

    # Verify _raw_text is stripped
    for p in products:
        assert "_raw_text" not in p, f"_raw_text not stripped from {p.get('sku')}"
    print("  ✓ _raw_text stripped from all products")

    # ── Summary ────────────────────────────────────────────────────
    print("\n" + "=" * 70)
    print(f"  PIPELINE COMPLETE — Total time: {_elapsed(pipeline_start)}")
    print("=" * 70)

    # Save evaluation report
    if eval_result:
        eval_report_path = OUTPUT_DIR / "evaluation_report.json"
        with open(eval_report_path, "w", encoding="utf-8") as f:
            json.dump(eval_result, f, ensure_ascii=False, indent=2)
        print(f"\n  Evaluation report: {eval_report_path}")


def main():
    parser = argparse.ArgumentParser(
        description="Module 1 — Semantic Catalog Transformation Engine Pipeline"
    )
    parser.add_argument(
        "--skip-extract",
        action="store_true",
        help="Skip LLM extraction (use cache)",
    )
    parser.add_argument(
        "--skip-eval",
        action="store_true",
        help="Skip golden set evaluation",
    )

    args = parser.parse_args()

    run_pipeline(
        skip_extract=args.skip_extract,
        skip_eval=args.skip_eval,
    )


if __name__ == "__main__":
    main()
