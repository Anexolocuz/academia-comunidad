# 🗺️ Plan de mejoras: medir el dominio y ordenar solo

> Parte de [Propósito](PROPOSITO.md). Estado vivo de cada fase: `privado/PROGRESO_MEJORAS.md` (solo en la copia de trabajo).
> Este plan nace de una revisión de lo que **falta**, lo que **pesa de más** y lo que se haría **distinto**.

## 0. Reglas del plan (no negociables)

1. **Calidad antes que velocidad.** Ninguna fase se activa por defecto si no hay evidencia de que no baja la calidad. Lo nuevo
   corre primero en **modo sombra** (calcula, compara y no decide) y pasa a decidir cuando la comparación lo respalda.
2. **No se quita ni se reduce ninguna capacidad.** Se **ordena**: lo que el sistema considera menos útil *hoy* pasa a una capa
   más profunda (mantenimiento, «Explorar», archivo), siempre alcanzable y siempre con la razón visible. Nada se borra.
3. **Cada persona aprende distinto.** Todo ajuste es **por persona**: pesos, ritmos, formatos y orden se aprenden de sus propios
   datos y arrancan con valores neutros. Los perfiles siguen independientes e invisibles entre sí.
4. **Mientras más medidas, mejor, con transparencia.** Toda métrica dice de dónde sale (directa o indirecta), cómo se calcula y qué
   decisión alimenta, y la persona puede verla, discutirla, corregirla o ignorarla.
5. **Reversible y respaldado.** Antes de cada migración, copia de `academia.db`; cada función nueva tras una bandera de configuración.
6. **Una cosa a la vez.** Un solo frente activo por vez (ver `PROGRESO_MEJORAS.md`); cada fase se cierra con pruebas, manuales y
   un criterio de aceptación comprobable antes de abrir otra.
7. **Local primero.** La API (Gemini) y el agente (Hermes) son **apoyos opcionales**; la Academia debe seguir funcionando sin ellos.

## 1. Qué se arma: el sistema de orden

Cuatro piezas que trabajan sobre **una línea de tiempo de eventos**, en este orden de datos → significado → decisión:

```
 eventos (directos e indirectos) ──► métricas ──► clasificador (¿qué es esto y para qué sirve?) ──► ordenador (¿qué toca hoy y por qué?)
                                         └──► dominio medido ──► señales de aporte a la frontera
```

### 1.1 `eventos.py` — una sola línea de tiempo
Hoy los datos viven en tablas separadas (actividad, repaso, lectura, quiz, entregas…). Se agrega `evento(usuario, ts, fuente, tipo,
objeto, valor, contexto)` como **proyección** de todas (no las reemplaza). **Directos:** respuestas, notas FSRS, entregas, metas,
valoraciones. **Indirectos:** velocidad y pausas de lectura, scroll, relecturas, hora, dispositivo, abandono de una sesión,
reintentos, el orden en que la persona elige, cuánto tarda en decidir, qué ignora.

### 1.2 `metricas.py` — catálogo y vista «🔬 Qué sabe el sistema de ti»
Cada métrica tiene `id`, qué mide, origen (directa/indirecta), fórmula, ventana, **confianza** (según cuántos datos hay) y la
decisión que alimenta. Se guardan en `metrica_valor`. La vista muestra todo lo que el sistema deduce de la persona y de dónde,
con «esto está mal» para corregirlo. Catálogo inicial en la sección 4.

### 1.3 `clasificador.py` — ontología de competencias
Cada objeto (tema, lección, noticia, tarjeta, nota, tarea, evento) se clasifica en un **mapa único de competencias**:
nodo, **tipo de conocimiento** (dato, concepto, procedimiento, criterio, habilidad aplicada), **nivel** (Fundamentos…Horizonte),
prerrequisitos y metas a las que sirve. Así los temas repetidos entre áreas (p. ej. probabilidad en matemáticas, finanzas e IA)
son **un solo nodo** que se domina una vez. Método: reglas sobre la estructura que ya existe + la IA con salida estructurada,
**dos pasadas independientes** y confianza por acuerdo; lo dudoso se marca para revisión. Sin dependencias nuevas; embeddings
solo si el servidor de IA los ofrece (opcional).

