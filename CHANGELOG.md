# Cambios

Formato: [Keep a Changelog](https://keepachangelog.com/es-ES/1.1.0/) · versiones [SemVer](https://semver.org/lang/es/).
El número de la versión actual está en [`VERSION`](VERSION) (ver [docs/VERSIONES.md](docs/VERSIONES.md)).

## [Sin publicar]

## [1.2.0] - 2026-10-28

### Nuevo
- 💹 **Acciones bajo vigilancia** (`app/acciones.py`, `web/acciones.js`; botón 💹 y tarjeta en «Hoy»): lista por persona
  con búsqueda (Yahoo Finance, también Bolsa de Colombia `.CL`), precio, cambio, mini-gráfico y alertas (cruza un
  precio o se mueve más de x % en el día). Detalle con gráfico (media de 50 días y cono del rango estadístico),
  indicadores y lectura en palabras; **noticias directas e indirectas** (mapa de relaciones de la IA: competidores,
  proveedores, clientes y factores; Google Noticias, Yahoo y las noticias de la Academia) leídas y clasificadas por la
  IA (vía, impacto, plazo); **pronóstico por escenarios** a 7/30/90 días agrupado de muy probable a muy poco probable,
  con la probabilidad de subir anclada a la tasa base histórica (±20 puntos); **aciertos medidos** al vencer (dirección,
  Brier, dentro del rango) y estimación propia opcional para comparar tu calibración con la de la IA. Cada día: precios,
  noticias y pronóstico (`acciones_pronostico_diario`). Hermes: `/api/hermes/acciones`, `/api/hermes/alertas` (solo lo
  nuevo, para un cron en horario de bolsa) y alertas en el resumen de la mañana.

### Mejorado
- 💹 Acciones v2: **💼 Mi cartera** (cantidad y precio de compra; valor y ganancia en COP, pesos por acción, sector y
  moneda, volatilidad de la cartera y cuánto riesgo le quita la diversificación, avisos de concentración); **beta**
  frente al S&P 500 o al COLCAP y movimiento propio del día; **alerta por noticia fuerte** (impacto ±2, también por
  Telegram); **margen que aprende** (con 5+ pronósticos cerrados, si la IA no supera a la estadística se le acerca);
  conceptos del pronóstico enlazados a temas de tu Academia.
- Cola de la IA: al reanudar tras un reinicio también vuelven las noticias a fondo, las síntesis que falten y los
  pronósticos del día. `/api/prioridad` informa también el trabajo del día y el masivo (para que otras apps de IA alternen turnos).
- Barra de arriba en el celular: lo menos usado va a «⋯». Pruebas unitarias nuevas: `pruebas/unidad.py`.
- ⚡ «Hoy» 2,6 s → 0,14 s y la cola ⏳ 1,1 s → 0,19 s: `curriculo.areas()` en caché por persona, invalidada por
  triggers de SQLite (tabla `areas_version`).
- 📦 Respuestas con gzip: `app.js` 270 → 80 KB y el mapa 300 → 64 KB (se nota en el celular).
- 🔎 Búsqueda web con frenado automático ante motores suspendidos (hasta 6 s entre consultas, vuelve sola a 1,2 s).
- 🧹 Los cortes de conexión del navegador ya no llenan el registro de errores.
- 🎯 **La meta del proyecto, explícita**: prepararte en semanas o meses para presentar algo lo más innovador posible,
  dominando desde lo básico hasta la frontera con todas las sub-ramas necesarias.
  - **🌳 Mapa de sub-ramas** por meta (al crearla y con un botón): el árbol completo (sub-ramas del campo, de campos
    vecinos y los fundamentos que se usan) con lo esencial marcado y el dominio de cada una; los módulos del catálogo
    que las cubren entran a la meta y las ramas sin cobertura se vuelven módulos «🌳» nuevos.
  - **🚀 Laboratorio de innovación**: 4-6 ideas que atacan los problemas abiertos de la frontera y cruzan la meta con
    lo que ya sabes, cada una con **chequeo de novedad contra trabajos publicados reales** (OpenAlex y arXiv: los más
    parecidos, qué aporta la idea y cómo hacerla más nueva); **⭐ elegir proyecto** (su ruta crítica va primero en el
    plan, ×2); **🎤 preparar la presentación** (título, resumen, estructura, guion de 10 min, preguntas difíciles del
    público con cómo responderlas, plan de validación semanal y qué dominar antes); **🧑‍⚖️ revisión de pares**
    simulada (teórico, experimental y escéptico). «💡 Tu propia idea» también se compara con la literatura.
- ⚖️ **Lo que pides pasa antes** (`modelos_cedibles`, `supermemory_estado_url`): una tarea pedida por una persona entra
  cuando el modelo de otra app lleva 20 s sin procesar y esa app no está a mitad de un trabajo; las demás apps pueden
  consultar `GET /api/prioridad` para no empezar trabajo nuevo mientras alguien espera. Nada se corta a medias.
- Búsqueda web responsable: las consultas a SearXNG van en fila (una cada 1,2 s), con caché de 6 h y pausa de 5 min si
  los motores avisan de suspensión; la búsqueda agresiva usa ~11 consultas bien elegidas en vez de ~27 (una ráfaga
  había hecho que Brave, Google y Wikipedia suspendieran el buscador, también para Hermes y Open WebUI).
- Calidad: las preguntas del diagnóstico previo ya no cuentan en la nota del quiz; las noticias solo suman fuentes de
  la MISMA historia; las rutas vivas agregan como máximo 5 temas y 1 módulo por revisión y el referente del mercado
  se renueva partiendo del anterior (no salta por azar); las rutas vivas se encolan después de las noticias; los
  papers clave de la frontera se emparejan por título; citas múltiples [P7, P11] enlazadas.
- 🔎 **Fuentes verificadas y comparador** (`app/verificacion.py`): cada fuente lleva su **fiabilidad** (🏛️ académica u
  oficial · 📚 referencia, medio de calidad, universidad o verificador de datos · 🌐 general · ⚠️ baja; redes sociales
  fuera). **Búsqueda agresiva**: varias consultas en español e inglés, dirigidas a Wikipedia, .edu y .gov, verificadores
  de datos y OpenAlex, máximo 2 por dominio, diversidad de tipos y lectura del texto completo. **Comparador**: por cada
  afirmación, veredicto (confirmada, con matices, en disputa, contradicha, sin evidencia), qué fuentes la apoyan o la
  contradicen, confianza ponderada por fiabilidad y en qué difieren las fuentes.
  - **Lecciones**: las fuentes con que se escriben salen de esa búsqueda (ordenadas por fiabilidad) y cada lección
    trae «🔎 Fuentes contrastadas» (automático con `verificar_lecciones`, o con un botón).
  - **Noticias**: se buscan más fuentes (mínimo 5, antes 3), también primarias y verificadores; cada fuente con su
    fiabilidad y cada afirmación con su respaldo (alto/medio/bajo); la comparación pesa más lo oficial y académico.
  - **🔎 Verificar** (barra superior): pega una afirmación o pregunta («¿es cierto que…?») y la contrasta.
- 💾 **Nada se pierde al cerrar una ventana**: las **pruebas de nivel** se guardan en el servidor con cada respuesta al
  tocarla; se retoman donde ibas desde el módulo, «Hoy» o **📝 Mis pruebas** (también en otro equipo), con su
  resultado guardado. **🎯 Ubícame** guarda su avance (se retoma o se reinicia). Todo resultado de la IA queda 7 días
  en la base (`trabajo_hecho`): sobrevive a cerrar la ventana, cambiar de equipo o reiniciar el servidor. Escape y
  cambiar de vista cierran las ventanas.
- 🔄 **Rutas vivas** (`app/revision.py`): cada ruta (área o meta) se revisa sola contra el referente del mercado de
  hoy y la investigación reciente (en las metas, su frontera): agrega los temas y módulos «🆕» que falten (al final:
  los ids de lo estudiado no cambian), marca 📉 lo que pesa menos y prepara las lecciones de lo nuevo. Las rutas del
  catálogo crecen por persona en una capa propia (tabla `ruta_extra`), sin tocar la de los demás.
  - Cada día (actualización diaria) para todas las rutas con prioridad > 0 y las metas activas, con
    `mercado_cada_dias` (nivel profesional vs. mercado; antes 1 área cada 30 días) y `revision_rutas_cada_dias`
    (por defecto 30 y 7; se pueden poner en 1).
  - Botones en cada área y cada meta: **📥 Preparar toda la ruta** (todas las lecciones pendientes, de fondo y detrás
    de lo diario; queda recordado y se re-encola cada día lo que falte) y **🔄 Actualizar ahora** (mercado o frontera +
    revisión + lecciones de lo nuevo).
- 🎓 **Programa de dominio** (`app/dominio.py`): una meta ya no termina en un resumen, sino cuando puedes aplicar,
  leer la investigación actual, seguir una conferencia y proponer algo propio.
  - **📅 Plan con plazo** (2 semanas a 1 año, también al crear la meta): con tu ritmo real dice cuántos min/día hacen
    falta, si cabe en tu meta y en lo que de verdad estudias, hitos semana a semana y si vas adelantado o atrasado.
    Los temas de las metas con plazo van primero en el plan del día (×3).
  - **🔭 Frontera viva**: mapa del estado del arte hecho con investigación real (OpenAlex: revisiones de los últimos
    4 años, lo más citado de los últimos 2 y preprints de arXiv) y la web: líneas activas con su madurez, problemas
    abiertos, vocabulario de las charlas, conferencias y papers clave en orden de lectura, con citas enlazadas. Se
    hace sola al crear la meta, **se renueva cada 30 días**, dice qué cambió y agrega los temas nuevos a la ruta
    (módulo «🔭 Frontera viva»).
  - **📄 Lectura guiada de papers**: idea central, por qué importa, cómo leerlo, requisitos enlazados a tu ruta,
    glosario y 6 preguntas (problema, método, resultado, límites, conexión, crítica) que la IA corrige.
  - **💡 Tu aporte**: tu idea o pregunta de investigación contrastada con los problemas abiertos y los papers:
    originalidad, viabilidad, si ya existe, siguiente paso y cómo presentarla.
  - **🎯 Ubícame en esta meta**: búsqueda binaria de pruebas de nivel sobre toda la ruta de la meta (infiere
    requisitos también entre áreas).
- 📚 La lectura por defecto vuelve a ser la **lección completa** (la meta es dominar): **paso a paso** automático para
  quien no termina las lecciones; la ruta rápida pasa a ser **🗺️ Vista previa** (mapa de 10 min antes de estudiar
  y repaso después).
- 🧭 **Aprendizaje adaptativo** (motor `app/adaptativo.py`): la Academia optimiza «aprendizaje por minuto».
  - **⚡ Ruta rápida** de cada lección (10-15 min con lo esencial de cada parte, un ejemplo y 3 preguntas para
    fijarlo); se prepara sola de fondo para quien no alcanza a terminar las lecciones completas.
  - **Lectura a la medida**: modos ⚡ Rápida / 📗 Esencial (pliega «más a fondo», matices, ejemplos extra,
    investigación y horizonte) / 📚 Completo, y **👣 Paso a paso** (una parte a la vez). Tiempo estimado a tu
    velocidad. El modo se elige solo según si terminas las lecciones (Ajustes → Básico para fijarlo).
  - **«¿Lo entendiste?» al final de cada parte**; si no, **🔄 Explícamelo de otra forma** (🪶 más simple,
    🔧 con un ejemplo, 🗺️ en un esquema) con tu duda, y la lección vuelve a tu plan hasta que la superes.
  - **⚡ Diagnóstico antes de leer**: la mitad del quiz; si aciertas todo, se confirma con la otra mitad y el tema
    queda dominado sin leer; si no, se marcan 📌 las partes donde enfocarte.
  - **Dominio vivo**: la memoria real (FSRS) de cada tema se ve en la Ruta (🧠 %); los **requisitos que se te están
    olvidando** de lo que vas a estudiar se refuerzan antes, con su motivo en «Hoy».
  - **Ritmo real**: temas nuevos por día según los minutos que de verdad te cuesta cada tema.
  - **Prioridad por valor**: pesan más los temas que desbloquean más camino hacia tus áreas y los requisitos de tus metas.
  - **🔭 Horizonte**: cuánto falta para cada nivel profesional por área (a tu meta diaria, a tu ritmo real y
    enfocándote) y botón **🎯 Enfocarte** (áreas elegidas a prioridad 3, el resto en mantenimiento).
  - **🎯 Ubícame en un área**: pruebas de nivel en búsqueda binaria (3-4 en vez de una por módulo); al superar un
    módulo, sus requisitos de la misma área quedan como sabidos.
  - **📥 Lo que estudiaste fuera** (Coursera, Platzi, DataCamp, universidad…): la IA lo relaciona con tu ruta y
    propone una prueba de nivel por módulo para verificarlo.
  - **👉 Tu siguiente paso** arriba de «Hoy»: una sola acción, la que más rinde ahora (chequeo, pulso, repaso
    vencido, el tema a reforzar o el siguiente nuevo), con su porqué.
  - **Errores del quiz → tarjetas**: cada pregunta fallada se guarda como tarjeta (desde el quiz de la lección) y
    vuelve en el repaso hasta dominarla.
  - **Hermes**: `GET /api/hermes/siguiente` (lo que más rinde hoy, para Telegram), `GET/POST /api/hermes/repaso`
    (repaso de tarjetas por chat con FSRS) y secciones «Adaptación» y «Reforzar» en `/api/hermes/resumen`.
- 🔬 **Todo el día a máxima profundidad** (Ajustes → Básico, por persona): la actualización diaria prepara TODAS
  las lecciones del plan del día a máxima profundidad (sin tope de adelantadas) y antes que las noticias, para
  levantarse y leer sin abrir cada sesión. Las lecciones nuevas que se abran ese día también nacen a máxima.

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
