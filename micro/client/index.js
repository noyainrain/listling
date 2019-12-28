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

/**
 * Client toolkit for social micro web apps.
 */

"use strict";

micro.util.watchErrors();

micro.LIST_LIMIT = 100;

/**
 * Find the first ancestor of *elem* that satisfies *predicate*.
 *
 * .. deprecated: 0.11.0
 *
 *    Use :func:`micro.keyboard.findAncestor` .
 */
micro.findAncestor = micro.keyboard.findAncestor;

/**
 * User interface of a micro app.
 *
 * At the core of the UI are pages, where any page has a corresponding (shareable and bookmarkable)
 * URL. The UI takes care of user navigation.
 *
 * .. attribute:: pages
 *
 *    Subclass API: Table of available pages.
 *
 *    It is a list of objects with the attributes *url* and *page*, where *page* is the page to show
 *    if the requested URL matches the regular expression pattern *url*.
 *
 *    *page* is either the tag of a :ref:`Page` or a function. If it is a tag, the element is
 *    created and used as page.
 *
 *    If *page* is a function, it has the form *page(url)* and is responsible to prepare and return
 *    a :ref:`Page`. *url* is the requested URL. Groups captured from the URL pattern are passed as
 *    additional arguments. The function may return a promise. For convenience, if one of the
 *    following common call errors is thrown:
 *
 *    - `NetworkError`: The `micro-offline-page` is shown
 *    - `NotFoundError`: The `micro-not-found-page` is shown
 *    - `PermissionError`: The `micro-forbidden-page` is shown
 *
 *    May be set by subclass in :meth:`init`. Defaults to ``[]``.
 *
 * .. attribute:: service
 *
 *    Service worker of the app, more precisely a :class:`ServiceWorkerRegistration`.
 *
 * .. attribute:: renderEvent
 *
 *    Subclass API: Table of event rendering hooks by event type. Used by the activity page to
 *    visualize :ref:`Event` s. A hook has the form *renderEvent(event)* and is responsible to
 *    render the given *event* to a :class:`Node`.
 *
 * .. describe:: navigate
 *
 *    Fired when the user navigates around the UI (either via link, browser history,
 *    :meth:`navigate` or initially on app launch). *oldURL* and *newURL* are the previous and now
 *    current URL respectively.
 */
