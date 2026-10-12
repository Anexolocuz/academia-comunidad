/* Cuaderno a mano para S Pen (tablet y celular Samsung) y mouse.
   - Coordenadas lógicas: 1000 de ancho, así la misma nota se ve igual en el celular, la tablet y el PC.
   - El lápiz escribe con presión; con "solo lápiz" el dedo desplaza la página (rechazo de palma).
   - Botón lateral del S Pen apretado = borrador.
   - Se guarda en el PC: PNG (para la IA y miniaturas) + trazos JSON (para seguir editando). */
"use strict";
const ANCHO = 1000, PAGINA = 1400;
const COLORES = ["#1b1b1f", "#1f4fd8", "#d62828", "#1f9d55", "#8e44ad"];
const RESALTADOR = ["#ffe066", "#8ce99a", "#74c0fc", "#ffa8a8"];

VISTAS.cuaderno = async ([id, accion], q) => {
  if (!id) return listaCuaderno();
  if (id === "nueva") return editor(null, q.tema || null, q.ejercicio || null, q.tarea ? +q.tarea : null);
  if (accion === "editar") return editor(+id);
  return verNota(+id);
};

async function listaCuaderno() {
  const d = await api("cuaderno");
  vista.innerHTML = `<div class="fila entre"><h1 style="margin:0">✍️ Cuaderno</h1><button class="btn pri" onclick="ir('cuaderno/nueva')">＋ Nueva nota</button></div>
    <p class="suave">Escribe con el S Pen en la tablet o el celular. Todo se guarda en tu PC. «Evaluar» hace que la IA lea tu letra, la transcriba, corrija errores y proponga tarjetas.
    Escribir a mano y explicar con tus palabras (Feynman) fija mucho mejor que copiar.</p>
    <div class="miniaturas">${d.notas.map((n) => `<div class="tarjeta miniatura" onclick="ir('cuaderno/${n.id}')">
      <img loading="lazy" src="api/cuaderno/img/${n.id}.png?v=${Math.round(n.actualizado)}" alt="">
      <div style="margin-top:.4rem"><b>${esc(n.titulo)}</b></div>
      <div class="suave peq">${new Date(n.actualizado * 1000).toLocaleDateString(LOC)} ${n.evaluada ? `· <span class="etq ${n.puntaje >= 80 ? "bien" : n.puntaje >= 55 ? "medio" : "mal"}">${Math.round(n.puntaje)}/100</span>` : "· sin evaluar"}</div></div>`).join("")
      || `<p class="vacio">Aún no tienes apuntes. Toca «Nueva nota».</p>`}</div>`;
}

async function verNota(id) {
  const n = await api("cuaderno/nota?id=" + id);
  if (n.error) throw new Error(n.error);
  const ev = n.evaluacion;
  E.areaActual = n.area; E.temaActual = n.tema;
  vista.innerHTML = `<button class="btn fantasma peq" onclick="ir('cuaderno')">← Cuaderno</button>
    <h1>${esc(n.titulo)}</h1>
    <div class="fila" style="margin-bottom:.8rem"><button class="btn pri" onclick="ir('cuaderno/${id}/editar')">✏️ Seguir escribiendo</button>
      <button class="btn" id="evaluar">🧠 ${ev ? "Evaluar de nuevo" : "Evaluar con IA"}</button>
      ${n.tema ? `<button class="btn" onclick="ir('tema/${n.tema}')">📖 Ver lección</button><button class="btn" id="entregarNota">📤 Entregar como práctica</button>` : ""}
      <button class="btn fantasma" id="borrar">🗑</button></div>
    <div id="evEstado"></div>
    <div class="rejilla" style="grid-template-columns:repeat(auto-fit,minmax(min(100%,360px),1fr))">
      <div class="tarjeta"><img src="api/cuaderno/img/${id}.png?v=${Math.round(n.actualizado)}" style="width:100%;background:#fff;border-radius:8px" alt="Apunte"></div>
      <div id="evCuerpo">${ev ? "" : `<div class="tarjeta suave">Pulsa «Evaluar con IA»: transcribe tu letra (fórmulas incluidas), señala errores y propone tarjetas de repaso.</div>`}</div></div>`;
  if (ev) pintarEvaluacion(id, ev);
  $("#evaluar").onclick = () => evaluarNota(id);
  if ($("#entregarNota")) $("#entregarNota").onclick = async () => {
    const r = await api("entregas?tema=" + encodeURIComponent(n.tema));
    modal(`<h2>📤 Entregar como práctica</h2><label>¿Qué ejercicio es?</label><select id="mEj">${r.ejercicios.map((e) => `<option value="${e.n}">${esc(e.titulo)} — ${esc(e.enunciado.slice(0, 60))}…</option>`).join("")}<option value="otro">Otro…</option></select>
      <input type="text" id="mOtro" placeholder="¿Qué es?" hidden style="margin-top:.4rem">
      <div class="fila" style="margin-top:.8rem"><button class="btn pri" id="mEnviar">Entregar</button><button class="btn" onclick="cerrarModal()">Cancelar</button></div>`, (c) => {
      $("#mEj", c).onchange = () => ($("#mOtro").hidden = $("#mEj").value !== "otro");
      $("#mEnviar", c).onclick = async () => {
        const ej = $("#mEj").value === "otro" ? ($("#mOtro").value.trim() || "otro") : $("#mEj").value;
        const j = await api("entrega", { tema: n.tema, ejercicio: ej, cuaderno: id });
        cerrarModal(); aviso(`📤 Entregado (versión ${j.version})`); E.irPractica = true; ir("tema/" + n.tema);
      };
    });
  };
  $("#borrar").onclick = async () => { if (confirm("¿Borrar esta nota?")) { await api("cuaderno/borrar", { id }); ir("cuaderno"); } };
}

