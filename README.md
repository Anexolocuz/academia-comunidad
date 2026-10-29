<p align="center"><img src="web/icono-192.png" width="96" alt="Academia"></p>

<h1 align="center">🎓 Academia</h1>
<p align="center"><b>Tu escuela personal con IA local.</b> De lo básico a la frontera, en tu PC, con tus datos en tu PC.</p>

<p align="center">
<a href="CHANGELOG.md"><img alt="versión" src="https://img.shields.io/github/v/tag/Anexolocuz/academia-comunidad?label=versión&color=4f6df5"></a>
<a href="LICENSE"><img alt="licencia" src="https://img.shields.io/badge/licencia-AGPL--3.0-1f9d55"></a>
<img alt="sistemas" src="https://img.shields.io/badge/Windows%20·%20macOS%20·%20Linux%20·%20Docker-listo-555">
<img alt="dependencias" src="https://img.shields.io/badge/dependencias-0-d99a19">
</p>

<p align="center"><a href="docs/facil/INICIO_RAPIDO.md"><b>🚀 Empieza en 5 minutos</b></a> · <a href="README.en.md">English</a></p>

---

Rutas de aprendizaje de 20 áreas (~940 temas, y las que crees tú) escritas **a fondo, por partes** por una IA que
corre en tu PC, con fuentes web y **documentos científicos reales** (OpenAlex). Quizzes, técnica Feynman, ejercicios
con entrega por foto o a mano, **repetición espaciada (FSRS)**, cuaderno para lápiz (S Pen, Apple Pencil), tutor,
metas con ruta completa de requisitos, noticias de tus áreas **comparadas entre medios**, chequeo semanal, panel de
**cómo aprendes** y **nivel profesional** por área, también medido contra lo que pide hoy el mercado.

> **Proyecto para la comunidad.** Se dona el **software**, no el hardware: cada persona la instala y la corre en **su
> propio PC** (Windows, macOS o Linux), con su propia IA. Nadie —tampoco quien la publica— ve tus datos.

## ✨ Lo que la hace distinta

- 🎓 **Hasta la frontera, de verdad** — cada meta con plazo, hitos y una **frontera viva** (investigación actual
  de OpenAlex y arXiv, renovada cada mes), lectura guiada de papers y evaluación de tus propias ideas.
- 🧭 **Se adapta a ti de verdad** — ruta rápida de 10-15 min por lección, paso a paso con «¿lo entendiste?» y
  reexplicación de otra forma, diagnóstico antes de leer, refuerzo de lo que se te olvida, ritmo real y horizonte
  de cuánto te falta para cada nivel.
- 🔒 **Privada de verdad** — sin nube, sin cuentas, sin telemetría. Cerrada a la red por defecto.
- 🪄 **Se configura sola** — un botón escanea tu PC (con tu permiso, sí/no), te dice qué puedes usar y cómo, y aplica
  la mejor configuración. El escaneo se borra solo a las 24 h.
- 🧠 **Cualquier IA local** — Ollama, LM Studio, llama.cpp, llama-swap, vLLM, Jan… o la de otro PC tuyo.
- 📱 **En todos tus equipos** — PC, celular y tablet (instalable como app), por Tailscale o con clave en tu casa.
- 💹 **Acciones bajo vigilancia** — tu lista con alertas, noticias directas e indirectas (competidores, proveedores,
  economía) y pronóstico por escenarios de «muy probable» a «muy poco probable», anclado a la estadística y medido
  contra lo que de verdad pasó (puedes competir con tu propia estimación). Educativo, no asesoría financiera.
- ☁️ **API de IA opcional** — para esperar menos y, a veces, subir la calidad: OpenAI, Claude, Gemini, OpenRouter, Groq,
  DeepSeek, Mistral… o la tuya. Apagada por defecto, por persona, con tope de gasto, sin tu nombre y con regreso solo a la IA local.
- ⏱️ **Modo corto y 🔔 avisos** — una sesión de 5-30 minutos para quien estudia poco y un recordatorio opcional (Telegram, ntfy o tu webhook).
- 🌍 **Noticias por región** — Global + las regiones que elijas (Latinoamérica, tu país…), cada una con tu prioridad; agrega o quita regiones y fuentes.
- 🎨 **A tu gusto** — claro/oscuro, 6 paletas (incluida alto contraste), color de acento y tamaño de letra.
- 🧩 **Cruda y legible** — Python estándar + HTML/JS sin frameworks: ideal para aprender cómo se construye.

## 📦 Instalar — elige una