micro.UI = class extends HTMLBodyElement {
    createdCallback() {
        this.mapServiceKey =
            document.querySelector("meta[itemprop=map-service-key]").content || null;
        this._url = null;
        this._page = null;
        this._progressElem = this.querySelector(".micro-ui-progress");
        this._pageSpace = this.querySelector("main .micro-ui-inside");
        this._activities = new Set();

        this.pages = [
            {url: "^/(?:users/([^/]+)|user)/edit$", page: micro.EditUserPage.make},
            {url: "^/settings/edit$", page: micro.EditSettingsPage.make},
            {url: "^/analytics$", page: micro.components.analytics.AnalyticsPage.make},
            {url: "^/activity$", page: micro.ActivityPage.make}
        ];

        this.renderEvent = {
            "editable-edit": event => {
                let a = document.createElement("a");
                a.classList.add("link");
                a.href = "/settings/edit";
                a.textContent = "site settings";
                let userElem = document.createElement("micro-user");
                userElem.user = event.user;
                return micro.util.formatFragment("The {settings} were edited by {user}",
                                                 {settings: a, user: userElem});
            }
        };

        window.addEventListener("error", event => {
            // Work around bogus EventSource polyfill errors
            if (event.message.startsWith("EventSource")) {
                return;
            }
            this.notify(document.createElement("micro-error-notification"));
        });
        window.addEventListener("popstate", () => this._navigate().catch(micro.util.catch));
        this.addEventListener("click", event => {
            let a = micro.findAncestor(event.target, e => e instanceof HTMLAnchorElement, this);
            if (a && a.origin === location.origin) {
                event.preventDefault();
                this.navigate(a.pathname + a.hash).catch(micro.util.catch);
            }
        });
        this.addEventListener("focusin", event => {
            if (event.target.id) {
                this.url = `#${event.target.id}`;
            }
        });
        this.addEventListener("user-edit", this);
        this.addEventListener("settings-edit", this);

        // Register UI as global
        window.ui = this;

        // Cancel launch if platform checks failed
        if (!micro.launch) {
            return;
        }

        micro.keyboard.enableActivatedClass();
        this.shortcutContext = new micro.keyboard.ShortcutContext(this);
        this.shortcutContext.add("J", micro.keyboard.quickNavigate.bind(null, "next"));
        this.shortcutContext.add("K", micro.keyboard.quickNavigate.bind(null, "prev"));

        this.insertBefore(
            document.importNode(this.querySelector(".micro-ui-template").content, true),
            this.querySelector("main"));
        for (let elem of this.querySelectorAll("[slot=menu]")) {
            this.querySelector(".micro-ui-about").insertAdjacentElement("beforebegin", elem);
        }
        /*this.querySelector(".micro-ui-header-menu ul").prepend(
            ...this.querySelectorAll("[slot=menu]")
        );*/

        this._data = new micro.bind.Watchable({
            user: null,
            settings: null,
            offline: false,
            temp: 0,
            co2: 0
        });
        micro.bind.bind(this.children, this._data);

        let update = () => {
            document.querySelector('link[rel=icon][sizes="16x16"]').href =
                this._data.settings && this._data.settings.icon_small || "";
            document.querySelector('link[rel=icon][sizes="512x512"]').href =
                this._data.settings && this._data.settings.icon_large || "";
            document.querySelector("meta[name=theme-color]").content =
                getComputedStyle(this).getPropertyValue("--micro-color-primary").trim();
            this.classList.toggle("micro-ui-user-is-staff",
                                  this._data.settings && this._data.user && this.staff);
            this.classList.toggle("micro-ui-settings-have-icon-small",
                                  this._data.settings && this._data.settings.icon_small);
            this.classList.toggle("micro-ui-settings-have-feedback-url",
                                  this._data.settings && this._data.settings.feedback_url);
            this.classList.toggle("micro-ui-offline", this._data.offline);
        };
        ["user", "settings", "offline"].forEach(prop => this._data.watch(prop, update));

        this.features = {
            es6TypedArray: "ArrayBuffer" in window,
            serviceWorkers: "serviceWorker" in navigator,
            push: "PushManager" in window
        };
        this.classList.add(
            ...Object.entries(this.features)
                .filter(([, supported]) => supported)
                .map(([feature]) => `micro-feature-${micro.bind.dash(feature)}`));
        this.classList.toggle("micro-ui-map-service-enabled", this.mapServiceKey);

        this.service = null;
        if (this.features.serviceWorkers) {
            let url = document.querySelector("link[rel=service]").href;
            // Technically the app should stop with an offline indication on any network error, but
            // to not slow startup, register in the background
            (async() => {
                try {
                    this.service = await navigator.serviceWorker.register(url, {scope: "/"});
                } catch (e) {
                    // Work around Firefox disabling service workers depending on privacy settings
                    // (see https://bugzilla.mozilla.org/show_bug.cgi?id=1413615)
                    if (e instanceof DOMException && e.name === "SecurityError") {
                        this.features.serviceWorkers = false;
                        this.classList.remove("micro-feature-service-workers");
                    } else {
                        throw e;
                    }
                }
            })().catch(micro.util.catch);
        }

        const version = parseInt(localStorage.microVersion) || null;
        if (!version) {
            this._storeUser(null);
            localStorage.microSettings = JSON.stringify(null);
            localStorage.microVersion = 2;
        }
        // Deprecated since 0.36.0
        if (version < 2) {
            localStorage.microSettings = JSON.stringify(null);
            localStorage.microVersion = 2;
        }

        // Go!
        let go = async() => {
            try {
                this._progressElem.style.display = "block";
                await Promise.resolve(this.update());
                this._data.user = JSON.parse(localStorage.microUser);
                this._data.settings = JSON.parse(localStorage.microSettings);

                // If requested, log in with code
                let match = /^#login=(.+)$/u.exec(location.hash);
                if (match) {
                    history.replaceState(null, null, location.pathname);
                    try {
                        this._storeUser(await ui.call("POST", "/api/login", {code: match[1]}));
                    } catch (e) {
                        // Ignore invalid login codes
                        if (!(e instanceof micro.APIError)) {
                            throw e;
                        }
                    }
                }

                // If not logged in (yet), log in as a new user
                if (!this.user) {
                    this._storeUser(await ui.call("POST", "/api/login"));
                }

                if (!this.settings) {
                    this._data.settings = await ui.call("GET", "/api/settings");
                    localStorage.microSettings = JSON.stringify(this._data.settings);
                }

                // Update user details and settings
                (async() => {
                    try {
                        const user = await ui.call("GET", `/api/users/${this.user.id}`);
                        this.dispatchEvent(new CustomEvent("user-edit", {detail: {user}}));
                        const settings = await ui.call("GET", "/api/settings");
                        this.dispatchEvent(new CustomEvent("settings-edit", {detail: {settings}}));
                        if (
                            document.referrer &&
                            new URL(document.referrer).origin !== location.origin
                        ) {
                            await ui.call(
                                "POST", "/api/analytics/referrals", {url: document.referrer}
                            );
                        }
                    } catch (e) {
                        if (!(e instanceof micro.NetworkError)) {
                            throw e;
                        }
                    }
                })().catch(micro.util.catch);

                await this.init();

                this.querySelector(".micro-ui-header").style.display = "block";
                await this._navigate();

            } catch (e) {
                if (e instanceof micro.NetworkError) {
                    this._progressElem.style.display = "none";
                    this._data.settings = {title: document.title};
                    this.page = document.createElement("micro-offline-page");
                } else {
                    throw e;
                }
            }
        };
        go().catch(micro.util.catch);

        setInterval(async () => {
            const result = await micro.call("GET", "/api/co2");
            this._data.co2 = result.data[0];
            this._data.temp = result.data[1];
        }, 10000);
    }

    /** Current URL. Set to rewrite the browser URL. */
    get url() {
        return this._url;
    }

    set url(value) {
        value = new URL(value, location.href);
        value = value.pathname + value.hash;
        this._url = value;
        history.replaceState(null, null, this._url);
    }

    /** Active :class:`micro.Page`. Set to open the given page. May be ``null``. */
    get page() {
        return this._page;
    }

    set page(value) {
        if (this._page) {
            this._page.remove();
        }
        this._page = value;
        if (this._page) {
            this._pageSpace.appendChild(this._page);
            // Compatibility for overriding attachedCallback without chaining (deprecated since
            // 0.19.0)
            micro.Page.prototype.attachedCallback.call(this._page);
            this._updateTitle();
        }
    }

    /** Current :ref:`User`. */
    get user() {
        return this._data.user;
    }

    /**
     * App settings.
     */
    get settings() {
        return this._data.settings;
    }

    /**
     * Is the current :attr:`user` a staff member?
     */
    get staff() {
        return this._data.settings.staff.map(s => s.id).indexOf(this.user.id) !== -1;
    }

    /**
     * Indicates if the UI is in non-interactive mode, where interactive elements (marked with the
     * class ``micro-interactive``) are hidden.
     */
    get noninteractive() {
        return this.hasAttribute("noninteractive");
    }

    set noninteractive(value) {
        if (value) {
            this.setAttribute("noninteractive", "noninteractive");
        } else {
            this.removeAttribute("noninteractive");
        }
    }

    /**
     * Subclass API: Update the UI storage.
     *
     * If the storage is fresh, it will be initialized. If the storage is already up-to-date,
     * nothing will be done.
     *
     * May return a promise. Note that the UI is not available to the user before the promise
     * resolves.
     *
     * May be overridden by subclass. The default implementation does nothing. Called on startup.
     */
    update() {}

    /**
     * Subclass API: Initialize the UI.
     *
     * May return a promise. Note that the UI is not available to the user before the promise
     * resolves.
     *
     * May be overridden by subclass. The default implementation does nothing. Called on startup.
     */
    init() {}

    /**
     * Call a *method* on the HTTP JSON REST API endpoint at *url*.
     *
     * This is a wrapper around :func:`micro.call` which takes responsibility of handling
     * `AuthenticationError`s.
     */
    async call(method, url, args) {
        try {
            return await micro.call(method, url, args);
        } catch (e) {
            // Authentication errors are a corner case and happen only if a) the user has deleted
            // their account on another device or b) the database has been reset (during
            // development)
            if (e instanceof micro.APIError && e.error.__type__ === "AuthenticationError") {
                this._storeUser(null);
                location.reload();
                // Never return
                await new Promise(() => {});
            }
            throw e;
        }
    }

    /**
     * Handle a common call error *e* with a default reaction:
     *
     * - `NetworkError`: Notify the user that they seem to be offline
     * - `NotFoundError`: Notify the user that the current page has been deleted
     * - `PermissionError`: Notify the user that their permissions for the current page have been
     *   revoked
     *
     * Other errors are not handled and re-thrown.
     */
    handleCallError(e) {
        if (e instanceof micro.NetworkError) {
            this.notify(
                "Oops, you seem to be offline! Please check your connection and try again.");
        } else if (e instanceof micro.APIError && e.error.__type__ === "NotFoundError") {
            this.notify("Oops, someone has just deleted this page!");
        } else if (e instanceof micro.APIError && e.error.__type__ === "PermissionError") {
            this.notify("Oops, someone has just revoked your permissions for this page!");
        } else if (e instanceof micro.APIError && e.error.__type__ === "RateLimitError") {
            this.notify("Oops, not so fast. Please wait a few minutes.");
        } else {
            throw e;
        }
    }

    /**
     * Navigate to the given *url*.
     */
    async navigate(url) {
        url = new URL(url, location.href);
        url = url.pathname + url.hash;
        if (url !== this._url) {
            history.pushState(null, null, url);
        }
        await this._navigate();
    }

    /**
     * Show a *notification* to the user.
     *
     * *notification* is a :class:`HTMLElement`, like for example :class:`SimpleNotification`.
     * Alternatively, *notification* can be a simple message string to display.
     */
    notify(notification) {
        if (typeof notification === "string") {
            let elem = document.createElement("micro-simple-notification");
            let p = document.createElement("p");
            p.textContent = notification;
            elem.content.appendChild(p);
            notification = elem;
        }

        let space = this.querySelector(".micro-ui-notification-space");
        space.textContent = "";
        space.appendChild(notification);
    }

    /**
     * Show a dialog about enabling device notifications to the user.
     *
     * The result of the dialog is returned:
     *
     * - ``ok``: Notifications have been enabled
     * - ``cancel``: The user canceled the dialog
     * - ``error``: A communication error occured
     */
    async enableDeviceNotifications() {
        const COMMUNICATION_ERROR_MESSAGE = "Oops, there was a problem communicating with your device. Please try again in a few moments.";

        if (!(this.features.push && this.features.serviceWorkers && this.features.es6TypedArray)) {
            throw new Error("features");
        }

        // Chrome does not yet support base64-encoded VAPID keys (see
        // https://bugs.chromium.org/p/chromium/issues/detail?id=802280)
        let applicationServerKey = Uint8Array.from(
            atob(this.settings.push_vapid_public_key.replace(/-/ug, "+").replace(/_/ug, "/")),
            c => c.codePointAt(0));

        const service = await navigator.serviceWorker.ready;
        // Subscribing fails with an InvalidStateError if there is an existing subscription and we
        // pass a different VAPID public key (after a database reset)
        let subscription = await service.pushManager.getSubscription();
        if (subscription) {
            await subscription.unsubscribe();
        }
        try {
            subscription = await service.pushManager.subscribe(
                {userVisibleOnly: true, applicationServerKey}
            );
        } catch (e) {
            if (e instanceof DOMException && e.name === "NotAllowedError") {
                return "cancel";
            } else if (e instanceof DOMException && e.name === "AbortError") {
                ui.notify(COMMUNICATION_ERROR_MESSAGE);
                return "error";
            }
            throw e;
        }
        subscription = JSON.stringify(subscription.toJSON());

        let user;
        try {
            user = await ui.call("PATCH", `/api/users/${this.user.id}`,
                                 {op: "enable_notifications", push_subscription: subscription});
            micro.util.dispatchEvent(this, new CustomEvent("user-edit", {detail: {user}}));
            return "ok";
        } catch (e) {
            if (e instanceof micro.APIError && e.error.__type__ === "CommunicationError") {
                ui.notify(COMMUNICATION_ERROR_MESSAGE);
            } else {
                ui.handleCallError(e);
            }
            return "error";
        }
    }

    /** Scroll :class:`Element` *elem* into view, minding the header. */
    scrollToElement(elem) {
        const em = parseFloat(getComputedStyle(this).fontSize);
        scroll(0, elem.offsetTop - (2 * 1.5 * em + 2 * 1.5 * em / 4));
    }

    async _navigate() {
        let oldURL = this._url;
        let oldLocation = oldURL ? new URL(oldURL, location.origin) : null;
        this._url = location.pathname + location.hash;

        if (oldLocation === null || location.pathname !== oldLocation.pathname) {
            this._progressElem.style.display = "block";
            this.page = null;
            this.page = await this._route(location.pathname);
            this._progressElem.style.display = "none";
        }

        if (location.hash) {
            await this.page.ready;
            try {
                let elem = this.querySelector(location.hash);
                if (elem) {
                    elem.focus({preventScroll: true});
                    elem.scrollIntoView();
                }
            } catch (e) {
                // Ignore if hash is not a valid CSS selector
                if (e instanceof DOMException && e.name === "SyntaxError") {
                    return;
                }
                throw e;
            }
        }

        this.dispatchEvent(new CustomEvent("navigate", {detail: {oldURL, newURL: this._url}}));
    }

    async _route(url) {
        let match = null;
        let route = null;
        for (route of this.pages) {
            match = new RegExp(route.url, "u").exec(url);
            if (match) {
                break;
            }
        }

        if (!match) {
            return document.createElement("micro-not-found-page");
        }
        if (typeof route.page === "string") {
            return document.createElement(route.page);
        }
        let args = [url].concat(match.slice(1));
        try {
            return await Promise.resolve(route.page(...args));
        } catch (e) {
            if (e instanceof micro.NetworkError) {
                return document.createElement("micro-offline-page");
            } else if (e instanceof micro.APIError &&
                       e.error.__type__ === "NotFoundError") {
                return document.createElement("micro-not-found-page");
            } else if (e instanceof micro.APIError &&
                       e.error.__type__ === "PermissionError") {
                return document.createElement("micro-forbidden-page");
            }
            throw e;
        }
    }

    _updateTitle() {
        document.title = [this.page.caption, this._data.settings.title].filter(p => p).join(" - ");
    }

    _storeUser(user) {
        this._data.user = user;
        if (user) {
            localStorage.microUser = JSON.stringify(user);
            document.cookie =
                `auth_secret=${user.auth_secret}; path=/; max-age=${360 * 24 * 60 * 60}`;
        } else {
            localStorage.microUser = null;
            document.cookie = "auth_secret=; path=/; max-age=0";
        }
    }

    _addActivity(activity) {
        const update = () => {
            this._data.offline = !Array.from(this._activities).every(a => a.connected);
        };
        this._activities.add(activity);
        update();
        activity.events.addEventListener("close", () => {
            this._activities.delete(activity);
            update();
        });
        ["connect", "disconnect"].forEach(event => activity.events.addEventListener(event, update));
    }

    handleEvent(event) {
        if (event.target === this && event.type === "user-edit") {
            this._storeUser(event.detail.user);

        } else if (event.target === this && event.type === "settings-edit") {
            this._data.settings = event.detail.settings;
            localStorage.microSettings = JSON.stringify(event.detail.settings);
        }
    }
};

