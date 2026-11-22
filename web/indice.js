/* Academia — 🧠 Índice y ⚡ Reto (servidor: app/indice.py).
   El Índice es una escala tipo CI medida contra los niveles del currículo (no contra otras personas): sube o baja
   con lo que sabes responder sin mirar. El Reto son 10 preguntas de tus lecciones, cerca de tu nivel, con tiempo.
   Lo fallado vuelve como tarjeta y enlaza su lección. Se carga después de app.js. */
"use strict";

const IX_FECHA = (t) => new Date(t * 1000).toLocaleDateString(LOC, { day: "numeric", month: "short" });
const ixNum = (x) => (x == null ? "—" : Math.round(x));
const ixDelta = (x) => (x > 0 ? `<span class="ix-sube">▲ ${x.toFixed(1)}</span>` : x < 0 ? `<span class="ix-baja">▼ ${Math.abs(x).toFixed(1)}</span>` : `<span class="suave">= 0</span>`);

function ixLinea(hist, ancho = 260, alto = 54) {
  if (!hist || hist.length < 2) return "";
  const v = hist.map((p) => p.indice), lo = Math.min(...v) - 3, hi = Math.max(...v) + 3;
  const x = (k) => (k / (v.length - 1)) * (ancho - 6) + 3, y = (val) => alto - 4 - ((val - lo) / (hi - lo || 1)) * (alto - 8);
  const d = v.map((val, k) => `${k ? "L" : "M"}${x(k).toFixed(1)},${y(val).toFixed(1)}`).join(" ");
  return `<svg class="ix-linea" viewBox="0 0 ${ancho} ${alto}" preserveAspectRatio="none" role="img" aria-label="Tu Índice al final de cada reto, de ${Math.round(v[0])} a ${Math.round(v[v.length - 1])}">
    <path d="${d}" fill="none" stroke="var(--acento)" stroke-width="2" vector-effect="non-scaling-stroke" stroke-linejoin="round"/>
    <circle cx="${x(v.length - 1)}" cy="${y(v[v.length - 1])}" r="3.5" fill="var(--acento)"/></svg>`;
}

function ixMeta(g) {
  if (g.provisional) return `Provisional: faltan ${20 - g.n} respuestas para que sea firme`;
  return g.siguiente ? `+${g.siguiente.faltan} para <b>${esc(g.siguiente.nombre)}</b>` : "Nivel más alto de la escala";
}

/* Tarjeta de la pantalla Hoy: el número, la meta siguiente y un botón. Un toque para entrar. */
async function indiceHoy(zona) {
  if (!zona) return;
  let x;
  try { x = await api("indice"); } catch (e) { zona.innerHTML = ""; return; }
  const g = x.global, corto = x.banco.total < x.banco.minimo;
  const vs = x.hace30 != null ? `<span class="peq">vs. tú hace 30 días: ${ixDelta(g.indice - x.hace30)}</span>` : "";
  zona.innerHTML = `<div class="tarjeta ix-hoy">
    <div class="ix-cab" role="button" tabindex="0" id="ixVer" title="Ver el detalle de tu Índice">
      <div><div class="suave peq">🧠 Tu Índice</div>
        <div class="ix-num">${g.n ? ixNum(g.indice) : "?"}<small class="suave"> ${g.n ? "±" + Math.round(g.mas_menos) : ""}</small></div>
        <div class="peq">${g.n ? `${esc(g.nivel)} · ${ixMeta(g)}` : "Aún sin medir: haz tu primer reto"}</div></div>
      <div class="ix-der">${ixLinea(x.historial, 130, 46)}
        <div class="peq suave">${x.record != null ? `🏆 récord ${ixNum(x.record)}` : ""}</div>${vs}</div></div>
    ${corto ? `<p class="suave peq" style="margin:.5rem 0 0">Tus lecciones aún tienen ${x.banco.total} preguntas (hacen falta ${x.banco.minimo}). Abre o prepara lecciones y el reto se habilita solo.</p>`
      : `<button class="btn pri ix-btn" id="ixReto">${x.abierto ? `▶ Seguir el reto (${x.abierto.i}/${x.abierto.total})` : `⚡ Reto · ${x.escala.preguntas} preguntas · ~5 min`}</button>
         <div class="suave peq" style="text-align:center">${x.retos_hoy ? `${x.retos_hoy} reto(s) hoy · ` : ""}cuenta lo que sabes sin mirar, no los días seguidos</div>`}
  </div>`;
  $("#ixVer").onclick = () => ir("indice");
  $("#ixVer").onkeydown = (e) => { if (e.key === "Enter") ir("indice"); };
  if ($("#ixReto")) $("#ixReto").onclick = () => ir("reto");
}

