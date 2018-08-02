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
 * Start page.
 */
listling.StartPage = class extends micro.Page {
    createdCallback() {
        const USE_CASES = [
            {id: "todo", title: "To-Do list", icon: "check"},
            {id: "shopping", title: "Shopping list", icon: "shopping-cart"},
            {id: "meeting-agenda", title: "Meeting agenda", icon: "handshake"},
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
        let page = document.createElement("listling-list-page");
        if (id !== "new") {
            page.list = await micro.call("GET", `/api/lists/List:${id}`);
        }
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
            editMode: true,
            trashExpanded: false,
            creatingItem: false,
            settingsExpanded: false,
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

            startEdit: () => {
                this._data.editMode = true;
                this._form.elements[0].focus();
            },

            edit: async() => {
                let url = this._data.lst ? `/api/lists/${this._data.lst.id}` : "/api/lists";
                let list = await micro.call("POST", url, {
                    title: this._form.elements.title.value,
                    description: this._form.elements.description.value,
                    features: Array.from([this._form.elements.features], e => e.checked && e.value)
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
            }
        });
        micro.bind.bind(this.children, this._data);

        let updateClass = () => {
            this.classList.toggle("listling-list-has-trashed-items", this._data.trashedItemsCount);
            this.classList.toggle("listling-list-mode-view", !this._data.editMode);
            this.classList.toggle("listling-list-mode-edit", this._data.editMode);
            this.classList.toggle("listling-list-feature-check",
                                  this._data.lst && this._data.lst.features.includes("check"));
        };
        ["lst", "editMode", "trashedItemsCount"].forEach(
            prop => this._data.watch(prop, updateClass));
        updateClass();

        this._items = null;
        this._form = this.querySelector("form");
        this._events = ["list-items-create", "list-items-move", "item-edit", "item-trash",
                        "item-restore", "item-check", "item-uncheck"];
    }

    async attachedCallback() {
        ui.shortcutContext.add("B", this._data.toggleTrash);
        ui.shortcutContext.add("C", this._data.toggleSettings);
        this._events.forEach(e => ui.addEventListener(e, this));
        if (this._data.editMode) {
            this._form.elements[0].focus();
        } else {
            let items = await micro.call("GET", `/api/lists/${this._data.lst.id}/items`);
            this._items = new micro.bind.Watchable(items);
            this._data.presentItems = micro.bind.filter(this._items, i => !i.trashed);
            this._data.trashedItems = micro.bind.filter(this._items, i => i.trashed);
            this._data.trashedItemsCount = this._data.trashedItems.length;
        }
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
        this._data.editMode = !this._data.lst;
        this.caption = this._data.lst.title;
        history.replaceState(null, null, listling.util.makeListURL(this._data.lst));
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
        await micro.call("POST", `/api/lists/${this._data.lst.id}/items/move`, {
            item_id: item.id,
            to_id: to && to.id
        });
    }
};

listling.ItemElement = class extends HTMLLIElement {
    createdCallback() {
        this.appendChild(
            document.importNode(ui.querySelector(".listling-item-template").content, true));
        this._data = new micro.bind.Watchable({
            item: null,
            editMode: true,

            startEdit: () => {
                this._data.editMode = true;
                this._form.elements[0].focus();
            },

            edit: async() => {
                let url = this._data.item
                    ? `/api/lists/${ui.page.list.id}/items/${this._data.item.id}`
                    : `/api/lists/${ui.page.list.id}/items`;
                let item = await micro.call("POST", url, {
                    title: this._form.elements.title.value,
                    text: this._form.elements.text.value
                });
                if (this._data.item) {
                    ui.dispatchEvent(new CustomEvent("item-edit", {detail: {item}}));
                } else {
                    this._form.reset();
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
                }
                if (this.oncancel) {
                    this.oncancel(new CustomEvent("cancel"));
                }
            },

            trash: async() => {
                let item = await micro.call(
                    "POST", `/api/lists/${ui.page.list.id}/items/${this._data.item.id}/trash`);
                ui.dispatchEvent(new CustomEvent("item-trash", {detail: {item}}));
            },

            restore: async() => {
                let item = await micro.call(
                    "POST", `/api/lists/${ui.page.list.id}/items/${this._data.item.id}/restore`);
                ui.dispatchEvent(new CustomEvent("item-restore", {detail: {item}}));
            },

            check: async() => {
                let item = await micro.call(
                    "POST", `/api/lists/${ui.page.list.id}/items/${this._data.item.id}/check`);
                ui.dispatchEvent(new CustomEvent("item-check", {detail: {item}}));
            },

            uncheck: async() => {
                let item = await micro.call(
                    "POST", `/api/lists/${ui.page.list.id}/items/${this._data.item.id}/uncheck`);
                ui.dispatchEvent(new CustomEvent("item-uncheck", {detail: {item}}));
            }
        });
        micro.bind.bind(this.children, this._data);

        let updateClass = () => {
            this.classList.toggle("listling-item-trashed",
                                  this._data.item && this._data.item.trashed);
            this.classList.toggle("listling-item-checked",
                                  this._data.item && this._data.item.checked);
            this.classList.toggle("listling-item-mode-view", !this._data.editMode);
            this.classList.toggle("listling-item-mode-edit", this._data.editMode);
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
    }

    get item() {
        return this._data.item;
    }

    set item(value) {
        this._data.item = value;
        this._data.editMode = !this._data.item;
    }
};

document.registerElement("listling-ui", {prototype: listling.UI.prototype, extends: "body"});
document.registerElement("listling-start-page", listling.StartPage);
document.registerElement("listling-list-page", listling.ListPage);
document.registerElement("listling-item",
                         {prototype: listling.ItemElement.prototype, extends: "li"});
