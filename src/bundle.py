"""
Module 1 — Bundle
§5.9: Expand required_with first, then completes_outcome cheapest-first.
Budget applies to BUNDLE TOTAL, not individual items (Gotcha #2).
"""

from __future__ import annotations

import csv
from pathlib import Path
from typing import Any

from config import RELATIONS_CSV_PATH


def load_relations(path: str | Path | None = None) -> list[dict[str, Any]]:
    """Load relations từ CSV file.

    §5.9: relations.csv columns: sku_a, sku_b, type, outcome, note

    Args:
        path: Đường dẫn relations.csv

    Returns:
        List of relation dicts
    """
    if path is None:
        path = RELATIONS_CSV_PATH

    path = Path(path)
    if not path.exists():
        print(f"  [bundle] WARNING: relations file not found: {path}")
        return []

    relations: list[dict[str, Any]] = []
    with open(path, "r", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            relations.append({
                "sku_a": row.get("sku_a", "").strip(),
                "sku_b": row.get("sku_b", "").strip(),
                "type": row.get("type", "").strip(),
                "outcome": row.get("outcome", "").strip(),
                "note": row.get("note", "").strip(),
            })

    print(f"  [bundle] Loaded {len(relations)} relations")
    return relations


def _find_relations(
    sku: str,
    relations: list[dict[str, Any]],
    rel_type: str | None = None,
    outcome: str | None = None,
) -> list[dict[str, Any]]:
    """Find relations for a SKU, optionally filtered by type and outcome.

    Args:
        sku: SKU to find relations for
        relations: All relations
        rel_type: Filter by relation type (e.g., "required_with")
        outcome: Filter by outcome

    Returns:
        List of matching relations
    """
    matches: list[dict[str, Any]] = []
    for rel in relations:
        # Check if SKU is in this relation
        if rel["sku_a"] != sku and rel["sku_b"] != sku:
            continue
        # Filter by type
        if rel_type and rel["type"] != rel_type:
            continue
        # Filter by outcome
        if outcome and rel["outcome"] and rel["outcome"] != outcome:
            continue

        # Get the other SKU
        other_sku = rel["sku_b"] if rel["sku_a"] == sku else rel["sku_a"]
        matches.append({**rel, "_other_sku": other_sku})

    return matches


def build_bundle(
    primary_sku: str,
    outcome: str,
    budget_max: float | None,
    catalog: dict[str, dict[str, Any]],
    relations_path: str | Path | None = None,
) -> tuple[list[dict[str, Any]], float, list[dict[str, Any]]]:
    """Build a product bundle around a primary SKU.

    §5.9 Rules:
    1. Expand required_with first — product whose requirement is missing
       is NOT usable alone; its true cost is the sum of the pair.
    2. Then add completes_outcome items cheapest-first under budget.
    3. Budget applies to BUNDLE TOTAL, not individual items (Gotcha #2).
    4. Carry each relation's note into justification or exclusion detail.

    Args:
        primary_sku: SKU of the primary product
        outcome: Target outcome/use case
        budget_max: Maximum budget (None = no limit)
        catalog: Dict sku → record

    Returns:
        (bundle_items, bundle_total, excluded_items)
    """
    relations = load_relations(relations_path)

    # Start with primary product
    primary = catalog.get(primary_sku)
    if not primary:
        print(f"  [bundle] Primary SKU {primary_sku} not found in catalog")
        return [], 0, []

    primary_price = primary.get("price", 0) or 0
    bundle_items: list[dict[str, Any]] = [{
        "sku": primary_sku,
        "role_in_bundle": "primary",
        "price": primary_price,
        "justification": [{"constraint": f"outcome={outcome}", "matched_field": "primary",
                          "evidence": "selected as primary product", "confidence": "high"}],
    }]
    running_total = primary_price
    excluded: list[dict[str, Any]] = []
    added_skus = {primary_sku}

    # ── Step 1: Expand required_with ───────────────────────────────
    required_rels = _find_relations(primary_sku, relations, rel_type="required_with")
    for rel in required_rels:
        other_sku = rel["_other_sku"]
        if other_sku in added_skus:
            continue

        other = catalog.get(other_sku)
        if not other:
            continue

        other_price = other.get("price", 0) or 0
        new_total = running_total + other_price

        # Budget check on BUNDLE TOTAL
        if budget_max is not None and new_total > budget_max:
            excluded.append({
                "sku": other_sku,
                "reason": "requires_over_budget",
                "detail": f"{other_sku} is required with {primary_sku} "
                         f"({rel.get('note', '')}); bundle total {new_total} "
                         f"exceeds budget {budget_max}",
            })
            continue

        bundle_items.append({
            "sku": other_sku,
            "role_in_bundle": "required",
            "price": other_price,
            "justification": [{
                "constraint": f"required_with={primary_sku}",
                "matched_field": "relation",
                "evidence": rel.get("note", "required accessory"),
                "confidence": "high",
            }],
        })
        running_total = new_total
        added_skus.add(other_sku)

    # ── Step 2: Add completes_outcome items, cheapest-first ────────
    outcome_rels = _find_relations(primary_sku, relations, rel_type="completes_outcome")

    # Also find items related to any bundle item already added
    for item in list(bundle_items[1:]):  # skip primary
        more_rels = _find_relations(item["sku"], relations, rel_type="completes_outcome")
        outcome_rels.extend(more_rels)

    # Deduplicate and sort by price (cheapest first)
    outcome_candidates: list[tuple[float, str, dict]] = []
    seen = set()
    for rel in outcome_rels:
        other_sku = rel["_other_sku"]
        if other_sku in added_skus or other_sku in seen:
            continue
        seen.add(other_sku)

        other = catalog.get(other_sku)
        if not other:
            continue

        other_price = other.get("price", 0) or 0
        outcome_candidates.append((other_price, other_sku, rel))

    outcome_candidates.sort(key=lambda x: x[0])

    for price, sku, rel in outcome_candidates:
        new_total = running_total + price

        if budget_max is not None and new_total > budget_max:
            excluded.append({
                "sku": sku,
                "reason": "over_budget",
                "detail": f"Adding {sku} (${price}) would bring bundle total to "
                         f"{new_total}, exceeding budget {budget_max}. "
                         f"{rel.get('note', '')}",
            })
            continue

        bundle_items.append({
            "sku": sku,
            "role_in_bundle": "complementary",
            "price": price,
            "justification": [{
                "constraint": f"completes_outcome={outcome}",
                "matched_field": "relation",
                "evidence": rel.get("note", "completes the outcome"),
                "confidence": "high",
            }],
        })
        running_total = new_total
        added_skus.add(sku)

    print(f"  [bundle] Bundle: {len(bundle_items)} items, total ${running_total}, "
          f"{len(excluded)} excluded")

    return bundle_items, running_total, excluded


# ── CLI test ───────────────────────────────────────────────────────────
if __name__ == "__main__":
    print("Run bundle via retrieve.py or run_pipeline.py.")
    print("This module requires a catalog dict and relations.csv.")
