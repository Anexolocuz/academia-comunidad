# 🔬 Eventos y métricas: qué sabe el sistema de ti

> Parte de [Plan de mejoras](PLAN_MEJORAS.md), fase F1. Versión corta: [fácil](facil/METRICAS.md).

La Academia solo puede ordenar tu estudio bien si **mide** cómo estudias. Esta función tiene dos piezas:

1. Una **línea de tiempo de eventos** (`app/eventos.py`): una sola tabla donde cae todo lo que haces.
2. Un **catálogo de métricas** (`app/metricas.py`): números calculados sobre esa línea de tiempo, cada uno con su origen, su fórmula, su
   confianza y la decisión que alimentará.

Todo se ve en el botón 🔬 de la barra superior («Qué sabe el sistema de ti», `#/metricas`) y **es solo tuyo**: cada perfil ve únicamente lo suyo.

## 1. Eventos

`evento(usuario, ts, fuente, tipo, objeto, valor, contexto, directo, ref)`.

- **Es una proyección.** No reemplaza ninguna tabla: copia, cada minuto, lo nuevo de las que ya existen (actividad, repasos, lectura, entregas,
  reexplicaciones, partes entendidas, pruebas de nivel y chequeos). Cada fila lleva una `ref` única, así que sincronizar dos veces no duplica nada
  y una sesión de lectura que crece sigue siendo un solo evento. No se toca ninguna ruta que ya escribía datos.
- **Directo o indirecto.** *Directo* (`directo=1`) es lo que diste de forma explícita: una nota de repaso, un puntaje, una entrega. *Indirecto*
  se deduce de tu comportamiento: tiempo de estudio, lectura, a dónde vas.
- **Lo que solo ve la interfaz.** `web/eventos.js` manda, en lotes, dos cosas sin ningún texto tuyo: los segundos que estuviste en cada vista y a qué vista
  fuiste después. Con eso se mide cuánto tardas en decidir y si sigues lo que «Hoy» te sugiere (la sugerencia la anota el servidor, una vez por hora y destino).
  El servidor solo acepta una lista blanca de tipos (`vista`, `navega`), recorta los nombres y los valores y descarta el resto.
- **Qué NO se copia:** el texto de tus apuntes, entregas, chat o ideas. Solo el hecho, el objeto, el puntaje y el tiempo.
- **Apagar.** Si apagas la familia «Decisión y comportamiento» en 🔬, el servidor deja de guardar tu navegación y tus sugerencias.

## 2. Métricas

Cada métrica declara:

| Campo | Qué es |
|---|---|
| Origen | **directa** (la diste tú) o **indirecta** (se deduce de tu comportamiento) |
| Fórmula | cómo se calcula, en palabras |
| Ventana | el periodo que mira (7 días, 30 días, acumulado…) |
| Qué decide | la decisión futura que alimentará (por ejemplo el ordenador de la fase F5) |
| Muestra `n` y confianza | cuántos datos respaldan el valor |

**Confianza.** *Sin datos* (n = 0), *baja* (n por debajo del mínimo de la métrica), *media* (menos de 3 veces el mínimo) o *alta*. En las métricas de hábito
la muestra son los **días de historia disponibles** dentro de la ventana, no el número de eventos (quien lleva 1 día de uso no tiene 30 días de datos).
**Una métrica de confianza baja o sin datos no decide nada** (`metricas.usable()`): se muestra para que veas qué se mide, pero no se usa.

**Tú mandas.** En cada métrica puedes pulsar **«Esto está mal»** (el dato es erróneo) o **«Ignorar»**, y **«Quitar mi ajuste»** para deshacerlo; también puedes **apagar una familia
entera**. Una métrica marcada, ignorada o apagada deja de poder decidir. Los ajustes son por persona.

**Tendencia.** Una vez al día se guarda una foto de tus métricas (`metrica_valor`); el botón «📈 Tendencia» muestra su historial.

