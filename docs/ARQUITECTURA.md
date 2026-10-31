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
  adaptativo.py  motor adaptativo: dominio vivo (FSRS), requisitos olvidados, partes no entendidas, ritmo real,
                 formato recomendado, ruta rápida (tabla leccion_rapida), «¿lo entendiste?» por parte
                 (parte_estado), reexplicaciones (reexplicacion), diagnóstico (kv diag:<u>:<tema>), horizonte,
                 ubicación (inferir_requisitos) y aprendizaje externo (kv externo:<u>)
  dominio.py     programa de dominio por meta: plazo (kv programa:<u>:<oid>), frontera viva (tabla frontera_meta,
                 versiones; ciencia.frontera = revisiones/citados/arXiv), lectura guiada (lectura_paper) y aportes (aporte)
  revision.py    rutas vivas: revisar(ctx, usuario, perfil, area) con mercado/frontera → aplicar() agrega temas y
                 módulos upd<N> (catálogo: capa propia en ruta_extra que curriculo.areas(usuario) mezcla; propias:
                 area_extra); registro en kv revision:<u>:<area>
  verificacion.py fiabilidad(url), buscar_fuentes() agresiva, comparar() afirmaciones↔fuentes, verificar_leccion/
                 verificar_texto (tabla verificacion); noticias.fuentes_de y lecciones._fuentes_* la usan
  lectura.py     sesiones de lectura medidas (tabla `lectura`): velocidad por idioma y fórmulas, lecturas
                 terminadas, avance por actividad (/api/lectura/sesion; la interfaz lo mide en web/app.js «LECT»)
  noticias.py    regiones (config() = config/fuentes.json + datos/regiones.json; ranking(regiones={id: 0-3})), RSS, agrupación, análisis (lee el artículo completo), síntesis, lecturas en idiomas,
                 comparar() entre medios y explicar() a fondo (columna noticia.profundo)
  ciencia.py     documentos científicos de OpenAlex (caché 30 días en kv papers:<consulta>, consultas en inglés por módulo)
  mercado.py     referente de lo que pide hoy el mercado por área (kv mercado:<area>, 30 días) y nivel de mercado
  acciones.py    💹 acciones vigiladas: Yahoo Finance (buscar, cotizar: serie diaria de 2 años en accion_info),
                 indicadores y tasa_base (sin IA), noticias directas/indirectas (Yahoo RSS, Google Noticias, tabla
                 noticia; accion_noticia), relaciones() y pronosticar() con la IA (clasifica noticias, escenarios,
                 p_sube anclada a la tasa base ±20), evaluar()/calibracion() (Brier), lista por persona (accion_vigilada);
                 casos() (5 zonas excluyentes del peor al mejor caso, suman 100), patrones_velas() (martillos y demás,
                 con su historia a 5 sesiones; la serie guarda también la apertura), composicion() (posiciones de un
                 fondo/índice por stockanalysis.com, caché 7 días en accion_composicion) y familia() (S&P 500 y rivales; también la de ⚡ energía eléctrica, datos y tipo de energía en familia_energia.py; `grupo` en accion_vigilada), dividendos_de() (dividendos de Yahoo en `meta.dividendos`, rendimiento 12/24 meses) y vista_de()/guardar_vista() (agrupar en dos niveles, ordenar; `kv acciones_vista:<persona>`)
  nube.py        API de IA opcional: proveedores (OpenAI-compatibles y Anthropic), privacidad (`limpiar`), gasto y topes, reajuste
                 de parámetros, respaldo en la IA local; `intentar()` lo llama `Contexto._chat`
  secretos.py    datos/secretos.json (clave de la API, token de Telegram), permiso 600
  avisos.py      recordatorio diario opcional por Telegram / ntfy / webhook (una vez al día, a su hora, solo si hay algo)
  salud.py       F0: `evaluar()` (problemas con gravedad), resumen de la cola, `correr_diaria()`, diario de la cola (tabla `cola_diario`,
                 ganchos de `ia.ganchos`, `al_arrancar()`/`conciliar()`) y línea base de uso por persona (`kv linea_base:<persona>`)
  vigia.py       proceso APARTE del servicio: consulta `/api/salud` y avisa por `ACADEMIA_ALARMA_CMD`; `--probar`, `--pausar`, `--reanudar`
  eventos.py     F1: línea de tiempo `evento` (proyección idempotente de actividad, repasos, lectura, entregas… con marca de agua por fuente),
                 eventos de la interfaz (lista blanca `vista`/`navega`) y sugerencias de «Hoy»; todo por persona
  metricas.py    F1: catálogo de 54 métricas (origen D/I, fórmula, ventana, decisión, muestra mínima), confianza, `usable()`, ajustes por persona
                 (mal/ignorar/familia apagada), foto diaria `metrica_valor` y tendencia
  medicion.py    F2: banco de pruebas de la IA (variantes de modelo, fuentes congeladas, comprobaciones objetivas, juez anónimo, lectura ciega, informe)
