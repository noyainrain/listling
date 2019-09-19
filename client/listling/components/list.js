/*
 * Open Listling
 * Copyright (C) 2018 Open Listling contributors
 *
 * This program is free software: you can redistribute it and/or modify it under the terms of the
 * GNU Affero General Public License as published by the Free Software Foundation, either version 3
 * of the License, or (at your option) any later version.
 *
 * This program is distributed in the hope that it will be useful, but WITHOUT ANY WARRANTY; without
 * even the implied warranty of MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE. See the GNU
 * Affero General Public License for more details.
 *
 * You should have received a copy of the GNU Affero General Public License along with this program.
 * If not, see <https://www.gnu.org/licenses/>.
 */

/** List page. */

"use strict";

self.listling = self.listling || {};
self.listling.components = self.listling.components || {};
self.listling.components.list = {};

/** Share the :ref:`List` *list*. */
listling.components.list.share = function(list) {
    if ("share" in navigator) {
        // Work around Chrome not rejecting the promise on cancel (see
        // https://bugs.chromium.org/p/chromium/issues/detail?id=636274)
        (async() => {
            try {
                await navigator.share(
                    {url: `${location.origin}${listling.util.makeListURL(list)}`}
                );
            } catch (e) {
                if (e instanceof DOMException && e.name === "AbortError") {
                    // Pass
                } else {
                    throw e;
                }
            }
        })().catch(micro.util.catch);
        return;
    }

    const dialog = document.createElement("listling-share-dialog");
    dialog.list = list;
    ui.notify(dialog);
};

/** Share dialog. */
listling.components.list.ShareDialog = class extends HTMLElement {
    createdCallback() {
        this.appendChild(
            document.importNode(ui.querySelector("#listling-share-dialog-template").content, true)
        );
        this._data = new micro.bind.Watchable({
            lst: null,
            url: null,

            onFocus(event) {
                // Since the user cannot be prevented in all cases from (accidentally) making a
                // partial selection, e.g. by long press, just set a default selection. On mobile,
                // the copy action is presented only if a selection is set in response to a user
                // action, thus it is not possible to autofocus the input.
                event.target.select();
            },

            close: () => {
                this.remove();
            }
        });
        micro.bind.bind(this.children, this._data);
    }

    get list() {
        return this._data.lst;
    }

    set list(value) {
        this._data.lst = value;
        this._data.url = `${location.origin}${listling.util.makeListURL(this._data.lst)}`;
    }
};
document.registerElement("listling-share-dialog", listling.components.list.ShareDialog);

