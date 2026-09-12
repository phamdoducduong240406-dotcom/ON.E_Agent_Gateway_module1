# Module 1 — Implementation Spec
## Semantic Catalog Transformation Engine

**For:** the AI coding assistant implementing this module.
**Read this whole file before writing any code.** Implement files in the order given in §2.
All code in this module is written during UAVS Hackathon 2026 Day 1 (from 09:00 AEST, 12/09/2026).

---

## 1. What this module does

Turns a human-written product catalogue into machine-readable records, then answers
multi-constraint agent queries with **justified** product selections.

Downstream consumers:
- **Module 2 (Merchant Dashboard)** reads the handoff file and the retrieval payload
- **Module 3 (B2A API Gateway)** wraps `retrieve()` and `build_bundle()` as endpoints

The single most important output is not the product list. It is the **justification payload**
in §4.3: which constraint matched which field, with the source text as evidence.

---

## 2. Build order and time boxes

Implement strictly in this order. Each step has an acceptance test in its section.
Do not start step N+1 until step N passes.

| Step | File | Box | Blocking? |
|---|---|---|---|
| 1 | `config.py`, `schema.py` | 20 min | Yes, everything imports these |
| 2 | `ingest.py` | 30 min | Yes |
| 3 | `extract.py` | 55 min | Yes, network-bound, start the full run early |
| 4 | `verify.py` | 25 min | Yes |
| 5 | `compose.py`, `index.py` | 30 min | Yes |
| 6 | `retrieve.py`, `bundle.py` | 60 min | **Highest value, do not compress** |
| 7 | `evaluate.py` | 25 min | No, but needed for dashboard metrics |
| 8 | `run_pipeline.py` + freeze | 25 min | Yes |
| — | `mapper.py` (JSON-LD) | Day 2 | Deferred, deterministic, off the demo path |

If behind at step 6: drop `certifications`, drop `alternative_to`/`upgrade_of` relation types,
cut the golden set to 8 rows. **Never drop:** outcome/value fields, justification payload,
`required_with` relations, the confidence layer.

---

## 3. Project layout

```
module1/
├── config.py
├── schema.py
├── ingest.py
├── extract.py
├── verify.py
├── compose.py
├── index.py
├── retrieve.py
├── bundle.py
├── evaluate.py
├── run_pipeline.py
└── data/
    ├── catalog_raw.json
    ├── golden_queries.json
    ├── relations.csv
    ├── cache/
    └── out/catalog_standardized.json
```

---

## 4. Shared contracts — freeze these first, send to Modules 2 and 3

### 4.1 Enums (in `schema.py`, closed sets, never let the model invent labels)

```python
VALUE_TAXONOMY = [
    "sustainable_materials", "recyclable_packaging", "repairability",
    "long_warranty", "local_manufacturing", "ethical_sourcing",
    "energy_efficiency", "carbon_disclosure",
]
USE_CASES    = ["podcasting", "streaming", "vocal_recording", "instrument_recording",
                "field_recording", "video_calls", "gaming"]
SKILL_LEVELS = ["beginner", "intermediate", "pro"]
ENVIRONMENTS = ["home_untreated", "studio", "mobile", "office"]
RELATION_TYPES = ["required_with", "completes_outcome", "upgrade_of", "alternative_to"]
UNIT_CODES = {"hz": "HTZ", "khz": "KHZ", "inch": "INH", "watt": "WTT", "mm": "MMT"}
```

### 4.2 Standardized product record

```json
{
  "sku": "MIC-USB-01",
  "name": "...",
  "brand": "...",
  "category": "microphone",
  "price": 189, "currency": "AUD", "stock": 12,
  "specs": [
    { "name": "connection_type", "value": "USB-C", "unit": null,
      "confidence": "high", "source_span": "kết nối USB-C cắm là chạy" }
  ],
  "policy": {
    "warranty_months": { "value": 24, "confidence": "high", "source_span": "..." },
    "return_days":     { "value": 14, "confidence": "high", "source_span": "..." },
    "exclusions": ["rơi vỡ", "vào nước"]
  },
  "outcomes": {
    "use_cases":   { "value": ["podcasting"], "confidence": "high", "source_span": "..." },
    "skill_level": { "value": "beginner", "confidence": "low", "source_span": null,
                     "note": "inferred from 'plug and play'" },
    "environment": { "value": ["home_untreated"], "confidence": "high", "source_span": "..." }
  },
  "values": [
    { "claim": "recyclable_packaging", "confidence": "high", "source_span": "hộp giấy tái chế 100%" }
  ],
  "agent_text": "...",
  "_raw_text": "..."
}
```

`_raw_text` is internal only. Strip it from the handoff file.