**Fórmula única de «minutos por tema dominado».** Es el tiempo total de estudio registrado (minutos) dividido entre los temas con estado «dominado» o «probado». La
línea base de la fase F0 usa la misma. (El valor de 128 min por tema que menciona [Propósito](PROPOSITO.md) venía de otra definición; este manual manda.)
Ojo: «probado» hoy significa que pasó una prueba de nivel; la exigencia de **prueba diferida** llega en la fase F3.

## 3. Catálogo (54 métricas)

D = directa · I = indirecta. Las que dependen de datos que aún no existen (prueba diferida, calibración de confianza, dispositivo) se añadirán en las fases F3 y siguientes.

### Dominio y memoria

| Métrica | Origen | Fórmula | Ventana | Qué decide | Muestra mínima |
|---|---|---|---|---|---|
| **Temas dominados** (`temas_dominados`) | directa | Temas con estado «dominado» o «probado» en el avance. Aún no exige prueba diferida (eso llega en la fase F3). | acumulado | Estados de dominio (F3) y señales de aporte (F7) | 1 |
| **Temas vistos sin dominar** (`temas_expuestos`) | directa | Temas con estado «visto» (se abrió la lección o la ruta rápida, sin pasar su verificación). | acumulado | Barra «explorado» frente a «dominado» (F3) | 1 |
| **Retención a 1 día** (`retencion_1d`) | directa | De los repasos hechos cuando la tarjeta llevaba entre 0.5 y 2 días sin verse, qué fracción se contestó bien (nota ≥ 2). | 180 días | Intervalos de repaso y diagnóstico de olvido | 8 |
| **Retención a 7 días** (`retencion_7d`) | directa | De los repasos hechos cuando la tarjeta llevaba entre 5 y 10 días sin verse, qué fracción se contestó bien (nota ≥ 2). | 180 días | Intervalos de repaso y diagnóstico de olvido | 8 |
| **Retención a 30 días** (`retencion_30d`) | directa | De los repasos hechos cuando la tarjeta llevaba entre 20 y 40 días sin verse, qué fracción se contestó bien (nota ≥ 2). | 180 días | Intervalos de repaso y diagnóstico de olvido | 8 |
| **Retención a 90 días** (`retencion_90d`) | directa | De los repasos hechos cuando la tarjeta llevaba entre 60 y 120 días sin verse, qué fracción se contestó bien (nota ≥ 2). | 180 días | Intervalos de repaso y diagnóstico de olvido | 8 |
| **Estabilidad media de las tarjetas** (`estabilidad_fsrs`) | indirecta | Promedio de la estabilidad FSRS (días hasta que la probabilidad de recordar baja al 90 %) de las tarjetas ya repasadas. | acumulado | Cuánto tardar en repasar; estado 5 «domina» (F3) | 10 |
| **Dificultad media de las tarjetas** (`dificultad_fsrs`) | indirecta | Promedio de la dificultad FSRS (1 fácil – 10 difícil) de las tarjetas ya repasadas. | acumulado | Qué temas reforzar y con qué formato | 10 |
| **Acierto medio en quizzes** (`acierto_quiz`) | directa | Promedio del puntaje (0-1) de los quizzes de lección de los últimos 90 días. | 90 días | Cuándo dar por comprendido un tema | 5 |
| **Acierto medio en pruebas de nivel** (`acierto_prueba`) | directa | Promedio del puntaje (0-1) de las pruebas de nivel de los últimos 90 días. | 90 días | Ubicar el nivel real y saltar lo que ya sabe | 3 |
| **Explicación con tus palabras (Feynman)** (`feynman_medio`) | directa | Promedio del mejor puntaje Feynman (0-1) de los temas donde se intentó. | acumulado | Estado 3 «comprende» (F3) | 3 |
| **Tarjetas que fallas una y otra vez** (`errores_repetidos`) | indirecta | Número de tarjetas con 2 o más fallos (nota «Otra vez»). | acumulado | Reexplicar el concepto en vez de repetir la tarjeta | 5 |
| **Tarjetas que ya probablemente olvidaste** (`olvido_estimado`) | indirecta | Fracción de tarjetas repasadas cuya probabilidad actual de recordarlas (FSRS) es menor de 80 %. | acumulado | Prioridad de repaso y requisitos por reponer | 10 |
| **Tasa de lapsos en repaso** (`tasa_lapsos`) | directa | Fracción de repasos de 30 días calificados «Otra vez» (nota 1). | 30 días | Ajustar cuántas tarjetas nuevas por día | 20 |
| **Tarjetas vencidas ahora** (`tarjetas_vencidas`) | indirecta | Tarjetas no suspendidas cuya fecha de repaso ya pasó. | ahora | Cuánto repaso pesa en el plan de hoy | 1 |
| **Segundos por tarjeta** (`segundos_por_tarjeta`) | indirecta | Mediana de segundos por repaso (se descartan los de más de 5 minutos) en 30 días. | 30 días | Tamaño de la sesión de repaso | 20 |

