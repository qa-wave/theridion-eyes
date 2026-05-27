# PyInstaller spec for the Theridion FE sidecar.
#
# Slimmer than BE: drops zeep/grpcio/kafka/mqtt/jdbc deps; only collects
# fastapi + uvicorn + pydantic + httpx + lxml runtime data.
#
# Build with:  uv run pyinstaller sidecar.spec --clean --noconfirm

# ruff: noqa: F821  -- spec-file globals are injected by PyInstaller.

from PyInstaller.utils.hooks import collect_all

datas = []
binaries = []
hiddenimports = []
for pkg in ("fastapi", "uvicorn", "pydantic", "lxml", "httpx"):
    pkg_datas, pkg_bins, pkg_hidden = collect_all(pkg)
    datas += pkg_datas
    binaries += pkg_bins
    hiddenimports += pkg_hidden

hiddenimports += [
    "uvicorn.logging",
    "uvicorn.loops",
    "uvicorn.loops.auto",
    "uvicorn.loops.asyncio",
    "uvicorn.protocols",
    "uvicorn.protocols.http",
    "uvicorn.protocols.http.auto",
    "uvicorn.protocols.http.h11_impl",
    "uvicorn.protocols.websockets",
    "uvicorn.protocols.websockets.auto",
    "uvicorn.lifespan",
    "uvicorn.lifespan.on",
]

# Exclude heavy BE-only modules so PyInstaller doesn't bundle them even if
# referenced indirectly (e.g. via theridion_sidecar.api.* unused submodules).
EXCLUDED = [
    "grpc",
    "_grpc_helpers",
    "google.protobuf",
    "zeep",
    "xmlsec",
    "aiokafka",
    "kafka",
    "paho",
    "paho.mqtt",
    "psycopg2",
    "psycopg2-binary",
    "stomp",
]


a = Analysis(
    ["scripts/sidecar_entry.py"],
    pathex=[],
    binaries=binaries,
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=EXCLUDED,
    noarchive=False,
    optimize=0,
)

pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.datas,
    [],
    name="theridion-sidecar-fe",
    debug=False,
    bootloader_ignore_signals=False,
    strip=True,  # FE bundle target < 30 MB — strip symbols for size
    upx=False,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=True,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)
