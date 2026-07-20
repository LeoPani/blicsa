"""Servidor HTTP local do Blicsa.

SEGURANÇA: serve APENAS um diretório dedicado (~/Blicsa/.serve), para onde o
app copia só o que o navegador/webview precisa (map_template.html, map.js,
graph.json e mapas da galeria). Nunca a raiz do repositório — settings com
API key, código e projetos ficam fora do alcance de outros processos locais
e de DNS rebinding via navegador.
"""
import http.server
import shutil
import socketserver
import threading
from pathlib import Path

DEFAULT_SERVE_DIR = Path.home() / "Blicsa" / ".serve"

# Únicos arquivos estáticos copiados do repo para o diretório servido.
STATIC_ASSETS = ("map_template.html", "map_template_empty.html", "map.js", "graph_empty.json")


def _copy_writable(src: Path, dest: Path) -> None:
    """Copia src→dest garantindo destino gravável.

    Num app instalado o código é somente-leitura: shutil.copy2 copiaria esse bit
    read-only para o destino e a próxima cópia falharia. Usamos copyfile (não
    copia permissões) e forçamos 0o644 no destino.
    """
    dest.parent.mkdir(parents=True, exist_ok=True)
    if dest.exists():
        dest.chmod(0o644)
    shutil.copyfile(src, dest)
    dest.chmod(0o644)


def prepare_serve_dir(app_root, serve_dir=None) -> Path:
    """Cria o diretório dedicado e copia só os estáticos do webview."""
    serve_dir = Path(serve_dir or DEFAULT_SERVE_DIR)
    (serve_dir / "assets").mkdir(parents=True, exist_ok=True)
    (serve_dir / "gallery").mkdir(parents=True, exist_ok=True)
    for name in STATIC_ASSETS:
        src = Path(app_root) / "assets" / name
        if src.exists():
            _copy_writable(src, serve_dir / "assets" / name)

    # Vendors locais (graphology + sigma). Sem eles o mapa Sigma não renderiza
    # offline — são a espinha do local-first deste passo.
    vendor_src = Path(app_root) / "assets" / "vendor"
    if vendor_src.is_dir():
        for src in sorted(vendor_src.iterdir()):
            if src.is_file():
                _copy_writable(src, serve_dir / "assets" / "vendor" / src.name)

    return serve_dir


def start_server(serve_dir) -> tuple[int, socketserver.TCPServer]:
    """Sobe o server numa porta efêmera de 127.0.0.1 servindo APENAS serve_dir.
    Retorna (porta, httpd); o loop roda em thread daemon."""
    directory = str(serve_dir)

    class Handler(http.server.SimpleHTTPRequestHandler):
        def __init__(self, *args, **kwargs):
            super().__init__(*args, directory=directory, **kwargs)

        def log_message(self, *args):
            pass  # sem ruído por request

    socketserver.TCPServer.allow_reuse_address = True
    httpd = socketserver.TCPServer(("127.0.0.1", 0), Handler)
    port = httpd.server_address[1]
    threading.Thread(target=httpd.serve_forever, daemon=True).start()
    return port, httpd
