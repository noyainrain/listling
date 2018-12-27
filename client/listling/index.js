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

/**
 * Open Listling UI.
 */

"use strict";

self.listling = self.listling || {};

/**
 * Open Listling UI.
 */
listling.UI = class extends micro.UI {
    init() {
        function makeAboutPage() {
            return document
                .importNode(ui.querySelector(".listling-about-page-template").content, true)
                .querySelector("micro-about-page");
        }

        this.pages = this.pages.concat([
            {url: "^/$", page: "listling-start-page"},
            {url: "^/about$", page: makeAboutPage},
            {url: "^/lists/([^/]+)(?:/[^/]+)?$", page: listling.ListPage.make},
            {url: "^/l/([^/]+)$", page: listling.ListPage.make}
        ]);

        Object.assign(this.renderEvent, {
            "create-list"(event) {
                let elem = document.importNode(
                    ui.querySelector(".listling-create-list-event-template").content, true);
                micro.bind.bind(elem, {event, makeListURL: listling.util.makeListURL});
                return elem;
            }
        });
    }
};

/**
 * Start page.
 */
listling.StartPage = class extends micro.Page {
    createdCallback() {
        const USE_CASES = [
            {id: "todo", title: "To-Do list", icon: "check"},
            {id: "shopping", title: "Shopping list", icon: "shopping-cart"},
            {id: "meeting-agenda", title: "Meeting agenda", icon: "handshake"},
            ...ui.mapServiceKey ? [{id: "map", title: "Map", icon: "map"}] : [],
            {id: "simple", title: "Simple list", icon: "list"}
        ];

        super.createdCallback();
        this.appendChild(
            document.importNode(ui.querySelector(".listling-start-page-template").content, true));
        this._data = new micro.bind.Watchable({
            settings: ui.settings,
            useCases: USE_CASES,
            selectedUseCase: USE_CASES[0],

            focusUseCase(event) {
                event.target.focus();
            },

            selectUseCase: useCase => {
                // On touch, a mouseenter and a click event are triggered. Delay selecting the use
                // case on mouseenter, so the click cannot interact with child elements becoming
                // visible.
                setTimeout(() => {
                    this._data.selectedUseCase = useCase;
                }, 0);
            },

            createList: async useCase => {
                let list = await micro.call("POST", "/api/lists", {use_case: useCase.id, v: 2});
                ui.navigate(`/lists/${list.id.split(":")[1]}`);
            },

            createExample: async useCase => {
                let list = await micro.call("POST", "/api/lists/create-example",
                                            {use_case: useCase.id});
                ui.navigate(`/lists/${list.id.split(":")[1]}`);
            }
        });
        micro.bind.bind(this.children, this._data);
    }

    attachedCallback() {
        super.attachedCallback();
        ui.shortcutContext.add("S", () => {
            this.querySelector(".listling-selected .listling-start-create-list").click();
        });
        ui.shortcutContext.add("E", () => {
            if (this._data.selectedUseCase.id !== "simple") {
                this.querySelector(".listling-selected .listling-start-create-example button")
                    .click();
            }
        });
    }

    detachedCallback() {
        ui.shortcutContext.remove("S");
        ui.shortcutContext.remove("E");
    }
};