### Lectura y atención

| Métrica | Origen | Fórmula | Ventana | Qué decide | Muestra mínima |
|---|---|---|---|---|---|
| **Velocidad de lectura en español** (`wpm_es`) | indirecta | Palabras por minuto en textos en español, medidas con el tiempo de lectura activa (por defecto 180 hasta tener 5 min leídos). | 30 días | Estimar cuánto dura una lección para esta persona | 1 |
| **Palabras leídas por sesión** (`palabras_por_sesion`) | indirecta | Promedio de palabras de las sesiones de lectura de 20 segundos o más. | 30 días | Longitud de las partes de una lección | 5 |
| **Cuánto de cada lectura termina** (`avance_medio_lectura`) | indirecta | Promedio del avance (0-1) de las sesiones de lectura. | 30 días | Si recomendar ruta rápida o lección completa | 5 |
| **Lecturas que abandona a medias** (`abandono_lectura`) | indirecta | Fracción de sesiones de lectura que terminaron con menos del 50 % de avance. | 30 días | Partir las lecciones en partes más cortas | 5 |
| **Lecturas que termina** (`lectura_completa`) | indirecta | Fracción de sesiones de lectura con 90 % de avance o más. | 30 días | Formato recomendado | 5 |
| **Temas que relee** (`relecturas`) | indirecta | Fracción de los temas leídos en 60 días que tienen 2 o más sesiones de lectura. | 60 días | Detectar partes que no se entienden a la primera | 5 |
| **Uso de audio al leer** (`uso_audio`) | indirecta | Fracción de sesiones de lectura en las que el audio sonó. | 30 días | Ofrecer o no la lectura en voz alta | 5 |
| **Longitud de lectura que sí termina** (`lectura_que_termina`) | indirecta | Mediana de palabras de las sesiones terminadas (avance ≥ 90 %). | 60 días | Tamaño ideal de cada parte de una lección | 5 |
| **Reexplicaciones pedidas** (`reexplicaciones_30d`) | directa | Veces que pidió explicarle una parte de otra forma. | 30 días | Estilo de explicación que le funciona | 3 |
| **Partes que marcó «no lo entendí»** (`partes_no_entendidas`) | directa | De las partes de lección marcadas con «¿lo entendiste?» (sabido, dudoso o no) en 90 días, fracción con respuesta «no». | 90 días | Qué partes reexplicar antes de seguir | 5 |

### Ritmo y hábito

