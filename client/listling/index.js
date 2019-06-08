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
            {url: "^/$", page: listling.components.start.StartPage.make},
            {url: "^/intro$", page: "listling-intro-page"},
            {url: "^/about$", page: makeAboutPage},
            {url: "^/lists/([^/]+)(?:/[^/]+)?$", page: listling.ListPage.make}
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
 * Intro page.
 */
listling.IntroPage = class extends micro.Page {
    createdCallback() {
        super.createdCallback();
        const useCases = listling.components.start.getUseCases();
        this.appendChild(
            document.importNode(ui.querySelector(".listling-intro-page-template").content, true));
        this._data = new micro.bind.Watchable({
            settings: ui.settings,
            useCases,
            selectedUseCase: useCases[0],
            createList: listling.components.start.createList,

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

            createExample: async useCase => {
                try {
                    const list = await ui.call(
                        "POST", "/api/lists/create-example", {use_case: useCase.id}
                    );
                    ui.navigate(`/lists/${list.id.split(":")[1]}`).catch(micro.util.catch);
                } catch (e) {
                    ui.handleCallError(e);
                }
            }
        });
        micro.bind.bind(this.children, this._data);
    }

    attachedCallback() {
        super.attachedCallback();
        ui.shortcutContext.add("S", () => {
            this.querySelector(".listling-selected .listling-intro-create-list").click();
        });
        ui.shortcutContext.add("E", () => {
            if (this._data.selectedUseCase.id !== "simple") {
                this.querySelector(".listling-selected .listling-intro-create-example button")
                    .click();
            }
        });
        ui.url = "/intro";
    }

    detachedCallback() {
        ui.shortcutContext.remove("S");
        ui.shortcutContext.remove("E");
    }
};

listling.ListPage = class extends micro.Page {
    static async make(url, id) {
        let page = document.createElement("listling-list-page");
        if (id !== "new") {
            page.list = await ui.call("GET", `/api/lists/List:${id}`);
        }
        return page;
    }

    createdCallback() {
        super.createdCallback();
        this.appendChild(
            document.importNode(ui.querySelector(".listling-list-page-template").content, true));
        this._data = new micro.bind.Watchable({
            lst: null,
            modes: ["collaborate", "view"],
            modeToText: (ctx, mode) => ({collaborate: "Collaborate", view: "View"}[mode]),
            presentItems: null,
            trashedItems: null,
            trashedItemsCount: 0,
            locations: null,
            locationEnabled: false,
            editMode: true,
            trashExpanded: false,
            creatingItem: false,
            settingsExpanded: false,
            toggleTrash: () => {
                this._data.trashExpanded = !this._data.trashExpanded;
            },
            startCreateItem: () => {
                this._data.creatingItem = true;
                this.querySelector(".listling-list-create-item [is=listling-item]").focus();
            },
            stopCreateItem: () => {
                this._data.creatingItem = false;
            },
            toggleSettings: () => {
                this._data.settingsExpanded = !this._data.settingsExpanded;
            },

            startEdit: () => {
                this._data.editMode = true;
            },

            edit: async() => {
                try {
                    const url = this._data.lst ? `/api/lists/${this._data.lst.id}` : "/api/lists";
                    const list = await ui.call("POST", url, {
                        title: this._form.elements.title.value,
                        description: this._form.elements.description.value,
                        features:
                            Array.from(this._form.elements.features, e => e.checked && e.value)
                                .filter(feature => feature),
                        mode: this._form.elements.mode.valueAsObject
                    });
                    if (this._data.lst) {
                        this.list = list;
                    } else {
                        ui.navigate(`/lists/${list.id.split(":")[1]}`).catch(micro.util.catch);
                    }
                } catch (e) {
                    ui.handleCallError(e);
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

                try {
                    this._data.lst.activity = await ui.call(
                        "PATCH", `/api/lists/${this._data.lst.id}/activity`, {op: "subscribe"}
                    );
                    this.list = this._data.lst;
                } catch (e) {
                    ui.handleCallError(e);
                }
            },

            unsubscribe: async() => {
                try {
                    this._data.lst.activity = await ui.call(
                        "PATCH", `/api/lists/${this._data.lst.id}/activity`, {op: "unsubscribe"}
                    );
                    this.list = this._data.lst;
                } catch (e) {
                    ui.handleCallError(e);
                }
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

            may: (ctx, op, mode) => {
                // eslint-disable-next-line no-underscore-dangle
                const permissions = listling.ListPage._PERMISSIONS[mode || "view"];
                return (
                    permissions.user.has(op) ||
                    this._data.lst && ui.user.id === this._data.lst.authors[0].id
                );
            }
        });
        micro.bind.bind(this.children, this._data);

        let updateClass = () => {
            this.classList.toggle("listling-list-has-trashed-items", this._data.trashedItemsCount);
            this.classList.toggle("listling-list-mode-view", !this._data.editMode);
            this.classList.toggle("listling-list-mode-edit", this._data.editMode);
            for (let feature of ["check", "location"]) {
                this.classList.toggle(
                    `listling-list-feature-${feature}`,
                    this._data.lst && this._data.lst.features.includes(feature)
                );
            }
            this.classList.toggle(
                "listling-list-may-modify",
                this._data.may(null, "list-modify", this._data.lst && this._data.lst.mode)
            );
        };
        ["lst", "editMode", "trashedItemsCount"].forEach(
            prop => this._data.watch(prop, updateClass));
        updateClass();

        this._items = null;
        this._form = this.querySelector("form");
        this._events = ["list-items-create", "list-items-move", "item-edit", "item-trash",
                        "item-restore", "item-check", "item-uncheck"];
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
                try {
                    const items = await ui.call("GET", `/api/lists/${this._data.lst.id}/items`);
                    this._items = new micro.bind.Watchable(items);
                } catch (e) {
                    ui.handleCallError(e);
                    return;
                }

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
            }
        })().catch(micro.util.catch));

        // Add list to lists of user
        (async() => {
            try {
                await ui.call(
                    "POST", `/api/users/${ui.user.id}/lists`, {list_id: this._data.lst.id}
                );
            } catch (e) {
                ui.handleCallError(e);
            }
        })().catch(micro.util.catch);
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
    }

    handleEvent(event) {
        if (event.type === "list-items-create") {
            this._items.push(event.detail.item);
        } else if (event.type === "list-items-move") {
            let i = this._items.findIndex(item => item.id === event.detail.item.id);
            this._items.splice(i, 1);
            let j = event.detail.to
                ? this._items.findIndex(item => item.id === event.detail.to.id) + 1 : 0;
            this._items.splice(j, 0, event.detail.item);
        } else if (
            ["item-edit", "item-trash", "item-restore", "item-check", "item-uncheck"]
                .includes(event.type)) {
            let i = this._items.findIndex(item => item.id === event.detail.item.id);
            this._items[i] = event.detail.item;
            this._data.trashedItemsCount = this._data.trashedItems.length;
        }
    }

    async _moveItem(item, to) {
        ui.dispatchEvent(new CustomEvent("list-items-move", {detail: {item, to}}));
        try {
            await ui.call("POST", `/api/lists/${this._data.lst.id}/items/move`, {
                item_id: item.id,
                to_id: to && to.id
            });
        } catch (e) {
            ui.handleCallError(e);
        }
    }
};

