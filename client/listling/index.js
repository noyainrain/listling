/*
 * Open Listling
 * Copyright (C) 2017 Open Listling contributors
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

window.listling = {};

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
            {url: "^/lists/([^/]+)$", page: listling.ListPage.make}
        ]);
    }
};

/**
 * TODO.
 */
listling.StartPage = class extends micro.Page {
    createdCallback() {
        super.createdCallback();
        this.appendChild(
            document.importNode(ui.querySelector(".listling-start-page-template").content, true));
        this.querySelector(".micro-logo span").textContent = ui.settings.title;
        this.querySelector(".micro-logo img").src = ui.settings.icon || "";
        this.querySelector(".listling-start-lists").addEventListener("select", this);
    }

    handleEvent(event) {
        if (event.type === "select") {
            this.querySelector(".listling-selected").classList.remove("listling-selected");
            event.target.classList.add("listling-selected");
        }
    }
}

/**
 * TODO.
 */
listling.UseCaseElement = class extends HTMLLIElement {
    createdCallback() {
        this.appendChild(
            document.importNode(ui.querySelector(".listling-use-case-template").content, true));
        //this.tabIndex = 0;
        this.querySelector("h1").textContent = this.getAttribute("titl");
        this.querySelector("span").classList.add(`fa-${this.getAttribute("icon")}`);
        this.addEventListener("mouseenter", this);
        this.querySelector("a").addEventListener("focus", this);
        let button = this.querySelector("button");
        console.log("kind", this.getAttribute("kind"));
        console.log(button);
        button.run = async () => {
            let list = await micro.call("POST", `/api/lists/create-example`, {kind: this.getAttribute("kind")});
            ui.navigate(`/lists/${list.id.split(":")[1]}`);
        }
        button.addEventListener("focus", this);
    }

    handleEvent(event) {
        // on mobile, mouseenter is followed by click. delay select event so click cannot interact
        // with child elements that just became visible
        setTimeout(x => this.dispatchEvent(new CustomEvent("select", {bubbles: true})), 0);
    }
}

