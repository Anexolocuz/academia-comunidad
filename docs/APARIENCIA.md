# 🎨 Apariencia y temas (manual completo)

> ¿Prefieres lo corto? → [Versión fácil](facil/APARIENCIA.md)

## Para quien la usa

**⚙️ Ajustes → Básico → 🎨 Apariencia** (se guarda en cada navegador, así el celular y el PC pueden verse distinto):

- **Modo:** automático (sigue al sistema), claro u oscuro.
- **Paleta:** Clásica, Bosque, Océano, Atardecer, Sepia (para leer mucho rato) y Alto contraste (accesible).
- **Color de acento propio:** cualquier color; «Usar el de la paleta» lo quita.
- **Tamaño de letra:** pequeña, normal, grande, muy grande (todo escala, también fórmulas y botones).

## Cómo funciona (para modificarla)

Todo el aspecto sale de **variables CSS** («tokens») definidas en `web/estilo.css` → `:root`:

| Token | Uso |
|---|---|
| `--fondo`, `--panel`, `--panel2` | fondo de la página, tarjetas, zonas secundarias |
| `--texto`, `--suave` | texto principal y secundario |
| `--borde` | bordes y separadores |
| `--acento`, `--acento-t` | color principal (botones, enlaces) y el texto sobre él |
| `--bien`, `--mal`, `--medio` | aciertos, errores, avisos |
| `--radio`, `--sombra` | esquinas y sombras |

El modo oscuro redefine los mismos tokens (`@media (prefers-color-scheme: dark)` y `[data-theme="dark"]`).
Una **paleta** solo cambia tokens: la interfaz (`aplicarApariencia()` en `web/app.js`) los pone en
`document.documentElement.style` según el modo activo. Así nunca se rompe el diseño.

## Crear una paleta nueva (y compartirla)

1. Copia `web/temas/bosque.json` como `web/temas/mi-paleta.json`:

   ```json
   {
     "nombre": "Mi paleta",
     "descripcion": "Una línea que la describa",
     "claro":  {"fondo": "#ffffff", "panel": "#ffffff", "panel2": "#f0f0f0", "texto": "#111111", "suave": "#555555",
                "borde": "#dddddd", "acento": "#7a3cff", "acento-t": "#ffffff"},
     "oscuro": {"fondo": "#101010", "panel": "#1a1a1a", "panel2": "#242424", "texto": "#eeeeee", "suave": "#aaaaaa",
                "borde": "#333333", "acento": "#b18cff", "acento-t": "#120a24"}
   }
   ```

2. Añádela a `web/temas/index.json`: `{"id": "mi-paleta", "nombre": "Mi paleta", "descripcion": "…"}`.
3. Recarga la página: aparece en Ajustes. No hace falta reiniciar.
4. **Contraste:** texto/fondo al menos 4.5:1 y `acento-t`/`acento` al menos 4.5:1 (comprueba en
   https://webaim.org/resources/contrastchecker/). Prueba claro y oscuro, celular y PC.
5. Para compartirla con la comunidad: un pull request con el JSON y una captura ([CONTRIBUTING.md](../CONTRIBUTING.md)).

Solo se aceptan claves con letras, números y guiones; los valores son colores CSS.

## Llegar a más público: ideas en marcha

- **Capturas y GIF** en el README (claro y oscuro, celular y PC) — es lo que más convence.
- **Traducciones:** hoy la interfaz está en español; los textos viven en `web/app.js`. El siguiente paso es sacarlos
  a `web/idiomas/<código>.json` (se aceptan contribuciones).
- **Logo e icono:** `web/icono.svg` (+ PNG 180/192/512 para iPhone y Android). Si cambias el SVG, regenera los PNG:
  `for n in 180 192 512; do rsvg-convert -w $n -h $n web/icono.svg -o web/icono-$n.png; done`.
- **Accesibilidad:** paleta de alto contraste, escalado de letra, botones con `aria-label`.
