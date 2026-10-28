/* themachine: System-tab wheel + dedicated tab. Read-only; all controls in Orbit still manage the Pi.
   Fed by fleet.js, which dispatches `orbit-fleet` with /api/fleet data every 3 s (empty machines on failure). */
(() => {
  const q = id => document.getElementById(id);
  const set = (id, v) => { const el = q(id); if (el) el.textContent = v; };
  const html = (id, v) => { const el = q(id); if (el) el.innerHTML = v; };
  const ring = (id, f) => { const el = q(id); if (el) setRing(el, Number.isFinite(f) ? f : 0); };
  const num = v => (Number.isFinite(Number(v)) ? Number(v) : null);
  const pct = (a, b) => (b ? Math.max(0, Math.min(1, a / b)) : 0);
  const tempColor = t => (t > 80 ? "var(--bad)" : t > 70 ? "var(--warn)" : "");
  const STATES = { passed: "SMART PASSED", attention: "REVIEW", failed: "FAILED", unavailable: "UNAVAILABLE", missing: "MISSING", stale: "STALE" };

  function offline(msg) {
    set("tm-state", msg); q("tmHero")?.classList.add("offline");
    ["tm-cpuVal", "tm-tempVal", "tm-clockVal", "tm-memVal", "tm-upVal"].forEach(id => set(id, "--"));
    ring("tm-cpuArc", 0);
    set("machine-state", msg.toUpperCase() + " · reconnecting");
    const c = q("machine-content"); if (c) c.hidden = true;
  }

  document.addEventListener("orbit-fleet", ev => {
    const m = ((ev.detail && ev.detail.machines) || []).find(x => x.id === "themachine");
    if (!m || m.online !== true || !m.metrics) return offline(m ? (m.status || "Offline") : "No data");
    const d = m.metrics, mem = d.mem || {};
    const age = Date.now() / 1000 - (d.ts || 0);
    if (age > 30) return offline("Stale");           // never show old numbers as live
    const cpu = num(d.cpu) ?? 0, temp = num(d.temp);
    const used = Math.max(0, (mem.total || 0) - (mem.avail || 0)), memF = pct(used, mem.total);

    // System-tab wheel
    q("tmHero")?.classList.remove("offline");
    set("tm-state", age > 10 ? "DELAYED" : "LIVE");
    set("tm-cpuVal", Math.round(cpu)); ring("tm-cpuArc", cpu / 100);
    const tv = q("tm-tempVal"); if (tv) { tv.innerHTML = temp == null ? "--" : `${temp.toFixed(1)}<small>°C</small>`; tv.style.color = temp == null ? "" : tempColor(temp); }
    set("tm-clockVal", d.clock ? d.clock + " MHz" : "--");
    set("tm-memVal", Math.round(memF * 100) + "%");
    set("tm-upVal", fmtUp(d.uptime || 0));

    // Dedicated tab
    const c = q("machine-content"); if (c) c.hidden = false;
    set("machine-state", `ONLINE · ${new Date(d.ts * 1000).toLocaleTimeString()}`);
    set("machine-cpuVal", Math.round(cpu)); ring("machine-cpuArc", cpu / 100);
    const mv = q("machine-tempVal"); if (mv) { mv.innerHTML = temp == null ? "--" : `${temp.toFixed(1)}<small>°C</small>`; mv.style.color = temp == null ? "" : tempColor(temp); }
    set("machine-clockVal", d.clock ? d.clock + " MHz" : "--");
    html("machine-powerVal", age > 10 ? '<span style="color:var(--warn)">DELAYED</span>' : '<span style="color:var(--good)">LIVE</span>');
    set("machine-upVal", fmtUp(d.uptime || 0));
    set("machine-memVal", Math.round(memF * 100) + "%");
    set("machine-memSub", `${fmtB(used)} / ${fmtB(mem.total)}`); ring("machine-memArc", memF);
    set("machine-swap", mem.swapTotal ? `swap ${fmtB(mem.swapTotal - (mem.swapFree || 0))} / ${fmtB(mem.swapTotal)}` : "no swap");
    const disks = Array.isArray(d.disks) ? d.disks : [];
    const root = disks.find(x => x.mount === "/" && x.mounted !== false);
    if (root) { const u = root.total - root.free; set("machine-diskVal", Math.round(pct(u, root.total) * 100) + "%"); set("machine-diskSub", `${fmtB(u)} / ${fmtB(root.total)}`); ring("machine-diskArc", pct(u, root.total)); }
    html("machine-cores", (d.cores || []).map((v, i) => { const p = Math.max(0, Math.min(100, num(v) ?? 0)); return `<div class="core"><em>C${i}</em><i style="height:${p}%"></i><b>${Math.round(p)}%</b></div>`; }).join(""));
    set("machine-loadVal", "load " + (d.load || []).map(x => Number(x).toFixed(2)).join(" "));
    set("machine-rxVal", fmtRate((d.net && d.net.rx) || 0)); set("machine-txVal", fmtRate((d.net && d.net.tx) || 0));
    const h = d.history || {};
    if (!q("view-themachine")?.classList.contains("active")) { /* skip canvas work when tab hidden */ }
    else {
      const cs = q("machine-cpuSpark"), ns = q("machine-netSpark");
      if (cs) spark(cs, [{ data: h.cpu || [], color: accent() }], { max: 100 });
      if (ns) spark(ns, [{ data: h.rx || [], color: accent() }, { data: h.tx || [], color: "#ff3df2" }]);
    }
    const names = {};
    ((d.driveHealth || {}).drives || []).forEach(x => { if (x.device) names[String(x.device).replace("/dev/", "")] = x.label; });
    renderIO("machine-", d.io, h.rd, h.wr, names);
    html("machine-storage", disks.map(x => `<div class="row"><div class="main"><div class="name">${esc(x.label || x.mount)}</div><div class="meta">${esc(x.mount)}</div></div><div class="num">${x.mounted === false ? '<span style="color:var(--warn)">NOT MOUNTED</span>' : esc(fmtB(x.free)) + " free"}<div class="meta">${x.total ? esc(fmtB(x.total)) + " total" : ""}</div></div></div>`).join("") || '<div class="note">No storage data.</div>');
    const hl = d.driveHealth || {};
    html("machine-health", (hl.drives || []).map(x => {
      const st = hl.stale ? "stale" : String(x.status || "unknown");
      const details = [x.temperature == null ? null : `${x.temperature}°C`, x.powerOnHours == null ? null : `${Number(x.powerOnHours).toLocaleString()} power-on hours`].filter(Boolean).join(" · ");
      const errs = Object.entries(x.errors || {}).map(([k, v]) => `${k}: ${v}`).join(" · ");
      return `<div class="fleet-drive"><div class="fleet-heading"><b>${esc(x.label || x.device)}</b><span class="fleet-state ${st === "passed" ? "up" : "down"}">${esc(STATES[st] || st.toUpperCase())}</span></div><small>${esc(x.model || x.device || "")}</small>${details ? `<p>${esc(details)}</p>` : ""}${errs ? `<p>${esc(errs)}</p>` : ""}${x.message ? `<p>${esc(x.message)}</p>` : ""}</div>`;
    }).join("") + (hl.ts ? `<p class="fleet-caption">Checked ${esc(new Date(hl.ts * 1000).toLocaleTimeString())}. A passing check can't guarantee future reliability.</p>` : "") || '<div class="note">Drive health is awaiting its first check.</div>');
    const b = d.backup || {};
    set("machine-backup", b.configured ? `${String(b.status || "unknown").toUpperCase()}${b.lastSuccess ? " · last success " + new Date(b.lastSuccess * 1000).toLocaleString() : " · no completed backup yet"} · nightly 3:15–3:30 AM` : "Backups not configured");
    html("machine-procs", (d.procs || []).map(p => `<div class="row"><div class="main"><div class="name">${esc(p.name)}</div><div class="meta">pid ${esc(p.pid)}</div></div><div class="num">${(num(p.cpu) ?? 0).toFixed(1)}%<div class="meta">${(num(p.mem) ?? 0).toFixed(1)}% mem</div></div></div>`).join("") || '<div class="note">No process data.</div>');
  });
})();
