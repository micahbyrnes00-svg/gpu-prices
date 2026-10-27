"use strict";
const $ = (s, r = document) => r.querySelector(s);
const $$ = (s, r = document) => [...r.querySelectorAll(s)];
const api = (p, o = {}) => fetch(p, { cache: "no-store", ...o }).then(r => r.json());
const post = (p, body) => api(p, { method: "POST", headers: { "Content-Type": "application/json", "X-PiCommand": "1" }, body: JSON.stringify(body) });

const ACCENTS = { cyan: "#33e1ff", magenta: "#ff3df2", lime: "#b6ff3d", amber: "#ffb23d", violet: "#9d8cff" };
const PANELS = { system: "System gauges", cores: "CPU cores", network: "Network", market: "Used market",
  services: "Services", containers: "Containers", jobs: "Jobs & backups", links: "Links" };
let settings = null, status = null, es = null;

/* ---------------- info sheets: what each thing is and how it connects ---------------- */
const INFO = {
  overview: ["How Orbit fits together", `
<p><b>The Pi</b> (Raspberry Pi 4, 4 GB) boots from the 2 TB Seagate. The SD card holds the old system as a last-resort fallback.</p>
<p><b>Orbit</b> (this app) is a small Python service on the Pi (<code>picommand.service</code>) on port 8099, reachable only from the Pi itself. <code>tailscale serve</code> publishes it to your private Tailscale network over HTTPS. The service only answers requests that Tailscale has tagged with your login, so nobody else on the internet or your Wi-Fi can open it.</p>
<p><b>The price site</b> works like this: every 6 hours <code>gpu-prices.timer</code> runs the tracker. It pulls listings from the official eBay API, stores them in SQLite, has Claude write short summaries, and rebuilds static pages in <code>/home/pi/site</code>. A Caddy web server in Docker serves those pages, and <b>Tailscale Funnel</b> makes them public at your ts.net address. Your router has no open ports.</p>
<p><b>Money:</b> every "View on eBay" link carries your eBay Partner Network campaign ID, so qualifying purchases pay you a commission.</p>
<p><b>Backups:</b> every Sunday <code>pi-cloud-backup.timer</code> compresses the whole system, encrypts it with your password, and uploads it to Google Drive. It keeps the last 4.</p>
<p><b>Code:</b> everything lives in your GitHub repo <code>gpu-prices</code>. "Update this app" pulls the latest version.</p>`],
  cpu: ["CPU load", `<p>Percentage of the 4 ARM cores busy, sampled every second from <code>/proc/stat</code>. Sustained 100% means the Pi is saturated. The weekly backup and price updates cause short spikes.</p>
<p><b>Temp</b> comes from the SoC sensor. The Pi slows itself at 80 °C, so below 70 °C is comfortable.</p>
<p><b>Clock</b> is the current ARM speed. 1800 MHz is full speed, and a lower number while busy means throttling.</p>
<p><b>Power</b> reads the firmware's throttle flags. <code>0x0</code> means clean power. Anything else means under-voltage or throttling, which is the problem the new power supply fixed.</p>`],
  mem: ["Memory", `<p>Used = total minus what Linux reports as <i>available</i>. Disk cache counts as available because Linux frees it instantly when programs need it. Swap is compressed RAM (zram), not the disk.</p>`],
  disk: ["Disk", `<p>Space on the root filesystem, the Seagate's <code>sgroot</code> partition. Prices, the site, Docker images and logs all live here. The boot files sit on a small separate partition (<code>SGBOOT</code>).</p>`],
  cores: ["Cores", `<p>Each bar is one CPU core. The line below is the last two minutes of overall load. Load average (1, 5 and 15 min) counts how many tasks were waiting to run. Under 4 on this 4-core Pi means it's keeping up.</p>`],
  network: ["Network", `<p>Combined throughput on Ethernet and Wi-Fi, from <code>/proc/net/dev</code>. Docker's internal interfaces are excluded. Big upload spikes on Sunday nights are the encrypted backup going to Google Drive.</p>`],
  procs: ["Top processes", `<p>The programs using the most CPU right now, from <code>ps</code>. Usual residents: <code>wayvnc</code> (VNC), <code>labwc</code> (desktop), <code>dockerd</code>, <code>tailscaled</code>, and <code>zstd</code>/<code>rclone</code> during backups.</p>`],
  market: ["Used market index", `<p>The average 7-day change in the typical used price across every tracked GPU or RAM kit. Green and down means cheaper, which is good for buyers. Red and up means prices are rising.</p>
<p>The data comes from the tracker's SQLite database, which <code>gpu-prices.timer</code> fills every 6 hours from the eBay Browse API. This panel reads the same numbers the public site shows.</p>`],
  deals: ["Live deals", `<p>Listings at least 15% under the model's typical price from sellers with 98%+ feedback and 20+ ratings. Listings that look too good to be true (under 60% of the low range) are dropped.</p>
<p>Tapping one opens eBay through your affiliate link.</p>`],
  rows: ["Model rows", `<p>The typical (median) used price including shipping, the 7-day change, and a 30-day sparkline. Tap a row to open that model's public page on your site.</p>`],
  jobs: ["Jobs", `<p><b>Run price update</b> starts <code>gpu-prices.service</code> now, without waiting for the 6-hour timer.</p>
<p><b>Run cloud backup</b> starts the encrypted Google Drive backup now. It takes about 15 to 40 minutes.</p>
<p><b>Go public / Go private</b> turns Tailscale Funnel on or off for the price site. Off means the site stays private.</p>
<p><b>Update this app</b> pulls the latest code from GitHub and restarts this service.</p>
<p>Each button runs one fixed command. The app can't run arbitrary commands.</p>`],
  services: ["Services", `<p>The systemd units that make up the setup. <b>Timers</b> schedule jobs. Services are long-running programs.</p>
<p><code>tailscaled</code> handles private networking, Funnel and this app's HTTPS. <code>docker</code> runs the web server, Portainer and Glances. <code>wayvnc</code> is remote desktop.</p>
<p>Restart fixes most hiccups. Stopping <code>tailscaled</code> cuts off this app until the Pi reboots.</p>`],
  containers: ["Containers", `<p>Docker containers on the Pi. <code>gpu-prices-web</code> (Caddy) serves the price site to Funnel. <code>portainer</code> is a full Docker admin UI. <code>glances</code> is a detailed system monitor.</p>`],
  links: ["Links", `<p>Shortcuts to the other tools. Tailnet links only work while your phone's Tailscale is connected.</p>`],
  power: ["Reboot", `<p>Hold for 2 seconds to reboot the Pi. It takes about 2 minutes to come back, because it boots from a spinning disk. This app reconnects by itself.</p>`],
  settings: ["Settings", `<p>Settings are saved on the Pi, so every device sees the same layout. Refresh controls how often live numbers update. A faster refresh uses a little more battery.</p>`],
  identity: ["Identity & security", `<p>Tailscale tells the Pi who you are on every request. The app only accepts your login, so there's no password to steal, and it isn't reachable from the public internet.</p>`],
};

