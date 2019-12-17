/*
 * bind.js
 * Released into the public domain
 * https://github.com/noyainrain/micro/blob/master/client/bind.js
 */

/**
 * Simple data binding.
 */

"use strict";

window.micro = window.micro || {};
micro.bind = {};

/** If ``true``, information about data binding updates is logged. */
micro.bind.trace = false;

/**
 * Wrapper around an object which can be watched for modification.
 *
 * .. attribute:: target
 *
 *    Wrapped :class:`Object`.
 *
 * .. method:: watch(prop, onUpdate)
 *
 *    Watch the property *prop* and call *onUpdate* when it is updated.
 *
 *    *onUpdate* is a function of the form ``onUpdate(prop, value)``, where *prop* is the property
 *    being set to *value*.
 *
 *    In addition to watching a single property, *prop* may also be one of the following special
 *    values:
 *
 *    * ``Symbol.for("*")``: Watch for updates of any property
 *    * ``Symbol.for("+")``: If *target* is an :class:`Array`, get notified when an item is inserted
 *    * ``Symbol.for("-")``: If *target* is an :class:`Array`, get notified when an item is removed
 */
micro.bind.Watchable = function(target = {}) {
    let watchers = {};

    function notify(key, prop, value) {
        (watchers[key] || []).forEach(onUpdate => onUpdate(prop, value));
    }

    let ext = {
        target,

        watch(prop, onUpdate) {
            if (!(prop in watchers)) {
                watchers[prop] = [];
            }
            watchers[prop].push(onUpdate);
        },

        splice(start, deleteCount, ...items) {
            let removed = target.splice(start, deleteCount, ...items);
            for (let [i, item] of Array.from(removed.entries()).reverse()) {
                notify(Symbol.for("-"), (start + i).toString(), item);
            }
            for (let [i, item] of items.entries()) {
                notify(Symbol.for("+"), (start + i).toString(), item);
            }
            return removed;
        },

        push(...items) {
            ext.splice(target.length, 0, ...items);
            return target.length;
        },

        unshift(...items) {
            ext.splice(0, 0, ...items);
            return target.length;
        }
    };

    return new Proxy(target, {
        get(t, prop) {
            return ext[prop] || target[prop];
        },

        set(t, prop, value) {
            target[prop] = value;
            notify(prop, prop, value);
            notify(Symbol.for("*"), prop, value);
            return true;
        }
    });
};

/**
 * Bind the given DOM *elem* to *data*.
 *
 * If *data* is :class:`Watchable`, updating *data* will update the DOM accordingly.
 *
 * The binding works by simply setting DOM properties to values from *data*. This is denoted by data
 * attributes ``data-{prop}``, where *prop* specifies the property to set and the value is a bind
 * expression that is evaluated.
 *
 * Besides setting properties, there are also the following special data attributes:
 *
 * - ``data-content``: Set the content of the element, or *textContent* if the value is not a
 *   :class:`Node`.
 * - ``data-class-{class}``: Apply a *class* to the element if the value is truthy.
 *
 * For details on the bind expression see :func:`micro.bind.parse`. Transforms can be applied to
 * data values: If the expression contains multiple arguments, the first one must be a function of
 * the form ``transform(ctx, ...args)`` and transform the remaining *args* to a final value.
 *
 * Consider this example illustrating various features. Binding the following DOM::
 *
 *    <a data-href="url"><h1 data-content="title"></h1></a>
 *    <p data-title="not highlight">Daily relevant news</p>
 *    <p data-class-highlight="highlight">Recent articles:</p>
 *    <ul data-content="list posts 'post'">
 *        <template>
 *            <li data-content="post"></li>
 *        </template>
 *    </ul>
 *
 * To the data::
 *
 *    new micro.bind.Watchable({
 *        title: "The blog",
 *        url: "http://example.org/",
 *        highlight: true,
 *        posts: new micro.bind.Watchable(["More stuff", "First post"])
 *    })
 *
 * Will produce::
 *
 *    <a href="http://example.org/"><h1>The blog</h1></a>
 *    <p title="false">Daily relevant news</p>
 *    <p class="highlight">Recent articles:</p>
 *    <ul>
 *        <li>More stuff</li>
 *        <li>First post</li>
 *    </ul>
 *
 * And the DOM will be updated automatically if a data property changes or the *posts* array is
 * modified.
 *
 * .. deprecated:: 0.9.0
 *
 *    *template* is deprecated.
 **/
