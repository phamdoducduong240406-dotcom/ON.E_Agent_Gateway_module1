# Module 1 — Semantic Catalog Transformation Engine
## Design Blueprint (tài liệu thiết kế, chuẩn bị trước Hackathon)

> Tài liệu này là **thiết kế**, không chứa source code.
> Toàn bộ code được viết trong giờ thi (từ 09:00 12/09/2026) theo mục IV.C.5.b Rulebook.
> Khai báo trong Technical Documentation: schema, prompt, golden set và catalog mẫu được chuẩn bị trước dưới dạng tài liệu và dữ liệu.

---

## 1. Cấu trúc thư mục dự kiến

```
module1/
├── config.py          Hằng số: MODEL, PROMPT_VERSION, đường dẫn, tên field
├── schema.py          Định nghĩa bộ field chuẩn + FIELD_MAP + UNIT_CODES
├── ingest.py          Đọc catalog thô → record chuẩn hoá tên field
├── extract.py         Gọi LLM + cache theo SKU
├── verify.py          Đối chiếu source_span với text gốc → gán confidence
├── mapper.py          Record nội bộ → JSON-LD Schema.org
├── compose.py         Ghép agent_text từ field high confidence
├── index.py           Embedding + tìm kiếm cosine
├── evaluate.py        Chạy golden set, in hit rate top-3
├── run_pipeline.py    Chạy tuần tự 1→6, xuất file bàn giao
└── data/
    ├── catalog_raw.json          (chuẩn bị trước)
    ├── golden_queries.json       (chuẩn bị trước)
    ├── compat.csv                (chuẩn bị trước)
    └── cache/                    (sinh trong giờ thi)
```

Mỗi file một trách nhiệm. Lý do tách nhỏ: nếu bước 2 hỏng vì quota, các bước khác vẫn test được độc lập bằng dữ liệu giả.

---

## 2. Trách nhiệm từng file

| File | Nhận vào | Trả ra | Có gọi mạng |
|---|---|---|---|
| ingest | file catalog thô | list record đã đổi tên field, có `_raw_text` | Không |
| extract | 1 record | dict specs kèm `source_span` mỗi field | **Có** |
| verify | specs + `_raw_text` | specs đã gán `confidence` | Không |
| mapper | record đầy đủ | dict JSON-LD | Không |
| compose | record | chuỗi `agent_text` | Không |
| index | list `agent_text` | ma trận vector + hàm search | **Có** (lúc embed) |
| evaluate | golden set + index | hit rate top-3 | Không |

Chỉ 2 file chạm mạng. Hai file đó phải có cache và retry, các file còn lại thì không cần.

---

## 3. Bộ field chuẩn

| Nhóm | Field | Nguồn | Dùng LLM |
|---|---|---|---|
| Định danh | sku, name, brand, category | PIM, có sẵn | Không |
| Giao dịch | price, currency, stock, shipping_fee | API real-time | Không |
| Kỹ thuật | screen_size, panel_type, refresh_rate, resolution, ports, power | chôn trong văn xuôi | **Có** |
| Chính sách | warranty_months, warranty_scope, return_days, exclusions | đoạn text dài | **Có** |

Nguyên tắc: chỉ gọi LLM cho nhóm 3 và 4.

---

## 4. Data contract (khoá trước, hai module kia đọc theo)

```json
{
  "sku": "MON-27-4K-01",
  "@context": "https://schema.org",
  "@type": "Product",
  "name": "...",
  "brand": { "@type": "Brand", "name": "..." },
  "offers": {
    "@type": "Offer",
    "price": 899,
    "priceCurrency": "AUD",
    "availability": "https://schema.org/InStock"
  },
  "additionalProperty": [
    {
      "@type": "PropertyValue",
      "name": "refresh_rate",
      "value": 144,
      "unitCode": "HTZ",
      "confidence": "high",
      "source_span": "Tần số quét 144Hz"
    }
  ],
  "policy": {
    "warranty_months": { "value": 36, "confidence": "high", "source_span": "..." },
    "return_days":     { "value": 14, "confidence": "high", "source_span": "..." },
    "exclusions": ["rơi vỡ", "vào nước", "tự ý tháo máy"]
  },
  "compatible_with": ["LAP-MBP-14"],
  "agent_text": "..."
}
```

File bàn giao bọc thêm metadata:

