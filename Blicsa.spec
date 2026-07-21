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
# assets/ COMPLETO — inclui assets/vendor/ (graphology+sigma do passo 5),
# branding, fontes, ícones, templates do webview e map.js.
if os.path.exists('assets'):
    datas.append(('assets', 'assets'))
# Dataset de exemplo para o usuário testar o app sem dados próprios.
if os.path.exists('docs/sample_dataset.csv'):
    datas.append(('docs/sample_dataset.csv', 'docs'))

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

# Extras ai+pdf: importados de forma lazy (dentro de funções), então o
# PyInstaller não os enxerga sozinho. Declaramos os que ESTIVEREM instalados no
# ambiente de build para entrarem no bundle — o usuário final não roda pip.
import importlib.util as _ilu

def _has(mod):
    try:
        return _ilu.find_spec(mod) is not None
    except (ImportError, ValueError):
        return False

# PDF (requirements-pdf.txt)
if _has('pdfplumber'):
    tmp_ret = collect_all('pdfplumber')
    datas += tmp_ret[0]; binaries += tmp_ret[1]; hiddenimports += tmp_ret[2]
    hiddenimports += ['pdfplumber', 'pdfminer', 'pdfminer.six']

# IA — LDA/TF-IDF (scikit-learn, parte do requirements-ai.txt)
if _has('sklearn'):
    hiddenimports += [
        'sklearn',
        'sklearn.decomposition',
        'sklearn.feature_extraction.text',
        'sklearn.metrics.pairwise',
        'sklearn.utils._typedefs',
        'sklearn.utils._heap',
        'sklearn.utils._sorting',
        'sklearn.utils._vector_sentinel',
        'sklearn.neighbors._partition_nodes',
    ]

# IA — embeddings (sentence-transformers) NÃO é empacotado de propósito: puxa
# torch (multi-GB) e torna o onefile frágil/enorme, sem entrar no teste de
# fumaça nem no fluxo básico (busca+mapa). Excluímos explicitamente para o
# bundle ficar leve e o build confiável mesmo com o pacote instalado no ambiente.
excludes = ['torch', 'sentence_transformers', 'transformers']

a = Analysis(
    ['main.py'],
    pathex=[],
    binaries=binaries,
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=excludes,
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