micro.bind.bind = function(elem, data, template = null) {
    // Compatibility for template (deprecated since 0.9.0)
    if (template) {
        if (typeof template === "string") {
            template = document.querySelector(template);
        }
        elem.appendChild(document.importNode(template.content, true));
    }

    let stack = [].concat(data, micro.bind.transforms);
    let elems;
    if (elem.length) {
        elems = Array.from(elem);
    } else if (elem instanceof DocumentFragment) {
        elems = Array.from(elem.children);
    } else {
        elems = [elem];
    }
    for (elem of elems) {
        if (elem.__bound__) {
            throw new Error("already bound");
        }
        elem.__bound__ = true;
    }

    function compact(str) {
        str = str.replace(/\n/ug, "\\n");
        return str.length > 32 ? `${str.slice(0, 31)}…` : str;
    }
    if (micro.bind.trace) {
        let tags = elems.map(e => `<${e.tagName.toLowerCase()}>`).join(", ");
        console.log(`Binding ${compact(tags)} to ${compact(JSON.stringify(data))}`);
    }

    elems.reverse();
    while (elems.length) {
        // eslint-disable-next-line no-shadow
        let elem = elems.pop();

        for (let [prop, expr] of Object.entries(elem.dataset)) {
            let loc = `<${elem.tagName.toLowerCase()} data-${prop}="${expr}">`;
            let args = micro.bind.parse(expr);
            if (args.length === 0) {
                throw new SyntaxError(`Expression is empty (in ${loc})`);
            }

            // eslint-disable-next-line func-style
            let update = () => {
                // Resolve references
                let values = args.map(arg => {
                    if (arg instanceof Object) {
                        return arg.tokens.reduce(
                            (object, token) =>
                                object === null || object === undefined ? undefined : object[token],
                            arg.scope);
                    }
                    return arg;
                });
                let [value] = values;

                // Apply transform
                if (values.length > 1) {
                    try {
                        value = value({elem, data}, ...values.slice(1));
                    } catch (e) {
                        e.message = `${e.message} (in ${loc})`;
                        throw e;
                    }
                }

                // Update property
                if (micro.bind.trace) {
                    console.log(
                        `Updating ${loc} with ${compact(JSON.stringify(value) || String(value))}`);
                }
                if (prop === "content") {
                    if (value instanceof Node) {
                        elem.textContent = "";
                        elem.appendChild(value);
                    } else {
                        elem.textContent = value;
                    }
                } else if (prop.startsWith("class") && prop !== "className") {
                    elem.classList.toggle(micro.bind.dash(prop.slice(5)), value);
                } else {
                    elem[prop] = value;
                }
            };

            // Resolve scope of and bind property to references
            for (let ref of args.filter(a => a instanceof Object)) {
                ref.scope = stack.find(scope => ref.tokens[0] in scope);
                if (!ref.scope) {
                    throw new ReferenceError(`${ref.name} is not defined (in ${loc})`);
                }
                if (ref.scope.watch) {
                    ref.scope.watch(ref.tokens[0], update);
                }
            }

            update();
        }

        if (!("content" in elem.dataset)) {
            elems.push(...Array.from(elem.children).filter(e => !e.__bound__).reverse());
        }
    }
};

/**
 * Parse the bind expression *expr* into a list of arguments.
 *
 * A bind expression is a string consisting of space-separated arguments. An argument may contain
 * whitespace characters if they are enclosed in single quotes. An argument can have one of the
 * following forms:
 *
 * - true
 * - false
 * - null
 * - undefined
 * - A string, enclosed in single quotes
 * - A number (see :func:`parseFloat`)
 * - A reference, i.e. a (optionally) dotted name. The parsed result is an :class:`Object`, where
 *   *name* is the full reference name and *tokens* are the dot-separated components.
 *
 * The expression ``x.y 'Purr'`` for example contains two arguments, a reference and a string, and
 * would be parsed into::
 *
 *    [{name: "x.y", tokens: ["x", "y"]}, "Purr"]
 */
