# Cambios

Formato: [Keep a Changelog](https://keepachangelog.com/es-ES/1.1.0/) · versiones [SemVer](https://semver.org/lang/es/).
El número de la versión actual está en [`VERSION`](VERSION) (ver [docs/VERSIONES.md](docs/VERSIONES.md)).

## [1.1.0] - 2026-10-12

### Nuevo
- 🌍 **Noticias por región**: segmento Global + regiones (de fábrica Latinoamérica, México, Colombia, Perú, Chile,
  Argentina y España, con fuentes nuevas probadas). Cada persona da a cada región una prioridad 0-3 (Ajustes →
  Básico) que decide qué ve, en qué orden y qué se prepara a fondo para ella; `regiones_por_defecto` para perfiles nuevos.
- El administrador agrega o quita regiones y fuentes RSS desde Ajustes → Avanzado (con prueba de la fuente); se
  guarda en `datos/regiones.json`. Solo se descargan las regiones que alguien usa; la síntesis común sale de Global.
- La región aparece como bandera en cada noticia.

### Seguridad
- Descargar las noticias a mano (`/api/noticias/actualizar`) ahora es solo para administradores.

## [1.0.2] - 2026-10-12

### Cambiado
- Currículo: ejemplos genéricos en algunos temas (redes, firmware, apps móviles, Linux, PL/SQL).
- El filtro de publicación ya no distingue mayúsculas.
- Fechas en el formato de español de cada navegador; Docker usa UTC por defecto (pon tu `TZ` en `.env`).

### Seguridad
- Identificadores y colores de las áreas creadas por la IA se limpian antes de llegar a la interfaz (evita XSS por
  inyección de instrucciones a la IA).
- El lector de artículos solo abre direcciones públicas de internet, también al seguir redirecciones (evita que un
  enlace de RSS haga abrir tu router u otros equipos de tu red).
- `datos/` se crea solo para tu usuario (700) y `configuracion.json` (puede tener la clave) con permisos 600.
- Los intentos de clave van de a uno (1 s cada uno), también si llegan muchos a la vez.
- Carpetas por usuario sin nombres especiales (`..`).

## [1.0.1] - 2026-10-12

### Arreglado
- Windows: el instalador, la prueba de humo y el servidor ya no fallan al escribir emojis cuando la salida no es una
  consola UTF-8 (tuberías, CI, registros).
- La publicación de la versión (imagen Docker y ZIP) se dispara con la etiqueta.

## [1.0.0] - 2026-10-12

Primera versión pública para la comunidad.

### Lo que trae
- Rutas de 20 áreas (~940 temas) y áreas propias creadas con IA; lecciones a fondo por partes con fuentes web y
  documentos científicos (OpenAlex); quizzes, Feynman, práctica con entrega por foto o cuaderno.
- Repetición espaciada FSRS-4.5, pulso diario, chequeo semanal, plan adaptativo, niveles profesionales y nivel de mercado.
- Noticias por área con comparación entre medios y explicación a fondo; lecturas guiadas en idiomas.
- Perfiles independientes por persona (Tailscale) y panel «Cómo aprendes».

### Nuevo
- 🪄 **Configuración automática**: escaneo del PC con confirmación sí/no (hardware, servidores de IA y modelos con
  visión, SearXNG, Tailscale, Docker), qué se puede usar, cómo completarlo y configuración recomendada aplicable con
  otro sí/no. El escaneo se guarda en `datos/escaneo.json` y se borra solo a las 24 h. También en el instalador
  (`--auto` para hacerlo sin preguntas) y en `python3 app/escaneo.py`.
- 🐳 **Docker**: imagen sin root y de solo lectura, perfiles `ollama` y `buscador`, GPU NVIDIA/AMD, asistentes
  `docker/arrancar.sh` y `docker/arrancar.ps1`, valores de partida `ACADEMIA_INICIAL_*`.
- ⚙️ Ajustes en **Básico** y **Avanzado**.
- 🎨 Apariencia: 6 paletas (`web/temas/*.json`, ampliables), color de acento y tamaño de letra; iconos PNG para iPhone/Android.
- 📱 macOS con doble clic (`Instalar.command`); `ACTUALIZAR.bat` sin `wmic` (Windows 11).
- 📚 Cada manual en versión fácil (`docs/facil/`) y completa; nuevos DOCKER, DISPOSITIVOS, APARIENCIA, VERSIONES.
- 🏷️ Versión única en `VERSION` (app, instalador, etiqueta git, imagen Docker y ZIP).
- 🧪 `pruebas/humo.py` (arranque y seguridad) y pruebas en GitHub para Windows, macOS y Linux.
- Licencia AGPL-3.0-or-later y enlace al código fuente en Ajustes.

### Seguridad
- Solo se confía en conexiones desde `redes_locales` (este PC); la cabecera `Tailscale-User-Login` ya no se puede
  falsificar desde la red.
- `clave_acceso` opcional para entrar desde la red de casa (cookie HMAC, `HttpOnly`, `SameSite=Strict`); sin ella,
  los demás equipos reciben 403.
- Protección CSRF (escrituras solo JSON y del mismo origen) y contra DNS rebinding (`Host` conocido).
- Probar/detectar servidores de IA y el escaneo solo para administradores.
- Enlaces solo `http(s)` (RSS y respuestas de la IA); cabeceras `nosniff`, `SAMEORIGIN`, `no-referrer`.

### Cambiado
- Sin referencias a una instalación concreta: los presets propios van en `privado/presets.json` (no se publica).
- Las imágenes del cuaderno y las entregas se reubican solas si mueves la carpeta `datos/` (otro PC o Docker).
