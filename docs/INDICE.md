# 🧠 Índice y ⚡ Reto

> Versión fácil: [facil/INDICE.md](facil/INDICE.md) · Código: [`app/indice.py`](../app/indice.py), [`web/indice.js`](../web/indice.js)
> · Pruebas: [`pruebas/unidad_indice.py`](../pruebas/unidad_indice.py)

## Para qué existe

Las plataformas de cursos (y esta Academia hasta la 1.5) motivan con **rachas**: premian abrir la app, no saber.
El Índice premia **lo que sabes responder sin mirar**, con un número que sube o baja con cada respuesta, y el Reto es
la forma más corta de moverlo: 10 preguntas, ~5 minutos, un toque desde ☀️ Hoy.

No es un adorno: el Reto es **práctica de recuperación** (acordarse sin mirar) y, en temas que aún no lees,
**pre-prueba** (responder antes de estudiar prepara el terreno). Las dos están entre las técnicas que más fijan la
memoria. Cada fallo se vuelve tarjeta FSRS y enlaza su lección.

## Qué mide (y qué no)

Escala tipo CI: empieza en **100** y cada escalón vale **15**. **No es un CI** y **no te compara con otras personas**:
te compara con los **niveles del currículo**. Cada pregunta vale lo que el nivel de su módulo:

| Nivel del módulo | Dificultad | Índice entre |
|---|---|---|
| Fundamentos | 85 | < 92,5 |
| Intermedio | 100 | 92,5 – 107,5 |
| Avanzado | 115 | 107,5 – 122,5 |
| Experto | 130 | 122,5 – 137,5 |
| Horizonte | 145 | ≥ 137,5 |

Un Índice de 115 significa: respondes las preguntas de nivel Avanzado a mitad de camino entre adivinar y acertar
siempre. La escala va de **55** a **175** (piso y techo): responder al azar deja el Índice en el piso, no en cifras
sin sentido.

## Cómo se calcula

Modelo de respuesta al ítem con adivinación (3PL con discriminación fija) y actualización tipo **Elo**:

```
P(acierto) = g + (1 − g) / (1 + 10^((dificultad − Índice) / 40))     g = 1 / opciones (0,5 si la correcta se delata)
Índice    ← Índice + K · (resultado − P)                               resultado = 1 si acierta, 0 si no, g si «no sé»
K = 24 (primeras 20 respuestas) · 12 (hasta 60) · 8 (después)
```

- Acertar una difícil sube mucho; fallar una fácil baja mucho. Adivinar se descuenta.
- **Provisional** hasta 20 respuestas (un área, hasta 10): el número se mueve rápido para encontrar tu nivel.
- **±** = error estándar a partir de la información de Fisher de todas tus respuestas. Si pasas días sin retos, el
  Índice **no baja**: lo que crece es el ± (+~10 a los 60 días, como en Glicko). Nada de castigar por no entrar.
- Solo se guardan las **respuestas crudas** (`reto_respuesta`). El Índice global y el de cada área se **recalculan**
  reproduciendo ese registro: si la fórmula cambia, se recalcula todo sin migrar datos.
- **Récord personal**: el máximo al final de un reto, contado solo cuando el Índice ya es firme.

## Sin suerte: acertar sin saber no cuenta

Al revisar el banco real (1015 preguntas escritas por la IA) apareció la causa de los aciertos «de suerte»: **la
correcta era la opción más larga el 71 % de las veces**, y elegir siempre la más larga acertaba el **66 %** sin saber
nada. No era suerte: era una pista que la mente aprende sola. Las IA alargan la correcta porque la escriben con más
cuidado y matices que los distractores. Tres defensas:

1. **Retos neutrales al largo.** Cada pregunta guarda su `pista` = largo de la correcta ÷ largo de la opción más larga
   entre las demás. Las de pista fuerte (> 1,1) quedan fuera del reto. Entre las demás, cada ronda se arma para que la
   correcta sea la más larga (o empate) en ~1 de cada 4 preguntas y la más corta en ~1 de cada 4, como al azar con 4
   opciones. Así no sirve ni «elige la más larga» ni «nunca la más larga». Medido en el banco real: «elige la más
   larga» pasó de 66 % a ~19 % y «elige la más corta» queda en ~29 % (azar = 25 %). Si por falta de banco entra una
   de pista fuerte, acertarla vale como acertar entre 2 opciones (g = 0,5).
2. **Primero la respuesta, después las opciones.** La pregunta aparece sola con tres botones: **💪 La sé**, **🤔 Creo**
   y **🤷 No sé** (teclas `S`, `C`, `N`). Las opciones solo aparecen después, así que la respuesta se forma antes de
   ver los largos (práctica de recuperación de verdad, no reconocimiento).
   - **No sé** no deja adivinar: muestra la respuesta y vale `g`, lo mismo que daría adivinar en promedio. Decir la
     verdad no cuesta ni regala nada, pero quita la varianza de la suerte. Responder solo lo fácil y decir «no sé»
     en lo difícil **no protege** el Índice (hay una prueba que lo simula).
   - **La sé** y fallar = **falsa seguridad**: se muestra aparte. Lo ideal es que «la sé» acierte casi siempre.
   - La calibración («la sé» acierta X %, «creo» Y %, falsa seguridad N) aparece al final de cada reto y en 🧠 Tu Índice.
3. **En el origen.** Todo prompt que escribe opción múltiple (quiz de la lección, quiz de práctica, prueba de nivel,
   chequeo semanal, prueba diferida) lleva la regla `REGLA_OPCIONES`: opciones de largo y detalle parecidos (±15 %),
   la correcta nunca la más larga ni la única con matices. Como la IA no siempre obedece (pedir «posiciones
   variadas» no evitó el sesgo de posición), la prueba diferida además **descarta** sin IA las preguntas con pista
   fuerte, y el reto las mide al vuelo.

