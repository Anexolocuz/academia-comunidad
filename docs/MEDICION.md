# 🧪 Banco de pruebas de la IA

> Parte de [Plan de mejoras](PLAN_MEJORAS.md), fase F2 «Medir la IA». Estado: el banco de pruebas está construido; el informe
> con calidad, tiempo y costo por modelo se completa cuando se ejecuta la corrida completa.

Hasta ahora nadie había medido si una API o un modelo distinto mejoraba las lecciones: era fe. Este banco de pruebas
(`app/medicion.py`) compara modelos con **la misma tarea, los mismos temas y las mismas fuentes**, de modo que la única
diferencia sea el modelo.

## Qué compara

Cada **variante** es un modelo con un nivel de razonamiento y, opcionalmente, con las *skills* como contexto (`+sk`):

| Variante | Qué es |
|---|---|
| `local` | La IA local de la Academia |
| `g38-bajo`, `g38-medio`, `g38-alto` | Gemini 3.8 Flash con razonamiento bajo, medio y alto |
| `g35-alto` | Gemini 3.5 Flash (el respaldo) |
| `…+sk` | Cualquiera de las anteriores con el método de enseñar, investigar y verificar cargado en sus instrucciones |

Dos **tareas**, las mismas que hace la Academia de verdad:

1. **Parte de lección**: la misma petición que la lección a fondo, con ideas y fuentes fijas.
2. **Ejercicios**: el quiz y las tarjetas, usando el mismo código de producción (`lecciones.generar_ejercicios`).

Seis **temas** generales y verificables de áreas distintas (probabilidad, estructuras de datos, física, economía, inteligencia
artificial y ética). Las fuentes de cada tema se buscan **una sola vez** (`congelar`) y todas las variantes leen las mismas.

## Cómo se califica (tres capas)

| Capa | Qué mide | Peso en la decisión |
|---|---|---|
| **Comprobaciones objetivas** (por programa) | citas que apuntan a una fuente que no existe, enlaces inventados, secciones pedidas presentes, respuestas desplegables, fórmulas balanceadas, repeticiones en bucle, idioma y longitud. Da una nota de 0 a 100 con una fórmula visible en `revisar_parte` | alto: no depende de ninguna opinión |
| **Juez** | otro modelo califica de 1 a 5 exactitud, profundidad, claridad, ejemplos y fuentes, y lista cada error factual que encuentra. Las lecciones llegan **anónimas y en orden aleatorio**, en dos rondas con orden distinto | medio: puede favorecer su propio estilo |
| **Lectura ciega de la persona** | las lecciones sin nombre de modelo; la persona elige la mejor, la peor y marca errores | **decisiva**: es la verdad de fondo |

Un fallo (tiempo agotado, servicio saturado) **cuenta como dato** y nunca se sustituye por otro modelo; si no, la medición
quedaría contaminada. El costo se calcula a precio de lista aunque el plan gratuito no cobre, para saber qué pasaría con un plan de pago.

## Cómo se usa

```bash
# 1) Una sola vez: buscar y guardar las fuentes (con datos temporales, porque la búsqueda de papers guarda caché)
ACADEMIA_DATOS=$(mktemp -d) python3 app/medicion.py congelar
# 2) Generar y revisar (con los datos reales, porque ahí está la clave de la API, que este módulo nunca imprime)
python3 app/medicion.py correr --corrida 2026-10-29 --variantes local,g38-bajo,g38-medio,g38-alto
# 3) Juez, informe y lecturas ciegas
python3 app/medicion.py juzgar  --corrida 2026-10-29
python3 app/medicion.py informe --corrida 2026-10-29
python3 app/medicion.py ciega   --corrida 2026-10-29 --n 4
```

Todo queda en `datos/medicion/<corrida>/` (`resultados.jsonl`, `juicios.jsonl`, `informe.md`, `ciega/` y `clave_ciega.json`).
La corrida es **reanudable**: lo ya medido no se repite.

## Qué pasó en la primera corrida (2026-10-29)

La IA local completó las 12 tareas (nota objetiva media 92 en lecciones y 98 en ejercicios). Gemini casi no respondió: la
cuota del plan gratuito se agotó (429) y hubo saturación (503), así que **no hay aún comparación válida**. El juez también
falló por cuota. Por eso `correr` reintenta ahora los fallos (el último intento de cada tarea es el que cuenta), `congelar`
rehace las fuentes incompletas y `--pausa` espacia los pedidos. El reintento se programa con `privado/sistema/instalar_f2.sh`.

## Privacidad

Solo viajan temas generales y fuentes públicas: nunca el perfil, el tutor, los apuntes, las entregas, las ideas ni la cartera.
Los mensajes dicen «Estudiante anónimo» (hay una prueba que lo exige). No toca la cola de IA ni la base real.

## Cuidados con el equipo

- La IA local atiende un solo pedido a la vez: si la cola real está trabajando, el banco espera su turno y el **tiempo** de la
  IA local sale inflado. Para comparar tiempos, mídelo con la cola quieta.
- Si otro modelo (el de otra aplicación) está cargado en la tarjeta gráfica, el banco espera en vez de descargarlo.
- Respeta los límites del plan gratuito de la API: un solo pedido a la vez, con pausa entre pedidos.

## Pruebas

`python3 pruebas/unidad_medicion.py` (16 pruebas, sin red ni modelos): puntuación de las comprobaciones, citas e índices de código
que no son citas, anonimización reproducible, que el juez no nombre modelos, reanudación y que la lectura ciega no revele el modelo.