function pintarEvaluacion(id, ev) {
  const cls = ev.puntaje >= 80 ? "bien" : ev.puntaje >= 55 ? "medio" : "mal";
  $("#evCuerpo").innerHTML = `<div class="tarjeta"><div class="fila entre"><b>Evaluación</b><b style="font-size:1.4rem;color:var(--${cls})">${ev.puntaje}/100</b></div>
      ${ev.correcto.length ? `<p>✅ <b>Bien:</b></p><ul>${ev.correcto.map((x) => `<li>${esc(x)}</li>`).join("")}</ul>` : ""}
      ${ev.errores.length ? `<p>❌ <b>Errores:</b></p><ul>${ev.errores.map((x) => `<li class="md-inline">${esc(x)}</li>`).join("")}</ul>` : `<p>Sin errores detectados.</p>`}
      ${ev.mejoras.length ? `<p>➕ <b>Para mejorar tus apuntes:</b></p><ul>${ev.mejoras.map((x) => `<li>${esc(x)}</li>`).join("")}</ul>` : ""}
      ${ev.tarjetas.length ? `<button class="btn pri" id="evTarj">➕ Agregar ${ev.tarjetas.length} tarjetas a mi repaso</button>` : ""}</div>
    <details class="tarjeta" open><summary><b>📝 Transcripción</b></summary><div class="leccion" id="evTrans"></div></details>`;
  pintarMd($("#evTrans"), ev.transcripcion);
  renderMath($("#evCuerpo"));
  if ($("#evTarj")) $("#evTarj").onclick = async () => { const r = await api("cuaderno/tarjetas", { id }); aviso(`${r.agregadas} tarjetas agregadas`); $("#evTarj").disabled = true; };
}

async function evaluarNota(id) {
  const e = $("#evEstado");
  e.innerHTML = `<div class="tarjeta"><span class="cargando"></span> Enviando a la IA…</div>`;
  try {
    const j = await api("cuaderno/evaluar", { id });
    const r = await esperarTrabajo(j.trabajo, (t) => { if ($("#evEstado")) $("#evEstado").innerHTML = `<div class="tarjeta"><span class="cargando"></span> ${esc(textoEstado(t))} (≈30-90 s)</div>`; });
    e.innerHTML = ""; pintarEvaluacion(id, r);
  } catch (x) { e.innerHTML = `<div class="tarjeta">❌ ${esc(x.message)}</div>`; }
}

