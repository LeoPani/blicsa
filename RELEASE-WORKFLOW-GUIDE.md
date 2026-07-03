# Blicsa — Release Workflow Guide

This document explains how to publish a new release of Blicsa to GitHub Releases
with executables for Windows, macOS, and Linux.

---

## Files involved

| File | Role |
|------|------|
| `.github/workflows/release.yml` | GitHub Actions workflow — builds and publishes releases |
| `blicsa.spec` | PyInstaller spec — controls how executables are built |
| `installer.iss` | Inno Setup script — produces the Windows installer (optional) |
| `main.py` | Contains `__version__` — must match the git tag before releasing |

---

## Before your first release

1. **Set `__version__` in `main.py`** (already done — it is `"1.0.0"`).
2. Ensure `requirements.txt` lists all production dependencies.
3. Confirm icon files exist in `assets/branding/`:
   - `blicsa-icon.ico` (Windows)
   - `blicsa-icon.icns` (macOS)
   - `blicsa-icon-256.png` (Linux)

---

## How to publish a release

### Step 1 — Update the version in `main.py`

Open `main.py` and change the version number at the top:

```python
__version__ = "1.1.0"   # change this to your new version
```

Commit the change:

```bash
git add main.py
git commit -m "chore: bump version to 1.1.0"
git push origin main
```

### Step 2 — Create and push a git tag

```bash
git tag v1.1.0 -m "Release 1.1.0"
git push origin v1.1.0
```

That is the only command needed to trigger the release.

---

## What happens automatically

After you push the tag, GitHub Actions runs four sequential stages:

```
validate-version
    │
    ├── build-windows  ──┐
    ├── build-macos    ──┼──> create-release
    └── build-linux    ──┘
```

1. **validate-version** — confirms that `__version__` in `main.py` matches the tag.
   If they differ, the workflow fails immediately with a clear error message.

2. **build-windows** (runs on `windows-latest`)
   - Installs Python 3.11 and all dependencies.
   - Runs `pyinstaller blicsa.spec`.
   - Packages `Blicsa-onefile.exe` into `Blicsa-windows-portable.zip`.
   - If Inno Setup 6 is installed on the runner, also builds `Blicsa_Setup.exe`.

3. **build-macos** (runs on `macos-latest`)
   - Installs Python 3.11 and all dependencies.
   - Runs `pyinstaller blicsa.spec` → produces `dist/Blicsa.app`.
   - Creates `Blicsa.dmg` using macOS built-in `hdiutil`.

4. **build-linux** (runs on `ubuntu-latest`)
   - Installs system packages (`python3-tk`, `libgl1`, etc.).
   - Runs `pyinstaller blicsa.spec`.
   - Attempts to build `Blicsa-x86_64.AppImage` using AppImageKit.
   - If AppImage fails, falls back to `Blicsa-linux-x86_64.tar.gz`.

5. **create-release**
   - Downloads all artifacts from the three build jobs.
   - Calculates SHA256 checksums for every file → `CHECKSUMS.txt`.
   - Creates the GitHub Release with the tag name and uploads all files.

---

## Where to monitor progress

- Go to **https://github.com/LeoPani/PyBibliomics/actions**
- Find the workflow run named **Release** triggered by your tag.
- Click on any job to see real-time logs.

---

## Where artifacts appear

**https://github.com/LeoPani/PyBibliomics/releases**

Each release contains:

| File | Platform |
|------|----------|
| `Blicsa_Setup.exe` | Windows installer |
| `Blicsa-windows-portable.zip` | Windows portable |
| `Blicsa.exe` | Windows single executable |
| `Blicsa.dmg` | macOS disk image |
| `Blicsa-x86_64.AppImage` | Linux AppImage |
| `Blicsa-linux-x86_64.tar.gz` | Linux fallback |
| `CHECKSUMS.txt` | SHA256 hashes for all files |

---

## Verify download integrity

Download `CHECKSUMS.txt` alongside your file, then run:

```bash
# Linux / macOS
sha256sum -c CHECKSUMS.txt

# Windows (PowerShell)
Get-FileHash Blicsa_Setup.exe -Algorithm SHA256
# compare the hash manually with CHECKSUMS.txt
```

---

## Troubleshooting

### "Version mismatch" error
The tag (e.g. `v1.1.0`) does not match `__version__` in `main.py`.
Update `main.py`, commit, push, delete the bad tag, and re-tag:

```bash
git tag -d v1.1.0
git push origin :refs/tags/v1.1.0
# fix main.py, commit, push...
git tag v1.1.0 -m "Release 1.1.0"
git push origin v1.1.0
```

### macOS app does not open (Gatekeeper)
The build is unsigned. Right-click `Blicsa.app` → **Open** → **Open**.
This only needs to be done once per machine.

### Linux AppImage does not run
Make it executable first:

```bash
chmod +x Blicsa-x86_64.AppImage
./Blicsa-x86_64.AppImage
```

If it still fails (e.g. missing FUSE), use the tar.gz fallback:

```bash
tar -xzf Blicsa-linux-x86_64.tar.gz
./Blicsa-dir/Blicsa
```

### Windows Defender blocks the exe
On first run, Windows SmartScreen may show a warning because the executable is
unsigned. Click **More info** → **Run anyway**.

---

## Deferred / future improvements

| Item | Effort | Notes |
|------|--------|-------|
| macOS code signing & notarization | High | Requires Apple Developer account and certificate stored as a GitHub secret |
| Windows code signing | High | Requires EV certificate; eliminates SmartScreen warning |
| AppImage via newer tooling (appimage-builder) | Medium | Better dependency isolation than AppImageKit |
| Auto-update via Sparkle (macOS) or WinSparkle | High | Notifies users of new releases from within the app |
| Separate `dev` / `stable` release channels | Low | Use tag patterns `v*-beta` vs `v*` |
