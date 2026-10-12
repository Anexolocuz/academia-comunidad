#!/usr/bin/env bash
# macOS: doble clic en este archivo abre la Terminal y corre el instalador.
cd "$(dirname "$0")" && ./instalar.sh "$@"
echo; read -n 1 -s -r -p "Pulsa una tecla para cerrar…"