listling.ListPage = class extends micro.Page {
    static async make(url, id) {
        const page = document.createElement("listling-list-page");
        id = id.length === 4 ? `Short:${id}` : `List:${id}`;
        page.list = await micro.call("GET", `/api/lists/${id}`);
        return page;
    }

    createdCallback() {
        super.createdCallback();
        this.appendChild(
            document.importNode(ui.querySelector(".listling-list-page-template").content, true));
        this._data = new micro.bind.Watchable({
            lst: null,
            presentItems: null,
            trashedItems: null,
            trashedItemsCount: 0,
            locations: null,
            locationEnabled: false,
            editMode: true,
            trashExpanded: false,
            creatingItem: false,
            settingsExpanded: false,
            shortUrl: null,
            presentation: false,
            idle: false,
            toggleTrash: () => {
                this._data.trashExpanded = !this._data.trashExpanded;
            },
            startCreateItem: () => {
                this._data.creatingItem = true;
                this.querySelector(".listling-list-create-item form").elements[1].focus();
            },
            stopCreateItem: () => {
                this._data.creatingItem = false;
            },
            toggleSettings: () => {
                this._data.settingsExpanded = !this._data.settingsExpanded;
            },

            share: () => {
                // TODO: use data binding
                let notification = document.createElement("micro-simple-notification");
                notification.content.appendChild(document.importNode(
                    ui.querySelector(".listling-share-notification-template").content, true));
                notification.content.querySelector("input").value =
                    `${location.origin}${listling.util.makeListURL(this._data.lst)}`;
                ui.notify(notification);
            },

            showPresentation: async() => {
                try {
                    await Promise.resolve(document.documentElement.requestFullscreen());
                } catch (e) {
                    // TODO: handle specific error
                }

                const div = document.createElement("div");
                div.style.width = "70ch";
                this.appendChild(div);
                const em = parseFloat(getComputedStyle(div).fontSize);
                const maxWidth = parseFloat(getComputedStyle(div).width);
                div.remove();
                const xs = 1.5 * em / 4;
                const height =
                    1.5 * em + 2 * xs + // UI header
                    xs +
                    1.5 * em + 2 * xs + // Item header
                    2 * xs + // Item padding
                    (maxWidth - 2 * xs) * 9 / 16 + // Web content
                    xs +
                    1.5 * em + // Item detail
                    xs +
                    1.5 * em + 2 * xs; // UI footer
                const width =
                    2 * 1.5 * em + // UI padding
                    2 * xs + // Item padding
                    maxWidth; // Item
                const ratio = Math.min(
                    document.documentElement.clientHeight / height,
                    document.documentElement.clientWidth / width
                );
                document.documentElement.style.fontSize = `${ratio * em}px`;

                this._data.presentation = true;
                this._focus(this.querySelector(".listling-list-items > li"));

                const {short} = await micro.call(
                    "POST", "/api/lists/shorts", {list_id: this._data.lst.id}
                );
                this._data.shortUrl = `${location.origin}/l/${short.split(":")[1]}`;
            },

            startEdit: () => {
                this._data.editMode = true;
                this._form.elements[0].focus();
            },

            edit: async() => {
                let url = this._data.lst ? `/api/lists/${this._data.lst.id}` : "/api/lists";
                let list = await micro.call("POST", url, {
                    title: this._form.elements.title.value,
                    description: this._form.elements.description.value,
                    features: Array.from(this._form.elements.features, e => e.checked && e.value)
                        .filter(feature => feature)
                });
                if (this._data.lst) {
                    this.list = list;
                } else {
                    ui.navigate(`/lists/${list.id.split(":")[1]}`);
                }
            },

            cancelEdit: () => {
                if (this._data.lst) {
                    this._data.editMode = false;
                } else {
                    ui.navigate("/");
                }
            },

            subscribe: async() => {
                let pushSubscription = await ui.service.pushManager.getSubscription();
                if (!pushSubscription || !ui.user.push_subscription) {
                    let result = await ui.enableDeviceNotifications();
                    if (result === "error") {
                        return;
                    }
                }
                this._data.lst.activity = await micro.call(
                    "PATCH", `/api/lists/${this._data.lst.id}/activity`, {op: "subscribe"});
                this.list = this._data.lst;
            },

            unsubscribe: async() => {
                this._data.lst.activity = await micro.call(
                    "PATCH", `/api/lists/${this._data.lst.id}/activity`, {op: "unsubscribe"});
                this.list = this._data.lst;
            },

            moveItemDrag: event => {
                // NOTE: This may be better done by micro.OL itself if some reset attribute is set
                this.querySelector(".listling-list-items").insertBefore(event.detail.li,
                                                                        event.detail.from);
                let to = event.detail.to && event.detail.to.item;
                if (to) {
                    let i = this._data.presentItems.findIndex(item => item.id === to.id);
                    to = this._data.presentItems[i - 1] || null;
                } else {
                    to = this._data.presentItems[this._data.presentItems.length - 1];
                }
                this._moveItem(event.detail.li.item, to);
            },

            moveItemKey: event => {
                let ol = event.target.parentElement;
                let {item} = event.target;
                let i = this._data.presentItems.findIndex(other => other.id === item.id);

                let j = i + (event.detail.dir === "up" ? -2 : 1);
                if (j === -2 || j === this._data.presentItems.length) {
                    return;
                }
                let to = this._data.presentItems[j] || null;

                // Move, then refocus
                this._moveItem(item, to);
                ol.children[i + (event.detail.dir === "up" ? -1 : 1)].focus();
            },

            play: () => {
                this._play();
            }
        });
        micro.bind.bind(this.children, this._data);

        let updateClass = () => {
            this.classList.toggle("listling-list-has-trashed-items", this._data.trashedItemsCount);
            this.classList.toggle("listling-list-mode-view", !this._data.editMode);
            this.classList.toggle("listling-list-mode-edit", this._data.editMode);
            this.classList.toggle("listling-list-presentation", this._data.presentation);
            this.classList.toggle("listling-list-idle", this._data.idle);
            this.classList.toggle(
                "listling-list-can-modify",
                micro.bind.transforms.can(null, "list-modify", this._data.lst)
            );
            for (let feature of ["check", "location", "playlist"]) {
                this.classList.toggle(
                    `listling-list-feature-${feature}`,
                    this._data.lst && this._data.lst.features.includes(feature)
                );
            }
        };
        ["lst", "editMode", "trashedItemsCount", "presentation", "idle"].forEach(
            prop => this._data.watch(prop, updateClass));
        updateClass();

        this._items = null;
        this._form = this.querySelector("form");
        this._events = ["list-items-move"];

        this.addEventListener("play", event => {
            console.log("PLAY", event.target);
            if (event.target !== this._currentItem) {
                if (this._currentItem) {
                    this._currentItem.pause();
                }
                this._currentItem = event.target;
                this._focus(this._currentItem);
            }
        });
    }

    _focus(elem) {
        // window.scroll(
        //     0, elem.offsetTop - (window.innerHeight / 2 - elem.offsetHeight / 2)
        // );
        const em = parseFloat(getComputedStyle(this).fontSize);
        const xs = 1.5 * em / 4;
        window.scroll(0, elem.offsetTop - (1.5 * em + 3 * xs));
        elem.focus();
    }

    _play(item = null) {
        item = item || this.querySelector(".listling-list-items > li");
        item.play();
    }

    attachedCallback() {
        super.attachedCallback();
        ui.shortcutContext.add("B", this._data.toggleTrash);
        ui.shortcutContext.add("C", this._data.toggleSettings);
        this._events.forEach(e => ui.addEventListener(e, this));

        this.ready.when((async() => {
            if (this._data.editMode) {
                this._form.elements[0].focus();
            } else {
                const base = `/api/lists/${this._data.lst.id}`;
                let items = await micro.call("GET", `${base}/items`);
                this._items = new micro.bind.Watchable(items);
                this._data.presentItems = micro.bind.filter(this._items, i => !i.trashed);
                this._data.trashedItems = micro.bind.filter(this._items, i => i.trashed);
                this._data.trashedItemsCount = this._data.trashedItems.length;

                this._data.locations = micro.bind.map(
                    micro.bind.filter(
                        this._items, item => !item.trashed && item.location && item.location.coords
                    ),
                    item => Object.assign({
                        url: listling.util.makeItemURL(null, item),
                        hash: `map-${item.id.split(":")[1]}`
                    }, item.location)
                );

                this._activity = await micro.Activity.open(`${base}/activity/stream`);
                this._activity.events.addEventListener(
                    "list-create-item", event => this._items.push(event.detail.event.detail.item)
                );
                const events = [
                    "editable-edit", "trashable-trash", "trashable-restore", "item-check",
                    "item-uncheck"
                ];
                events.forEach(
                    type => this._activity.events.addEventListener(type, event => {
                        const object = event.detail.event.object;
                        if (!(object && object.__type__ === "Item")) {
                            return;
                        }

                        if (["editable-edit", "trashable-trash"].includes(type)) {
                            if (this._currentItem && this._currentItem.item.id === object.id) {
                                this._play(this._currentItem.nextElementSibling);
                            }
                        }

                        let i = this._items.findIndex(item => item.id === object.id);
                        this._items[i] = object;
                        this._data.trashedItemsCount = this._data.trashedItems.length;
                    })
                );

                if (location.hash === "#p") {
                    this._data.showPresentation();
                    this._play();
                }
            }
        })().catch(micro.util.catch));
    }

    detachedCallback() {
        ui.shortcutContext.remove("B");
        ui.shortcutContext.remove("C");
        this._events.forEach(e => ui.removeEventListener(e, this));
    }

    get list() {
        return this._data.lst;
    }

    set list(value) {
        this._data.lst = value;
        this._data.locationEnabled =
            Boolean(ui.mapServiceKey) && this._data.lst.features.includes("location");
        this._data.editMode = !this._data.lst;
        this.caption = this._data.lst.title;
        ui.url = listling.util.makeListURL(this._data.lst) + location.hash;
        this._playlist =
            this._data.lst.features.includes("playlist") ? new listling.Playlist(this) : null;
    }

    handleEvent(event) {
        if (event.type === "list-items-move") {
            let i = this._items.findIndex(item => item.id === event.detail.item.id);
            this._items.splice(i, 1);
            let j = event.detail.to
                ? this._items.findIndex(item => item.id === event.detail.to.id) + 1 : 0;
            this._items.splice(j, 0, event.detail.item);
        }
    }

    async _moveItem(item, to) {
        ui.dispatchEvent(new CustomEvent("list-items-move", {detail: {item, to}}));
        await micro.call("POST", `/api/lists/${this._data.lst.id}/items/move`, {
            item_id: item.id,
            to_id: to && to.id
        });
    }
};