/**
 * :ref:`Collection` receivable in chunks.
 *
 * .. attribute:: url
 *
 *    URL of the collection.
 *
 * .. attribute:: items
 *
 *    :class:`micro.bind.Watchable` :class:`Array` of fetched items.
 *
 * .. attribute:: count
 *
 *    Overall number of items in the collection or ``null`` if not known yet.
 *
 * .. describe:: fetch
 *
 *    Dispatched when new items have been fetched.
 */
micro.Collection = class {
    constructor(url) {
        this.url = url;
        this.items = new micro.bind.Watchable([]);
        this.count = null;
        this.events = document.createElement("span");
        this.events.collection = this;
    }

    /** Indicates if all items have been fetched. */
    get complete() {
        return this.items.length === this.count;
    }

    /**
     * Fetch the next *n* *items*.
     *
     * If :http:get:`querying the collection </api/(resource-url)?slice>` fails, an
     * :class:`APIError` or :class:`NetworkError` is thrown.
     */
    async fetch(n = micro.LIST_LIMIT) {
        const query = await ui.call(
            "GET", `${this.url}?slice=${this.items.length}:${this.items.length + n}`
        );
        this.items.push(...query.items);
        this.count = query.count;
        this.events.dispatchEvent(new CustomEvent("fetch"));
    }
};

/**
 * :ref:`Activity` stream of events.
 *
 * Received events are dispatched.
 *
 * .. attribute:: url
 *
 *    :http:get:`/api/(activity-url)/stream` URL.
 *
 * .. attribute:: connected
 *
 *    Indicates if the stream is connected and ready to emit events. If disconnected, it'll be
 *    reconnected automatically.
 *
 * .. describe:: connect
 *
 *    Dispatched if the stream has been reconnected.
 *
 * .. describe:: disconnect
 *
 *    Dispatched if the stream has been disconnected.
 *
 * .. describe:: close
 *
 *    Dispatched when the stream has been closed (via :meth:`close`).
 */
micro.Activity = class {
    /** Open the activity stream at *url*. */
    static async open(url) {
        const eventSource = new EventSource(url, {heartbeatTimeout: 60 * 60 * 1000});
        // Wait for initial connection attempt
        await new Promise(resolve => {
            function stop() {
                ["open", "error"].forEach(event => eventSource.removeEventListener(event, stop));
                resolve();
            }
            ["open", "error"].forEach(event => eventSource.addEventListener(event, stop));
        });

        const activity = new micro.Activity(eventSource);
        // eslint-disable-next-line no-underscore-dangle
        ui._addActivity(activity);
        return activity;
    }

    constructor(eventSource) {
        this._RESET_TIMEOUT = 60 * 1000;

        this.url = eventSource.url;
        this.connected = eventSource.readyState === 1;
        this.events = document.createElement("span");
        this._eventSource = eventSource;
        this._timeout = null;

        this._setupEventSource();
        if (this._eventSource.readyState === 2) {
            this._resetEventSource();
        }
    }

    /** Close the stream. */
    close() {
        this._eventSource.close();
        clearTimeout(this._timeout);
        this.events.dispatchEvent(new CustomEvent("close"));
    }

    _setupEventSource() {
        this._eventSource.addEventListener("open", () => {
            this.connected = true;
            this.events.dispatchEvent(new CustomEvent("connect"));
        });

        this._eventSource.addEventListener("error", () => {
            if (this.connected) {
                this.connected = false;
                this.events.dispatchEvent(new CustomEvent("disconnect"));
            }
            if (this._eventSource.readyState === 2) {
                this._resetEventSource();
            }
        });

        this._eventSource.addEventListener("message", event => {
            const e = JSON.parse(event.data);
            this.events.dispatchEvent(new CustomEvent(e.type, {detail: {event: e}}));
        });
    }

    _resetEventSource() {
        this._timeout = setTimeout(() => {
            this._eventSource = new EventSource(this.url, {heartbeatTimeout: 60 * 60 * 1000});
            this._setupEventSource();
        }, this._RESET_TIMEOUT);
    }
};

