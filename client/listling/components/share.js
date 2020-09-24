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

/** Share page. */

"use strict";

self.listling = self.listling || {};
self.listling.components = self.listling.components || {};
self.listling.components.share = {};

/** Share page. */
listling.components.share.SharePage = class extends micro.Page {
    createdCallback() {
        super.createdCallback();
        this.caption = "Share to list";
        this._share = {
            title: null,
            text: null,
            url: null,
            files: []
        };

        this.appendChild(
            document.importNode(
                document.querySelector("#listling-share-page-template").content, true
            )
        );
        this._data = new micro.bind.Watchable({
            lists: new micro.Collection(`/api/users/${ui.user.id}/lists`),
            listsComplete: false,

            onClick: async list => {
                const match =
                    this._share.title && this._share.title.match(micro.core.URL_PATTERN) ||
                    this._share.text && this._share.text.match(micro.core.URL_PATTERN);
                const url = match ? match[2] : null;
                await ui.navigate(listling.util.makeListURL(list));
                ui.page.startCreateItem({
                    title: this._share.title,
                    text: this._share.text,
                    resource: this._share.files[0] || this._share.url || url
                });
            },

            onKeyDown: event => {
                if (event.key === "Enter") {
                    event.target.click();
                }
            }
        });
        micro.bind.bind(this.children, this._data);

        this._data.lists.events.addEventListener("fetch", () => {
            this._data.listsComplete = this._data.lists.complete;
        });
    }

    attachedCallback() {
        super.attachedCallback();
        this._onMessage = event => {
            if (event.data.type === "share") {
                this._share = event.data.data;
            }
        };
        navigator.serviceWorker.addEventListener("message", this._onMessage);
        this.querySelector(".link").click();
    }

    detachedCallback() {
        navigator.serviceWorker.removeEventListener("message", this._onMessage);
    }
};
document.registerElement("listling-share-page", listling.components.share.SharePage);