listling.Playlist = class {
    constructor(page) {
        this.page = page;
        this._data = this.page._data;

        this.page.addEventListener("pause", event => {
            console.log("PAUSE", event.target, this.page._currentItem.time, this.page._currentItem.duration);
            if (this.page._currentItem.time === this.page._currentItem.duration) {
                if (this.page._currentItem.nextElementSibling === null) {
                    this._data.idle = true;
                }
                this.page._play(this.page._currentItem.nextElementSibling);
            }
        });

        this.page.ready.then(() => {
            this.page._activity.events.addEventListener("list-create-item", () => {
                if (this._data.idle) {
                    this._data.idle = false;
                    this.page._play(
                        this.page.querySelector(".listling-list-items > li:last-child")
                    );
                }
            });
        });
    }
};

micro.bind.transforms.can = function(ctx, op, list, item = null) {
    const PERMISSIONS = {
        collaboration: {
            "list-modify": "user",
            "item-modify": "user"
        },
        contribution: {
            "list-modify": "list-owner",
            "item-modify": "item-owner"
        }
    };

    const mode = list && list.features.includes("playlist") ? "contribution" : "collaboration";
    const permission = PERMISSIONS[mode][op];
    return (
        permission === "user" ||
        (permission === "item-owner" && item && item.authors[0].id === ui.user.id) ||
        list && list.authors[0].id === ui.user.id ||
        ui.staff
    );
};