Lo mismo en el resto de las evaluaciones que marcan dominio:

- **Quiz de la lección**: decir antes qué tan seguro estás (💪 Seguro / 🤔 Dudo / 🎲 Adivino) es obligatorio, y las
  opciones se barajan al mostrarlas. Acertar con «Adivino» **no cuenta** para el tema y vuelve como tarjeta.
- **Prueba de nivel** (la que permite saltar módulos): seguridad obligatoria y opciones barajadas. Un acierto es
  **firme** solo si no dijiste «adivino» y la correcta no se delataba por su largo. El módulo se supera con 95 % de
  aciertos firmes sobre (firmes + errores) y al menos la mitad de la prueba firme; un tema suelto queda como sabido
  con **2 aciertos firmes y ningún error**. Acertar con pista o adivinando no suma ni resta; fallar resta siempre.

## El Reto

- **10 preguntas** de opción múltiple de **tus** lecciones (las generadas por la IA; las abiertas no entran).
- Elegidas **cerca de tu nivel** en cada área (un poco por encima, con algo de azar): donde aciertas ~60-70 % es
  donde más se aprende. Máximo ~40 % de un área y un tema por pregunta mientras haya variedad.
- **Sin repetir** preguntas respondidas en los últimos 30 días (si el banco no alcanza, usa las más viejas).
- **Opciones barajadas** en el servidor: las IA suelen dejar la correcta en la misma posición (al medir un banco
  real, la correcta casi siempre estaba en las primeras posiciones y casi nunca en la última).
- **Neutral al largo** y con **«la sé / creo / no sé» antes de ver las opciones** (ver «Sin suerte»).
- **60 s por pregunta** (el servidor tolera 15 s más por la red). Fuera de tiempo cuenta como fallo. Recargar no
  regala tiempo; un reto abandonado se retoma donde iba con el reloj de nuevo.
- La respuesta correcta y la explicación **nunca** llegan al navegador antes de responder.
- Teclado: `S` / `C` / `N` (la sé, creo, no sé), luego `1`-`4` responde, `Enter` sigue.
- Al terminar: cambio del Índice, aciertos, récord, **qué estudiar ahora** (hasta 3 temas con su lección) y las
  preguntas falladas con su explicación. Lo fallado queda como tarjeta en 🔁 Repasar (origen `reto`).

Hacen falta al menos 10 preguntas en tus lecciones para abrir un reto; si no, la tarjeta de Hoy lo dice.

## Dónde aparece

- **☀️ Hoy**, arriba: el Índice, su ±, el nivel, cuánto falta para el siguiente, una línea con su evolución, el récord,
  «vs. tú hace 30 días» y el botón ⚡ Reto. La racha ya no se muestra en Hoy (sigue en 📈 Cómo aprendes).
- **⚡ Reto** en el menú principal.
- **🧠 Tu Índice** (`#/indice`): detalle, evolución, Índice por área, cómo se calcula y tu banco de preguntas por nivel.

## Privacidad y perfiles

Cada perfil ve solo su Índice, sus retos y preguntas de sus propias lecciones. No hay tabla entre personas: se
compite contra uno mismo (récord, hace 30 días, siguiente nivel). Una tabla compartida rompería la regla de perfiles
independientes.

## API

| Método | Ruta | Qué hace |
|---|---|---|
| GET | `/api/indice` | Índice global y por área, ±, historial, récord, hace 30 días, banco, reto abierto |
| POST | `/api/reto/nuevo` | Abre un reto o retoma el abierto; devuelve la pregunta sin la respuesta |
| GET | `/api/reto?id=` | Pregunta actual de un reto propio |
| POST | `/api/reto/responder` | `{id, i, elegida, seguridad}` (`seguridad`: `se`, `creo` o `nose`; `elegida: null` = sin tiempo o «no sé»). Corrige, mueve el Índice y da la siguiente o el cierre |

Las dos tablas entran en 🔬 «Qué sabe el sistema de ti» y en la exportación de tus datos.

Tablas: `reto` (preguntas barajadas del reto, posición, reloj) y `reto_respuesta` (una fila por respuesta: ítem, tema,
área, nivel, dificultad, opciones, acierto, tiempo, `pista` y `seguridad`). Se crean solas al arrancar; las columnas
`pista` y `seguridad` se agregan solas a una base vieja.

## Ajustes finos

Constantes al inicio de `app/indice.py`: `DIF_NIVEL`, `ESCALA`, `PISO`/`TECHO`, `PROVISIONAL`, `PREGUNTAS_RETO`,
`SEGUNDOS`, `SIN_REPETIR_DIAS`, `MIN_BANCO`, `PISTA_MAX`, `AZAR_PISTA`, `REGLA_OPCIONES`. Como el Índice se recalcula desde las respuestas, cambiarlas se aplica a
todo el historial al instante.

## Límites conocidos

- La dificultad de cada pregunta es la de su **módulo**, no la medida de la pregunta: con una sola persona no hay
  datos para calibrar ítem por ítem.
- Las áreas con pocas lecciones tienen pocas preguntas: su Índice es provisional más tiempo.
- La pista de largo es la más fuerte que se mide, no la única: un distractor absurdo también delata la correcta.
  Las lecciones ya escritas conservan sus preguntas con pista (fuera del reto); reescribir sus distractores sería un
  trabajo largo de la IA y se deja como opción.
- Las preguntas las escribió la IA: si una está mal, aparecerá como fallo injusto. Repórtala desde la lección
  (🔎 verificar) o regenera la lección.
