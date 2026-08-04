# Installation

*Versão em português: [instalacao.md](instalacao.md)*

**Common requirement: Python 3.11 or newer.** The pinned scientific stack (`numpy`, `pandas`,
`scipy`, `networkx`) declares `requires-python >=3.11`; on 3.10 `pip install` fails to resolve
the dependencies.

```bash
python3 --version      # must report 3.11.x or newer
```

---

## Option 1 — Prebuilt executable (simplest)

Download the file for your platform from the
[releases page](https://github.com/LeoPani/blicsa/releases). No Python installation needed.

### Windows

1. Download `Blicsa-windows.exe`.
2. Run it. SmartScreen may warn that the publisher is unknown — this is expected, the
   executable is not code-signed. Click **More info → Run anyway**.

### macOS

1. Download `Blicsa-macos.zip` and unzip it.
2. **Do not double-click it the first time.** Right-click `Blicsa.app` → **Open** → **Open**
   again in the dialog that appears.

   Why: the app is **neither signed nor notarised** by Apple. On a double-click, macOS refuses
   with *"cannot be opened because it is from an unidentified developer"* and offers no way
   forward. Through the context menu, the system offers the exception. You only need to do
   this **once**; afterwards the app opens normally.

3. If it is still blocked, clear the quarantine flag from the terminal:

   ```bash
   xattr -dr com.apple.quarantine /path/to/Blicsa.app
   ```

### Linux

1. Download `Blicsa-linux`.
2. Make it executable and run it:

   ```bash
   chmod +x Blicsa-linux
   ./Blicsa-linux
   ```

---

## Option 2 — From source

```bash
git clone https://github.com/LeoPani/blicsa.git
cd blicsa
python3 -m venv .venv && source .venv/bin/activate     # Windows: .venv\Scripts\activate
pip install -r requirements-core.txt
python3 main.py
```

To run the test suite as well:

```bash
pip install -r requirements-dev.txt
python -m pytest tests/ -q
```

### What each requirements file covers

| file | purpose |
|---|---|
| `requirements-core.txt` | the working app: interface, analyses, maps, export |
| `requirements.txt` | core plus optional extras (AI, PDF reading) |
| `requirements-dev.txt` | test dependencies only |

---

## Troubleshooting

### `ModuleNotFoundError: No module named 'core'`

You ran `pytest` from another directory, or the root `conftest.py` was not found. Always run
from the repository root.

### `ERROR: Could not find a version that satisfies the requirement networkx==3.6.1`

Python 3.10 or older. See the requirement at the top of this page.

### `_tkinter.TclError: no display name and no $DISPLAY environment variable`

Linux without a graphical server. Blicsa is a desktop app and needs one. On a server, use
`xvfb-run python3 main.py` — but the interface will not be visible, so this is only useful for
tests.

### The window opens blank, or the map does not render

The map uses an embedded browser component (`pywebview`). On Linux, install WebKit:

```bash
sudo apt install python3-gi gir1.2-webkit2-4.0        # Debian/Ubuntu
```

### macOS: "is damaged and can't be opened"

That is the Gatekeeper quarantine flag, not actual file corruption. Use the `xattr` command
above.

### The app opens in an unexpected language

The language lives in **Settings → Language** and is stored under the `lang` key in
`~/Library/Application Support/blicsa/settings.json` (macOS),
`%APPDATA%\blicsa\settings.json` (Windows) or `~/.config/blicsa/settings.json` (Linux).
Deleting the file makes the app fall back to the system language.
