"""
Unit tests for Ingest step.
"""

import unittest
from pathlib import Path
import sys

# Add src/ to path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from config import CATALOG_RAW_PATH
from ingest import load_catalog, normalize_record, ingest


class TestIngest(unittest.TestCase):
    def test_load_catalog(self):
        records = load_catalog(CATALOG_RAW_PATH)
        self.assertGreater(len(records), 0, "Catalog should not be empty")
        self.assertEqual(len(records), 63, "Expected 63 records in catalog_raw.json")

    def test_normalize_record(self):
        sample = {
            "mã sản phẩm": "TEST-01",
            "tên sản phẩm": "Màn hình Test",
            "mô tả": "Mô tả sản phẩm test",
            "bảo hành": "Bảo hành 24 tháng chính hãng",
        }
        normalized = normalize_record(sample)
        self.assertIsNotNone(normalized)
        self.assertEqual(normalized["sku"], "TEST-01")
        self.assertEqual(normalized["name"], "Màn hình Test")
        self.assertIn("_raw_text", normalized)
        self.assertIn("Mô tả sản phẩm test", normalized["_raw_text"])
        self.assertIn("Bảo hành 24 tháng chính hãng", normalized["_raw_text"])

    def test_normalize_record_drops_missing_sku(self):
        sample = {
            "tên sản phẩm": "Sản phẩm không có mã",
            "mô tả": "Mô tả",
        }
        normalized = normalize_record(sample)
        self.assertIsNone(normalized, "Record without SKU must be dropped")

    def test_ingest_all_records_valid(self):
        records = ingest(CATALOG_RAW_PATH)
        self.assertEqual(len(records), 63)
        for r in records:
            self.assertIn("sku", r, f"Record missing SKU: {r.get('name')}")
            self.assertTrue(len(r["sku"]) > 0, "SKU must not be empty")
            self.assertIn("_raw_text", r, f"Missing _raw_text in {r['sku']}")
            self.assertGreater(len(r["_raw_text"]), 0, f"Empty _raw_text in {r['sku']}")

    def test_vague_skus_present(self):
        """Kiểm tra 3 SKU có mô tả mơ hồ được cài cắm cho bài test Anti-Hallucination."""
        records = ingest(CATALOG_RAW_PATH)
        skus = {r["sku"] for r in records}
        vague_skus = ["MON-27-4K-08", "MON-27-GAME-24", "LAP-ACER-14"]
        for v in vague_skus:
            self.assertIn(v, skus, f"Vague SKU {v} must be present in raw catalog")


if __name__ == "__main__":
    unittest.main()