listling.ListPage = class extends micro.Page {
    static async make(url, id) {
        let page = document.createElement("listling-list-page");
        if (id === "new") {
            page.edit = true;
        } else {
            page.list = await micro.call("GET", `/api/lists/List:${id}`);
        }
        return page;
    }

    createdCallback() {
        super.createdCallback();
        this.appendChild(
            document.importNode(ui.querySelector(".listling-list-page-template").content, true));
        this.querySelector("form > :not(header) button").run = this._edit.bind(this);
        this.querySelector(".action").run = () => this.edit = true;
        this.querySelector(".action-cancel").run = this._cancel.bind(this);
        this.querySelector(".listling-list-create-item .action").run = this._createItem.bind(this);
        this._trashDiv = this.querySelector(".listling-list-trash");
        this.querySelector(".listling-list-trash > p .link").run =
            () => this._trashDiv.classList.add("listling-list-trash-expanded");
        this.querySelector(".listling-list-trash > div .link").run =
            () => this._trashDiv.classList.remove("listling-list-trash-expanded");
        this._form = this.querySelector("form");
        this._list = null;
        this.edit = false;

        ui.addEventListener("list-items-create", this);
        ui.addEventListener("list-items-move", this);
        ui.addEventListener("item-edit", this);
        ui.addEventListener("item-trash", this);
        ui.addEventListener("item-restore", this);
        this._itemsUl = this.querySelector(".listling-list-items")
        this._itemsUl.addEventListener("moveitem", this);

        this._items = new micro.bind.Watchable([]);
        let trashedItems = micro.bind.filter(this._items, i => i.trashed);
        let trashUl = this.querySelector(".listling-list-trash ul");
        this._itemsUl.appendChild(micro.bind.list(this._itemsUl, this._items, "item", micro.bind.filter, i => !i.trashed));
        trashUl.appendChild(micro.bind.list(trashUl, trashedItems, "item"));
        let foo = () => {
            this.classList.toggle("listling-list-has-trashed-items", trashedItems.length);
            this.querySelector(".listling-list-trash span").textContent =
                trashedItems.length === 1 ? "There is one trashed item." :
                    `There are ${trashedItems.length} trashed items.`;
        }
        trashedItems.watch(Symbol.for("+"), foo);
        trashedItems.watch(Symbol.for("-"), foo);
    }

    async attachedCallback() {
        //let panel = this.querySelector(".listling-list-create-item");

        if (!this.edit) {
            let items = await micro.call("GET", `/api/lists/${this._list.id}/items`);
            this._items.splice(0, 0, ...items);
        }

        // TODO
        /*allItems = new micro.bind.Watchable(items);
        items = micro.bind.filter(allItems, i => !i.trashed);
        trashedItems = micro.bind.filter(allItems, i => i.trashed);*/

        // TODO

        /*items.watch(Symbol.for("+"), (prop, value) => {
            let li = document.createElement("li", "listling-item");
            li.list = this._list;
            li.item = value;
            ul.insertBefore(li, ul.children[parseInt(prop)]);
        });
        items.watch(Symbol.for("-"), (prop, value) => {
            ul.children[parseInt(prop)].remove();
        });*/
        // TODO: same for trashedItems, but with other ul

        /*for (let item of items) {
            let li = document.createElement("li", "listling-item");
            li.list = this._list;
            li.item = item;
            console.log(item);
            ul.insertBefore(li, panel);
        }*/
    }

    get list() {
        return this._list;
    }

    set list(value) {
        this._list = value;
        this.querySelector("h1 span").textContent = this._form.elements.title.value =
            this._list.title;
        this.querySelector(".listling-list-description").textContent =
            this._form.elements.description.value = this._list.description || "";
        let span = this.querySelector(".listling-detail span:not(.fa)");
        let fragment = micro.bind.join(span, this._list && this._list.authors, "user");
        span.textContent = "";
        span.appendChild(fragment);
    }

    get edit() {
        return this._edit;
    }

    set edit(value) {
        this._edit = value;
        Array.from(this.querySelectorAll(".view")).forEach(e => e.style.display = this._edit ? "none" : "");
        Array.from(this.querySelectorAll(".edit")).forEach(e => e.style.display = this._edit ? "" : "none");
    }

    _createItem() {
        let div = this.querySelector(".listling-list-create-item");
        let li = div.querySelector("li");
        // TODO: add event listeners in create
        li.addEventListener("cancel", () => {
            div.classList.remove("listling-list-create");
            li.item = null;
        });
        li.addEventListener("done", () => {
            div.classList.remove("listling-list-create");
            li.item = null;
        });
        div.classList.add("listling-list-create");
    }

    async _edit() {
        let url = this._list ? `/api/lists/${this._list.id}` : "/api/lists";
        let list = await micro.call("POST", url, {
            title: this._form.elements.title.value,
            description: this._form.elements.description.value
        });
        if (this._list) {
            this.list = list;
            this.edit = false;
        } else {
            ui.navigate(`/lists/${list.id.split(":")[1]}`);
        }
    }

    _cancel() {
        if (this._list) {
            this.edit = false;
        } else {
            ui.navigate("/");
        }
    }

    async handleEvent(event) {
        if (event.type === "list-items-create") {
            this._items.splice(this._items.length, 0, event.detail.item);
        } else if (["item-edit", "item-trash", "item-restore"].includes(event.type)) {
            let i = this._items.findIndex(i => i.id === event.detail.item.id);
            this._items[i] = event.detail.item;
        } else if (event.type === "list-items-move") {
            let i = this._items.findIndex(i => i.id === event.detail.item.id);
            this._items.splice(i, 1);
            let j = event.detail.to ? this._items.findIndex(i => i.id === event.detail.to.id) + 1 : 0;
            this._items.splice(j, 0, event.detail.item);
            console.log("IJ", i, j, event.detail.item, event.detail.to);
        } else if (event.type === "moveitem") {
            // FIXME _to in micro
            this._itemsUl.insertBefore(event.detail.li, event.detail.from);
            let item = event.detail.li.item;
            let to = event.detail.to ? event.detail.to.previousElementSibling : this._itemsUl.lastElementChild;
            to = to && to.item;

            ui.dispatchEvent(new CustomEvent("list-items-move", {detail: {item, to}}));

            await micro.call("POST", `/api/lists/${this._list.id}/items/move`, {
                item_id: item.id,
                to_id: to && to.id
            });
            // TODO: handle two bad cases: item has been trashed or to has been trashed
            console.log("MOVED SERVER");
        }
    }
}