/**
 * Simple notification.
 */
micro.SimpleNotification = class extends HTMLElement {
    createdCallback() {
        this.appendChild(document.importNode(
            ui.querySelector(".micro-simple-notification-template").content, true));
        this.classList.add("micro-notification", "micro-simple-notification");
        this.querySelector(".micro-simple-notification-dismiss").addEventListener("click", this);
        this.content = this.querySelector(".micro-simple-notification-content");
    }

    handleEvent(event) {
        if (event.currentTarget === this.querySelector(".micro-simple-notification-dismiss") &&
                event.type === "click") {
            this.parentNode.removeChild(this);
        }
    }
};

/**
 * Notification that informs the user about app errors.
 */
micro.ErrorNotification = class extends HTMLElement {
    createdCallback() {
        this.appendChild(document.importNode(
            ui.querySelector(".micro-error-notification-template").content, true));
        this.classList.add("micro-notification", "micro-error-notification");
        this.querySelector(".micro-error-notification-reload").addEventListener("click", this);
    }

    handleEvent(event) {
        if (event.currentTarget === this.querySelector(".micro-error-notification-reload") &&
                event.type === "click") {
            location.reload();
        }
    }
};

/**
 * Enhanced ordered list.
 *
 * The list is sortable by the user, i.e. an user can move an item of the list by dragging it by a
 * handle. A handle is defined by the ``micro-ol-handle`` class; if an item has no handle, it cannot
 * be moved. While an item is moving, the class ``micro-ol-li-moving` is applied to it.
 *
 * Events:
 *
 * .. describe:: moveitem
 *
 *    Dispatched if an item has been moved by the user. The *detail* object of the
 *    :class:`CustomEvent` has the following attributes: *li* is the item that has been moved, from
 *    the position directly before the reference item *from* to directly before *to*. If *from* or
 *    *to* is ``null``, it means the end of the list. Thus *from* and *to* may be used in
 *    :func:`Node.insertBefore`.
 */
micro.OL = class extends HTMLOListElement {
    createdCallback() {
        this._li = null;
        this._from = null;
        this._to = null;
        this._over = null;

        this.addEventListener("mousedown", this);
        this.addEventListener("mousemove", this);
        this.addEventListener("touchstart", this);
        this.addEventListener("touchmove", this);
    }

    attachedCallback() {
        window.addEventListener("mouseup", this);
        window.addEventListener("touchend", this);
    }

    detachedCallback() {
        window.removeEventListener("mouseup", this);
        window.removeEventListener("touchend", this);
    }

    handleEvent(event) {
        if (event.currentTarget === this) {
            let handle, x, y, over;
            switch (event.type) {
            case "touchstart":
            case "mousedown":
                // Locate li intended for moving
                handle = micro.findAncestor(event.target,
                                            e => e.classList.contains("micro-ol-handle"), this);
                if (!handle) {
                    break;
                }
                this._li = micro.findAncestor(handle, e => e.parentElement === this, this);
                if (!this._li) {
                    break;
                }

                // Prevent scrolling and text selection
                event.preventDefault();
                this._from = this._li.nextElementSibling;
                this._to = null;
                this._over = this._li;
                this._li.classList.add("micro-ol-li-moving");
                ui.classList.add("micro-ui-dragging");
                break;

            case "touchmove":
            case "mousemove":
                if (!this._li) {
                    break;
                }

                // Locate li the pointer is over
                if (event.type === "touchmove") {
                    x = event.changedTouches[0].clientX;
                    y = event.changedTouches[0].clientY;
                } else {
                    x = event.clientX;
                    y = event.clientY;
                }
                over = micro.findAncestor(document.elementFromPoint(x, y),
                                          e => e.parentElement === this, this);
                if (!over) {
                    break;
                }

                // If the moving li swaps with a larger item, the pointer is still over that item
                // after the swap. We prevent accidently swapping back on the next pointer move by
                // remembering the last item the pointer was over.
                if (over === this._over) {
                    break;
                }
                this._over = over;

                if (this._li.compareDocumentPosition(this._over) &
                        Node.DOCUMENT_POSITION_PRECEDING) {
                    this._to = this._over;
                } else {
                    this._to = this._over.nextElementSibling;
                }
                this.insertBefore(this._li, this._to);
                break;

            default:
                // Unreachable
                throw new Error();
            }

        } else if (event.currentTarget === window &&
                   ["touchend", "mouseup"].indexOf(event.type) !== -1) {
            if (!this._li) {
                return;
            }

            this._li.classList.remove("micro-ol-li-moving");
            ui.classList.remove("micro-ui-dragging");
            if (this._to !== this._from) {
                event = new CustomEvent("moveitem",
                                        {detail: {li: this._li, from: this._from, to: this._to}});
                if (this.onmoveitem) {
                    this.onmoveitem(event);
                }
                this.dispatchEvent(event);
            }
            this._li = null;
        }
    }
};

/**
 * Button with an associated action that runs on click.
 *
 * While an action is running, the button is suspended, i.e. it shows a progress indicator and is
 * not clickable.
 *
 * .. attribute:: run
 *
 *    Hook function of the form *run()*, which performs the associated action. If it returns a
 *    promise, the button will be suspended until the promise resolves.
 */
micro.Button = class extends HTMLButtonElement {
    createdCallback() {
        this.run = null;
        this.addEventListener("click", event => {
            if (this.form && this.type === "submit") {
                if (this.form.checkValidity()) {
                    // Prevent default form submission
                    event.preventDefault();
                } else {
                    // Do not trigger the action and let the default validation handling kick in
                    return;
                }
            }
            this.trigger().catch(micro.util.catch);
        });
    }

    /**
     * Trigger the button.
     *
     * The associated action is run and a promise is returned which resolves to the result of
     * :attr:`run`.
     */
    async trigger() {
        if (!this.run) {
            return undefined;
        }

        let i = this.querySelector("i");
        let progressI;
        this.disabled = true;
        if (i) {
            progressI = document.createElement("i");
            progressI.className = "fa fa-spinner fa-spin";
            i.insertAdjacentElement("afterend", progressI);
            // TODO via class and style
            i.style.display = "none";
        }
        try {
            return await Promise.resolve(this.run());
        } finally {
            this.disabled = false;
            if (i) {
                progressI.remove();
                // TODO via class and style
                i.style.display = "";
            }
        }
    }
};

/**
 * Menu containing actions and / or links.
 *
 * Menus can be nested, in which case submenus are hidden by default and expanded on focus or hover.
 *
 * The following example illustrates the markup for a typical menu::
 *
 *    <ul is="micro-menu">
 *        <li><button class="action">Do this</button></li>
 *        <li><a class="link" href="/">Something</a></li>
 *        <li>
 *            <button class="link">More</button>
 *            <ul is="micro-menu">
 *                <li><button class="action">Do that</button></li>
 *            </ul>
 *        </li>
 *    </ul>
 */
micro.Menu = class extends HTMLUListElement {
    attachedCallback() {
        let expand = event => {
            let li = Array.from(this.children).find(elem => elem.contains(event.target));
            if (["focus", "blur"].includes(event.type) && li.contains(event.relatedTarget)) {
                return;
            }
            li.classList.toggle("micro-menu-expanded",
                                ["mouseenter", "focus"].includes(event.type));
        };

        for (let li of Array.from(this.children)) {
            if (li.lastElementChild instanceof micro.Menu) {
                li.addEventListener("mouseenter", expand);
                li.addEventListener("mouseleave", expand);
                let items = Array.from(li.querySelectorAll("a, button, [tabindex]"));
                for (let item of items) {
                    item.addEventListener("focus", expand);
                    item.addEventListener("blur", expand);
                }
            }
        }
    }
};

