# ON.E Agent Gateway — Module 1: Semantic Catalog Transformation Engine
> **UAVS Hackathon 2026** | Deliverable cho **Module 2 (Merchant Dashboard)** & **Module 3 (B2A API Gateway)**

Hệ thống biến đổi danh mục sản phẩm thương mại điện tử từ dạng văn xuôi tự do, lộn xộn của con người thành dữ liệu có cấu trúc chuẩn máy đọc (**Agent-Ready & Machine-Readable**), hỗ trợ các AI Shopping Agents tìm kiếm và đóng gói combo giải pháp kèm **minh chứng xác thực nguồn gốc (Justification Payload)** và **giải trình lý do loại trừ sản phẩm (Excluded Reasons)**.

---

## 🌟 Tính Năng Nổi Bật (Key Highlights)

1. **Anti-Hallucination & Provenance Tracing (Chống ảo tưởng thông số):**
   - Mọi trường dữ liệu LLM bóc tách đều bắt buộc trích dẫn nguyên văn chuỗi ký tự nguồn (`source_span`).
   - Tầng **Verify** tự động đối chiếu `source_span` với văn bản gốc bằng chuẩn hóa **Unicode NFC** (xử lý triệt để khác biệt giữa dấu tiếng Việt dạng dựng sẵn và tổ hợp).
   - Nếu không khớp hoặc thiếu bằng chứng, trường dữ liệu lập tức bị gán cờ `low confidence` và tước bỏ `source_span`.
2. **Anti-Greenwashing Mechanism (Chống quảng cáo xanh vô căn cứ):**
   - Sử dụng tập nhãn đóng `VALUE_TAXONOMY` nghiêm ngặt cho các tuyên bố về môi trường & bền vững.
   - Chỉ những tuyên bố có trích dẫn thực tế từ mô tả nhà sản xuất mới được phép xuất hiện trong minh chứng (`values_provenance_rate`).
3. **Agent Text Composition (Loại bỏ nhiễu tiếp thị):**
   - Loại bỏ hoàn toàn các từ ngữ marketing phóng đại ("đắm chìm", "mượt như lụa") vốn gây nhiễu ma trận vector.
   - Ưu tiên mục đích sử dụng (*Outcomes*) trước thông số kỹ thuật (*Specs*).
4. **Outcome-based Bundling & Budget Management (Đóng gói Combo giải pháp):**
   - Đọc đồ thị quan hệ thiết bị (`relations.csv`), tự động mở rộng phụ kiện bắt buộc (`required_with`) và phụ kiện hoàn thiện trải nghiệm (`completes_outcome`).
   - Ràng buộc ngân sách được kiểm soát trên **Tổng giá cả bộ combo (Bundle Total)** thay vì từng sản phẩm đơn lẻ.
5. **Decoded Constraints & Explainable Retrieval (§4.3 Payload):**
   - Bộ máy tìm kiếm ngữ nghĩa (`BAAI/bge-m3`) kết hợp bộ lọc cứng (Hard filter).
   - Lọc cứng chạy **sau** tìm kiếm ngữ nghĩa để thu thập đầy đủ danh sách `excluded` giải thích lý do tại sao sản phẩm bị loại (vượt ngân sách, thiếu cổng kết nối, hết hàng).

---

## 🏗️ Kiến Trúc Luồng Xử Lý (Pipeline Architecture)

```
catalog_raw.json (63 SKU thô)
       │
       ▼
1. ingest.py      ──► Ánh xạ tên field qua FIELD_MAP, gộp _raw_text (description + warranty_raw)
       │
       ▼
2. extract.py     ──► Gemini 3.5 trích xuất specs, policy, outcomes, values kèm source_span (Cache Resumable)
       │
       ▼
3. verify.py      ──► Đối chiếu source_span vs text gốc qua Unicode NFC ──► Gán High/Low Confidence
       │
       ▼
4. compose.py     ──► Ghép agent_text súc tích từ các trường High-Confidence (loại bỏ marketing copy)
       │
       ▼
5. index.py       ──► Tạo vector nhúng với model đa ngôn ngữ BAAI/bge-m3 + NumPy Cosine Similarity
       │
       ▼
6. retrieve.py    ──► Decode truy vấn ──► Semantic Search ──► Hard Filter ──► Bundle ──► Justification
       │
       ▼
7. evaluate.py    ──► Đánh giá tự động trên 16 câu truy vấn Golden Set (3 Metrics)
       │
       ▼
run_pipeline.py   ──► Xuất file bàn giao catalog_standardized.json (Schema v2.0) cho Module 2 & 3
```

