# -*- mode: python ; coding: utf-8 -*-
# PyInstaller spec — Windows
#
# Run on a Windows PC:
#   pip install pyinstaller
#   pyinstaller build_windows.spec
#
# Output: dist\APA_POS\APA_POS.exe
# Zip the entire dist\APA_POS\ folder and send it.
#
# Prerequisites on the build machine:
#   - Python 3.10+ from python.org  (Tk included)
#   - pip install pyinstaller
#   - pip install python-barcode[images] Pillow reportlab  (optional but recommended)

import os

block_cipher = None

a = Analysis(
    ['main.py'],
    pathex=[os.path.abspath('.')],
    binaries=[],
    datas=[
        ('assets/logo.png',            'assets'),
        ('assets/apa-app-logo.png',    'assets'),
        ('db/schema.sql',              'db'),
        ('import_export_config.json',  '.'),
    ],
    hiddenimports=[
        'barcode', 'barcode.writer',
        'PIL', 'PIL.Image',
        'reportlab', 'reportlab.pdfgen',
        'reportlab.lib.pagesizes', 'reportlab.platypus',
    ],
    hookspath=[],
    runtime_hooks=[],
    excludes=['seed'],
    cipher=block_cipher,
    noarchive=False,
)

pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

exe = EXE(
    pyz, a.scripts, [],
    exclude_binaries=True,
    name='APA_POS',
    debug=False, strip=False, upx=True,
    console=False,                   # no black terminal window
    icon=os.path.join(os.path.abspath('.'), 'assets', 'apa-app-logo.ico'),
)

coll = COLLECT(
    exe, a.binaries, a.zipfiles, a.datas,
    strip=False, upx=True, upx_exclude=[],
    name='APA_POS',
)
