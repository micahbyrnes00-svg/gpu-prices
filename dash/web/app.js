"use strict";
const $ = (s, r = document) => r.querySelector(s);
const $$ = (s, r = document) => [...r.querySelectorAll(s)];
const api = (p, o = {}) => fetch(p, { cache: "no-store", ...o }).then(r => r.json());
let unlockTok = null, unlockExp = 0;
const post = (p, body) => api(p, { method: "POST", headers: { "Content-Type": "application/json", "X-PiCommand": "1",
  ...(unlockTok && Date.now() < unlockExp ? { "X-Unlock": unlockTok } : {}) }, body: JSON.stringify(body) });

const ACCENTS = { cyan: "#33e1ff", magenta: "#ff3df2", lime: "#b6ff3d", amber: "#ffb23d", violet: "#9d8cff" };
const PANELS = { system: "System gauges", cores: "CPU cores", network: "Network", market: "Used market",
  services: "Services", containers: "Containers", jobs: "Jobs & backups", links: "Links", disks: "Drive health", money: "Money & traffic" };
let settings = null, status = null, es = null;

/* ---------------- info sheets: what each thing is and how it connects ---------------- */
const INFO = {
  diskio: ["Disk I/O", `<p>How fast each drive is being read from and written to right now, sampled every second from the kernel's <code>/proc/diskstats</code> counters. <b>Busy</b> is the share of time the drive spent handling requests; a drive near 100% busy is the bottleneck, even when the MB/s looks low (small random reads are slow on hard drives).</p><p>This is live activity, separate from <b>drive health</b> (SMART), which reports the drive's own wear and error counters on a schedule.</p>`],
  fleet: ["Your two-machine home lab", `<p><b>Raspberry Pi:</b> hosts Orbit, the price tracker, its website, and the existing cloud backup jobs.</p><p><b>themachine:</b> runs Ubuntu and Xfce from its Kingston SSD. The 2 TB drive at <code>/srv/data</code> holds shared files; the 4 TB drive at <code>/srv/backups</code> is a backup destination. A mounted backup drive does not mean backups have been scheduled or verified.</p><p>Every three seconds, Orbit reads a fixed set of health metrics over your private Tailscale network. Its dedicated SSH key is restricted to the metrics program and cannot open an interactive shell or forward ports.</p><p>An unreachable machine shows no live readings. A disconnected storage volume shows NOT MOUNTED instead of reporting the SSD's free space. Detailed gauges and management controls elsewhere in Orbit still apply to the Pi.</p>`],
  overview: ["How Orbit works", `
<p><b>Orbit</b> is a control panel for a Raspberry Pi, a small single-board Linux computer that runs all day as a home server. The Pi runs the operating system from an external USB drive, which is faster and lasts longer than a microSD card. Its programs and data are stored on that drive too.</p>
<p><b>The app:</b> a small Python web service on the Pi (<code>picommand.service</code>, managed by <b>systemd</b>, the Linux service manager) builds every screen. It listens only on the Pi's own loopback address (<code>127.0.0.1</code>), so no other device can connect to it directly.</p>
<p><b>Private access:</b> <b>Tailscale</b> is a VPN that links your own devices into a private, encrypted network (a "tailnet") over WireGuard. <code>tailscale serve</code> publishes the app on that network with a real HTTPS certificate. Each request is labelled with the signed-in Tailscale user, and Orbit only answers the owner's account. There's no password to steal and no open port on the router.</p>
<p><b>The price site:</b> a scheduled job collects used GPU and RAM listings from the official eBay API, stores them in a <b>SQLite</b> database, and generates static HTML pages. <b>Caddy</b>, a web server running in a <b>Docker</b> container, serves those pages. <b>Tailscale Funnel</b> can make the site public without opening router ports.</p>
<p><b>Revenue:</b> product links carry an eBay Partner Network (affiliate) tracking ID. eBay pays a commission on qualifying purchases made after a visitor clicks through.</p>
<p><b>Installable app:</b> Orbit is a Progressive Web App. Adding it to the Home Screen gives it its own icon, full-screen display and push notifications.</p>`],
  cpu: ["CPU, temperature & power", `<p><b>CPU load</b> is the share of time the processor's 4 cores spend working. It's measured once a second from the Linux kernel's counters in <code>/proc/stat</code>. Short spikes during scheduled jobs are normal. Staying near 100% means the Pi is overloaded.</p>
<p><b>Temp</b> is the processor (SoC) temperature from its built-in sensor. The Pi automatically slows itself (thermal throttling) at about 80 °C, so under 70 °C is healthy.</p>
<p><b>Clock</b> is the current CPU frequency. The Pi lowers it when idle to save power and raises it under load. A low clock while busy points to heat or power throttling.</p>
<p><b>Power</b> reads the firmware's throttle flags (<code>vcgencmd get_throttled</code>). <code>0x0</code> / CLEAN means the power supply is delivering enough voltage. Any other value means under-voltage or throttling, usually from a weak power supply or cable, which can cause crashes and drive disconnects.</p>`],
  mem: ["Memory (RAM)", `<p>Used memory is total RAM minus what the kernel reports as <i>available</i>. Linux uses spare RAM as a file cache to speed things up, and gives it back instantly when a program needs it, so the cache doesn't count as used.</p>
<p>Swap here is <b>zram</b>, a compressed area inside RAM, not space on the disk.</p>`],
  disk: ["Storage", `<p>How full the root filesystem (<code>/</code>) is: the partition holding the operating system, apps, databases, Docker images and logs. A small separate partition holds the boot files the Pi's firmware reads at power-on.</p>
<p>Above about 90% full, updates and databases can start failing, so an alert fires before that point.</p>`],
  cores: ["CPU cores", `<p>Each bar is one of the processor's cores. The line underneath is overall load for the last two minutes.</p>
<p><b>Load average</b> (1, 5 and 15 minutes) is the average number of tasks running or waiting for CPU time. On a 4-core machine, numbers under 4 mean it's keeping up.</p>`],
  network: ["Throughput", `<p>Live data rate in and out of the Pi across its wired (Ethernet) and wireless (Wi-Fi) interfaces, read from <code>/proc/net/dev</code>. Docker's internal virtual interfaces are excluded so traffic isn't counted twice.</p>`],
  procs: ["Top processes", `<p>The programs using the most CPU right now, from <code>ps</code>. A <b>PID</b> is the process ID Linux assigns to each running program. Common entries are the web server, Docker, Tailscale and the remote-desktop server.</p>`],
  market: ["Used market index", `<p>The average 7-day change in typical used price across all tracked graphics cards or RAM kits. Down (green) means prices are falling, which is good for buyers. Up (red) means rising.</p>
<p>Prices come from listings collected every 6 hours through the eBay Browse API and stored in the tracker's database. This screen shows the same numbers as the public site.</p>`],
  deals: ["Live deals", `<p>Listings priced at least 15% below that model's typical (median) price. To reduce scams, only sellers with 98%+ positive feedback and at least 20 ratings count, and anything priced suspiciously low is dropped.</p>
<p>Tapping a deal opens eBay through the affiliate link.</p>`],
  rows: ["Model prices", `<p>Every tracked category (graphics cards, CPUs, RAM, SSDs, monitors, consoles, iPhones) gets its own panel. For each model: the <b>median</b> used price including shipping (the middle value, so a few extreme listings don't skew it), the 7-day change, and a 30-day trend line.</p>
<p>Tap a row for the full price chart, 90-day high and low, and the cheapest trusted listings. <span class="signal">BUY</span> appears when today's typical price is the lowest in 90 days. You can get a push alert for that, too.</p>`],
  jobs: ["Jobs", `<p><b>Run price update</b> starts the price collection job immediately instead of waiting for its scheduled time.</p>
<p><b>Run cloud backup</b> creates a compressed, encrypted image of the system and uploads it to cloud storage. It can take a while, depending on upload speed.</p>
<p><b>Go public / Go private</b> turns Tailscale Funnel on or off, which controls whether the price site is reachable from the internet.</p>
<p><b>Update this app</b> pulls the latest code from the Git repository and restarts the service.</p>
<p>Each button runs one predefined command, and the server rejects anything else. It never runs arbitrary commands.</p>`],
  services: ["Services & timers", `<p><b>Services</b> are long-running background programs managed by systemd. <b>Timers</b> are systemd's scheduler (like cron) and start jobs at set times. The badge shows the current state, such as running, exited or failed.</p>
<p>↻ restarts a unit, which fixes most hiccups. ■ stops it and ▶ starts it. Stopping <code>tailscaled</code> cuts off remote access to this app until it's started again or the Pi reboots.</p>`],
  containers: ["Containers", `<p><b>Docker</b> runs apps in isolated containers that each bundle their own dependencies. That keeps them separate from the main system and easy to update or remove. The list shows each container's image (the app it runs) and its status.</p>`],
  links: ["Links", `<p>Shortcuts to related tools and accounts. Addresses on the private tailnet only open while the phone's Tailscale VPN is connected.</p>`],
  power: ["Reboot", `<p>Hold the button for 2 seconds to restart the Pi. The hold stops accidental taps. Booting from a USB drive takes a minute or two, and the app reconnects on its own.</p>`],
  settings: ["Settings", `<p>Settings are saved on the Pi, not in the browser, so every device sees the same layout. Refresh sets how often live numbers update. Faster updates use slightly more phone battery and data.</p>`],
  smart: ["Drive health (SMART)", `<p>Hard drives and SSDs track their own condition with <b>SMART</b> (Self-Monitoring, Analysis and Reporting Technology). Orbit reads it with <code>smartctl</code> on a schedule. A tightly limited sudo rule allows only that one read-only command.</p>
<p><b>Reallocated</b>, <b>pending</b> and <b>uncorrectable</b> sectors are areas of the disk that failed or are about to fail. Zero is ideal. A count that keeps rising means the drive is wearing out and should be backed up and replaced. <b>CRC errors</b> are data transfer errors, usually from a bad cable or USB adapter, not the disk.</p>
<p>Some USB enclosures don't pass SMART data through, so those drives show N/A. An alert fires on a failed health check, new bad sectors, or high drive temperature.</p>`],
  internet: ["Internet monitor", `<p>Every 30 seconds the Pi sends a <b>ping</b> (an ICMP echo request) to two public DNS servers, Cloudflare 1.1.1.1 and Google 8.8.8.8. If either replies, the connection is up. <b>Latency</b> is the round-trip time in milliseconds.</p>
<p>Three failed checks in a row count as an outage. You get an alert when it starts and when service comes back. Uptime percentages are calculated from the stored checks, which are kept for 8 days.</p>`],
  speed: ["Speed test", `<p>Measures the Pi's own connection by downloading about 20 MB from and uploading about 5 MB to Cloudflare's speed-test servers, timing each transfer. Results are in megabits per second (Mbps).</p>
<p>A wired Pi measures close to the internet plan's speed. Over Wi-Fi the result is also limited by signal strength.</p>`],
  devices: ["Network radar", `<p>Every few minutes the Pi pings each address on the local network. It then reads the kernel's <b>ARP/neighbour table</b>, the list of IP addresses mapped to hardware <b>MAC addresses</b> for devices that answered.</p>
<p>The manufacturer is looked up from the first half of the MAC address (the OUI, assigned by the IEEE). "Private address" means a phone or tablet using a randomized Wi-Fi MAC for privacy.</p>
<p>Devices found on the first scan are marked trusted. Any new device after that is flagged and triggers an alert. Tap a name to rename it, ✓ to trust it, or ✕ to forget it. The radar only observes and doesn't block or change other devices.</p>`],
  money: ["Money & traffic", `<p><b>Two income sources.</b> Every "View" button on the price site is an <b>eBay Partner Network</b> affiliate link, and every model page has a "Compare new on Amazon" button carrying your <b>Amazon Associates</b> tracking ID. When a visitor buys after clicking, that store pays a commission. The price is the same for the buyer.</p>
<p><b>Traffic</b> comes from the web server's access log, which records each page request. To count unique visitors without storing anyone's IP address, Orbit keeps only a one-way hash that changes daily. Known bots and crawlers are filtered out.</p>
<p><b>Clicks:</b> when a visitor taps an eBay or Amazon button, the site sends a tiny tracking request (<code>/c</code>), so you can see which products and which store get interest. <b>Clicks by page type</b> shows which kind of page sends buyers: model pages, buying guides, comparisons, the weekly report and so on. Write more of whatever works.</p>
<p><b>Earnings:</b> neither program offers a live earnings feed, so reports are imported. For eBay, download the <i>Transaction Detail Report</i> from the EPN portal. For Amazon, open Associates Central → Reports, choose <i>Earnings</i> and download the CSV. Tap Import and pick either file: Orbit detects which store it came from, skips duplicates and sends a "Money made" notification.</p>
<p><b>Amazon's 180-day rule:</b> a new Associates account must refer 3 qualifying sales within 180 days of signing up, or Amazon closes it. The orange bar tracks progress, and you get reminders at 60, 30 and 7 days left.</p>`],
  push: ["Push notifications", `<p>Orbit sends notifications with the <b>Web Push</b> standard. The phone registers with its platform's push service (Apple's, on iPhone), and the Pi sends each message there for delivery.</p>
<p>Each message is encrypted with keys only the subscribed device holds, so the push service relays it without being able to read it. The Pi proves it's the sender with a signed <b>VAPID</b> key.</p>
<p>On iPhone, push only works from the Home Screen app (iOS 16.4 or later). Open Orbit from its icon, tap Enable and allow notifications. Each device is subscribed separately, and expired subscriptions are removed automatically.</p>`],
  rules: ["Alert rules", `<p>A background watcher on the Pi checks every rule about every 30 seconds. Each rule can be turned on or off and its threshold changed, and changes save right away.</p>
<p>Cooldowns stop an ongoing problem from sending repeated notifications. <span class="lvl critical"></span>Critical alerts (power, drive failure, outages) still come through during quiet hours.</p>`],
  watchlist: ["Deal watchlist", `<p>Choose a model and the maximum price you'd pay, including shipping. After each price update, any listing from a trusted seller at or below that price sends a notification with a direct link. Each listing alerts only once.</p>`],
  quiet: ["Quiet hours", `<p>During quiet hours, info and warning alerts are still saved to History but don't make a sound or appear on the phone. Critical alerts always come through.</p>`],
  schedule: ["Schedule", `<p>Sets how often the heavier background checks run. Device scans ping the whole local network. Speed tests use about 25 MB of data each. Drive health checks wake sleeping drives. The defaults balance freshness against load.</p>`],
  history: ["History", `<p>The most recent 300 alerts, newest first. "Pushed" means a notification was delivered to at least one device. "Logged only" means it was recorded but not sent, because of quiet hours or no subscribed devices.</p>`],
  logs: ["Live logs", `<p>Recent output from a service, read from the systemd <b>journal</b> with <code>journalctl</code>, or from a container with <code>docker logs</code>. Logs are the first place to look when something fails.</p>
<p>Only known services and containers can be read. FOLLOW refreshes every 3 seconds and keeps the newest lines in view.</p>`],
  faceid: ["Face ID", `<p>Adds a <b>passkey</b> (WebAuthn), a cryptographic key pair whose private half stays in the phone's Secure Enclave and is unlocked by Face ID. The Pi keeps only the public key.</p>
<p>Once it's set up, risky actions ask for Face ID first: reboot, stopping services, going public and updating. The phone signs a one-time challenge from the Pi, and the Pi checks the signature before allowing the action. One approval lasts 5 minutes.</p>
<p>This is a second layer on top of the Tailscale login check.</p>`],
  sites: ["Website monitor", `<p>Every few minutes the Pi requests each website like a browser would and records the <b>HTTP status code</b> (200 means OK, 4xx/5xx means an error) and how long the response took.</p>
<p>For HTTPS sites it also reads the site's <b>TLS certificate</b>, the file that proves the site's identity and enables encryption, and shows how many days until it expires. An expired certificate makes browsers show a security warning.</p>
<p>Two failed checks in a row send a "down" alert, and another when it recovers. The checks run from your home connection, so if your internet is down every site will look down too. The Internet panel shows when that happens.</p>`],
  security: ["Security autopilot", `<p><b>Automatic updates:</b> <code>unattended-upgrades</code> installs security patches from Debian every day without asking, which closes known holes quickly. Other updates are listed so you can install them with one tap.</p>
<p><b>Restart:</b> some updates, mainly the Linux kernel, only take effect after a reboot. Orbit tells you when one is needed.</p>
<p><b>Admin ports:</b> a firewall rule (<code>iptables</code>) blocks Portainer, Cockpit, Glances and the raw site port from your home network, so only devices on your Tailscale network can reach them.</p>
<p><b>SSH:</b> every successful remote login is reported, and repeated failed logins (someone guessing passwords) trigger an alert.</p>
<p><b>Site probing:</b> bots constantly scan public websites for files like <code>/wp-admin</code> or <code>/.env</code>. The price site is plain static HTML with no login, database or scripts on the server, so those scans find nothing. Orbit counts them and alerts on heavy scanning.</p>`],
  ebaykeys: ["eBay API keys", `<p>The <b>Production</b> keyset from developer.ebay.com → Application Keys. The <b>App ID</b> identifies the app and the <b>Cert ID</b> is its password. Orbit sends both to eBay to check they work before saving, and stores them only on the Pi in a file only the Pi's user can read. They're never shown again.</p>
<p>The keys let the Pi read public listings through eBay's official Browse API. They can't buy, sell or see anyone's account.</p>`],
  discordint: ["Discord", `<p><b>Invite link:</b> paste your server's permanent invite (Server menu → Invite People → Edit invite link → Expire after: Never). It's public, so it's safe to show on the site. It appears as "Join the deals Discord" on every page, and Orbit uses it to count members and online users through Discord's public invite lookup.</p>
<p><b>Channel webhooks:</b> each deals channel gets its own webhook (Edit Channel → Integrations → Webhooks → New Webhook → Copy Webhook URL). Deals go to their category's channel, and anything without a channel goes to #deals (main). The weekly report goes to #market-report. Webhook URLs work like passwords. They're stored only on the Pi and never shown again.</p>`],
  newsletterint: ["Price-drop emails", `<p>Visitors type their email into a small form on the site, and the form sends it straight to your newsletter service (for example Buttondown, free up to 100 subscribers). Nothing is stored on the Pi. In Buttondown, find Settings → Embedding and copy the form's action URL (it looks like https://buttondown.com/api/emails/embed-subscribe/yourname), then paste it here. Each signup is tagged with the product page it came from.</p>`],
  integrations: ["Integrations", `<p>Every outside service in one list: <b>ON</b> means connected and working, <b>CHECK</b> means connected but something needs attention, and <b>OFF</b> means not set up. ↗ opens that service's dashboard, and TEST runs a live check.</p>
<p><b>Discord deal bot:</b> a <b>webhook</b> is a private address that lets a program post into one Discord channel without a bot account. After each price update, the Pi posts new deals there with your affiliate links. Paste the webhook URL here and Orbit checks it by sending a test message.</p>
<p>The URL is stored only on the Pi, in a settings file only the Pi's user can read. Anyone with the URL could post to the channel, so keep it private. Delete the webhook in Discord to revoke it.</p>
<p><b>Amazon Associates</b> and the <b>site address</b> come from the same settings file and are used when the site is rebuilt.</p>`],
  funnel: ["Revenue funnel", `<p>How visitors turn into money. <b>Visitors</b> are unique people on the price site. <b>Clicks</b> are taps on an eBay "View" button or an Amazon button. <b>Sales</b> and <b>earned</b> come from the eBay and Amazon earnings reports you import.</p>
<p>The <b>click rate</b> is clicks divided by visitors. <b>Per visitor</b> is earnings divided by visitors, the number to grow.</p>
<p>The table matches each commission to a tracked model by its product name, so you can see which models actually earn and add similar ones. Purchases of other items show as "Other items". With an affiliate link, buying anything on eBay or Amazon after the click can pay you.</p>`],
  widget: ["iPhone widget", `<p>Shows Pi health, internet status, today's visitors, clicks and earnings on your Home Screen.</p>
<p><b>Setup:</b> 1) Install the free <b>Scriptable</b> app from the App Store. 2) Tap <b>Copy widget script</b> here. 3) In Scriptable, tap <b>+</b>, paste, and name it "Orbit". 4) Long-press the Home Screen → <b>+</b> → Scriptable → pick small or medium → <b>Add Widget</b>. 5) Long-press the new widget → <b>Edit Widget</b> → Script: <b>Orbit</b>.</p>
<p><b>Security:</b> the widget calls a read-only address that only answers over your Tailscale network, and only with the widget key built into the script. <b>New widget key</b> cancels the old one, which helps if the script is ever shared by mistake. Tapping the widget opens Orbit. It refreshes about every 15 minutes (iOS decides the exact timing).</p>`],
  identity: ["Identity & security", `<p>Every request reaches the Pi through Tailscale, which attaches the verified identity of the signed-in user. Orbit only accepts the owner's account. Requests that change anything also need a special header, which blocks cross-site request forgery from other web pages.</p>
<p>The app isn't exposed to the public internet or the local network. Only the owner's devices on the tailnet can reach it.</p>`],
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
const ago = t => { if (!t) return "never"; const s = Date.now() / 1000 - t; if (Math.abs(s) < 60) return "just now"; return s < 0 ? "in " + fmtUp(-s) : fmtUp(s) + " ago"; };
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
/* Live disk I/O panel, shared by the Pi and themachine tabs. pfx = "" (Pi) or "machine-". */
function renderIO(pfx, io, rd, wr, names = {}) {
  const g = id => document.getElementById(pfx + id);
  if (!g("ioRead")) return;
  io = io || {};
  g("ioRead").textContent = fmtRate(io.read || 0);
  g("ioWrite").textContent = fmtRate(io.write || 0);
  const disks = io.disks || [];
  const busy = disks.reduce((m, x) => Math.max(m, x.busy || 0), 0);
  g("ioBusy").textContent = disks.length ? `busiest ${Math.round(busy)}%` : "live";
  if (g("ioSpark").offsetParent) spark(g("ioSpark"), [{ data: rd || [], color: accent() }, { data: wr || [], color: "#ff3df2" }]);
  g("ioDisks").innerHTML = disks.map(x => `<div class="row"><div class="main"><div class="name">${esc(names[x.dev] || x.dev)}</div><div class="meta">/dev/${esc(x.dev)} · ${Math.round(x.busy || 0)}% busy</div></div><div class="num">▼ ${fmtRate(x.read)}<div class="meta">▲ ${fmtRate(x.write)}</div></div></div>`).join("") || '<div class="note">Measuring…</div>';
}
function miniSpark(data) {
  if (!data || data.length < 2) return "";
  const min = Math.min(...data), max = Math.max(...data), r = max - min || 1;
  const pts = data.map((v, i) => `${(i / (data.length - 1) * 64).toFixed(1)},${(20 - (v - min) / r * 18).toFixed(1)}`).join(" ");
  const up = data.at(-1) > data[0];
  return `<svg class="sparkmini" viewBox="0 0 64 22"><polyline points="${pts}" fill="none" stroke="${up ? "var(--bad)" : "var(--good)"}" stroke-width="1.6"/></svg>`;
}

/* ---------------- live stream ---------------- */
const hist = { cpu: [], rx: [], tx: [], rd: [], wr: [] };
function onLive(d) {
  $("#host").textContent = "by Micah";
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
  hist.rd.push(d.io?.read || 0); hist.wr.push(d.io?.write || 0);
  for (const k in hist) hist[k] = hist[k].slice(-120);
  if ($("#cpuSpark").offsetParent) spark($("#cpuSpark"), [{ data: hist.cpu, color: accent() }], { max: 100 });
  if ($("#netSpark").offsetParent) spark($("#netSpark"), [{ data: hist.rx, color: accent() }, { data: hist.tx, color: "#ff3df2" }]);
  // Pi tab copies of the System wheel, plus swap, storage list and disk I/O
  $("#piCpuVal").textContent = Math.round(d.cpu); setRing($("#piCpuArc"), d.cpu / 100);
  $("#piTempVal").innerHTML = $("#tempVal").innerHTML; $("#piTempVal").style.color = $("#tempVal").style.color;
  $("#piClockVal").textContent = $("#clockVal").textContent; $("#piPowerVal").innerHTML = $("#powerVal").innerHTML;
  $("#piUpVal").textContent = fmtUp(d.uptime || 0);
  $("#piState").textContent = "LIVE · " + new Date((d.ts || Date.now() / 1000) * 1000).toLocaleTimeString();
  $("#memSwap").textContent = d.mem.swapTotal ? `swap ${fmtB(d.mem.swapTotal - (d.mem.swapFree || 0))} / ${fmtB(d.mem.swapTotal)}` : "no swap";
  $("#piStorage").innerHTML = (d.disks || []).map(x => `<div class="row"><div class="main"><div class="name">${x.mount === "/" ? "USB drive · system" : "Boot partition"}</div><div class="meta">${esc(x.mount)}</div></div><div class="num">${fmtB(x.free)} free<div class="meta">${fmtB(x.total)} total</div></div></div>`).join("");
  renderIO("", d.io, hist.rd, hist.wr, { sda: "USB drive" });
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
  if (!m || !m.ready) { note.textContent = (m && (m.note || m.error)) || "No data yet."; ["#gpu7", "#ram7"].forEach(s => $(s).textContent = "--"); $("#deals").innerHTML = ""; $("#catRows").innerHTML = ""; return; }
  note.textContent = (m.demo ? "DEMO DATA · " : "") + "updated " + esc(m.lastRun?.replace("T", " ").slice(0, 16) + " UTC");
  $("#siteLink").href = m.site;
  $("#gpu7").innerHTML = pct(m.gpu7); $("#ram7").innerHTML = pct(m.ram7);
  $("#gpu30").innerHTML = "30d " + pct(m.gpu30); $("#ram30").innerHTML = "30d " + pct(m.ram30);
  $("#deals").innerHTML = m.deals.length ? m.deals.map(d => `<a class="row" href="${esc(d.url)}" target="_blank" rel="noopener sponsored"><div class="main"><div class="name">${esc(d.model)}</div><div class="meta">${esc(d.title)}</div></div><div class="num">${money(d.total)}<div class="meta down">${d.under}% under</div></div></a>`).join("") : '<div class="note">No standout deals right now.</div>';
  const row = r => `<button class="row" data-model="${esc(r.id)}"><div class="main"><div class="name">${esc(r.name)}${r.signal ? ' <span class="signal">BUY</span>' : ""}</div><div class="meta">${r.perGb ? "$" + r.perGb.toFixed(2) + "/GB · " : ""}30d ${r.chg30 == null ? "--" : r.chg30.toFixed(1) + "%"}</div></div>${miniSpark(r.spark)}<div class="num">${money(r.median)}<div class="meta">${pct(r.chg7)}</div></div></button>`;
  $("#catRows").innerHTML = (m.cats || []).map(c => `<div class="panel" data-panel="market"><div class="ph"><span>${esc(c.label.toUpperCase())}</span><span class="mini">7d ${pct(c.chg7)}</span><button class="info" data-info-btn="rows" aria-label="How this works">i</button></div>
    <div class="list">${m.rows.filter(r => r.cat === c.id).map(row).join("")}</div></div>`).join("");
  if (settings) $$("#catRows [data-panel]").forEach(p => p.classList.toggle("hidden", settings.panels.market === false));
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
    ["Price site", s.market?.site && !s.market.site.includes("ts.net") && !s.market.site.includes("github.io") ? s.market.site.replace("https://", "") : ts.funnel ? "public · Funnel" : "private until go-live",
      s.market?.site && !s.market.site.includes("github.io") ? s.market.site + "/" : `https://${host}/`],
    ["Glances", "deep system monitor", `https://${host}:10000/`],
    ["Portainer", "Docker admin", `https://${ts.ip || host}:9443/`],
    ["Cockpit", "Pi admin & terminal", `https://${ts.ip || host}:9090/`],
    ["GitHub repo", "gpu-prices code", "https://github.com/micahbyrnes00-svg/gpu-prices"],
    ["eBay Partner", "affiliate earnings", "https://partnernetwork.ebay.com/"],
    ["Amazon Associates", "earnings & reports", "https://affiliate-program.amazon.com/home/reports"],
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
    let r = await post("api/action", { action, target });
    if (r.needFaceId && await faceUnlock()) r = await post("api/action", { action, target });
    toast((r.ok ? "✓ " : "✗ ") + (r.message || action));
  } catch { toast("✗ no response"); }
  btn?.classList.remove("busy");
  setTimeout(loadStatus, 1200);
}
document.addEventListener("click", e => {
  const info = e.target.closest("[data-info-btn]"); if (info) { openInfo(info.dataset.infoBtn); return; }
  if (e.target.closest("#sheet .close") || e.target.id === "sheet") { closeInfo(); return; }
  const tab = e.target.closest(".tabs button");
  if (tab) { $$(".tabs button").forEach(b => b.classList.toggle("on", b === tab)); $$(".view").forEach(v => v.classList.toggle("active", v.id === "view-" + tab.dataset.view)); scrollTo(0, 0); history.replaceState(null, "", "#" + tab.dataset.view); onView(tab.dataset.view); return; }
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
  $("#compact").checked = s.compact; $("#reduceMotion").checked = s.reduceMotion; $("#faceId").checked = s.faceId !== false;
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

/* ---------------- views ---------------- */
let cur = "system";
function onView(v) {
  cur = v;
  if (v === "network") { loadNetwork(); loadSites(); }
  if (v === "market") { loadStatus(); loadMoney(); loadFunnel(); if (!window._dcGrowth) loadIntegrations(); }
  if (v === "alerts") { loadAlerts(); $("#alertDot").classList.remove("on"); try { localStorage.setItem("seenAlert", String(Date.now() / 1000)); } catch { } }
  if (v === "control") { loadStatus(); fillLogSources(); loadSecurity(); }
  if (v === "settings") { loadStatus(); loadAlerts(); loadIntegrations(); }
}
const b64u = buf => btoa(String.fromCharCode(...new Uint8Array(buf))).replace(/\+/g, "-").replace(/\//g, "_").replace(/=+$/, "");
const b64uDec = s => Uint8Array.from(atob(s.replace(/-/g, "+").replace(/_/g, "/") + "===".slice((s.length + 3) % 4)), c => c.charCodeAt(0));
const when = t => t ? new Date(t * 1000).toLocaleString([], { month: "short", day: "numeric", hour: "numeric", minute: "2-digit" }) : "--";

/* ---------------- drive health ---------------- */
async function loadDisks() {
  let d; try { d = await api("api/disks"); } catch { return; }
  const el = $("#drives");
  if (!d.disks?.length) { el.innerHTML = `<div class="note">${d.ts ? "No USB/SATA drives found." : "First read runs a minute after start."}</div>`; return; }
  el.innerHTML = d.disks.map(x => {
    if (x.error) return `<div class="row"><div class="main"><div class="name">${esc(x.model || x.dev)}</div><div class="meta">${esc(x.dev)} · ${esc(x.size)}</div><div class="mini wrap">${esc(x.error)}</div></div><span class="badge">N/A</span></div>`;
    const bad = Object.entries(x.attrs || {}).filter(([k, v]) => v > 0 && k !== "Command timeouts");
    const ok = x.passed && !bad.length;
    return `<div class="row"><div class="main"><div class="name">${esc(x.model || x.dev)}</div><div class="meta">${esc(x.dev)} · ${esc(x.size)} · ${x.hours != null ? Math.round(x.hours / 24) + " days on" : ""}${x.cycles != null ? " · " + x.cycles + " starts" : ""}</div>
      ${bad.length ? `<div class="meta up">${bad.map(([k, v]) => esc(k) + " " + v).join(" · ")}</div>` : ""}</div>
      <div class="num">${x.temp != null ? x.temp + "°C" : ""}<div class="meta"><span class="badge ${ok ? "on" : x.passed ? "warn" : "off"}">${ok ? "HEALTHY" : x.passed ? "WATCH" : "FAILING"}</span></div></div></div>`;
  }).join("") + `<div class="mini" style="padding-top:6px">checked ${ago(d.ts)}</div>`;
}
$("#smartRefresh").addEventListener("click", async () => { await post("api/disks/refresh", {}); toast("Reading drives…"); setTimeout(loadDisks, 8000); });

/* ---------------- network radar ---------------- */
async function loadNetwork() {
  let n; try { n = await api("api/network"); } catch { return; }
  const st = $("#netState");
  st.textContent = n.online ? "ONLINE" : n.latencySeries.length ? "DOWN" : "--";
  st.className = "badge " + (n.online ? "on" : n.latencySeries.length ? "off" : "");
  $("#netLat").textContent = n.latency != null ? n.latency.toFixed(0) + " ms" : "--";
  $("#up24").textContent = n.uptime24 != null ? n.uptime24 + "%" : "--";
  $("#up7").textContent = n.uptime7 != null ? n.uptime7 + "%" : "--";
  spark($("#latSpark"), [{ data: n.latencySeries, color: accent() }]);
  $("#outages").innerHTML = n.outages.length ? n.outages.slice().reverse().map(o => `<div class="row"><div class="main"><div class="name">Outage</div><div class="meta">${when(o.start)}</div></div><div class="num">${o.end ? fmtUp(o.end - o.start) : "ongoing"}</div></div>`).join("")
    : `<div class="meta">No outages in the last 24h.</div>`;
  const last = n.speed.find(s => s.down != null);
  $("#spDown").textContent = last ? last.down + " Mb" : "--";
  $("#spUp").textContent = last ? last.up + " Mb" : "--";
  $("#spPing").textContent = last ? last.ping.toFixed(0) + " ms" : "--";
  $("#speedHist").innerHTML = n.speed.slice(0, 6).map(s => `<div class="row"><div class="main"><div class="meta">${when(s.ts)}</div></div><div class="num">${s.err ? '<span class="up">failed</span>' : `▼ ${s.down} · ▲ ${s.up} Mbps`}</div></div>`).join("");
  const devs = n.devices || [];
  const online = devs.filter(d => d.online).length, fresh = devs.filter(d => !d.trusted).length;
  $("#devNote").textContent = devs.length ? `${online} online · ${devs.length} known${fresh ? ` · ${fresh} new` : ""} · scanned ${ago(n.lastScan)}` : "First scan runs shortly after start. Tap SCAN to run now.";
  $("#devices").innerHTML = devs.map(d => `<div class="row dev ${d.trusted ? "" : "new"}" data-mac="${esc(d.mac)}">
    <div class="main"><div class="name"><input value="${esc(d.name || d.host || d.vendor || d.mac)}" data-rename aria-label="Device name"></div>
    <div class="meta">${esc(d.ip)} · ${esc((d.name || d.host) ? (d.vendor || d.mac) : d.mac)} · ${d.online ? "online" : "seen " + ago(d.last_seen)}</div></div>
    ${d.trusted ? `<span class="badge ${d.online ? "on" : ""}">${d.online ? "ON" : "OFF"}</span>` : `<button class="btn go" data-trust>✓</button>`}
    ${d.online ? "" : `<button class="btn" data-wake aria-label="Wake">⏻</button>`}<button class="btn" data-forget>✕</button></div>`).join("");
}
document.addEventListener("change", async e => {
  const r = e.target.closest("[data-rename]"); if (!r) return;
  await post("api/network/device", { mac: r.closest("[data-mac]").dataset.mac, name: r.value.trim() }); toast("Saved");
});
document.addEventListener("click", async e => {
  const row = e.target.closest(".dev[data-mac]"); if (!row) return;
  if (e.target.closest("[data-trust]")) { await post("api/network/device", { mac: row.dataset.mac, trusted: true }); loadNetwork(); }
  if (e.target.closest("[data-forget]")) { await post("api/network/forget", { mac: row.dataset.mac }); loadNetwork(); }
});
$("#scanBtn").addEventListener("click", async e => { e.target.classList.add("on"); toast((await post("api/network/scan", {})).message); setTimeout(() => { e.target.classList.remove("on"); loadNetwork(); }, 15000); });
$("#speedBtn").addEventListener("click", async e => { e.target.textContent = "…"; toast((await post("api/network/speedtest", {})).message); setTimeout(() => { e.target.textContent = "RUN"; loadNetwork(); }, 35000); });

/* ---------------- money ---------------- */
async function loadMoney() {
  let m; try { m = await api("api/money"); } catch { return; }
  const usd = v => "$" + (v || 0).toFixed(2);
  $("#earnTot").textContent = usd(m.earnings.total); $("#earn30").textContent = usd(m.earnings.last30);
  $("#clicks7").textContent = m.clicks7; $("#vis24").textContent = m.today.u || 0; $("#vis7").textContent = m.week.u || 0; $("#views7").textContent = m.week.v || 0;
  spark($("#visSpark"), [{ data: m.dailyVisitors.length ? m.dailyVisitors : [0, 0], color: accent() }]);
  $("#moneyNote").textContent = (m.logFound ? "" : "Traffic log appears once the site is public. ") + "Earnings imported " + ago(m.earnings.lastImport) + ".";
  const li = (rows, k, empty) => rows.length ? rows.map(r => `<div class="row"><div class="main"><div class="name">${esc(r[k] || "(direct)")}</div></div><div class="num">${r.n}</div></div>`).join("") : `<div class="meta">${empty}</div>`;
  $("#topPages").innerHTML = li(m.pages, "path", "No visits yet.");
  $("#topRefs").innerHTML = li(m.refs, "ref", "No referrers yet.");
  const PT = { model: "Model pages", category: "Category pages", guide: "Buying guides", compare: "Comparisons", report: "Market report", home: "Homepage", check: "Price checker", guides: "Guides index", page: "Other pages" };
  $("#clickPages").innerHTML = li((m.clicksByPage || []).map(r => ({ ...r, pt: PT[r.pt] || r.pt })), "pt", "No clicks yet.");
  $("#topClicked").innerHTML = li(m.clicked.map(c => ({ ...c, model: c.model.startsWith("amz:") ? "Amazon · " + c.model.slice(4) : "eBay · " + (c.model || "listing") })), "model", "No clicks yet.");
  $("#earnEbay").textContent = usd(m.earnings.ebay); $("#earnAmz").textContent = usd(m.earnings.amazon); $("#amzClicks").textContent = m.amazonClicks7 ?? 0;
  renderDcGrowth();
  const a = m.earnings.amazonStatus || {};
  $("#amzStatus").innerHTML = !a.tag ? `<div class="t"><span>Amazon Associates</span><span class="mini">not connected</span></div>` :
    `<div class="t"><span>Amazon Associates · ${esc(a.tag)}</span><span class="mini">${a.sales >= 3 ? "qualified" : a.daysLeft != null ? a.daysLeft + " days left" : ""}</span></div>
     <div class="pips">${[0, 1, 2].map(i => `<i class="${i < a.sales ? "on" : ""}"></i>`).join("")}</div>
     <div class="mini">${a.sales >= 3 ? "3 qualifying sales reached. Account stays open." : `${Math.min(a.sales, 3)} of 3 qualifying sales needed${a.deadline ? " by " + new Date(a.deadline * 1000).toLocaleDateString([], { month: "short", day: "numeric", year: "numeric" }) : ""}`}</div>`;
  $("#earnRecent").innerHTML = m.earnings.recent.length ? m.earnings.recent.map(r => `<div class="row"><div class="main"><div class="name"><span class="src ${esc(r.source || "ebay")}">${r.source === "amazon" ? "AMZ" : "EBAY"}</span>${esc(r.item || "Commission")}</div><div class="meta">${when(r.ts)}</div></div><div class="num down">${usd(r.amount)}</div></div>`).join("") : `<div class="meta">No commissions imported yet.</div>`;
}
$("#tdrFile").addEventListener("change", async e => {
  const f = e.target.files[0]; if (!f) return;
  const r = await post("api/money/import", { csv: await f.text() }); e.target.value = "";
  toast((r.ok ? "✓ " : "✗ ") + r.message); loadMoney();
});

/* ---------------- alerts + push ---------------- */
let alertCfg = null, vapid = null, passkeys = [];
async function loadAlerts() {
  let a; try { a = await api("api/alerts"); } catch { return; }
  alertCfg = a.config; vapid = a.vapid; passkeys = a.passkeys;
  renderPush(a.subs); renderRules(); renderWatch(); renderFace();
  const q = alertCfg.quiet, hrs = [...Array(24).keys()].map(h => `<option value="${h}">${String(h).padStart(2, "0")}:00</option>`).join("");
  $("#quietOn").checked = q.enabled;
  if (!$("#quietStart").options.length) { $("#quietStart").innerHTML = hrs; $("#quietEnd").innerHTML = hrs; }
  $("#quietStart").value = q.start; $("#quietEnd").value = q.end;
  for (const k in alertCfg.schedule) { const i = $("#sch_" + k); if (i && document.activeElement !== i) i.value = alertCfg.schedule[k]; }
  $("#alertHist").innerHTML = a.history.length ? a.history.map(h => `<a class="row" href="${esc(h.url || "#")}"><div class="main"><div class="name"><span class="lvl ${esc(h.level)}"></span>${esc(h.title)}</div><div class="meta">${esc(h.body)}</div></div><div class="num"><div class="meta">${when(h.ts)}</div><div class="meta">${h.pushed ? "pushed" : "logged only"}</div></div></a>`).join("")
    : `<div class="meta">No alerts yet.</div>`;
  let seen = 0; try { seen = +localStorage.getItem("seenAlert") || 0; } catch { }
  $("#alertDot").classList.toggle("on", cur !== "alerts" && a.history.some(h => h.ts > seen && h.level !== "info"));
}
async function pushSub() { const r = await navigator.serviceWorker?.ready; return r?.pushManager ? r.pushManager.getSubscription() : null; }
async function renderPush(count) {
  const st = $("#pushState"), note = $("#pushNote"), btn = $("#pushBtnText");
  const standalone = matchMedia("(display-mode: standalone)").matches || navigator.standalone;
  if (!("PushManager" in window) || !("serviceWorker" in navigator)) {
    st.textContent = "UNAVAILABLE"; st.className = "badge off";
    note.textContent = standalone ? "This browser doesn't support Web Push." : "Open Orbit from its Home Screen icon to enable notifications.";
    $("#pushBtn").disabled = true; return;
  }
  const sub = await pushSub();
  const on = !!sub && Notification.permission === "granted";
  st.textContent = on ? "ON" : Notification.permission === "denied" ? "BLOCKED" : "OFF";
  st.className = "badge " + (on ? "on" : Notification.permission === "denied" ? "off" : "");
  btn.textContent = on ? "Disable on this device" : "Enable on this device";
  $("#pushBtn").disabled = false;
  note.textContent = Notification.permission === "denied" ? "Notifications are blocked. Turn them on in iPhone Settings → Notifications → Orbit."
    : `${count} device${count === 1 ? "" : "s"} subscribed.`;
}
$("#pushBtn").addEventListener("click", async () => {
  try {
    const reg = await navigator.serviceWorker.ready, sub = await reg.pushManager.getSubscription();
    if (sub && Notification.permission === "granted") {
      await post("api/push/unsubscribe", { endpoint: sub.endpoint }); await sub.unsubscribe(); toast("Notifications off"); return loadAlerts();
    }
    if (await Notification.requestPermission() !== "granted") { toast("Permission not granted"); return loadAlerts(); }
    const s = await reg.pushManager.subscribe({ userVisibleOnly: true, applicationServerKey: b64uDec(vapid) });
    const r = await post("api/push/subscribe", s.toJSON());
    toast(r.ok ? "✓ Notifications on" : "✗ " + (r.error || "failed")); loadAlerts();
  } catch (err) { toast("✗ " + err.message); }
});
$("#pushTest").addEventListener("click", async () => { const r = await post("api/push/test", {}); toast(r.ok ? "✓ Test sent" : "✗ No subscribed devices answered"); setTimeout(loadAlerts, 1500); });
$("#alertsClear").addEventListener("click", async () => { await post("api/alerts/clear", {}); loadAlerts(); });

function renderRules() {
  const el = $("#rules");
  if (el.contains(document.activeElement)) return;
  const unit = { limit: k => k === "disk_full" ? "%" : "°C", temp: () => "°C", visitors: () => "visitors", down: () => "Mbps", hour: () => ":00",
    ms: () => "ms", days: () => "days", fails: () => "fails", hits: () => "errors" };
  el.innerHTML = Object.entries(alertCfg.rules).map(([k, r]) => `<div class="rule" data-rule="${k}">
    <label class="tog"><span class="rn"><span class="lvl ${r.level}"></span>${esc(r.label)}</span><input type="checkbox" data-ron ${r.enabled ? "checked" : ""}></label>
    <div class="rd">${esc(r.desc)}</div>
    ${Object.entries(r.params).map(([p, v]) => `<div class="rp"><span>${p === "limit" || p === "temp" ? "Limit" : p === "hour" ? "Send at" : p === "visitors" || p === "fails" || p === "hits" ? "Threshold" : p === "days" ? "Within" : p === "ms" ? "Slower than" : "Below"}</span><input type="number" data-rparam="${p}" value="${v}"><span>${unit[p] ? unit[p](k) : ""}</span></div>`).join("")}
  </div>`).join("");
}
document.addEventListener("change", async e => {
  const rule = e.target.closest("[data-rule]");
  if (rule) {
    const k = rule.dataset.rule, patch = {};
    if (e.target.matches("[data-ron]")) patch.enabled = e.target.checked;
    if (e.target.dataset.rparam) patch.params = { [e.target.dataset.rparam]: +e.target.value };
    alertCfg = await post("api/alerts/config", { rules: { [k]: patch } }); toast("Saved"); return;
  }
  if (["quietOn", "quietStart", "quietEnd"].includes(e.target.id)) {
    alertCfg = await post("api/alerts/config", { quiet: { enabled: $("#quietOn").checked, start: +$("#quietStart").value, end: +$("#quietEnd").value } }); toast("Saved");
  }
  if (e.target.id?.startsWith("sch_")) { alertCfg = await post("api/alerts/config", { schedule: { [e.target.id.slice(4)]: +e.target.value } }); toast("Saved"); }
  if (e.target.id === "faceId") saveSettings({ faceId: e.target.checked });
});

function renderWatch() {
  const models = status?.market?.models || [];
  const sel = $("#watchModel");
  if (sel.options.length !== Math.max(models.length, 1)) sel.innerHTML = models.map(m => `<option value="${esc(m.id)}">${esc(m.name)}</option>`).join("") || "<option value=''>Prices load after the first update</option>";
  const name = id => models.find(m => m.id === id)?.name || id;
  $("#watch").innerHTML = alertCfg.watchlist.length ? alertCfg.watchlist.map((w, i) => `<div class="row"><div class="main"><div class="name">${esc(name(w.model))}</div><div class="meta">alert at or under</div></div><div class="num">$${w.max}</div><button class="btn" data-wdel="${i}">✕</button></div>`).join("")
    : `<div class="meta">Nothing watched yet.</div>`;
}
$("#watchAdd").addEventListener("click", async () => {
  const model = $("#watchModel").value, max = parseFloat($("#watchMax").value);
  if (!model || !(max > 0)) return toast("Pick a model and a price");
  alertCfg = await post("api/alerts/config", { watchlist: [...alertCfg.watchlist, { model, max }] }); $("#watchMax").value = ""; renderWatch(); toast("Watching");
});
document.addEventListener("click", async e => {
  const d = e.target.closest("[data-wdel]"); if (!d) return;
  const wl = alertCfg.watchlist.filter((_, i) => i !== +d.dataset.wdel);
  alertCfg = await post("api/alerts/config", { watchlist: wl }); renderWatch();
});

/* ---------------- logs ---------------- */
let followT = null;
function fillLogSources() {
  const sel = $("#logSrc"), prev = sel.value;
  const units = (status?.services || []).map(u => u.unit), ctrs = (status?.containers || []).map(c => c.name);
  const opts = [...new Set([...units, "gpu-prices.service", "pi-cloud-backup.service"])].map(u => `<option value="unit:${esc(u)}">${esc(u)}</option>`).join("")
    + ctrs.map(c => `<option value="container:${esc(c)}">🐳 ${esc(c)}</option>`).join("");
  if (sel.innerHTML !== opts) { sel.innerHTML = opts; if (prev) sel.value = prev; }
}
async function loadLogs() {
  const [k, v] = ($("#logSrc").value || "").split(/:(.*)/s); if (!v) return;
  const out = $("#logOut"), atEnd = out.scrollTop + out.clientHeight >= out.scrollHeight - 20;
  try { const r = await api(`api/logs?${k}=${encodeURIComponent(v)}&n=300`); out.textContent = r.text ?? r.error ?? ""; } catch { out.textContent = "No response."; }
  if (atEnd) out.scrollTop = out.scrollHeight;
}
$("#logLoad").addEventListener("click", () => { loadLogs().then(() => { const o = $("#logOut"); o.scrollTop = o.scrollHeight; }); });
$("#logSrc").addEventListener("change", loadLogs);
$("#logFollow").addEventListener("click", e => {
  clearInterval(followT); followT = null;
  if (e.target.classList.toggle("on")) { loadLogs(); followT = setInterval(() => cur === "control" && !document.hidden && loadLogs(), 3000); }
});

/* ---------------- Face ID (passkey) ---------------- */
function renderFace() {
  const on = passkeys.length > 0;
  $("#faceState").textContent = on ? "ON" : "OFF"; $("#faceState").className = "badge " + (on ? "on" : "");
  $("#faceNote").textContent = !window.PublicKeyCredential ? "This browser doesn't support passkeys." : on ? `Passkey set up ${when(passkeys[0].created)}.` : "Not set up. Power actions work without Face ID.";
  $("#faceEnroll").style.display = on ? "none" : ""; $("#faceRemove").style.display = on ? "" : "none";
  if (settings) $("#faceId").checked = settings.faceId !== false;
}
$("#faceEnroll").addEventListener("click", async () => {
  try {
    const o = await api("api/auth/options");
    const cred = await navigator.credentials.create({ publicKey: {
      challenge: b64uDec(o.challenge), rp: { id: o.rpId, name: "Orbit" },
      user: { id: crypto.getRandomValues(new Uint8Array(16)), name: "owner@orbit", displayName: "Orbit owner" },
      pubKeyCredParams: [{ type: "public-key", alg: -7 }], attestation: "none", timeout: 60000,
      authenticatorSelection: { authenticatorAttachment: "platform", userVerification: "required", residentKey: "preferred" } } });
    const r = await post("api/auth/register", { clientDataJSON: b64u(cred.response.clientDataJSON), attestationObject: b64u(cred.response.attestationObject) });
    toast(r.ok ? "✓ Face ID set up" : "✗ " + r.message); loadAlerts();
  } catch (err) { toast("✗ " + err.message); }
});
async function faceUnlock() {
  try {
    const o = await api("api/auth/options");
    const a = await navigator.credentials.get({ publicKey: { challenge: b64uDec(o.challenge), rpId: o.rpId, userVerification: "required", timeout: 60000,
      allowCredentials: o.credentials.map(id => ({ type: "public-key", id: b64uDec(id) })) } });
    const r = await post("api/auth/verify", { id: b64u(a.rawId), clientDataJSON: b64u(a.response.clientDataJSON),
      authenticatorData: b64u(a.response.authenticatorData), signature: b64u(a.response.signature) });
    if (!r.ok) { toast("✗ " + r.message); return false; }
    unlockTok = r.token; unlockExp = Date.now() + (r.seconds - 10) * 1000; return true;
  } catch (err) { toast("✗ Face ID cancelled"); return false; }
}
$("#faceRemove").addEventListener("click", async () => {
  let r = await post("api/auth/remove", {});
  if (r.needFaceId && await faceUnlock()) r = await post("api/auth/remove", {});
  toast(r.ok ? "Face ID removed" : "✗ Not removed"); loadAlerts();
});
/* ---------------- website monitor ---------------- */
let siteList = [];
async function loadSites() {
  let d; try { d = await api("api/sites"); } catch { return; }
  siteList = d.sites.map(s => ({ url: s.url, name: s.name }));
  $("#sites").innerHTML = d.sites.length ? d.sites.map((s, i) => {
    const l = s.last, up = l ? l.ok : null;
    const cert = l?.certDays != null ? `cert ${Math.floor(l.certDays)}d` : "";
    return `<div class="row"><div class="main"><div class="name">${esc(s.name)}</div>
      <div class="meta">${l ? (l.ok ? l.ms + " ms" : esc(l.code ? "HTTP " + l.code : l.err || "no response")) : "checking…"}${s.uptime24 != null ? " · " + s.uptime24 + "% 24h" : ""}${cert ? " · " + cert : ""}</div></div>
      ${miniSpark(s.series.length > 1 ? s.series : null)}
      <span class="badge ${up == null ? "" : up ? "on" : "off"}">${up == null ? "--" : up ? "UP" : "DOWN"}</span>
      <button class="btn" data-sdel="${i}" aria-label="Remove">✕</button></div>`;
  }).join("") : `<div class="meta">Add a website to watch its uptime, speed and certificate.</div>`;
}
$("#siteAdd").addEventListener("click", async () => {
  const v = $("#siteUrl").value.trim(); if (!v) return;
  const r = await post("api/sites", { sites: [...siteList, { url: v }] }); $("#siteUrl").value = "";
  toast(r.ok ? "Watching " + v : "✗ failed"); setTimeout(loadSites, 600); setTimeout(loadSites, 8000);
});
document.addEventListener("click", async e => {
  const d = e.target.closest("[data-sdel]"); if (!d) return;
  await post("api/sites", { sites: siteList.filter((_, i) => i !== +d.dataset.sdel) }); loadSites();
});
$("#sitesCheck").addEventListener("click", async () => { await post("api/sites/check", {}); toast("Checking…"); setTimeout(loadSites, 6000); });

/* ---------------- wake-on-LAN ---------------- */
document.addEventListener("click", async e => {
  const w = e.target.closest("[data-wake]"); if (!w) return;
  const r = await post("api/network/wake", { mac: w.closest("[data-mac]").dataset.mac });
  toast((r.ok ? "⏻ " : "✗ ") + r.message);
});

/* ---------------- security ---------------- */
async function loadSecurity() {
  let s; try { s = await api("api/security"); } catch { return; }
  const row = (name, meta, badge, cls) => `<div class="row"><div class="main"><div class="name">${name}</div><div class="meta">${meta}</div></div><span class="badge ${cls}">${badge}</span></div>`;
  const u = s.updates;
  const open = s.openPorts.filter(p => !p.blocked).map(p => p.port);
  $("#security").innerHTML = [
    row("Automatic security updates", s.auto.lastRun ? "last run " + ago(s.auto.lastRun) : "daily, via unattended-upgrades", s.auto.enabled ? "ON" : "OFF", s.auto.enabled ? "on" : "off"),
    row("Pending updates", u ? `${u.pending} waiting · ${u.security} security · checked ${ago(u.ts)}` : "first check runs shortly", u ? (u.pending ? u.pending : "NONE") : "--", u && u.security ? "warn" : u ? "on" : ""),
    row("Restart", s.reboot ? "needed for: " + esc(s.rebootPkgs.join(", ") || "updated packages") : "not needed", s.reboot ? "NEEDED" : "OK", s.reboot ? "warn" : "on"),
    row("Admin ports from home network", s.lockdown ? "Portainer, Cockpit, Glances, site port: Tailscale only" : "lockdown not active", s.lockdown ? "BLOCKED" : "OPEN", s.lockdown ? "on" : "off"),
    row("Listening on all interfaces", esc(open.join(", ") || "none") + (open.length ? " (SSH, VNC and similar)" : ""), open.length, ""),
    row("SSH logins", s.sshOk.length ? `last: ${esc(s.sshOk[0].user)} from ${esc(s.sshOk[0].ip)} ${ago(s.sshOk[0].ts)}` : "none recorded yet", s.sshFail24 + " FAILED", s.sshFail24 ? "warn" : "on"),
    row("Site probing (24h)", s.probes24 ? `${s.probes24} error hits from ${s.probers24} visitors · ${esc(s.probePaths.slice(0, 3).map(p => p.path).join(" "))}` : "no suspicious requests", s.probes24 || "0", s.probes24 > 50 ? "warn" : "on"),
  ].join("");
}
$("#secCheck").addEventListener("click", async () => { await post("api/security/check", {}); toast("Checking for updates…"); setTimeout(loadSecurity, 15000); });
$("#secApply").addEventListener("click", e => runAction("apply_updates", "", e.target));

/* ---------------- price chart ---------------- */
let chartData = null, chartRange = 90;
async function openChart(id) {
  $("#sheetTitle").textContent = "Loading…"; $("#sheetBody").innerHTML = ""; $("#sheet").classList.add("open");
  try { chartData = await api("api/market/model?id=" + encodeURIComponent(id)); } catch { $("#sheetTitle").textContent = "No data"; return; }
  renderChart();
}
function renderChart() {
  const d = chartData; if (!d) return;
  $("#sheetTitle").textContent = d.name;
  if (!d.series?.length) { $("#sheetBody").innerHTML = "<p>No price history yet.</p>"; return; }
  const ser = chartRange ? d.series.slice(-chartRange) : d.series;
  const W = 340, H = 190, L = 40, R = 8, T = 10, B = 22;
  const vals = ser.flatMap(p => [p.p25, p.p75, p.median]);
  let lo = Math.min(...vals), hi = Math.max(...vals); const pad = (hi - lo) * .08 || 5; lo -= pad; hi += pad;
  const x = i => L + (ser.length < 2 ? (W - L - R) / 2 : i / (ser.length - 1) * (W - L - R)), y = v => T + (hi - v) / (hi - lo) * (H - T - B);
  const band = ser.map((p, i) => `${x(i)},${y(p.p75)}`).join(" ") + " " + ser.map((p, i) => `${x(i)},${y(p.p25)}`).reverse().join(" ");
  const line = ser.map((p, i) => `${x(i)},${y(p.median)}`).join(" ");
  const ticks = [lo + pad, (lo + hi) / 2, hi - pad].map(v => `<text x="2" y="${y(v) + 3}">$${Math.round(v)}</text><line x1="${L}" x2="${W - R}" y1="${y(v)}" y2="${y(v)}" stroke="var(--line)"/>`).join("");
  const low90 = `<line x1="${L}" x2="${W - R}" y1="${y(d.low90)}" y2="${y(d.low90)}" stroke="var(--good)" stroke-dasharray="3 4" opacity=".7"/>`;
  const dl = [ser[0], ser.at(-1)].map((p, k) => `<text x="${k ? W - R : L}" y="${H - 6}" text-anchor="${k ? "end" : "start"}">${p.day.slice(5)}</text>`).join("");
  const last = ser.at(-1);
  $("#sheetBody").innerHTML = `
    <div>${d.signal ? '<span class="signal">BUY SIGNAL · 90-DAY LOW</span>' : '<span class="mini">Typical used price, including shipping</span>'}</div>
    <div class="kv"><div><div class="k">NOW</div><div class="v">${money(d.current)}</div></div><div><div class="k">7D</div><div class="v">${pct(d.chg7)}</div></div><div><div class="k">30D</div><div class="v">${pct(d.chg30)}</div></div>
      <div><div class="k">90D LOW</div><div class="v down">${money(d.low90)}</div></div><div><div class="k">90D HIGH</div><div class="v up">${money(d.high90)}</div></div><div><div class="k">ALL-TIME LOW</div><div class="v">${money(d.lowAll)}</div></div></div>
    <svg class="chart" viewBox="0 0 ${W} ${H}" preserveAspectRatio="none" role="img" aria-label="Price history">${ticks}${low90}
      <polygon points="${band}" fill="var(--a)" opacity=".13"/><polyline points="${line}" fill="none" stroke="var(--a)" stroke-width="2.2" stroke-linejoin="round" vector-effect="non-scaling-stroke"/>
      <circle cx="${x(ser.length - 1)}" cy="${y(last.median)}" r="3.5" fill="var(--a)"/>${dl}</svg>
    <div class="mini">Line = median · band = middle 50% of listings · dashed = 90-day low</div>
    <div class="ranges">${[[30, "30D"], [90, "90D"], [365, "1Y"], [0, "ALL"]].map(([r, t]) => `<button class="btn ${r === chartRange ? "on" : ""}" data-range="${r}">${t}</button>`).join("")}</div>
    <div class="sub2">CHEAPEST TRUSTED LISTINGS</div>
    <div class="list">${d.listings.map(l => `<a class="row" href="${esc(l.url)}" target="_blank" rel="noopener sponsored"><div class="main"><div class="name">${esc(l.title)}</div><div class="meta">${(l.seller || 0).toFixed(1)}% seller feedback</div></div><div class="num">${money(l.total)}</div></a>`).join("") || '<div class="meta">None right now.</div>'}</div>
    <a class="btn wide" href="${esc(d.url)}" target="_blank" rel="noopener">OPEN ON SITE ↗</a>`;
}
document.addEventListener("click", e => {
  const r = e.target.closest("[data-range]"); if (r) { chartRange = +r.dataset.range; renderChart(); return; }
  const m = e.target.closest("[data-model]"); if (m) openChart(m.dataset.model);
});

/* ---------------- integrations ---------------- */
async function loadIntegrations() {
  let d; try { d = await api("api/integrations"); } catch { return; }
  const st = { on: ["ON", "on"], warn: ["CHECK", "warn"], off: ["OFF", ""] };
  $("#intList").innerHTML = d.items.map(i => `<div class="row"><div class="main"><div class="name">${esc(i.name)}</div><div class="meta wrapm">${esc(i.detail)}</div></div>
    ${i.test ? `<button class="btn" data-itest="${esc(i.id)}">TEST</button>` : ""}
    ${i.link ? `<a class="btn" href="${esc(i.link)}" target="_blank" rel="noopener" aria-label="Open ${esc(i.name)}">↗</a>` : ""}
    <span class="badge ${st[i.state][1]}">${st[i.state][0]}</span></div>`).join("");
  const eb = d.items.find(i => i.id === "ebay");
  const gl = d.golive, keys = eb && eb.state !== "off";
  $("#goLive").style.display = keys && !(gl && gl.done) ? "" : "none";
  $("#goLive").textContent = gl && !gl.done ? "COLLECTING PRICES… (TAP TO RE-RUN)" : "GO LIVE WITH REAL PRICES";
  $("#ebNote").textContent = gl && gl.done ? "Live: prices update every 6 hours." : gl ? "First run started " + ago(gl.started) + ". You'll get a notification when the site is live." : keys ? "Keys saved. Tap Go live to collect real prices and switch the site over." : "Paste your Production keys from developer.ebay.com → Application Keys.";
  if (eb) { $("#ebState").textContent = eb.state === "off" ? "NOT SET" : "SAVED"; $("#ebState").className = "badge " + (eb.state === "off" ? "" : "on"); }
  const c = d.discordCounts;
  $("#dcCount").textContent = c && c.members != null ? `${c.members} MEMBERS` : "--";
  $("#dcCount").className = "badge " + (c && c.members != null ? "on" : "");
  if (document.activeElement !== $("#dcInvite")) $("#dcInvite").value = d.discordInvite ? "discord.gg/" + d.discordInvite : "";
  $("#dcHooks").innerHTML = d.discordHooks.map(h => `<div class="row" data-hook="${esc(h.key)}"><div class="main"><div class="name">${esc(h.label)}</div>
      <input type="password" autocomplete="off" placeholder="${h.set ? "Connected · paste to replace" : "Paste webhook URL"}" aria-label="Webhook for ${esc(h.label)}" class="hookin"></div>
      ${h.set ? `<button class="btn" data-htest>TEST</button>` : ""}<button class="btn go" data-hsave>SAVE</button><span class="badge ${h.set ? "on" : ""}">${h.set ? "ON" : "OFF"}</span></div>`).join("");
  window._dcGrowth = d.discordGrowth; renderDcGrowth();
}
function growthSpark(d) {
  if (!d || d.length < 2) return "";
  const lo = Math.min(...d), hi = Math.max(...d), r = hi - lo || 1;
  const pts = d.map((v, i) => `${(i / (d.length - 1) * 100).toFixed(1)},${(24 - (v - lo) / r * 20).toFixed(1)}`).join(" ");
  return `<svg class="sparkmini" viewBox="0 0 100 26" preserveAspectRatio="none"><polyline points="${pts}" fill="none" stroke="#7d8cff" stroke-width="1.6" vector-effect="non-scaling-stroke"/></svg>`;
}
function renderDcGrowth() {
  const g = window._dcGrowth, el = $("#dcGrowth"); if (!el) return;
  el.innerHTML = g ? `<div class="t"><span>Discord · ${g.members} members</span><span class="mini">${g.week >= 0 ? "+" : ""}${g.week} this week</span></div>${growthSpark(g.series)}` : `<div class="t"><span>Discord</span><span class="mini">add the invite in Settings</span></div>`;
}
$("#intRefresh").addEventListener("click", loadIntegrations);
document.addEventListener("click", async e => {
  const t = e.target.closest("[data-itest]");
  if (t) { t.textContent = "…"; const r = await post("api/integrations/test", { id: t.dataset.itest }); toast((r.ok ? "✓ " : "✗ ") + r.message); loadIntegrations(); return; }
  const row = e.target.closest("[data-hook]"); if (!row) return;
  const key = row.dataset.hook;
  if (e.target.closest("[data-htest]")) { const r = await post("api/integrations/test", { id: "discord", key }); toast((r.ok ? "✓ " : "✗ ") + r.message); }
  if (e.target.closest("[data-hsave]")) {
    const url = row.querySelector(".hookin").value.trim(); if (!url) return toast("Paste the webhook URL first");
    const r = await post("api/integrations/discord", { key, url }); toast((r.ok ? "✓ " : "✗ ") + r.message); if (r.ok) loadIntegrations();
  }
});
$("#dcInviteSave").addEventListener("click", async () => { const r = await post("api/integrations/invite", { code: $("#dcInvite").value.trim() }); toast((r.ok ? "✓ " : "✗ ") + r.message); loadIntegrations(); });
$("#ebSave").addEventListener("click", async () => {
  const id = $("#ebId").value.trim(), secret = $("#ebSec").value.trim();
  if (!id || !secret) return toast("Paste both the App ID and the Cert ID");
  $("#ebSave").textContent = "…";
  const r = await post("api/integrations/ebay", { id, secret }); $("#ebSave").textContent = "SAVE";
  toast((r.ok ? "✓ " : "✗ ") + r.message); if (r.ok) { $("#ebId").value = ""; $("#ebSec").value = ""; } loadIntegrations();
});
$("#goLive").addEventListener("click", e => runAction("go_live", "", e.target).then(() => setTimeout(loadIntegrations, 1500)));
$("#nlSave").addEventListener("click", async () => { const r = await post("api/integrations/newsletter", { url: $("#nlUrl").value.trim() }); toast((r.ok ? "✓ " : "✗ ") + r.message); $("#nlUrl").value = ""; loadIntegrations(); });

/* ---------------- Ask Orbit ---------------- */
const askHist = [];
const ASK_CHIPS = ["How is the Pi doing?", "Anything I should fix?", "Why did my last alert fire?", "How is the site making money?", "Explain these logs"];
function renderAsk() {
  const chat = askHist.map(m => `<div class="msg ${m.who}${m.wait ? " wait" : ""}">${esc(m.text)}</div>`).join("");
  const units = [...new Set([...(status?.services || []).map(u => u.unit), "gpu-prices.service", "pi-cloud-backup.service"])];
  const prev = $("#askSrc")?.value || "";
  $("#sheetBody").innerHTML = `${askHist.length ? "" : `<p class="mini" style="margin-top:0">Claude on your Pi reads a live snapshot (stats, services, internet, drives, traffic, money, recent alerts) and explains it. It can't run commands or change anything.</p>`}
    <div class="chat" id="askChat">${chat}</div>
    <div class="chips">${ASK_CHIPS.map(c => `<button data-askchip="${esc(c)}">${esc(c)}</button>`).join("")}</div>
    <div class="askin">
      <select id="askSrc" aria-label="Include logs"><option value="">No logs</option>${units.map(u => `<option value="unit:${esc(u)}">Include logs: ${esc(u)}</option>`).join("")}${(status?.containers || []).map(c => `<option value="container:${esc(c.name)}">Include logs: 🐳 ${esc(c.name)}</option>`).join("")}</select>
      <textarea id="askQ" rows="2" placeholder="Ask about your Pi, network, site or money…"></textarea>
      <button class="btn go wide" id="askGo" style="margin-top:0">ASK</button>
    </div>`;
  if (prev) $("#askSrc").value = prev;
  const ch = $("#askChat"); ch.lastElementChild?.scrollIntoView({ block: "end" });
}
function openAsk() { $("#sheetTitle").textContent = "Ask Orbit"; renderAsk(); $("#sheet").classList.add("open"); }
async function sendAsk(q) {
  q = (q || "").trim(); if (!q || askHist.some(m => m.wait)) return;
  const source = $("#askSrc")?.value || "";
  askHist.push({ who: "q", text: q }, { who: "a", text: "Thinking… (up to a minute)", wait: true }); renderAsk();
  const done = (text) => { askHist.pop(); askHist.push({ who: "a", text }); if ($("#sheetTitle").textContent === "Ask Orbit") renderAsk(); };
  let r; try { r = await post("api/ask", { question: q, source }); } catch { return done("No response from the Pi."); }
  if (!r.ok) return done(r.message || "Couldn't ask.");
  for (let i = 0; i < 55; i++) {
    await new Promise(res => setTimeout(res, 2000));
    let j; try { j = await api("api/ask?id=" + r.id); } catch { continue; }
    if (j.status === "done") return done(j.answer);
    if (j.status === "error") return done("⚠ " + j.error);
  }
  done("⚠ Timed out waiting for an answer.");
}
$("#askBtn").addEventListener("click", openAsk);
document.addEventListener("click", e => {
  if (e.target.id === "askGo") sendAsk($("#askQ").value);
  const c = e.target.closest("[data-askchip]"); if (c) sendAsk(c.dataset.askchip);
});
document.addEventListener("keydown", e => { if (e.target.id === "askQ" && e.key === "Enter" && !e.shiftKey) { e.preventDefault(); sendAsk(e.target.value); } });

/* ---------------- revenue funnel ---------------- */
let fDays = 7;
async function loadFunnel() {
  let f; try { f = await api("api/funnel?days=" + fDays); } catch { return; }
  const clicks = f.ebayClicks + f.amzClicks, sales = f.ebaySales + f.amzSales, earned = f.ebayEarned + f.amzEarned;
  const max = Math.max(f.visitors, 1);
  const st = (label, val, n, sub) => `<div class="st"><i style="width:${Math.max(4, Math.min(100, n / max * 100))}%"></i><span>${label}</span><b>${val}${sub ? ` <small class="mini">${sub}</small>` : ""}</b></div>`;
  $("#funnel").innerHTML = `<div class="fun">
      ${st("VISITORS", f.visitors, f.visitors, f.views + " views")}
      ${st("CLICKS", clicks, clicks, `eBay ${f.ebayClicks} · Amazon ${f.amzClicks}${f.clickRate != null ? " · " + f.clickRate + "%" : ""}`)}
      ${st("SALES", sales, sales, `eBay ${f.ebaySales} · Amazon ${f.amzSales}`)}
      ${st("EARNED", "$" + earned.toFixed(2), sales, f.perVisitor != null ? "$" + f.perVisitor.toFixed(3) + "/visitor" : "")}
    </div>
    ${f.models.length ? `<table class="mtab"><tr><th>MODEL</th><th>EBAY</th><th>AMZ</th><th>SALES</th><th>EARNED</th></tr>
      ${f.models.map(m => `<tr><td>${esc(m.name)}</td><td>${m.ebayClicks}</td><td>${m.amzClicks}</td><td>${m.sales}</td><td class="${m.earned ? "down" : ""}">$${m.earned.toFixed(2)}</td></tr>`).join("")}</table>`
      : `<div class="meta">Clicks and sales per model appear here once visitors start clicking.</div>`}`;
}
document.addEventListener("click", e => {
  const b = e.target.closest("[data-fdays]"); if (!b) return;
  fDays = +b.dataset.fdays; $$("[data-fdays]").forEach(x => x.classList.toggle("on", x === b)); loadFunnel();
});

/* ---------------- iPhone widget ---------------- */
$("#wCopy").addEventListener("click", async () => {
  try { const w = await api("api/widget/info"); await navigator.clipboard.writeText(w.script); toast("✓ Widget script copied. Paste it into a new Scriptable script."); }
  catch { toast("✗ Couldn't copy. Try again from the Home Screen app."); }
});
$("#wNew").addEventListener("click", async () => {
  if (!confirm("Make a new widget key? The current widget stops working until you paste the new script.")) return;
  const r = await post("api/widget/token", {}); toast(r.message || "Done");
});

/* ---------------- boot ---------------- */
(async () => {
  addInfoButtons();
  try { applySettings(await api("api/settings")); } catch { }
  try { const me = await api("api/me"); $("#me").textContent = "Signed in via Tailscale as " + me.login; } catch { }
  if ("serviceWorker" in navigator) navigator.serviceWorker.register("sw.js").catch(() => { });
  await seedHistory(); connect(); loadStatus(); loadAlerts(); loadDisks();
  const start = location.hash.slice(1);
  if (start && $(`.tabs [data-view="${start}"]`)) $(`.tabs [data-view="${start}"]`).click();
  setInterval(() => { loadStatus(); if (cur === "network") { loadNetwork(); loadSites(); } if (cur === "control") loadSecurity(); if (cur === "market") { loadMoney(); loadFunnel(); } if (cur === "alerts") loadAlerts(); }, 30000);
  setInterval(loadDisks, 300000);
  document.addEventListener("visibilitychange", () => { if (!document.hidden) { connect(); onView(cur); } });
  navigator.serviceWorker?.addEventListener("message", e => { if (e.data?.type === "nav") { const v = (e.data.url.split("#")[1] || "alerts"); $(`.tabs [data-view="${v}"]`)?.click(); } });
})();