---

## 📁 Cấu Trúc Thư Mục Dự Án

```
ON.E_Agent_Gateway_module1/
├── docs/                                  # Tài liệu đặc tả và thiết kế
│   ├── MODULE1_IMPLEMENTATION_SPEC.md     # Bản đặc tả kỹ thuật chi tiết
│   └── module1_design.md                  # Bản thiết kế kiến trúc hệ thống
│
├── tests/                                 # Bộ kiểm thử tự động
│   ├── __init__.py
│   ├── test_ingest.py                     # Kiểm thử Ingest & SKU mơ hồ
│   ├── test_verify.py                     # Kiểm thử Anti-Hallucination & NFC
│   └── test_schema.py                     # Kiểm thử Enums & FIELD_MAP
│
├── data/                                  # Dữ liệu đầu vào & bộ nhớ đệm
│   ├── catalog_raw.json                   # 63 sản phẩm mẫu (Màn hình, Laptop, Phụ kiện)
│   ├── golden_queries.json                # 16 câu truy vấn đánh giá đa kịch bản
│   ├── relations.csv                      # 58 quan hệ tương thích, nâng cấp và phụ kiện
│   └── cache/                             # 63 file cache kết quả LLM trích xuất (Offline-ready)
│
├── output/                                # Sản phẩm bàn giao chính thức
│   ├── catalog_standardized.json          # File bàn giao chuẩn Schema v2.0 cho Module 2 & 3
│   ├── evaluation_report.json             # Báo cáo đánh giá 3 metrics chi tiết
│   ├── index.npy                          # Ma trận vector nhúng BGE-M3 (258 KB)
│   └── index.meta.json                    # Siêu dữ liệu vector index
│
├── config.py                              # Cấu hình hằng số, model, paths, prompt
├── schema.py                              # Closed taxonomies, FIELD_MAP, Pydantic models
├── ingest.py                              # Step 1: Đọc & làm sạch danh mục thô
├── extract.py                             # Step 2: LLM trích xuất thông tin
├── verify.py                              # Step 3: Xác thực nguồn gốc thông tin
├── compose.py                             # Step 4: Tạo văn bản cho Agent
├── index.py                               # Step 5: Xây dựng chỉ mục vector ngữ nghĩa
├── retrieve.py                            # Step 6: Bộ máy truy xuất & sinh minh chứng
├── bundle.py                              # Thuật toán đóng gói combo sản phẩm
├── evaluate.py                            # Đo lường định lượng trên Golden Set
├── mapper.py                              # Xuất định dạng chuẩn JSON-LD Schema.org
├── run_pipeline.py                        # Điều phối toàn bộ pipeline khép kín
├── demo.py                                # Kịch bản trình diễn tương tác với Giám Khảo
│
├── requirements.txt                       # Thư viện phụ thuộc
├── .env.example                           # File mẫu biến môi trường
├── .gitignore                             # Cấu hình loại trừ bí mật & file tạm
└── README.md                              # Tài liệu dự án
```

---

## 🚀 Hướng Dẫn Cài Đặt & Sử Dụng

### 1. Cài đặt môi trường
Yêu cầu: **Python 3.10+**

```powershell
# Di chuyển vào thư mục dự án
cd module1

# Cài đặt các thư viện phụ thuộc
pip install -r requirements.txt
```

### 2. Thiết lập Biến Môi Trường (Tùy chọn nếu chạy live API)
```powershell
cp .env.example .env
```
Mở file `.env` và điền khóa `GEMINI_API_KEY`:
```env
GEMINI_API_KEY=your_actual_gemini_api_key_here
```
> *Lưu ý:* Thư mục `data/cache/` đã chứa sẵn kết quả trích xuất của toàn bộ 63 sản phẩm, vì vậy hệ thống có thể chạy toàn bộ pipeline và demo **hoàn toàn offline/tức thì** mà không cần tốn quota API.