listling.ItemElement = class extends HTMLLIElement {
    createdCallback() {
        this.appendChild(
            document.importNode(ui.querySelector(".listling-item-template").content, true));
        this._data = new micro.bind.Watchable({
            item: null,
            editMode: true,
            resourceElem: null,
            makeItemURL: listling.util.makeItemURL,

            play: () => {
                this.play();
            },

            startEdit: () => {
                this._data.editMode = true;
                this._form.elements[0].focus();
            },

            edit: async() => {
                const text = this._form.elements.text.value;
                const match = text.match(/^https?:\/\/\S+/u);
                const resource = match ? match[0] : null;
                let url = this._data.item
                    ? `/api/lists/${ui.page.list.id}/items/${this._data.item.id}`
                    : `/api/lists/${ui.page.list.id}/items`;

                let item;
                try {
                    item = await micro.call("POST", url, {
                        text,
                        resource,
                        title: this._form.elements.title.value,
                        location: this._form.elements.location.wrapper.value
                    });
                } catch (e) {
                    if (
                        e instanceof micro.APIError && [
                            "CommunicationError", "NoResourceError", "ForbiddenResourceError",
                            "BrokenResourceError"
                        ].includes(e.error.__type__)
                    ) {
                        ui.notify("Oops, there was a problem opening the link. Please try again in a few moments.");
                        return;
                    }
                    ui.handleCallError(e);
                    return;
                }

                if (!this._data.item) {
                    this._form.reset();
                    this._form.elements.location.wrapper.value = null;
                }
                if (this.onedit) {
                    this.onedit(new CustomEvent("edit"));
                }
            },

            cancelEdit: () => {
                if (this._data.item) {
                    this._data.editMode = false;
                } else {
                    this._form.reset();
                    this._form.elements.location.wrapper.value = null;
                }
                if (this.oncancel) {
                    this.oncancel(new CustomEvent("cancel"));
                }
            },

            trash: async() => {
                await micro.call(
                    "POST", `/api/lists/${ui.page.list.id}/items/${this._data.item.id}/trash`);
            },

            restore: async() => {
                await micro.call(
                    "POST", `/api/lists/${ui.page.list.id}/items/${this._data.item.id}/restore`);
            },

            check: async() => {
                await micro.call(
                    "POST", `/api/lists/${ui.page.list.id}/items/${this._data.item.id}/check`);
            },

            uncheck: async() => {
                await micro.call(
                    "POST", `/api/lists/${ui.page.list.id}/items/${this._data.item.id}/uncheck`);
            }
        });
        micro.bind.bind(this.children, this._data);

        let updateClass = () => {
            this.classList.toggle(
                "listling-item-has-location",
                this._data.item && this._data.item.location
            );
            this.classList.toggle(
                "listling-item-has-location-coords",
                this._data.item && this._data.item.location && this._data.item.location.coords
            );
            this.classList.toggle("listling-item-trashed",
                                  this._data.item && this._data.item.trashed);
            this.classList.toggle("listling-item-checked",
                                  this._data.item && this._data.item.checked);
            this.classList.toggle("listling-item-mode-view", !this._data.editMode);
            this.classList.toggle("listling-item-mode-edit", this._data.editMode);
            this.classList.toggle(
                "listling-item-can-modify",
                micro.bind.transforms.can(
                    null, "item-modify", ui.page && ui.page.list, this._data.item
                )
            );
        };
        this._data.watch("item", updateClass);
        this._data.watch("editMode", updateClass);
        updateClass();

        this.tabIndex = 0;
        this.shortcutContext = new micro.keyboard.ShortcutContext(this);
        let move = dir => micro.util.dispatchEvent(this, new CustomEvent("move", {detail: {dir}}));
        this.shortcutContext.add("Alt+ArrowUp", move.bind(null, "up"));
        this.shortcutContext.add("Alt+ArrowDown", move.bind(null, "down"));

        this._form = this.querySelector("form");
        this._timeout = null;
        this._interval = null;

        this.static_duration = 30;
        this.max_duration = 5 * 60;
    }

    get item() {
        return this._data.item;
    }

    set item(value) {
        this._data.item = value;
        this._data.editMode = !this._data.item;
        this.id = this._data.item ? `items-${this._data.item.id.split(":")[1]}` : "";

        this._data.resourceElem = micro.bind.transforms.renderResource(null, value.resource);
        if (this._playable) {
            this._data.resourceElem.addEventListener("play", () => {
                if (!this._interval) {
                    this._interval = setInterval(() => {
                        if (this._data.resourceElem.time >= this.max_duration) {
                            console.log("max time reached", this._data.resourceElem.time);
                            this._data.resourceElem.pause();
                        }
                    }, 1000);
                    this.dispatchEvent(new CustomEvent("play", {bubbles: true}));
                }
            });
            this._data.resourceElem.addEventListener("pause", () => {
                if (this._interval) {
                    clearInterval(this._interval);
                    this._interval = null;
                    this.dispatchEvent(new CustomEvent("pause", {bubbles: true}));
                }
            });
        }
    }

    play() {
        if (this._playable) {
            this._data.resourceElem.play({reset: true});
        } else {
            if (!this._timeout) {
                this._startTime = new Date();
                this._timeout = setTimeout(() => this.pause(), this.duration * 1000);
                this.dispatchEvent(new CustomEvent("play", {bubbles: true}));
            }
        }
    }

    pause() {
        if (this._playable) {
            this._data.resourceElem.pause();
        } else {
            if (this._timeout) {
                clearTimeout(this._timeout);
                this._timeout = null;
                this.dispatchEvent(new CustomEvent("pause", {bubbles: true}));
            }
        }
    }

    get time() {
        return this._playable ? Math.min(this._data.resourceElem.time, this.max_duration)
            : Math.min((new Date() - this._startTime) / 1000, this.duration);
    }

    get duration() {
        return this._playable ? Math.min(this._data.resourceElem.duration, this.max_duration)
            : this.static_duration;
    }

    get _playable() {
        return this._data.resourceElem && "play" in this._data.resourceElem;
    }
};

document.registerElement("listling-ui", {prototype: listling.UI.prototype, extends: "body"});
document.registerElement("listling-start-page", listling.StartPage);
document.registerElement("listling-list-page", listling.ListPage);
document.registerElement("listling-item",
                         {prototype: listling.ItemElement.prototype, extends: "li"});