### 1.4 `ordenador.py` — qué toca hoy, y por qué
Puntúa cada candidato con criterios explícitos: utilidad para sus metas, lo que desbloquea, riesgo de olvido, dificultad esperada
frente a su nivel, su hora y energía (de sus datos), variedad (intercalado), fatiga y tiempo disponible. Los **pesos se aprenden
por persona** con un método simple y auditable (regresión logística pequeña sobre «lo hizo / lo aprendió a distancia»), con
exploración controlada. **Siempre explica «por qué esto»** y deja ver la alternativa. Sustituye a `cur.recomendar` solo tras el
modo sombra. El **tope de áreas activas** se resuelve aquí sin quitar nada: las áreas pasan solas, con explicación, entre
*activa → mantenimiento → archivada*, y vuelven cuando una meta las necesita.

## 2. Dominio medido (la métrica que valida la meta)

**Definición.** Un tema está «dominado» cuando hay **evidencia independiente de al menos dos tipos**: recuperación diferida sin
ayuda **y** transferencia a un problema nuevo, con memoria estable. Leer o abrir una lección cuenta como *exposición*, no como dominio.

| Estado | Evidencia mínima |
|---|---|
| 0 No visto | — |
| 1 Expuesto | lectura o ruta rápida |
| 2 Recuerda | acierta tarjetas/quiz |
| 3 Comprende | explica con sus palabras (Feynman aprobado) |
| 4 Aplica | resuelve un problema **nuevo** sin pistas |
| 5 Domina | 4 + **prueba diferida** aprobada a los 3, 14 y 45 días + estabilidad FSRS alta |

**Prueba diferida:** banco de preguntas **distintas** a las del quiz, generado de forma independiente y revisado por una segunda
pasada (idealmente otro modelo); sin pistas; se registran tiempo, ayuda usada y **confianza declarada** (para medir calibración con
Brier). Se descartan las preguntas malas (todas las aciertan o nadie las acierta). La barra de progreso pasa a mostrar
**dominado** y, aparte, **explorado**: así no hay falsa sensación de avance.

**Señales de aporte a la frontera** (por meta): cobertura de ramas dominadas, papers clave leídos y respondidos, ideas con novedad
comprobada, presentación y revisión de pares preparadas, huecos críticos pendientes, tiempo desde el último dominio. Se muestran
como **señales con su evidencia, nunca como una nota ni una orden**: decidir si aportar es siempre de la persona.

## 3. Fases

Cada fase: **qué** · **por qué** · **cómo se sabe que terminó**. Se hacen en este orden salvo que el progreso diga otra cosa.

