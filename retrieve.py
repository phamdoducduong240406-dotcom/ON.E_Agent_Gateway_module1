"""
Module 1 — Retrieve
§5.8: Highest-value file in the module.
Decode constraints → semantic search → hard filter → justify → payload.

Hard filters run AFTER semantic search, never before.
"""

from __future__ import annotations

import json
import re
from typing import Any

from config import (
    GEMINI_API_KEY,
    MODEL_NAME,
    TEMPERATURE,
    MAX_TOKENS,
    TOP_K_SEMANTIC,
    TOP_K_RETURN,
)
from schema import (
    VALUE_TAXONOMY, USE_CASES, SKILL_LEVELS, ENVIRONMENTS,
    TECHNICAL_FIELDS, POLICY_FIELDS, OUTCOME_FIELDS,
)


def decode_constraints(query: str) -> dict[str, Any]:
    """Decode query thành hard + soft constraints bằng LLM.

    §5.8: Second LLM call. Split query into:
    - hard: budget_max, in_stock, required connection type, required certification
    - soft: use_case, skill_level, environment, values

    Args:
        query: Natural language query từ agent

    Returns:
        {"hard": {...}, "soft": {...}}
    """
    from google import genai

    prompt = f"""You are a query constraint decoder for an agentic-commerce system.
Analyze the user query and split it into hard constraints (must be satisfied)
and soft constraints (preferences, best-effort matching).

RULES:
1. Hard constraints: budget_max (number), currency (default "AUD"), in_stock (boolean),
   required_connection_type, required_certification
2. Soft constraints: use_case (from {USE_CASES}), skill_level (from {SKILL_LEVELS}),
   environment (from {ENVIRONMENTS}), values (from {VALUE_TAXONOMY})
3. Extract budget from phrases like "dưới 600 đô", "under $1000", "budget 500 AUD"
4. Default currency is AUD unless specified otherwise
5. If a constraint is not mentioned, omit it from the output

QUERY: {query}

Return JSON only with this structure:
{{"hard": {{}}, "soft": {{}}}}
No markdown fences, no explanation."""

    client = genai.Client(api_key=GEMINI_API_KEY)

    try:
        response = client.models.generate_content(
            model=MODEL_NAME,
            contents=prompt,
            config={
                "temperature": TEMPERATURE,
                "max_output_tokens": 500,
                "response_mime_type": "application/json",
            },
        )

        text = response.text.strip()
        # Strip markdown fences
        text = re.sub(r'^```(?:json)?\s*\n?', '', text)
        text = re.sub(r'\n?\s*```$', '', text)

        constraints = json.loads(text)

        # Ensure structure
        if "hard" not in constraints:
            constraints["hard"] = {}
        if "soft" not in constraints:
            constraints["soft"] = {}

        # Default in_stock = True if not specified
        if "in_stock" not in constraints["hard"]:
            constraints["hard"]["in_stock"] = True

        print(f"  [retrieve] Decoded constraints: {json.dumps(constraints, ensure_ascii=False)}")
        return constraints

    except Exception as e:
        print(f"  [retrieve] Failed to decode constraints: {e}")
        return {"hard": {"in_stock": True}, "soft": {}}