/* ---------------------------------------------------------------- el reto */
VISTAS.reto = async () => {
  let p;
  try { p = await api("reto/nuevo", {}); }
  catch (e) {
    vista.innerHTML = `<div class="tarjeta"><h2>⚡ Reto</h2><p>${e.message === "banco_corto" ? "Tus lecciones todavía no tienen suficientes preguntas. Prepara o abre algunas lecciones y vuelve." : esc(e.message)}</p>
      <button class="btn" onclick="ir('hoy')">Volver</button></div>`;
    return;
  }
  let reloj = null, enviando = false;
  const parar = () => { if (reloj) clearInterval(reloj); reloj = null; };
  E.salir = () => { parar(); document.removeEventListener("keydown", escucha); };
  let teclas = () => {};
  const escucha = (ev) => teclas(ev);
  document.addEventListener("keydown", escucha);

  const pintar = (p) => {
    const q = p.pregunta, t0 = Date.now();
    window.scrollTo(0, 0);
    vista.innerHTML = `<div class="ix-reto">
      <div class="fila entre"><b>⚡ Reto</b><span class="suave peq">${p.i + 1} / ${p.total}</span></div>
      <div class="ix-pasos">${Array.from({ length: p.total }, (_, k) => `<i class="${k < p.i ? "hecho" : k === p.i ? "ahora" : ""}"></i>`).join("")}</div>
      <div class="ix-tiempo" aria-hidden="true"><i id="ixT"></i></div>
      <div class="suave peq" style="margin:.4rem 0">${esc(q.area)} · ${esc(q.nivel)}</div>
      <div class="pregunta"><div class="pq" id="ixPq"></div>
        <div id="ixSeg" class="ix-seg"><div class="suave peq">Antes de ver las opciones, piensa tu respuesta. ¿La sabes?</div>
          <div class="ix-seg-btns">
            <button class="btn pri" data-seg="se"><b>💪 La sé</b><small>tengo la respuesta</small></button>
            <button class="btn" data-seg="creo"><b>🤔 Creo</b><small>tengo una idea</small></button>
            <button class="btn fantasma" data-seg="nose"><b>🤷 No sé</b><small>ver la respuesta</small></button></div></div>
        <div id="ixOps" hidden>${q.opciones.map((o, j) => `<button class="opcion" data-j="${j}"><span class="ix-tecla">${j + 1}</span><span class="ix-op"></span></button>`).join("")}</div>
        <div class="exp" id="ixExp"></div></div>
      <div id="ixPie" class="suave peq">Teclas: <b>S</b> la sé · <b>C</b> creo · <b>N</b> no sé; luego 1-${q.opciones.length}. «No sé» vale lo mismo que adivinar en promedio, pero sin suerte: es la opción honesta.</div></div>`;
    pintarMd($("#ixPq"), q.texto);
    $$(".opcion", vista).forEach((b, j) => pintarMd($(".ix-op", b), q.opciones[j]));
    const barra = $("#ixT");
    parar();
    reloj = setInterval(() => {
      const r = Math.max(0, 1 - (Date.now() - t0) / (p.segundos * 1000));
      barra.style.width = r * 100 + "%";
      barra.classList.toggle("poco", r < 0.25);
      if (r <= 0) responder(null);
    }, 200);
    let seguridad = null;
    const elegirSeg = (sg) => {
      if (seguridad || enviando) return;
      seguridad = sg;
      $("#ixSeg").innerHTML = `<span class="etq">${{ se: "💪 La sé", creo: "🤔 Creo", nose: "🤷 No sé" }[sg]}</span>`;
      if (sg === "nose") { $("#ixOps").hidden = false; return responder(null); }
      $("#ixOps").hidden = false;
      teclas = (ev) => { const n = parseInt(ev.key, 10); if (n >= 1 && n <= q.opciones.length && !ev.repeat) responder(n - 1); };
    };
    $$("[data-seg]", vista).forEach((b) => (b.onclick = () => elegirSeg(b.dataset.seg)));
    const responder = async (j) => {
      if (enviando) return; enviando = true; parar();
      let r;
      try { r = await api("reto/responder", { id: p.id, i: p.i, elegida: j, seguridad }); }
      catch (e) { enviando = false; aviso("No se pudo enviar: " + e.message); return; }
      enviando = false;
      const ops = $$(".opcion", vista);
      ops.forEach((b) => (b.disabled = true));
      ops[r.correcta]?.classList.add("ok");
      if (j != null && !r.acierto) ops[j]?.classList.add("no");
      const titulo = r.seguridad === "nose" ? "🤷 No la sabías: esta es la respuesta" : r.falsa_seguridad ? "⚠️ Incorrecta, y dijiste «la sé»: falsa seguridad"
        : r.acierto ? (r.seguridad === "creo" ? "✅ Correcta (dijiste «creo»)" : "✅ Correcta") : j == null || !r.a_tiempo ? "⏱️ Se acabó el tiempo" : "❌ Incorrecta";
      const exp = $("#ixExp");
      exp.innerHTML = `<div class="fila entre"><b>${titulo}</b><span class="ix-delta">${ixDelta(r.delta)} → ${ixNum(r.indice)}</span></div>
        <div class="suave peq">${r.seguridad === "nose" ? "Queda como tarjeta para repasar. " : ""}Probabilidad esperada de acertar a tu nivel: ${Math.round(r.prob * 100)} %${!r.acierto ? ` · <a href="#/tema/${encodeURIComponent(r.tema)}">ver la lección: ${esc(r.tema_t)}</a>` : ""}</div><div id="ixExpTxt"></div>`;
      if (r.explicacion) pintarMd($("#ixExpTxt"), "💡 " + r.explicacion);
      const sig = () => (r.fin ? final(r.fin) : pintar(r.siguiente));
      $("#ixPie").innerHTML = `<button class="btn pri ix-btn" id="ixSig">${r.fin ? "Ver resultado" : "Siguiente →"}</button>`;
      $("#ixSig").onclick = sig; $("#ixSig").focus({ preventScroll: true });
      teclas = (ev) => { if (ev.key === "Enter" && !ev.repeat) { ev.preventDefault(); teclas = () => {}; sig(); } };
    };
    $$(".opcion", vista).forEach((b) => (b.onclick = () => { if (seguridad) responder(+b.dataset.j); }));
    teclas = (ev) => { const k = { s: "se", c: "creo", n: "nose" }[(ev.key || "").toLowerCase()]; if (k && !ev.repeat) elegirSeg(k); };
  };

  const final = (f) => {
    parar(); teclas = () => {};
    window.scrollTo(0, 0);
    const g = f.global;
    vista.innerHTML = `<div class="ix-reto">
      <div class="tarjeta ix-final">
        ${f.record_nuevo ? `<div class="ix-record">🏆 ¡Nuevo récord personal!</div>` : ""}
        <div class="suave peq">Tu Índice</div>
        <div class="ix-num grande">${ixNum(f.despues)} <small class="ix-delta">${ixDelta(f.delta)}</small></div>
        <div>${esc(g.nivel)} · ${ixMeta(g)} <span class="suave peq">(±${Math.round(g.mas_menos)})</span></div>
        <div class="peq" style="margin-top:.4rem"><b>${f.aciertos}/${f.total}</b> correctas</div>
        ${ixCalib(f.calibracion)}</div>
      ${f.debiles.length ? `<h2>📌 Lo que conviene estudiar ahora</h2>
        <p class="suave peq">Equivocarse en un reto no es perder: es justo lo que más enseña, si lo repasas pronto.
        ${f.tarjetas ? `Lo fallado ya quedó como <b>${f.tarjetas} tarjeta(s)</b> en 🔁 Repasar.` : ""}</p>
        ${f.debiles.map((d) => `<div class="tarjeta" style="cursor:pointer" data-tema="${esc(d.tema)}"><div class="suave peq">${esc(d.area)}</div><b>${esc(d.t)}</b> <span class="suave peq">→ abrir la lección</span></div>`).join("")}`
        : `<div class="tarjeta" style="border-color:var(--bien)">🎯 Sin fallos. El próximo reto vendrá más difícil.</div>`}
      ${f.fallos.length ? `<details class="tarjeta"><summary><b>Revisar las ${f.fallos.length} que fallaste</b></summary><div id="ixFallos"></div></details>` : ""}
      <div class="fila" style="margin-top:1rem"><button class="btn pri" id="ixOtro">⚡ Otro reto</button>
        <button class="btn" onclick="ir('indice')">🧠 Mi Índice</button><button class="btn fantasma" onclick="ir('hoy')">Hoy</button></div></div>`;
    $$("[data-tema]", vista).forEach((c) => (c.onclick = () => ir("tema/" + c.dataset.tema)));
    const zf = $("#ixFallos");
    if (zf) f.fallos.forEach((x) => {
      const d = document.createElement("div"); d.className = "ix-fallo"; zf.appendChild(d);
      pintarMd(d, `**${x.pregunta}**\n\n✔ ${x.correcta}\n\n${x.explicacion || ""}`);
    });
    $("#ixOtro").onclick = () => enrutar();
  };

  pintar(p);
};