```json
{
  "generated_at": "...",
  "schema_version": "1.0",
  "count": 120,
  "retrieval_hit_rate_top3": "11/14",
  "products": [ ... ],
  "compatibility": [ ... ]
}
```

`confidence` và `source_span` là field mở rộng ngoài chuẩn Schema.org. Giữ trong output nội bộ cho dashboard đọc, ghi rõ trong tài liệu là mở rộng.

---

## 5. Prompt extraction (bản chốt)

```
You are a product data extraction system. Extract specifications from the
raw product text below into the given schema.

RULES:
1. For every field you extract, you MUST return "source_span": the exact
   substring, copied character for character, from the input text where
   the value appears.
2. If a value is not stated explicitly and you had to infer it, set
   "source_span" to null and explain briefly in "note".
3. Never guess a value that has no basis in the text. Omit the field instead.
4. Do not normalise units inside source_span. Copy it raw.
5. The input may be in Vietnamese or English. Return field names in English,
   values in the original language where they are textual.

FIELDS: screen_size, panel_type, refresh_rate, resolution, ports, power,
        warranty_months, warranty_scope, return_days, exclusions

RAW TEXT:
{{TEXT}}

Return JSON only. No markdown fences, no explanation.
```

Tham số: `temperature=0`, `max_tokens=1500`, bật structured output nếu API hỗ trợ.

---

## 6. Quy tắc verification

1. Chuẩn hoá cả `source_span` và `_raw_text` bằng Unicode NFC, hạ về chữ thường, gộp mọi khoảng trắng về một dấu cách.
2. Nếu span chuẩn hoá nằm trong text chuẩn hoá → `confidence = "high"`.
3. Ngược lại → `confidence = "low"` và **xoá** `source_span` về null.
4. Field low confidence **không bị xoá khỏi record**, chỉ bị gắn cờ.

Lý do bước 1 phải có NFC: tiếng Việt có hai cách mã hoá cùng một chữ có dấu. Thiếu NFC thì mọi field tiếng Việt bị flag low một cách oan uổng.

Lý do bước 4: field như `resolution = 3840x2160` suy từ chữ "4K" là suy luận đúng nhưng không có trong text. Xoá thì mất thông tin, publish như sự thật thì tự mâu thuẫn. Gắn cờ là lựa chọn thứ ba.

---

## 7. Quy tắc compose agent_text

Thứ tự ghép: tên sản phẩm → thông số (chỉ field high confidence) → chính sách → tương thích → giá và tình trạng hàng.

**Tuyệt đối không ghép mô tả marketing gốc vào.** Từ như "đắm chìm", "mượt như lụa" kéo vector về phía nhiễu, làm hỏng đúng thứ cả module đang cố sửa.

Mở ngoặc: nếu golden set cho hit rate thấp vì thiếu field, thử đưa field low confidence vào kèm chú thích rồi đo lại. Quyết bằng số, không quyết bằng cảm tính.

---

## 8. Golden set (chuẩn bị trước, file `golden_queries.json`)

Mỗi dòng test một cơ chế khác nhau. Tối thiểu 12 dòng, phải phủ đủ các nhóm sau:

| Nhóm test | Ví dụ query | Kiểm tra điều gì |
|---|---|---|
| Thông số đơn | "màn hình 144Hz" | extraction có lấy được refresh_rate |
| Thông số kết hợp | "màn 4K cắm USB-C sạc luôn laptop" | nhiều field cùng lúc |
| Tương thích | "màn hình dùng được với MacBook Pro 14" | bảng compat |
| Chính sách | "màn hình bảo hành trên 2 năm" | policy vào được embedding |
| Ràng buộc giá | "monitor gaming dưới 1000 đô" | giá có trong agent_text |
| Đa ngôn ngữ | "cheap second screen for spreadsheets" | embedding model xử lý được VI/EN |

Dòng cuối quan trọng nhất và phải chạy sớm. Nếu model embedding không xử lý được chéo ngôn ngữ thì phải đổi model, và phải biết lúc 14:00 chứ không phải lúc demo.

Cấu trúc mỗi dòng: `query`, `expect_top3` (list SKU), `tests` (ghi chú cơ chế đang test).

---

## 9. Catalog mẫu (chuẩn bị trước, file `catalog_raw.json`)