| | Cómo | Para quién |
|---|---|---|
| **🪟 Windows** | doble clic en `INSTALAR.bat` | la mayoría |
| **🍎 macOS** | doble clic en `Instalar.command` | la mayoría |
| **🐧 Linux** | `./instalar.sh` | la mayoría |
| **🐳 Docker** | `./docker/arrancar.sh` · `docker\arrancar.ps1` — o `docker compose --profile ollama up -d` | todo aislado, IA incluida, GPU NVIDIA/AMD |
| **🛠️ Cruda** | `python3 app/servidor.py` | aprender y modificar |

Antes, una IA: [Ollama](https://ollama.com/download) + `ollama pull gemma3:4b` (o deja que Docker la incluya).
Se abre en **http://127.0.0.1:8092** → ⚙️ Ajustes → 🪄 **Escanear mi PC**.

| Necesitas | Mínimo | Recomendado |
|---|---|---|
| PC | 8 GB de RAM, Python 3.10+ | 16-32 GB de RAM o tarjeta gráfica de 8 GB+ |
| Disco | 1 GB + 3-20 GB por modelo | SSD |

## 📚 Manuales — cada uno en versión fácil y completa

| Tema | 🟢 Fácil (leer y seguir) | 📖 Completo |
|---|---|---|
| Para qué existe (razón, misión, visión, límites) | — | [Propósito](docs/PROPOSITO.md) · [Plan de mejoras](docs/PLAN_MEJORAS.md) |
| API de IA opcional | [Fácil](docs/facil/API_IA.md) | [Completo](docs/API_IA.md) |
| Modo corto y avisos | [Fácil](docs/facil/AVISOS_Y_MODO_CORTO.md) | [Completo](docs/AVISOS_Y_MODO_CORTO.md) |
| Salud, alarma y línea base | [Fácil](docs/facil/SALUD.md) | [Completo](docs/SALUD.md) |
| Eventos y métricas («Qué sabe el sistema de ti») | [Fácil](docs/facil/METRICAS.md) | [Completo](docs/METRICAS.md) |
| Banco de pruebas de la IA (medir modelos) | — | [Completo](docs/MEDICION.md) |
| Empezar | [Inicio rápido](docs/facil/INICIO_RAPIDO.md) | [Instalación](docs/INSTALACION.md) |
| Instalar | [Fácil](docs/facil/INSTALACION.md) | [Completo](docs/INSTALACION.md) |
| Docker | [Fácil](docs/facil/DOCKER.md) | [Completo](docs/DOCKER.md) |
| Celular, tablet y sistemas | [Fácil](docs/facil/CELULAR.md) | [Completo](docs/DISPOSITIVOS.md) |
| Configuración (básica y avanzada) | [Fácil](docs/facil/CONFIGURACION.md) | [Completo](docs/CONFIGURACION.md) |
| Uso y método | [Fácil](docs/facil/USO.md) | [Completo](docs/USO.md) |
| Apariencia y temas | [Fácil](docs/facil/APARIENCIA.md) | [Completo](docs/APARIENCIA.md) |
| Mantenimiento y respaldo | [Fácil](docs/facil/MANTENIMIENTO.md) | [Completo](docs/MANTENIMIENTO.md) |
| Si algo falla | [Fácil](docs/facil/PROBLEMAS.md) | [Completo](docs/SOLUCION_DE_PROBLEMAS.md) |
| Seguridad y privacidad | [Fácil](docs/facil/SEGURIDAD.md) | [Completo](docs/SEGURIDAD_Y_DATOS.md) |
| Versiones y actualizaciones | [Fácil](docs/facil/VERSIONES.md) | [Completo](docs/VERSIONES.md) |
| Cómo está hecha (y cómo se construyó) | [Fácil](docs/facil/ARQUITECTURA.md) | [Completo](docs/ARQUITECTURA.md) |

## 🏷️ Versiones

Una sola versión para todo (archivo [`VERSION`](VERSION)): código, instalador, imagen Docker
(`ghcr.io/anexolocuz/academia-comunidad`) y ZIP de Releases. Novedades en [CHANGELOG.md](CHANGELOG.md).
Actualizar: botón en Ajustes, `./actualizar.sh` / `ACTUALIZAR.bat`, o `docker compose pull && docker compose up -d`.
**Tus datos (`datos/`) nunca se tocan.**

## 🤝 Aportar

Paletas de color, áreas del currículo, fuentes de noticias, traducciones, arreglos: ver [CONTRIBUTING.md](CONTRIBUTING.md).
¿Un fallo de seguridad? Avísalo en privado: [SECURITY.md](SECURITY.md).

## 📄 Licencia

[AGPL-3.0-or-later](LICENSE): úsala, estúdiala, cámbiala y compártela. Si la ofreces a otros como servicio,
comparte también tus cambios.
