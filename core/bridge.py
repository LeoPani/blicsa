import json
import logging
from http.server import BaseHTTPRequestHandler, HTTPServer
import threading
from typing import Callable, Dict, Any, Optional
from core.sources.openalex import OpenAlexProvider

logger = logging.getLogger("BridgeServer")

class ExtensionBridgeHandler(BaseHTTPRequestHandler):
    bridge_token = ""
    on_add_record: Optional[Callable[[Dict[str, Any]], int]] = None
    on_expand: Optional[Callable[[Dict[str, Any]], Dict[str, Any]]] = None
    
    def _send_cors_headers(self):
        self.send_header('Access-Control-Allow-Origin', '*')
        self.send_header('Access-Control-Allow-Methods', 'GET, POST, OPTIONS')
        self.send_header('Access-Control-Allow-Headers', 'Authorization, Content-Type')

    def do_OPTIONS(self):
        self.send_response(200, "ok")
        self._send_cors_headers()
        self.end_headers()

    def _validate_token(self):
        auth_header = self.headers.get('Authorization', '')
        if not auth_header.startswith('Bearer '):
            return False
        token = auth_header.split(' ')[1]
        return token == self.bridge_token

    def do_GET(self):
        if self.path == '/api/status':
            if not self._validate_token():
                self.send_response(401)
                self._send_cors_headers()
                self.end_headers()
                self.wfile.write(b'{"error": "Unauthorized"}')
                return
            
            self.send_response(200)
            self.send_header('Content-Type', 'application/json')
            self._send_cors_headers()
            self.end_headers()
            self.wfile.write(b'{"status": "ok", "version": "1.0"}')
        else:
            self.send_response(404)
            self._send_cors_headers()
            self.end_headers()

    def do_POST(self):
        if not self._validate_token():
            self.send_response(401)
            self._send_cors_headers()
            self.end_headers()
            self.wfile.write(b'{"error": "Unauthorized"}')
            return

        content_length = int(self.headers.get('Content-Length', 0))
        post_data = self.rfile.read(content_length)
        try:
            data = json.loads(post_data)
        except json.JSONDecodeError:
            self.send_response(400)
            self._send_cors_headers()
            self.end_headers()
            self.wfile.write(b'{"error": "Invalid JSON"}')
            return

        if self.path == '/api/add':
            if ExtensionBridgeHandler.on_add_record:
                try:
                    # 1. Fetch OpenAlex
                    provider = OpenAlexProvider()
                    query = ""
                    if data.get('doi'):
                        # Using doi prefix to search by DOI accurately
                        doi = data['doi'].replace('https://doi.org/', '')
                        query = f"doi:{doi}"
                    elif data.get('title'):
                        query = f"TITLE(\"{data['title']}\")"
                        if data.get('authors'):
                            query += f" AND AUTHOR(\"{data['authors']}\")"
                    
                    if not query:
                        raise ValueError("Missing doi or title in payload")
                        
                    records = list(provider.search(query=query, max_results=1))
                    if not records:
                        raise ValueError("Paper not found in OpenAlex")
                        
                    record = records[0]
                    
                    # 2. Dedupe & Add (delegated to callback)
                    # The callback should return the new count of the active corpus
                    new_count = ExtensionBridgeHandler.on_add_record(record)
                    
                    result = {
                        "added": 1, 
                        "count": new_count, 
                        "title": record.get("title"),
                        "doi": record.get("doi")
                    }
                    self.send_response(200)
                    self.send_header('Content-Type', 'application/json')
                    self._send_cors_headers()
                    self.end_headers()
                    self.wfile.write(json.dumps(result).encode('utf-8'))
                except Exception as e:
                    logger.error(f"Error in /api/add: {e}")
                    self.send_response(500)
                    self._send_cors_headers()
                    self.end_headers()
                    self.wfile.write(json.dumps({"error": str(e)}).encode('utf-8'))
            else:
                self.send_response(500)
                self._send_cors_headers()
                self.end_headers()
                self.wfile.write(b'{"error": "on_add_record callback not configured"}')
                
        elif self.path == '/api/expand':
            if ExtensionBridgeHandler.on_expand:
                try:
                    result = ExtensionBridgeHandler.on_expand(data)
                    self.send_response(200)
                    self.send_header('Content-Type', 'application/json')
                    self._send_cors_headers()
                    self.end_headers()
                    self.wfile.write(json.dumps(result).encode('utf-8'))
                except Exception as e:
                    logger.error(f"Error in /api/expand: {e}")
                    self.send_response(500)
                    self._send_cors_headers()
                    self.end_headers()
                    self.wfile.write(json.dumps({"error": str(e)}).encode('utf-8'))
            else:
                self.send_response(500)
                self._send_cors_headers()
                self.end_headers()
                self.wfile.write(b'{"error": "on_expand callback not configured"}')
        else:
            self.send_response(404)
            self._send_cors_headers()
            self.end_headers()


class BridgeServer:
    def __init__(self, token: str, port: int = 8765):
        self.port = port
        self.token = token
        self.server = None
        self.thread = None
        ExtensionBridgeHandler.bridge_token = token
        
    def set_callbacks(self, on_add_record: Callable[[Dict[str, Any]], int], on_expand: Optional[Callable[[Dict[str, Any]], Dict[str, Any]]] = None):
        ExtensionBridgeHandler.on_add_record = on_add_record
        ExtensionBridgeHandler.on_expand = on_expand

    def start(self):
        if self.server:
            return
        self.server = HTTPServer(('127.0.0.1', self.port), ExtensionBridgeHandler)
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()
        logger.info(f"Bridge server started on port {self.port}")

    def stop(self):
        if self.server:
            self.server.shutdown()
            self.server.server_close()
            self.server = None
        if self.thread:
            self.thread.join()
            self.thread = None
        logger.info("Bridge server stopped")