micro.bind.parse = function(expr) {
    const KEYWORDS = {
        true: true,
        false: false,
        null: null,
        undefined
    };

    // NOTE: For escaped quote characters we could use the pattern ('(\\'|[^'])*'|\S)+
    return (expr.match(/('[^']*'|\S)+/ug) || []).map(arg => {
        if (arg in KEYWORDS) {
            return KEYWORDS[arg];
        } else if (arg.startsWith("'")) {
            return arg.slice(1, -1);
        } else if (/^[-+]?[0-9]/u.test(arg)) {
            return parseFloat(arg);
        }
        return {name: arg, tokens: arg.split(".")};
    });
};

/**
 * Create a new :class:`Watchable` live array from *arr* with all items that pass the given test.
 *
 * *arr* is a :class:`Watchable` array. *callback* and *thisArg* are equivalent to the arguments of
 * :func:`Array.filter`. Because the filtered array is updated live, it may be called out of order
 * and multiple times for the same index.
 */
micro.bind.filter = function(arr, callback, thisArg = null) {
    let cache = arr.map(callback, thisArg);
    let filtered = new micro.bind.Watchable(arr.filter((item, i) => cache[i]));

    function mapIndex(i) {
        // The index of the the filtered array corresponds to the count of passing items up to the
        // index of the source array
        return cache.slice(0, i).reduce((count, result) => result ? count + 1 : count, 0);
    }

    function update(i, value) {
        filtered[mapIndex(i)] = value;
    }

    function add(i, value) {
        filtered.splice(mapIndex(i), 0, value);
    }

    function remove(i) {
        filtered.splice(mapIndex(i), 1);
    }

    arr.watch(Symbol.for("*"), (prop, value) => {
        let i = parseInt(prop);
        let [prior] = cache.splice(i, 1, callback.call(thisArg, value, i, arr));
        if (prior && cache[i]) {
            update(i, value);
        } else if (!prior && cache[i]) {
            add(i, value);
        } else if (prior && !cache[i]) {
            remove(i);
        }
    });

    arr.watch(Symbol.for("+"), (prop, value) => {
        let i = parseInt(prop);
        cache.splice(i, 0, callback.call(thisArg, value, i, arr));
        if (cache[i]) {
            add(i, value);
        }
    });

    arr.watch(Symbol.for("-"), prop => {
        let i = parseInt(prop);
        let [prior] = cache.splice(i, 1);
        if (prior) {
            remove(i);
        }
    });

    return filtered;
};

/**
 * Create a new :class:`Watchable` live array from *arr*, applying a function to every item.
 *
 * *arr* is a :class:`Watchable` array. *callback* and *thisArg* are equivalent to
 * :func:`Array.map`.
 */
micro.bind.map = function(arr, callback, thisArg = null) {
    let mapped = new micro.bind.Watchable(arr.map(callback, thisArg));
    arr.watch(Symbol.for("*"), (prop, value) => {
        mapped[prop] = callback.call(thisArg, value);
    });
    arr.watch(
        Symbol.for("+"),
        (prop, value) => mapped.splice(parseInt(prop), 0, callback.call(thisArg, value))
    );
    arr.watch(Symbol.for("-"), prop => mapped.splice(parseInt(prop), 1));
    return mapped;
};

/**
 * Default transforms available in bind expressions.
 */
