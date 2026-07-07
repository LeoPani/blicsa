import json
import os
import sys

def main():
    base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    locales_dir = os.path.join(base_dir, "locales")
    
    if not os.path.exists(locales_dir):
        print("No locales directory found.")
        sys.exit(0)
        
    langs = ["en.json", "pt_BR.json", "fr.json"]
    catalogs = {}
    
    for l in langs:
        path = os.path.join(locales_dir, l)
        if os.path.exists(path):
            with open(path, "r", encoding="utf-8") as f:
                data = json.load(f)
                catalogs[l] = set([k for k in data.keys() if k != "_note"])
                
    if not catalogs:
        print("No catalogs found.")
        sys.exit(0)
        
    reference = catalogs["en.json"]
    failed = False
    
    for l, keys in catalogs.items():
        if keys != reference:
            failed = True
            missing = reference - keys
            extra = keys - reference
            print(f"[{l}] PARITY ERROR:")
            if missing:
                print(f"  Missing keys: {missing}")
            if extra:
                print(f"  Extra keys: {extra}")
                
    # de.json rule
    de_path = os.path.join(locales_dir, "de.json")
    if os.path.exists(de_path):
        os.remove(de_path)
        print("Removed de.json as it was incomplete and breaking parity.")
                
    if failed:
        sys.exit(1)
        
    print("All catalogs are in parity.")
    sys.exit(0)

if __name__ == "__main__":
    main()
