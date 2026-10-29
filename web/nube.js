/* Academia — modo corto, avisos opcionales y API de IA opcional (vista #/conexiones y tarjeta «sesión corta» de Hoy).
   Se carga después de app.js y usa sus utilidades (api, esc, aviso, VISTAS, vista, $, $$). Todo está APAGADO por
   defecto y es por persona; lo que cambia la configuración de todo el PC (clave de la API, bot) solo lo ve el administrador. */
"use strict";

/* ---------- Hoy: «tu sesión de N minutos» ---------- */
function sesionCortaHtml(d) {
  const s = d.sesion_corta;
  if (!s || !s.pasos.length) return "";
  return `<div class="tarjeta" style="border-color:var(--bien)"><b>⏱️ Tu sesión de ${s.minutos} minutos</b>
    <div class="suave peq">Pocos pasos, lo que más rinde hoy. Con eso basta; si te sobra tiempo, el resto de la página sigue ahí.</div>
    <ol style="margin:.5rem 0 0;padding-left:1.2rem">${s.pasos.map((p) =>
      `<li style="margin:.3rem 0"><a href="#/${esc(p.ir)}">${esc(p.titulo)}</a> <span class="suave peq">· ~${p.min} min</span></li>`).join("")}</ol></div>`;
}

const NUBE_USD = (x) => "US$ " + Number(x || 0).toLocaleString(LOC, { minimumFractionDigits: 2, maximumFractionDigits: 2 });

