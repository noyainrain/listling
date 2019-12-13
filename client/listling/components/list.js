/*
 * Open Listling
 * Copyright (C) 2019 Open Listling contributors
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

/** Assign dialog. */
listling.components.list.AssignDialog = class extends HTMLElement {
    createdCallback() {
        this.appendChild(
            document.importNode(ui.querySelector(".listling-assign-dialog-template").content, true)
        );
        this._data = new micro.bind.Watchable({
            itemElement: null,
            userToText: user => user.name,

            queryUsers: async query => {
                const result = await ui.call(
                    "GET",
                    `/api/lists/${this._data.itemElement.list.id}/users?name=${encodeURIComponent(query)}`
                );
                let users = result.items;
                if (ui.user.name.toLowerCase().includes(query.toLowerCase())) {
                    users = [ui.user, ...users.filter(user => user.id !== ui.user.id)];
                }
                const assigneeIDs = new Set(
                    this._data.itemElement.assignees.map(assignee => assignee.id)
                );
                return users.filter(user => !assigneeIDs.has(user.id));
            },

            add: async () => {
                const assignee = this._input.valueAsObject;
                try {
                    await ui.call(
                        "POST",
                        `/api/lists/${this._data.itemElement.list.id}/items/${this._data.itemElement.item.id}/assignees`,
                        {assignee_id: assignee.id}
                    );
                } catch (e) {
                    if (
                        e instanceof micro.APIError && e.error.__type__ === "ValueError" &&
                        e.message.includes("assignees")
                    ) {
                        // Continue as usual to update the UI
                    } else {
                        throw e;
                    }
                }
                ui.dispatchEvent(
                    new CustomEvent(
                        "item-assignees-assign",
                        {detail: {item: this._data.itemElement.item, assignee}}
                    )
                );
                this._input.value = "";
                this._input.valueAsObject = null;
                this.querySelector("micro-options").activate();
            },

            remove: async assignee => {
                try {
                    await ui.call(
                        "DELETE",
                        `/api/lists/${this._data.itemElement.list.id}/items/${this._data.itemElement.item.id}/assignees/${assignee.id}`
                    );
                } catch (e) {
                    if (e instanceof micro.APIError && e.error.__type__ === "NotFoundError") {
                        // Continue as usual to update the UI
                    } else {
                        throw e;
                    }
                }
                ui.dispatchEvent(
                    new CustomEvent(
                        "item-assignees-unassign",
                        {detail: {item: this._data.itemElement.item, assignee}}
                    )
                );
            },

            close: () => this.remove(),

            onChange: () => {
                if (this._input.valueAsObject) {
                    this._input.setCustomValidity("");
                } else {
                    this._input.setCustomValidity(
                        "The user is unknown. Share the list with others to assign them here."
                    );
                }
            },

            onSelect: () => {
                this._input.dispatchEvent(new Event("change", {bubbles: true}));
                this.querySelector(".listling-assign-add").click();
            }
        });
        micro.bind.bind(this.children, this._data);

        this._input = this.querySelector("input");
        this.querySelector("div").shortcutContext.add("A", () => this._input.focus());
    }

    attachedCallback() {
        ui.classList.add("listling-ui-dialog");
        setTimeout(() => this._input.focus(), 0);
    }

    detachedCallback() {
        ui.classList.remove("listling-ui-dialog");
    }

    get itemElement() {
        return this._data.itemElement;
    }

    set itemElement(value) {
        this._data.itemElement = value;
    }
};
document.registerElement("listling-assign-dialog", listling.components.list.AssignDialog);

