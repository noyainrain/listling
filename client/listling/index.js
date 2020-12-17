/*
 * Open Listling
 * Copyright (C) 2020 Open Listling contributors
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
            {url: "^/share$", page: "listling-share-page"},
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
                this.querySelector(".listling-selected .listling-intro-create-example").click();
            }
        });
        ui.url = "/intro";
    }

    detachedCallback() {
        ui.shortcutContext.remove("S");
        ui.shortcutContext.remove("E");
    }
};

/**
 * List page.
 *
 * .. attribute:: activity
 *
 *    List :ref:`Activity` stream.
 */
listling.ListPage = class extends micro.Page {
    static async make(url, id) {
        let page = document.createElement("listling-list-page");
        page.list = await ui.call("GET", `/api/lists/List:${id}`);
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
            owners: null,
            presentItems: null,
            trashedItems: null,
            trashedItemsCount: 0,
            locations: null,
            locationEnabled: false,
            valueFeature: false,
            editMode: true,
            trashExpanded: false,
            creatingItem: false,
            startCreateItem: this.startCreateItem.bind(this),
            settingsExpanded: false,
            share: listling.components.list.share,
            quickNavigate: micro.keyboard.quickNavigate,
            playlist: null,
            playlistPlaying: null,
            playlistPlayPause: null,
            playlistPlayNext: null,
            playlistPlayPrevious: null,

            toggleTrash: () => {
                this._data.trashExpanded = !this._data.trashExpanded;
            },
            stopCreateItem: () => {
                this._data.creatingItem = false;
            },
            toggleSettings: () => {
                this._data.settingsExpanded = !this._data.settingsExpanded;
            },

            startEdit: () => {
                this._data.editMode = true;
                this._form.elements.title.focus();
            },

            edit: async() => {
                try {
                    const list = await ui.call("POST", `/api/lists/${this._data.lst.id}`, {
                        title: this._form.elements.title.value,
                        description: this._form.elements.description.value,
                        value_unit: this._form.elements["value-unit"].value || null,
                        features:
                            Array.from(this._form.elements.features, e => e.checked && e.value)
                                .filter(feature => feature),
                        mode: this._form.elements.mode.valueAsObject,
                        item_template: this._form.elements["item-template"].value
                    });
                    this._data.editMode = false;
                    this._replayEvents();
                    this.activity.events.dispatchEvent({type: "editable-edit", object: list});
                } catch (e) {
                    ui.handleCallError(e);
                }
            },

            cancelEdit: () => {
                this._data.editMode = false;
                this._replayEvents();
            },

            subscribeUnsubscribe: async() => {
                const op = this._data.lst.activity.user_subscribed ? "unsubscribe" : "subscribe";
                if (op === "subscribe") {
                    const pushSubscription = await ui.service.pushManager.getSubscription();
                    if (!pushSubscription || !ui.device.push_subscription) {
                        const result = await ui.enableDeviceNotifications();
                        if (result === "error") {
                            return;
                        }
                    }
                }

                try {
                    this._data.lst.activity = await ui.call(
                        "PATCH", `/api/lists/${this._data.lst.id}/activity`, {op}
                    );
                    this.list = this._data.lst;
                } catch (e) {
                    ui.handleCallError(e);
                }
            },

            moveItemDrag: event => {
                // NOTE: This may be better done by micro.OL itself if some reset attribute is set
                this._itemsOL.insertBefore(event.detail.li, event.detail.from);
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

            onValueFeatureChange: event => {
                this._data.valueFeature = event.target.checked;
            },

            may: (ctx, op, mode) => {
                // eslint-disable-next-line no-underscore-dangle
                const permissions = listling.ListPage._PERMISSIONS[mode || "view"];
                return Boolean(
                    permissions.user.has(op) ||
                    this._data.lst && this._data.lst.owners.user_owner
                );
            }
        });
        Object.assign(this._data, {
            presentation: new listling.components.list.Presentation(this),
            presentationMode: false,
            presentationShortURL: null
        });
        micro.bind.bind(this.children, this._data);

        let updateClass = () => {
            this.classList.toggle("listling-list-has-trashed-items", this._data.trashedItemsCount);
            this.classList.toggle("listling-list-mode-view", !this._data.editMode);
            this.classList.toggle("listling-list-mode-edit", this._data.editMode);
            for (let feature of ["check", "assign", "vote", "value", "location", "play"]) {
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

        this.activity = null;
        this._items = null;
        this._eventBuffer = [];
        this._form = this.querySelector("form");
        this._itemsOL = this.querySelector(".listling-list-items");
    }

    attachedCallback() {
        super.attachedCallback();
        ui.shortcutContext.add("G", this._data.toggleTrash);
        ui.shortcutContext.add("C", this._data.toggleSettings);
        ui.addEventListener("list-items-move", this);

        this.ready.when((async() => {
            const setUpItems = async() => {
                const items = await ui.call("GET", `/api/lists/${this._data.lst.id}/items`);
                this._items = new micro.bind.Watchable(items);
            };
            try {
                await Promise.all([this._data.owners.fetch(), setUpItems()]);
            } catch (e) {
                ui.handleCallError(e);
                return;
            }

            this.activity =
                await micro.Activity.open(`/api/lists/${this._data.lst.id}/activity/stream`);
            this.activity.events.addEventListener("list-create-item", event => {
                if (!this._items.find(item => item.id === event.detail.event.detail.item.id)) {
                    this._items.push(event.detail.event.detail.item);
                }
            });
            const events = [
                "editable-edit", "trashable-trash", "trashable-restore", "item-check",
                "item-uncheck"
            ];
            for (let type of events) {
                this.activity.events.addEventListener(type, event => {
                    const object = event.detail.event.object;
                    let li;
                    let i;
                    switch (object.__type__) {
                    case "List":
                        if (this._data.editMode) {
                            // Buffer modifications until editing is done
                            this._bufferEvent(event);
                            break;
                        }
                        this.list = object;
                        break;
                    case "Item":
                        li = Array.from(this._itemsOL.children).find(
                            node => node.item.id === object.id
                        );
                        if (li && li.editMode) {
                            // Buffer modifications until editing is done
                            this._bufferEvent(event);
                            break;
                        }
                        i = this._items.findIndex(item => item.id === object.id);
                        this._items[i] = object;
                        this._data.trashedItemsCount = this._data.trashedItems.length;
                        break;
                    default:
                        // Unreachable
                        throw new Error();
                    }
                });
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

            if (["#presentation", "#presentation+play"].includes(location.hash)) {
                this._data.presentation.enter().catch(micro.util.catch);
            }
            if (["#play", "#presentation+play"].includes(location.hash)) {
                if (this._data.playlist) {
                    this._data.playlistPlayPause();
                }
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
        ui.shortcutContext.remove("G");
        ui.shortcutContext.remove("C");
        ui.removeEventListener("list-items-move", this);
        if (this.activity) {
            this.activity.close();
        }
        this._data.presentation.exit().catch(micro.util.catch);
        if (this._data.playlist) {
            this._data.playlist.dispose();
        }
    }

    get list() {
        return this._data.lst;
    }

    set list(value) {
        const playFeature = value.features.includes("play");
        if (this._data.playlist && !playFeature) {
            this._data.playlist.dispose();
            this._data.playlist = null;
        }

        this._data.lst = value;
        this._data.owners = new micro.Collection(`/api/lists/${this._data.lst.id}/owners`);
        this._data.locationEnabled =
            Boolean(ui.mapServiceKey) && this._data.lst.features.includes("location");
        this._data.valueFeature = value.features.includes("value");
        this._data.editMode = !this._data.lst;
        this.caption = this._data.lst.title;
        ui.url = listling.util.makeListURL(this._data.lst) + location.hash;

        if (!this._data.playlist && playFeature) {
            this._data.playlist = new listling.components.list.Playlist(this);
        }
    }

    /**
     * Start to create an :ref:`Item` via editor.
     *
     * *title*, *text*, *resource*, *value* and *location* correspond to the arguments of
     * :meth:`ItemElement.startEdit`. *text* defaults to :attr:`list` *item_template*.
     */
    startCreateItem({title = null, text, resource = null, value = null, location = null} = {}) {
        if (text === undefined) {
            text = this._data.lst.item_template;
        }
        this._data.creatingItem = true;
        const elem = this.querySelector(".listling-list-create-item [is=listling-item]");
        elem.startEdit({title, text, resource, value, location});
        elem.scrollIntoView(false);
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
        try {
            await ui.call("POST", `/api/lists/${this._data.lst.id}/items/move`, {
                item_id: item.id,
                to_id: to && to.id
            });
        } catch (e) {
            ui.handleCallError(e);
        }
    }

    _bufferEvent(event) {
        this._eventBuffer.push(event);
    }

    _replayEvents() {
        const events = this._eventBuffer;
        this._eventBuffer = [];
        for (let event of events) {
            this.activity.events.dispatchEvent(event);
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
            resourceElem: null,
            assignees: null,
            assigneesCount: 0,
            votes: null,
            votesComplete: false,
            votesMeta: null,
            expanded: false,
            editMode: false,
            startEdit: this.startEdit.bind(this),
            isCheckDisabled:
                (ctx, trashed, mode) => trashed || !this._data.may(ctx, "item-modify", mode),
            makeItemURL: listling.util.makeItemURL,
            playable: null,
            playablePlaying: null,
            playablePlayPause: null,

            edit: async() => {
                const input = this.querySelector("micro-content-input");
                const {text, resource} = input.valueAsObject;
                let value = this._form.elements.value.valueAsNumber;
                if (isNaN(value)) {
                    value = null;
                }
                const url = this._data.item
                    ? `/api/lists/${this._data.lst.id}/items/${this._data.item.id}`
                    : `/api/lists/${this._data.lst.id}/items`;

                let item;
                try {
                    item = await ui.call("POST", url, {
                        text,
                        resource: resource && resource.url,
                        title: this._form.elements.title.value,
                        value,
                        location: this._form.elements.location.wrapper.valueAsObject
                    });
                } catch (e) {
                    if (
                        e instanceof micro.APIError && [
                            "CommunicationError", "NoResourceError", "ForbiddenResourceError",
                            "BrokenResourceError"
                        ].includes(e.error.__type__)
                    ) {
                        // Delete the resource if it is no longer retrievable
                        input.valueAsObject = {text, resource: null};
                    } else {
                        ui.handleCallError(e);
                    }
                    return;
                }

                if (this._data.item) {
                    this._data.editMode = false;
                    // eslint-disable-next-line no-underscore-dangle
                    ui.page._replayEvents();
                    this._activity.events.dispatchEvent({type: "editable-edit", object: item});
                } else {
                    // Reset form
                    this._data.item = null;
                    this._activity.events.dispatchEvent(
                        {type: "list-create-item", object: this._data.lst, detail: {item}}
                    );
                }
                if (this.onedit) {
                    this.onedit(new CustomEvent("edit"));
                }
            },

            cancelEdit: () => {
                if (this._data.item) {
                    this._data.editMode = false;
                    // eslint-disable-next-line no-underscore-dangle
                    ui.page._replayEvents();
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
                    this._activity.events.dispatchEvent({type: "trashable-trash", object: item});
                } catch (e) {
                    ui.handleCallError(e);
                }
            },

            restore: async() => {
                try {
                    const item = await ui.call(
                        "POST", `/api/lists/${ui.page.list.id}/items/${this._data.item.id}/restore`
                    );
                    this._activity.events.dispatchEvent({type: "trashable-restore", object: item});
                } catch (e) {
                    ui.handleCallError(e);
                }
            },

            checkUncheck: async() => {
                const op = this._data.item.checked ? "uncheck" : "check";
                try {
                    const item = await ui.call(
                        "POST", `/api/lists/${this._data.lst.id}/items/${this._data.item.id}/${op}`
                    );
                    this._activity.events.dispatchEvent({type: `item-${op}`, object: item});
                } catch (e) {
                    ui.handleCallError(e);
                }
            },

            assign: () => {
                const dialog = document.createElement("listling-assign-dialog");
                dialog.itemElement = this;
                ui.notify(dialog);
            },

            voteUnvote: async() => {
                try {
                    if (this._data.votesMeta.user_voted) {
                        const item = Object.assign(
                            {}, this._data.item,
                            {votes: {count: this._data.votesMeta.count - 1, user_voted: false}}
                        );
                        await ui.call("DELETE", `${this._data.votes.url}/user`);
                        this._activity.events.dispatchEvent(
                            {type: "item-votes-unvote", object: item}
                        );
                    } else {
                        const item = Object.assign(
                            {}, this._data.item,
                            {votes: {count: this._data.votesMeta.count + 1, user_voted: true}}
                        );
                        await ui.call("POST", this._data.votes.url);
                        this._activity.events.dispatchEvent(
                            {type: "item-votes-vote", object: item}
                        );
                    }
                } catch (e) {
                    ui.handleCallError(e);
                }
            },

            onVotesActivate: () => {
                if (this._data.votes.count === null) {
                    this.querySelector(".listling-item-more-votes").trigger();
                }
            },

            onURLInput: event => {
                const input = this.querySelector("micro-content-input");
                if (!input.valueAsObject.resource) {
                    input.attach(event.detail.url).catch(micro.util.catch);
                }
            },

            hasContent: (ctx, item, lst, assigneesCount) =>
                item && lst && (
                    item.text || item.resource ||
                    lst.features.includes("value") && item.value !== null ||
                    lst.features.includes("location") && item.location ||
                    lst.features.includes("assign") && assigneesCount > 0
                ),

            may: (ctx, op, mode) => {
                // eslint-disable-next-line no-underscore-dangle
                const permissions = listling.ListPage._PERMISSIONS[mode || "view"];
                return Boolean(
                    permissions.user.has(op) ||
                    this._data.lst && this._data.lst.owners.user_owner
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

        this._activity = null;
        this._form = this.querySelector("form");

        // Expand / collapse item
        this.addEventListener("click", event => {
            if (
                !this._data.expanded &&
                !micro.keyboard.findAncestor(event.target, elem => elem.tabIndex !== -1, this)
            ) {
                this._data.expanded = true;
            }
        });
        this.addEventListener("keydown", event => {
            if (event.target === this && event.key === "Enter") {
                this.click();
            }
        });
        this.addEventListener("focusout", event => {
            if (this._data.expanded && !this.contains(event.relatedTarget)) {
                this._data.expanded = false;
            }
        });
    }

    attachedCallback() {
        (async () => {
            await ui.page.ready;
            this._activity = ui.page.activity;
        })().catch(micro.util.catch);

        if (!this._data.item) {
            return;
        }
        this._activity = ui.page.activity;

        this._data.assignees = new micro.bind.Watchable(this._data.item.assignees.items);
        this._data.assigneesCount = this._data.assignees.length;

        this._onAssign = event => {
            if (
                event.detail.event.object.id === this._data.item.id &&
                !this._data.assignees.find(
                    assignee => assignee.id === event.detail.event.detail.assignee.id
                )
            ) {
                this._data.assignees.unshift(event.detail.event.detail.assignee);
                this._data.assigneesCount = this._data.assignees.length;
            }
        };
        this._activity.events.addEventListener("item-assignees-assign", this._onAssign);
        this._onUnassign = event => {
            if (event.detail.event.object.id === this._data.item.id) {
                const i = this._data.assignees.findIndex(
                    assignee => assignee.id === event.detail.event.detail.assignee.id
                );
                if (i !== -1) {
                    this._data.assignees.splice(i, 1);
                    this._data.assigneesCount = this._data.assignees.length;
                }
            }
        };
        this._activity.events.addEventListener("item-assignees-unassign", this._onUnassign);

        this._data.votes = new micro.Collection(
            `/api/lists/${this._data.lst.id}/items/${this._data.item.id}/votes`
        );
        this._data.votes.events.addEventListener("fetch", () => {
            this._data.votesComplete = this._data.votes.complete;
        });
        this._data.votesComplete = false;
        this._data.votesMeta = this._data.item.votes;

        this._onVote = event => {
            if (event.detail.event.object.id === this._data.item.id) {
                this._data.votesMeta = event.detail.event.object.votes;
                if (!this._data.votes.items.find(vote => vote.id === event.detail.event.user.id)) {
                    this._data.votes.items.unshift(event.detail.event.user);
                }
            }
        };
        this._activity.events.addEventListener("item-votes-vote", this._onVote);

        this._onUnvote = event => {
            if (event.detail.event.object.id === this._data.item.id) {
                this._data.votesMeta = event.detail.event.object.votes;
                const i = this._data.votes.items.findIndex(
                    vote => vote.id === event.detail.event.user.id
                );
                if (i !== -1) {
                    this._data.votes.items.splice(i, 1);
                }
            }
        };
        this._activity.events.addEventListener("item-votes-unvote", this._onUnvote);
    }

    detachedCallback() {
        if (!this._data.item) {
            return;
        }
        this._activity.events.removeEventListener("item-assignees-assign", this._onAssign);
        this._activity.events.removeEventListener("item-assignees-unassign", this._onUnassign);
        this._activity.events.removeEventListener("item-votes-vote", this._onVote);
        this._activity.events.removeEventListener("item-votes-unvote", this._onUnvote);
        if (this._data.playable) {
            this._data.playable.dispose();
        }
    }

    get item() {
        return this._data.item;
    }

    set item(value) {
        this._data.item = value;
        this._data.resourceElem =
            micro.bind.transforms.renderResource(null, value && value.resource) || null;
        this.id = this._data.item ? `items-${this._data.item.id.split(":")[1]}` : "";
        if (this._data.playable) {
            this._data.playable.resourceElement = this._data.resourceElem;
        }
    }

    get list() {
        return this._data.lst;
    }

    set list(value) {
        const playFeature = value && value.features.includes("play");
        if (this._data.playable && !playFeature) {
            this._data.playable.dispose();
            this._data.playable = null;
        }

        this._data.lst = value;

        if (!this._data.playable && playFeature) {
            this._data.playable = new listling.components.list.Playable(this);
            this._data.playable.resourceElement = this._data.resourceElem;
        }
    }

    /** Item assignees. */
    get assignees() {
        return this._data.assignees;
    }

    /** Indicates if the element is in edit mode. */
    get editMode() {
        return this._data.editMode;
    }

    /** :class:`listling.components.list.Playable` extension. */
    get playable() {
        return this._data.playable;
    }

    /**
     * Start to edit :attr:`item` via edit mode.
     *
     * The form is populated with *title*, *text*, *resource*, *value* and *location*. *resource*
     * may also be a URL or :class:`File` to attach. They default to the corresponding :attr:`item`
     * attributes or ``null``.
     */
    startEdit({title, text, resource, value, location} = {}) {
        if (title === undefined) {
            title = this._data.item && this._data.item.title;
        }
        if (text === undefined) {
            text = this._data.item && this._data.item.text;
        }
        if (resource === undefined) {
            resource = this._data.item && this._data.item.resource;
        }
        if (value === undefined) {
            value = this._data.item && this._data.item.value;
        }
        if (location === undefined) {
            location = this._data.item && this._data.item.location;
        }

        // Populate the form directly without data binding because attach() is used
        this._data.editMode = true;
        this._form.elements.title.value = title || "";
        // Work around Safari not accepting NaN for valueAsNumber
        this._form.elements.value.value = value === null ? "" : value.toString();
        this.querySelector("micro-location-input").valueAsObject = location;
        const contentInput = this.querySelector("micro-content-input");
        if (typeof resource === "string" || resource instanceof File) {
            contentInput.valueAsObject = {text, resource: null};
            contentInput.attach(resource).catch(micro.util.catch);
        } else {
            contentInput.valueAsObject = {text, resource};
        }
        this._form.elements.title.focus();
    }
};

/** Test if *a* and *b* are (strictly) unequal. */
micro.bind.transforms.neq = function(ctx, a, b) {
    return a !== b;
};

document.registerElement("listling-ui", {prototype: listling.UI.prototype, extends: "body"});
document.registerElement("listling-intro-page", listling.IntroPage);
document.registerElement("listling-list-page", listling.ListPage);
document.registerElement("listling-item",
                         {prototype: listling.ItemElement.prototype, extends: "li"});