listling.ItemElement = class extends HTMLLIElement {
    createdCallback() {
        this.appendChild(
            document.importNode(ui.querySelector(".listling-item-template").content, true));
        this.querySelector(".listling-item-edit").run = () => this._toggleEdit(true);
        this.querySelector(".listling-item-trash").run = this._trash.bind(this);
        this.querySelector(".listling-item-restore").run = this._restore.bind(this);
        this.querySelector(".action-done").run = this._edit.bind(this);
        this.querySelector(".action-cancel").run = this._cancel.bind(this);
        this._form = this.querySelector("form");
        //this.list = null;
        this.item = null;
    }

    get item() {
        return this._item;
    }

    set item(value) {
        this._item = value;
        this.classList.toggle("listling-item-trashed", this._item && this._item.trashed);
        this.querySelector("h1 span").textContent = this._form.elements.title.value =
            this._item && this._item.title || "";
        this.querySelector(".listling-item-description").textContent =
            this._form.elements.description.value = this._item && this._item.description || "";
        let span = this.querySelector(".listling-detail span:not(.fa)");
        let fragment = micro.bind.join(span, this._item && this._item.authors, "user");
        span.textContent = "";
        span.appendChild(fragment);
        this._toggleEdit(this._item === null);
    }

    _toggleEdit(edit) {
        console.log("EDIT", edit, this._item);
        this._edit = edit;
        this.classList.toggle("listling-item-mode-edit", this._edit);
        /*this.querySelectorAll(".listling-item-mode-view").forEach(e => e.style.display = this._edit ? "none" : "");
        this.querySelectorAll(".listling-item-mode-edit").forEach(e => e.style.display = this._edit
        ? "" : "none");*/
    }

    async _edit() {
        let url = this._item ? `/api/lists/${ui.page.list.id}/items/${this._item.id}` : `/api/lists/${ui.page.list.id}/items`;
        let item = await micro.call("POST", url, {
            title: this._form.elements.title.value,
            description: this._form.elements.description.value
        });
        if (this._item) {
            ui.dispatchEvent(new CustomEvent("item-edit", {detail: {item}}));
        } else {
            ui.dispatchEvent(new CustomEvent("list-items-create", {detail: {item}}));
        }
        this.dispatchEvent(new CustomEvent("done"));
    }

    async _trash() {
        await micro.call("POST", `/api/lists/${ui.page.list.id}/items/${this._item.id}/trash`);
        ui.dispatchEvent(
            new CustomEvent("item-trash",
                            {detail: {item: Object.assign({}, this._item, {trashed: true})}}));
    }

    async _restore() {
        await micro.call("POST", `/api/lists/${ui.page.list.id}/items/${this._item.id}/restore`);
        ui.dispatchEvent(
            new CustomEvent("item-restore",
                            {detail: {item: Object.assign({}, this._item, {trashed: false})}}));
    }

    _cancel() {
        if (this._item) {
            this._toggleEdit(false);
        }
        this.dispatchEvent(new CustomEvent("cancel"));
    }
}

document.registerElement("listling-ui", {prototype: listling.UI.prototype, extends: "body"});
document.registerElement("listling-start-page", listling.StartPage);
document.registerElement("listling-use-case", {prototype: listling.UseCaseElement.prototype, extends: "li"});
document.registerElement("listling-list-page", listling.ListPage);
document.registerElement("listling-item", {prototype: listling.ItemElement.prototype, extends: "li"});
