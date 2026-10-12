#!/usr/bin/env bash
# Trae la última versión de GitHub y reinicia la Academia. Tus datos (datos/) no se tocan.
set -e
cd "$(dirname "$0")"
git pull --ff-only
if command -v systemctl >/dev/null && systemctl --user cat academia.service >/dev/null 2>&1; then
  systemctl --user restart academia.service && echo "✅ Actualizada y reiniciada."
elif [ "$(uname)" = "Darwin" ]; then
  launchctl unload ~/Library/LaunchAgents/com.academia.servidor.plist; launchctl load ~/Library/LaunchAgents/com.academia.servidor.plist
  echo "✅ Actualizada y reiniciada."
else
  echo "Actualizada. Reinicia la Academia para usar la versión nueva."
fi
