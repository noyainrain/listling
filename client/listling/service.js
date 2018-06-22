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

/* eslint-env serviceworker */

/** Service worker. */

"use strict";

// Chrome does not yet update the service worker if imports change (see
// https://bugs.chromium.org/p/chromium/issues/detail?id=648295)
// micro 0.16.0
importScripts("/static/node_modules/@noyainrain/micro/util.js",
              "/static/node_modules/@noyainrain/micro/service.js", "/static/listling/util.js");

self.listling = self.listling || {};
listling.service = {};

/**
 * Open Listling service worker.
 */
listling.service.Service = class extends micro.service.Service {
    constructor() {
        super();

        async function renderItemNotification(event, body) {
            let list = await micro.call("GET", `/api/lists/${event.object.list_id}`);
            return {
                title: list.title,
                body: micro.util.format(
                    body, {user: micro.util.truncate(event.user.name), item: event.object.title}),
                url: listling.util.makeListURL(list)
            };
        }

        this.setNotificationRenderers({
            "editable-edit+List"(event) {
                return {
                    title: event.object.title,
                    body: `${micro.util.truncate(event.user.name)} edited the list`,
                    url: listling.util.makeListURL(event.object)
                };
            },
            "list-create-item"(event) {
                return {
                    title: event.object.title,
                    body: `${micro.util.truncate(event.user.name)} added "${event.detail.item.title}"`,
                    url: listling.util.makeListURL(event.object)
                };
            },
            "editable-edit+Item": event => renderItemNotification(event, '{user} edited "{item}"'),
            "trashable-trash+Item":
                event => renderItemNotification(event, '{user} trashed "{item}"'),
            "trashable-restore+Item":
                event => renderItemNotification(event, '{user} restored "{item}"'),
            "item-check": event => renderItemNotification(event, '{user} checked "{item}"'),
            "item-uncheck": event => renderItemNotification(event, '{user} unchecked "{item}"')
        });
    }
};

self.service = new listling.service.Service();
