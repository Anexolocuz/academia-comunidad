/* Academia — 🧬 Dominio medido: estado 0-5 del tema y prueba diferida (a los 3, 14 y 45 días). Modo sombra: solo mide y muestra.
   Se carga después de app.js. */
"use strict";

const DOM_ETAPAS = { 1: "3 días", 2: "14 días", 3: "45 días" };

async function montarDominio(tid, caja) {
  let d;
  try { d = await api("dominio/tema?tema=" + encodeURIComponent(tid)); } catch (e) { return; }
  if (!d || d.error) return;
  const fecha = (t) => new Date(t * 1000).toLocaleDateString(LOC, { day: "numeric", month: "short", year: "numeric" });
  const pintar = () => {
    const e = d.estado, sig = d.siguiente;
    caja.innerHTML = `<div class="tarjeta"><h2 style="margin-top:0">6️⃣ ¿Cuánto dominas de verdad?</h2>
      <div class="fila"><span class="insignia n${Math.min(e.nivel, 3)}"${tip("Estado de dominio " + e.nivel + " de 5")}>${e.nivel} · ${esc(e.etiqueta)}</span>
        <span class="peq suave">${d.estados.map((x, k) => `<span style="opacity:${k <= e.nivel ? 1 : .3}">●</span>`).join("")}</span></div>
      ${e.evidencia.length ? `<p class="peq" style="margin:.4rem 0 0"><b>Evidencia:</b> ${e.evidencia.map(esc).join(" · ")}</p>` : `<p class="peq suave" style="margin:.4rem 0 0">Aún sin evidencia: empieza leyendo la lección.</p>`}
      ${e.falta.length ? `<p class="peq" style="margin:.2rem 0 0"><b>Para subir:</b> ${esc(e.falta[0])}.</p>` : `<p class="peq" style="margin:.2rem 0 0">🏆 Evidencia completa.</p>`}
      <p class="suave peq" style="margin:.3rem 0 0">Leer o abrir una lección es <i>exposición</i>, no dominio. Este estado solo mide: no cambia tu nota, tus repasos ni lo que te toca hoy.</p>
      ${d.calendario.length ? `<h3>🧬 Pruebas diferidas</h3><p class="suave peq">Preguntas de aplicación en un caso nuevo, distintas del quiz, a los 3, 14 y 45 días de dominar el tema: miden lo que <b>queda</b>.</p>
        <ul class="temas">${d.calendario.map((c) => `<li style="cursor:default"><span style="flex:1"><b>A los ${DOM_ETAPAS[c.etapa]}</b> <span class="suave peq">· desde el ${fecha(c.desde)}</span></span>
          ${c.hecha ? `<span class="etq ${c.aprobada ? "bien" : "mal"}">${c.aprobada ? "✅ aprobada" : "❌ no aprobada"} · ${Math.round(c.puntaje * 100)} %</span>` : c.disponible ? `<span class="etq medio">disponible</span>` : `<span class="etq">aún no toca</span>`}</li>`).join("")}</ul>
        <div class="fila">${d.lista ? `<button class="btn pri" id="dfHacer">▶ Hacer la prueba de ${DOM_ETAPAS[d.lista.etapa]}</button>`
          : sig && sig.disponible ? `<button class="btn pri" id="dfPrep">🧬 Preparar la prueba de ${DOM_ETAPAS[sig.etapa]}</button>` : ""}<span id="dfEstado" class="suave peq"></span></div>`
        : `<p class="suave peq" style="margin-top:.5rem">Cuando el tema cuente como dominado, aquí se programan sus pruebas diferidas.</p>`}
      <div id="dfPrueba"></div></div>`;
    if ($("#dfHacer")) $("#dfHacer").onclick = () => hacer(d.lista.id);
    if ($("#dfPrep")) $("#dfPrep").onclick = async () => {
      $("#dfPrep").disabled = true;
      try {
        const j = await api("diferida/preparar", { tema: tid });
        if (j.lista) { d = await api("dominio/tema?tema=" + encodeURIComponent(tid)); pintar(); return hacer(j.lista); }
        await esperarTrabajo(j.trabajo, (t) => ($("#dfEstado").innerHTML = `<span class="cargando"></span> ${esc(textoEstado(t))}`));
        d = await api("dominio/tema?tema=" + encodeURIComponent(tid)); pintar(); if (d.lista) hacer(d.lista.id);
      } catch (x) { const s = $("#dfEstado"); if (s) s.textContent = "Error: " + x.message; if ($("#dfPrep")) $("#dfPrep").disabled = false; }
    };
    if (d.trabajo && d.trabajo.id && $("#dfEstado")) {
      esperarTrabajo(d.trabajo.id, (t) => { const s = $("#dfEstado"); if (s) s.innerHTML = `<span class="cargando"></span> ${esc(textoEstado(t))}`; })
        .then(async () => { d = await api("dominio/tema?tema=" + encodeURIComponent(tid)); if ($("#dfEstado")) pintar(); }).catch(() => {});
    }
  };
  const hacer = async (id) => {
    const p = await api("diferida/prueba?id=" + id), z = $("#dfPrueba");
    if (p.error) { z.textContent = p.error; return; }
    const resp = p.preguntas.map(() => ({ j: null, conf: null }));
    z.innerHTML = `<h3>Prueba de ${p.dias} días · ${p.preguntas.length} preguntas</h3>
      <p class="suave peq">Se responde <b>una sola vez</b> y sin mirar la lección: es una medida, no un ensayo. Marca antes qué tan seguro estás (opcional).</p>
      ${p.preguntas.map((q, i) => `<div class="pregunta" data-i="${i}"><div class="pq"></div>
        <div class="conf peq">${[["seguro", "💪 Seguro"], ["dudo", "🤔 Dudo"], ["adivino", "🎲 Adivino"]].map(([k, t]) => `<button class="chip" data-conf="${k}" aria-pressed="false">${t}</button>`).join("")}</div>
        ${q.opciones.map((o, j) => `<button class="opcion" data-j="${j}"></button>`).join("")}</div>`).join("")}
      <div class="fila"><button class="btn pri" id="dfEnviar" disabled>Entregar la prueba</button><span id="dfFalta" class="suave peq"></span></div><div id="dfRes"></div>`;
    p.preguntas.forEach((q, i) => {
      const c = $(`[data-i="${i}"]`, z);
      pintarMd($(".pq", c), `**${i + 1}.** ${q.pregunta}`);
      $$(".opcion", c).forEach((b, j) => { pintarMd(b, q.opciones[j]); b.onclick = () => { resp[i].j = j; $$(".opcion", c).forEach((x, k) => x.classList.toggle("sel", k === j)); revisar(); }; });
      $$("[data-conf]", c).forEach((b) => (b.onclick = () => { resp[i].conf = b.dataset.conf; $$("[data-conf]", c).forEach((x) => { x.classList.toggle("activo", x === b); x.setAttribute("aria-pressed", x === b); }); }));
    });
    const revisar = () => { const f = resp.filter((r) => r.j == null).length; $("#dfEnviar").disabled = f > 0; $("#dfFalta").textContent = f ? `Faltan ${f} por responder` : ""; };
    revisar();
    $("#dfEnviar").onclick = async () => {
      $("#dfEnviar").disabled = true;
      try {
        const r = await api("diferida/responder", { id, respuestas: resp });
        if (r.error) { $("#dfRes").innerHTML = `<p class="etq mal">${esc(r.error)}</p>`; return; }
        $$(".opcion", z).forEach((b) => (b.disabled = true));
        $("#dfRes").innerHTML = `<div class="tarjeta" style="border-color:var(--${r.aprobada ? "bien" : "medio"})"><b>${r.aprobada ? "✅ Aprobada" : "❌ No aprobada"} · ${r.aciertos} de ${r.total} (${Math.round(r.puntaje * 100)} %)</b>
          <p class="suave peq">${r.aprobada ? "Lo que sabías sigue en pie." : "Se te escapó parte: repasa lo que fallaste y la siguiente cita lo volverá a medir."}</p>
          ${r.respuestas.map((x, i) => `<div class="peq" style="margin:.4rem 0">${x.ok ? "✅" : "❌"} <b>${i + 1}.</b> ${x.ok ? "" : `Elegiste «${esc(r.preguntas[i].opciones[x.j] ?? "—")}»; correcta: «${esc(r.preguntas[i].opciones[x.correcta])}». `}<span class="suave">${esc(x.explicacion)}</span></div>`).join("")}</div>`;
        const resultado = $("#dfRes").innerHTML;
        d = await api("dominio/tema?tema=" + encodeURIComponent(tid)); pintar();     // repinta el estado y el calendario; el resultado se conserva debajo
        $("#dfPrueba").innerHTML = `<div id="dfRes">${resultado}</div>`;
      } catch (x) { $("#dfRes").innerHTML = `<p class="etq mal">${esc(x.message)}</p>`; $("#dfEnviar").disabled = false; }
    };
  };
  pintar();
}
