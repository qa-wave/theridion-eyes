#!/usr/bin/env bash
# Build the PyInstaller FE sidecar bundle and stage it into apps/studio-fe
# /src-tauri/binaries under the platform-specific name Tauri's externalBin
# resolver expects.
#
# Local dev:  pnpm --filter theridion-fe sidecar:bundle
# CI:         called from the desktop matrix job before `tauri build`.
set -euo pipefail

cd "$(dirname "$0")/.."

TARGET=$(rustc -vV | grep "^host:" | awk '{print $2}')
if [[ -z "$TARGET" ]]; then
  echo "fatal: could not determine host target triple via rustc" >&2
  exit 1
fi

OUT="../studio-fe/src-tauri/binaries"
mkdir -p "$OUT"

uv sync --all-extras
uv run pyinstaller sidecar.spec --clean --noconfirm

SRC="dist/theridion-sidecar-fe"
EXT=""
if [[ "$TARGET" == *windows* ]]; then
  SRC="${SRC}.exe"
  EXT=".exe"
fi

DEST="${OUT}/theridion-sidecar-fe-${TARGET}${EXT}"
cp "$SRC" "$DEST"
chmod +x "$DEST"

echo "✓ staged $(du -h "$DEST" | cut -f1) at $DEST"
