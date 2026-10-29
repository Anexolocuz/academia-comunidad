/* Academia — 💻 Práctica con código: ejercicios de Python que se corrigen EJECUTANDO tu código (entorno aislado en el servidor).
   Se carga después de app.js. Solo aparece en las áreas de código y si el servidor tiene el aislamiento activo. */
"use strict";

async function montarCodigo(tid, caja) {
  let est;
  try { est = await api("codigo/estado?tema=" + encodeURIComponent(tid)); } catch (e) { return; }
  if (!est || est.error || !est.area_ok) return;
  if (!est.disponible) { caja.innerHTML = `<div class="tarjeta"><h2 style="margin-top:0">5️⃣ Práctica con código</h2><p class="suave peq">${esc(est.motivo)}</p></div>`; return; }
  const cuerpo = () => {
    caja.innerHTML = `<div class="tarjeta"><h2 style="margin-top:0">5️⃣ Practica con código (Python)</h2>
      <p class="suave peq">Un ejercicio sobre este tema que se corrige <b>ejecutando tu código</b> contra casos de prueba (algunos ocultos). Es evidencia objetiva de que sabes aplicarlo: no depende de que una IA opine. Corre en un entorno aislado, sin red ni acceso a tus archivos.</p>
      <div class="fila"><button class="btn pri" id="cdNuevo">➕ Nuevo ejercicio</button><span id="cdEstado" class="suave peq"></span></div>
      ${est.ejercicios.length ? `<ul class="temas" style="margin-top:.5rem">${est.ejercicios.map((x) => `<li data-ej="${x.id}" tabindex="0"><span style="flex:1;min-width:0"><b>${esc(x.titulo || "Ejercicio")}</b><br><span class="suave peq">${x.intentos} intento${x.intentos === 1 ? "" : "s"}</span></span>
        ${x.limpio ? `<span class="etq bien">✅ resuelto</span>` : x.aprobado ? `<span class="etq medio">resuelto con la solución a la vista</span>` : `<span class="etq">pendiente</span>`}</li>`).join("")}</ul>` : ""}
      <div id="cdEjercicio"></div></div>`;
    $$("[data-ej]", caja).forEach((li) => { li.onclick = () => abrir(li.dataset.ej); li.onkeydown = (e) => { if (e.key === "Enter") abrir(li.dataset.ej); }; });
    $("#cdNuevo").onclick = async () => {
      $("#cdNuevo").disabled = true;
      try {
        const j = await api("codigo/nuevo", { tema: tid });
        await esperarTrabajo(j.trabajo, (t) => ($("#cdEstado").innerHTML = `<span class="cargando"></span> ${esc(textoEstado(t))}`));
        est = await api("codigo/estado?tema=" + encodeURIComponent(tid)); cuerpo(); if (est.ejercicios[0]) abrir(est.ejercicios[0].id);
      } catch (e) { $("#cdEstado").textContent = "Error: " + e.message; $("#cdNuevo").disabled = false; }
    };
    if (est.trabajo && est.trabajo.id) {
      $("#cdNuevo").disabled = true;
      esperarTrabajo(est.trabajo.id, (t) => { const e = $("#cdEstado"); if (e) e.innerHTML = `<span class="cargando"></span> ${esc(textoEstado(t))}`; })
        .then(async () => { est = await api("codigo/estado?tema=" + encodeURIComponent(tid)); if ($("#cdEstado")) cuerpo(); }).catch(() => {});
    }
  };
  const abrir = async (id) => {
    const z = $("#cdEjercicio"); z.innerHTML = `<p><span class="cargando"></span> Abriendo…</p>`;
    const x = await api("codigo/ejercicio?id=" + id);
    if (x.error) { z.textContent = x.error; return; }
    let vioSolucion = x.vio_solucion, intentos = x.intentos;
    z.innerHTML = `<h3>${esc(x.titulo)}</h3><div class="leccion" id="cdEnun"></div>
      <p class="suave peq">Función a escribir: <code>${esc(x.funcion)}</code> · casos visibles: ${x.visibles.length} · ocultos: ${x.ocultos}</p>
      <textarea id="cdCodigo" spellcheck="false" autocapitalize="off" autocomplete="off" style="font-family:ui-monospace,monospace;min-height:220px;tab-size:4;white-space:pre"></textarea>
      <div class="fila" style="margin-top:.4rem"><button class="btn pri" id="cdEjecutar">▶ Ejecutar</button><button class="btn" id="cdPista">💡 Pista</button>
        <button class="btn fantasma" id="cdSol" ${vioSolucion || intentos >= 3 ? "" : "hidden"}>👁 Ver la solución</button><span id="cdRes0" class="suave peq"></span></div>
      <div id="cdPistaT" class="peq" hidden></div><div id="cdRes"></div><div id="cdSolT"></div>`;
    pintarMd($("#cdEnun"), x.enunciado);
    const ta = $("#cdCodigo");
    ta.value = x.ultimo_codigo || x.plantilla;
    ta.onkeydown = (e) => {
      if (e.key === "Tab") { e.preventDefault(); const i = ta.selectionStart; ta.setRangeText("    ", i, ta.selectionEnd, "end"); }
      if ((e.ctrlKey || e.metaKey) && e.key === "Enter") { e.preventDefault(); $("#cdEjecutar").click(); }
    };
    if (x.solucion) $("#cdSolT").innerHTML = `<h4>Solución de referencia</h4><pre><code>${esc(x.solucion)}</code></pre>`;
    $("#cdPista").onclick = () => { const p = $("#cdPistaT"); p.hidden = !p.hidden; p.textContent = "💡 " + (x.pista || "Sin pista."); };
    $("#cdSol").onclick = async () => {
      if (!(await preguntarSiNo("¿Ver la solución?", "Puedes aprender de ella, pero este ejercicio ya no contará como resuelto por ti.", "Ver la solución", "Aún no"))) return;
      const r = await api("codigo/solucion", { id }); vioSolucion = true;
      $("#cdSolT").innerHTML = `<h4>Solución de referencia</h4><pre><code>${esc(r.solucion)}</code></pre>`;
    };
    $("#cdEjecutar").onclick = async () => {
      const b = $("#cdEjecutar"); b.disabled = true; $("#cdRes0").innerHTML = `<span class="cargando"></span> Ejecutando…`;
      try {
        const r = await api("codigo/ejecutar", { id, codigo: ta.value });
        $("#cdRes0").textContent = "";
        if (r.error) { $("#cdRes").innerHTML = `<p class="etq mal">${esc(r.error)}</p>`; return; }
        intentos++; if (intentos >= 3) $("#cdSol").hidden = false;
        const val = (v) => `<code>${esc(typeof v === "string" ? JSON.stringify(v) : JSON.stringify(v))}</code>`;
        $("#cdRes").innerHTML = `<div class="tarjeta" style="border-color:var(--${r.aprobado ? "bien" : "medio"})">
          <b>${r.aprobado ? "🎉 ¡Pasaste todos los casos!" : `${r.aprobados} de ${r.total} casos`}</b>${r.aprobado && vioSolucion ? ` <span class="etq medio">con la solución a la vista: no cuenta como resuelto por ti</span>` : ""}
          ${r.error_carga ? `<p class="etq mal">${esc(r.error_carga)}</p>` : ""}
          <ul class="peq">${r.casos.map((c, k) => `<li>${c.ok ? "✅" : "❌"} ${c.oculto ? `Caso oculto ${k + 1}${c.error ? ": " + esc(c.error) : ""}`
            : `${esc(x.funcion)}(${(c.args || []).map((a) => val(a)).join(", ")}) → esperado ${val(c.esperado)}${c.ok ? "" : c.error ? `, error: ${esc(c.error)}` : `, obtuviste ${val(c.obtenido)}`}`}</li>`).join("")}</ul>
          ${r.salida ? `<details class="peq"><summary class="suave">Lo que imprimió tu código</summary><pre>${esc(r.salida)}</pre></details>` : ""}</div>`;
        if (r.aprobado) { est = await api("codigo/estado?tema=" + encodeURIComponent(tid)); }
      } catch (e) { $("#cdRes0").textContent = "Error: " + e.message; } finally { b.disabled = false; }
    };
  };
  cuerpo();
}
