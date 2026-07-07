import os
import time
import threading
import http.server
import socketserver
from playwright.sync_api import sync_playwright
import pandas as pd
from core.matrix_builders import NetworkGenerator
from core.visualizer import compute_fa2_layout
from core.sigma_exporter import export_sigma_json

PORT = 8000
DIRECTORY = "assets"

class Handler(http.server.SimpleHTTPRequestHandler):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory=DIRECTORY, **kwargs)

def start_server():
    with socketserver.TCPServer(("", PORT), Handler) as httpd:
        httpd.serve_forever()

def capture():
    # Setup graph
    df = pd.read_csv("docs/sample_dataset.csv")
    gen = NetworkGenerator(df)
    gen.build_keyword_cooccurrence(field="keywords", min_occurrence=1)
    
    positions = compute_fa2_layout(gen.G)
    export_sigma_json(gen.G, positions, "assets/graph.json")
    
    # Start server
    server_thread = threading.Thread(target=start_server, daemon=True)
    server_thread.start()
    
    # Capture screenshot
    with sync_playwright() as p:
        browser = p.chromium.launch()
        page = browser.new_page()
        page.goto(f"http://localhost:{PORT}/map_template.html")
        time.sleep(3) # Wait for Sigma.js to render
        os.makedirs("docs/evidence", exist_ok=True)
        page.screenshot(path="docs/evidence/fase0_mapa_ok.png")
        browser.close()

if __name__ == "__main__":
    capture()