VISTAS.conexiones = async () => {
  const [yo, nb, av] = await Promise.all([api("yo"), api("nube"), api("avisos")]);
  const p = yo.perfil, n = nb.yo, a = av.ajustes, adm = nb.admin;
  const cfg = nb.config;
  const corto = +p.sesion_corta || 0;
  const grupos = Object.entries(nb.grupos);
  vista.innerHTML = `<h1>🔔 Estudio suave, avisos y ☁️ API</h1>
    <p class="suave peq">Todo esto es <b>opcional y está apagado</b> hasta que tú lo enciendas. <a href="#/ajustes">← Ajustes</a></p>

    <div class="tarjeta"><b>⏱️ Modo corto</b>
      <p class="suave peq">Si estudias pocos minutos al día, la Academia arma una sesión que cabe en ese tiempo: un pulso, un poco de repaso y <b>una parte</b> de una lección (no la lección entera). Aprender cada día un poco rinde más que mucho un solo día.</p>
      <div class="chips">${[[0, "Apagado"], [5, "5 min"], [10, "10 min"], [15, "15 min"], [20, "20 min"], [30, "30 min"]].map(([m, t]) =>
        `<button class="chip ${corto === m ? "activo" : ""}" data-corto="${m}">${t}</button>`).join("")}</div>
      <p class="suave peq" id="cortoNota">${corto ? `Activo: ${corto} minutos al día, 1 tema nuevo y 10 tarjetas nuevas por día.` : "Apagado: usas tu meta de minutos normal."}</p></div>

    <div class="tarjeta" id="cajaAvisos"><b>🔔 Recordatorio diario en tu celular</b>
      <p class="suave peq">Una vez al día, a la hora que elijas, te llega un mensaje corto con <b>cantidades</b> («12 tarjetas por repasar, 1 lección»). Nunca lo que estudias, tu perfil ni tu progreso. Solo si hay algo por hacer. <b>Apagado por defecto.</b></p>
      <label>¿Por dónde?</label>
      <select id="avCanal"><option value="">— elige —</option>${Object.entries(av.canales).map(([k, v]) => `<option value="${k}" ${a.canal === k ? "selected" : ""}>${esc(v)}</option>`).join("")}</select>
      <div id="avDetalle"></div>
      <div class="rejilla"><div><label>Hora</label><input type="time" id="avHora" value="${esc(a.hora)}" style="width:auto"></div></div>
      <label class="fila" style="font-weight:500"><input type="checkbox" id="avTit" ${a.con_titulos ? "checked" : ""} style="width:auto;min-height:0"> Incluir el título de lo siguiente (así el mensaje pasa por Telegram/ntfy/tu servicio)</label>
      <label class="fila" style="font-weight:600"><input type="checkbox" id="avActivo" ${a.activo ? "checked" : ""} style="width:auto;min-height:0"> Activar los avisos</label>
      <div class="fila"><button class="btn pri" id="avGuardar">💾 Guardar</button><button class="btn" id="avPrueba">📨 Enviar una prueba</button><span id="avEstado" class="suave peq"></span></div>
      ${av.error ? `<p class="peq" style="color:var(--mal)">Último fallo: ${esc(av.error.mensaje)}</p>` : ""}
      <p class="suave peq">WhatsApp no tiene una puerta gratuita y oficial para esto. Si usas un puente propio, elige «Dirección propia (webhook)».</p></div>

    <div class="tarjeta" id="cajaNube"><b>☁️ API de IA (opcional)</b>
      ${cfg.configurada && cfg.activa ? "" : `<p class="peq" style="color:var(--medio)">${adm ? "Aún no está lista: configúrala abajo en «Administración»." : "El administrador aún no la dejó lista. Mientras tanto todo corre en la IA local."}</p>`}
      <p class="suave peq">Hace las tareas <b>más rápido</b> y, con un modelo mayor, a veces mejor. La IA local sigue siendo el camino principal: si la API falla o se acaba tu tope, la tarea sigue sola en tu equipo. <b>Apagada por defecto.</b></p>
      <div class="tarjeta" style="background:var(--fondo2,transparent)"><b>🔒 Qué sale y qué no</b>
        <ul class="peq" style="margin:.3rem 0 0;padding-left:1.1rem">
          <li><b>Sale</b> (a ${esc(cfg.proveedor || "tu proveedor")}): el tema, las fuentes y los textos de la tarea que elijas abajo. Tu nombre se quita siempre.</li>
          <li><b>Tus metas y tu situación</b> solo salen si lo marcas aquí.</li>
          <li><b>Nunca sale</b>: el tutor, tus apuntes y fotos, tus entregas y respuestas, tus ideas, tu cartera y pronósticos, reportes ni lo que estudiaste fuera.</li></ul></div>
      <label class="fila" style="font-weight:600"><input type="checkbox" id="nbUsar" ${n.usar ? "checked" : ""} style="width:auto;min-height:0"> Usar la API en mi cuenta</label>
      <label>¿Para qué tareas?</label>
      <div class="chips" style="margin-bottom:.4rem">
        <button class="chip" data-atajo="lecciones">📖 Solo lecciones (recomendado)</button>
        <button class="chip" data-atajo="todo">🌐 Todo</button>
        <button class="chip" data-atajo="nada">⛔ Nada</button></div>
      ${grupos.map(([k, t]) => `<label class="fila" style="font-weight:500"><input type="checkbox" data-grupo="${k}" ${n.grupos.includes(k) ? "checked" : ""} style="width:auto;min-height:0"> ${esc(t)}</label>`).join("")}
      <label class="fila" style="font-weight:500"><input type="checkbox" id="nbMetas" ${n.enviar_metas ? "checked" : ""} style="width:auto;min-height:0"> Mandar también mis metas y situación (para que se adapte mejor)</label>
      <label class="fila" style="font-weight:500"><input type="checkbox" id="nbReserva" ${n.usar_reserva !== false ? "checked" : ""} style="width:auto;min-height:0"> Si la API principal se acaba, usar la API de reserva del administrador (si hay)</label>
      <div class="rejilla"><div><label>Si el límite es mensual, reintentar cada (días; 0 = lo que fije el administrador)</label><input type="number" id="nbDias" min="0" max="60" value="${n.reintento_dias || 0}" style="width:7rem"></div></div>
      <div class="rejilla" ${n.plan_gratuito ? "hidden" : ""}><div><label>Mi tope al mes (USD)</label><input type="number" id="nbTope" min="0" step="0.5" value="${n.tope_usd}" style="width:7rem"></div></div>
      ${n.plan_gratuito ? `<p class="peq">🆓 <b>Plan gratuito:</b> sin costo. Este mes: ${n.llamadas} llamadas y ${(n.tokens || 0).toLocaleString(LOC)} tokens. Al llegar al límite del proveedor, la tarea sigue sola en la IA local.</p>
        <p class="peq" style="color:var(--medio)">⚠️ En el nivel gratuito, el proveedor puede usar lo que se le manda para mejorar sus productos y personas pueden leerlo. Por eso nunca sale tu nombre ni lo personal. Si quieres máxima privacidad, apaga «Rutas, metas, frontera y mercado» y usa un plan de pago.</p>`
      : `<p class="peq">Este mes llevas <b>${NUBE_USD(n.gastado_usd)}</b> de ${NUBE_USD(n.tope_usd)} (${n.llamadas} llamadas) · entre todos: ${NUBE_USD(n.gastado_global_usd)} de ${NUBE_USD(n.tope_global_usd)}. El costo es una estimación con los precios que puso el administrador.</p>`}
      <div class="fila"><button class="btn pri" id="nbGuardar">💾 Guardar</button><span id="nbEstado" class="suave peq"></span></div></div>

    ${adm ? `<details class="tarjeta" id="cajaAdmin" ${(!cfg.configurada || !av.config.tiene_token) ? "open" : ""}><summary><b>🛠️ Administración</b> <span class="suave peq">(solo tú: la clave de la API y el bot de Telegram)</span></summary>
      <h2>☁️ Conectar una API</h2>
      <label class="fila" style="font-weight:600"><input type="checkbox" id="adActiva" ${cfg.activa ? "checked" : ""} style="width:auto;min-height:0"> Permitir la API en esta Academia (interruptor general)</label>
      <label class="fila" style="font-weight:600"><input type="checkbox" id="adGratis" ${cfg.plan_gratuito ? "checked" : ""} style="width:auto;min-height:0"> 🆓 Mi clave es del plan gratuito (costo 0, sin tope en dinero; el proveedor pone sus propios límites)</label>
      <p class="suave peq">Desmárcalo si tu proyecto tiene facturación activada: entonces se calcula el costo y se aplican los topes en dólares. En el plan gratuito algunos proveedores (Google, por ejemplo) pueden usar lo que se les manda para mejorar sus productos.</p>
      <label>Proveedor</label><select id="adProv"><option value="">— elige —</option>${cfg.proveedores.map((x) => `<option value="${x.id}" ${cfg.proveedor === x.id ? "selected" : ""}>${esc(x.nombre)}</option>`).join("")}</select>
      <p class="peq" id="adClaveAyuda"></p>
      <label>Dirección de la API <span class="suave">(se rellena sola; cámbiala solo para «Otro»)</span></label><input type="text" id="adUrl" value="${esc(cfg.url)}">
      <label>Clave de la API <span class="suave">${cfg.tiene_clave ? `· guardada ${esc(cfg.pista_clave)} (déjala vacía para conservarla)` : ""}</span></label>
      <input type="password" id="adClave" autocomplete="off" placeholder="${cfg.tiene_clave ? "••••••••" : "pega aquí tu clave"}">
      <label>Modelo</label><div class="fila"><input type="text" id="adModelo" value="${esc(cfg.modelo)}" list="adModelos" style="flex:1"><datalist id="adModelos"></datalist><button class="btn peq" id="adVer">📋 Ver modelos</button></div>
      <label>Modelo de respaldo <span class="suave">(si el principal está saturado o no responde se prueba este antes de pasar a la IA local; vacío = el sugerido)</span></label>
      <input type="text" id="adRespaldo" value="${esc(cfg.modelo_respaldo || "")}" list="adModelos">
      <label>API de reserva <span class="suave">(si la principal llega a su límite, se prueba esta antes de pasar a la IA local; cada persona puede desactivarla)</span></label>
      <select id="adProv2"><option value="">— ninguna —</option>${cfg.proveedores.map((x) => `<option value="${x.id}" ${cfg.proveedor2 === x.id ? "selected" : ""}>${esc(x.nombre)}</option>`).join("")}</select>
      <div class="rejilla"><div><label>Modelo de la reserva</label><input type="text" id="adModelo2" value="${esc(cfg.modelo2 || "")}" placeholder="el sugerido del proveedor"></div>
        <div><label>Su respaldo</label><input type="text" id="adModelo2r" value="${esc(cfg.modelo2_respaldo || "")}"></div>
        <div><label>Su clave ${cfg.tiene_clave2 ? "(ya guardada)" : ""}</label><input type="password" id="adClave2" autocomplete="off" placeholder="${cfg.tiene_clave2 ? "••••••••" : "pega aquí la clave"}"></div>
        <div><label>Si el límite es mensual, reintentar cada (días)</label><input type="number" id="adDias" min="1" max="60" value="${cfg.reintento_mensual_dias || 15}"></div></div>
      <div id="adRazon" ${(cfg.proveedores.find((x) => x.id === cfg.proveedor) || {}).razonamiento?.length ? "" : "hidden"}>
        <label>Esfuerzo de razonamiento <span class="suave">(más alto = piensa más: mejor calidad, más lento y más caro)</span></label>
        <select id="adRaz">${[["", "Lo que decida el modelo"], ["low", "Bajo"], ["medium", "Medio (recomendado)"], ["high", "Alto (máxima calidad)"]].map(([v, t]) => `<option value="${v}" ${cfg.razonamiento === v ? "selected" : ""}>${t}</option>`).join("")}</select></div>
      <div class="rejilla" ${cfg.plan_gratuito ? "hidden" : ""}>
        <div><label>Precio entrada (USD por millón de tokens)</label><input type="number" id="adPin" min="0" step="0.01" value="${cfg.precio_estimado ? "" : cfg.precio_in}" placeholder="${cfg.precio_in}"></div>
        <div><label>Precio salida (USD por millón)</label><input type="number" id="adPout" min="0" step="0.01" value="${cfg.precio_estimado ? "" : cfg.precio_out}" placeholder="${cfg.precio_out}"></div>
        <div><label>Tope global al mes (USD)</label><input type="number" id="adTope" min="0" step="1" value="${cfg.tope_global_usd}"></div></div>
      ${!cfg.precio_estimado && !cfg.precio_in ? "" : ""}${cfg.precio_estimado ? `<p class="peq" style="color:var(--medio)">Sin precios, se usa una estimación alta (US$ ${cfg.precio_in} / ${cfg.precio_out}) para que el tope proteja. Pon los de tu proveedor para un cálculo justo.</p>` : ""}
      ${(cfg.pausas || []).length ? `<div class="tarjeta"><b>⏸️ En pausa por su límite o un fallo</b><ul class="peq">${cfg.pausas.map((x) => `<li><code>${esc(x.proveedor)}</code> · ${esc(x.modelo)} — vuelve a intentarse ${new Date(x.hasta * 1000).toLocaleString(LOC)}${x.mensual ? " (límite mensual)" : ""}</li>`).join("")}</ul>
        <button class="btn peq" id="adReanudar">▶️ Reintentar ahora</button></div>` : ""}
      <div class="fila"><button class="btn" id="adProbar">🔌 Probar</button><button class="btn pri" id="adGuardar">💾 Guardar</button><span id="adEstado" class="suave peq"></span></div>
      ${nb.ultimo_error ? `<p class="peq" style="color:var(--mal)">Último fallo de la API (${new Date(nb.ultimo_error.cuando * 1000).toLocaleString(LOC)}): ${esc(nb.ultimo_error.mensaje)}</p>` : ""}

      <h2>🤖 Bot de Telegram para los avisos</h2>
      <p class="suave peq">1) En Telegram abre <b>@BotFather</b> → <code>/newbot</code> → copia el token. 2) Pégalo aquí. 3) Cada persona lo vincula desde su propia cuenta con un código; así nadie recibe el aviso de otro.</p>
      <label>Token del bot <span class="suave">${av.config.tiene_token ? `· guardado ${esc(av.config.pista_token)}${av.config.bot ? " · @" + esc(av.config.bot) : ""}` : ""}</span></label>
      <input type="password" id="tgToken" autocomplete="off" placeholder="${av.config.tiene_token ? "••••••••" : "123456:ABC…"}">
      <label>Servidor de ntfy <span class="suave">(deja ntfy.sh o pon el tuyo)</span></label><input type="text" id="tgNtfy" value="${esc(av.config.ntfy_url)}">
      <label>Dirección con la que se abre la Academia <span class="suave">(va dentro del aviso para tocar y entrar; opcional)</span></label><input type="text" id="tgUrl" value="${esc(av.config.url_publica)}" placeholder="https://mi-equipo:puerto">
      <div class="fila"><button class="btn pri" id="tgGuardar">💾 Guardar</button><span id="tgEstado" class="suave peq"></span></div></details>` : ""}`;

  /* --- modo corto --- */
  $$("[data-corto]").forEach((b) => (b.onclick = async () => {
    const m = +b.dataset.corto;
    const cambios = m ? { sesion_corta: m, minutos_dia: m, nuevos_dia: 1, tarjetas_nuevas_dia: 10, dia_maxima: false } : { sesion_corta: 0 };
    await api("perfil", cambios);
    $$("[data-corto]").forEach((x) => x.classList.toggle("activo", x === b));
    $("#cortoNota").textContent = m ? `Activo: ${m} minutos al día, 1 tema nuevo y 10 tarjetas nuevas por día.` : "Apagado: usas tu meta de minutos normal.";
    aviso(m ? `Modo corto: ${m} min al día` : "Modo corto apagado");
  }));

  /* --- avisos --- */
  const pintarCanal = () => {
    const c = $("#avCanal").value, z = $("#avDetalle");
    if (c === "telegram") {
      z.innerHTML = !av.telegram_listo ? `<p class="peq" style="color:var(--medio)">El administrador aún no conectó un bot de Telegram. Pídele que lo haga (o elige ntfy).</p>`
        : `<p class="suave peq">Pulsa «Obtener código», escríbeselo a <b>@${esc(av.bot || "el bot")}</b> en Telegram y pulsa «Vincular».</p>
           <div class="fila"><button class="btn peq" id="avCodigo">1. Obtener código</button><b id="avCod"></b><button class="btn peq" id="avVincular">2. Vincular</button></div>
           <p class="peq">${a.canal === "telegram" && a.destino ? `✅ Vinculado (chat ${esc(a.destino)})` : "Sin vincular"}</p>`;
      const cod = $("#avCodigo");
      if (cod) {
        cod.onclick = async () => { const r = await api("avisos/codigo", {}); $("#avCod").textContent = r.codigo; };
        $("#avVincular").onclick = async () => {
          try { const r = await api("avisos/vincular", {}); a.canal = "telegram"; a.destino = r.destino; aviso("Telegram vinculado ✅"); pintarCanal(); }
          catch (e) { aviso(e.message, 6000); }
        };
      }
    } else if (c === "ntfy") {
      z.innerHTML = `<p class="suave peq">1) Instala la app <b>ntfy</b> (gratis, iPhone y Android). 2) Genera tu tema, que es como una contraseña: quien lo sepa puede leer tus avisos. 3) En la app pulsa «+» y escribe ese tema (servidor: ${esc(av.ntfy_url)}).</p>
        <label>Tu tema</label><div class="fila"><input type="text" id="avDestino" value="${esc(a.canal === "ntfy" ? a.destino : "")}" style="flex:1"><button class="btn peq" id="avGen">🎲 Generar</button></div>`;
      $("#avGen").onclick = async () => { $("#avDestino").value = (await api("avisos/tema", {})).tema; };
    } else if (c === "webhook") {
      z.innerHTML = `<p class="suave peq">Una dirección pública (https) que reciba un POST con <code>{"texto": "…", "url": "…"}</code>: Home Assistant, Zapier, n8n, un puente a WhatsApp…</p>
        <label>Dirección</label><input type="text" id="avDestino" value="${esc(a.canal === "webhook" ? a.destino : "")}" placeholder="https://…">`;
    } else z.innerHTML = "";
  };
  $("#avCanal").onchange = pintarCanal;
  pintarCanal();
  const datosAv = () => {
    const c = $("#avCanal").value;
    const o = { canal: c, hora: $("#avHora").value, con_titulos: $("#avTit").checked };
    if ($("#avDestino")) o.destino = $("#avDestino").value.trim();
    return o;
  };
  $("#avGuardar").onclick = async () => {
    try {
      await api("avisos", { ...datosAv(), activo: $("#avActivo").checked });
      $("#avEstado").textContent = "✅ Guardado"; aviso("Avisos guardados");
    } catch (e) { $("#avEstado").textContent = "❌ " + e.message; }
  };
  $("#avPrueba").onclick = async () => {
    $("#avEstado").innerHTML = `<span class="cargando"></span> Enviando…`;
    try { await api("avisos", datosAv()); await api("avisos/prueba", {}); $("#avEstado").textContent = "✅ Enviado: mira tu celular"; }
    catch (e) { $("#avEstado").textContent = "❌ " + e.message; }
  };

  /* --- API: mi parte --- */
  $$("[data-atajo]").forEach((b) => (b.onclick = () => {
    const a = b.dataset.atajo;
    $$("[data-grupo]").forEach((x) => (x.checked = a === "todo" || (a === "lecciones" && x.dataset.grupo === "lecciones")));
    $("#nbUsar").checked = a !== "nada" ? true : false;
  }));
  $("#nbGuardar").onclick = async () => {
    try {
      await api("nube/yo", { usar: $("#nbUsar").checked, grupos: $$("[data-grupo]").filter((x) => x.checked).map((x) => x.dataset.grupo),
        tope_usd: $("#nbTope") ? +$("#nbTope").value : n.tope_usd, enviar_metas: $("#nbMetas").checked,
        usar_reserva: $("#nbReserva").checked, reintento_dias: +$("#nbDias").value || 0 });
      $("#nbEstado").textContent = "✅ Guardado"; aviso("Guardado");
    } catch (e) { $("#nbEstado").textContent = "❌ " + e.message; }
  };

  /* --- administración --- */
  if (adm) {
    const ayuda = () => {
      const x = cfg.proveedores.find((q) => q.id === $("#adProv").value);
      $("#adClaveAyuda").innerHTML = x ? `${x.clave_url ? `Crea tu clave aquí: <a href="${escUrl(x.clave_url)}" target="_blank" rel="noopener">${esc(x.clave_url)}</a>. ` : ""}${x.modelos.length ? `Modelos sugeridos: ${x.modelos.map((m) => `<button class="chip" data-mod="${esc(m)}">${esc(m)}</button>`).join(" ")}` : "Pulsa «Ver modelos» para ver los que tu clave puede usar."}` : "";
      $$("[data-mod]").forEach((b) => (b.onclick = () => ($("#adModelo").value = b.dataset.mod)));
    };
    $("#adProv").onchange = () => {
      const x = cfg.proveedores.find((q) => q.id === $("#adProv").value);
      if (x) { $("#adUrl").value = x.url; $("#adModelo").value = x.modelos[0] || ""; }
      $("#adRazon").hidden = !(x && x.razonamiento.length);
      $("#adRaz").value = x && x.razonamiento.length ? "medium" : "";
      ayuda();
    };
    ayuda();
    const datosAd = () => {
      const o = { plan_gratuito: $("#adGratis").checked, activa: $("#adActiva").checked, proveedor: $("#adProv").value, url: $("#adUrl").value.trim(), modelo: $("#adModelo").value.trim(),
        razonamiento: $("#adRazon").hidden ? "" : $("#adRaz").value, modelo_respaldo: $("#adRespaldo").value.trim(),
        tope_global_usd: +$("#adTope").value || 0, proveedor2: $("#adProv2").value, modelo2: $("#adModelo2").value.trim(),
        modelo2_respaldo: $("#adModelo2r").value.trim(), reintento_mensual_dias: +$("#adDias").value || 15 };
      if ($("#adClave2").value.trim()) o.clave2 = $("#adClave2").value.trim();
      if ($("#adPin").value !== "") o.precio_in = +$("#adPin").value;
      if ($("#adPout").value !== "") o.precio_out = +$("#adPout").value;
      if ($("#adClave").value.trim()) o.clave = $("#adClave").value.trim();
      return o;
    };
    $("#adGuardar").onclick = async () => {
      try { await api("nube/config", datosAd()); $("#adClave").value = ""; $("#adClave2").value = ""; $("#adEstado").textContent = "✅ Guardado"; aviso("Configuración de la API guardada"); setTimeout(() => VISTAS.conexiones(), 500); }
      catch (e) { $("#adEstado").textContent = "❌ " + e.message; }
    };
    if ($("#adReanudar")) $("#adReanudar").onclick = async () => { await api("nube/reanudar", {}); aviso("Pausas quitadas"); VISTAS.conexiones(); };
    $("#adVer").onclick = async () => {
      try { await api("nube/config", datosAd()); } catch (e) { return ($("#adEstado").textContent = "❌ " + e.message); }
      $("#adEstado").innerHTML = `<span class="cargando"></span> Pidiendo la lista…`;
      try {
        const r = await api("nube/modelos", {});
        $("#adModelos").innerHTML = r.modelos.map((m) => `<option value="${esc(m)}">`).join("");
        $("#adEstado").textContent = `✅ ${r.modelos.length} modelos: escribe o elige uno en el campo Modelo`;
      } catch (e) { $("#adEstado").textContent = "❌ " + e.message; }
    };
    $("#adProbar").onclick = async () => {
      try { await api("nube/config", datosAd()); } catch (e) { return ($("#adEstado").textContent = "❌ " + e.message); }
      $("#adEstado").innerHTML = `<span class="cargando"></span> Probando…`;
      try {
        const r = await api("nube/probar", {});
        $("#adEstado").textContent = `✅ Funciona: respondió «${r.respuesta}» en ${r.segundos} s (${r.tokens_in}+${r.tokens_out} tokens ≈ US$ ${r.usd})`;
      } catch (e) { $("#adEstado").textContent = "❌ " + e.message; }
    };
    $("#tgGuardar").onclick = async () => {
      const o = { ntfy_url: $("#tgNtfy").value.trim(), url_publica: $("#tgUrl").value.trim() };
      if ($("#tgToken").value.trim()) o.telegram_token = $("#tgToken").value.trim();
      try { await api("avisos/admin", o); $("#tgToken").value = ""; $("#tgEstado").textContent = "✅ Guardado"; aviso("Guardado"); }
      catch (e) { $("#tgEstado").textContent = "❌ " + e.message; }
    };
  }
};
