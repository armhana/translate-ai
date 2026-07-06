// Service Worker: macht die Web-Oberfläche als App installierbar
// (Chrome/Edge auf Windows, Android, Linux, Mac). Statische Dateien werden
// gecacht; alle API-Aufrufe gehen immer live an den Server.
const CACHE = "uebersetzer-v2";
const SHELL = ["/", "/index.html", "/manifest.json", "/icon.svg"];

self.addEventListener("install", (e) => {
  e.waitUntil(caches.open(CACHE).then((c) => c.addAll(SHELL)));
  self.skipWaiting();
});

self.addEventListener("activate", (e) => {
  e.waitUntil(
    caches.keys().then((keys) =>
      Promise.all(keys.filter((k) => k !== CACHE).map((k) => caches.delete(k)))
    )
  );
});

self.addEventListener("fetch", (e) => {
  const url = new URL(e.request.url);
  if (url.pathname.startsWith("/api/")) return; // API immer live
  e.respondWith(
    fetch(e.request)
      .then((res) => {
        const kopie = res.clone();
        caches.open(CACHE).then((c) => c.put(e.request, kopie));
        return res;
      })
      .catch(() => caches.match(e.request))
  );
});
