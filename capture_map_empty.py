import asyncio
from playwright.async_api import async_playwright
import os
import networkx as nx
from core.sigma_exporter import export_sigma_json

async def main():
    # Generate empty graph
    G = nx.Graph()
    export_sigma_json(G, {}, "assets/graph_empty.json")
    
    # modify assets/map_template.html to load graph_empty.json
    with open("assets/map_template.html", "r") as f:
        html = f.read()
    with open("assets/map_template_empty.html", "w") as f:
        f.write(html.replace("graph.json", "graph_empty.json"))
        
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        page = await browser.new_page(viewport={"width": 1024, "height": 768})
        
        import threading
        from http.server import SimpleHTTPRequestHandler
        from socketserver import TCPServer
        
        class Handler(SimpleHTTPRequestHandler):
            def __init__(self, *args, **kwargs):
                super().__init__(*args, directory=os.path.abspath("assets"), **kwargs)
                
            def log_message(self, format, *args):
                pass
                
        httpd = TCPServer(("", 8889), Handler)
        thread = threading.Thread(target=httpd.serve_forever)
        thread.daemon = True
        thread.start()
        
        try:
            await page.goto("http://localhost:8889/map_template_empty.html")
            await page.wait_for_timeout(2000)
            os.makedirs("docs/evidence", exist_ok=True)
            await page.screenshot(path="docs/evidence/verif_mapa_vazio.png")
            print("Screenshot saved to docs/evidence/verif_mapa_vazio.png")
        finally:
            httpd.shutdown()
            httpd.server_close()
            await browser.close()
            
if __name__ == "__main__":
    asyncio.run(main())
