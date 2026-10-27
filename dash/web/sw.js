// Network-first: always live data; cached shell only when the Pi is unreachable.
const C = "orbit-v5", SHELL = ["./", "index.html", "style.css", "app.js", "icon-mark.svg", "icon-192.png"];
self.addEventListener("install", e => { e.waitUntil(caches.open(C).then(c => c.addAll(SHELL))); self.skipWaiting(); });
self.addEventListener("activate", e => e.waitUntil(caches.keys().then(ks => Promise.all(ks.filter(k => k !== C).map(k => caches.delete(k)))).then(() => self.clients.claim())));
self.addEventListener("fetch", e => {
  const u = new URL(e.request.url);
  if (e.request.method !== "GET" || u.pathname.includes("/api/")) return;
  e.respondWith(fetch(e.request).then(r => { const cp = r.clone(); caches.open(C).then(c => c.put(e.request, cp)); return r; })
    .catch(() => caches.match(e.request)));
});
// Web Push: iOS requires a visible notification for every push.
self.addEventListener("push", e => {
  let d = {}; try { d = e.data ? e.data.json() : {}; } catch { d = { body: e.data && e.data.text() }; }
  e.waitUntil(self.registration.showNotification(d.title || "Orbit", {
    body: d.body || "", tag: d.tag, data: { url: d.url || "./#alerts" }, icon: "icon-192.png", badge: "icon-192.png",
    requireInteraction: d.level === "critical", renotify: !!d.tag,
  }));
});
self.addEventListener("notificationclick", e => {
  e.notification.close();
  const url = new URL(e.notification.data?.url || "./#alerts", self.registration.scope).href;
  e.waitUntil(self.clients.matchAll({ type: "window", includeUncontrolled: true }).then(cs => {
    const c = cs[0];
    if (c) { c.postMessage({ type: "nav", url }); return c.focus(); }
    return self.clients.openWindow(url);
  }));
});
