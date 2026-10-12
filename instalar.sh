#!/usr/bin/env bash
# Instalador de la Academia para Linux y macOS: busca Python 3.10+ y corre instalar.py
cd "$(dirname "$0")"
for py in python3 python; do
  if command -v $py >/dev/null && $py -c 'import sys; sys.exit(sys.version_info < (3,10))'; then exec $py instalar.py "$@"; fi
done
echo "Necesitas Python 3.10 o más nuevo:"
echo "  Arch: sudo pacman -S python   ·   Ubuntu/Debian: sudo apt install python3   ·   macOS: brew install python"
exit 1