/** Presentation controller. */
listling.components.list.Presentation = class {
    constructor(page) {
        this.page = page;
        this._em = null;
        this._maxWidth = null;
    }

    /** Enter presentation mode. */
    async enter() {
        if ("requestFullscreen" in document.documentElement) {
            try {
                await document.documentElement.requestFullscreen();
            } catch (e) {
                if (e instanceof TypeError || e instanceof DOMException && e.name === "TypeError") {
                    // Ignore if we are not allowed to go fullscreen
                } else {
                    throw e;
                }
            }
        }

        if ("orientation" in screen) {
            try {
                await screen.orientation.lock("landscape-primary");
            } catch (e) {
                if (
                    e instanceof DOMException &&
                    ["NotSupportedError", "SecurityError"].includes(e.name)
                ) {
                    // Ignore
                } else {
                    throw e;
                }
            }
        }

        this._onFullscreenChange = () => {
            if (!document.fullscreenElement) {
                this.exit().catch(micro.util.catch);
            }
        };
        document.documentElement.addEventListener("fullscreenchange", this._onFullscreenChange);

        this._onResize = () => this._zoom();
        addEventListener("resize", this._onResize);

        this._onFocusIn = () => this._scroll();
        ui.addEventListener("focusin", this._onFocusIn);

        this._onFocusOut = event => {
            if (!event.relatedTarget) {
                this._scroll();
            }
        };
        ui.addEventListener("focusout", this._onFocusOut);

        let timeout;
        this._onScroll = () => {
            if (timeout) {
                clearTimeout(timeout);
            }
            timeout = setTimeout(() => {
                const em = parseFloat(getComputedStyle(this.page).fontSize);
                // Use scrollingElement to work around Safari scrolling via body instead of root
                // (see https://bugs.webkit.org/show_bug.cgi?id=5991)
                const snap = document.scrollingElement.scrollTop + 2 * 1.5 * em + 2 * 1.5 * em / 4;
                const elems = [
                    this.page.querySelector(".listling-list-title"),
                    ...this.page.querySelector(".listling-list-items").children
                ];
                const elem = elems.reduce(
                    (a, b) => Math.abs(a.offsetTop - snap) < Math.abs(b.offsetTop - snap) ? a : b
                );
                if (elem instanceof listling.ItemElement) {
                    if (!elem.contains(document.activeElement)) {
                        elem.focus();
                    }
                } else {
                    document.activeElement.blur();
                }
            }, 500);
        };
        addEventListener("scroll", this._onScroll);

        // Cache pre-zoom sizes
        if (!this._em) {
            this._em = parseFloat(getComputedStyle(this.page).fontSize);
            this._maxWidth = parseFloat(
                getComputedStyle(document.querySelector(".micro-ui-inside")).maxWidth
            );
        }

        ui.noninteractive = true;
        // eslint-disable-next-line no-underscore-dangle
        this.page._data.presentationMode = true;
        this._zoom();
        document.scrollingElement.classList.add("listling-list-scroll-snap");
    }

    /** Exit presentation mode. */
    async exit() {
        if (!ui.noninteractive) {
            return;
        }

        ui.noninteractive = false;
        // eslint-disable-next-line no-underscore-dangle
        this.page._data.presentationMode = false;
        this._resetZoom();
        document.documentElement.classList.remove("listling-list-scroll-snap");

        document.documentElement.removeEventListener("fullscreenchange", this._onFullscreenChange);
        removeEventListener("resize", this._onResize);
        ui.removeEventListener("focusin", this._onFocusIn);
        ui.removeEventListener("focusout", this._onFocusOut);
        removeEventListener("scroll", this._onScroll);

        if ("orientation" in screen) {
            await screen.orientation.unlock();
        }

        if (document.fullscreenElement) {
            await document.exitFullscreen();
        }
    }

    onFooterMouseDown(event) {
        event.preventDefault();
    }

    _zoom() {
        const m = 1.5 * this._em;
        const xs = m / 4;
        const width = this._maxWidth + 2 * m;
        const height =
            // UI header and footer space
            2 * (2 * m + 2 * xs) +
            // Item header
            m + 2 * xs +
            // Item content padding
            2 * xs +
            // Item content
            (this._maxWidth - 2 * xs) / 16 * 9;
        const ratio = Math.min(
            document.documentElement.clientWidth / width,
            document.documentElement.clientHeight / height
        );
        document.documentElement.style.fontSize = `${ratio * this._em}px`;
        // Work around Chrome misinterpreting rem units in root element (see
        // https://bugs.chromium.org/p/chromium/issues/detail?id=918480)
        document.scrollingElement.style.scrollPadding = `${ratio * (2 * m + 2 * xs)}px 0`;
        this._scroll();
    }

    _resetZoom() {
        document.documentElement.style.fontSize = "";
        document.scrollingElement.style.scrollPadding = "";
    }

    _scroll() {
        const elem = micro.keyboard.findAncestor(
            document.activeElement, e => e instanceof listling.ItemElement
        ) || this.page.querySelector(".listling-list-title");
        const em = parseFloat(getComputedStyle(this.page).fontSize);
        scroll(0, elem.offsetTop - (2 * 1.5 * em + 2 * 1.5 * em / 4));
    }
};
