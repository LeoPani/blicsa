# Instalação

*English version: [installation.md](installation.md)*

**Requisito comum: Python 3.11 ou superior.** As bibliotecas científicas fixadas
(`numpy`, `pandas`, `scipy`, `networkx`) declaram `requires-python >=3.11`; em 3.10 o
`pip install` falha ao resolver as dependências.

```bash
python3 --version      # precisa dizer 3.11.x ou mais
```

---

## Opção 1 — Executável pronto (mais simples)

Baixe o arquivo da sua plataforma na [página de releases](https://github.com/LeoPani/blicsa/releases).
Não precisa de Python instalado.

### Windows

1. Baixe `Blicsa-windows.exe`.
2. Execute. O SmartScreen pode avisar que o publicador é desconhecido — é esperado, o
   executável não tem assinatura de código. Clique em **Mais informações → Executar assim mesmo**.

### macOS

1. Baixe `Blicsa-macos.zip` e descompacte.
2. **Não abra com duplo clique na primeira vez.** Clique com o botão direito em `Blicsa.app`
   → **Abrir** → **Abrir** de novo na caixa que aparece.

   O motivo: o app **não é assinado nem notarizado** pela Apple. Com duplo clique, o macOS
   recusa com *"não pode ser aberto porque é de um desenvolvedor não identificado"* e não
   oferece alternativa. Pelo menu de contexto, o sistema oferece a exceção. Você só precisa
   fazer isso **uma vez**; depois o app abre normalmente.

3. Se ainda assim for bloqueado, libere pelo terminal:

   ```bash
   xattr -dr com.apple.quarantine /caminho/para/Blicsa.app
   ```

### Linux

1. Baixe `Blicsa-linux`.
2. Dê permissão de execução e rode:

   ```bash
   chmod +x Blicsa-linux
   ./Blicsa-linux
   ```

---

## Opção 2 — A partir do código

```bash
git clone https://github.com/LeoPani/blicsa.git
cd blicsa
python3 -m venv .venv && source .venv/bin/activate     # Windows: .venv\Scripts\activate
pip install -r requirements-core.txt
python3 main.py
```

Para rodar os testes também:

```bash
pip install -r requirements-dev.txt
python -m pytest tests/ -q
```

### O que cada arquivo de dependências traz

| arquivo | para quê |
|---|---|
| `requirements-core.txt` | o app funcionando: interface, análises, mapas, exportação |
| `requirements.txt` | o núcleo mais os extras (IA, leitura de PDF) |
| `requirements-dev.txt` | só para rodar os testes |

---

## Solução de problemas

### `ModuleNotFoundError: No module named 'core'`

Você rodou `pytest` a partir de outro diretório, ou o `conftest.py` da raiz não foi
encontrado. Rode sempre da raiz do repositório.

### `ERROR: Could not find a version that satisfies the requirement networkx==3.6.1`

Python 3.10 ou anterior. Veja o requisito no topo desta página.

### `_tkinter.TclError: no display name and no $DISPLAY environment variable`

Linux sem servidor gráfico. O Blicsa é um app de desktop e precisa de um. Em servidor, use
`xvfb-run python3 main.py` — mas a interface não será visível, então isso só serve para testes.

### A janela abre em branco ou o mapa não aparece

O mapa usa um componente de navegador embutido (`pywebview`). No Linux, instale o WebKit:

```bash
sudo apt install python3-gi gir1.2-webkit2-4.0        # Debian/Ubuntu
```

### macOS: "está danificado e não pode ser aberto"

É a quarentena do Gatekeeper, não corrupção real do arquivo. Use o comando `xattr` acima.

### O app abre em outro idioma

O idioma fica em **Configurações → Idioma** e é gravado em
`~/Library/Application Support/blicsa/settings.json` (macOS),
`%APPDATA%\blicsa\settings.json` (Windows) ou `~/.config/blicsa/settings.json` (Linux),
na chave `lang`. Apagar o arquivo faz o app voltar ao idioma do sistema.
