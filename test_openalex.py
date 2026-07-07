import sys
import threading
from core.sources.openalex import OpenAlexProvider

def test():
    provider = OpenAlexProvider()
    print("Testing OpenAlexProvider search")
    results = []
    
    def progress_cb(current, total):
        print(f"Fetched {current}/{total}")
    
    for r in provider.search(query="bibliometrics", max_results=200, progress_cb=progress_cb, cancel_event=threading.Event()):
        results.append(r)
        
    print(f"Final results: {len(results)}")

if __name__ == "__main__":
    test()