| Fase | Qué | Por qué | Criterio de aceptación |
|---|---|---|---|
| **F0 Operación sana** | Alarma por Telegram si cae el servicio o falla la rutina diaria; cola de IA 100 % persistente; tablero de salud (cola, GPU, API, último ciclo); línea base de uso | Hoy el servicio puede estar caído horas sin que nadie lo sepa; la línea base permite saber si algo mejora | Matar el servicio recupera todo lo pendiente; la alarma llega en < 5 min; la línea base queda guardada |
| **F1 Eventos y métricas** | `eventos.py`, `metricas.py`, vista de transparencia, ≥ 40 métricas (sección 4) | Es el suelo de todo lo demás y lo que más quieres ver | Cada métrica tiene origen, fórmula, confianza y una prueba; la vista las lista por persona |
| **F2 Medir la IA** | Comparación pareada de lecciones: IA local, Hermes (qwen) y Gemini 3.8 Flash (razonamiento bajo/medio/alto), con rúbrica, comprobaciones objetivas (citas existentes, fórmulas, hechos) y lectura ciega de una muestra por la persona. **Enrutador de modelos** por tipo de tarea. **Skills como contexto:** las skills compartidas (método de enseñanza, investigación con fuentes, verificación) se cargan también en las llamadas de la Academia, para cualquier modelo, y se mide su efecto con la misma comparación | No hay datos de si la API o Hermes mejoran la calidad; sin esto, es fe | Un informe con calidad, tiempo y costo por modelo y tarea; el enrutador usa lo mejor medido, configurable |
| **F3 Dominio medido** | Estados 0-5, prueba diferida, transferencia, calibración, «explorado» vs «dominado» | Valida tu meta: comprender de verdad | Un tema solo llega a 5 con la evidencia de la tabla; informe de calibración por persona |
| **F4 Clasificador** | Ontología única de competencias; auto-etiquetado y fusión de temas repetidos; revisión de lo dudoso | Evita estudiar dos veces lo mismo y habilita ordenar de verdad | ≥ 90 % de acuerdo entre las dos pasadas en una muestra revisada a mano; nada se pierde al fusionar |
| **F5 Ordenador** | Puntuación, pesos por persona, explicación, estados de área automáticos; **modo sombra** primero | Con 25 áreas el avance es superficial; el orden debe ser automático y explicable | En sombra, el orden nuevo supera al actual en dominio a distancia por hora estudiada durante 2 semanas, **antes** de activarlo |
| **F6 Metas primero** | La meta define su ruta crítica y arrastra solo lo necesario; el ordenador la prioriza | Las metas son lo que importa; las áreas son un medio | Una meta nueva produce su ruta sin tocar las demás áreas |
| **F7 Señales de aporte** | Panel por meta (sección 2) y vínculo con laboratorio de ideas y presentación | Responde a «¿ya puedo aportar?» sin decidir por la persona | Cada señal muestra su evidencia y su fecha |
| **F8 Tutor examinador** | Recuperación guiada en vivo (pregunta → respuesta → repregunta hacia el error). Lo conduce **el agente (Hermes)** con sus skills y herramientas, hablando con la Academia por `/api/hermes/*` (la Academia guarda los eventos de dominio y las tarjetas); la app lo ofrece también en pantalla | Es el método con más evidencia y hoy es sobre todo «lección + quiz» | Una sesión deja eventos de dominio y tarjetas de lo fallado |
| **F9 Proyectos reales** | Mini-proyecto por módulo (software primero), revisión de código por rúbrica | En ingeniería de software se domina construyendo | Un proyecto entregado se revisa con rúbrica y alimenta el dominio 4 |
| **F10 Perfil de competencias** | Importar certificados, cursos y repositorios como evidencia con confianza | Evita repetir diagnósticos | Una meta nueva parte de lo ya demostrado |
| **F11 Hábito** | Modo corto como valor inicial en perfiles nuevos; métricas de adherencia; avisos | La constancia manda sobre la profundidad puntual | Más días activos por semana en los perfiles que lo usan |
| **F12 Publicación** | Versión de la comunidad, con ensayo y revisión manual | Que otros lo usen sin tus datos | `publicar.sh --ensayo` limpio y manuales al día |

## 4. Catálogo inicial de métricas

**D** = directa (la persona la dio) · **I** = indirecta (se deduce). Se amplía sin límite; cada una entra con su prueba.

| Familia | Métricas |
|---|---|
| **Dominio y memoria** | estado de dominio por tema (D/I) · retención a 1, 7, 30 y 90 días (D) · estabilidad y dificultad FSRS (I) · acierto diferido sin ayuda (D) · transferencia (D) · calibración de confianza, Brier (D) · errores repetidos por concepto (I) · olvido estimado por tema (I) · cobertura de prerrequisitos (I) |
| **Lectura y atención** | palabras por minuto por idioma y por dificultad (I) · pausas y relecturas (I) · avance real vs. tiempo abierto (I) · abandono por parte de lección (I) · «¿lo entendiste?» vs. acierto posterior (D/I) · partes que piden reexplicación (D) · profundidad que aguanta (I) |
| **Ritmo y hábito** | minutos reales al día (I) · días activos por semana (I) · racha y recaídas (I) · hora y duración típicas (I) · minutos por tema dominado (I) · tamaño de sesión que sí termina (I) · efecto del modo corto (I) |
| **Estilo de aprendizaje** | método que más rinde por persona (lectura, práctica, Feynman, tutor, cuaderno) (I) · formato que termina (I) · mejor franja del día (I) · dispositivo y su rendimiento (I) · intercalado vs. bloque (I) |
| **Contenido y calidad** | calidad de cada lección según uso y aciertos (I) · preguntas con mala discriminación (I) · citas verificadas o falsas (I) · acuerdo entre modelos (I) · tiempo y costo por tarea y por modelo (I) |
| **Metas y avance** | ruta crítica restante por meta (I) · plazo vs. ritmo (I) · brechas contra el mercado (I) · señales de aporte (I) · temas que más desbloquean (I) |
| **Decisión y comportamiento** | qué elige y qué ignora de lo sugerido (I) · cuánto tarda en decidir (I) · cuántas veces cambia de tema (I) · dispersión entre áreas en una semana (I) · acuerdo con el «por qué esto» (D) |
| **Sistema** | cola, tiempos y fallos de IA (I) · uso de GPU y de la API (I) · gasto por persona (I) · salud de la rutina diaria (I) |