/**
 * Options for an `input` field.
 *
 * Attaches itself to the preceding sibling `input` and presents a list of options to the user,
 * based on their input.
 *
 * Content may include a `template` that is used to render an individual option, bound as *option*.
 * By default an option is shown as simple text. Arbitrary content can be placed in the `footer`
 * slot.
 *
 * .. attribute: delay
 *
 *    Time to wait in milliseconds after user input before generating the selection of options.
 *    Defaults to `0`.
 *
 * .. describe:: select
 *
 *    Fired when the user selects an *option*.
 */
micro.OptionsElement = class extends HTMLElement {
    createdCallback() {
        this.delay = 0;
        this._input = null;
        this._options = [];
        this._limit = 5;
        this._toText = option => option.toString();
        this._job = null;
        Object.defineProperty(this, "onselect", micro.util.makeOnEvent("select"));

        let template = this.querySelector("template:not([name])");
        let footerTemplate = this.querySelector("template[name=footer]");

        this.appendChild(
            document.importNode(document.querySelector("#micro-options-template").content, true)
        );
        this._data = new micro.bind.Watchable({
            options: [],
            template,
            footerTemplate,
            active: false,
            generating: false,
            toText: (ctx, option) => this._toText(option),

            onClick: option => {
                this._input.value = this._toText(option);
                if ("valueAsObject" in this._input) {
                    this._input.valueAsObject = option;
                }
                this.deactivate();
                this.dispatchEvent(new CustomEvent("select", {detail: {option}}));
            }
        });
        micro.bind.bind(this.children, this._data);

        let update = () => {
            this.classList.toggle(
                "micro-options-has-footer", this._data.footerTemplate || this._data.generating
            );
            this.classList.toggle("micro-options-active", this._data.active);
            this.classList.toggle("micro-options-generating", this._data.generating);
        };
        ["footerTemplate", "active", "generating"].forEach(prop => this._data.watch(prop, update));
        update();

        // The input should not loose focus when interacting with the options
        this.addEventListener("mousedown", event => event.preventDefault());
    }

    attachedCallback() {
        this._input = this.previousElementSibling;
        this._input.autocomplete = "off";
        this._input.addEventListener(
            "input", () => {
                if (!this._data.active) {
                    this._data.active = true;
                }
                if (this._job) {
                    return;
                }
                this._data.generating = true;
                this._job = setTimeout(
                    () => {
                        this._job = null;
                        (async() => {
                            await this._updateOptions();
                            if (this._job) {
                                this._data.generating = true;
                            }
                        })().catch(micro.util.catch);
                    },
                    this.delay
                );
            }
        );
        this._input.addEventListener("focus", () => this.activate());
        // Listen for mouseup to prevent reopening if the element is inside a label (as clicking on
        // label content will trigger a click event on the input)
        this._input.addEventListener("mouseup", () => this.activate());
        this._input.addEventListener("blur", () => this.deactivate());
    }

    /**
     * Pool of predefined options. Only options which (partially) match the user input are
     * presented.
     *
     * Alternatively, may be a function of the form `options(query, limit)` that dynamically
     * generates a list of options to present from the user input *query*. *limit* is the maximum
     * number of results. May be async.
     *
     * An option may be an arbitrary object. If a text representation is needed (e.g. for input
     * matching), :attr:`toText` is used.
     */
    get options() {
        return this._options;
    }

    set options(value) {
        this._options = value;
        this._updateOptions().catch(micro.util.catch);
    }

    /** Maximum number of presented options. Defaults to `5`. */
    get limit() {
        return this._limit;
    }

    set limit(value) {
        this._limit = value;
        this._updateOptions().catch(micro.util.catch);
    }

    /**
     * Function of the form *toText(option)* that returns a text representation of *option*. By
     * default :meth:`Object.toString()` is called.
     */
    get toText() {
        return this._toText;
    }

    set toText(value) {
        this._toText = value;
        this._updateOptions().catch(micro.util.catch);
    }

    /** Activate, i.e. show the element. */
    activate() {
        this._data.active = true;
        this._updateOptions().catch(micro.util.catch);
    }

    /** Deactivate, i.e. hide the element. */
    deactivate() {
        this._data.active = false;
    }

    async _updateOptions() {
        if (!this._data.active) {
            return;
        }
        this._data.generating = true;
        let generate = (query, limit) => this.options.filter(
            option => this._toText(option).toLowerCase().includes(query.trim().toLowerCase())
        ).slice(0, limit);
        if (this.options instanceof Function) {
            generate = this.options;
        }
        const query = this._input.readOnly ? "" : this._input.value;
        this._data.options = await Promise.resolve(generate(query, this._limit));
        this._data.generating = false;
    }
};
document.registerElement("micro-options", micro.OptionsElement);

/**
 * Simple map for visualizing locations.
 *
 * Map data is provided by Mapbox. :attr:`micro.UI.mapServiceKey` must be set.
 *
 * .. attribute:: ready
 *
 *    Promise that resolves once the map is ready.
 */
micro.MapElement = class extends HTMLElement {
    createdCallback() {
        this.ready = new micro.util.PromiseWhen();
        this._map = null;
        this._locations = null;
        this._markers = [];
        this._iconDim = null;
        this._leaflet = null;

        this._onNavigate = () => {
            (async () => {
                await this.ready;
                if (this._locations) {
                    let loc = this._locations.find(item => item.hash === location.hash.slice(1));
                    if (loc) {
                        this._updateView();
                        this.querySelector(`#${loc.hash}`).focus();
                    }
                }
            })().catch(micro.util.catch);
        };

        this.appendChild(
            document.importNode(document.querySelector("#micro-map-template").content, true)
        );
    }

    attachedCallback() {
        let height = parseInt(getComputedStyle(this).fontSize) * 2;
        let width = height * 3 / 4;
        this._iconDim = {
            size: [width, height],
            anchor: [width / 2, height]
        };

        ui.addEventListener("navigate", this._onNavigate);

        this.ready.when((async() => {
            micro.util.importCSS(document.head.querySelector("link[rel=leaflet-stylesheet]").href)
                .catch(micro.util.catch);
            this._leaflet = await micro.util.import(
                document.head.querySelector("link[rel=leaflet-script]").href, "L"
            );

            this._map = this._leaflet.map(
                this.querySelector("div"),
                {
                    attributionControl: false,
                    zoomControl: false,
                    boxZoom: false,
                    inertia: false,
                    maxBounds: [[-90, -180], [90, 180]]
                }
            );
            this._leaflet.control.attribution({prefix: false, position: "bottomright"})
                .addTo(this._map);

            let url = `https://api.mapbox.com/v4/mapbox.light/{z}/{x}/{y}.png?access_token=${ui.mapServiceKey}`;
            let attribution = document.importNode(
                ui.querySelector("#micro-map-attribution-template").content, true
            ).firstElementChild.innerHTML;
            this._leaflet.tileLayer(url, {attribution, noWrap: true}).addTo(this._map);

            this._updateView();
        })().catch(micro.util.catch));
    }

    detachedCallback() {
        ui.removeEventListener("navigate", this._onNavigate);
    }

    /**
     * List of locations shown on the map.
     *
     * A location here is a :ref:`Location` with two additional properties: *url* is the URL the
     * associated marker links to and *hash* is the marker's :attr:`Element.id` (may be `null`).
     *
     * If :class:`Watchable`, the map will be updated live whenever the array changes.
     */
    get locations() {
        return this._locations;
    }

    set locations(value) {
        let add = (i, loc) => {
            if (!loc.coords) {
                throw new Error("missing-coords-in-locations");
            }
            let a = document.importNode(
                document.querySelector("#micro-map-marker-template").content, true
            ).firstElementChild;
            micro.bind.bind(a, {location: loc});
            let icon = this._leaflet.divIcon({
                html: a.innerHTML,
                iconSize: this._iconDim.size,
                iconAnchor: this._iconDim.anchor
            });
            let marker = this._leaflet.marker(loc.coords, {icon, keyboard: false})
                .addTo(this._map);
            this._markers.splice(i, 0, marker);
            this._updateView();
        };

        let remove = i => {
            this._markers.splice(i, 1)[0].remove();
            this._updateView();
        };

        this._locations = value;

        (async() => {
            await this.ready;
            this._markers.forEach(marker => marker.remove());
            this._markers = [];

            if (value) {
                if (value.watch) {
                    value.watch(Symbol.for("*"), (prop, loc) => {
                        let i = parseInt(prop);
                        remove(i);
                        add(i, loc);
                    });
                    value.watch(Symbol.for("+"), (prop, loc) => add(parseInt(prop), loc));
                    value.watch(Symbol.for("-"), prop => remove(parseInt(prop)));
                }
                Array.from(value.entries()).forEach(([i, loc]) => add(i, loc));
            }

            this._updateView();
        })().catch(micro.util.catch);
    }

    _updateView() {
        if (this._locations && this._locations.length > 1) {
            let padding = parseInt(getComputedStyle(this).fontSize) * 0.375;
            this._map.fitBounds(
                this._locations.map(loc => loc.coords),
                {
                    paddingTopLeft:
                        [this._iconDim.anchor[0] + padding, this._iconDim.anchor[1] + padding],
                    paddingBottomRight: [this._iconDim.anchor[0] + padding, padding],
                    animate: false
                }
            );
        } else {
            this._map.fitWorld({animate: false});
            this._map.zoomIn(1, {animate: false});
        }
    }
};
document.registerElement("micro-map", micro.MapElement);

