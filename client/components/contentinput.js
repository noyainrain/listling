/*
 * micro
 * Copyright (C) 2020 micro contributors
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

/** Input for text and web resource content. */

"use strict";

self.micro = self.micro || {};
micro.components = micro.components || {};
micro.components.contentinput = {};

/**
 * Input for text and web :ref:`Resource` content.
 *
 * For convenience, when a URL is entered, the web resource is attached automatically.
 */
micro.components.contentinput.ContentInputElement = class extends HTMLElement {
    createdCallback() {
        this.appendChild(
            document.importNode(
                document.querySelector("#micro-content-input-template").content, true
            )
        );
        this._data = new micro.bind.Watchable({
            resource: null,
            placeholder: this.getAttribute("placeholder") || "",
            getPlaceholder: (ctx, placeholder, resource) => resource ? "" : placeholder,
            attaching: false,

            deleteResource: () => {
                this._data.resource = null;
                this._data.validate();
            },

            validate: () => {
                if (this.required && !(this._textarea.value || this._data.resource)) {
                    this._textarea.setCustomValidity("Please fill out this field.");
                } else {
                    this._textarea.setCustomValidity("");
                }
            },

            onAttachClick: () => {
                this._upload.click();
            },

            onUploadChange: () => {
                const [file] = this._upload.files;
                if (file) {
                    (async () => {
                        await this.attach(file);
                        this._upload.value = "";
                    })();
                }
            },

            onURLInput: event => {
                if (!this._data.resource) {
                    this.attach(event.detail.url).catch(micro.util.catch);
                }
            }
        });
        micro.bind.bind(this.children, this._data);

        this._textarea = this.querySelector(".micro-content-input-text");
        this._upload = this.querySelector(".micro-content-input-upload");
        this._data.validate();

        this.addEventListener("mousedown", event => {
            const elem = micro.keyboard.findAncestor(event.target, e => e.tabIndex !== -1, this);
            if (!elem) {
                event.preventDefault();
                this._textarea.focus();
            }
        });
    }

    /**
     * Current value as object ``{text, resource}``.
     *
     * *text* is the text and *resource* the web :ref:`Resource` content. May both be ``null``.
     */
    get valueAsObject() {
        return {text: this._textarea.value || null, resource: this._data.resource};
    }

    set valueAsObject(value) {
        this._textarea.value = value.text || "";
        this._data.resource = value.resource;
        this._data.validate();
    }

    /** See :attr:`HTMLInputElement.required`. */
    get required() {
        return this.hasAttribute("required");
    }

    set required(value) {
        if (value) {
            this.setAttribute("required", "required");
        } else {
            this.removeAttribute("required");
        }
        this._data.validate();
    }

    /** See :attr:`HTMLInputElement.placeholder`. */
    get placeholder() {
        return this._data.placeholder;
    }

    set placeholder(value) {
        this._data.placeholder = value;
    }

    /**
     * Attach the web resource at *url*.
     *
     * Alternatively, *url* may be a :class:`File` to upload and attach.
     */
    async attach(url) {
        this._data.attaching = true;
        try {
            if (url instanceof File) {
                const response = await fetch("/files", {method: "POST", body: url});
                url = response.headers.get("Location");
            }
            this._data.resource = await micro.call(
                "GET", `/api/previews/${encodeURIComponent(url)}`
            );
            this._data.validate();
        } catch (e) {
            if (
                e instanceof micro.APIError && [
                    "CommunicationError", "NoResourceError", "ForbiddenResourceError",
                    "BrokenResourceError"
                ].includes(e.error.__type__)
            ) {
                // Ignore
            } else {
                ui.handleCallError(e);
            }
        } finally {
            this._data.attaching = false;
        }
    }
};
document.registerElement("micro-content-input", micro.components.contentinput.ContentInputElement);

/**
 * Extension for an input that detects when a URL is entered.
 *
 * .. attribute:: input
 *
 *    Extended :class:`HTMLInputElement` or :class:`HTMLTextAreaElement`.
 *
 * .. describe:: onurlinput
 *
 *    Event handler for ``urlinput``, dispatched when a *url* is entered.
 */
micro.components.contentinput.URLDetection = class {
    constructor(input) {
        this.input = input;
        this._urls = new Set();
        this._newURL = null;

        const findURLs = () => {
            let urls = this.input.value.match(new RegExp(micro.core.URL_PATTERN, "ug")) || [];
            return new Set(urls.map(url => url.charAt() === "h" ? url : url.slice(1)));
        };

        this.input.addEventListener("focus", () => {
            this._urls = findURLs();
        });
        for (let type of ["input", "change", "keyup", "click"]) {
            this.input.addEventListener(type, event => {
                const urls = findURLs();
                if (!urls.has(this._newURL)) {
                    this._newURL = null;
                }
                this._newURL = Array.from(urls).find(url => !this._urls.has(url)) || this._newURL;
                this._urls = urls;

                if (this._newURL) {
                    const i = this.input.value.indexOf(this._newURL);
                    if (
                        event.type === "change" || this.input.selectionStart < i ||
                        this.input.selectionStart > i + this._newURL.length
                    ) {
                        this.input.dispatchEvent(
                            new CustomEvent("urlinput", {detail: {url: this._newURL}})
                        );
                        this._newURL = null;
                    }
                }
            });
        }

        Object.defineProperty(this.input, "onurlinput", micro.util.makeOnEvent("urlinput"));
    }
};

Object.assign(micro.bind.transforms, {URLDetection: micro.components.contentinput.URLDetection});
