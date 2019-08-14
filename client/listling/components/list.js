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