pruebas/humo.py  arranca en carpeta temporal y comprueba páginas, versión y protecciones de seguridad
pruebas/unidad.py unittest sin internet ni IA: cálculos de acciones (RSI, tasa base, cartera, margen) y caché de áreas
pruebas/unidad_salud.py unittest de la fase F0: problemas, diario y conciliación de la cola, rutina diaria, línea base y vigía
pruebas/unidad_metricas.py unittest de la fase F1: eventos sin duplicados, aislamiento entre perfiles, valores de las métricas, confianza y ajustes
pruebas/unidad_medicion.py unittest de la fase F2: puntuación objetiva, anonimización, reanudación y lectura ciega
Dockerfile, docker-compose.yml, docker/   imagen sin root + perfiles ollama/buscador + GPU NVIDIA/AMD + asistentes
instalar.py      instalador (Windows/macOS/Linux) con auto-escaneo, --auto y arranque automático
web/temas/       paletas de color (JSON de tokens CSS) e index.json
web/             index.html, app.js (vistas por hash #/…), cuaderno.js (lienzo S Pen), acciones.js (💹), salud.js (🩺), metricas.js (🔬), eventos.js (eventos de la interfaz), nube.js (modo corto, avisos, API), estilo.css, vendor/ (KaTeX, marked, DOMPurify)
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

- **Motor adaptativo** (`adaptativo.py`, 2026-10-27): `plan_adaptativo` usa `ritmo()` (tope de temas nuevos),
  `partes_no_entendidas()` y `requisitos_olvidados()` (van a `recuperar` con `motivo`; el plan guarda `motivos`) y
  `formato()`; `curriculo.recomendar` multiplica por `1 + 0,1·dependientes` (módulos de tus áreas que lo necesitan) y
  da 1,5 a los requisitos de tus metas. `mapa()` trae `memoria` por tema. La interfaz parte la lección por `## Parte N`
  (`adaptarLectura` en `web/app.js`): pliega capas opcionales, agrega el control por parte y el paso a paso;
  `ofrecerDiagnostico` relaciona cada pregunta con su parte por palabras en común. La ruta rápida se encola detrás de
  cada lección del plan (`_leccion_y_rapida`) y en la actualización diaria si `formato()` recomienda «esencial».

- **Caché de áreas** (2026-10-28): `curriculo.areas(usuario)` se arma una vez por persona y se reutiliza mientras no
  cambie su versión (tabla `areas_version`, la suben triggers de SQLite en cada INSERT/UPDATE/DELETE de `area_extra`
  y `ruta_extra`, las escriba quien las escriba). Lo devuelto es de solo lectura: para cambiar un área se lee su fila
  de la base (como `revision.aplicar` y `dominio`). «Hoy» pasó de 2,6 s a 0,14 s.
- **Respuestas comprimidas**: `Manejador._comprimir` manda gzip (texto/JSON de más de 2 KB) si el navegador lo acepta
  (`app.js` 270 → 80 KB, el mapa 300 → 64 KB). Los cortes de conexión (`BrokenPipeError`) ya no ensucian el registro.
- **Búsqueda web con frenado automático** (`ia.buscar_web`): si SearXNG avisa de un motor suspendido, el intervalo
  entre consultas se duplica (hasta 6 s) y vuelve poco a poco a 1,2 s.

## API principal

`GET /api/hoy · /api/mapa · /api/tema?id= · /api/noticia?id= · /api/ciencia?ref=|q= · /api/leccion/anterior?tema= · /api/repaso · /api/analitica · /api/niveles · /api/largo_plazo ·
/api/reporte · /api/reporte.md · /api/exportar · /api/noticias?periodo= · /api/config`
`POST /api/leccion · /api/lecciones/profundizar · /api/noticia/profundo {id, que: explicacion|comparacion} · /api/mercado {area} · /api/visto · /api/resultado · /api/repaso · /api/entrega · /api/corregir · /api/tutor ·
/api/objetivos · /api/area/nueva · /api/chequeo/crear · /api/pulso · /api/hoy/extra · /api/config`
Las tareas de IA devuelven `{trabajo}`; se consulta con `GET /api/trabajo?id=`.

Adaptativo: `POST /api/parte {tema, parte, estado: sabido|dudoso|no} · /api/reexplicar {tema, parte, estilo: simple|ejemplo|esquema, duda}
· /api/rapida {tema} · /api/diagnostico {tema, bien, total, flojas} · /api/enfoque {areas, resto} · /api/ubicacion/inferir {ref}
· /api/externo {texto}` y `GET /api/horizonte?enfoque= · /api/externo`; `/api/tema` trae `formato` y `partes`.

Programa de dominio: `GET /api/dominio?objetivo=` · `POST /api/programa {objetivo, semanas}` · `/api/frontera {objetivo}`
· `/api/paper/guia {objetivo, paper}` · `GET /api/paper?id=` · `POST /api/paper/responder {id, i, respuesta}` ·
`/api/aporte {objetivo, texto}`; `POST /api/objetivos` acepta `semanas` y encola la frontera detrás del plan; la
actualización diaria renueva 1 frontera vencida (30 días) por persona; `curriculo.refs_con_plazo` da ×3 en `recomendar`.

Rutas vivas: `GET /api/ruta/estado?area=|objetivo=` · `POST /api/ruta/preparar {area|objetivo}` (prioridad 2, kv
`preparar_ruta:<u>`) · `POST /api/ruta/actualizar {area|objetivo}` (tarea `ruta` = `actualizar_ruta`: mercado o
frontera → `revision.revisar` → lecciones de lo nuevo); la actualización diaria llama `rutas_vivas(u)`.

Innovación: `POST /api/ramas {objetivo}` (dominio.mapear_ramas; plan.ramas) · `POST /api/ideas {objetivo, enfoque}`
(dominio.idear + _chequeo_novedad; tabla idea) · `POST /api/idea/elegir|presentacion|pares {idea}`;
`dominio.refs_proyecto` da ×2 en `recomendar`. Prioridad: `ia.otros_modelos(usuario_espera=)` + `GET /api/prioridad`.

Verificación: `POST /api/verificar/leccion {tema}` · `POST /api/verificar {texto}` · `GET /api/verificar[?clave=]`.
Persistencia: `ia.guardar_resultado` (tabla `trabajo_hecho`, 7 días; `GET /api/trabajo` cae ahí si ya no está en
memoria); pruebas en `prueba_nivel` (`POST /api/prueba` retoma la abierta, `GET /api/prueba?id=`,
`POST /api/prueba/respuesta {id,i,j}`, `POST /api/prueba/resultado {id}`, `GET /api/pruebas`); Ubícame en
kv `ubicacion:<u>:<clave>` (`GET/POST /api/ubicacion/estado`).

Acciones: `GET /api/acciones[?rapido=1]` (lista + calibración; rapido = sin pedir precios) · `GET /api/acciones/buscar?q=`
· `POST /api/acciones/vigilar|quitar {simbolo}` · `/api/acciones/ajustar {simbolo, alerta_arriba, alerta_abajo,
alerta_pct, nota}` · `/api/acciones/orden {simbolos}` · `GET /api/accion?s=` (vista previa si no es de tu lista) ·
`POST /api/accion/noticias {simbolo}` · `/api/accion/pronostico {simbolo, dias, p_usuario?}` · `/api/accion/relaciones
{simbolo}`. Tareas de IA `pronostico` y `relaciones` (de la persona, enmascaradas para los demás en ⏳). La
actualización diaria llama `acciones_diarias(u)`.

Integración con agentes (Hermes): `GET /api/hermes/resumen` (markdown), `GET /api/hermes/siguiente` (texto para
Telegram), `GET /api/hermes/repaso?n=` y `POST /api/hermes/repaso {id, nota}` (repaso por chat), `GET /api/hermes/buscar_tema?q=`,
`POST /api/hermes/tarjetas`, `POST /api/hermes/nota`, `GET /api/hermes/acciones` (lista vigilada en texto) y
`GET /api/hermes/alertas` (solo alertas no avisadas hoy; vacío = nada).

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
