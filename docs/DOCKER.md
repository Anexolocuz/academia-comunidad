# 🐳 Docker (manual completo)

> ¿Prefieres lo corto? → [Versión fácil](facil/DOCKER.md)

Docker deja la Academia **aislada y lista en un comando**, y opcionalmente también la IA (Ollama) y el buscador
(SearXNG). Funciona igual en Windows, macOS y Linux. La imagen es la misma versión que el código
(`ghcr.io/anexolocuz/academia-comunidad:vX.Y.Z`, para PC x86 y ARM: Raspberry Pi 5, Apple Silicon).

## Lo más fácil: el asistente

| Sistema | Comando |
|---|---|
| Linux / macOS | `./docker/arrancar.sh` |
| Windows | clic derecho en `docker\arrancar.ps1` → **Ejecutar con PowerShell** |

Pregunta **sí/no**: ¿IA dentro de Docker? ¿usar tu tarjeta NVIDIA/AMD? ¿buscador web? Crea `.env` (con una clave
aleatoria para SearXNG), arranca todo y ofrece descargar el modelo recomendado. Luego abre http://127.0.0.1:8092
→ **⚙️ Ajustes → 🪄 Configuración automática**.

## Las opciones (perfiles)

| Quieres | Comando |
|---|---|
| Solo la Academia (ya tienes Ollama/LM Studio en el PC) | `docker compose up -d` |
| + IA incluida (Ollama) | `docker compose --profile ollama up -d` |
| + buscador web privado | `docker compose --profile ollama --profile buscador up -d` |
| + tarjeta NVIDIA | `docker compose -f docker-compose.yml -f docker/nvidia.yml --profile ollama up -d` |
| + tarjeta AMD (Linux, ROCm) | `docker compose -f docker-compose.yml -f docker/amd.yml --profile ollama up -d` |

Descargar un modelo en el Ollama de Docker: `docker compose exec ollama ollama pull gemma3:12b`.

NVIDIA necesita el **NVIDIA Container Toolkit** en Linux, o Docker Desktop con WSL2 en Windows. En macOS, Docker no
puede usar la GPU de Apple: ahí es mejor Ollama nativo (https://ollama.com) + `docker compose up -d` (solo la Academia).

## `.env` (opcional)

```ini
ACADEMIA_VERSION=1.0.0          # versión de la imagen (latest si no se pone)
ACADEMIA_PUERTO=8092            # puerto en este PC
ACADEMIA_USUARIO=yo             # tu nombre de perfil
ACADEMIA_CLAVE=                 # clave para entrar desde otros equipos de tu red (ver Seguridad)
IA_URL=http://ollama:11434      # valor de partida; luego se cambia en Ajustes
IA_MODELO=gemma3:4b
BUSCADOR_URL=http://searxng:8080
SEARXNG_SECRET=<aleatorio>      # obligatorio con el perfil buscador (lo crea el asistente: openssl rand -hex 32)
TZ=America/Mexico_City         # tu zona horaria (por defecto UTC)
```

`IA_URL`, `IA_MODELO` y `BUSCADOR_URL` son **solo valores de partida** (`ACADEMIA_INICIAL_*`): lo que cambies en
Ajustes o con la configuración automática se guarda en el volumen y manda.

## Usar la IA que ya tienes en el PC

`IA_URL=http://host.docker.internal:11434`. Ollama en Linux escucha solo en 127.0.0.1: para que el contenedor lo vea,
`sudo systemctl edit ollama` → `Environment="OLLAMA_HOST=0.0.0.0"` (y un cortafuegos que no lo exponga a tu red).
En Windows/macOS con Ollama de escritorio funciona sin cambios.

## Datos, actualizar, respaldar

- Tus datos viven en el volumen `academia_academia-datos` (montado en `/datos`); los modelos en `academia_ollama-modelos`.
- **Actualizar:** `docker compose pull && docker compose up -d` (o vuelve a correr el asistente). Para fijar una
  versión: `ACADEMIA_VERSION=1.0.0` en `.env`.
- **Respaldar:** `docker run --rm -v academia_academia-datos:/datos -v "$PWD":/r alpine tar czf /r/academia-datos.tgz -C /datos .`
- **Restaurar / traer datos de una instalación A:** `docker compose stop academia`, luego
  `docker run --rm -v academia_academia-datos:/datos -v "$PWD/datos":/origen alpine cp -a /origen/. /datos/` y `docker compose start academia`.
- Registro: `docker compose logs -f academia`.

## Seguridad en Docker

- El puerto se publica **solo en 127.0.0.1**: nadie de tu red entra. Ollama y SearXNG **no publican puertos**
  (solo la Academia los ve por la red interna).
- El contenedor corre **sin root**, con sistema de archivos de solo lectura (salvo `/datos`), sin capacidades
  de Linux y `no-new-privileges`.
- La red interna es `172.29.89.0/24` y cuenta como «este PC» (`ACADEMIA_REDES_LOCALES`): por ahí llegan tus
  conexiones al puerto publicado. Si ese rango choca con tu red, cámbialo en los dos sitios de `docker-compose.yml`.
- **Celular:** Tailscale en el PC (no en Docker): `tailscale serve --bg --https=15443 http://127.0.0.1:8092`.
- **Red de casa sin Tailscale:** cambia `"127.0.0.1:${ACADEMIA_PUERTO:-8092}:8092"` por `"${ACADEMIA_PUERTO:-8092}:8092"`
  **y** define `ACADEMIA_CLAVE` en `.env`. Sin clave, la Academia rechaza a los demás equipos.

## SearXNG para la forma A (instalación sin Docker)

Si instalaste la Academia con el instalador y solo quieres el buscador en Docker, añade a `docker-compose.yml` en el
servicio `searxng` → `ports: ["127.0.0.1:8888:8080"]`, corre `docker compose --profile buscador up -d searxng` y pon
`http://127.0.0.1:8888` en Ajustes → Avanzado → IA → Buscador (o vuelve a escanear).

## Construir la imagen tú mismo

`docker compose build` (usa el `Dockerfile` de la raíz; no necesita internet salvo la imagen base de Python).
