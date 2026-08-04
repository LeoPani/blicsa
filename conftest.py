"""Coloca a raiz do repositório no `sys.path` para a suíte de testes.

Sem isto, `pytest tests/` falha com `ModuleNotFoundError: No module named 'core'`, enquanto
`python -m pytest tests/` funciona — a diferença é que `python -m` insere o diretório atual no
`sys.path` e o executável `pytest` não. O projeto não é instalado como pacote (roda de dentro
do diretório, via `python3 main.py`), então nada mais coloca a raiz lá.

O custo dessa diferença foi concreto: o CI chamava `pytest tests/` e quebrava na coleção dos
32 módulos de teste, mas isso ficou **escondido atrás de outra falha** — o build já morria
antes, em `Install dependencies`, por causa da matriz com Python 3.10. Corrigida a primeira
camada, a segunda apareceu.

Um `conftest.py` na raiz resolve para as duas formas de invocar, inclusive a de quem clona o
repositório e digita `pytest` por hábito.
"""

import sys
from pathlib import Path

RAIZ = Path(__file__).resolve().parent
if str(RAIZ) not in sys.path:
    sys.path.insert(0, str(RAIZ))