### 4.3 Retrieval payload — **the key deliverable**

```json
{
  "query": "bộ đồ podcast cho người mới, phòng chưa tiêu âm, dưới 600 đô",
  "decoded_constraints": {
    "hard": { "budget_max": 600, "currency": "AUD", "in_stock": true },
    "soft": { "use_case": "podcasting", "skill_level": "beginner",
              "environment": "home_untreated", "values": [] }
  },
  "selected": [
    {
      "sku": "MIC-USB-01",
      "role_in_bundle": "primary",
      "price": 189,
      "justification": [
        { "constraint": "skill_level=beginner", "matched_field": "connection_type",
          "evidence": "kết nối USB-C cắm là chạy", "confidence": "high" }
      ]
    }
  ],
  "bundle_total": 548,
  "excluded": [
    { "sku": "MIC-XLR-07", "reason": "requires_interface",
      "detail": "XLR connection requires an audio interface; bundle total 720 exceeds budget 600" }
  ]
}
```

`excluded` is not optional. Module 2's Agent Query Simulator shows the merchant **why a product
lost**, which is the module's business-value story. Always populate it.

---

## 5. File specs

### 5.1 `config.py`

```python
MODEL = "<set from the API the team is using>"
EMBED_MODEL = "<...>"
PROMPT_VERSION = "v2"
TOP_K_SEMANTIC = 20        # retrieve wide, filter after
TOP_K_RETURN = 3
DATA_DIR = "data"
CACHE_DIR = "data/cache"
OUT_PATH = "data/out/catalog_standardized.json"
```

### 5.2 `schema.py`

Holds the enums from §4.1 plus:

```python
FIELD_MAP: dict[str, str]        # messy source name -> canonical name
TECHNICAL_FIELDS: list[str]
POLICY_FIELDS: list[str]
OUTCOME_FIELDS: list[str]
```

`FIELD_MAP` must cover at least: `item_code|product_id|SKU_NO -> sku`,
`title|product_name -> name`, `mfr|manufacturer -> brand`,
`long_desc|desc_html|description -> description`, `warranty_blob -> warranty_raw`.

**Acceptance:** `python -c "import schema"` runs, all enums are non-empty lists.

---

### 5.3 `ingest.py`

```python
def load_catalog(path: str) -> list[dict]: ...
def normalize_record(raw: dict) -> dict | None: ...
def ingest(path: str) -> list[dict]: ...
```

Rules:
1. Rename keys via `FIELD_MAP`; unmapped keys pass through unchanged.
2. Drop any record with no `sku` (return `None`).
3. Build `_raw_text` by joining **every** free-text source field, at minimum
   `description` and `warranty_raw`, separated by a space.

**Rule 3 is load-bearing.** `verify.py` matches spans against `_raw_text`.
If `warranty_raw` is left out, every policy field gets flagged low confidence and you will
lose 20 minutes debugging correct code.

**Acceptance:** ingest the raw catalogue; every returned record has `sku`, `name`, `_raw_text`,
and `len(_raw_text) > 0`.

---

### 5.4 `extract.py`

```python
def build_prompt(raw_text: str) -> str: ...
def call_llm(raw_text: str) -> dict: ...
def cache_key(sku: str, raw_text: str) -> str: ...
def extract_with_cache(record: dict) -> dict: ...
def extract_all(records: list[dict]) -> list[dict]: ...
```