/* Qué tan bien sabes lo que sabes: «la sé» debería acertar casi siempre. */
function ixCalib(c) {
  if (!c || !(c.se.n + c.creo.n + c.nose.n)) return "";
  const pct = (x) => (x.pct == null ? "—" : Math.round(x.pct * 100) + " %");
  return `<div class="ix-calib peq"><span>💪 La sé: <b>${pct(c.se)}</b> <span class="suave">(${c.se.aciertos}/${c.se.n})</span></span>
    <span>🤔 Creo: <b>${pct(c.creo)}</b> <span class="suave">(${c.creo.aciertos}/${c.creo.n})</span></span>
    <span>🤷 No sé: <b>${c.nose.n}</b></span>
    ${c.falsa_seguridad ? `<span class="ix-baja">⚠️ Falsa seguridad: ${c.falsa_seguridad}</span>` : ""}</div>`;
}

/* ---------------------------------------------------------------- detalle del Índice */
VISTAS.indice = async () => {
  const x = await api("indice"), g = x.global;
  const esc_ = x.escala.niveles;
  vista.innerHTML = `<h1>🧠 Tu Índice</h1>
    <div class="tarjeta ix-final">
      <div class="ix-num grande">${g.n ? ixNum(g.indice) : "?"} <small class="suave">${g.n ? "±" + Math.round(g.mas_menos) : ""}</small></div>
      <div>${g.n ? `${esc(g.nivel)} · ${ixMeta(g)}` : "Aún sin medir"}</div>
      <div class="stats" style="margin-bottom:0">
        <div class="stat"><b>${x.record != null ? ixNum(x.record) : "—"}</b><span>récord personal</span></div>
        <div class="stat"><b>${x.hace30 != null ? ixDelta(g.indice - x.hace30) : "—"}</b><span>vs. tú hace 30 días</span></div>
        <div class="stat"><b>${x.retos}</b><span>retos hechos</span></div>
        <div class="stat"><b>${g.n}</b><span>respuestas medidas</span></div></div>
      ${x.calibracion && (x.calibracion.se.n + x.calibracion.creo.n) ? `<div style="margin-top:.6rem"><div class="suave peq">¿Sabes lo que sabes? (lo que dijiste antes de ver las opciones)</div>${ixCalib(x.calibracion)}
        <div class="suave peq">«La sé» debería acertar casi siempre. La falsa seguridad es lo más caro en un examen o en el trabajo.</div></div>` : ""}
      ${x.historial.length > 1 ? `<div style="margin-top:.8rem">${ixLinea(x.historial, 600, 120)}
        <div class="fila entre suave peq"><span>${IX_FECHA(x.historial[0].ts)}</span><span>${IX_FECHA(x.historial[x.historial.length - 1].ts)}</span></div></div>` : ""}
      <button class="btn pri ix-btn" onclick="ir('reto')" ${x.banco.total < x.banco.minimo ? "disabled" : ""}>${x.abierto ? "▶ Seguir el reto" : "⚡ Hacer un reto"}</button></div>
    ${x.areas.length ? `<h2>Por área</h2><div class="tarjeta"><table class="ix-tabla"><thead><tr><th>Área</th><th>Índice</th><th>Nivel</th><th>Respuestas</th></tr></thead><tbody>
      ${x.areas.map((a) => `<tr><td>${esc(a.nombre)}</td><td><b>${ixNum(a.indice)}</b> <span class="suave peq">±${Math.round(a.mas_menos)}</span></td>
        <td>${a.provisional ? `<span class="suave">provisional</span>` : esc(a.nivel)}</td><td>${a.aciertos}/${a.n}</td></tr>`).join("")}</tbody></table>
      <p class="suave peq">Un área con menos de 10 respuestas es provisional: su número todavía se mueve mucho.</p></div>` : ""}
    <h2>Cómo se calcula</h2>
    <div class="tarjeta peq">
      <p>Es una escala tipo CI (pasos de 15) pero <b>no es un CI</b> ni te compara con otras personas: te compara con los
        <b>niveles del currículo</b>. Cada pregunta vale según el nivel de su módulo:
        ${Object.entries(esc_).map(([n, d]) => `${esc(n)} <b>${d}</b>`).join(" · ")}.</p>
      <p>Un Índice de 115 significa que respondes las preguntas de nivel Avanzado a mitad de camino entre adivinar y
        acertar siempre. Acertar una difícil sube mucho; fallar una fácil baja mucho (como el Elo del ajedrez, con un
        modelo que descuenta lo que se acierta adivinando).</p>
      <p><b>Sin suerte.</b> Las preguntas escritas por IA suelen delatar la correcta por ser la más larga (en un banco
        real, elegir siempre la más larga acertaba el 66 % sin saber nada). Cada reto se arma para que la correcta sea
        la más larga solo ~1 de cada 4 veces y la más corta ~1 de cada 4, como al azar; las de pista fuerte quedan fuera
        (${x.banco.con_pista} en tu banco). Y antes de ver las opciones dices si la sabes: con «no sé» no se adivina,
        se muestra la respuesta y cuenta lo mismo que adivinar en promedio.</p>
      <p><b>No baja por no entrar</b>: lo único que crece si pasas días sin retos es el ± (la incertidumbre).
        Las preguntas salen de <b>tus</b> lecciones, se barajan, no se repiten en ${30} días y tienen ${x.escala.segundos} s cada una.</p>
      <p class="suave">Tu banco: ${x.banco.total} preguntas (${x.banco.frescas} sin usar en 30 días) ·
        por nivel: ${Object.entries(x.banco.por_nivel).map(([n, c]) => `${esc(NIVELES[n])} ${c}`).join(" · ")}.
        Cuantas más lecciones de un nivel prepares, mejor se mide ese nivel.</p></div>`;
};
