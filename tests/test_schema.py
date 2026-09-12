"""
Unit tests for Schema and Closed Taxonomies.
"""

import unittest
from pathlib import Path
import sys

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import schema


class TestSchema(unittest.TestCase):
    def test_enums_non_empty(self):
        self.assertGreater(len(schema.VALUE_TAXONOMY), 0)
        self.assertGreater(len(schema.USE_CASES), 0)
        self.assertGreater(len(schema.SKILL_LEVELS), 0)
        self.assertGreater(len(schema.ENVIRONMENTS), 0)
        self.assertGreater(len(schema.RELATION_TYPES), 0)
        self.assertGreater(len(schema.UNIT_CODES), 0)

    def test_field_map_covers_required(self):
        required_keys = [
            "item_code", "product_id", "sku_no", "title", "product_name",
            "mfr", "manufacturer", "long_desc", "desc_html", "warranty_blob",
        ]
        for key in required_keys:
            self.assertIn(key, schema.FIELD_MAP, f"Required key '{key}' missing from FIELD_MAP")

    def test_field_map_canonical_values(self):
        self.assertEqual(schema.FIELD_MAP["item_code"], "sku")
        self.assertEqual(schema.FIELD_MAP["title"], "name")
        self.assertEqual(schema.FIELD_MAP["mfr"], "brand")
        self.assertEqual(schema.FIELD_MAP["long_desc"], "description")
        self.assertEqual(schema.FIELD_MAP["warranty_blob"], "warranty_raw")


if __name__ == "__main__":
    unittest.main()
