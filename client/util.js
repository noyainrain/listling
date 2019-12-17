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
 * Various utilities.
 */

"use strict";

self.micro = self.micro || {};
micro.util = {};

/** Thrown if network communication failed. */
micro.NetworkError = class NetworkError extends TypeError {};

/**
 * Thrown for HTTP JSON REST API errors.
 *
 * .. attribute:: error
 *
 *    The error object.
 *
 * .. attribute:: status
 *
 *    The associated HTTP status code.
 */
micro.APIError = class APIError extends Error {
    constructor(error, status) {
        super(`${error.__type__}: ${error.message}`);
        this.error = error;
        this.status = status;
    }
};

/**
 * Call a *method* on the HTTP JSON REST API endpoint at *url*.
 *
 * *method* is a HTTP method (e.g. ``GET`` or ``POST``). Arguments are passed as JSON object *args*.
 * A promise is returned that resolves to the result as JSON value, once the call is complete.
 *
 * If an error occurs, the promise rejects with an :class:`APIError`. For any IO related errors, it
 * rejects with a :class:`micro.NetworkError`.
 *
 * .. deprecated:: 0.19.0
 *
 *    :class:`TypeError` for IO related errors. Check for :class:`micro.NetworkError` instead.
 */
micro.call = async function(method, url, args) {
    let options = {method, credentials: "same-origin"};
    if (args) {
        options.headers = {"Content-Type": "application/json"};
        options.body = JSON.stringify(args);
    }

    let response;
    let result;
    try {
        response = await fetch(url, options);
        result = await response.json();
    } catch (e) {
        if (e instanceof TypeError) {
            throw new micro.NetworkError(`${e.message} for ${method} ${url}`);
        } else if (e instanceof SyntaxError) {
            throw new micro.NetworkError(`Bad response format for ${method} ${url}`);
        }
        throw e;
    }
    if (!response.ok) {
        throw new micro.APIError(result, response.status);
    }
    return result;
};

/**
 * Promise that resolves when another given promise is done.
 *
 * .. method:: when(promise)
 *
 *    Resolve once *promise* is fulfilled.
 */
micro.util.PromiseWhen = function() {
    let when = null;
    let p = new Promise(resolve => {
        when = function(promise) {
            if (!resolve) {
                throw new Error("already-called-when");
            }
            resolve(promise);
            resolve = null;
        };
    });
    p.when = when;
    return p;
};

/**
 * Promise which can be aborted.
 *
 * *executor* is a promise executor with an additional argument *signal*, which indicates if the
 * execution should be aborted.
 *
 * .. method:: abort()
 *
 *    Abort the promise.
 */
micro.util.AbortablePromise = function(executor) {
    const signal = {aborted: false};
    const p = new Promise((resolve, reject) => executor(resolve, reject, signal));
    p.abort = () => {
        signal.aborted = true;
    };
    return p;
};

/**
 * Return an asynchronous function which can be aborted.
 *
 * *f* is the asynchronous function to run. It is called with an additional argument *signal*
 * prepended, which indicates if the execution should be aborted.
 */
micro.util.abortable = function(f) {
    return function(...args) {
        return new micro.util.AbortablePromise(
            (resolve, reject, signal) => f(signal, ...args).then(resolve, reject)
        );
    };
};

/**
 * Dispatch an *event* at the specified *target*.
 *
 * If defined, the related on-event handler is called.
 */
micro.util.dispatchEvent = function(target, event) {
    target.dispatchEvent(event);
    let on = target[`on${event.type}`];
    if (on) {
        on.call(target, event);
    }
};

/**
 * Create an on-event handler property for the given event *type*.
 *
 * The returned property can be assigned to an object, for example::
 *
 *    Object.defineProperty(elem, "onmeow", micro.util.makeOnEvent("meow"));
 */
micro.util.makeOnEvent = function(type) {
    let listener = null;
    return {
        get() {
            return listener;
        },

        set(value) {
            if (listener) {
                this.removeEventListener(type, listener);
            }
            listener = value;
            if (listener) {
                this.addEventListener(type, listener);
            }
        }
    };
};

/**
 * Truncate *str* at *length*.
 *
 * A truncated string ends with an ellipsis character.
 */
micro.util.truncate = function(str, length = 16) {
    return str.length > length ? `${str.slice(0, length - 1)}…` : str;
};

/**
 * Convert *str* to a slug, i.e. a human readable URL path segment.
 *
 * All characters are converted to lower case, non-ASCII characters are removed and all
 * non-alphanumeric symbols are replaced with a dash. The slug is limited to *max* characters and
 * prefixed with a single slash (not counting towards the limit). Note that the result is an empty
 * string if *str* does not contain any alphanumeric symbols.
 *
 * Optionally, the computed slug is checked against a list of *reserved* strings, resulting in an
 * empty string if there is a match.
 */
micro.util.slugify = (str, {max = 32, reserved = []} = {}) => {
    let slug = str.replace(/[^\x00-\x7F]/ug, "").toLowerCase().replace(/[^a-z0-9]+/ug, "-")
        .slice(0, max).replace(/^-|-$/ug, "");
    return slug && !reserved.includes(slug) ? `/${slug}` : "";
};

/**
 * Format a string containing placeholders.
 *
 * *str* is a format string with placeholders of the form ``{key}``. *args* is an :class:`Object`
 * mapping keys to values to replace.
 */
