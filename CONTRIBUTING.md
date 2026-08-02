# Contributing to Blicsa (PyBibliomics)

Thank you for your interest in contributing to Blicsa! Here are some guidelines to help you get started.

## Development Environment Setup

1. Clone the repository.
2. Install the required dependencies:
   ```bash
   pip install -r requirements.txt
   ```
3. Run the application:
   ```bash
   python main.py
   ```

## Running Tests

We use Python's built-in `unittest` framework. Run all tests with:
```bash
python -m unittest discover tests
```

## Creating a Pull Request

1. Fork the repository and create a branch.
2. Implement your changes.
3. Make sure all tests pass.
4. Submit a pull request with a detailed description of your changes.

## Evidências visuais

Capturas em `docs/evidence/` são **sempre da janela do app**, nunca da tela inteira.

No macOS, isso significa `screencapture -l <CGWindowID>`. **Não use `-R` com coordenadas** —
esse modo grava o que estiver naquela região da tela, e já aconteceu de uma captura
automatizada registrar o navegador do desenvolvedor em vez do app. O modo de falha é
silencioso: a imagem tem variância, passa em qualquer teste de "não está em branco", e só um
olho humano percebe.

Se o `CGWindowID` não for encontrado, **falhe** em vez de capturar coordenadas.

Antes de commitar uma evidência:

```bash
python3 scripts/check_evidence_privacy.py            # reprova captura de tela cheia
python3 scripts/check_evidence_privacy.py --historico  # inclui blobs antigos do git
```

O verificador reprova imagem com dimensões de tela cheia ou com o fundo papel `#F6F4EE`
abaixo do limiar. Exceções legítimas (tema tinta, modo pôster) são declaradas no próprio
script, com o motivo.

## Segredos

Nenhuma chave, token ou senha entra em commit. As chaves ficam em `.env` (Groq) e no
`settings.json` do usuário, fora do repositório — ambos no `.gitignore`.

```bash
python3 scripts/check_secrets.py              # arquivos rastreados
python3 scripts/check_secrets.py --historico  # todos os commits
```

Os dois verificadores rodam no CI e quebram o build.

**Se uma chave real já foi commitada:** removê-la num commit novo **não basta**. O conteúdo
continua no histórico e acessível por `git show`. Revogue a chave e gere outra — chave que já
esteve num arquivo versionado deve ser considerada comprometida.
