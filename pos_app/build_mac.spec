# -*- mode: python ; coding: utf-8 -*-
# PyInstaller spec — macOS
#
# Run on a Mac:
#   pyinstaller build_mac.spec
#
# Output: dist/APA_POS.app  (drag to Applications, AirDrop, or zip to send)

import os

block_cipher = None

a = Analysis(
    ['main.py'],
    pathex=[os.path.abspath('.')],
    binaries=[],
    datas=[
        ('assets/logo.png',         'assets'),
        ('assets/apa-app-logo.png', 'assets'),
        ('db/schema.sql',           'db'),
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
    console=False,
    icon='assets/apa-app-logo.icns',
)

coll = COLLECT(
    exe, a.binaries, a.zipfiles, a.datas,
    strip=False, upx=True, upx_exclude=[],
    name='APA_POS',
)

app = BUNDLE(
    coll,
    name='APA_POS.app',
    icon='assets/apa-app-logo.icns',
    bundle_identifier='com.apastore.pos',
    info_plist={
        'NSHighResolutionCapable': True,
        'CFBundleShortVersionString': '1.0.0',
        'CFBundleName': 'APA@POS',
    },
)