Rules:
1. `temperature=0`, `max_tokens=2000`. Use the API's structured-output / JSON-schema mode if available.
2. **Strip markdown fences before parsing**, even with structured output on. Models still emit them.
   Strip a leading ```` ```json ````, a leading ```` ``` ````, and a trailing ```` ``` ````.
3. Cache every response to `CACHE_DIR/{sku}_{hash}.json` where hash covers
   `raw_text + PROMPT_VERSION`. Changing the prompt must invalidate the cache automatically.
4. `extract_all` must be resumable: on restart, cached SKUs are skipped with no network call.
5. Wrap each call in try/except. One bad SKU logs and continues; it never kills the run.
6. Write with `ensure_ascii=False` everywhere. The catalogue is partly Vietnamese.

**Start the full-catalogue run as soon as 5 SKUs look correct**, and write the next files while
it runs in the background. This step is the only network bottleneck in the module.

**Acceptance:** run on 5 SKUs; every returned field carries a `source_span` key
(value may be `null`); a second run makes zero network calls.

---

### 5.5 `verify.py`

```python
def norm(s: str) -> str: ...
def verify_fields(fields: list[dict], raw_text: str) -> list[dict]: ...
def verify_record(rec: dict) -> dict: ...
```

`norm` must: `unicodedata.normalize("NFC", s)`, lowercase, then `" ".join(s.split())`.

**NFC is mandatory.** Vietnamese diacritics have two encodings that look identical on screen
but fail `in` comparison. Without NFC every Vietnamese field is wrongly flagged low.

Rules:
1. If `norm(source_span) in norm(raw_text)` → `confidence = "high"`.
2. Otherwise → `confidence = "low"` and set `source_span = None`.
3. **Never delete a low-confidence field.** Flag it and keep it.
4. Apply to `specs`, `policy`, `outcomes` and `values` alike.

Rule 3 exists because an inferred-but-reasonable value (`resolution=3840x2160` from the word "4K")
is useful information; deleting it loses data, publishing it as fact breaks the module's own thesis.
Flagging is the third option and it is the one to defend in Q&A.

**Acceptance:** inject a fabricated field with `source_span="totally not in the text"`;
it must come back `low` with `source_span=None`, while a real field stays `high`.

---

### 5.6 `compose.py`

```python
def build_agent_text(rec: dict) -> str: ...
```

Compose order: name → `use_cases` and `skill_level` → specs → `environment` →
values → policy → price and stock.

Rules:
1. Include **only `confidence == "high"`** entries from `specs` and `values`.
2. **Never include the original marketing description.** Words like "immersive" or
   "buttery-smooth" pull the vector toward noise, which is exactly what this module exists
   to remove. Embedding the raw copy defeats the whole pipeline.
3. Outcomes go before specs: agent queries are phrased in purpose language, not spec language.

**Acceptance:** `build_agent_text` output contains no substring longer than 8 words that also
appears in `rec["description"]`.

---

### 5.7 `index.py`

```python
class VectorIndex:
    def build(self, records: list[dict]) -> None: ...
    def search(self, query: str, k: int = TOP_K_SEMANTIC) -> list[tuple[str, float]]: ...
```

Use a plain numpy matrix with cosine similarity. Do **not** add a hosted vector DB today:
it is one more failure point outside your control during a timed build. Name the serverless
option in the technical documentation as the production path instead.

Cache embeddings to disk keyed by a hash of `agent_text`, same pattern as `extract.py`.

**Acceptance:** query `"mic for a beginner podcaster"` returns a beginner USB mic in the top 3.

---

### 5.8 `retrieve.py` — highest-value file in the module

```python
def decode_constraints(query: str) -> dict: ...
def apply_hard_filters(cands: list[dict], hard: dict) -> tuple[list[dict], list[dict]]: ...
def build_justification(rec: dict, soft: dict) -> list[dict]: ...
def retrieve(query: str, index: VectorIndex, catalog: dict) -> dict: ...
```

**`decode_constraints`** is a second LLM call. Prompt it to split the query into `hard`
(budget_max, in_stock, required connection type, required certification) and `soft`
(use_case, skill_level, environment, values), using only the §4.1 enums, and to return
JSON only.

**Execution order inside `retrieve`:**
```
decode_constraints
  → index.search(query, k=TOP_K_SEMANTIC)     # retrieve wide
  → apply_hard_filters                         # filter AFTER, not before
  → build_bundle if the query names an outcome
  → build_justification for kept items
  → assemble the §4.3 payload
```

**Hard filters run after semantic search, never before.** Filtering first throws away the
information about *which constraint eliminated which candidate*, and `excluded` would be empty.
Module 2's simulator has nothing to show without it.

**`build_justification`** returns one entry per satisfied soft constraint:
`{constraint, matched_field, evidence, confidence}` where `evidence` is the field's
`source_span`. Only use `confidence == "high"` fields as evidence. A low-confidence value
claim must never appear in a justification: asserting an unverified sustainability claim is a
real greenwashing exposure for the retailer, and saying so in Q&A shows domain understanding.

**Acceptance:** a query with a budget returns a non-empty `excluded` list with a human-readable
`detail` string for at least one over-budget candidate.

---

### 5.9 `bundle.py`

```python
def load_relations(path: str) -> list[dict]: ...
def build_bundle(primary_sku: str, outcome: str, budget_max: float | None,
                 catalog: dict) -> tuple[list[dict], float, list[dict]]: ...
