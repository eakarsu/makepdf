# -*- mode: python ; coding: utf-8 -*-
"""PyInstaller spec for building MakePDF.app on macOS."""

import os
import sys
from pathlib import Path

block_cipher = None

PROJECT = Path(SPECPATH)
PKG = PROJECT / "makepdf"

a = Analysis(
    [str(PROJECT / "launcher.py")],
    pathex=[str(PROJECT)],
    binaries=[],
    datas=[
        (str(PKG / "web" / "templates"), "makepdf/web/templates"),
        (str(PKG / "web" / "static"), "makepdf/web/static"),
    ],
    hiddenimports=[
        "makepdf",
        "makepdf.core",
        "makepdf.core.creator",
        "makepdf.core.merger",
        "makepdf.core.text_extractor",
        "makepdf.core.editor",
        "makepdf.core.watermark",
        "makepdf.core.transform",
        "makepdf.core.forms",
        "makepdf.core.sign",
        "makepdf.core.converter",
        "makepdf.core.toc",
        "makepdf.core.security",
        "makepdf.core.info",
        "makepdf.core.ocr",
        "makepdf.core.redaction",
        "makepdf.core.cropper",
        "makepdf.core.stamps",
        "makepdf.core.bates",
        "makepdf.core.compare",
        "makepdf.core.flatten",
        "makepdf.core.metadata",
        "makepdf.core.attachments",
        "makepdf.core.links",
        "makepdf.core.page_labels",
        "makepdf.core.optimizer",
        "makepdf.core.accessibility",
        "makepdf.core.markup",
        "makepdf.web.app",
        "makepdf.web.shared",
        "makepdf.cli.app",
        "makepdf.config",
        "uvicorn",
        "uvicorn.logging",
        "uvicorn.loops",
        "uvicorn.loops.auto",
        "uvicorn.protocols",
        "uvicorn.protocols.http",
        "uvicorn.protocols.http.auto",
        "uvicorn.protocols.websockets",
        "uvicorn.protocols.websockets.auto",
        "uvicorn.lifespan",
        "uvicorn.lifespan.on",
        "fastapi",
        "jinja2",
        "starlette",
        "multipart",
        "reportlab",
        "reportlab.lib.pagesizes",
        "reportlab.pdfgen.canvas",
        "reportlab.lib.colors",
        "pypdf",
        "PIL",
        "markdown",
        "cryptography",
        "objc",
        "AppKit",
        "Foundation",
        "CoreFoundation",
        "PyObjCTools",
        "Quartz",
        "Quartz.CoreGraphics",
        "Quartz.ImageIO",
        "Quartz.PDFKit",
        "Quartz.QuartzCore",
        "Quartz.CoreVideo",
        "Quartz.ImageKit",
        "pyobjc_framework_Quartz",
    ],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
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
    name="MakePDF",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    console=False,
    target_arch=None,
)

coll = COLLECT(
    exe,
    a.binaries,
    a.zipfiles,
    a.datas,
    strip=False,
    upx=True,
    upx_exclude=[],
    name="MakePDF",
)

app = BUNDLE(
    coll,
    name="MakePDF.app",
    icon=None,
    bundle_identifier="com.makepdf.app",
    info_plist={
        "CFBundleName": "MakePDF",
        "CFBundleDisplayName": "MakePDF",
        "CFBundleShortVersionString": "0.1.0",
        "CFBundleVersion": "0.1.0",
        "NSHighResolutionCapable": True,
        "CFBundleDocumentTypes": [
            {
                "CFBundleTypeName": "PDF Document",
                "CFBundleTypeExtensions": ["pdf"],
                "CFBundleTypeRole": "Editor",
                "LSHandlerRank": "Alternate",
            }
        ],
    },
)