/**
 * Input for entering a location, e.g. an address or POI.
 *
 * When converting text to a :ref:`Location`, *name* matches the input value. Additionally *coords*
 * are set if the input value represents geographic coordinates (ISO-6709-like). On :ref:`Location`
 * to text conversion, *name* is used.
 *
 * Mapbox is used for geocoding. :attr:`micro.UI.mapServiceKey` must be set.
 *
 * .. attribute:: nativeInput
 *
 *    Wrapped :class:`HTMLInputElement`. It has an additional property *wrapper* pointing back to
 *    this element.
 */
micro.LocationInputElement = class extends HTMLElement {
    createdCallback() {
        this._valueAsObject = null;

        this.appendChild(
            document.importNode(
                document.querySelector("#micro-location-input-template").content, true
            )
        );
        this._data = new micro.bind.Watchable({
            async queryLocations(query, limit) {
                if (!query) {
                    return [];
                }
                let limitArg;
                try {
                    // Reverse geocoding
                    query = micro.util.parseCoords(query).reverse().join(",");
                    limitArg = 0;
                } catch (e) {
                    if (!(e instanceof SyntaxError || e instanceof RangeError)) {
                        throw e;
                    }
                    // Forward geocoding
                    // Comma and semicolon are special characters for reverse and batch geocoding
                    query = encodeURIComponent(query.slice(0, 256).replace(/[,;]/ug, " "));
                    limitArg = limit;
                }
                const url = `https://api.mapbox.com/geocoding/v5/mapbox.places/${query}.json?limit=${limitArg}&access_token=${ui.mapServiceKey}`;
                try {
                    const result = await micro.call("GET", url);
                    return result.features.slice(0, limit).map(
                        feature => ({
                            name: feature.matching_place_name || feature.place_name,
                            coords: [
                                feature.geometry.coordinates[1], feature.geometry.coordinates[0]
                            ]
                        })
                    );
                } catch (e) {
                    if (e instanceof micro.NetworkError || e instanceof micro.APIError) {
                        ui.notify("Oops, there was a problem communicating with Mapbox. Please try again in a few moments.");
                        return [];
                    }
                    throw e;
                }
            },

            locationToText(loc) {
                return loc.name;
            }
        });
        micro.bind.bind(this.children, this._data);

        function parse(value) {
            if (!value) {
                return null;
            }
            try {
                return {name: value, coords: micro.util.parseCoords(value)};
            } catch (e) {
                if (!(e instanceof SyntaxError || e instanceof RangeError)) {
                    throw e;
                }
                return {name: value, coords: null};
            }
        }

        this.nativeInput = this.querySelector("input");
        this.nativeInput.wrapper = this;
        this.nativeInput.name = this.getAttribute("name") || "";
        this.nativeInput.placeholder = this.getAttribute("placeholder") || "";
        this.nativeInput.addEventListener("input", () => {
            this._valueAsObject = parse(this.nativeInput.value);
        });

        Object.defineProperty(this.nativeInput, "value", {
            get: Object.getOwnPropertyDescriptor(HTMLInputElement.prototype, "value").get,

            set: value => {
                Object.getOwnPropertyDescriptor(HTMLInputElement.prototype, "value").set.call(
                    this.nativeInput, value
                );
                this._valueAsObject = parse(value);
            }
        });

        Object.defineProperty(this.nativeInput, "valueAsObject", {
            get: () => this._valueAsObject,

            set: value => {
                this._valueAsObject = value;
                Object.getOwnPropertyDescriptor(HTMLInputElement.prototype, "value").set.call(
                    this.nativeInput, value ? value.name : ""
                );
            }
        });
    }

    /**
     * Current value as :ref:`Location`. May be ``null``.
     *
     * .. deprecated:: 0.35.0
     *
     *    Use :attr:`valueAsObject` instead.
     */
    get value() {
        return this.valueAsObject;
    }

    set value(value) {
        this.valueAsObject = value;
    }

    get valueAsObject() {
        return this.nativeInput.valueAsObject;
    }

    set valueAsObject(value) {
        this.nativeInput.valueAsObject = value;
    }

    /** See :attr:`HTMLInputElement.name`. */
    get name() {
        return this.nativeInput.name;
    }

    set name(value) {
        this.nativeInput.name = value;
    }

    /** See :attr:`HTMLInputElement.placeholder`. */
    get placeholder() {
        return this.nativeInput.placeholder;
    }

    set placeholder(value) {
        this.nativeInput.placeholder = value;
    }
};
document.registerElement("micro-location-input", micro.LocationInputElement);

/**
 * User element.
 *
 * .. attribute:: user
 *
 *    Represented :ref:`User`. Initialized from the JSON value of the corresponding HTML attribute,
 *    if present.
 */
micro.UserElement = class extends HTMLElement {
    createdCallback() {
        this._user = null;
        this.appendChild(document.importNode(
            document.querySelector(".micro-user-template").content, true));
        this.classList.add("micro-user");
    }

    get user() {
        return this._user;
    }

    set user(value) {
        this._user = value;
        if (this._user) {
            this.querySelector("span").textContent = this._user.name;
            this.setAttribute("title", this._user.name);
        }
    }
};

/**
 * Page.
 *
 * .. attribute:: ready
 *
 *    Promise that resolves once the page is ready.
 *
 *    Subclass API: :meth:`micro.util.PromiseWhen.when` may be used to signal when the page will be
 *    ready. By default, the page is considered all set after it has been attached to the DOM.
 */
micro.Page = class extends HTMLElement {
    createdCallback() {
        this.ready = new micro.util.PromiseWhen();
        this._caption = null;
    }

    /**
     * .. deprecated:: 0.19.0
     *
     *    Overriding without chaining.
     */
    attachedCallback() {
        setTimeout(
            () => {
                try {
                    this.ready.when(Promise.resolve());
                } catch (e) {
                    // The subclass may call when
                    if (e.message === "already-called-when") {
                        return;
                    }
                    throw e;
                }
            },
            0
        );
    }

    /**
     * Page title. May be ``null``.
     */
    get caption() {
        return this._caption;
    }

    set caption(value) {
        this._caption = value;
        if (this === ui.page) {
            // eslint-disable-next-line no-underscore-dangle
            ui._updateTitle();
        }
    }
};

/** Offline page. */
micro.OfflinePage = class extends micro.Page {
    createdCallback() {
        super.createdCallback();
        this.caption = "Offline";
        this.appendChild(
            document.importNode(ui.querySelector("#micro-offline-page-template").content, true));
    }
};
document.registerElement("micro-offline-page", micro.OfflinePage);