```

`relations.csv` columns: `sku_a, sku_b, type, outcome, note`.

Rules:
1. Expand `required_with` first. A product whose requirement is missing is **not usable alone**
   and its true cost is the sum of the pair.
2. Then add `completes_outcome` items for the requested outcome, cheapest-first, while the
   running total stays under budget.
3. **Budget applies to the bundle total, not to individual items.** This is the most common
   bug in this file and it breaks the best moment in the demo.
4. Carry each relation's `note` through into the justification or the exclusion detail.

The demo-critical case: a cheap XLR mic that needs an interface ends up more expensive than a
slightly pricier USB mic. Getting that right is the strongest evidence that the system
understands the buyer's actual problem rather than matching keywords.

**Acceptance:** given the XLR trap pair, `build_bundle` with a tight budget excludes the XLR mic
and its `detail` mentions the interface requirement and the combined total.

---

### 5.10 `evaluate.py`

```python
def run_golden(index: VectorIndex, catalog: dict, golden: list[dict]) -> dict: ...
```

`golden_queries.json` rows: `{query, expect_top3, expect_bundle?, tests}`.

Report three metrics:
- `retrieval_hit_rate_top3`
- `intent_accuracy` — bundle contains the expected roles
- `values_provenance_rate` — share of value claims with a non-null `source_span`

Print one line per case: `OK/MISS | query | returned SKUs`.

**Run the cross-language case and the price-trap case first.** If the embedding model cannot
match an English query against Vietnamese catalogue text, you need to know at 14:00, not during
the demo.

---

### 5.11 `run_pipeline.py`

Order: ingest → extract_all → verify → compose → index.build → evaluate → write handoff.

Handoff file:
```json
{ "generated_at": "...", "schema_version": "2.0", "count": 30,
  "metrics": { "...": "..." },
  "products": [...], "relations": [...], "value_taxonomy": [...] }
```

Strip `_raw_text` from products before writing. Include `schema_version` so Modules 2 and 3
fail loudly rather than silently on a contract change.

**Freeze and hand off with 25 minutes left in the day, not at the final minute.**
Modules 2 and 3 need time to integrate; a structural change at the last moment means Day 2
starts from a broken build.

---

## 6. Extraction prompt (use verbatim)

```
You are a product data extraction system for an agentic-commerce catalogue.
Extract structured data from the raw product text below.

RULES:
1. For every field you extract, you MUST return "source_span": the exact
   substring, copied character for character, from the input text.
2. If a value is not stated explicitly and you had to infer it, set
   "source_span" to null and explain briefly in "note".
3. Never invent a value that has no basis in the text. Omit the field instead.
4. Do not normalise units inside source_span. Copy it raw.
5. Input may be Vietnamese or English. Field names in English; textual values
   stay in the original language.
6. For "values": use ONLY the labels in VALUE_TAXONOMY. Do not create new labels.
   A vague marketing phrase that names no specific practice must be returned
   with source_span null.
7. For "use_cases", "skill_level", "environment": use ONLY the allowed enums.

TECHNICAL FIELDS: connection_type, polar_pattern, freq_response,
                  phantom_power, sample_rate, ports
POLICY FIELDS:    warranty_months, warranty_scope, return_days, exclusions
OUTCOME FIELDS:   use_cases, skill_level, environment
VALUE_TAXONOMY:   sustainable_materials, recyclable_packaging, repairability,
                  long_warranty, local_manufacturing, ethical_sourcing,
                  energy_efficiency, carbon_disclosure

RAW TEXT:
{{TEXT}}

Return JSON only. No markdown fences, no explanation.
```

Rule 6 is the anti-greenwashing mechanism. "Responsibly made" is empty marketing and must be
flagged; "100% recycled paper packaging" is a specific claim and is accepted.

---

## 7. Gotchas, ranked by how much time they cost

1. **Missing NFC normalization** → every Vietnamese field flagged low, code looks correct. ~20 min lost.
2. **Budget checked per item instead of per bundle** → the best demo moment silently breaks.
3. **Hard filters applied before semantic search** → `excluded` comes back empty, Module 2 has nothing to render.
4. **Marketing copy leaking into `agent_text`** → retrieval quality degrades for no visible reason.
5. **Markdown fences not stripped** → `json.loads` throws an unhelpful error mid-run.
6. **`warranty_raw` missing from `_raw_text`** → all policy fields flagged low.
7. **`ensure_ascii=True` on dumps** → unreadable cache files, painful debugging.

---

## 8. Definition of done for Module 1

- [ ] `run_pipeline.py` completes end to end on the full catalogue without manual steps
- [ ] A fabricated field is correctly flagged low by `verify.py`
- [ ] `retrieve()` returns a payload matching §4.3 exactly, with non-empty `justification` and `excluded`
- [ ] The XLR price-trap case produces the correct exclusion with a readable reason
- [ ] `evaluate.py` prints all three metrics
- [ ] Handoff file written, `_raw_text` stripped, `schema_version` present
- [ ] Contract §4.2 and §4.3 confirmed received by Modules 2 and 3
- [ ] External resources (API provider, embedding model, libraries) listed for the technical documentation
