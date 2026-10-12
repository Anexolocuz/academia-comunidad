# 🏗️ Arquitectura (para modificar la app) (manual completo)

> ¿Prefieres lo corto? → [Versión fácil](facil/ARQUITECTURA.md)

Python estándar (sin dependencias) + HTML/JS sin frameworks. SQLite en modo WAL.

```
app/
  servidor.py    HTTP (ThreadingHTTPServer), rutas /api/*, identidad por cabecera Tailscale-User-Login,
                 actualización diaria (trabajador de fondo, revisa cada minuto si pasó la hora)
  config.py      datos/configuracion.json + variables ACADEMIA_* (+ ACADEMIA_INICIAL_*), VERSION, presets
  escaneo.py     auto-escaneo del PC (hardware, servidores de IA, SearXNG, Tailscale, Docker) → recomendación;
                 guarda datos/escaneo.json y lo borra a las 24 h (purgar() en el trabajador)
  base.py        esquema SQLite y migraciones
  ia.py          cola única de IA (prioridad 0 = el usuario espera, 1 = fondo), conflicto con otros modelos,
                 streaming, JSON Schema (response_format), detector de bucles, SearXNG
  curriculo.py   carga curriculo/*.json + áreas personales (tabla area_extra), dominio, desbloqueo, recomendación
  lecciones.py   prompts: lección a fondo (plan → partes → cierre, misma conversación; versión anterior en
                 leccion_anterior), ejercicios, corrección, Feynman, prueba de nivel, tutor, apuntes (visión),
                 objetivos, áreas nuevas, entregas de práctica
  fsrs.py        FSRS-4.5 (repetición espaciada)
  analitica.py   panel «Cómo aprendes», chequeo semanal
  adaptacion.py  pulso, largo plazo, plan adaptativo, plan del día, instantáneas, niveles profesionales, reportes, exportación
  lectura.py     sesiones de lectura medidas (tabla `lectura`): velocidad por idioma y fórmulas, lecturas
                 terminadas, avance por actividad (/api/lectura/sesion; la interfaz lo mide en web/app.js «LECT»)
  noticias.py    regiones (config() = config/fuentes.json + datos/regiones.json; ranking(regiones={id: 0-3})), RSS, agrupación, análisis (lee el artículo completo), síntesis, lecturas en idiomas,
                 comparar() entre medios y explicar() a fondo (columna noticia.profundo)
  ciencia.py     documentos científicos de OpenAlex (caché 30 días en kv papers:<consulta>, consultas en inglés por módulo)
  mercado.py     referente de lo que pide hoy el mercado por área (kv mercado:<area>, 30 días) y nivel de mercado
pruebas/humo.py  arranca en carpeta temporal y comprueba páginas, versión y protecciones de seguridad
Dockerfile, docker-compose.yml, docker/   imagen sin root + perfiles ollama/buscador + GPU NVIDIA/AMD + asistentes
instalar.py      instalador (Windows/macOS/Linux) con auto-escaneo, --auto y arranque automático
web/temas/       paletas de color (JSON de tokens CSS) e index.json
web/             index.html, app.js (vistas por hash #/…), cuaderno.js (lienzo S Pen), estilo.css, vendor/ (KaTeX, marked, DOMPurify)
curriculo/       un JSON por área
config/          fuentes.json
```

## Seguridad en el servidor (`Manejador._rutear`)

Antes de cualquier ruta: 1) `host_permitido()` (contra DNS rebinding, 421); 2) `de_confianza()` = IP del cliente en
`redes_locales`, si no, cookie `acceso` = HMAC de `clave_acceso` (`_acceso()` la emite; sin clave definida → 403);
3) POST/DELETE con cuerpo exigen JSON y `Origin` igual a `Host`. `tailscale()` solo devuelve la cabecera
`Tailscale-User-Login` si la conexión es de confianza. `es_admin()`: este PC, o cuentas `administradores` por Tailscale.
Cabeceras `nosniff`, `SAMEORIGIN`, `no-referrer` en `end_headers()`.

## Ideas clave

- **Una sola cola de IA** (`ia.cola`) con hasta `trabajos_paralelos` tareas a la vez (config; 1 por defecto, 2 con
  llama-server `--parallel 2 --kv-unified`). Hilos `ia-cola-<n>`; los de sobra duermen, así el número se
  cambia en Ajustes sin reiniciar. `cola.actuales` = las que corren.
- **Profundidad de lecciones**: `lecciones.PROFUNDIDAD` por versión (2 = a fondo, 3 = máxima: partes 6-8,
  1300-1900 palabras/parte, 4 web + 3 papers por parte, sección «🔍 Más a fondo», 8 ejercicios). `generar_leccion(...,
  maxima=True)`; rutas `POST /api/leccion {maxima}`, `GET /api/modulo/estado?area=`, `POST /api/modulo/preparar
  {ref, maxima?}`.
- **Noticias a máxima profundidad**: `actualizacion_diaria` → `_profundizar_noticias` elige por persona
  `nt.a_profundizar(sus áreas, noticias_a_fondo_por_persona)` y encola `a_fondo` (= `nt.a_fondo_completo`: analizar →
  comparar → explicar, saltando lo hecho); las síntesis van detrás. `ranking(..., solo_a_fondo=True)` en Noticias y
  Hoy: solo se muestra lo completo (`nt.a_fondo`).
- **Refresco suave** (`refrescar()` = `enrutar({suave:true})`): los redibujos automáticos (lección que termina una
  parte, tareas/objetivos pendientes, trabajo de IA terminado) no muestran el cargando ni suben al inicio.
  Lo de fondo espera si otro programa tiene otro modelo cargado (`/running` de llama-swap) o si aigate dice «ocupado».
