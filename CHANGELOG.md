# Cambios

Formato: [Keep a Changelog](https://keepachangelog.com/es-ES/1.1.0/) · versiones [SemVer](https://semver.org/lang/es/).
El número de la versión actual está en [`VERSION`](VERSION) (ver [docs/VERSIONES.md](docs/VERSIONES.md)).

## [Sin publicar]

## [1.5.0] - 2026-10-31

### Seguridad
- 🔒 **RSS sin entidades XML**: `noticias._items` rechaza cualquier fuente que declare entidades (`<!ENTITY …>`), que es lo que
  permite la «bomba» de expansión de entidades. Ningún RSS legítimo las necesita.
- 🔒 **Refrescar una fuente guardada también exige dirección pública**: `noticias._bajar` ya no usa `urlopen` directo; comprueba
  `url_publica` y usa el abridor que revalida cada redirección. Antes, una fuente que fue pública al añadirla podía redirigir
  después hacia el router u otro equipo de la red (o apuntar a `file://`) al refrescarse.
- 🧪 Dos pruebas del reporte y del tablero ya no dependen de la hora ni del día de la semana en que se corren (fallaban entre las 00:00 y las 04:00 y los fines de semana; el código estaba bien: el día de estudio empieza a las 4 a. m.).
- 🧪 3 pruebas nuevas (`NoticiasSeguridad`): RSS normal, rechazo de entidades y rechazo de direcciones no públicas (96 en total).

### Nuevo
- ↕️ **Reordenar la cola de la IA** (⏳ Cola): cada tarea que espera tiene ⏫ al principio de su grupo, ▲ ▼ un puesto, ⏬ al final,
  ⚡ urgente (las de fondo pasan a «te espera» y van primero, como si las esperaras tú) y ✖ quitar. Cada persona mueve solo lo suyo;
  el administrador, cualquiera. No afecta a lo que ya corre (`POST /api/cola/mover`, `Cola.mover` en `app/ia.py`).
- 🧹 **Botón «Limpiar» en ⏳ Cola de la IA**: quita lo que ESPERA en la cola (no lo que corre ahora). Cada persona limpia solo lo suyo
  (y puede olvidar sus tareas fallidas); el administrador, además, la cola de todos y las tareas comunes del sistema
  (`POST /api/cola/limpiar`, `Cola.vaciar` en `app/ia.py`).
- 🤝 **Hermes como motor de IA (opcional, apagado por defecto)**: `motor: "hermes"` en la configuración hace que la Academia mande
  sus peticiones a la API local de un perfil de Hermes (`hermes_url`, clave en `datos/secretos.json`, grupo «hermes») en vez de a
  llama-swap. Cambia solo el destino de la llamada (`app/ia.py`): la cola, los permisos, las cortesías con otras apps y el
  análisis del JSON siguen siendo los de la Academia; el esquema JSON viaja en el mensaje porque esa API no admite
  `response_format`. Con `motor: "local"` (por defecto) nada cambia. Guía: [docs/HERMES_MOTOR.md](docs/HERMES_MOTOR.md).
- ⚡ **Energía eléctrica del mundo y su competencia** (`app/familia_energia.py`, segunda familia de 💹 Acciones): 229 símbolos en
  16 grupos (generadoras independientes y nuclear, eléctricas reguladas de EE. UU., equipos de red y turbinas, solar, viento y
  baterías, Canadá, Reino Unido, Península Ibérica, Italia-Francia-Alemania, resto de Europa, Japón y Corea, China y Hong Kong,
  India, Sudeste asiático-Oceanía-Medio Oriente, Latinoamérica y fondos del sector). Cada símbolo se comprobó contra Yahoo Finance.
- **Grupos plegables en la lista de acciones** (columna `grupo`): el universo eléctrico no mezcla ni satura la lista principal;
  sus precios se renuevan de fondo cada 15 min, sin alertas de movimiento y sin IA diaria. El tope de 60 solo cuenta la lista
  principal (tope total 400).
- Las familias ahora llevan `clave`, `descripcion`, `ancla` y `nucleo`: el `nucleo` (lo que la persona pidió expresamente) entra a
  la lista principal con alertas y pronóstico diario; el `ancla` (^GSPC en el S&P 500) también. «➕ Vigilar a todos» las agrega
  de fondo cuando son muchas y el botón «⚡ Agregar la energía eléctrica del mundo» las ofrece desde la lista.
- El resumen de Hermes no lista los grupos plegables salvo que alerten.
- 🗂️ **Agrupar toda la lista de acciones, en dos niveles y configurable por persona** («⚙️ Cómo ver mi lista»): primer nivel por
  tema (familia), tipo de energía, dividendos, sector, país de la bolsa, moneda o sin agrupar; segundo nivel (subdividir) por lo mismo.
  Cada grupo muestra cuántas pagan dividendos y su rendimiento promedio. Se guarda en `kv acciones_vista:<persona>` y se valida
  (`ac.vista_de` / `ac.guardar_vista`, `POST /api/acciones/vista`).
- 🔆 **Tipos de energía** dentro de ⚡ energía eléctrica (`familia_energia.FUENTES`): renovables, nucleares, no renovables fósiles,
  mixtas e integradas, redes, equipos y almacenamiento e hidrógeno. Cada uno de los 229 símbolos está en uno solo (lo comprueba una prueba).
- 💰 **Dividendos** (`ac.dividendos_de`): se bajan de Yahoo con el precio (`events=div`, 2 años) y se calculan sobre los últimos 12 meses
  o el promedio anual de 24: si paga, monto anual por acción, **rendimiento (anual ÷ precio de hoy)**, pagos y el último. Ordenar cada
  grupo por «Dividendo, de mayor a menor» pone primero las que más rinden; las que no pagan van al final. Incluye pagos especiales y, en
  los fondos, sus distribuciones. Aparece como etiqueta en cada fila, en el panel de competencia y en el detalle de cada acción.

## [1.4.0] - 2026-10-29

### Nuevo
- 🧬 **Dominio medido** (fase F3, en **modo sombra**: solo mide y muestra, no cambia `avance.estado`, los repasos ni lo que te toca hoy): estado 0 a 5 por tema (no visto, expuesto, recuerda, comprende, aplica, domina) a partir de la evidencia —quiz, tarjetas, Feynman, tutor examinador, código sin ver la solución, entregas—, visible en cada lección y en 📊 Tablero. **Pruebas diferidas** a los 3, 14 y 45 días del primer dominio: preguntas de aplicación en un caso nuevo, distintas del quiz y de las pruebas anteriores, con una **segunda lectura independiente** que descarta las que otra llamada no contesta igual; se responden una sola vez, se corrigen sin IA y llevan confianza declarada. Solo se generan cuando la persona las pide y ya toca (nada se genera en masa). Métrica `prueba_diferida` (59). `app/estados.py`, `web/diferida.js`.
- 📬 **Resumen semanal por Telegram** (sin IA): `GET /api/hermes/semanal` arma el resumen ejecutivo de la semana (los cinco semáforos, minutos frente a la semana anterior, metas con fecha estimada y un siguiente paso) y el cron de Hermes `semanal-academia` (domingos 7 p. m., script `~/.hermes/scripts/semanal-academia.sh`) lo entrega a tu Telegram. Los semáforos ahora se calculan en el servidor (`adaptacion.semaforos`): una sola fuente para el reporte y el mensaje.
- 🎤 **Tutor examinador** (con Hermes): `GET /api/hermes/examen` entrega las preguntas de la lección con su respuesta modelo y los errores típicos (sin gastar IA) y `POST /api/hermes/evidencia` recibe lo que Hermes vio (puntaje 0-1, pistas, repreguntas, confianza declarada). Es evidencia directa en la línea de tiempo y alimenta la métrica `examen_tutor` (58); no cambia el dominio todavía. Una pregunta floja con respuesta modelo pasa a tus tarjetas. Skill nueva `tutor-examinador` en la colección compartida (Claude Code y Hermes).
- 💻 **Práctica con código** (`app/ejecucion.py`, `web/codigo.js`; `practica_codigo`, apagada por defecto): ejercicios de Python que se corrigen **ejecutando tu código** contra casos de prueba (visibles y ocultos), en un entorno aislado (bubblewrap sin red ni archivos tuyos + cgroup de systemd con tope de memoria, procesos y tiempo). El ejercicio solo se muestra si su solución de referencia pasa todos los casos y la plantilla vacía falla alguno. Si falta el aislamiento, la función se apaga: nunca ejecuta sin aislar. Métrica nueva `codigo_aprobado` (57). Pruebas hostiles en `pruebas/aislamiento.py` (17).
- 📊 **Tablero** (📊 arriba y desde 🔬): cada meta con su avance, los temas que faltan y la **fecha estimada** a tu ritmo real (con rango entre tu ritmo más rápido y más lento, su nivel de confianza y lo que necesitarías por semana para terminarla en 12 meses); temas dominados frente a explorados en 12 semanas; minutos, retención y calendario de actividad; y cuánto recuerdas según la edad del aprendizaje. El ritmo cuenta solo los temas dominados **estudiando** y por la fecha de su **primer** dominio (no por la última vez que se tocaron).
- 🔘 Botones: «⬇️ Descargar noticias ahora» (solo el administrador), «🧠 Analizar noticias pendientes» y «📚 Profundizar lecciones antiguas» (en Tu ruta).

### Nuevo
- 🎯 **Confianza declarada en los quizzes** («seguro», «dudo», «adivino», opcional) y dos métricas nuevas, `calibracion_brier` y `sobreconfianza` (56 en total): miden si tu seguridad coincide con tu acierto. Solo registran: no cambian el dominio ni el repaso. `POST /api/confianza`.
- 📄 **Reporte profesional**: portada, resumen ejecutivo con semáforos (icono y palabra, no solo color), tendencias de 12 semanas (minutos y retención por semana, calendario de actividad, vista en tabla), calibración, dominado frente a explorado, y hoja A4 para imprimir (tema claro, secciones que no se parten, numeración de páginas).
- 🔘 Botones que faltaban: escribir la síntesis de noticias del periodo, rehacer el mapa de relaciones de una acción y ordenar la lista de acciones.
- 🔎 [`docs/REVISION_2026-10-29.md`](docs/REVISION_2026-10-29.md): revisión completa (vistas, botones, formas de verificar el conocimiento, métricas, reportes) con lo comprobado y lo que sigue, amarrado a las fases del plan.

### Corregido
- El análisis de la IA del reporte mostraba «## ## Título» con los símbolos a la vista (el prompt enumeraba los títulos en una línea): se arregla al guardar y al mostrar.
- El análisis de la IA podía estar desactualizado sin avisar (escrito semanas antes, bajo cifras de hoy): ahora se guarda una foto de las cifras y el reporte avisa cuando tiene 7 días o más o las cifras cambiaron mucho.

### Nuevo
- 🎚️ **Del peor al mejor caso** en 💹 Acciones: cinco zonas excluyentes donde puede terminar el precio (peor caso, pesimista, central, optimista, mejor caso) que suman 100 %, cada una con su porcentaje, su rango de precio y su variación, y con **lo más probable** y **lo menos probable** marcados. Salen de la volatilidad actual y de lo que pasó en las ventanas de los últimos 2 años; en el pronóstico se ajustan a la probabilidad de subir ya anclada. Los escenarios concretos de la IA ahora llevan su zona (`caso`) y se ordenan del peor al mejor; se aclara que su probabilidad no suma 100 % porque pueden ocurrir juntos. Sin pronóstico (o en los antiguos) se muestra la versión solo estadística.
- 🕯️ **Velas japonesas y martillos**: el gráfico se puede ver como línea o como velas (se recuerda tu elección), con marcas ▲▼◆ sobre los patrones, y una sección que explica cada patrón detectado (martillo, hombre colgado, martillo invertido, estrella fugaz, doji, doji libélula y lápida, envolvente alcista y bajista) con **lo que pasó en ese mismo activo** las veces anteriores a 5 sesiones. La apertura se guarda ahora en la serie (sexta columna); las series antiguas se vuelven a bajar solas.
- 🧬 **De qué se compone** un fondo o índice: qué empresas y qué porcentaje pesa cada una (las 25 mayores, el total, el resto y la fecha de los datos), con caché de una semana (`accion_composicion`). Un índice usa el fondo que lo copia (S&P 500 → SPY, Nasdaq-100 → QQQ, Dow Jones → DIA, Russell 2000 → IWM).
- ⚔️ **Alternativas y competencia del S&P 500**: panel con los fondos que lo copian (SPY, VOO, IVV, SPYM), otras formas de comprar el mercado (RSP de peso igual, VTI), los índices rivales (Nasdaq-100, Nasdaq Composite, Dow Jones, Russell 2000), sus fondos (QQQ, DIA, IWM) y MSCI World (URTH), con rendimientos y volatilidad comparados y un botón «Vigilar a todos» (`POST /api/acciones/familia`, sin gastar IA). Para no ocupar la GPU, solo el ^GSPC entra en el pronóstico diario; los demás se pronostican a pedido.

## [1.3.0] - 2026-10-29

### Corregido
- ☁️ Los avisos de cuota diaria de Google («billing details») ya no se toman por límite mensual (descansaban 15 días en vez de 3 horas). Nuevo: el administrador ve qué modelos están en pausa y puede pulsar «Reintentar ahora».
- 🔎 Búsqueda de fuentes más pertinente: se descartan los resultados que solo comparten una palabra suelta con la consulta (p. ej. «cambio de paradigma» o una lista de entrenadores al buscar Zero Trust) y las portadas de sitios, y dentro de cada nivel de fiabilidad se ordena por pertinencia. Con la misma consulta, la lección pasa de blogs y páginas sin relación a documentos primarios (NIST, CISA, universidades).
- ☁️ Si un servicio de IA acepta el formato JSON pedido pero no lo aplica (caso de Ollama Cloud, que devolvía otras claves y rompía la lección con `KeyError`), la Academia valida el resultado contra el esquema y reintenta una vez con el esquema escrito en la instrucción.
- ☁️ La cola de IA ya no espera a que otra app suelte la tarjeta gráfica (ni a que termine un juego) cuando la tarea va a la API.
- ☁️ Si la API llega a su límite de uso (429 o cuota agotada) prueba el modelo de respaldo y, si tampoco, pasa sola a la IA local y descansa
  15 minutos (3 horas si el límite es diario) sin insistir; un modelo caído no vuelve a ser el primero durante 10 minutos.
- ☁️ La API ya no se queda colgada si el equipo no tiene salida por IPv6 (`app/red.py`: IPv4 primero y conexión con límite de 10 s), reintenta
  con pausas cuando el servicio está saturado (503) y quita el prefijo `models/` de los nombres de modelo de Gemini.

### Nuevo
- 📎 «Aportar una fuente» en cada lección: pegas el texto de una página que bloquea a las IA (copiado con el modo lector del navegador); la Academia lo guarda por tema, lo resume, saca las referencias y enlaces que cita y contrasta sus afirmaciones con otras fuentes verificadas. Además entra como primera fuente cuando se escribe o reescribe esa lección. El análisis se hace siempre en tu equipo (`app/aportadas.py`).
- 🔬 Crossref como respaldo y complemento de OpenAlex en los documentos científicos: si OpenAlex no responde o trae menos de los pedidos, se completan con Crossref (API pública de los DOI, sin clave), sin repetir.
- ☁️ API de reserva y límites mensuales: si la API principal llega a su límite se prueba una de reserva (otro proveedor, por ejemplo Gemini) antes de pasar a la IA local. Un límite mensual o de créditos hace descansar ese modelo 15 días (cada persona puede cambiar los días y desactivar la reserva); el diario, 3 horas; el que no dice periodo, 15 minutos. Las pausas largas se guardan y sobreviven a un reinicio.
- ⚙️ Carril propio para la API de la nube (`trabajos_nube`, 0 a 6; 0 = como antes): trabaja a la vez que las tareas locales (`trabajos_paralelos`). El carril de la nube solo toma lo que la API puede hacer; el local toma primero lo que solo puede hacerse en el equipo y, de lo demás, únicamente cuando el carril de la nube está lleno o la API no responde (límite, fallo o pausa), así lo que falte pasa solo a lo local. Se ajusta en Configuración → IA.
- 🔬 **Eventos y métricas** (fase F1 del plan; [`docs/METRICAS.md`](docs/METRICAS.md), `app/eventos.py`, `app/metricas.py`, `web/metricas.js`, `web/eventos.js`): una **línea de tiempo de
- 🧪 **Banco de pruebas de la IA** (fase F2 del plan; [`docs/MEDICION.md`](docs/MEDICION.md), `app/medicion.py`): compara modelos y niveles de razonamiento con la misma tarea, los mismos temas y las mismas fuentes congeladas; califica con comprobaciones objetivas (citas inexistentes, enlaces inventados, estructura, fórmulas, repeticiones), un juez anónimo en dos rondas y lectura ciega de la persona; los fallos cuentan como dato; reanudable; sin datos personales. 16 pruebas en `pruebas/unidad_medicion.py`.
  eventos** por persona (proyección idempotente de las tablas existentes, sin tocar las rutas que las escriben), **54 métricas** con origen directo o indirecto, fórmula, ventana,
  decisión que alimentan, muestra y **confianza** (las de poca muestra no deciden nada), y la vista 🔬 «Qué sabe el sistema de ti»: cada persona ve solo lo suyo, puede marcar
  una métrica como errónea, ignorarla o apagar una familia, y ver su tendencia. Los eventos de la interfaz (tiempo en cada vista, a dónde va, si sigue la sugerencia de «Hoy») no
  llevan texto de la persona y se apagan con la familia «Decisión y comportamiento». Fórmula única de «minutos por tema dominado». 18 pruebas nuevas en `pruebas/unidad_metricas.py`.
- 📖 **La API solo prepara las lecciones por defecto** (con sus fuentes: escribirlas, contrastarlas, consultas de papers, ruta rápida, reexplicaciones); cada persona puede ampliar a rutas, noticias o pruebas, o a todo, con atajos de un toque. Lo personal nunca sale.
- 🆓 **Plan gratuito** en la API de IA (encendido de fábrica): costo 0, sin topes en dólares, cuenta llamadas y tokens, aviso de privacidad del nivel gratuito; el límite del proveedor pasa la tarea al respaldo y a la IA local.
- 🩺 **Salud, alarma y línea base** (fase F0 del plan; [`docs/SALUD.md`](docs/SALUD.md), `app/salud.py`, `app/vigia.py`, `web/salud.js`): tablero 🩺 con los problemas
  detectados, la cola, la IA, la GPU, el disco y la rutina diaria; **vigía** (proceso aparte del servicio) que avisa por el canal que se le indique si el servicio
  cae (en menos de 5 minutos) o algo falla, sin repetir avisos y con aviso de recuperación; **cola de IA que sobrevive a los reinicios** (diario en la base,
  `reanudar()` ahora también rehace revisión de rutas y fronteras, y lo que alguien esperaba y no se pudo reconstruir queda a la vista); **línea base de uso**
  por persona (minutos, días activos, minutos por tema dominado…), cada número con su origen. 12 pruebas nuevas en `pruebas/unidad_salud.py`.
- 🗺️ [`docs/PLAN_MEJORAS.md`](docs/PLAN_MEJORAS.md): plan para medir el dominio y ordenar solo (eventos, métricas, clasificador, ordenador, dominio medido, señales de aporte).
- ♊ **Gemini 3.8 Flash** listo en la API opcional, con esfuerzo de razonamiento (`low|medium|high`), sin `temperature` (Gemini 3 no la admite), margen para los tokens de razonamiento y precios de lanzamiento.
- ☁️ **API de IA opcional** (`app/nube.py`, `app/secretos.py`, `web/nube.js`; manual: [`docs/API_IA.md`](docs/API_IA.md)): conecta OpenAI, Anthropic,
  Gemini, OpenRouter, Groq, Cerebras, Together, Fireworks, DeepSeek, Mistral, xAI, SambaNova, NVIDIA NIM, Ollama Cloud u otro servicio compatible. Apagada por
  defecto y por persona; grupos de tareas a elegir, tope de gasto por persona y global con costo medido, «Ver modelos» y «Probar», se
  reajusta sola a cada servicio (parámetros y JSON), tu nombre se quita siempre y lo personal (tutor, apuntes, entregas, ideas, cartera)
  nunca sale; si falla o se acaba el tope, la tarea sigue en la IA local. La clave vive en `datos/secretos.json` (600).
- ⏱️ **Modo corto**: sesión de 5-30 minutos en «Hoy» (pulso, repaso que cabe y una parte de una lección).
- 🔔 **Avisos opcionales** (`app/avisos.py`; [`docs/AVISOS_Y_MODO_CORTO.md`](docs/AVISOS_Y_MODO_CORTO.md)): recordatorio diario con cantidades por Telegram
  (vinculado con un código), ntfy o webhook; apagados por defecto.
- 🧭 [`docs/PROPOSITO.md`](docs/PROPOSITO.md): razón de ser, misión, visión, meta medible (señales de dominio), qué es y qué
  no es, principios, límites, riesgos y preguntas abiertas. Deja escrito el requisito de una **API de IA opcional**
  (apagada por defecto, por persona, sin datos personales, con aviso, tope de gasto y regreso a la IA local); aún no
  está implementada.

### Mejorado
- 📖 Las lecciones a fondo ya no conservan **citas a fuentes que no existen**: al cerrar la lección se quitan los `[n]`
  y `[Pn]` que apuntan más allá de las fuentes realmente encontradas (la IA a veces cita de más y una cita falsa da una
  apariencia de respaldo que no tiene). No toca índices de código ni matemáticas (`x[3]`). Con pruebas unitarias.
- Revisión de seguridad con Bandit: sin hallazgos reales (las URL configurables son solo de administración; los SQL
  dinámicos solo usan nombres de tabla fijos); el hash de la caché de verificación se marca como no criptográfico.

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
