/*
 * keyboard.js
 * Released into the public domain
 * https://github.com/noyainrain/micro/blob/master/client/keyboard.js
 */

/** Utilities for keyboard navigation. */

"use strict";

window.micro = window.micro || {};
micro.keyboard = {};

/**
 * Extension for :class:`Element` serving as context for keyboard shortcuts.
 *
 * Shortcuts can be registered to the context and are triggered if the element or any child has
 * focus.
 *
 * .. attribute:: elem
 *
 *    Extended element.
 */
micro.keyboard.ShortcutContext = class {
    constructor(elem) {
        this.elem = elem;
        this._shortcuts = new Map();
        this._prefixes = new Set();
        this._prefix = null;

        function toKeyString(event) {
            // Normalize letter case
            const key = event.key.length === 1 ? event.key.toUpperCase() : event.key;
            // Consume Shift for symbols
            const shift = event.shiftKey && !(key.length === 1 && key === key.toLowerCase());
            return `${event.altKey ? "Alt+" : ""}${event.ctrlKey ? "Control+" : ""}${event.metaKey ? "Meta+" : ""}${shift ? "Shift+" : ""}${key}`;
        }

        this.elem.addEventListener("keydown", event => {
            // Work around Chrome dispatching KeybordEvent with undefined key (see
            // https://bugs.chromium.org/p/chromium/issues/detail?id=904420)
            if (!event.key) {
                return;
            }
            if (!this._prefix) {
                return;
            }
            event.stopPropagation();
            event.preventDefault();
            event.captured = true;
            let key = `${this._prefix},${toKeyString(event)}`;
            this._prefix = null;
            if (this._shortcuts.has(key)) {
                this.trigger(key);
            }
        }, true);

        this.elem.addEventListener("keydown", event => {
            // Work around Chrome dispatching KeybordEvent with undefined key (see
            // https://bugs.chromium.org/p/chromium/issues/detail?id=904420)
            if (!event.key) {
                return;
            }
            // If the event reaches us in the target phase, both listeners are called, irrespective
            // of stopPropagation. Ignore the event if it has been marked as handled by the capture
            // listener.
            if (event.captured) {
                return;
            }
            if (["INPUT", "TEXTAREA", "SELECT"].includes(event.target.tagName) &&
                    event.key.length === 1) {
                return;
            }
            let key = toKeyString(event);
            if (this._prefixes.has(key)) {
                event.stopPropagation();
                event.preventDefault();
                this._prefix = key;
            } else if (this._shortcuts.has(key)) {
                event.stopPropagation();
                event.preventDefault();
                this.trigger(key);
            }
        });
    }

    /**
     * Add a shortcut *key*.
     *
     * *key* is a key string, meaning a
     * `key identifier <https://developer.mozilla.org/en-US/docs/Web/API/KeyboardEvent/key/Key_Values>`_,
     * letter (upper case) or symbol, prefixed with any modifier (``Alt``, ``Control``, ``Meta`` and
     * ``Shift``, in the given order), separated by ``+``. For symbols, ``Shift`` is not applicable,
     * as the character is determined by the modifier (e.g. ``/`` and ``?``). Examples of valid key
     * strings are ``A``, ``Shift+A``, ``?`` or ``Control+Shift+Enter``.
     *
     * *handle* is a function of the form ``handle(key, context)``, where *key* is the pressed key
     * and *context* refers to the shortcut context.
     */
    add(key, handle) {
        this._shortcuts.set(key, handle);
        this._updatePrefixes();
    }

    /** Remove the shortcut *key*. */
    remove(key) {
        this._shortcuts.delete(key);
        this._updatePrefixes();
    }

    /** Trigger the shortcut for *key*. */
    trigger(key) {
        this._shortcuts.get(key)(key, this);
    }

    _updatePrefixes() {
        function getPrefix(key) {
            let keys = key.split(",");
            return keys.length > 1 ? keys[0] : null;
        }
        this._prefixes =
            new Set(Array.from(this._shortcuts.keys(), getPrefix).filter(prefix => prefix));
    }
};

/**
 * Extension for :class:`Element` that can be activated with an associated keyboard shortcut.
 *
 * .. attribute:: elem
 *
 *    Extended element.
 *
 * .. attribute: key
 *
 *    Associated key string (see :meth:`ShortcutContext.add`).
 *
 * .. attribute: title
 *
 *    Original element title, which is supplemented with information about the shortcut key. May be
 *    ``null``.
 *
 * .. attribute: context
 *
 *    Parent :class:`ShortcutContext`. May be ``null``.
 */
