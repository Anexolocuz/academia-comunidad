# 📱 Sistemas y dispositivos (manual completo)

> ¿Prefieres lo corto? → [Versión fácil](facil/CELULAR.md)

La Academia **corre en un PC** (Windows, macOS o Linux) y se **usa** desde cualquier navegador: el mismo PC, un
celular, una tablet (con lápiz) u otro computador de la casa.

## Dónde se puede instalar

| Sistema | Instalador | Arranque automático | Docker | Notas |
|---|---|---|---|---|
| Windows 10/11 | `INSTALAR.bat` | acceso directo oculto en Inicio | Docker Desktop (WSL2), NVIDIA sí | Python lo instala winget |
| macOS 12+ (Intel y Apple Silicon) | `Instalar.command` | LaunchAgent | Docker Desktop (sin GPU) | Mejor Ollama nativo: usa la GPU de Apple |
| Linux (x86 y ARM) | `./instalar.sh` | servicio de usuario systemd | Docker Engine, NVIDIA y AMD | `loginctl enable-linger` para que arranque sin iniciar sesión |
| Raspberry Pi 5 / mini PC ARM | `./instalar.sh` o Docker (imagen arm64) | systemd | sí | La IA conviene en otro PC más potente (modo remoto) |
| Celular / tablet | — (solo se **usa**) | — | — | La IA no corre en el celular |

## Usarla desde el celular o la tablet

### Opción 1 · Tailscale (recomendada: cifrada, también fuera de casa)

1. Instala Tailscale en el PC y en el celular (https://tailscale.com/download), con la misma cuenta o una invitada a tu tailnet.
2. En el PC: `tailscale serve --bg --https=15443 http://127.0.0.1:8092` (el instalador lo ofrece; el escaneo te da tu dirección).
3. En el celular abre `https://<tu-pc>.<tu-tailnet>.ts.net:15443/`.
4. Opcional: en `datos/configuracion.json` → `usuarios_permitidos` pon las cuentas de Tailscale que pueden entrar
   (cada una tiene su propio perfil y progreso).

### Opción 2 · Red de casa con clave (sin Tailscale, sin cifrado)

1. En `datos/configuracion.json`: `"host": "0.0.0.0"` y `"clave_acceso": "una frase larga"`. Reinicia.
   (Docker: ver [DOCKER.md](DOCKER.md) → «Red de casa sin Tailscale».)
2. Permite el puerto 8092 en el cortafuegos del PC **solo para la red privada** (Windows lo pregunta la primera vez:
   marca solo «Redes privadas»).
3. En el celular abre `http://<IP-del-PC>:8092` (la IP sale en `ipconfig` / `ip addr`) y escribe la clave.

Quien entra con clave usa el perfil de `usuario_local` y no puede cambiar la configuración.

### Instalarla como app

| Dispositivo | Cómo |
|---|---|
| Android (Chrome, Samsung Internet, Edge) | menú ⋮ → **Instalar app** / Agregar a pantalla de inicio |
| iPhone / iPad (Safari) | botón Compartir → **Agregar a inicio** |
| PC (Chrome, Edge, Brave) | icono de instalar en la barra de direcciones |

Con Tailscale (HTTPS) se instala como app completa (pantalla completa, icono propio). Por HTTP en la red de casa,
los navegadores solo permiten un acceso directo.

### Tablets con lápiz

El 📓 cuaderno funciona con S Pen, Apple Pencil y lápices de Windows. En Ajustes → Básico activa **«solo lápiz»**
para que el dedo desplace y no raye. iPhone sin lápiz: déjalo apagado y dibuja con el dedo.

### Pantallas y accesibilidad

- Diseño adaptable de 320 px (celular) a pantallas grandes; respeta la muesca y la barra de gestos.
- **Tamaño de letra** (hasta 130 %), **alto contraste**, modo claro/oscuro automático: Ajustes → Apariencia.
- Voz 🔊 para leer lecciones e idiomas: usa las voces del sistema (Android: Google TTS; Windows: Configuración → Voz;
  macOS/iOS: Contenido leído).
