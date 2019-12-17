/*
 * micro
 * Copyright (C) 2018 micro contributors
 *
 * This program is free software: you can redistribute it and/or modify it under the terms of the
 * GNU Lesser General Public License as published by the Free Software Foundation, either version 3
 * of the License, or (at your option) any later version.
 *
 * This program is distributed in the hope that it will be useful, but WITHOUT ANY WARRANTY; without
 * even the implied warranty of MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the GNU
 * Lesser General Public License for more details.
 *
 * You should have received a copy of the GNU Lesser General Public License along with this program.
 * If not, see <http://www.gnu.org/licenses/>.
 */

/* eslint-env serviceworker */

/** Service worker. */

"use strict";

self.micro = self.micro || {};
micro.service = {};

/**
 * :class:`Object` holding client assembly information.
 *
 * *shell* is the set of resources that make up the app shell. May be ``null``. *debug* indicates
 * debug mode.
 */
micro.service.MANIFEST = {shell: null, debug: false};

micro.service.STANDALONE = location.pathname.endsWith("@noyainrain/micro/service.js");
if (micro.service.STANDALONE) {
    // Chrome does not yet update the service worker if imports change (see
    // https://bugs.chromium.org/p/chromium/issues/detail?id=648295)
    // {{ version }}
    importScripts(new URL("util.js", location.href).href, "/manifest.js");
}

micro.util.watchErrors();

/**
 * Main service worker of a micro app.
 *
 * The app shell is cached for offline availability, if *shell* in :data:`micro.service.MANIFEST` is
 * set.
 *
 * .. attribute:: settings
 *
 *    Subclass API: App settings.
 *
 * .. attribute:: notificationRenderers
 *
 *    Subclass API: Table of notification render functions by event type.
 *
 *    A render function has the form *render(event)* and produces an :class:`Object`
 *    *{title, body, url}* from the given :ref:`Event` *event*. May return a :class:`Promise`. If
 *    one of the common call errors `NetworkError`, `AuthenticationError`, `NotFoundError` or
 *    `PermissionError` is thrown, no notification is displayed.
 *
 *    The key defines the event *type* (e.g. `editable-edit`) a renderer can handle, optionally
 *    augmented with event's *object* type (e.g. `editable-edit+Settings`). When rendering a
 *    notification, the most specific matching render function is used.
 */
micro.service.Service = class {
    constructor() {
        this.settings = null;
        this.notificationRenderers = {
            "user-enable-device-notifications": () => ({
                title: this.settings.title,
                body: "Notifications enabled",
                url: "/"
            })
        };

        addEventListener("install", event => {
            skipWaiting();
            if (!micro.service.MANIFEST.shell) {
                return;
            }
            event.waitUntil((async () => {
                const cache = await caches.open("micro");
                const target = new Set(micro.service.MANIFEST.shell);
                let current = await cache.keys();
                current = new Set(
                    current.map(request => {
                        const url = new URL(request.url);
                        return url.pathname + url.search;
                    })
                );
                const fresh = Array.from(target).filter(url => !current.has(url));
                const stale = Array.from(current).filter(url => !target.has(url));
                await cache.addAll(fresh);
                await Promise.all(stale.map(url => cache.delete(url)));
            })().catch(micro.util.catch));
        });
        addEventListener("activate", () => clients.claim());

        const handlers = [
            ["^/api/.*$", () => {}],
            ["^/log-client-error$", () => {}],
            ["^/manifest.webmanifest$", () => {}],
            [
                "^/static/.*$",
                event => event.respondWith((async() => {
                    const response = await caches.match(event.request.url);
                    return response || new Response(null, {status: 404, statusText: "Not Found"});
                })())
            ],
            ["^/.*$", event => event.respondWith(caches.match("/index.html", {ignoreSearch: true}))]
        ];
        addEventListener("fetch", event => {
            if (!micro.service.MANIFEST.shell || micro.service.MANIFEST.debug) {
                return;
            }
            const url = new URL(event.request.url);
            if (url.origin !== location.origin) {
                return;
            }
            for (let [pattern, handle] of handlers) {
                if (url.pathname.match(new RegExp(pattern, "u"))) {
                    handle(event);
                    break;
                }
            }
        });

        addEventListener("push", event => {
            event.waitUntil((async() => {
                if (!this.settings) {
                    try {
                        this.settings = await micro.call("GET", "/api/settings");
                    } catch (e) {
                        if (
                            e instanceof micro.NetworkError ||
                                e instanceof micro.APIError &&
                                e.error.__type__ === "AuthenticationError") {
                            return;
                        }
                        throw e;
                    }
                }

                let ev = event.data.json();
                let render;
                if (ev.object) {
                    render = this.notificationRenderers[`${ev.type}+${ev.object.__type__}`];
                }
                if (!render) {
                    render = this.notificationRenderers[ev.type];
                }
                if (!render) {
                    throw new Error("notification-renderers");
                }

                try {
                    let notification = await Promise.resolve(render(ev));
                    await registration.showNotification(notification.title, {
                        body: notification.body || undefined,
                        icon: this.settings.icon_large || undefined,
                        data: {url: notification.url}
                    });
                } catch (e) {
                    if (
                        e instanceof micro.NetworkError ||
                            e instanceof micro.APIError &&
                            e.error.__type__ in
                                ["AuthenticationError", "NotFoundError", "PermissionError"]) {
                        // Pass
                    } else {
                        throw e;
                    }
                }
            })().catch(micro.util.catch));
        });

        addEventListener("notificationclick", event => {
            event.waitUntil((async() => {
                let windows = await clients.matchAll({type: "window"});
                for (let client of windows) {
                    if (new URL(client.url).pathname === event.notification.data.url) {
                        // eslint-disable-next-line no-await-in-loop
                        await client.focus();
                        return;
                    }
                }
                await clients.openWindow(event.notification.data.url);
            })().catch(micro.util.catch));
        });
    }

    /**
     * Subclass API: Update :attr:`notificationRenderers` with the given *renderers*.
     */
    setNotificationRenderers(renderers) {
        Object.assign(this.notificationRenderers, renderers);
    }
};

if (micro.service.STANDALONE) {
    self.service = new micro.service.Service();
}