micro.util.format = function(str, args) {
    return str.replace(/\{([^}\s]+)\}/ug, (match, key) => args[key]);
};

/**
 * Format a string containing placeholders, producing a :class:`DocumentFragment`.
 *
 * *str* is a format string containing placeholders of the form ``{key}``, where *key* may consist
 * of alpha-numeric characters plus underscores and dashes. *args* is an object mapping keys to
 * values to replace. If a value is a :class:`Node` it is inserted directly into the fragment,
 * otherwise it is converted to a text node first.
 */
micro.util.formatFragment = function(str, args) {
    let fragment = document.createDocumentFragment();
    let pattern = /\{([a-zA-Z0-9_-]+)\}/ug;
    let match = null;

    do {
        let start = pattern.lastIndex;
        match = pattern.exec(str);
        let stop = match ? match.index : str.length;
        if (stop > start) {
            fragment.appendChild(document.createTextNode(str.substring(start, stop)));
        }
        if (match) {
            let arg = args[match[1]];
            if (!(arg instanceof Node)) {
                arg = document.createTextNode(arg);
            }
            fragment.appendChild(arg);
        }
    } while (match);

    return fragment;
};

/**
 * Parse an ISO 6709 representation of geographic coordinates *str* into a latitude-longitude pair.
 *
 * Units and hemisphere indicators are optional. Only latitude and longitude, without elevation, are
 * supported. Additonally, negative coordinates are allowed.
 */
micro.util.parseCoords = function(str) {
    const part = "(\\d+(?:\\.\\d+)?)[^.NSEW]?";
    const coord = `(-)?${part}(?:\\s*${part})?(?:\\s*${part})?(?:\\s*([NSEW]))?`;
    const pattern = new RegExp(`^\\s*${coord}\\s+${coord}\\s*$`, "u");
    const match = str.match(pattern);
    if (!match) {
        throw new SyntaxError(`Bad str format "${str}"`);
    }
    const coords = [match.slice(1, 6), match.slice(6, 11)].map(groups => {
        const [d, m, s] = groups.slice(1, 4).map(p => parseFloat(p) || 0);
        return (d + m / 60 + s / (60 * 60)) * (groups[0] ? -1 : 1) *
            ("SW".includes(groups[4]) ? -1 : 1);
    });
    if (!(coords[0] >= -90 && coords[0] <= 90 && coords[1] >= -180 && coords[1] <= 180)) {
        throw new RangeError(`Out of range str coordinates "${str}"`);
    }
    return coords;
};

/** Return the given CSS *color* with transparency *alpha*. */
micro.util.withAlpha = function(color, alpha) {
    function normalize(c) {
        if (c.length === 4) {
            const value = Array.map(c.slice(1), component => component + component).join("");
            return `#${value}`;
        }
        return c;
    }
    const [r, g, b] = micro.bind.chunk(normalize(color).slice(1), 2)
        .map(component => parseInt(component, 16));
    return `rgba(${r}, ${g}, ${b}, ${alpha})`;
};

/**
 * Import the script located at *url*.
 *
 * *namespace* is the identifier of the namespace (i.e. global variable) created by the imported
 * script, if any. If given, the namespace is returned.
 */
micro.util.import = function(url, namespace = null) {
    // eslint-disable-next-line no-underscore-dangle
    const imports = micro.util.import._imports;
    if (imports.has(url)) {
        return imports.get(url);
    }

    const p = new Promise((resolve, reject) => {
        const script = document.createElement("script");
        script.src = url;
        script.addEventListener("load", () => resolve(window[namespace]));
        script.addEventListener("error", () => {
            script.remove();
            reject(new micro.NetworkError(`Error for GET ${url}`));
        });
        document.head.appendChild(script);
    });

    imports.set(url, p);
    p.catch(() => imports.delete(url));
    return p;
};
// eslint-disable-next-line no-underscore-dangle
micro.util.import._imports = new Map();

/**
 * Import the stylesheet located at *url*.
 */
micro.util.importCSS = function(url) {
    return new Promise((resolve, reject) => {
        let link = document.head.querySelector(`link[rel='stylesheet'][src='${url}']`);
        if (link) {
            resolve();
            return;
        }
        link = document.createElement("link");
        link.rel = "stylesheet";
        link.href = url;
        link.addEventListener("load", resolve);
        link.addEventListener("error", reject);
        document.head.appendChild(link);
    });
};

/**
 * Watch for unhandled exceptions and report them.
 */
micro.util.watchErrors = function() {
    async function report(e) {
        await micro.call("POST", "/log-client-error", {
            type: e.constructor.name,
            // Stack traces may be truncated for security reasons, resulting in an empty string at
            // worst
            stack: e.stack || "?",
            url: location.pathname,
            message: e.message
        });
    }
    addEventListener("error", event => report(event.error));

    /**
     * Catch unhandled rejections.
     *
     * Use it whenever an asynchronous function / :class:`Promise`
     *
     * - Is called without `await`
     * - Is passed to non-micro code
     */
    micro.util.catch = e => {
        report(e);
        throw e;
    };
    // NOTE: Once cross-browser support for unhandled rejection events exists, the above can be
    // replaced with:
    // addEventListener("unhandledrejection", event => {
    //     report(event.reason);
    // });
};
