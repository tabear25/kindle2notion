/* kindle2notion service worker.
 *
 * Why it exists: together with manifest.webmanifest it lets Android Chrome
 * install the UI as an app (home-screen icon, shortcuts, share target), and
 * an installed app should still open its shell when the phone is offline.
 *
 * What it must never do: become the reason a deployed fix fails to reach the
 * phone — the bug the ?v= asset queries in index.html were added to kill. So
 * the network always wins and the cache is only an offline fallback:
 *   - Navigations are left to the browser while online. Besides freshness,
 *     this keeps Basic auth working when Flask serves the UI: a 401 answered
 *     to a service-worker fetch does not bring up the browser's login prompt.
 *   - Same-origin /static/ assets are network-first, copied into the cache
 *     only so the shell can open offline.
 *   - API traffic (/api/*, /healthz, and every other origin, i.e. the Render
 *     backend) is never intercepted: SSE streams and cold-start probes behave
 *     exactly as they would without a service worker.
 *
 * Bump CACHE_NAME whenever the caching logic below changes.
 */
"use strict";

var CACHE_NAME = "k2n-shell-v1";
var SHELL_URL = "/";
var STATIC_PREFIX = "/static/";

function isCacheable(response) {
  return !!response && response.ok && response.type === "basic" && !response.redirected;
}

// Cache "/" plus the assets it references, so the very first offline launch
// after installing already has a complete shell. Reading the asset URLs out
// of the HTML keeps this file free of the ?v= values it would otherwise have
// to be kept in sync with.
function precacheShell() {
  return caches.open(CACHE_NAME).then(function (cache) {
    return fetch(SHELL_URL, { cache: "no-cache" }).then(function (response) {
      if (!isCacheable(response)) {
        return undefined; // e.g. 401 behind Basic auth: simply skip
      }
      return response
        .clone()
        .text()
        .then(function (html) {
          var assets = [];
          html.replace(/(?:src|href)="(\/static\/[^"]+)"/g, function (match, url) {
            assets.push(url);
            return match;
          });
          return cache.put(SHELL_URL, response).then(function () {
            return Promise.all(
              assets.map(function (url) {
                return fetch(url, { cache: "no-cache" }).then(
                  function (assetResponse) {
                    return isCacheable(assetResponse) ? cache.put(url, assetResponse) : undefined;
                  },
                  function () {
                    return undefined;
                  }
                );
              })
            );
          });
        });
    });
  });
}

// A new deploy changes app.js?v=… — drop the copies of older versions so
// the cache holds one entry per file instead of one per deploy.
function storeAsset(request, response) {
  var target = new URL(request.url);
  return caches.open(CACHE_NAME).then(function (cache) {
    return cache
      .keys()
      .then(function (keys) {
        return Promise.all(
          keys
            .filter(function (key) {
              var url = new URL(key.url);
              return url.pathname === target.pathname && url.search !== target.search;
            })
            .map(function (key) {
              return cache.delete(key);
            })
        );
      })
      .then(function () {
        return cache.put(request, response);
      });
  });
}

self.addEventListener("install", function (event) {
  event.waitUntil(
    precacheShell()
      .catch(function () {
        // Offline support is a bonus: never fail the install over it.
      })
      .then(function () {
        return self.skipWaiting();
      })
  );
});

self.addEventListener("activate", function (event) {
  event.waitUntil(
    caches
      .keys()
      .then(function (names) {
        return Promise.all(
          names
            .filter(function (name) {
              return name.indexOf("k2n-") === 0 && name !== CACHE_NAME;
            })
            .map(function (name) {
              return caches.delete(name);
            })
        );
      })
      .then(function () {
        return self.clients.claim();
      })
  );
});

self.addEventListener("fetch", function (event) {
  var request = event.request;
  if (request.method !== "GET") {
    return;
  }
  var url = new URL(request.url);
  if (url.origin !== self.location.origin) {
    return; // the backend API on another origin: never touched
  }

  if (request.mode === "navigate") {
    if (self.navigator.onLine !== false) {
      return; // online: the browser navigates natively (see header comment)
    }
    event.respondWith(
      fetch(request).catch(function () {
        return caches.match(SHELL_URL).then(function (cached) {
          return cached || Response.error();
        });
      })
    );
    return;
  }

  if (url.pathname.indexOf(STATIC_PREFIX) !== 0) {
    return; // /api/*, /healthz, the manifest, this script
  }

  event.respondWith(
    fetch(request).then(
      function (response) {
        if (isCacheable(response)) {
          event.waitUntil(storeAsset(request, response.clone()).catch(function () {}));
        }
        return response;
      },
      function (error) {
        return caches.match(request).then(function (cached) {
          if (cached) {
            return cached;
          }
          throw error;
        });
      }
    )
  );
});
