/* Academia — 🔬 «Qué sabe el sistema de ti» (fase F1). Se carga después de app.js y usa sus utilidades (api, esc, VISTAS, vista, aviso).
   Muestra TODO lo que el sistema deduce de ESTA persona: cada métrica con su origen (directa o indirecta), su fórmula, la ventana, cuánta muestra
   tiene, su confianza y la decisión que alimenta. La persona puede marcar «esto está mal», ignorar una métrica o apagar una familia entera:
   las de confianza baja nunca deciden nada. Cada perfil ve solo lo suyo. */
"use strict";

const MT = {
  conf: { "sin datos": ["", "⚪ sin datos"], baja: ["mal", "🔴 baja"], media: ["medio", "🟡 media"], alta: ["bien", "🟢 alta"] },
  orden: ["memoria", "lectura", "habito", "estilo", "contenido", "metas", "decision", "sistema"],
};
const mtValor = (m) => {
  if (m.error) return `<span class="ac-baja">error</span>`;
  if (m.valor == null) return `<span class="suave">—</span>`;
  const v = typeof m.valor === "number" && m.unidad === "%" ? Math.round(m.valor * 1000) / 10 : m.valor;
  return `<b style="font-size:1.25rem">${esc(typeof v === "number" ? v.toLocaleString(LOC) : v)}</b> <span class="suave peq">${esc(m.unidad === "%" ? "%" : m.unidad || "")}</span>`;
};

function mtTarjeta(m) {
  const c = MT.conf[m.confianza] || MT.conf["sin datos"], aj = m.ajuste;
  return `<li style="cursor:default;display:block;${aj || m.familia_apagada ? "opacity:.6" : ""}" data-id="${esc(m.id)}">
    <div class="fila entre" style="gap:.5rem;align-items:flex-start">
      <div style="flex:1;min-width:0"><b>${esc(m.nombre)}</b>
        <span class="etq" title="${m.origen === "D" ? "Directa: la diste tú de forma explícita" : "Indirecta: se deduce de cómo estudias"}">${m.origen === "D" ? "directa" : "indirecta"}</span>
        <span class="etq ${c[0]}">${c[1]}</span>${m.usable ? "" : ` <span class="etq" title="No decide nada: poca muestra, la ignoraste o está apagada">no decide</span>`}
        ${aj ? `<span class="etq medio">${aj.estado === "mal" ? "marcada como errónea" : "ignorada"}</span>` : ""}</div>
      <div style="text-align:right">${mtValor(m)}</div></div>
    <details style="margin-top:.3rem"><summary class="suave peq">Cómo se calcula · muestra n = ${m.n} · ventana: ${esc(m.ventana)}</summary>
      <p class="peq" style="margin:.4rem 0"><b>Fórmula:</b> ${esc(m.formula)}</p>
      <p class="peq" style="margin:.2rem 0"><b>Qué decide:</b> ${esc(m.decide)}</p>
      <p class="peq" style="margin:.2rem 0"><b>Confianza:</b> ${esc(m.confianza)} (mínimo para decidir: ${m.n_min} de muestra).</p>
      <div class="fila" style="gap:.4rem;flex-wrap:wrap;margin-top:.4rem">
        ${aj ? `<button class="btn peq" data-aj="ok">↩️ Quitar mi ajuste</button>` : `<button class="btn peq" data-aj="mal">⚠️ Esto está mal</button>
          <button class="btn peq" data-aj="ignorar">🙈 Ignorar</button>`}
        <button class="btn peq" data-tend="1">📈 Tendencia</button></div>
      <div class="mt-tend"></div></details></li>`;
}

VISTAS.metricas = async () => {
  const pintar = async () => {
    const d = await api("metricas");
    const off = new Set(d.metricas.filter((m) => m.familia_apagada).map((m) => m.familia));
    const por = {};
    d.metricas.forEach((m) => (por[m.familia] = por[m.familia] || []).push(m));
    const ev = d.eventos;
    vista.innerHTML = `<h1>🔬 Qué sabe el sistema de ti</h1>
      <p class="suave peq">Todo lo que la Academia deduce de cómo estudias, y de dónde sale. <b>Directa</b> = la diste tú (una nota, un puntaje). <b>Indirecta</b> = se
        deduce de tu comportamiento (tiempo, lectura, a dónde vas). Si algo está mal, márcalo: el sistema deja de usarlo para decidir. Solo tú ves esto.</p>
      <div class="stats">
        <div class="stat"><b>${d.resumen.total}</b><span>métricas</span></div>
        <div class="stat"><b>${d.resumen.usables}</b><span>con confianza suficiente para decidir</span></div>
        <div class="stat"><b>${d.resumen.baja}</b><span>con poca muestra (no deciden)</span></div>
        <div class="stat"><b>${d.resumen.sin_datos}</b><span>sin datos todavía</span></div>
        <div class="stat"><b>${ev.total}</b><span>eventos en tu línea de tiempo</span></div></div>
      ${MT.orden.filter((f) => por[f]).map((f) => `<h2>${esc(d.familias[f])} <span class="suave peq">(${por[f].length})</span>
        <button class="btn peq" data-fam="${f}" data-off="${off.has(f) ? 0 : 1}">${off.has(f) ? "▶️ Encender familia" : "⏸ Apagar familia"}</button></h2>
        <ul class="temas">${por[f].map(mtTarjeta).join("")}</ul>`).join("")}
      <p class="suave peq">Las métricas de confianza <b>baja</b> o <b>sin datos</b> se muestran para que veas qué se mide, pero no deciden nada hasta tener muestra suficiente.</p>`;
    vista.querySelectorAll("[data-aj]").forEach((b) => b.onclick = async () => {
      await api("metricas/ajustar", { id: b.closest("li").dataset.id, estado: b.dataset.aj }); aviso("Anotado"); pintar();
    });
    vista.querySelectorAll("[data-fam]").forEach((b) => b.onclick = async () => {
      await api("metricas/ajustar", { familia: b.dataset.fam, apagada: b.dataset.off === "1" }); pintar();
    });
    vista.querySelectorAll("[data-tend]").forEach((b) => b.onclick = async () => {
      const li = b.closest("li"), cont = li.querySelector(".mt-tend"), t = await api("metricas/tendencia?id=" + encodeURIComponent(li.dataset.id));
      cont.innerHTML = t.serie.length ? `<p class="peq suave">${t.serie.map((x) => `${esc(x.dia)}: <b>${esc(x.valor ?? "—")}</b>`).join(" · ")}</p>`
        : `<p class="peq suave">Aún no hay historial: se guarda una foto por día.</p>`;
    });
  };
  await pintar();
};
