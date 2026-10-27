// Orbit widget for Scriptable (iOS). Works only while Tailscale is connected on this iPhone.
// Small: Pi health. Medium: Pi health + site traffic and money.
const URL = "__URL__";
const C = { bg: "#05070c", panel: "#0e1522", ink: "#e7f0ff", mute: "#7d8ba3", a: "#33e1ff", good: "#3dffa8", warn: "#ffc04d", bad: "#ff4d6d" };

async function load() {
  try {
    const r = new Request(URL);
    r.timeoutInterval = 10;
    return await r.loadJSON();
  } catch (e) {
    return null;
  }
}

function stat(stack, label, value, color) {
  const s = stack.addStack();
  s.layoutVertically();
  const l = s.addText(label);
  l.font = Font.semiboldMonospacedSystemFont(9);
  l.textColor = new Color(C.mute);
  const v = s.addText(String(value));
  v.font = Font.boldMonospacedSystemFont(17);
  v.textColor = new Color(color || C.ink);
  v.minimumScaleFactor = 0.6;
  return s;
}

const d = await load();
const w = new ListWidget();
w.backgroundColor = new Color(C.bg);
w.setPadding(12, 14, 12, 14);
w.url = URL.split("/api/")[0] + "/";

const head = w.addStack();
head.centerAlignContent();
const t = head.addText("ORBIT");
t.font = Font.heavySystemFont(13);
t.textColor = new Color(C.a);
head.addSpacer();
const dot = head.addText(d ? (d.online ? "● ONLINE" : "● NO INTERNET") : "● OFFLINE");
dot.font = Font.semiboldMonospacedSystemFont(9);
dot.textColor = new Color(!d ? C.mute : d.online ? C.good : C.bad);
w.addSpacer(8);

if (!d) {
  const m = w.addText("Can't reach the Pi. Is Tailscale on?");
  m.font = Font.systemFont(12);
  m.textColor = new Color(C.mute);
} else {
  const big = config.widgetFamily !== "small";
  const row1 = w.addStack();
  stat(row1, "CPU", d.cpu + "%");
  row1.addSpacer();
  stat(row1, "TEMP", d.temp != null ? Math.round(d.temp) + "°" : "--", d.temp > 75 ? C.bad : d.temp > 65 ? C.warn : C.ink);
  if (big) {
    row1.addSpacer();
    stat(row1, "MEM", d.mem + "%");
    row1.addSpacer();
    stat(row1, "PING", d.latency != null ? Math.round(d.latency) + "ms" : "--");
  }
  w.addSpacer(8);
  const row2 = w.addStack();
  stat(row2, "VISITORS", d.visitors);
  row2.addSpacer();
  stat(row2, "EARNED", "$" + (d.earned || 0).toFixed(2), C.good);
  if (big) {
    row2.addSpacer();
    stat(row2, "CLICKS", d.clicks);
    row2.addSpacer();
    stat(row2, "ALERTS", d.alerts, d.alerts ? C.warn : C.ink);
  }
  w.addSpacer();
  const f = w.addText("updated " + new Date(d.ts * 1000).toLocaleTimeString([], { hour: "numeric", minute: "2-digit" }));
  f.font = Font.systemFont(9);
  f.textColor = new Color(C.mute);
}

w.refreshAfterDate = new Date(Date.now() + 15 * 60 * 1000);
if (config.runsInWidget) Script.setWidget(w);
else await w.presentMedium();
Script.complete();
