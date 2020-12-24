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

/* eslint-env serviceworker */

/** Service worker. */

"use strict";

// Chrome does not yet update the service worker if imports change (see
// https://bugs.chromium.org/p/chromium/issues/detail?id=648295)
// {{ version }}
importScripts(
    "/static/node_modules/@noyainrain/micro/util.js",
    "/static/node_modules/@noyainrain/micro/service.js", "/static/listling/util.js", "/manifest.js"
);

self.listling = self.listling || {};
listling.service = {};

/**
 * Open Listling service worker.
 */
listling.service.Service = class extends micro.service.Service {
    constructor() {
        addEventListener("fetch", event => {
            const url = new URL(event.request.url);
            if (url.origin === location.origin && url.pathname.match(/^\/s(\/.*)?$/u)) {
                event.respondWith(fetch(event.request));
            }
        });

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
            "object-owners-grant"(event) {
                return {
                    title: event.object.title,
                    body: `${micro.util.truncate(event.user.name)} granted ownership to ${micro.util.truncate(event.owner.name)}`,
                    url: listling.util.makeListURL(event.object)
                };
            },
            "object-owners-revoke"(event) {
                return {
                    title: event.object.title,
                    body: event.user.id === event.owner.id
                        ? `${micro.util.truncate(event.user.name)} revoked their ownership`
                        : `${micro.util.truncate(event.user.name)} revoked ownership from ${micro.util.truncate(event.owner.name)}`,
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
            "item-uncheck": event => renderItemNotification(event, '{user} unchecked "{item}"'),
            "item-assignees-assign"(event) {
                const body = event.user.id === event.detail.assignee.id
                    ? '{user} assigned themself to "{item}"'
                    : `{user} assigned ${micro.util.truncate(event.detail.assignee.name)} to "{item}"`;
                return renderItemNotification(event, body);
            },
            "item-assignees-unassign"(event) {
                const body = event.user.id === event.detail.assignee.id
                    ? '{user} unassigned themself from "{item}"'
                    : `{user} unassigned ${micro.util.truncate(event.detail.assignee.name)} from "{item}"`;
                return renderItemNotification(event, body);
            },
            "item-votes-vote": event => renderItemNotification(event, '{user} voted for "{item}"'),
            "item-votes-unvote": event => renderItemNotification(event, '{user} unvoted "{item}"')
        });
    }
};

self.service = new listling.service.Service();