| Métrica | Origen | Fórmula | Ventana | Qué decide | Muestra mínima |
|---|---|---|---|---|---|
| **Minutos de estudio (7 días)** (`minutos_7d`) | indirecta | Suma de los latidos de estudio activo (la interfaz solo cuenta con acción real o audio sonando). | 7 días | Cuánto pesa el plan del día | 5 |
| **Minutos de estudio (14 días)** (`minutos_14d`) | indirecta | Suma de los latidos de estudio activo (la interfaz solo cuenta con acción real o audio sonando). | 14 días | Cuánto pesa el plan del día | 5 |
| **Minutos de estudio (30 días)** (`minutos_30d`) | indirecta | Suma de los latidos de estudio activo (la interfaz solo cuenta con acción real o audio sonando). | 30 días | Cuánto pesa el plan del día | 5 |
| **Días activos (7 días)** (`dias_activos_7d`) | indirecta | Días distintos con alguna actividad de estudio (tiempo, repaso, lectura, quiz, prueba, práctica, entrega…). | 7 días | Adherencia (F11) y tamaño de la sesión | 3 |
| **Días activos (14 días)** (`dias_activos_14d`) | indirecta | Días distintos con alguna actividad de estudio (tiempo, repaso, lectura, quiz, prueba, práctica, entrega…). | 14 días | Adherencia (F11) y tamaño de la sesión | 3 |
| **Días activos (30 días)** (`dias_activos_30d`) | indirecta | Días distintos con alguna actividad de estudio (tiempo, repaso, lectura, quiz, prueba, práctica, entrega…). | 30 días | Adherencia (F11) y tamaño de la sesión | 3 |
| **Racha actual** (`racha_actual`) | indirecta | Días seguidos con actividad de estudio hasta hoy (o hasta ayer si hoy aún no estudió). | 90 días | Avisos y modo corto (F11) | 3 |
| **Mejor racha de 90 días** (`racha_maxima`) | indirecta | La racha más larga de días seguidos con actividad en los últimos 90 días. | 90 días | Meta realista de constancia | 3 |
| **Recaídas (3 días o más sin estudiar)** (`recaidas_30d`) | indirecta | Cuántas veces pasaron 3 o más días seguidos sin actividad entre dos días activos, en 30 días. | 30 días | Cuándo mandar un aviso o bajar la exigencia | 3 |
| **Hora en que más estudia** (`hora_tipica`) | indirecta | Hora del día (0-23) con más segundos de estudio activo en 30 días. | 30 días | Hora del aviso y de preparar lecciones | 7 |
| **Duración típica de una sesión** (`duracion_sesion`) | indirecta | Mediana de minutos de estudio de las sesiones (una sesión se corta con 30 minutos sin actividad), en 30 días. | 30 días | Tamaño de la sesión que sí termina y modo corto | 5 |
| **Minutos por día activo** (`minutos_por_dia_activo`) | indirecta | Minutos de estudio de 14 días / días activos de esos 14 días. | 14 días | Tamaño del plan diario | 3 |
| **Minutos de estudio por tema dominado** (`minutos_por_tema_dominado`) | indirecta | TODO el tiempo de estudio registrado (minutos) / temas con estado «dominado» o «probado». Es la fórmula única: la línea base de la fase F0 y el panel usan esta definición. | acumulado | La meta «aprender más rápido con el tiempo» (baja si se mejora) | 3 |

### Estilo de aprendizaje

| Métrica | Origen | Fórmula | Ventana | Qué decide | Muestra mínima |
|---|---|---|---|---|---|
| **Método al que dedica más tiempo** (`metodo_mas_tiempo`) | indirecta | Método (lección, noticias, lectura, tutor) con más segundos de lectura activa en 30 días. | 30 días | Formato recomendado y orden de las actividades | 5 |
| **Franja del día en que mejor repasa** (`mejor_franja`) | indirecta | Franja (madrugada 0-5, mañana 6-11, tarde 12-17, noche 18-23) con mayor fracción de repasos bien contestados; solo cuentan franjas con 10 repasos o más. | 90 días | Cuándo programar lo difícil | 30 |

### Contenido y calidad

| Métrica | Origen | Fórmula | Ventana | Qué decide | Muestra mínima |
|---|---|---|---|---|---|
| **Lecciones completas escritas para ti** (`lecciones_completas`) | indirecta | Lecciones de la persona con estado «completa». | acumulado | Cuánto preparar por adelantado | 1 |
| **Lecciones preparadas que sí abre** (`lecciones_abiertas`) | indirecta | De las lecciones completas escritas, fracción cuyo tema tiene fecha de «visto» en el avance. | acumulado | Si preparar menos por adelantado | 5 |
| **Verificaciones de contenido hechas** (`verificaciones`) | indirecta | Cuántas lecciones o afirmaciones se verificaron contra fuentes para esta persona. | acumulado | Qué contenido revisar con otra pasada | 1 |
| **Tareas de IA que fallaron** (`tareas_ia_fallidas`) | indirecta | Tareas de IA de esta persona que terminaron con error en 30 días. | 30 días | Confiabilidad de cada modelo (F2) | 1 |
| **Gasto en la API de IA este mes** (`gasto_api`) | indirecta | Dólares estimados que esta persona ha gastado en la API opcional en el mes en curso. | mes | Tope y enrutador de modelos (F2) | 1 |