def apply_hard_filters(
    cands: list[dict[str, Any]],
    hard: dict[str, Any],
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """Apply hard constraints, return (kept, excluded).

    §5.8: Hard filters run AFTER semantic search, not before.
    This preserves information about which constraint eliminated which candidate.

    Args:
        cands: List of candidate records from semantic search
        hard: Hard constraints dict

    Returns:
        (kept_candidates, excluded_candidates_with_reasons)
    """
    budget_max = hard.get("budget_max")
    currency = hard.get("currency", "AUD")
    in_stock = hard.get("in_stock", True)
    required_connection = hard.get("required_connection_type")

    kept: list[dict[str, Any]] = []
    excluded: list[dict[str, Any]] = []

    for cand in cands:
        reasons: list[str] = []

        # Budget check
        price = cand.get("price")
        if budget_max is not None and price is not None:
            if price > budget_max:
                reasons.append(f"price {price} {currency} exceeds budget {budget_max} {currency}")

        # Stock check
        stock = cand.get("stock", 0)
        if in_stock and (stock is None or stock <= 0):
            reasons.append("out of stock")

        # Connection type check
        if required_connection:
            specs = cand.get("_extracted_specs", {})
            conn = specs.get("connection_type", {})
            conn_val = conn.get("value", "") if isinstance(conn, dict) else ""
            ports = specs.get("ports", {})
            ports_val = ports.get("value", "") if isinstance(ports, dict) else ""
            combined = f"{conn_val} {ports_val}".lower()
            if required_connection.lower() not in combined:
                reasons.append(f"missing required connection: {required_connection}")

        if reasons:
            excluded.append({
                "sku": cand.get("sku", ""),
                "reason": reasons[0].split()[0] if reasons else "filtered",
                "detail": "; ".join(reasons),
            })
        else:
            kept.append(cand)

    print(f"  [retrieve] Hard filter: {len(kept)} kept, {len(excluded)} excluded")
    return kept, excluded


def build_justification(
    rec: dict[str, Any],
    soft: dict[str, Any],
) -> list[dict[str, Any]]:
    """Build justification entries per satisfied soft constraint.

    §5.8: Only use confidence == "high" fields as evidence.
    A low-confidence value claim must NEVER appear in justification —
    greenwashing exposure risk.

    Args:
        rec: Product record
        soft: Soft constraints dict

    Returns:
        List of {constraint, matched_field, evidence, confidence}
    """
    specs = rec.get("_extracted_specs", {})
    justifications: list[dict[str, Any]] = []

    # Check use_case match
    use_case = soft.get("use_case")
    if use_case:
        uc_data = specs.get("use_cases", {})
        if isinstance(uc_data, dict) and uc_data.get("confidence") == "high":
            uc_values = uc_data.get("value", [])
            if isinstance(uc_values, list) and use_case in uc_values:
                justifications.append({
                    "constraint": f"use_case={use_case}",
                    "matched_field": "use_cases",
                    "evidence": uc_data.get("source_span", ""),
                    "confidence": "high",
                })

    # Check skill_level match
    skill = soft.get("skill_level")
    if skill:
        sl_data = specs.get("skill_level", {})
        if isinstance(sl_data, dict) and sl_data.get("confidence") == "high":
            if sl_data.get("value") == skill:
                justifications.append({
                    "constraint": f"skill_level={skill}",
                    "matched_field": "skill_level",
                    "evidence": sl_data.get("source_span", ""),
                    "confidence": "high",
                })

    # Check environment match
    env = soft.get("environment")
    if env:
        env_data = specs.get("environment", {})
        if isinstance(env_data, dict) and env_data.get("confidence") == "high":
            env_values = env_data.get("value", [])
            if isinstance(env_values, list) and env in env_values:
                justifications.append({
                    "constraint": f"environment={env}",
                    "matched_field": "environment",
                    "evidence": env_data.get("source_span", ""),
                    "confidence": "high",
                })

    # Check values match (anti-greenwashing: ONLY high confidence)
    req_values = soft.get("values", [])
    if req_values:
        value_claims = specs.get("values", [])
        if isinstance(value_claims, list):
            for claim in value_claims:
                if isinstance(claim, dict) and claim.get("confidence") == "high":
                    claim_name = claim.get("claim") or claim.get("value", "")
                    if claim_name in req_values:
                        justifications.append({
                            "constraint": f"value={claim_name}",
                            "matched_field": "values",
                            "evidence": claim.get("source_span", ""),
                            "confidence": "high",
                        })

    # If no specific soft constraints matched, justify by semantic relevance
    # Check technical specs that might match the query intent
    if not justifications:
        for field_name in TECHNICAL_FIELDS + POLICY_FIELDS:
            field_data = specs.get(field_name, {})
            if isinstance(field_data, dict) and field_data.get("confidence") == "high":
                justifications.append({
                    "constraint": "semantic_match",
                    "matched_field": field_name,
                    "evidence": field_data.get("source_span", ""),
                    "confidence": "high",
                })
                if len(justifications) >= 3:
                    break

    return justifications


def retrieve(
    query: str,
    index: Any,  # VectorIndex
    catalog: dict[str, dict[str, Any]],
) -> dict[str, Any]:
    """Full retrieval pipeline → §4.3 payload.

    §5.8 Execution order:
    1. decode_constraints
    2. index.search(query, k=TOP_K_SEMANTIC)  — retrieve wide
    3. apply_hard_filters                      — filter AFTER
    4. build_bundle if query names an outcome
    5. build_justification for kept items
    6. assemble §4.3 payload

    Args:
        query: Natural language query
        index: VectorIndex object
        catalog: Dict sku → record for lookup

    Returns:
        §4.3 retrieval payload
    """
    print(f"\n[retrieve] Query: \"{query}\"")

    # 1. Decode constraints
    constraints = decode_constraints(query)
    hard = constraints.get("hard", {})
    soft = constraints.get("soft", {})

    # 2. Semantic search (retrieve wide)
    search_results = index.search(query, k=TOP_K_SEMANTIC)
    print(f"  [retrieve] Semantic search returned {len(search_results)} candidates")

    # Map SKUs to full records
    candidates: list[dict[str, Any]] = []
    for sku, score in search_results:
        if sku in catalog:
            rec = dict(catalog[sku])
            rec["_search_score"] = score
            candidates.append(rec)

    # 3. Apply hard filters (AFTER semantic search)
    kept, excluded = apply_hard_filters(candidates, hard)

    # 4. Try to build bundle if outcome is specified
    bundle_items = None
    bundle_total = 0
    bundle_excluded: list[dict[str, Any]] = []

    outcome = soft.get("use_case")
    budget_max = hard.get("budget_max")

    if outcome and kept:
        try:
            from bundle import build_bundle
            primary = kept[0]
            b_items, b_total, b_excl = build_bundle(
                primary_sku=primary["sku"],
                outcome=outcome,
                budget_max=budget_max,
                catalog=catalog,
            )
            if b_items:
                bundle_items = b_items
                bundle_total = b_total
                bundle_excluded.extend(b_excl)
        except Exception as e:
            print(f"  [retrieve] Bundle build failed: {e}")

    # 5. Build justification for top items
    top_items = kept[:TOP_K_RETURN]
    selected: list[dict[str, Any]] = []

    for rec in top_items:
        justification = build_justification(rec, soft)
        selected.append({
            "sku": rec.get("sku", ""),
            "role_in_bundle": "primary" if len(selected) == 0 else "complementary",
            "price": rec.get("price"),
            "justification": justification,
        })

    # Add bundle items to selected if any
    if bundle_items:
        for bi in bundle_items:
            if bi.get("sku") not in [s["sku"] for s in selected]:
                selected.append(bi)

    # 6. Assemble §4.3 payload
    total = sum(s.get("price", 0) or 0 for s in selected)

    # Merge excluded from hard filters and bundle
    all_excluded = excluded + bundle_excluded

    payload: dict[str, Any] = {
        "query": query,
        "decoded_constraints": {
            "hard": hard,
            "soft": soft,
        },
        "selected": selected,
        "bundle_total": total,
        "excluded": all_excluded,
    }

    print(f"  [retrieve] Result: {len(selected)} selected, {len(all_excluded)} excluded")
    return payload


# ── CLI test ───────────────────────────────────────────────────────────
if __name__ == "__main__":
    print("Run retrieve via run_pipeline.py or import and call retrieve() directly.")
    print("This module requires a VectorIndex and catalog dict.")
