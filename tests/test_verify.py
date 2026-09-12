"""
Unit tests for Verify step (Anti-Hallucination).
"""

import unittest
from pathlib import Path
import sys

# Add src/ to path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from verify import norm, verify_record, _verify_dict_fields


class TestVerify(unittest.TestCase):
    def test_unicode_nfc_normalization(self):
        # Composed vs decomposed Vietnamese
        decomposed = "ba\u0309o ha\u0300nh"  # bảo hành (NFD)
        composed = "bảo hành"                 # bảo hành (NFC)
        self.assertEqual(norm(decomposed), norm(composed))

    def test_high_confidence_when_span_exists(self):
        raw_text = "Màn hình Dell UltraSharp 27 inch tấm nền IPS tần số quét 144Hz chính hãng."
        specs = {
            "refresh_rate": {
                "value": 144,
                "source_span": "tần số quét 144Hz",
            },
            "panel_type": {
                "value": "IPS",
                "source_span": "tấm nền IPS",
            },
        }
        verified = _verify_dict_fields(specs, raw_text)
        self.assertEqual(verified["refresh_rate"]["confidence"], "high")
        self.assertEqual(verified["refresh_rate"]["source_span"], "tần số quét 144Hz")
        self.assertEqual(verified["panel_type"]["confidence"], "high")

    def test_fabricated_span_flagged_low(self):
        """Acceptance test: Field bịa đặt phải bị flag low và xóa source_span."""
        raw_text = "Màn hình viền mỏng độ phân giải cao phục vụ văn phòng."
        specs = {
            "resolution": {
                "value": "3840x2160",
                "source_span": "totally not in the text",
            },
        }
        verified = _verify_dict_fields(specs, raw_text)
        self.assertEqual(verified["resolution"]["confidence"], "low")
        self.assertIsNone(verified["resolution"]["source_span"], "source_span must be cleared to null")
        self.assertIn("not found", verified["resolution"].get("note", ""))

    def test_missing_span_flagged_low(self):
        raw_text = "Màn hình chuyên đồ hoạ."
        specs = {
            "skill_level": {
                "value": "pro",
                "source_span": None,
                "note": "inferred from text",
            },
        }
        verified = _verify_dict_fields(specs, raw_text)
        self.assertEqual(verified["skill_level"]["confidence"], "low")
        self.assertIsNone(verified["skill_level"]["source_span"])


if __name__ == "__main__":
    unittest.main()
