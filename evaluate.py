"""
Module 1 — Evaluate
§5.10: Chạy golden set, tính 3 metrics:
- retrieval_hit_rate_top3
- intent_accuracy (bundle contains expected roles)
- values_provenance_rate (share of value claims with non-null source_span)
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from config import GOLDEN_QUERIES_PATH, TOP_K_RETURN


def _compute_values_provenance(catalog: dict[str, dict[str, Any]]) -> float:
    """Tính values_provenance_rate: share of value claims with non-null source_span.

    Args:
        catalog: Dict sku → record

    Returns:
        Rate from 0.0 to 1.0
    """
    total_claims = 0
    sourced_claims = 0

    for sku, rec in catalog.items():
        specs = rec.get("_extracted_specs", {})
        values = specs.get("values", [])
        if isinstance(values, list):
            for v in values:
                if isinstance(v, dict) and v.get("value"):
                    total_claims += 1
                    if v.get("source_span"):
                        sourced_claims += 1

    if total_claims == 0:
        return 1.0  # No claims = vacuously true
    return sourced_claims / total_claims


def run_golden(
    index: Any,  # VectorIndex
    catalog: dict[str, dict[str, Any]],
    golden: list[dict[str, Any]] | None = None,
    golden_path: str | Path | None = None,
) -> dict[str, Any]:
    """Chạy golden set evaluation.

    §5.10: Report three metrics + one line per case.

    Args:
        index: VectorIndex object
        catalog: Dict sku → record
        golden: Pre-loaded golden set (or None to load from file)
        golden_path: Path to golden_queries.json

    Returns:
        Dict with metrics and detailed results
    """
    # Load golden set
    if golden is None:
        if golden_path is None:
            golden_path = GOLDEN_QUERIES_PATH
        golden_path = Path(golden_path)
        with open(golden_path, "r", encoding="utf-8") as f:
            golden = json.load(f)

    print(f"[evaluate] Running {len(golden)} golden queries...")

    # ── Retrieval hit rate ─────────────────────────────────────────
    total_queries = 0
    retrieval_hits = 0
    results: list[dict[str, Any]] = []

    # ── Intent accuracy (bundle) ───────────────────────────────────
    bundle_total = 0
    bundle_correct = 0

    for entry in golden:
        query = entry["query"]
        expected_top3 = entry.get("expect_top3", [])
        expected_bundle = entry.get("expect_bundle")
        test_group = entry.get("tests", "unknown")

        # Search
        search_results = index.search(query, k=TOP_K_RETURN)
        actual_skus = [sku for sku, _ in search_results]

        # Hit check: at least 1 expected SKU in actual
        hit = any(exp in actual_skus for exp in expected_top3)
        total_queries += 1
        if hit:
            retrieval_hits += 1

        # Bundle check
        if expected_bundle is not None:
            bundle_total += 1
            # Try building a bundle
            try:
                from retrieve import retrieve
                payload = retrieve(query, index, catalog)
                selected_skus = [s["sku"] for s in payload.get("selected", [])]
                # Check if expected bundle items are in selected
                if all(exp in selected_skus for exp in expected_bundle):
                    bundle_correct += 1
            except Exception as e:
                print(f"  [evaluate] Bundle eval failed for '{query}': {e}")

        # Print one line per case
        icon = "OK" if hit else "MISS"
        print(f"  {icon} | {query} | {actual_skus}")

        results.append({
            "query": query,
            "test_group": test_group,
            "expected_top3": expected_top3,
            "actual_top3": [
                {"sku": sku, "score": round(score, 4)}
                for sku, score in search_results
            ],
            "hit": hit,
        })

    # ── Compute metrics ────────────────────────────────────────────
    hit_rate = retrieval_hits / max(total_queries, 1)
    intent_acc = bundle_correct / max(bundle_total, 1) if bundle_total > 0 else None
    values_prov = _compute_values_provenance(catalog)

    metrics = {
        "retrieval_hit_rate_top3": round(hit_rate, 4),
        "intent_accuracy": round(intent_acc, 4) if intent_acc is not None else None,
        "values_provenance_rate": round(values_prov, 4),
    }

    # ── Print summary ──────────────────────────────────────────────
    print(f"\n{'=' * 70}")
    print(f"  EVALUATION RESULTS")
    print(f"{'=' * 70}")
    print(f"  retrieval_hit_rate_top3:  {retrieval_hits}/{total_queries} ({hit_rate:.1%})")
    if intent_acc is not None:
        print(f"  intent_accuracy:         {bundle_correct}/{bundle_total} ({intent_acc:.1%})")
    else:
        print(f"  intent_accuracy:         N/A (no bundle test cases)")
    print(f"  values_provenance_rate:  {values_prov:.1%}")
    print(f"{'=' * 70}")

    return {
        "metrics": metrics,
        "results": results,
        "summary": {
            "total": total_queries,
            "hits": retrieval_hits,
            "hit_rate_str": f"{retrieval_hits}/{total_queries}",
        },
    }


# ── CLI test ───────────────────────────────────────────────────────────
if __name__ == "__main__":
    print("Run evaluate via run_pipeline.py for full evaluation.")
    print("This module requires a VectorIndex and catalog dict.")