micro.bind.transforms = {
    /** Create a new instance of *constructor* with *args*. */
    new(ctx, constructor, ...args) {
        return new constructor(ctx.elem, ...args);
    },

    /** Test if *a* and *b* are (strictly) equal. */
    eq(ctx, a, b) {
        return a === b;
    },

    /* Apply logical or to *values* successively. */
    or(ctx, ...values) {
        return values.reduce((result, value) => result || value);
    },

    /** Negate *value* (logical not). */
    not(ctx, value) {
        return !value;
    },

    /**
     * Bind *args* to *func*.
     *
     * The returned function will call *func* with *args* prepended. ``this`` is set to ``null``.
     */
    bind(ctx, func, ...args) {
        return func.bind(null, ...args);
    },

    /**
     * Bind *args* to *func*.
     *
     * The returned function will call *func* with *args* prepended and ``this`` set to *thisArg*.
     */
    bindThis(ctx, func, thisArg, ...args) {
        return func.bind(thisArg, ...args);
    },

    /**
     * Format a string containing placeholders.
     *
     * *str* is a format string with placeholders of the form ``{key}``. *args* is a flat list of
     * key-value pairs, specifying the value to replace for a key.
     */
    format(ctx, str, ...args) {
        args = new Map(micro.bind.chunk(args, 2));
        return str.replace(/\{([^}\s]+)\}/ug, (match, key) => args.get(key));
    },

    /** Format a string with support for pluralization. */
    formatPlural(ctx, singular, plural, ...args) {
        let n = new Map(micro.bind.chunk(args, 2)).get("n");
        return micro.bind.transforms.format(ctx, n === 1 ? singular : plural, ...args);
    },

    /**
     * Return a string representation of the given :class:`Date` *date*.
     *
     * Alternatively, *date* may be a string parsable by :class:`Date`. *format* is equivalent to
     * the *options* argument of :meth:`Date.toLocaleString`.
     */
    formatDate(ctx, date, format) {
        if (typeof date === "string") {
            date = new Date(date);
        }
        return date.toLocaleString("en", format);
    },

    /**
     * Project *arr* into the DOM.
     *
     * If *arr* is :class:`Watchable`, the DOM will be live, i.e. updating *arr* will update the DOM
     * accordingly.
     *
     * Optionally, a live transform can be applied on *arr* with the function
     * ``transform(arr, ...args)``. *args* are passed through.
     */
    list(ctx, arr, itemName, transform, ...args) {
        let scopes = new Map();

        function create(item) {
            let child =
                document.importNode(ctx.elem.__templates__[0].content, true).querySelector("*");
            let scope = new micro.bind.Watchable({[itemName]: item});
            scopes.set(child, scope);
            micro.bind.bind(child, [scope].concat(ctx.data));
            return child;
        }

        if (!ctx.elem.__templates__) {
            ctx.elem.__templates__ = Array.from(ctx.elem.querySelectorAll("template"));
        }

        let fragment = document.createDocumentFragment();

        if (arr) {
            if (transform) {
                arr = transform(arr, ...args);
            }

            if (arr.watch) {
                arr.watch(Symbol.for("*"), (prop, value) => {
                    scopes.get(ctx.elem.children[prop])[itemName] = value;
                });
                arr.watch(Symbol.for("+"), (prop, value) => {
                    ctx.elem.insertBefore(create(value), ctx.elem.children[prop] || null);
                });
                arr.watch(Symbol.for("-"), prop => {
                    let child = ctx.elem.children[prop];
                    scopes.delete(child);
                    child.remove();
                });
            }

            arr.forEach(item => fragment.appendChild(create(item)));
        }

        return fragment;
    },

    /**
     * Join all items of the array *arr* into a DOM fragment.
     *
     * *separator* is inserted between adjacent items. *transform* and *args* are equivalent to the
     * arguments of :func:`micro.bind.list`.
     */
    join(ctx, arr, itemName, separator = ", ", transform, ...args) {
        if (!ctx.elem.__templates__) {
            ctx.elem.__templates__ = Array.from(ctx.elem.querySelectorAll("template"));
        }

        let fragment = document.createDocumentFragment();

        if (arr) {
            if (transform) {
                arr = transform(arr, ...args);
            }

            for (let [i, item] of arr.entries()) {
                if (i > 0) {
                    fragment.appendChild(document.createTextNode(separator));
                }
                let child =
                    document.importNode(ctx.elem.__templates__[0].content, true).querySelector("*");
                let scope = {[itemName]: item};
                micro.bind.bind(child, [scope].concat(ctx.data));
                fragment.appendChild(child);
            }
        }

        return fragment;
    },

    filter: micro.bind.filter,
    map: micro.bind.map,

    /**
     * Test if the array *arr* includes a certain item.
     *
     * *searchElement* and *fromIndex* are equivalent to the arguments of :func:`Array.includes`.
     */
    includes(ctx, arr, searchElement, fromIndex) {
        return arr ? arr.includes(searchElement, fromIndex) : false;
    },

    /**
     * Select and render a template associated with a case by matching against *value*.
     *
     * *cases* is a list of conditions corresponding to a list of templates. There may be an
     * additional default template. If *value* does not match any case, the default template is
     * rendered, or nothing if there is no default template.
     */
    switch(ctx, value, ...cases) {
        if (!ctx.elem.__templates__) {
            ctx.elem.__templates__ = Array.from(ctx.elem.querySelectorAll("template"));
        }

        if (cases.length === 0) {
            cases = [value ? value : Symbol("unmatchable")];
        }
        if (!(ctx.elem.__templates__.length >= cases.length &&
              ctx.elem.__templates__.length <= cases.length + 1)) {
            throw new Error("templates-do-not-match-cases");
        }

        let i = cases.indexOf(value);
        let template = ctx.elem.__templates__[i === -1 ? cases.length : i];
        if (!template) {
            return document.createDocumentFragment();
        }
        let node = document.importNode(template.content, true);
        micro.bind.bind(node, ctx.data);
        return node;
    },

    /**
     * Render a given *template*.
     *
     * The context element may contain a fallback `template`. If *template* is ``null``, the
     * fallback template is rendered, or nothing if there is no fallback.
     */
    render(ctx, template) {
        if (!ctx.elem.__templates__) {
            ctx.elem.__templates__ = Array.from(ctx.elem.querySelectorAll("template"));
        }
        template = template || ctx.elem.__templates__[0];
        if (!template) {
            return document.createDocumentFragment();
        }
        let elem = document.importNode(template.content, true);
        micro.bind.bind(elem, ctx.data);
        return elem;
    }
};

