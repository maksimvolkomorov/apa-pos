# -*- mode: python ; coding: utf-8 -*-
# PyInstaller spec for APA@POS
#
# Build:
#   Windows : pyinstaller pos_app.spec
#   macOS   : pyinstaller pos_app.spec
#
# Output lands in dist/APA_POS/
# The DB (pos.db) and receipts are written next to the executable at runtime.

import os

block_cipher = None

a = Analysis(
    ['main.py'],
    pathex=[os.path.abspath('.')],
    binaries=[],
    datas=[
        # Assets bundled into the package
        ('assets/logo.png',         'assets'),
        ('assets/apa-app-logo.png', 'assets'),
        # DB schema — needed at first run for migrations
        ('db/schema.sql',           'db'),
    ],
    hiddenimports=[
        'barcode',
        'barcode.writer',
        'PIL',
        'PIL.Image',
        'reportlab',
        'reportlab.pdfgen',
        'reportlab.lib.pagesizes',
        'reportlab.platypus',
    ],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=['seed'],          # never bundle the seed script
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=block_cipher,
    noarchive=False,
)

pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name='APA_POS',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    console=False,
    icon='assets/apa-app-logo.icns',
)

coll = COLLECT(
    exe,
    a.binaries,
    a.zipfiles,
    a.datas,
    strip=False,
    upx=True,
    upx_exclude=[],
    name='APA_POS',
)

# macOS .app bundle
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
