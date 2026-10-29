# 🔔 Modo corto y avisos (manual completo)

> ¿Prefieres lo corto? → [Versión fácil](facil/AVISOS_Y_MODO_CORTO.md)

Pensado para quien estudia **pocos minutos al día** (y para quien necesita un empujón): una sesión que cabe en su
tiempo y, **si él lo decide**, un recordatorio en el celular. Ambos son **por persona** y los avisos **vienen apagados**.

## ⏱️ Modo corto

**Ajustes → 🔔 … → Modo corto**: 5, 10, 15, 20 o 30 minutos al día. Al elegirlo, el perfil queda con esa meta de minutos,
**1 tema nuevo y 10 tarjetas nuevas por día**, sin «todo el día a máxima profundidad». «Hoy» muestra arriba **«⏱️ Tu sesión
de N minutos»** con pocos pasos: un pulso (2 min), un repaso que cabe (≈25 s por tarjeta) y **una parte** de la lección
siguiente (no la lección entera). Para quitarlo: «Apagado».

## 🔔 Avisos

Un mensaje al día, a la hora elegida, **solo si hay algo por hacer**: «🎓 Tu sesión de hoy (10 min): 🔁 12 tarjetas por
repasar · 📖 1 lección para hoy.». Opcional: el título de lo siguiente. **Nunca** el contenido de lo que estudia, su
perfil ni su progreso.

| Canal | Qué necesita | Notas |
|---|---|---|
| **Telegram** | Un bot (el administrador lo crea una vez con @BotFather y pega el token) | Cada persona pulsa «Obtener código», se lo escribe al bot y pulsa «Vincular»: así se enlaza **su** chat y no el de otro |
| **ntfy** | La app gratuita ntfy (iPhone/Android) | Sin número ni cuenta. Se genera un **tema** largo (funciona como contraseña) y se suscribe en la app |
| **Dirección propia (webhook)** | Un servicio que reciba un POST | Recibe `{"texto", "text", "url"}`. Debe ser una dirección **pública** (nunca de tu casa). Sirve para Home Assistant, Zapier, n8n o un puente propio hacia WhatsApp |

**WhatsApp** no tiene una puerta gratuita y oficial para esto: la Academia no le manda nada por sí sola; se puede llegar con un webhook.

**Administrador:** el token del bot, el servidor de ntfy (por defecto ntfy.sh, puede ser el tuyo) y la dirección con la que se abre
la Academia (va dentro del aviso para tocar y entrar) se configuran en Ajustes → … → 🛠️ Administración. El token se guarda en
`datos/secretos.json` (permiso 600).

**Qué sale a internet:** solo ese texto corto hacia el canal que la persona eligió (Telegram, el servidor de ntfy o su webhook).
Si no activa los avisos, no sale nada.

## Para quien modifica el código
`app/avisos.py` (canales, vínculo de Telegram con código, envío diario una vez por persona, a su hora, y solo si hay algo),
`servidor.py` (`resumen_aviso`, `_sesion_corta`, rutas `/api/avisos*`; el trabajador de fondo llama `avisos.enviar_pendientes` cada
minuto) y `web/nube.js`. El perfil guarda `sesion_corta` (minutos; 0 = apagado).