## 5. IA: qué modelo hace qué (se decide en F2, con datos)

- **IA local principal:** sigue siendo la base y el respaldo. Gratis y privada.
- **Decisión (2026-10-29): la IA local de la Academia se queda como está** (el modelo ligero que ya usaba, más rápido y probado); el agente conserva el suyo. La comparación de F2 es entonces *IA local frente a la API*.
- **Otro modelo local (p. ej. el que ya usa otra aplicación del equipo):** una ventaja real si **se comparte** el modelo cargado:
  desaparecen los turnos y las descargas entre modelos. El costo suele ser la velocidad (un modelo mayor en la misma tarjeta
  genera menos palabras por segundo), así que se compara con F2 antes de cambiar.
- **Gemini 3.8 Flash por API** (`gemini-3.8-flash`, razonamiento `low | medium | high`, medio por defecto, precios de lanzamiento
  0,75 / 3,75 USD por millón hasta 2026-12-31): para lo que alguien está esperando y para tareas de verificación y juez. Los tokens de
  razonamiento se cobran como salida.
### Reparto: el agente como director, la Academia como motor

Los modelos **sí pueden usar skills** (son instrucciones que se cargan en el contexto); lo que cambia es quién las carga. El agente
(Hermes) aporta lo que una llamada simple a un modelo no tiene: bucle de agente, herramientas, tareas programadas, mensajes al celular,
memoria compartida y sus skills. Lo repetitivo y estructurado (lecciones, quizzes, noticias y verificación en lote) va **directo** al mejor
modelo medido, porque necesita salida en formato exacto, paralelismo y resultados predecibles.

| Tarea | Quién la hace |
|---|---|
| Lecciones, quizzes, noticias y verificación en lote | La Academia, con el mejor modelo medido en F2 (API; la IA local es el respaldo) |
| Tutor que examina, repaso por chat, revisión de proyectos de software (F9), avisos y alarmas | El agente, con sus skills y herramientas, usando las rutas `/api/hermes/*` de la Academia |
| Skills de método, fuentes y verificación | Se cargan también en las llamadas de la Academia, para que todos los modelos las sigan |

**Privacidad del agente:** si el agente usa una API, sus conversaciones salen al proveedor, incluido lo que la Academia nunca manda por su
cuenta (tutor, apuntes, cartera). Se decide aparte y por escrito; por defecto el agente usa el modelo local para eso.

- **Agentes y asistentes externos:** si usan una interfaz compatible con OpenAI, pueden apuntar al mismo proveedor con su propia
  clave; la Academia no comparte la suya.

## 6. Riesgos y cómo se cubren

| Riesgo | Cobertura |
|---|---|
| Un juez de IA favorece su propio estilo | Rúbrica fija, **comprobaciones objetivas** y lectura ciega humana; jueces cruzados |
| Más métricas = más ruido | Cada métrica lleva **confianza**; las de poca muestra no deciden |
| El ordenador oculta cosas | Nada se oculta: capas visibles, razón en cada decisión y «ver lo que quedó fuera» |
| Los datos indirectos incomodan | Todo visible y corregible en «Qué sabe el sistema de ti»; se puede apagar una familia de métricas |
| Cambios grandes rompen datos | Respaldo antes de migrar, banderas de configuración, modo sombra y pruebas |
| El agente conversa con una API y filtra lo privado | Decisión explícita y por escrito; el modelo local queda para tutor, apuntes y cartera |
| Dispersión (muchos frentes) | **Un frente activo**, `PROGRESO_MEJORAS.md` y cierre de cada fase antes de abrir otra |