---

## 💻 Các Lệnh Thực Thi Chính

### 1. Chạy Toàn Bộ Pipeline End-to-End
Chạy tuần tự 6 bước, đánh giá Golden Set và xuất file bàn giao:
```powershell
python run_pipeline.py
```
*Tùy chọn chạy nhanh không gọi lại LLM (sử dụng cache):*
```powershell
python run_pipeline.py --skip-extract
```

### 2. Chạy Trình Diễn Tương Tác (Demo cho Ban Giám Khảo)
Hiển thị từng bước xử lý, giải thích các cơ chế cờ vàng và in Payload kết quả truy xuất:
```powershell
python demo.py
```

### 3. Chạy Toàn Bộ Bộ Kiểm Thử Tự Động (Unit Tests)
```powershell
python -m unittest discover tests
```

---

## 📊 Báo Cáo Đo Lường Chất Lượng (Evaluation Metrics)

Kết quả đánh giá trên 16 câu truy vấn mẫu (`golden_queries.json`):

| Chỉ số (Metric) | Kết quả | Ý nghĩa nghiệp vụ |
|---|---|---|
| **`retrieval_hit_rate_top3`** | **100% / High** | Tỷ lệ tìm đúng sản phẩm mục tiêu trong Top 3 kết quả trả về. |
| **`values_provenance_rate`** | **82.1%** | Tỷ lệ các tuyên bố bền vững/môi trường có trích dẫn văn bản thật (**Anti-Greenwashing**). |
| **`intent_accuracy`** | **Thỏa mãn** | Độ chính xác khi tạo bundle phụ kiện đúng theo vai trò và ngân sách. |

---

## 📑 Hợp Đồng Dữ Liệu Bàn Giao (Data Contracts)

### Contract §4.2 — Bản Ghi Sản Phẩm Chuẩn Hóa (`catalog_standardized.json`)
```json
{
  "sku": "MON-27-4K-01",
  "name": "Màn hình Dell UltraSharp 27 4K",
  "brand": "Dell",
  "category": "Màn hình",
  "price": 899,
  "currency": "AUD",
  "stock": 15,
  "specs": [
    {
      "name": "refresh_rate",
      "value": 144,
      "confidence": "high",
      "source_span": "tần số quét 144Hz"
    }
  ],
  "policy": {
    "warranty_months": { "value": 36, "confidence": "high", "source_span": "bảo hành 36 tháng" }
  },
  "outcomes": {
    "use_cases": { "value": ["office_work", "graphic_design"], "confidence": "high" }
  },
  "agent_text": "Màn hình Dell UltraSharp 27 4K (Dell) - Màn hình. Phù hợp cho: office_work..."
}
```

### Contract §4.3 — Payload Truy Xuất Thông Minh (`retrieve()`)
```json
{
  "query": "màn hình đồ hoạ dưới 1000 AUD",
  "decoded_constraints": {
    "hard": { "budget_max": 1000, "currency": "AUD", "in_stock": true },
    "soft": { "use_case": "graphic_design" }
  },
  "selected": [
    {
      "sku": "MON-27-4K-01",
      "role_in_bundle": "primary",
      "price": 899,
      "justification": [
        {
          "constraint": "use_case=graphic_design",
          "matched_field": "use_cases",
          "evidence": "chuyên cho thiết kế đồ họa",
          "confidence": "high"
        }
      ]
    }
  ],
  "bundle_total": 899,
  "excluded": [
    {
      "sku": "MON-32-4K-03",
      "reason": "price",
      "detail": "price 1299 AUD exceeds budget 1000 AUD"
    }
  ]
}
```

---

## 👥 Nhóm Tác Giả & Bản Quyền
- Dự án dự thi: **UAVS Hackathon 2026**
- Module: **Module 1 — Semantic Catalog Transformation Engine**
- GitHub Repository: [ON.E_Agent_Gateway_module1](https://github.com/phamdoducduong240406-dotcom/ON.E_Agent_Gateway_module1.git)
