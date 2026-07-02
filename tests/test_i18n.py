import unittest
import json
import os

class TestI18nCompatibility(unittest.TestCase):

    def test_keys_match(self):
        # Locate files
        base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        locales_dir = os.path.join(base_dir, "locales")
        
        en_path = os.path.join(locales_dir, "en.json")
        pt_path = os.path.join(locales_dir, "pt_BR.json")
        
        self.assertTrue(os.path.exists(en_path), "en.json should exist")
        self.assertTrue(os.path.exists(pt_path), "pt_BR.json should exist")
        
        with open(en_path, "r", encoding="utf-8") as f:
            en_data = json.load(f)
            
        with open(pt_path, "r", encoding="utf-8") as f:
            pt_data = json.load(f)
            
        en_keys = set(en_data.keys())
        pt_keys = set(pt_data.keys())
        
        # Check that both catalogs have exactly the same keys
        missing_in_pt = en_keys - pt_keys
        missing_in_en = pt_keys - en_keys
        
        self.assertEqual(len(missing_in_pt), 0, f"Keys present in en.json but missing in pt_BR.json: {missing_in_pt}")
        self.assertEqual(len(missing_in_en), 0, f"Keys present in pt_BR.json but missing in en.json: {missing_in_en}")

if __name__ == '__main__':
    unittest.main()