function openInfo(key) {
  const [t, html] = INFO[key] || ["Info", "<p>No details.</p>"];
  $("#sheetTitle").textContent = t;
  $("#sheetBody").innerHTML = html;
  $("#sheet").classList.add("open");
}
function closeInfo() { $("#sheet").classList.remove("open"); }

/* ---------------- helpers ---------------- */
const fmtB = b => { if (b == null) return "--"; const u = ["B", "KB", "MB", "GB", "TB"]; let i = 0; while (b >= 1024 && i < 4) { b /= 1024; i++; } return b.toFixed(b < 10 && i ? 1 : 0) + " " + u[i]; };
const fmtRate = b => fmtB(b) + "/s";
const fmtUp = s => { const d = Math.floor(s / 86400), h = Math.floor(s % 86400 / 3600), m = Math.floor(s % 3600 / 60); return d ? `${d}d ${h}h` : h ? `${h}h ${m}m` : `${m}m`; };
const money = v => v == null ? "--" : "$" + Math.round(v).toLocaleString();
const pct = v => v == null ? '<span class="flat">--</span>' : `<span class="${v > .5 ? "up" : v < -.5 ? "down" : "flat"}">${v > .5 ? "▲" : v < -.5 ? "▼" : "•"} ${Math.abs(v).toFixed(1)}%</span>`;
const esc = s => String(s ?? "").replace(/[&<>"']/g, c => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
const ago = t => { if (!t) return "never"; const s = Date.now() / 1000 - t; return s < 0 ? "in " + fmtUp(-s) : fmtUp(s) + " ago"; };
function setRing(el, frac) {
  const r = el.r.baseVal.value, c = 2 * Math.PI * r;
  el.style.strokeDasharray = c; el.style.strokeDashoffset = c * (1 - Math.max(0, Math.min(1, frac)));
  el.classList.toggle("hot", frac > .75 && frac <= .9); el.classList.toggle("crit", frac > .9);
}
function toast(msg) { const t = $("#toast"); t.textContent = msg; t.classList.add("show"); clearTimeout(t._h); t._h = setTimeout(() => t.classList.remove("show"), 3200); }
function accent() { return getComputedStyle(document.documentElement).getPropertyValue("--a").trim(); }

function spark(canvas, series, opts = {}) {
  const dpr = devicePixelRatio || 1, w = canvas.clientWidth, h = canvas.clientHeight;
  if (!w) return;
  canvas.width = w * dpr; canvas.height = h * dpr;
  const g = canvas.getContext("2d"); g.scale(dpr, dpr); g.clearRect(0, 0, w, h);
  const all = series.flatMap(s => s.data);
  const max = Math.max(opts.max || 0, ...all, 1), n = Math.max(...series.map(s => s.data.length), 2);
  series.forEach((s, si) => {
    const pts = s.data.map((v, i) => [w - (s.data.length - 1 - i) * (w / (n - 1)), h - 3 - (v / max) * (h - 8)]);
    if (pts.length < 2) return;
    g.beginPath(); pts.forEach(([x, y], i) => i ? g.lineTo(x, y) : g.moveTo(x, y));
    g.strokeStyle = s.color; g.lineWidth = 2; g.shadowColor = s.color; g.shadowBlur = 8; g.stroke(); g.shadowBlur = 0;
    if (si === 0) {
      g.lineTo(pts.at(-1)[0], h); g.lineTo(pts[0][0], h); g.closePath();
      const grd = g.createLinearGradient(0, 0, 0, h); grd.addColorStop(0, s.color + "55"); grd.addColorStop(1, s.color + "00");
      g.fillStyle = grd; g.fill();
    }
  });
}
function miniSpark(data) {
  if (!data || data.length < 2) return "";
  const min = Math.min(...data), max = Math.max(...data), r = max - min || 1;
  const pts = data.map((v, i) => `${(i / (data.length - 1) * 64).toFixed(1)},${(20 - (v - min) / r * 18).toFixed(1)}`).join(" ");
  const up = data.at(-1) > data[0];
  return `<svg class="sparkmini" viewBox="0 0 64 22"><polyline points="${pts}" fill="none" stroke="${up ? "var(--bad)" : "var(--good)"}" stroke-width="1.6"/></svg>`;
}

/* ---------------- live stream ---------------- */
const hist = { cpu: [], rx: [], tx: [] };
function onLive(d) {
  $("#host").textContent = `by Micah · ${d.host || "pi"} · ${(d.model || "").replace("Raspberry Pi", "RPi").replace(" Model B", "")}`;
  $("#cpuVal").textContent = Math.round(d.cpu);
  setRing($("#cpuArc"), d.cpu / 100);
  $("#tempVal").innerHTML = d.temp != null ? `${d.temp.toFixed(1)}<small>°C</small>` : "--";
  $("#tempVal").style.color = d.temp > 75 ? "var(--bad)" : d.temp > 65 ? "var(--warn)" : "";
  $("#clockVal").textContent = d.clock ? d.clock + " MHz" : "--";
  const clean = d.throttled === "0x0";
  $("#powerVal").innerHTML = d.throttled ? `<span style="color:${clean ? "var(--good)" : "var(--bad)"}">${clean ? "CLEAN" : d.throttled}</span>` : "--";
  $("#upVal").textContent = fmtUp(d.uptime || 0);
  const used = d.mem.total - d.mem.avail;
  $("#memVal").textContent = Math.round(used / d.mem.total * 100) + "%";
  $("#memSub").textContent = `${fmtB(used)} / ${fmtB(d.mem.total)}`;
  setRing($("#memArc"), used / d.mem.total);
  const root = (d.disks || []).find(x => x.mount === "/");
  if (root) {
    const u = root.total - root.free;
    $("#diskVal").textContent = Math.round(u / root.total * 100) + "%";
    $("#diskSub").textContent = `${fmtB(u)} / ${fmtB(root.total)}`;
    setRing($("#diskArc"), u / root.total);
  }
  const cores = $("#cores");
  if (cores.children.length !== d.cores.length) cores.innerHTML = d.cores.map((_, i) => `<div class="core"><em>C${i}</em><i></i><b></b></div>`).join("");
  d.cores.forEach((v, i) => { const c = cores.children[i]; c.querySelector("i").style.height = v + "%"; c.querySelector("b").textContent = Math.round(v) + "%"; });
  $("#loadVal").textContent = "load " + (d.load || []).map(x => x.toFixed(2)).join(" ");
  $("#rxVal").textContent = fmtRate(d.net.rx); $("#txVal").textContent = fmtRate(d.net.tx);
  hist.cpu.push(d.cpu); hist.rx.push(d.net.rx); hist.tx.push(d.net.tx);
  for (const k in hist) hist[k] = hist[k].slice(-120);
  spark($("#cpuSpark"), [{ data: hist.cpu, color: accent() }], { max: 100 });
  spark($("#netSpark"), [{ data: hist.rx, color: accent() }, { data: hist.tx, color: "#ff3df2" }]);
  $("#procs").innerHTML = (d.procs || []).map(p => `<div class="row"><div class="main"><div class="name">${esc(p.name)}</div><div class="meta">pid ${p.pid}</div></div><div class="num">${p.cpu.toFixed(1)}%<div class="meta">${p.mem.toFixed(1)}% mem</div></div></div>`).join("");
}
let fails = 0, poller = null, gotMsg = false;
function setLink(ok, txt) { $("#linkState").className = "link-state " + (ok ? "live" : "down"); $("#linkText").textContent = txt; }
function poll() {  // fallback if a proxy buffers the event stream
  clearInterval(poller);
  poller = setInterval(async () => { try { onLive(await api("api/live")); setLink(true, "LIVE"); } catch { setLink(false, "RETRY"); } }, (settings?.refresh || 2) * 1000);
}
function connect() {
  if (es) es.close();
  if (fails >= 2) return poll();
  gotMsg = false;
  es = new EventSource("api/stream");
  es.onmessage = e => { gotMsg = true; fails = 0; setLink(true, "LIVE"); onLive(JSON.parse(e.data)); };
  es.onerror = () => { setLink(false, "RETRY"); es.close(); fails++; setTimeout(connect, 3000); };
  setTimeout(() => { if (!gotMsg) { fails = 2; es.close(); poll(); } }, 8000);
}
async function seedHistory() {
  try { const d = await api("api/live"); if (d.history) { hist.cpu = d.history.cpu; hist.rx = d.history.rx; hist.tx = d.history.tx; } if (d.cpu != null) onLive(d); } catch { }
}

/* ---------------- status (slower) ---------------- */
async function loadStatus() {
  try { status = await api("api/status"); } catch { return; }
  renderMarket(status.market); renderControl(status);
}
function renderMarket(m) {
  const note = $("#marketNote");
  if (!m || !m.ready) { note.textContent = (m && (m.note || m.error)) || "No data yet."; ["#gpu7", "#ram7"].forEach(s => $(s).textContent = "--"); $("#deals").innerHTML = ""; $("#gpuRows").innerHTML = ""; $("#ramRows").innerHTML = ""; return; }
  note.textContent = (m.demo ? "DEMO DATA · " : "") + "updated " + esc(m.lastRun?.replace("T", " ").slice(0, 16) + " UTC");
  $("#siteLink").href = m.site;
  $("#gpu7").innerHTML = pct(m.gpu7); $("#ram7").innerHTML = pct(m.ram7);
  $("#gpu30").innerHTML = "30d " + pct(m.gpu30); $("#ram30").innerHTML = "30d " + pct(m.ram30);
  $("#deals").innerHTML = m.deals.length ? m.deals.map(d => `<a class="row" href="${esc(d.url)}" target="_blank" rel="noopener sponsored"><div class="main"><div class="name">${esc(d.model)}</div><div class="meta">${esc(d.title)}</div></div><div class="num">${money(d.total)}<div class="meta down">${d.under}% under</div></div></a>`).join("") : '<div class="note">No standout deals right now.</div>';
  const row = r => `<a class="row" href="${esc(r.url)}" target="_blank" rel="noopener"><div class="main"><div class="name">${esc(r.name)}</div><div class="meta">${r.perGb ? "$" + r.perGb.toFixed(2) + "/GB · " : ""}30d ${r.chg30 == null ? "--" : r.chg30.toFixed(1) + "%"}</div></div>${miniSpark(r.spark)}<div class="num">${money(r.median)}<div class="meta">${pct(r.chg7)}</div></div></a>`;
  $("#gpuRows").innerHTML = m.rows.filter(r => r.cat === "gpu").map(row).join("");
  $("#ramRows").innerHTML = m.rows.filter(r => r.cat === "ram").map(row).join("");
}
function renderControl(s) {
  const ts = s.tailscale || {};
  const funnel = !!ts.funnel;
  $("#funnelBtn").dataset.action = funnel ? "funnel_off" : "funnel_on";
  $("#funnelText").textContent = funnel ? "Go private" : "Go public";
  $("#funnelBtn").classList.toggle("live", funnel);
  $("#tsInfo").textContent = ts.dns ? `${ts.dns} · ${ts.ip} · ${(ts.peers || []).filter(p => p.online).length} peers online` : "";
  $("#timers").innerHTML = (s.timers || []).map(t => `<div class="row"><div class="main"><div class="name">${esc(t.unit.replace(".timer", ""))}</div><div class="meta">last ${ago(t.last)}</div></div><div class="num">${t.next ? ago(t.next) : "off"}<div class="meta">next run</div></div></div>`).join("") || '<div class="note">Timers appear after go-live.</div>';
  const b = s.backups || {};
  $("#backups").innerHTML = !b.configured ? '<div class="note">Cloud backup not configured.</div>' :
    b.loading ? '<div class="note">Reading backup list from Google Drive…</div>' :
    b.error ? `<div class="note">Backup list: ${esc(b.error)}</div>` :
    (b.running ? '<div class="row"><div class="main"><div class="name">Backup uploading…</div></div><span class="badge on">LIVE</span></div>' : "") +
    (b.files || []).filter(f => !f.name.includes("-boot")).slice(0, 4).map(f => `<div class="row"><div class="main"><div class="name">${esc(f.name)}</div><div class="meta">${esc(f.time.slice(0, 16).replace("T", " "))} · encrypted on Google Drive</div></div><div class="num">${fmtB(f.size)}</div></div>`).join("");
  $("#services").innerHTML = (s.services || []).map(u => {
    const on = u.active === "active";
    return `<div class="row"><div class="main"><div class="name">${esc(u.unit.replace(/\.(service|timer|socket)$/, ""))}</div><div class="meta">${esc(u.desc)}</div></div><span class="badge ${on ? "on" : "off"}">${esc((u.sub || u.active).toUpperCase())}</span>
      <button class="btn" data-act="restart" data-target="${esc(u.unit)}">↻</button>
      ${u.unit === "picommand.service" ? "" : `<button class="btn" data-act="${on ? "stop" : "start"}" data-target="${esc(u.unit)}">${on ? "■" : "▶"}</button>`}</div>`;
  }).join("");
  $("#containers").innerHTML = (s.containers || []).map(c => `<div class="row"><div class="main"><div class="name">${esc(c.name)}</div><div class="meta">${esc(c.image)} · ${esc(c.status)}</div></div><span class="badge ${c.state === "running" ? "on" : "off"}">${esc((c.state || "").toUpperCase())}</span><button class="btn" data-act="container_restart" data-target="${esc(c.name)}">↻</button></div>`).join("");
  const host = ts.dns || location.hostname;
  const links = [
    ["Price site", ts.funnel ? "public · Funnel" : "private until go-live", `https://${host}/`],
    ["Glances", "deep system monitor", `https://${host}:10000/`],
    ["Portainer", "Docker admin", `https://${ts.ip || host}:9443/`],
    ["Cockpit", "Pi admin & terminal", `https://${ts.ip || host}:9090/`],
    ["GitHub repo", "gpu-prices code", "https://github.com/micahbyrnes00-svg/gpu-prices"],
    ["eBay Partner", "affiliate earnings", "https://partnernetwork.ebay.com/"],
    ["eBay Developer", "API keys", "https://developer.ebay.com/my/keys"],
    ["Tailscale", "devices & Funnel", "https://login.tailscale.com/admin/machines"],
    ["Google Drive", "encrypted backups", "https://drive.google.com/drive/search?q=pi-backups"],
    ["Search Console", "Google ranking", "https://search.google.com/search-console"],
  ];
  $("#links").innerHTML = links.map(([n, d, u]) => `<a href="${esc(u)}" target="_blank" rel="noopener">${esc(n)}<small>${esc(d)}</small></a>`).join("");
}

/* ---------------- actions ---------------- */
async function runAction(action, target, btn) {
  btn?.classList.add("busy");
  try {
    const r = await post("api/action", { action, target });
    toast((r.ok ? "✓ " : "✗ ") + (r.message || action));
  } catch { toast("✗ no response"); }
  btn?.classList.remove("busy");
  setTimeout(loadStatus, 1200);
}
document.addEventListener("click", e => {
  const info = e.target.closest("[data-info-btn]"); if (info) { openInfo(info.dataset.infoBtn); return; }
  if (e.target.closest("#sheet .close") || e.target.id === "sheet") { closeInfo(); return; }
  const tab = e.target.closest(".tabs button");
  if (tab) { $$(".tabs button").forEach(b => b.classList.toggle("on", b === tab)); $$(".view").forEach(v => v.classList.toggle("active", v.id === "view-" + tab.dataset.view)); scrollTo(0, 0); if (tab.dataset.view !== "system") loadStatus(); return; }
  const act = e.target.closest(".act[data-action]"); if (act) { runAction(act.dataset.action, "", act); return; }
  const b = e.target.closest("[data-act]");
  if (b) { const a = b.dataset.act, t = b.dataset.target; if ((a === "stop" || t === "tailscaled.service") && !confirm(`${a} ${t}?`)) return; runAction(a, t, b); }
});

/* hold-to-reboot */
(() => {
  const btn = $("#rebootBtn"), fill = btn.querySelector(".fill"); let t0 = 0, raf = 0;
  const step = () => { const p = Math.min(1, (performance.now() - t0) / 2000); fill.style.width = p * 100 + "%"; if (p >= 1) { stop(true); return; } raf = requestAnimationFrame(step); };
  const start = e => { e.preventDefault(); t0 = performance.now(); raf = requestAnimationFrame(step); };
  const stop = done => { cancelAnimationFrame(raf); fill.style.width = "0"; if (done === true) { btn.querySelector(".txt").textContent = "REBOOTING…"; runAction("reboot", "", null); setTimeout(() => btn.querySelector(".txt").textContent = "HOLD TO REBOOT", 15000); } };
  btn.addEventListener("pointerdown", start); ["pointerup", "pointerleave", "pointercancel"].forEach(ev => btn.addEventListener(ev, () => stop(false)));
})();

/* ---------------- settings ---------------- */
function applySettings(s) {
  settings = s;
  document.documentElement.dataset.accent = s.accent;
  document.body.classList.toggle("compact", s.compact);
  document.body.classList.toggle("reduce", s.reduceMotion);
  $$("[data-panel]").forEach(p => p.classList.toggle("hidden", s.panels[p.dataset.panel] === false));
  $("#refresh").value = s.refresh; $("#refreshVal").textContent = s.refresh + "s";
  $("#compact").checked = s.compact; $("#reduceMotion").checked = s.reduceMotion;
  $("#swatches").innerHTML = Object.entries(ACCENTS).map(([k, c]) => `<button class="sw ${k === s.accent ? "on" : ""}" style="background:${c};color:${c}" data-accent="${k}" aria-label="${k}"></button>`).join("");
  $("#panelToggles").innerHTML = Object.entries(PANELS).map(([k, n]) => `<label class="tog"><span>${n}</span><input type="checkbox" data-ptog="${k}" ${s.panels[k] !== false ? "checked" : ""}></label>`).join("");
}
async function saveSettings(patch) { applySettings(await post("api/settings", patch)); }
document.addEventListener("change", e => {
  if (e.target.id === "refresh") { saveSettings({ refresh: +e.target.value }).then(connect); }
  if (e.target.id === "compact") saveSettings({ compact: e.target.checked });
  if (e.target.id === "reduceMotion") saveSettings({ reduceMotion: e.target.checked });
  if (e.target.dataset.ptog) saveSettings({ panels: { [e.target.dataset.ptog]: e.target.checked } });
});
document.addEventListener("input", e => { if (e.target.id === "refresh") $("#refreshVal").textContent = e.target.value + "s"; });
document.addEventListener("click", e => { const sw = e.target.closest(".sw"); if (sw) saveSettings({ accent: sw.dataset.accent }); });

/* ---------------- info buttons ---------------- */
function addInfoButtons() {
  $$("[data-info]").forEach(p => {
    const ph = p.querySelector(".ph") || p;
    if (ph.querySelector("[data-info-btn]")) return;
    const b = document.createElement("button");
    b.className = "info"; b.dataset.infoBtn = p.dataset.info; b.setAttribute("aria-label", "How this works"); b.textContent = "i";
    ph.appendChild(b);
  });
}

/* ---------------- boot ---------------- */
(async () => {
  addInfoButtons();
  try { applySettings(await api("api/settings")); } catch { }
  try { const me = await api("api/me"); $("#me").textContent = "Signed in via Tailscale as " + me.login; } catch { }
  await seedHistory(); connect(); loadStatus();
  setInterval(loadStatus, 30000);
  document.addEventListener("visibilitychange", () => { if (!document.hidden) { connect(); loadStatus(); } });
  if ("serviceWorker" in navigator) navigator.serviceWorker.register("sw.js").catch(() => { });
})();
