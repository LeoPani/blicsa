import hmac
import json
import logging
import time
from collections import deque
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import threading
from typing import Callable, Dict, Any, Optional
from core.sources.openalex import OpenAlexProvider

logger = logging.getLogger("BridgeServer")

#: Teto do corpo de um POST. Um registro bibliográfico com resumo cabe folgado em 1 MB; o que
#: não cabe é engano ou ataque. Sem teto, `rfile.read(Content-Length)` alocava o que o cliente
#: pedisse — 60 MB entraram na memória num teste da Auditoria 2.
LIMITE_CORPO_BYTES = 1 * 1024 * 1024

#: Profundidade máxima do JSON aceito. Um registro é raso; aninhamento de milhares de níveis
#: só serve para gastar pilha e memória do processo que hospeda a interface do usuário.
PROFUNDIDADE_MAXIMA_JSON = 40

#: Janela e teto do limitador de taxa, por processo. Não é proteção contra a internet — o
#: servidor só escuta em 127.0.0.1 — é contra extensão defeituosa em laço, que congelaria o
#: app inteiro sem nunca ter má intenção.
JANELA_TAXA_S = 10.0
MAX_PEDIDOS_NA_JANELA = 60


def profundidade_json(objeto, limite: int = PROFUNDIDADE_MAXIMA_JSON, nivel: int = 1) -> int:
    """Profundidade do objeto já decodificado, parando assim que passa do limite.

    Medir **depois** de decodificar é de propósito: o `json` do CPython usa varredura
    iterativa e não estoura a pilha, então o custo real é a memória do objeto resultante — e
    é ele que precisa ser recusado antes de seguir para o resto do app.
    """
    if nivel > limite:
        return nivel
    if isinstance(objeto, dict):
        filhos = objeto.values()
    elif isinstance(objeto, (list, tuple)):
        filhos = objeto
    else:
        return nivel
    maior = nivel
    for filho in filhos:
        maior = max(maior, profundidade_json(filho, limite, nivel + 1))
        if maior > limite:
            return maior
    return maior


class ExtensionBridgeHandler(BaseHTTPRequestHandler):
    bridge_token = ""
    on_add_record: Optional[Callable[[Dict[str, Any]], int]] = None
    on_expand: Optional[Callable[[Dict[str, Any]], Dict[str, Any]]] = None

    #: Instantes dos pedidos recentes, compartilhados por todas as instâncias do handler
    #: (o `HTTPServer` cria uma por requisição).
    _pedidos_recentes: deque = deque()
    _trava_taxa = threading.Lock()

    @classmethod
    def _dentro_do_limite_de_taxa(cls) -> bool:
        agora = time.monotonic()
        with cls._trava_taxa:
            while cls._pedidos_recentes and agora - cls._pedidos_recentes[0] > JANELA_TAXA_S:
                cls._pedidos_recentes.popleft()
            if len(cls._pedidos_recentes) >= MAX_PEDIDOS_NA_JANELA:
                return False
            cls._pedidos_recentes.append(agora)
            return True

    def _responder(self, codigo: int, corpo: bytes = b"", encerrar: bool = False):
        """Responde e, quando pedido, **fecha a conexão**.

        `encerrar=True` nas recusas que não leem o corpo (413, 429, Content-Length inválido):
        sem isso a requisição fica com bytes por subir num socket que o servidor considera
        reutilizável, e a próxima conexão espera para sempre. Medido: a suíte completa
        passou a dar `TimeoutError` no bridge depois que as recusas foram acrescentadas —
        um ataque de negação de serviço que a própria proteção criou.
        """
        if encerrar:
            self.close_connection = True
        self.send_response(codigo)
        self.send_header("Content-Type", "application/json")
        if encerrar:
            self.send_header("Connection", "close")
        self._send_cors_headers()
        self.end_headers()
        if corpo:
            self.wfile.write(corpo)

    def _send_cors_headers(self):
        origin = self.headers.get("Origin", "")
        if origin.startswith("chrome-extension://") or origin.startswith("moz-extension://"):
            self.send_header("Access-Control-Allow-Origin", origin)
        else:
            self.send_header("Access-Control-Allow-Origin", "null")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Authorization, Content-Type")

    def do_OPTIONS(self):
        self.send_response(200, "ok")
        self._send_cors_headers()
        self.end_headers()

    def _validate_token(self):
        auth_header = self.headers.get('Authorization', '')
        if not auth_header.startswith('Bearer '):
            return False
        token = auth_header.split(' ')[1]
        # `compare_digest` e não `==`: a comparação de string do Python sai no primeiro byte
        # diferente, e o tempo de resposta vaza quantos bytes iniciais o atacante acertou.
        # O servidor é local, mas qualquer processo da máquina fala com ele, e o token é o
        # que separa "extensão do usuário" de "qualquer programa que esteja rodando".
        if not self.bridge_token:
            return False
        return hmac.compare_digest(token, self.bridge_token)

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
            self._responder(401, b'{"error": "Unauthorized"}')
            return

        if not self._dentro_do_limite_de_taxa():
            self._responder(429, b'{"error": "Too many requests"}', encerrar=True)
            return

        # `int()` sem guarda: um `Content-Length: abc` levantava `ValueError` **fora** de
        # qualquer `try`, o handler morria com 500 e a conexão era cortada no meio. Medido
        # na Auditoria 2.
        try:
            content_length = int(self.headers.get('Content-Length', 0) or 0)
        except (TypeError, ValueError):
            self._responder(400, b'{"error": "Invalid Content-Length"}', encerrar=True)
            return

        if content_length < 0 or content_length > LIMITE_CORPO_BYTES:
            # Recusa ANTES de ler: o ponto do teto é não alocar o que o cliente pediu.
            self._responder(413, b'{"error": "Payload too large"}', encerrar=True)
            return

        post_data = self.rfile.read(content_length)
        try:
            data = json.loads(post_data)
        except json.JSONDecodeError:
            self._responder(400, b'{"error": "Invalid JSON"}')
            return
        except RecursionError:
            self._responder(400, b'{"error": "JSON too deep"}')
            return

        if profundidade_json(data) > PROFUNDIDADE_MAXIMA_JSON:
            self._responder(400, b'{"error": "JSON too deep"}')
            return

        if self.path == '/api/add':
            if ExtensionBridgeHandler.on_add_record:
                try:
                    # 1. Resolver o registro no OpenAlex.
                    provider = OpenAlexProvider()
                    record = None

                    # Caminho correto: lookup EXATO por DOI (não busca textual).
                    if data.get('doi'):
                        record = provider.get_by_doi(data['doi'])

                    # Fallback só se o DOI falhou (ou não veio): título + autor.
                    if record is None and data.get('title'):
                        query = f"TITLE(\"{data['title']}\")"
                        if data.get('authors'):
                            first_author = str(data['authors']).split(';')[0].strip()
                            if first_author:
                                query += f" AND AUTHOR(\"{first_author}\")"
                        results = list(provider.search(query=query, max_results=1))
                        record = results[0] if results else None

                    if record is None and not (data.get('doi') or data.get('title')):
                        raise ValueError("Missing doi or title in payload")
                    if record is None:
                        raise ValueError("Paper not found in OpenAlex")

                    # Preserva a URL de origem (página onde o usuário clicou).
                    if data.get('source_url'):
                        record['origin_url'] = data['source_url']

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
        # `ThreadingHTTPServer`: com o servidor de thread única, uma requisição lenta
        # (ou meio recusada) bloqueava todas as seguintes.
        self.server = ThreadingHTTPServer(('127.0.0.1', self.port), ExtensionBridgeHandler)
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