micro.keyboard.Shortcut = class {
    constructor(elem, key, title = null) {
        this.elem = elem;
        this.key = key;
        this.title = title;
        this.context = null;

        let info = `⌨ ${key.replace("+", " + ").replace(",", " then ")}`;
        this.elem.title = title ? `${title} (${info})` : info;

        micro.keyboard.watchLifecycle(this.elem, {
            onConnect: () => {
                this.context =
                    micro.keyboard.findAncestor(this.elem, e => e.shortcutContext).shortcutContext;
                this.context.add(this.key, () => {
                    // Activate only if element is available / visible
                    if (this.elem.offsetParent) {
                        this.elem.click();
                    }
                });
            },
            onDisconnect: () => this.context.remove(this.key)
        });
    }
};

/**
 * Navigate to, i.e. focus, the next (or previous) element available for quick navigation.
 *
 * The direction is given by *dir* (``next`` or ``prev``). Taking part in quick navigation are all
 * elements marked with the class ``micro-quick-nav``.
 */
micro.keyboard.quickNavigate = function(dir = "next") {
    let elems = Array.from(document.querySelectorAll(".micro-quick-nav"));
    if (dir === "prev") {
        elems.reverse();
    }
    if (document.activeElement !== document.body) {
        let pos = dir === "next" ? Node.DOCUMENT_POSITION_FOLLOWING
            : Node.DOCUMENT_POSITION_PRECEDING;
        elems = elems.filter(e => document.activeElement.compareDocumentPosition(e) & pos);
    }
    for (let elem of elems) {
        elem.focus();
        if (document.activeElement === elem) {
            return;
        }
    }
    document.activeElement.blur();
};

/**
 * Watch the lifecycle of an :class:`Element` *elem*.
 *
 * *onConnect* and *onDisconnect* are functions of the form ``function(elem)``, where *elem* is the
 * watched element. Each is called exactly once, when the element is connected to the DOM and when
 * it is disconnected, respectivly. If *elem* is already connected, *onConnect* is called instantly.
 * After *elem* has been disconnected, it will be no longer watched.
 */
micro.keyboard.watchLifecycle = function(elem, {onConnect, onDisconnect}) {
    /* eslint-disable no-underscore-dangle */
    let self = micro.keyboard.watchLifecycle;
    if (!self._elems) {
        self._elems = new Map();
        let observer = new MutationObserver(() => {
            for (let [node, meta] of self._elems.entries()) {
                let connected = document.body.contains(node);
                if (!meta.connected && connected) {
                    meta.connected = true;
                    for (let watcher of meta.watchers) {
                        if (watcher.onConnect) {
                            watcher.onConnect(node);
                        }
                    }
                } else if (meta.connected && !connected) {
                    self._elems.delete(node);
                    for (let watcher of meta.watchers) {
                        if (watcher.onDisconnect) {
                            watcher.onDisconnect(node);
                        }
                    }
                }
            }
        });
        observer.observe(document.body, {childList: true, subtree: true});
    }

    let meta = self._elems.get(elem);
    if (!meta) {
        meta = {connected: document.body.contains(elem), watchers: []};
        self._elems.set(elem, meta);
    }
    meta.watchers.push({onConnect, onDisconnect});
    if (meta.connected) {
        onConnect(elem);
    }
    /* eslint-enable no-underscore-dangle */
};

/**
 * Enable the ``micro-activated`` pseudo-class.
 *
 * The class is applied to an element that has just been activated. An element is considered
 * just activated until it looses focus.
 */
micro.keyboard.enableActivatedClass = function() {
    /* eslint-disable no-underscore-dangle */
    let self = micro.keyboard.enableActivatedClass;
    if (!self._applyClass) {
        self._applyClass = event => {
            let elem = micro.keyboard.findAncestor(event.target, e => e.tabIndex !== -1);
            if (elem && !elem.classList.contains("micro-activated")) {
                elem.classList.add("micro-activated");
                elem.addEventListener("blur", () => elem.classList.remove("micro-activated"),
                                      {once: true});
            }
        };
        addEventListener("mousedown", self._applyClass);
        addEventListener("click", self._applyClass);
    }
    /* eslint-enable no-underscore-dangle */
};

/**
 * Find the first ancestor of *elem* that satisfies *predicate*.
 *
 * If no ancestor is found, ``undefined`` is returned. The function *predicate(elem)* returns
 * ``true`` if *elem* fullfills the desired criteria, ``false`` otherwise. It is called for any
 * ancestor of *elem*, from its parent up until (excluding) *top* (defaults to
 * ``document.documentElement``).
 */
micro.keyboard.findAncestor = function(elem, predicate, top) {
    top = top || document.documentElement;
    for (let e = elem; e && e !== top; e = e.parentElement) {
        if (predicate(e)) {
            return e;
        }
    }
    return undefined;
};
