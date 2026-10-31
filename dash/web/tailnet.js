/* Tailnet panel (Network tab): devices, connection paths, ping, watch, serve/Funnel routes, admin API actions.
   Uses app.js helpers ($, api, post, esc, ago, fmtB, toast, runAction, alertCfg, cur). Refreshes every 15 s while visible. */
(() => {
  const list = $("#tnPeers");
  if (!list) return;
  const pings = {};
  let data = null, busy = false, lastLoad = 0;
  const watched = () => new Set(((typeof alertCfg !== "undefined" && alertCfg && alertCfg.tsWatch) || ["themachine"]).map(x => x.toLowerCase()));
  const days = t => t ? Math.round((t - Date.now() / 1000) / 86400) : null;

  function row(n, isSelf, api, watch) {
    const tags = [];
    if (isSelf) tags.push('<span class="tag">THIS PI</span>');
    if (n.exitNode) tags.push('<span class="tag">EXIT NODE</span>');
    if (n.authorized === false) tags.push('<span class="tag bad">NEEDS APPROVAL</span>');
    if (n.updateAvailable) tags.push('<span class="tag warn">UPDATE</span>');
    const exp = n.keyExpiryDisabled ? null : days(n.keyExpiry || n.expires);
    if (exp != null && exp <= 30) tags.push(`<span class="tag ${exp <= 7 ? "bad" : "warn"}">KEY ${exp <= 0 ? "EXPIRED" : exp + "D"}</span>`);
    const meta = [n.os, n.ip, n.online ? n.path : "last seen " + ago(n.lastSeen), n.clientVersion ? "v" + n.clientVersion : ""]
      .filter(Boolean).join(" · ");
    const p = pings[n.name];
    const pingLine = p ? `<div class="ping">${esc(p)}</div>` : "";
    const acts = [];
    if (!isSelf && n.online) acts.push(`<button class="btn" data-tsping="${esc(n.name)}">PING</button>`);
    if (!isSelf) acts.push(`<button class="btn ${watch.has(n.name.toLowerCase()) ? "on" : ""}" data-tswatch="${esc(n.name)}" aria-label="Watch ${esc(n.name)}">${watch.has(n.name.toLowerCase()) ? "★" : "☆"}</button>`);
    if (api && n.authorized === false) acts.push(`<button class="btn go" data-act="ts_authorize" data-target="${esc(n.id)}">APPROVE</button>`);
    if (api && exp != null && exp <= 30 && !n.keyExpiryDisabled) acts.push(`<button class="btn" data-act="ts_keyexpiry" data-target="${esc(n.id)}">NO EXPIRY</button>`);
    return `<div class="row tn-row"><span class="badge ${n.online ? "on" : "off"}">${n.online ? "ON" : "OFF"}</span>
      <div class="main"><div class="name">${esc(n.name)}${tags.join("")}</div><div class="meta">${esc(meta)}</div>${pingLine}</div>
      <div class="acts">${acts.join("")}</div></div>`;
  }

  function render() {
    const d = data;
    if (!d) return;
    const st = $("#tnState");
    if (d.error) {
      st.textContent = "DOWN"; st.className = "badge off";
      $("#tnNote").textContent = d.error; list.innerHTML = ""; return;
    }
    const peers = d.peers || [];
    st.textContent = d.backend === "Running" ? (d.serve?.funnel ? "FUNNEL ON" : "CONNECTED") : String(d.backend || "--").toUpperCase();
    st.className = "badge " + (d.backend === "Running" ? (d.serve?.funnel ? "warn" : "on") : "off");
    $("#tnCount").textContent = `${peers.filter(p => p.online).length + 1}/${peers.length + 1}`;
    const nc = d.netcheck || {};
    $("#tnDerp").textContent = nc.loading ? "…" : nc.derpMs != null ? `${nc.derpMs} ms` : "--";
    $("#tnNat").textContent = nc.loading ? "…" : nc.error ? "--" : !nc.udp ? "NO UDP" : nc.hardNAT ? "HARD" : "EASY";
    const notes = [`${d.self?.dns || ""}`, d.version ? `Tailscale ${d.version}` : "", ...(d.health || []).slice(0, 2)];
    if (!d.api?.enabled) notes.push("Add an admin API token below for updates, key expiry and approvals.");
    else if (d.api.error) notes.push("Admin API: " + d.api.error);
    $("#tnNote").textContent = notes.filter(Boolean).join(" · ");
    const watch = watched(), api = d.api?.enabled && !d.api.error;
    list.innerHTML = [row(d.self, true, api, watch), ...peers.map(p => row(p, false, api, watch))].join("");
    const routes = d.serve?.routes || [];
    $("#tnServe").innerHTML = routes.length ? routes.map(r => `<div class="row"><div class="main"><div class="name">:${esc(r.port)}${esc(r.path === "/" ? "" : r.path)}</div><div class="meta">→ ${esc(r.target)}</div></div><span class="badge ${r.public ? "warn" : "on"}">${r.public ? "PUBLIC" : "TAILNET"}</span></div>`).join("")
      : `<div class="note">${esc(d.serve?.error || "Nothing published with tailscale serve.")}</div>`;
    const up = $("#tnUpdate");
    up.hidden = !d.updateAvailable;
    up.textContent = `UPDATE TAILSCALE ON THE PI${d.latest ? " → " + d.latest : ""}`;
    $("#tnKey").placeholder = d.api?.enabled ? "Admin API token saved · paste to replace, SAVE empty to remove" : "Admin API token (tskey-api-…)";
  }

  async function load(force) {
    if (busy || (!force && Date.now() - lastLoad < 5000)) return;
    busy = true;
    try {
      if (force) await post("api/tailnet/refresh", {});
      data = await api("api/tailnet"); lastLoad = Date.now(); render();
    } catch { $("#tnNote").textContent = "Tailnet status unavailable."; }
    finally { busy = false; }
  }
  window.loadTailnet = load;

  document.addEventListener("click", async e => {
    const pb = e.target.closest("[data-tsping]");
    if (pb) {
      const name = pb.dataset.tsping;
      pb.classList.add("busy"); pings[name] = "pinging…"; render();
      try {
        const r = await post("api/tailnet/ping", { peer: name });
        pings[name] = r.ok ? `${r.ms} ms · ${r.via}` : "✗ " + (r.message || "no reply");
      } catch { pings[name] = "✗ no response"; }
      pb.classList.remove("busy"); render(); return;
    }
    const wb = e.target.closest("[data-tswatch]");
    if (wb) {
      const name = wb.dataset.tswatch.toLowerCase(), set = watched();
      set.has(name) ? set.delete(name) : set.add(name);
      try {
        const cfg = await post("api/alerts/config", { tsWatch: [...set] });
        if (typeof alertCfg !== "undefined") alertCfg = cfg;
        toast(set.has(name) ? `Watching ${name}` : `Stopped watching ${name}`);
      } catch { toast("✗ Couldn't save"); }
      render(); return;
    }
  });
  $("#tnRefresh").addEventListener("click", () => load(true));
  $("#tnKeySave").addEventListener("click", async () => {
    const key = $("#tnKey").value.trim();
    if (!key && !confirm("Remove the Tailscale admin API token?")) return;
    try {
      const r = await post("api/integrations/tailscale", { key });
      toast((r.ok ? "✓ " : "✗ ") + r.message);
      if (r.ok) { $("#tnKey").value = ""; load(true); }
    } catch { toast("✗ no response"); }
  });
  setInterval(() => { if (cur === "network" && !document.hidden) load(); }, 15000);
})();