// eslint-disable-next-line no-underscore-dangle
listling.ListPage._PERMISSIONS = {
    collaborate: {user: new Set(["list-modify", "item-modify"])},
    view: {user: new Set()}
};

listling.ItemElement = class extends HTMLLIElement {
    createdCallback() {
        this.appendChild(
            document.importNode(ui.querySelector(".listling-item-template").content, true));
        this._data = new micro.bind.Watchable({
            item: null,
            lst: null,
            editMode: true,
            isCheckDisabled:
                (ctx, trashed, mode) => trashed || !this._data.may(ctx, "item-modify", mode),
            makeItemURL: listling.util.makeItemURL,

            startEdit: () => {
                this._data.editMode = true;
                this.focus();
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
                    item = await ui.call("POST", url, {
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
                    } else {
                        ui.handleCallError(e);
                    }
                    return;
                }

                if (this._data.item) {
                    ui.dispatchEvent(new CustomEvent("item-edit", {detail: {item}}));
                } else {
                    this._form.reset();
                    this._form.elements.location.wrapper.value = null;
                    ui.dispatchEvent(new CustomEvent("list-items-create", {detail: {item}}));
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
                try {
                    const item = await ui.call(
                        "POST", `/api/lists/${ui.page.list.id}/items/${this._data.item.id}/trash`
                    );
                    ui.dispatchEvent(new CustomEvent("item-trash", {detail: {item}}));
                } catch (e) {
                    ui.handleCallError(e);
                }
            },

            restore: async() => {
                try {
                    const item = await ui.call(
                        "POST", `/api/lists/${ui.page.list.id}/items/${this._data.item.id}/restore`
                    );
                    ui.dispatchEvent(new CustomEvent("item-restore", {detail: {item}}));
                } catch (e) {
                    ui.handleCallError(e);
                }
            },

            check: async() => {
                try {
                    const item = await ui.call(
                        "POST", `/api/lists/${ui.page.list.id}/items/${this._data.item.id}/check`
                    );
                    ui.dispatchEvent(new CustomEvent("item-check", {detail: {item}}));
                } catch (e) {
                    ui.handleCallError(e);
                }
            },

            uncheck: async() => {
                try {
                    const item = await ui.call(
                        "POST", `/api/lists/${ui.page.list.id}/items/${this._data.item.id}/uncheck`
                    );
                    ui.dispatchEvent(new CustomEvent("item-uncheck", {detail: {item}}));
                } catch (e) {
                    ui.handleCallError(e);
                }
            },

            may: (ctx, op, mode) => {
                // eslint-disable-next-line no-underscore-dangle
                const permissions = listling.ListPage._PERMISSIONS[mode || "view"];
                return (
                    permissions.user.has(op) ||
                    this._data.lst && ui.user.id === this._data.lst.authors[0].id
                );
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
                "listling-item-may-modify",
                this._data.may(null, "item-modify", this._data.lst && this._data.lst.mode)
            );
        };
        this._data.watch("item", updateClass);
        this._data.watch("lst", updateClass);
        this._data.watch("editMode", updateClass);
        updateClass();

        this.tabIndex = 0;
        this.shortcutContext = new micro.keyboard.ShortcutContext(this);
        let move = dir => micro.util.dispatchEvent(this, new CustomEvent("move", {detail: {dir}}));
        this.shortcutContext.add("Alt+ArrowUp", move.bind(null, "up"));
        this.shortcutContext.add("Alt+ArrowDown", move.bind(null, "down"));

        this._form = this.querySelector("form");
    }

    get item() {
        return this._data.item;
    }

    set item(value) {
        this._data.item = value;
        this._data.lst = ui.page.list;
        this._data.editMode = !this._data.item;
        this.id = this._data.item ? `items-${this._data.item.id.split(":")[1]}` : "";
    }
};

document.registerElement("listling-ui", {prototype: listling.UI.prototype, extends: "body"});
document.registerElement("listling-intro-page", listling.IntroPage);
document.registerElement("listling-list-page", listling.ListPage);
document.registerElement("listling-item",
                         {prototype: listling.ItemElement.prototype, extends: "li"});
