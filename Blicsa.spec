import sys
# -*- mode: python ; coding: utf-8 -*-
from PyInstaller.utils.hooks import collect_all
import os

datas = []
binaries = []
hiddenimports = []

# Bundle locales if folder exists
if os.path.exists('locales'):
    datas.append(('locales', 'locales'))

# Bundle customtkinter and tkinterdnd2
tmp_ret = collect_all('customtkinter')
datas += tmp_ret[0]; binaries += tmp_ret[1]; hiddenimports += tmp_ret[2]
tmp_ret = collect_all('tkinterdnd2')
datas += tmp_ret[0]; binaries += tmp_ret[1]; hiddenimports += tmp_ret[2]

hiddenimports += [
    'core.parsers',
    'core.matrix_builders',
    'core.visualizer',
    'core.nlp',
    'core.sources',
    'core.sources.base',
    'core.sources.openalex',
    'core.sources.crossref',
    'core.sources.pubmed',
]

a = Analysis(
    ['main.py'],
    pathex=[],
    binaries=binaries,
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    noarchive=False,
    optimize=0,
)
pyz = PYZ(a.pure)

# Onefile target
exe_onefile = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.datas,
    [],
    name='Blicsa-onefile',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)

# Onedir target
exe_onedir = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name='Blicsa',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)

coll = COLLECT(
    exe_onedir,
    a.binaries,
    a.zipfiles,
    a.datas,
    strip=False,
    upx=True,
    upx_exclude=[],
    name='Blicsa-dir',
)

app = BUNDLE(
    coll,
    name='Blicsa.app',
    icon='assets/branding/blicsa-icon.icns' if sys.platform == 'darwin' else 'assets/branding/blicsa-icon.ico',
    bundle_identifier=None,
)