/**
 * Not found page.
 */
micro.NotFoundPage = class extends micro.Page {
    createdCallback() {
        super.createdCallback();
        this.caption = "Not found";
        this.appendChild(document.importNode(
            ui.querySelector(".micro-not-found-page-template").content, true));
    }
};

/**
 * Forbidden page.
 */
micro.ForbiddenPage = class extends micro.Page {
    createdCallback() {
        super.createdCallback();
        this.caption = "Forbidden";
        this.appendChild(document.importNode(
            ui.querySelector(".micro-forbidden-page-template").content, true));
    }
};

/**
 * About page.
 */
micro.AboutPage = class extends micro.Page {
    createdCallback() {
        super.createdCallback();
        this.caption = `About ${ui.settings.title}`;
        this.appendChild(document.importNode(
            ui.querySelector(".micro-about-page-template").content, true));

        let h1 = this.querySelector("h1");
        h1.textContent = h1.dataset.text.replace("{title}", ui.settings.title);
        this.querySelector(".micro-about-short").textContent =
            this.attributes.short.value.replace("{title}", ui.settings.title);

        if (ui.settings.provider_name) {
            let text = "The service is provided by {provider}.";
            let args = {provider: ui.settings.provider_name};
            if (ui.settings.provider_url) {
                let a = document.createElement("a");
                a.classList.add("link");
                a.href = ui.settings.provider_url;
                a.target = "_blank";
                a.textContent = ui.settings.provider_name;
                args.provider = a;
            }
            if (ui.settings.provider_description.en) {
                text = "The service is provided by {provider}, {description}.";
                args.description = ui.settings.provider_description.en;
            }
            this.querySelector(".micro-about-provider").appendChild(
                micro.util.formatFragment(text, args));
        }

        this.querySelector(".micro-about-project").style.display =
            this.getAttribute("project-title") ? "" : "none";
        this.querySelector(".micro-logo a").href = this.getAttribute("project-url");
        this.querySelector(".micro-logo img").src = this.getAttribute("project-icon") || "";
        this.querySelector(".micro-logo span").textContent = this.getAttribute("project-title");
        let a = this.querySelector(".micro-about-project-link");
        a.href = this.getAttribute("project-url");
        a.textContent = this.getAttribute("project-title");
        a = this.querySelector(".micro-about-license");
        a.href = this.getAttribute("project-license-url");
        a.textContent = this.getAttribute("project-license");
        this.querySelector(".micro-about-copyright").textContent =
            this.getAttribute("project-copyright");
    }
};

/**
 * Edit user page.
 */
micro.EditUserPage = class extends micro.Page {
    static async make(url, id) {
        id = id || ui.user.id;
        let user = await ui.call("GET", `/api/users/${id}`);
        if (!(ui.user.id === user.id)) {
            return document.createElement("micro-forbidden-page");
        }
        let page = document.createElement("micro-edit-user-page");
        page.user = user;
        return page;
    }

    createdCallback() {
        super.createdCallback();
        this._user = null;
        this.caption = "Edit user settings";
        this.appendChild(document.importNode(
            ui.querySelector(".micro-edit-user-page-template").content, true));
        this._form = this.querySelector("form");
        this.querySelector(".micro-edit-user-edit").addEventListener("submit", this);

        this._setEmail1 = this.querySelector(".micro-edit-user-set-email-1");
        this._setEmailForm = this.querySelector(".micro-edit-user-set-email-1 form");
        this._setEmail2 = this.querySelector(".micro-edit-user-set-email-2");
        this._emailP = this.querySelector(".micro-edit-user-email-value");
        this._setEmailAction = this.querySelector(".micro-edit-user-set-email-1 form button");
        this._cancelSetEmailAction = this.querySelector(".micro-edit-user-cancel-set-email button");
        this._removeEmailAction = this.querySelector(".micro-edit-user-remove-email");
        this._removeEmailAction.addEventListener("click", this);
        this._setEmailAction.addEventListener("click", this);
        this._cancelSetEmailAction.addEventListener("click", this);
        this._setEmailForm.addEventListener("submit", e => e.preventDefault());
    }

    attachedCallback() {
        super.attachedCallback();
        this.ready.when((async() => {
            let match = /^#set-email=([^:]+):([^:]+)$/u.exec(location.hash);
            if (match) {
                history.replaceState(null, null, location.pathname);
                let authRequestID = `AuthRequest:${match[1]}`;
                let authRequest = JSON.parse(localStorage.authRequest || null);
                if (!authRequest || authRequestID !== authRequest.id) {
                    ui.notify(
                        "The email link was not opened on the same browser/device on which the email address was entered (or the email link is outdated).");
                    return;
                }

                this._showSetEmailPanel2(true);
                try {
                    this.user = await ui.call(
                        "POST", `/api/users/${this._user.id}/finish-set-email`, {
                            auth_request_id: authRequest.id,
                            auth: match[2]
                        });
                    delete localStorage.authRequest;
                    this._hideSetEmailPanel2();
                } catch (e) {
                    if (e instanceof micro.APIError && e.__type__ === "ValueError") {
                        if (e.error.code === "auth_invalid") {
                            this._showSetEmailPanel2();
                            ui.notify("The email link was modified. Please try again.");
                        } else {
                            delete localStorage.authRequest;
                            this._hideSetEmailPanel2();
                            ui.notify({
                                auth_request_not_found:
                                    "The email link is expired. Please try again.",
                                email_duplicate:
                                    "The given email address is already in use by another user."
                            }[e.error.code]);
                        }
                    } else {
                        ui.handleCallError(e);
                    }
                }
            }
        })().catch(micro.util.catch));
    }

    /**
     * :ref:`User` to edit.
     */
    get user() {
        return this._user;
    }

    set user(value) {
        this._user = value;
        this.classList.toggle("micro-edit-user-has-email", this._user.email);
        this._form.elements.name.value = this._user.name;
        this._emailP.textContent = this._user.email;
    }

    async _setEmail() {
        if (!this._setEmailForm.checkValidity()) {
            return;
        }

        try {
            let authRequest = await ui.call("POST", `/api/users/${this.user.id}/set-email`, {
                email: this._setEmailForm.elements.email.value
            });
            localStorage.authRequest = JSON.stringify(authRequest);
            this._setEmailForm.reset();
            this._showSetEmailPanel2();
        } catch (e) {
            ui.handleCallError(e);
        }
    }

    _cancelSetEmail() {
        this._hideSetEmailPanel2();
    }

    async _removeEmail() {
        try {
            this.user = await ui.call("POST", `/api/users/${this.user.id}/remove-email`);
        } catch (e) {
            if (e instanceof micro.APIError && e.__type__ === "ValueError") {
                // If the email address has already been removed, we just update the UI
                this.user.email = null;
                this.user = this.user;
            } else {
                ui.handleCallError(e);
            }
        }
    }

    _showSetEmailPanel2(progress) {
        progress = progress || false;
        let progressP = this.querySelector(".micro-edit-user-set-email-2 .micro-progress");
        let actions = this.querySelector(".micro-edit-user-cancel-set-email");
        this._emailP.style.display = "none";
        this._setEmail1.style.display = "none";
        this._setEmail2.style.display = "block";
        if (progress) {
            progressP.style.display = "";
            actions.style.display = "none";
        } else {
            progressP.style.display = "none";
            actions.style.display = "";
        }
    }

    _hideSetEmailPanel2() {
        this._emailP.style.display = "";
        this._setEmail1.style.display = "";
        this._setEmail2.style.display = "";
    }

    handleEvent(event) {
        if (event.currentTarget === this._form) {
            event.preventDefault();
            (async() => {
                try {
                    let user = await ui.call("POST", `/api/users/${this._user.id}`, {
                        name: this._form.elements.name.value
                    });
                    ui.dispatchEvent(new CustomEvent("user-edit", {detail: {user}}));
                } catch (e) {
                    if (e instanceof micro.APIError && e.error.__type__ === "InputError") {
                        ui.notify("The name is missing.");
                    } else {
                        ui.handleCallError(e);
                    }
                }
            })().catch(micro.util.catch);

        } else if (event.currentTarget === this._setEmailAction && event.type === "click") {
            this._setEmail().catch(micro.util.catch);
        } else if (event.currentTarget === this._cancelSetEmailAction && event.type === "click") {
            this._cancelSetEmail();
        } else if (event.currentTarget === this._removeEmailAction && event.type === "click") {
            this._removeEmail().catch(micro.util.catch);
        }
    }
};