### Metas y avance

| Métrica | Origen | Fórmula | Ventana | Qué decide | Muestra mínima |
|---|---|---|---|---|---|
| **Metas activas** (`metas_activas`) | directa | Objetivos de la persona con estado «activo». | ahora | Cuántas rutas críticas ordenar (F6) | 1 |
| **Entregas corregidas** (`entregas_corregidas`) | directa | Entregas de práctica ya corregidas en 90 días. | 90 días | Dominio nivel 4 «aplica» (F3) | 1 |
| **Puntaje medio de las entregas** (`puntaje_entregas`) | directa | Promedio del puntaje (0-100) de las entregas corregidas en 90 días. | 90 días | Estado 4 «aplica» (F3) | 3 |

### Decisión y comportamiento

| Métrica | Origen | Fórmula | Ventana | Qué decide | Muestra mínima |
|---|---|---|---|---|---|
| **Áreas distintas en la semana** (`variedad_areas_7d`) | indirecta | Número de áreas distintas con actividad de estudio en 7 días (dispersión entre áreas). | 7 días | Avisar de dispersión y tope de áreas activas (F5) | 5 |
| **Cambios de tema en la semana** (`cambios_de_tema_7d`) | indirecta | Veces que el tema cambió entre dos actividades de estudio seguidas, en 7 días. | 7 días | Intercalado frente a bloque; fatiga (F5) | 10 |
| **Sugerencias de «Hoy» mostradas** (`sugerencias_14d`) | indirecta | Siguientes pasos propuestos por la pantalla «Hoy» (uno por hora y destino) en 14 días. | 14 días | Base para medir si el orden propuesto se sigue | 5 |
| **Cuánto sigue lo que Hoy le sugiere** (`acuerdo_sugerencia`) | indirecta | De las sugerencias seguidas por una navegación desde «Hoy» en los 30 minutos siguientes, fracción en que fue justo al destino sugerido. | 14 días | Aprender los pesos del ordenador por persona (F5) | 5 |
| **Tiempo en «Hoy» antes de decidir** (`tiempo_en_decidir`) | indirecta | Mediana de segundos que pasa en la vista «Hoy» antes de ir a otra, en 14 días. | 14 días | Reducir la parálisis: un solo siguiente paso | 5 |

## 4. Interfaz de programación

| Ruta | Qué hace |
|---|---|
| `GET /api/metricas` | métricas de la persona con ficha completa, resumen de eventos y cuántas son usables |
| `POST /api/metricas/ajustar` | `{id, estado: mal\|ignorar\|ok, nota}` o `{familia, apagada}` |
| `GET /api/metricas/tendencia?id=` | historial diario de una métrica |
| `POST /api/evento` | `{eventos:[{tipo, objeto, valor, contexto}]}` (solo `vista` y `navega`) |

## 5. Limitaciones conocidas

- Si el siguiente paso sugerido es «pulso» (un botón de la misma pantalla), no hay navegación y no cuenta como seguido ni ignorado.
- «Días activos» aquí cuenta solo actividades de estudio; el panel de línea base de la fase F0 (🩺) cuenta cualquier actividad: pueden diferir en uno o dos días.
- Aún no se mide el dispositivo ni el intercalado de verdad: se añadirán con datos que hoy no se guardan.

## 6. Pruebas

`python3 pruebas/unidad_metricas.py` (18 pruebas: catálogo, sincronización sin duplicados, aislamiento entre perfiles, lista blanca de eventos, valores calculados con datos
inventados, confianza, ajustes, historial y que una métrica que falla no tire a las demás).