/**
 * Project the :class:`Watchable` array :class:*arr* into a live DOM fragment.
 *
 * Optionally, a live transform can be applied on *arr* with the function
 * ``transform(arr, ...args)``. *args* are passed through.
 *
 * .. deprecated:: 0.8.0
 *
 *    Use :func:`micro.bind.transforms.list`.
 */
micro.bind.list = function(elem, arr, itemName, transform, ...args) {
    function create(item) {
        let child = document.importNode(elem.__templates__[0].content, true).querySelector("*");
        child[itemName] = item;
        return child;
    }

    if (!elem.__templates__) {
        elem.__templates__ = Array.from(elem.querySelectorAll("template"));
    }

    let fragment = document.createDocumentFragment();

    if (arr) {
        if (transform) {
            arr = transform(arr, ...args);
        }

        arr.watch(Symbol.for("*"), (prop, value) => {
            elem.children[prop][itemName] = value;
        });
        arr.watch(Symbol.for("+"),
                  (prop, value) => elem.insertBefore(create(value), elem.children[prop] || null));
        arr.watch(Symbol.for("-"), prop => elem.children[prop].remove());

        arr.forEach(item => fragment.appendChild(create(item)));
    }

    return fragment;
};

/**
 * Join all items of the array *arr* into a DOM fragment.
 *
 * *separator* is inserted between adjacent items. *transform* and *args* are equivalent to the
 * arguments of :func:`micro.bind.list`.
 *
 * .. deprecated:: 0.8.0
 *
 *    Use :func:`micro.bind.transforms.join`.
 */
micro.bind.join = function(elem, arr, itemName, separator = ", ", transform, ...args) {
    if (!elem.__templates__) {
        elem.__templates__ = Array.from(elem.querySelectorAll("template"));
    }

    let fragment = document.createDocumentFragment();

    if (arr) {
        if (transform) {
            arr = transform(arr, ...args);
        }

        for (let [i, item] of arr.entries()) {
            if (i > 0) {
                fragment.appendChild(document.createTextNode(separator));
            }
            let child = document.importNode(elem.__templates__[0].content, true).querySelector("*");
            child[itemName] = item;
            fragment.appendChild(child);
        }
    }

    return fragment;
};

/** Convert a camel case *str* to dashed style. */
micro.bind.dash = function(str) {
    return str.replace(/(?!^)([A-Z])/ug, "-$1").toLowerCase();
};

/** Split *arr* into chunks of the given *size*. */
micro.bind.chunk = function(arr, size) {
    let chunked = Array(Math.ceil(arr.length / size));
    for (let i = 0; i < chunked.length; i++) {
        chunked[i] = arr.slice(i * size, i * size + size);
    }
    return chunked;
};
