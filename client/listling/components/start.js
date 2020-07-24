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

/** Start page. */

"use strict";

self.listling = self.listling || {};
listling.components = listling.components || {};
listling.components.start = {};

/** Create a :ref:`List` for the given *useCase* and open it. */
listling.components.start.createList = async function(useCase) {
    try {
        const list = await ui.call("POST", "/api/lists", {use_case: useCase, v: 2});
        ui.navigate(`/lists/${list.id.split(":")[1]}`).catch(micro.util.catch);
    } catch (e) {
        ui.handleCallError(e);
    }
};

/** Return available list use cases. */
listling.components.start.getUseCases = function() {
    return [
        {id: "todo", title: "To-Do list", icon: "check"},
        {id: "poll", title: "Poll", icon: "poll"},
        {id: "shopping", title: "Shopping list", icon: "shopping-cart"},
        {id: "meeting-agenda", title: "Meeting agenda", icon: "handshake"},
        {id: "playlist", title: "Playlist", icon: "play"},
        ...ui.mapServiceKey ? [{id: "map", title: "Map", icon: "map"}] : [],
        {id: "simple", title: "Simple list", icon: "list"}
    ];
};

/** Start page. */
listling.components.start.StartPage = class extends micro.Page {
    static async make() {
        const lists = new micro.Collection(`/api/users/${ui.user.id}/lists`);
        await lists.fetch(10);
        if (lists.count === 0) {
            return document.createElement("listling-intro-page");
        }
        const page = document.createElement("listling-start-page");
        page.lists = lists;
        return page;
    }

    createdCallback() {
        super.createdCallback();
        this.appendChild(
            document.importNode(ui.querySelector("#listling-start-page-template").content, true)
        );
        this._data = new micro.bind.Watchable({
            user: ui.user,
            lists: null,
            listsComplete: false,
            useCases: listling.components.start.getUseCases(),
            createList: listling.components.start.createList,
            makeListURL: listling.util.makeListURL,

            startCreateList: () => {
                this.querySelector(".listling-start-create micro-contextual").scrollIntoView(false);
            },

            remove: async list => {
                try {
                    await ui.call("DELETE", `/api/users/${ui.user.id}/lists/${list.id}`);
                } catch (e) {
                    if (e instanceof micro.APIError && e.error.__type__ === "NotFoundError") {
                        // Continue as normal if the list has already been removed
                    } else {
                        ui.handleCallError(e);
                        return;
                    }
                }
                const i = this._data.lists.items.findIndex(l => l.id === list.id);
                this._data.lists.items.splice(i, 1);
                if (this._data.lists.items.length === 0) {
                    ui.navigate("/intro").catch(micro.util.catch);
                }
            },

            onListKeyDown: event => {
                if (event.currentTarget === event.target && event.key === "Enter") {
                    event.currentTarget.firstElementChild.click();
                }
            },

            onUseCaseKeyDown: event => {
                if (event.key === "Enter") {
                    event.target.click();
                }
            }
        });
        micro.bind.bind(this.children, this._data);
    }

    /** :ref:`Lists` of the user. */
    get lists() {
        return this._data.lists;
    }

    set lists(value) {
        this._data.lists = value;
        this._data.lists.events.addEventListener("fetch", () => {
            this._data.listsComplete = this._data.lists.complete;
        });
        this._data.listsComplete = this._data.lists.complete;
    }
};

document.registerElement("listling-start-page", listling.components.start.StartPage);