/* ------------------------------------------------------------ editor */
async function editor(id, temaInicial, ejercicio, tarea) {
  const yo = E.yo || (E.yo = await api("yo"));
  if (!E.mapa) { const m = await api("mapa"); E.mapa = m.areas; m.areas.forEach((a) => (AREA_ES[a.id] = a)); }
  let nota = id ? await api("cuaderno/nota?id=" + id) : null;
  const S = {
    trazos: nota?.trazos?.trazos || [], alto: nota?.trazos?.alto || PAGINA, fondo: nota?.trazos?.fondo || "lineas",
    herramienta: "pluma", color: COLORES[0], grosor: 3, rehacer: [], cambios: false,
    soloLapiz: yo.perfil.solo_lapiz !== false, actual: null, id, tema: nota?.tema || temaInicial,
  };
  const temas = E.mapa.flatMap((a) => a.modulos.flatMap((m) => m.temas.map((t) => ({ id: t.id, txt: `${a.icono} ${a.nombre} › ${t.t}` }))));
  const temaTxt = (tid) => (temas.find((t) => t.id === tid) || {}).txt || "";
  vista.innerHTML = `<div class="fila entre" style="margin-bottom:.5rem"><button class="btn fantasma peq" id="volver">← Cuaderno</button>
      <input type="text" id="titulo" placeholder="Título" value="${esc(nota?.titulo && nota.titulo !== "Apuntes" ? nota.titulo : ejercicio ? (/^\d+$/.test(ejercicio) ? "Práctica · Ejercicio " + ejercicio : "Práctica · " + ejercicio) : "")}" style="flex:1;min-width:140px;max-width:420px">
      <button class="btn ${ejercicio ? "" : "pri"}" id="guardar">💾 Guardar</button>
      ${ejercicio ? `<button class="btn pri" id="guardarEntregar">📤 Guardar y entregar</button>` : `<button class="btn" id="guardarEval">🧠 Guardar y evaluar</button>`}</div>
    ${ejercicio ? `<div class="tarjeta peq" style="border-color:var(--acento);padding:.5rem .8rem">Estás resolviendo la práctica: <b>${/^\d+$/.test(ejercicio) ? "Ejercicio " + esc(ejercicio) : esc(ejercicio)}</b>. Al terminar pulsa «📤 Guardar y entregar» y la IA lo corrige.</div>` : ""}
    <div class="fila" style="margin-bottom:.5rem"><input type="text" id="temaBus" list="listaTemas" placeholder="Tema del currículo (opcional): escribe para buscar…" value="${esc(temaTxt(S.tema))}" style="flex:1">
      <datalist id="listaTemas">${temas.map((t) => `<option value="${esc(t.txt)}">`).join("")}</datalist></div>
    <div class="herramientas" id="barraH">
      <button data-h="pluma" class="activo" title="Pluma">🖊️</button><button data-h="resaltador" title="Resaltador">🖍️</button><button data-h="borrador" title="Borrador (o botón del S Pen)">🧽</button>
      <span class="sep"></span>${COLORES.map((c, i) => `<button class="color ${i ? "" : "activo"}" data-c="${c}" style="background:${c}" title="Color"></button>`).join("")}
      <span class="sep"></span><button data-g="2" title="Fino">·</button><button data-g="3" class="activo" title="Medio">•</button><button data-g="6" title="Grueso">●</button>
      <span class="sep"></span><button id="deshacer" title="Deshacer">↶</button><button id="rehacer" title="Rehacer">↷</button>
      <button id="fondoB" title="Fondo: líneas / cuadrícula / blanco">▤</button><button id="masPag" title="Agregar página">＋📄</button>
      <button id="lapizB" title="Solo lápiz: el dedo desplaza">${S.soloLapiz ? "✋" : "👆"}</button></div>
    <div class="lienzo-envoltura" id="env"><canvas id="lienzo"></canvas></div>
    <p class="suave peq">${S.soloLapiz ? "✋ Solo lápiz activo: escribe con el S Pen, desplázate con el dedo." : "👆 Dedo y lápiz dibujan."} Botón lateral del S Pen = borrador. Se guarda solo cada 30 s.</p>`;
  const cv = $("#lienzo"), ctx = cv.getContext("2d");
  const base = document.createElement("canvas"), bctx = base.getContext("2d");
  let escala = 1, dpr = 1;

  const medir = () => {
    dpr = Math.min(window.devicePixelRatio || 1, 2.5);
    const w = $("#env").clientWidth; escala = w / ANCHO;
    for (const c of [cv, base]) { c.width = Math.round(w * dpr); c.height = Math.round(S.alto * escala * dpr); }
    cv.style.height = S.alto * escala + "px";
    redibujarBase(); componer();
  };
  const fondo = (c, conGuia) => {
    c.fillStyle = "#ffffff"; c.fillRect(0, 0, ANCHO, S.alto);
    if (!conGuia || S.fondo === "blanco") return;
    c.strokeStyle = "#e3e8f0"; c.lineWidth = 1;
    const paso = S.fondo === "cuadricula" ? 32 : 40;
    c.beginPath();
    for (let y = paso * 2; y < S.alto; y += paso) { c.moveTo(0, y); c.lineTo(ANCHO, y); }
    if (S.fondo === "cuadricula") for (let x = paso; x < ANCHO; x += paso) { c.moveTo(x, 0); c.lineTo(x, S.alto); }
    c.stroke();
    c.strokeStyle = "#cfd6e2"; for (let y = PAGINA; y < S.alto; y += PAGINA) { c.setLineDash([8, 8]); c.beginPath(); c.moveTo(0, y); c.lineTo(ANCHO, y); c.stroke(); c.setLineDash([]); }
  };
  const trazar = (c, t) => {
    const p = t.p; if (!p.length) return;
    c.save(); c.lineCap = "round"; c.lineJoin = "round"; c.strokeStyle = t.c; c.fillStyle = t.c;
    if (t.h === "resaltador") { c.globalAlpha = 0.35; c.lineWidth = t.w * 6; c.beginPath(); c.moveTo(p[0][0], p[0][1]);
      for (const q of p) c.lineTo(q[0], q[1]); c.stroke(); c.restore(); return; }
    if (p.length === 1) { c.beginPath(); c.arc(p[0][0], p[0][1], t.w * (0.4 + p[0][2] * 0.6), 0, 7); c.fill(); c.restore(); return; }
    for (let i = 1; i < p.length; i++) {  // grosor variable con la presión del S Pen
      const a = p[i - 1], b = p[i];
      c.lineWidth = t.w * (0.35 + ((a[2] + b[2]) / 2) * 1.1);
      c.beginPath();
      if (i > 1) { const z = p[i - 2]; c.moveTo((z[0] + a[0]) / 2, (z[1] + a[1]) / 2); c.quadraticCurveTo(a[0], a[1], (a[0] + b[0]) / 2, (a[1] + b[1]) / 2); }
      else { c.moveTo(a[0], a[1]); c.lineTo((a[0] + b[0]) / 2, (a[1] + b[1]) / 2); }
      c.stroke();
    }
    c.restore();
  };
  const redibujarBase = () => {
    bctx.setTransform(escala * dpr, 0, 0, escala * dpr, 0, 0);
    fondo(bctx, true);
    S.trazos.filter((t) => t.h === "resaltador").forEach((t) => trazar(bctx, t));  // resaltador debajo de la tinta
    S.trazos.filter((t) => t.h !== "resaltador").forEach((t) => trazar(bctx, t));
  };
  let pendiente = false;
  const componer = () => {
    pendiente = false;
    ctx.setTransform(1, 0, 0, 1, 0, 0); ctx.drawImage(base, 0, 0);
    if (S.actual) { ctx.setTransform(escala * dpr, 0, 0, escala * dpr, 0, 0); trazar(ctx, S.actual); }
  };
  const pedirCuadro = () => { if (!pendiente) { pendiente = true; requestAnimationFrame(componer); } };
  const punto = (e) => { const r = cv.getBoundingClientRect(); return [(e.clientX - r.left) / escala, (e.clientY - r.top) / escala,
    e.pointerType === "pen" ? (e.pressure || 0.5) : 0.5]; };
  const borrarEn = ([x, y]) => {
    const r = 14; const antes = S.trazos.length;
    const quedan = S.trazos.filter((t) => !t.p.some((q) => Math.hypot(q[0] - x, q[1] - y) < r + t.w));
    if (quedan.length !== antes) { S.rehacer = []; S.historial.push({ tipo: "borrar", trazos: S.trazos }); S.trazos = quedan; S.cambios = true; redibujarBase(); pedirCuadro(); }
  };
  S.historial = [];
  let modo = null, dedo = null;
  cv.addEventListener("pointerdown", (e) => {
    if (e.pointerType === "touch" && S.soloLapiz) { dedo = { y: e.clientY, x: e.clientX }; cv.setPointerCapture(e.pointerId); return; }
    e.preventDefault(); cv.setPointerCapture(e.pointerId);
    const borrar = S.herramienta === "borrador" || (e.pointerType === "pen" && (e.buttons & 2 || e.buttons & 32)) || e.button === 5;
    if (borrar) { modo = "borrar"; borrarEn(punto(e)); return; }
    modo = "dibujar";
    S.actual = { h: S.herramienta, c: S.herramienta === "resaltador" ? (RESALTADOR.includes(S.color) ? S.color : RESALTADOR[0]) : S.color, w: S.grosor, p: [punto(e)] };
    pedirCuadro();
  });
  cv.addEventListener("pointermove", (e) => {
    if (dedo) { window.scrollBy(0, dedo.y - e.clientY); dedo.y = e.clientY; return; }
    if (!modo) return;
    const evs = e.getCoalescedEvents ? e.getCoalescedEvents() : [e];
    if (modo === "borrar") { borrarEn(punto(e)); return; }
    for (const x of evs) { const p = punto(x); const u = S.actual.p[S.actual.p.length - 1]; if (Math.hypot(p[0] - u[0], p[1] - u[1]) > 0.6) S.actual.p.push(p); }
    pedirCuadro();
  });
  const soltar = () => {
    if (dedo) { dedo = null; return; }
    if (modo === "dibujar" && S.actual) {
      S.actual.p = S.actual.p.map((q) => [Math.round(q[0] * 10) / 10, Math.round(q[1] * 10) / 10, Math.round(q[2] * 100) / 100]);
      S.trazos.push(S.actual); S.historial.push({ tipo: "trazo" }); S.rehacer = []; S.cambios = true;
      trazar(bctx, S.actual); S.actual = null;
      if (S.trazos[S.trazos.length - 1].h === "resaltador") redibujarBase();
      const yMax = Math.max(...S.trazos[S.trazos.length - 1].p.map((q) => q[1]));
      if (yMax > S.alto - 150) { S.alto += PAGINA; medir(); }  // página nueva automática al llegar abajo
      pedirCuadro();
    }
    modo = null;
  };
  cv.addEventListener("pointerup", soltar); cv.addEventListener("pointercancel", soltar);
  cv.addEventListener("contextmenu", (e) => e.preventDefault());

  $$("[data-h]").forEach((b) => (b.onclick = () => { S.herramienta = b.dataset.h; $$("[data-h]").forEach((x) => x.classList.toggle("activo", x === b));
    if (S.herramienta === "resaltador" && !RESALTADOR.includes(S.color)) pintarColores(RESALTADOR); else if (S.herramienta === "pluma") pintarColores(COLORES); }));
  const pintarColores = (lista) => {
    const cs = $$(".color"); cs.forEach((b, i) => { const c = lista[i] || lista[0]; b.dataset.c = c; b.style.background = c; b.hidden = i >= lista.length; b.classList.toggle("activo", i === 0); });
    S.color = lista[0];
  };
  $$(".color").forEach((b) => (b.onclick = () => { S.color = b.dataset.c; $$(".color").forEach((x) => x.classList.toggle("activo", x === b)); }));
  $$("[data-g]").forEach((b) => (b.onclick = () => { S.grosor = +b.dataset.g; $$("[data-g]").forEach((x) => x.classList.toggle("activo", x === b)); }));
  $("#deshacer").onclick = () => {
    const h = S.historial.pop(); if (!h) return;
    if (h.tipo === "trazo") S.rehacer.push({ tipo: "trazo", t: S.trazos.pop() });
    else { S.rehacer.push({ tipo: "borrar", trazos: S.trazos }); S.trazos = h.trazos; }
    S.cambios = true; redibujarBase(); pedirCuadro();
  };
  $("#rehacer").onclick = () => {
    const h = S.rehacer.pop(); if (!h) return;
    if (h.tipo === "trazo") { S.trazos.push(h.t); S.historial.push({ tipo: "trazo" }); }
    else { S.historial.push({ tipo: "borrar", trazos: S.trazos }); S.trazos = h.trazos; }
    S.cambios = true; redibujarBase(); pedirCuadro();
  };
  $("#fondoB").onclick = () => { S.fondo = { lineas: "cuadricula", cuadricula: "blanco", blanco: "lineas" }[S.fondo]; aviso("Fondo: " + S.fondo); S.cambios = true; redibujarBase(); pedirCuadro(); };
  $("#masPag").onclick = () => { S.alto += PAGINA; S.cambios = true; medir(); };
  $("#lapizB").onclick = () => { S.soloLapiz = !S.soloLapiz; $("#lapizB").textContent = S.soloLapiz ? "✋" : "👆";
    aviso(S.soloLapiz ? "Solo lápiz: el dedo desplaza" : "El dedo también dibuja"); api("perfil", { solo_lapiz: S.soloLapiz }).catch(() => {}); E.yo.perfil.solo_lapiz = S.soloLapiz; };
  document.addEventListener("keydown", S.teclas = (e) => {
    if ((e.ctrlKey || e.metaKey) && e.key.toLowerCase() === "z") { e.preventDefault(); (e.shiftKey ? $("#rehacer") : $("#deshacer")).click(); }
  });

  const exportar = () => {
    // PNG recortado al contenido y sin líneas guía: más legible para la IA y para las miniaturas
    let x0 = ANCHO, y0 = S.alto, x1 = 0, y1 = 0;
    S.trazos.forEach((t) => t.p.forEach((q) => { x0 = Math.min(x0, q[0]); y0 = Math.min(y0, q[1]); x1 = Math.max(x1, q[0]); y1 = Math.max(y1, q[1]); }));
    if (!S.trazos.length) { x0 = 0; y0 = 0; x1 = ANCHO; y1 = 300; }
    x0 = Math.max(0, x0 - 30); y0 = Math.max(0, y0 - 30); x1 = Math.min(ANCHO, x1 + 30); y1 = Math.min(S.alto, y1 + 30);
    const k = Math.min(1.6, 1600 / Math.max(1, x1 - x0));
    const c = document.createElement("canvas"); c.width = Math.round((x1 - x0) * k); c.height = Math.round((y1 - y0) * k);
    const g = c.getContext("2d"); g.setTransform(k, 0, 0, k, -x0 * k, -y0 * k);
    fondo(g, false);
    S.trazos.filter((t) => t.h === "resaltador").forEach((t) => trazar(g, t));
    S.trazos.filter((t) => t.h !== "resaltador").forEach((t) => trazar(g, t));
    return c.toDataURL("image/png");
  };
  const temaElegido = () => { const v = $("#temaBus").value.trim(); return (temas.find((t) => t.txt === v) || {}).id || (v ? S.tema : null); };
  const guardar = async (silencioso) => {
    if (!S.trazos.length) { if (!silencioso) aviso("La nota está vacía"); return null; }
    const r = await api("cuaderno", { id: S.id, titulo: $("#titulo").value.trim() || "Apuntes", tema: temaElegido(), png: exportar(),
      trazos: { trazos: S.trazos, alto: S.alto, fondo: S.fondo }, ancho: ANCHO, alto: S.alto });
    S.id = r.id; S.cambios = false;
    if (!silencioso) aviso("💾 Guardado en tu PC");
    if (!location.hash.includes("/editar")) history.replaceState(null, "", `#/cuaderno/${S.id}/editar`);
    return r.id;
  };
  $("#guardar").onclick = () => guardar(false).catch((e) => aviso("Error: " + e.message));
  if ($("#guardarEntregar")) $("#guardarEntregar").onclick = async () => {
    const nid = await guardar(true); if (!nid) return aviso("La hoja está vacía");
    const tema = temaElegido(); if (!tema) return aviso("Elige el tema de la lección");
    const j = await api("entrega", { tema, ejercicio, cuaderno: nid, tarea: tarea || null });
    S.cambios = false; aviso(`📤 Entregado (versión ${j.version}); la IA lo está corrigiendo`);
    E.irPractica = true; ir(tarea ? "tarea/" + tarea : "tema/" + tema);
  };
  if ($("#guardarEval")) $("#guardarEval").onclick = async () => { const nid = await guardar(true); if (!nid) return aviso("La nota está vacía"); location.hash = "#/cuaderno/" + nid; setTimeout(() => evaluarNota(nid), 400); };
  $("#volver").onclick = async () => { if (S.cambios) await guardar(true).catch(() => {}); ir("cuaderno"); };
  const auto = setInterval(() => { if (S.cambios && !modo) guardar(true).catch(() => {}); }, 30000);
  const alSalirPag = (e) => { if (S.cambios) { e.preventDefault(); e.returnValue = ""; } };
  window.addEventListener("beforeunload", alSalirPag);
  const ro = new ResizeObserver(() => medir()); ro.observe($("#env"));
  E.salir = () => { clearInterval(auto); ro.disconnect(); window.removeEventListener("beforeunload", alSalirPag); document.removeEventListener("keydown", S.teclas);
    if (S.cambios) guardar(true).catch(() => {}); };
  medir();
}