- 50 đến 200 SKU, tập trung một ngành hàng (màn hình, laptop, phụ kiện) để bảng compat có nghĩa
- Mô tả phải **thật sự lộn xộn**: văn xuôi marketing, thông số chôn trong câu, chính sách ở field riêng dạng đoạn dài
- Tên field cố tình không thống nhất giữa các record, để `FIELD_MAP` có việc làm
- **Cài sẵn 2 hoặc 3 SKU có mô tả mơ hồ**, ví dụ chỉ ghi "độ phân giải cao" không ghi số. Model sẽ đoán, verification sẽ bắt, dashboard hiện cờ vàng. Đây là 30 giây thuyết phục nhất trong demo.

Cách làm nhanh: copy mô tả thật từ trang bán lẻ điện tử, đổi tên thương hiệu.

---

## 10. Thứ tự build và mốc thời gian Day 1

| Giờ | Việc | Xong thì có |
|---|---|---|
| 09:00–09:30 | repo, env, `config.py`, `schema.py` | import chạy được |
| 09:30–10:15 | `ingest.py` | list record chuẩn hoá |
| 10:15–11:15 | `extract.py` + cache, thử 5 SKU | JSON trả về đúng dạng |
| 11:15–11:45 | `verify.py`, test bằng 1 field cố tình bịa | cơ chế flag chạy đúng |
| 11:45–12:30 | chạy full catalog ở nền, song song viết `mapper.py` | cache đầy, mapper xong |
| 12:30–13:00 | nghỉ, để pipeline chạy | |
| 13:00–13:45 | `compose.py` + `index.py` | index sẵn sàng |
| 13:45–14:30 | `evaluate.py`, chạy golden set | có hit rate thật |
| 14:30–15:30 | sửa miss (thường do agent_text thiếu field) | hit rate cải thiện |
| **15:30** | **freeze, xuất `catalog_standardized.json`** | **bàn giao module 2, 3** |
| 15:30–17:00 | đệm tích hợp, viết README phần module 1 | |

**Chốt output 15:30, không phải 17:00.** Module 2 và 3 cần thời gian ghép. Còn sửa cấu trúc lúc 16:45 nghĩa là Day 2 bắt đầu từ chỗ vỡ.

---

## 11. Phụ thuộc và điểm gãy

```
ingest ──► extract ──► verify ──► compose ──► index ──► evaluate
  │                       │                              
  └──────────────────► mapper ──────────► file bàn giao
```

- `ingest` và `mapper` là code thuần, không hỏng được
- `extract` phụ thuộc mạng và quota → **cache phải làm cùng lúc, không để sau**
- `verify` phụ thuộc `extract` có trả `source_span`
- `compose` lọc theo `confidence` nên phụ thuộc `verify`

Nếu `extract` gãy, cả chuỗi đứng. Đó là lý do chạy full catalog trước 12:30.

---

## 12. Thứ tự cắt nếu trễ

1. Bảng compatibility
2. Enrichment field chính sách
3. Confidence layer

Giữ bằng mọi giá: ingest → extract → mapper → compose → index. Đó là phần tối thiểu module 2 và 3 không chạy được nếu thiếu.

Lưu ý: cắt confidence layer là cắt luôn luận điểm anti-hallucination trong proposal. Chỉ cắt khi thật sự không còn đường nào.

---

## 13. Checklist trước 09:00 ngày 12

- [ ] `schema.md` — bộ field, kiểu dữ liệu, unitCode, quy tắc confidence
- [ ] `catalog_raw.json` — 50 đến 200 SKU, có cài SKU mô tả mơ hồ
- [ ] `prompt.md` — bản prompt ở mục 5
- [ ] `golden_queries.json` — tối thiểu 12 dòng, phủ đủ 6 nhóm test
- [ ] `compat.csv` — khoảng 30 dòng viết tay
- [ ] API key, quota, tên model đã test trên **từng** máy
- [ ] Thống nhất với module 2 và 3 về data contract ở mục 4
- [ ] Repo rỗng đã tạo, `.gitignore` sẵn, chưa có commit code nào

---

## 14. Ba lỗi hay gặp

**Model trả về markdown fence.** Luôn strip ```` ```json ```` trước khi parse, kể cả khi đã bật structured output.

**agent_text ghép nhầm mô tả gốc.** Embedding nhiễu đúng thứ mình đang cố loại. Chỉ ghép từ field đã chuẩn hoá.

**Hết quota giữa buổi.** Cache đỡ được phần lớn, nhưng vẫn phải chạy full catalog sớm.
