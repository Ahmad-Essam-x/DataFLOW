# -*- mode: python ; coding: utf-8 -*-


a = Analysis(
    ['C:/Users/Ahmed Gad/Documents/antigravity/quick-noether/desktop_app.py'],
    pathex=[],
    binaries=[],
    datas=[('C:/Users/Ahmed Gad/Documents/antigravity/quick-noether/static', 'static'), ('C:/Users/Ahmed Gad/Documents/antigravity/quick-noether/templates', 'templates'), ('C:/Users/Ahmed Gad/Documents/antigravity/quick-noether/data', 'data'), ('C:/Users/Ahmed Gad/Documents/antigravity/quick-noether/workflows', 'workflows'), ('C:/Users/Ahmed Gad/Documents/antigravity/quick-noether/assets', 'assets')],
    hiddenimports=['waitress', 'openpyxl', 'openpyxl.cell._writer', 'pandas', 'numpy', 'flask', 'jinja2', 'webview', 'webview.platforms.winforms', 'pythonnet', 'clr_loader', 'werkzeug', 'werkzeug.serving', 'werkzeug.datastructures', 'desktop.diagnostics'],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=['scipy', 'matplotlib', 'skimage', 'plotly', 'bokeh', 'seaborn', 'statsmodels', 'tables', 'h5py', 'notebook', 'nbconvert', 'nbformat', 'IPython', 'ipykernel', 'jupyter', 'jupyter_client', 'jupyter_core', 'PIL', 'cv2', 'torch', 'torchvision', 'torchaudio', 'tensorflow', 'keras', 'PyQt5', 'PyQt6', 'PySide2', 'PySide6', 'tkinter', 'turtle', 'docutils', 'sphinx', 'sympy', 'pytest', 'shapely', 'patsy'],
    noarchive=False,
    optimize=0,
)
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name='AntigravityDataFlow',
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
    icon=['C:/Users/Ahmed Gad/Documents/antigravity/quick-noether/assets/icon.ico'],
)
coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=True,
    upx_exclude=[],
    name='AntigravityDataFlow',
)