- **Todo es por cuenta**, también las lecciones (tabla `leccion` con clave `(usuario, tema)`, desde 2026-10-08): se
  escriben con el perfil de quien estudia, así cada persona empieza en blanco. Al migrar una base vieja, las lecciones
  que había se copian a cada cuenta con perfil (`base._lecciones_por_usuario`). Noticias y síntesis sí son comunes.
- El tutor (`lecciones.SISTEMA_BASE`) ya no trae metas fijas: persigue las metas del perfil de cada persona.
- **Áreas de cada persona** = `curriculo.areas_de(usuario)` (claves de `pesos` + `area_extra` propias + áreas de
  sus metas activas `areas_de_metas` + áreas con `avance`); prioridad efectiva `curriculo.peso` (2 por defecto para
  las propias y las de sus metas). Sin catálogo en la interfaz. Todo lo que muestra áreas filtra con eso: `/api/progreso`, `/api/niveles`, reporte, `/api/noticias`
  (`mis_areas`, ranking, impacto; la síntesis común pasa por `noticias.sintesis_para`), `/api/lecturas`, y `/api/yo`
  devuelve `areas` para el front (`esMia`, `miaN`). Regla: ninguna lista fija de áreas en el código.
- `GET /api/cola` (vista ⏳, cada 10 s): `ia.cola.lista()` en orden + `trabajo_visible()` (propias con detalle,
  comunes = `COMUNES` tal cual, ajenas enmascaradas; también `estado_ia(usuario)` del indicador) + CPU/RAM de la
  Academia y del `llama-server` del modelo (puerto según `/running` de llama-swap).
- `/api/hermes/*` solo acepta `usuario` desde el propio PC; `/api/trabajo` solo devuelve trabajos propios.
- `/api/horario` (hora de la actualización diaria, global) solo para administradores; el día del chequeo es por
  persona (`kv chequeo_dia:<usuario>`, si no, el general).
- **Plan del día congelado** en `kv` (`plan:<usuario>:<fecha>`), sesiones extra se agregan.
- **Prompts**: todos en `lecciones.py` / `analitica.py` / `noticias.py`; salida estructurada con JSON Schema.

## API principal

`GET /api/hoy · /api/mapa · /api/tema?id= · /api/noticia?id= · /api/ciencia?ref=|q= · /api/leccion/anterior?tema= · /api/repaso · /api/analitica · /api/niveles · /api/largo_plazo ·
/api/reporte · /api/reporte.md · /api/exportar · /api/noticias?periodo= · /api/config`
`POST /api/leccion · /api/lecciones/profundizar · /api/noticia/profundo {id, que: explicacion|comparacion} · /api/mercado {area} · /api/visto · /api/resultado · /api/repaso · /api/entrega · /api/corregir · /api/tutor ·
/api/objetivos · /api/area/nueva · /api/chequeo/crear · /api/pulso · /api/hoy/extra · /api/config`
Las tareas de IA devuelven `{trabajo}`; se consulta con `GET /api/trabajo?id=`.

Integración con agentes (Hermes): `GET /api/hermes/resumen` (markdown), `GET /api/hermes/buscar_tema?q=`,
`POST /api/hermes/tarjetas`, `POST /api/hermes/nota`.

## Probar sin tocar tus datos

```bash
ACADEMIA_DATOS=/tmp/prueba ACADEMIA_PUERTO=8094 python3 app/servidor.py
```

## Cómo se construyó (para aprender)

La Academia es a propósito **«cruda»**: sin frameworks ni dependencias, para que se pueda leer de punta a punta.

1. **Servidor** — `http.server.ThreadingHTTPServer` de Python con un decorador `@ruta(método, camino)` que llena
   `RUTAS`. Cada función recibe `(usuario, q, d, h)`: cuenta, parámetros de la URL, cuerpo JSON y el manejador.
2. **Base de datos** — SQLite en modo WAL (`base.py`): un esquema y una lista de `MIGRACIONES` que se aplican solas.
   Nunca se borra nada al actualizar.
3. **IA** — cualquier servidor con la API de OpenAI. `ia.py` tiene **una sola cola** con prioridades: lo que pides
   tú (0) pasa antes que el trabajo de fondo (1). Respuestas estructuradas con JSON Schema (`response_format`) y un
   detector de bucles que corta y reintenta.
4. **Lecciones a fondo** — `lecciones.py`: primero un plan, luego cada parte en la misma conversación (contexto
   compartido), con fuentes web (SearXNG) y papers (OpenAlex) citados. Todo prompt está en ese archivo.
5. **Memoria** — FSRS-4.5 (`fsrs.py`, 80 líneas) decide cuándo repasar cada tarjeta.
6. **Interfaz** — HTML + JS sin frameworks: `web/app.js` tiene una vista por ruta (`VISTAS.hoy`, `VISTAS.ajustes`…)
   que pinta con plantillas; markdown con marked + DOMPurify y fórmulas con KaTeX (incluidos en `web/vendor/`).
7. **Instalar en todos lados** — `instalar.py` solo usa la biblioteca estándar y sabe dejarla arrancando sola en
   systemd, Windows y macOS. Docker es la misma app en una imagen `python:slim`.

**Para empezar a modificarla:** corre una copia aislada (`ACADEMIA_DATOS=/tmp/prueba ACADEMIA_PUERTO=8099 python3 app/servidor.py`),
busca la vista o la ruta (`grep -n '"/api/tema"' app/servidor.py`), cambia, recarga. Antes de proponer el cambio:
`python3 pruebas/humo.py`.
