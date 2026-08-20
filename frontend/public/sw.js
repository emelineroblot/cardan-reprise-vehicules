/**
 * Service worker du module terrain (PWA J2, décision C).
 *
 * Rôle volontairement restreint : rendre l'app INSTALLABLE et servir un repli hors ligne
 * pour la coquille de navigation. Le vrai mécanisme de résilience réseau (checklist,
 * photos) est IndexedDB + rejeu au premier plan (`src/lib/offline/`), PAS le cache HTTP de
 * ce service worker — une réponse API mise en cache ici serait une session ou un état
 * métier périmé servi à l'utilisateur sans qu'il le sache. Aucune requête vers
 * `/api/backend/...` n'est donc jamais interceptée : elle part toujours au réseau, et si
 * elle échoue, l'appelant (client.ts) la traduit en `ApiError` gérée par l'UI.
 */
const CACHE_VERSION = "cardan-terrain-v1";
const OFFLINE_URL = "/hors-ligne.html";
const APP_SHELL = [OFFLINE_URL, "/manifest.json"];

self.addEventListener("install", (event) => {
  event.waitUntil(
    caches
      .open(CACHE_VERSION)
      .then((cache) => cache.addAll(APP_SHELL))
      .then(() => self.skipWaiting()),
  );
});

self.addEventListener("activate", (event) => {
  event.waitUntil(
    caches
      .keys()
      .then((keys) => Promise.all(keys.filter((key) => key !== CACHE_VERSION).map((key) => caches.delete(key))))
      .then(() => self.clients.claim()),
  );
});

self.addEventListener("fetch", (event) => {
  const url = new URL(event.request.url);

  // Jamais d'interception pour l'API (proxy same-origin) ni pour les octets photo servis
  // par le backend — toujours le réseau, jamais un cache HTTP périmé sur une donnée
  // métier (voir commentaire d'en-tête).
  if (url.pathname.startsWith("/api/")) return;

  // Navigation (changement de page) : réseau d'abord, repli sur la page hors-ligne posée
  // au moment de l'installation si la requête échoue complètement.
  if (event.request.mode === "navigate") {
    event.respondWith(
      fetch(event.request).catch(() => caches.match(OFFLINE_URL).then((res) => res ?? Response.error())),
    );
    return;
  }

  // Assets statiques (Next, icônes) : cache d'abord, réseau en repli — accélère les
  // rechargements en conditions de réseau instable sans jamais bloquer une mise à jour
  // (le fichier a un hash dans son nom, donc jamais périmé une fois mis en cache).
  if (event.request.method === "GET" && (url.pathname.startsWith("/_next/") || url.pathname.startsWith("/icons/"))) {
    event.respondWith(
      caches.match(event.request).then(
        (cached) =>
          cached ??
          fetch(event.request).then((response) => {
            if (response.ok) {
              const clone = response.clone();
              caches.open(CACHE_VERSION).then((cache) => cache.put(event.request, clone));
            }
            return response;
          }),
      ),
    );
  }
});

/**
 * Web push réel (optionnel, actif seulement si VAPID est configuré côté backend —
 * `GET /notifications/push-public-key`). Ce handler ne fait jamais planter le service
 * worker si la charge utile est absente ou mal formée : le chemin nominal (pastille +
 * liste en base) ne dépend d'aucune de ces lignes.
 */
self.addEventListener("push", (event) => {
  if (!event.data) return;
  let payload;
  try {
    payload = event.data.json();
  } catch {
    return;
  }
  const title = payload.titre || "Cardan";
  const options = {
    body: payload.corps || "",
    icon: "/icons/icon-192.png",
    badge: "/icons/icon-192.png",
    data: payload.payload || {},
  };
  event.waitUntil(self.registration.showNotification(title, options));
});

self.addEventListener("notificationclick", (event) => {
  event.notification.close();
  const vehicleId = event.notification.data?.vehicle_id;
  const target = vehicleId ? `/vehicules/${vehicleId}` : "/missions";
  event.waitUntil(
    self.clients.matchAll({ type: "window", includeUncontrolled: true }).then((clientsList) => {
      for (const client of clientsList) {
        if (client.url.includes(target) && "focus" in client) return client.focus();
      }
      if (self.clients.openWindow) return self.clients.openWindow(target);
    }),
  );
});