/** Presentation controller. */
listling.components.list.Presentation = class {
    constructor(page) {
        this.page = page;
        this._em = null;
        this._maxWidth = null;
        this._onScrollTimeout = null;
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

        this._onScroll = () => {
            if (this._onScrollTimeout) {
                clearTimeout(this._onScrollTimeout);
            }
            this._onScrollTimeout = setTimeout(() => {
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
        clearTimeout(this._onScrollTimeout);

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
        ui.scrollToElement(elem);
    }
};

/** Playlist controller. */
listling.components.list.Playlist = class {
    constructor(page) {
        this.page = page;
        // eslint-disable-next-line no-underscore-dangle
        this._data = this.page._data;
        this._itemsOL = this.page.querySelector(".listling-list-items");
        this._current = this._itemsOL.firstElementChild;

        Object.assign(this._data, {
            playlistPlaying: false,

            playlistPlayPause: () => {
                // Wait until button does not touch icon anymore
                setTimeout(() => {
                    if (!this._current) {
                        return;
                    }
                    if (this._current.playable.paused) {
                        this._current.playable.play();
                    } else {
                        this._current.playable.pause();
                    }
                }, 0);
            },

            playlistPlayNext: () => {
                if (!this._current) {
                    return;
                }
                const item = this._current.nextElementSibling || this._itemsOL.firstElementChild;
                item.playable.play();
            },

            playlistPlayPrevious: () => {
                if (!this._current) {
                    return;
                }
                const item = this._current.previousElementSibling || this._itemsOL.lastElementChild;
                item.playable.play();
            }
        });

        this._onPlay = event => {
            if (event.target !== this._current) {
                this._current.playable.pause();
                this._current.playable.time = 0;
                this._current = event.target;
            }
            this._current.focus();
            ui.scrollToElement(this._current);
            this._data.playlistPlaying = true;
        };
        this._itemsOL.addEventListener("play", this._onPlay);

        this._onPause = event => {
            this._data.playlistPlaying = false;
            if (event.detail.ended) {
                this._data.playlistPlayNext();
            }
        };
        this._itemsOL.addEventListener("pause", this._onPause);

        this._observer = new MutationObserver(records => {
            // Handle empty list
            if (!this._current && this._itemsOL.hasChildNodes()) {
                this._current = this._itemsOL.firstElementChild;
            } else if (this._current && !this._itemsOL.hasChildNodes()) {
                this._current = null;
                this._data.playlistPlaying = false;
            }
            if (!this._current) {
                return;
            }

            // Handle trashed and moved items, which are removed from the DOM
            for (let record of records) {
                for (let node of record.removedNodes) {
                    if (node === this._current) {
                        this._current = record.nextSibling || this._itemsOL.firstElementChild;
                        if (this._data.playlistPlaying) {
                            this._current.playable.play();
                        }
                    }
                }
            }
        });
        this._observer.observe(this._itemsOL, {childList: true});
    }

    dispose() {
        this._itemsOL.removeEventListener("play", this._onPlay);
        this._itemsOL.removeEventListener("pause", this._onPause);
        this._observer.disconnect();
    }
};

/** Playable :class:`listling.ItemElement` extension. */
listling.components.list.Playable = class {
    constructor(elem) {
        this.elem = elem;
        // eslint-disable-next-line no-underscore-dangle
        this._data = this.elem._data;
        this._playableResource = false;
        this._resourceElement = null;
        this._clockTimeout = null;
        this._clockStartTime = null;
        this._clockTime = 0;
        this._frame = null;

        Object.assign(this._data, {
            playablePlaying: false,

            playablePlayPause: () => {
                if (this.paused) {
                    this.play();
                } else {
                    this.pause();
                }
            }
        });

        this._onPlay = () => {
            const render = () => {
                this._renderProgress();
                this._frame = requestAnimationFrame(render);
            };
            render();
            this._data.playablePlaying = true;
            this.elem.dispatchEvent(new CustomEvent("play", {bubbles: true}));
        };

        this._onPause = event => {
            cancelAnimationFrame(this._frame);
            this._frame = null;
            this._data.playablePlaying = false;
            this.elem.dispatchEvent(
                new CustomEvent("pause", {detail: {ended: event.detail.ended}, bubbles: true})
            );
        };

        this.elem.shortcutContext.add("P", () => {
            if (!this._data.item.trashed) {
                this._data.playablePlayPause();
            }
        });
    }

    dispose() {
        this.resourceElement = null;
        this.elem.shortcutContext.remove("P");
    }

    /** Web :ref:`Resource` element. */
    get resourceElement() {
        return this._resourceElement;
    }

    set resourceElement(value) {
        if (this._playableResource) {
            this._resourceElement.removeEventListener("play", this._onPlay);
            this._resourceElement.removeEventListener("pause", this._onPause);
            this._playableResource = false;
            if (this._data.playablePlaying) {
                this._onPause(new CustomEvent("pause", {detail: {ended: true}}));
            }
        } else {
            this._resetClock();
        }

        this._resourceElement = value;
        this._playableResource = this._resourceElement && "play" in this._resourceElement;

        if (this._playableResource) {
            this._resourceElement.addEventListener("play", this._onPlay);
            this._resourceElement.addEventListener("pause", this._onPause);
        }
        this._renderProgress();
    }

    get duration() {
        return this._playableResource
            ? this._resourceElement.duration : listling.components.list.Playable.STATIC_DURATION;
    }

    get time() {
        if (this._playableResource) {
            return this._resourceElement.time;
        }
        return this._clockTimeout
            ? Math.min((new Date() - this._clockStartTime) / 1000 + this._clockTime, this.duration)
            : this._clockTime;
    }

    set time(value) {
        if (this._playableResource) {
            this._resourceElement.time = value;
        } else {
            this._clockTime = value;
        }
        this._renderProgress();
    }

    get paused() {
        return this._playableResource ? this._resourceElement.paused : !this._clockTimeout;
    }

    play() {
        if (this._playableResource) {
            this._resourceElement.play();
        } else {
            this._startClock();
        }
    }

    pause() {
        if (this._playableResource) {
            this._resourceElement.pause();
        } else {
            this._resetClock(this.time);
        }
    }

    _startClock() {
        if (!this._clockTimeout) {
            this._clockStartTime = new Date();
            this._clockTimeout = setTimeout(
                () => this._resetClock(), (this.duration - this._clockTime) * 1000
            );
            this._onPlay();
        }
    }

    _resetClock(time = null) {
        this._clockTime = time || 0;
        if (this._clockTimeout) {
            clearTimeout(this._clockTimeout);
            this._clockTimeout = null;
            this._clockStartTime = null;
            this._onPause(new CustomEvent("pause", {detail: {ended: time === null}}));
        }
    }

    _renderProgress() {
        const progress = this.duration ? this.time / this.duration : 0;
        this.elem.firstElementChild.style.setProperty(
            "--listling-item-progress", `${progress * 100}%`
        );
    }
};

listling.components.list.Playable.STATIC_DURATION = 20;
