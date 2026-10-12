#!/usr/bin/env bash
# Academia en Docker, guiado con preguntas sí/no (Linux y macOS). Uso: ./docker/arrancar.sh
set -euo pipefail
cd "$(dirname "$0")/.."
command -v docker >/dev/null || { echo "Necesitas Docker: https://docs.docker.com/get-docker/"; exit 1; }
docker compose version >/dev/null 2>&1 || { echo "Necesitas Docker Compose v2 (viene con Docker Desktop)."; exit 1; }

si() { local r; read -r -p "$1 [${2:-s}/n] " r; r=${r:-${2:-s}}; [[ $r =~ ^[sSyY] ]]; }
poner() { grep -q "^$1=" .env 2>/dev/null && sed -i.bak "s|^$1=.*|$1=$2|" .env && rm -f .env.bak || echo "$1=$2" >> .env; }

touch .env; chmod 600 .env
grep -q '^SEARXNG_SECRET=' .env || echo "SEARXNG_SECRET=$(head -c 32 /dev/urandom | od -An -tx1 | tr -d ' \n')" >> .env
grep -q '^ACADEMIA_VERSION=' .env || echo "ACADEMIA_VERSION=$(cat VERSION)" >> .env

perfiles=(); extra=()
if si "¿Incluir la IA (Ollama) dentro de Docker? (no, si ya tienes Ollama/LM Studio en este PC)"; then
  perfiles+=(--profile ollama); poner IA_URL http://ollama:11434
  if command -v nvidia-smi >/dev/null && si "Detecté una tarjeta NVIDIA. ¿Usarla?"; then extra+=(-f docker-compose.yml -f docker/nvidia.yml)
  elif [[ -e /dev/kfd ]] && si "Detecté una tarjeta AMD (ROCm). ¿Usarla?"; then extra+=(-f docker-compose.yml -f docker/amd.yml); fi
else
  poner IA_URL http://host.docker.internal:11434
  echo "  → Tu Ollama debe escuchar fuera de 127.0.0.1: OLLAMA_HOST=0.0.0.0 (ver docs/DOCKER.md). Igual puedes cambiarlo en Ajustes."
fi
if si "¿Incluir un buscador web privado (SearXNG) para lecciones con fuentes actuales?"; then
  perfiles+=(--profile buscador); poner BUSCADOR_URL http://searxng:8080
else poner BUSCADOR_URL ""; fi

echo "Descargando y arrancando…"
docker compose "${extra[@]}" "${perfiles[@]}" pull --ignore-buildable 2>/dev/null || true
docker compose "${extra[@]}" "${perfiles[@]}" up -d --build

if [[ " ${perfiles[*]} " == *" ollama "* ]] && si "¿Descargar ya el modelo de IA recomendado (gemma3:4b, ~3 GB; luego el escaneo te dirá si te cabe uno mayor)?"; then
  docker compose "${extra[@]}" "${perfiles[@]}" exec ollama ollama pull gemma3:4b
fi
echo
echo "✅ Lista: abre http://127.0.0.1:${ACADEMIA_PUERTO:-8092}  →  ⚙️ Ajustes → 🪄 Configuración automática"
echo "   Detener: docker compose ${perfiles[*]} down   ·   Actualizar: ./docker/arrancar.sh de nuevo"
