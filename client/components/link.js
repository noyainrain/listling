/*
 * micro
 * Copyright (C) 2020 micro contributors
 *
 * This program is free software: you can redistribute it and/or modify it under the terms of the
 * GNU Lesser General Public License as published by the Free Software Foundation, either version 3
 * of the License, or (at your option) any later version.
 *
 * This program is distributed in the hope that it will be useful, but WITHOUT ANY WARRANTY; without
 * even the implied warranty of MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the GNU
 * Lesser General Public License for more details.
 *
 * You should have received a copy of the GNU Lesser General Public License along with this program.
 * If not, see <http://www.gnu.org/licenses/>.
 */

/** Link with preview. */

"use strict";

self.micro = self.micro || {};
micro.components = micro.components || {};

/**
 * Link including a preview of the target web resource.
 *
 * .. attribute:: resource
 *
 *    Target :ref:`Resource` description.
 *
 * .. describe:: --micro-link-max-height
 *
 *    Maximum height of the preview image. Defaults to ``none``.
 */
micro.components.LinkElement = class extends HTMLElement {
    createdCallback() {
        this.appendChild(
            document.importNode(document.querySelector("#micro-link-template").content, true)
        );
        this._data = new micro.bind.Watchable({resource: null, host: null});
        micro.bind.bind(this.children, this._data);
    }

    get resource() {
        return this._data.resource;
    }

    set resource(value) {
        this._data.resource = value;
        this._data.host = new URL(value.url).host;
    }
};
document.registerElement("micro-link", micro.components.LinkElement);
