#!/bin/bash
set -euo pipefail
ROOT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
APP="$ROOT_DIR/build/YA TU SAABE!!.app"
command -v xcrun >/dev/null || { echo 'Instala las herramientas de Xcode: xcode-select --install'; exit 1; }
mkdir -p "$APP/Contents/MacOS" "$APP/Contents/Resources"
xcrun swiftc -parse-as-library -O \
  "$ROOT_DIR/macos/App.swift" "$ROOT_DIR/macos/DestinationPicker.swift" \
  "$ROOT_DIR/macos/Robot.swift" "$ROOT_DIR/macos/WW2Scene.swift" \
  -framework SwiftUI -framework AppKit -framework SceneKit \
  -o "$APP/Contents/MacOS/YaTuSaabe"
cp "$ROOT_DIR/backend.py" "$ROOT_DIR/assets/WW2Map.png" "$ROOT_DIR/assets/Creditos.txt" "$APP/Contents/Resources/"
cat > "$APP/Contents/Info.plist" <<'PLIST'
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0"><dict>
<key>CFBundleDisplayName</key><string>YA TU SAABE!!</string>
<key>CFBundleName</key><string>YA TU SAABE!!</string>
<key>CFBundleExecutable</key><string>YaTuSaabe</string>
<key>CFBundleIdentifier</key><string>org.yatusaabe.app</string>
<key>CFBundlePackageType</key><string>APPL</string>
<key>CFBundleShortVersionString</key><string>1.0</string>
<key>CFBundleVersion</key><string>1</string>
<key>LSMinimumSystemVersion</key><string>14.0</string>
<key>NSHighResolutionCapable</key><true/>
</dict></plist>
PLIST
codesign --force --deep --sign - "$APP"
codesign --verify --deep --strict "$APP"
echo "Lista: $APP"
