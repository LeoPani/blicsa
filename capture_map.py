import asyncio
from playwright.async_api import async_playwright
import os

async def main():
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        page = await browser.new_page(viewport={"width": 1024, "height": 768})
        
        # Start a local simple HTTP server in Python to serve the assets dir
        # Because fetching graph.json from file:// usually gives CORS error in browser
        
        import threading
        from http.server import SimpleHTTPRequestHandler
        from socketserver import TCPServer
        
        class Handler(SimpleHTTPRequestHandler):
            def __init__(self, *args, **kwargs):
                super().__init__(*args, directory=os.path.abspath("assets"), **kwargs)
                
            def log_message(self, format, *args):
                pass
                
        httpd = TCPServer(("", 8888), Handler)
        thread = threading.Thread(target=httpd.serve_forever)
        thread.daemon = True
        thread.start()
        
        try:
            await page.goto("http://localhost:8888/map_template.html")
            await page.wait_for_timeout(3000) # Wait for Sigma.js to render
            os.makedirs("docs/evidence", exist_ok=True)
            await page.screenshot(path="docs/evidence/verif_mapa_ok.png")
            print("Screenshot saved to docs/evidence/verif_mapa_ok.png")
        finally:
            httpd.shutdown()
            httpd.server_close()
            await browser.close()

if __name__ == "__main__":
    asyncio.run(main())