/**
 * Edit settings page.
 */
micro.EditSettingsPage = class extends micro.Page {
    static make() {
        if (!ui.staff) {
            return document.createElement("micro-forbidden-page");
        }
        return document.createElement("micro-edit-settings-page");
    }

    createdCallback() {
        super.createdCallback();
        this.caption = "Edit site settings";
        this.appendChild(
            document.importNode(ui.querySelector(".micro-edit-settings-page-template").content,
                                true));
        this._data = {
            settings: ui.settings,

            edit: async() => {
                function toStringOrNull(str) {
                    return str.trim() ? str : null;
                }

                let form = this.querySelector("form");
                let description = toStringOrNull(form.elements.provider_description.value);
                description = description ? {en: description} : {};

                try {
                    let settings = await ui.call("POST", "/api/settings", {
                        title: form.elements.title.value,
                        icon: form.elements.icon.value,
                        icon_small: form.elements.icon_small.value,
                        icon_large: form.elements.icon_large.value,
                        provider_name: form.elements.provider_name.value,
                        provider_url: form.elements.provider_url.value,
                        provider_description: description,
                        feedback_url: form.elements.feedback_url.value
                    });
                    ui.navigate("/").catch(micro.util.catch);
                    micro.util.dispatchEvent(ui,
                                             new CustomEvent("settings-edit", {detail: {settings}}));
                } catch (e) {
                    ui.handleCallError(e);
                }
            }
        };
        micro.bind.bind(this.children, this._data);
    }
};

micro.ActivityPage = class extends micro.Page {
    static make() {
        if (!ui.staff) {
            return document.createElement("micro-forbidden-page");
        }
        return document.createElement("micro-activity-page");
    }

    createdCallback() {
        super.createdCallback();
        this.caption = "Site activity";
        this.appendChild(document.importNode(
            ui.querySelector(".micro-activity-page-template").content, true));
        this._showMoreButton = this.querySelector("button");
        this._showMoreButton.run = this._showMore.bind(this);
        this._start = 0;
    }

    attachedCallback() {
        super.attachedCallback();
        this.ready.when(this._showMoreButton.trigger().catch(micro.util.catch));
    }

    async _showMore() {
        let events;
        try {
            events = await ui.call("GET", `/api/activity/v2/${this._start}:`);
        } catch (e) {
            ui.handleCallError(e);
            return;
        }

        let ul = this.querySelector(".micro-timeline");
        for (let event of events.items) {
            let li = document.createElement("li");
            let time = document.createElement("time");
            time.dateTime = event.time;
            time.textContent = micro.bind.transforms.formatDate(
                null, event.time, micro.bind.transforms.SHORT_DATE_TIME_FORMAT
            );
            li.appendChild(time);
            li.appendChild(ui.renderEvent[event.type](event));
            ul.appendChild(li);
        }
        this.classList.toggle("micro-activity-all", events.items.length < micro.LIST_LIMIT);
        this._start += micro.LIST_LIMIT;
    }
};

Object.assign(micro.bind.transforms, {
    SHORT_DATE_FORMAT: {
        year: "numeric",
        month: "short",
        day: "numeric"
    },

    SHORT_DATE_TIME_FORMAT: {
        year: "numeric",
        month: "short",
        day: "numeric",
        hour: "2-digit",
        minute: "2-digit"
    },

    /**
     * Render *markup text* into a :class:`DocumentFragment`.
     *
     * HTTP(S) URLs are automatically converted to links.
     */
    markup(ctx, text) {
        if (!text) {
            return document.createDocumentFragment();
        }

        const patterns = {
            // Do not capture trailing whitespace because of link pattern
            item: "(^[^\\S\n]*[*+-](?=\\s|$))",
            strong: "\\*\\*(.+?)\\*\\*",
            em: "\\*(.+?)\\*",
            // Work around missing look behind by capturing whitespace
            link: "(^|[\\s!-.:-@])(https?://.+?)(?=[!-.:-@]?(\\s|$))"
        };
        const pattern = new RegExp(
            `${patterns.item}|${patterns.strong}|${patterns.em}|${patterns.link}`, "ugm"
        );

        const fragment = document.createDocumentFragment();
        let match;
        do {
            const skipStart = pattern.lastIndex;
            match = pattern.exec(text);
            const skipStop = match ? match.index : text.length;
            if (skipStop > skipStart) {
                fragment.appendChild(document.createTextNode(text.slice(skipStart, skipStop)));
            }
            if (match) {
                const [, item, strong, em, linkPrefix, linkURL] = match;
                if (item) {
                    fragment.appendChild(document.createTextNode("\u00a0•"));
                } else if (strong) {
                    const elem = document.createElement("strong");
                    elem.textContent = strong;
                    fragment.appendChild(elem);
                } else if (em) {
                    const elem = document.createElement("em");
                    elem.textContent = em;
                    fragment.appendChild(elem);
                } else if (linkURL) {
                    if (linkPrefix) {
                        fragment.appendChild(document.createTextNode(linkPrefix));
                    }
                    const a = document.createElement("a");
                    a.classList.add("link");
                    a.href = linkURL;
                    a.target = "_blank";
                    a.textContent = linkURL;
                    fragment.appendChild(a);
                } else {
                    // Unreachable
                    throw new Error();
                }
            }
        } while (match);
        return fragment;
    },

    /**
     * Fetch the next *n* items for *collection*.
     *
     * Wrapper around :meth:`Collection.fetch` that handles common call errors.
     */
    async fetchCollection(collection, n = micro.LIST_LIMIT) {
        try {
            await collection.fetch(n);
        } catch (e) {
            ui.handleCallError(e);
        }
    },

    /** Render the given web :ref:`Resource` *resource*. */
    renderResource(ctx, resource) {
        if (!resource) {
            return "";
        }
        let elem;
        switch (resource.__type__) {
        case "Image":
            elem = document.createElement("micro-image");
            elem.image = resource;
            break;
        case "Video":
            elem = document.createElement("micro-video");
            elem.video = resource;
            break;
        default:
            elem = document.createElement("micro-link");
            console.log(micro.components);
            elem.resource = resource;
            break;
        }
        return elem;
    },

    ShortcutContext: micro.keyboard.ShortcutContext,
    Shortcut: micro.keyboard.Shortcut
});

document.registerElement("micro-ui", {prototype: micro.UI.protoype, extends: "body"});
document.registerElement("micro-simple-notification", micro.SimpleNotification);
document.registerElement("micro-error-notification", micro.ErrorNotification);
document.registerElement("micro-ol", {prototype: micro.OL.prototype, extends: "ol"});
document.registerElement("micro-button", {prototype: micro.Button.prototype, extends: "button"});
document.registerElement("micro-menu", {prototype: micro.Menu.prototype, extends: "ul"});
document.registerElement("micro-user", micro.UserElement);
document.registerElement("micro-page", micro.Page);
document.registerElement("micro-not-found-page", micro.NotFoundPage);
document.registerElement("micro-forbidden-page", micro.ForbiddenPage);
document.registerElement("micro-about-page", micro.AboutPage);
document.registerElement("micro-edit-user-page", micro.EditUserPage);
document.registerElement("micro-edit-settings-page", micro.EditSettingsPage);
document.registerElement("micro-activity-page", micro.ActivityPage);
