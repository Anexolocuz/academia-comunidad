# 🧰 Instalación (manual completo)

> ¿Prefieres lo corto? → [Versión fácil](facil/INSTALACION.md)

La Academia se instala **en tu propio PC**. Es software libre que se dona a la comunidad: no hay servidor central,
nadie más ve tus datos y **tú pones el hardware** (tu PC, y si quieres tu celular o tablet).

Hay tres formas de instalarla. Todas usan el mismo código y la misma versión:

| Forma | Para quién | Cómo |
|---|---|---|
| **A · Instalador** (versión «cruda») | La mayoría, y quien quiera aprender cómo está hecha | `INSTALAR.bat` · `Instalar.command` · `./instalar.sh` |
| **B · Docker** (plug and play) | Quien ya usa Docker o quiere todo aislado, incluida la IA | `docker/arrancar.sh` · `docker\arrancar.ps1` — ver [DOCKER.md](DOCKER.md) |
| **C · A mano** | Desarrolladores | `python3 app/servidor.py` |

## Lo que necesitas

| | Mínimo | Recomendado |
|---|---|---|
| Sistema | Windows 10/11, macOS 12+, Linux (cualquiera con Python) | — |
| Python (formas A y C) | 3.10+ (en Windows el instalador lo instala con winget) | 3.12+ |
| Git | opcional: para actualizar con un clic | sí |
| Memoria | 8 GB de RAM (con un modelo pequeño o la IA en otro PC) | 16-32 GB, o tarjeta gráfica con 8 GB+ |
| Disco | 1 GB para la app y tus datos + 3-20 GB por modelo de IA | SSD |
| IA | un servidor compatible con la API de OpenAI: Ollama, LM Studio, llama.cpp, llama-swap, vLLM, Jan… | Ollama |
| Celular/tablet | opcional: cualquier navegador moderno | Tailscale |

La app es muy liviana (≈40 MB de RAM, Python estándar, **sin dependencias**). Lo pesado es la IA.

## Paso 1 · Descargar

**Con Git** (recomendado, para actualizar fácil):

```bash
git clone https://github.com/Anexolocuz/academia-comunidad.git academia
cd academia
```

En Windows, si no tienes Git: `winget install -e --id Git.Git` (PowerShell) y abre una terminal nueva.

**Sin Git:** en GitHub → **Releases** → descarga `academia-vX.Y.Z.zip` y descomprímelo.

## Paso 2 · Instalar (forma A)

| Sistema | Qué hacer |
|---|---|
| **Windows** | Doble clic en **`INSTALAR.bat`**. Si falta Python lo instala con winget: cierra y vuelve a abrir el .bat. |
| **macOS** | Doble clic en **`Instalar.command`** (la primera vez: clic derecho → Abrir, por Gatekeeper). Si falta Python: `brew install python` o https://www.python.org/downloads/ |
| **Linux** | `./instalar.sh` (Arch: `sudo pacman -S python` · Debian/Ubuntu: `sudo apt install python3`) |
| **Todo automático** | Añade `--auto`: escanea, aplica lo recomendado y no pregunta (`./instalar.sh --auto`, `INSTALAR.bat --auto`) |

El instalador hace cuatro cosas:

1. **🪄 Configuración automática** — te pregunta **sí/no** antes de escanear tu PC (sistema, procesador, memoria,
   tarjeta gráfica, servidores de IA y sus modelos, buscador SearXNG, Tailscale, Docker). Te muestra **qué puedes usar**,
   **cómo completar lo que falta** y la **configuración recomendada**, y vuelve a preguntar **sí/no** antes de
   aplicarla. El escaneo se guarda en `datos/escaneo.json` y **se borra solo a las 24 horas**. Si dices que no,
   te pregunta a mano: IA en este PC, o IA en otro PC tuyo (URL).
2. **Perfil y acceso** — nombre de la Academia, tu nombre de perfil, y qué cuentas de Tailscale pueden entrar.
3. **Arranque automático** — Linux: servicio de usuario systemd · Windows: acceso directo oculto en Inicio · macOS: LaunchAgent.
4. **Celular (opcional)** — `tailscale serve` en el puerto 15443 (ver [DISPOSITIVOS.md](DISPOSITIVOS.md)).

Al final se abre **http://127.0.0.1:8092/** (u otro puerto si estaba ocupado).

## Paso 3 · Primer uso

1. **⚙️ Ajustes → 🪄 Configuración automática** si no la usaste en el instalador (o para volver a revisar).
2. **⚙️ Ajustes → Básico**: tu situación y metas (la IA las lee) y la prioridad de las áreas (0-3).
3. Si ya sabes algo, en **🗺️ Ruta** usa la **⚡ prueba de nivel** de esos módulos.
4. Crea metas o áreas propias en **🎯**. Vuelve a **☀️ Hoy**: ahí está tu sesión.

## Elegir la IA

La forma más fácil es **Ollama** (https://ollama.com/download). El escaneo te dice cuál cabe en tu PC; como guía
(modelos con visión, para leer tus apuntes a mano):

| Tu PC | Modelo | Comando |
|---|---|---|
| 8 GB de RAM, sin tarjeta gráfica | Gemma 3 4B (o 1B si va muy lento) | `ollama pull gemma3:4b` |
| 16-32 GB de RAM, o tarjeta de 8-12 GB | Gemma 3 12B | `ollama pull gemma3:12b` |
| 48 GB+ de RAM, o tarjeta de 24 GB | Gemma 3 27B | `ollama pull gemma3:27b` |

Más grande = mejores lecciones pero más lento. Puedes cambiarlo cuando quieras en **Ajustes → Avanzado → IA**.

**Búsqueda web** (lecciones con fuentes actuales): necesita **SearXNG**. Sin él funciona igual, sin fuentes web.
Lo más fácil es el perfil `buscador` de Docker ([DOCKER.md](DOCKER.md)), que también sirve si la Academia está
instalada con la forma A (publica SearXNG solo para tu PC; ver allí «SearXNG para la forma A»).

**IA en otro PC tuyo:** si tienes un PC potente y otro modesto, instala la IA en el potente y en el instalador elige
«2 · IA en otro PC» con su URL (por Tailscale o en tu red de casa). Tus datos se quedan en el PC donde instalas la
Academia; la IA solo procesa los textos.

## Forma C · A mano (desarrollo)

```bash
python3 app/servidor.py                                   # usa datos/ y datos/configuracion.json
ACADEMIA_DATOS=/tmp/prueba ACADEMIA_PUERTO=8099 python3 app/servidor.py   # pruebas sin tocar tus datos
python3 pruebas/humo.py                                   # prueba de arranque y seguridad
python3 app/escaneo.py                                    # ver el escaneo del PC sin guardar nada
```

## Desinstalar

- **Linux:** `systemctl --user disable --now academia && rm ~/.config/systemd/user/academia.service`
- **Windows:** borra `Academia.vbs` de `shell:startup` (Win+R → `shell:startup`) y cierra `pythonw.exe` en el Administrador de tareas.
- **macOS:** `launchctl unload ~/Library/LaunchAgents/com.academia.servidor.plist && rm ~/Library/LaunchAgents/com.academia.servidor.plist`
- **Docker:** `docker compose down` (añade `-v` para borrar también los datos y los modelos).
- `tailscale serve --https=15443 off`
- Borra la carpeta. **Antes, respalda `datos/`** si quieres conservar tu progreso ([MANTENIMIENTO.md](MANTENIMIENTO.md)).
