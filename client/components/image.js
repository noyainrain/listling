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

/** Extended image element. */

"use strict";

self.micro = self.micro || {};
micro.components = micro.components || {};

/**
 * Extended image element.
 *
 * .. attribute:: image
 *
 *    :ref:`Image` to display.
 *
 * .. describe:: --micro-image-max-height
 *
 *    Maximum height of the element. Defaults to ``none``.
 */
micro.components.ImageElement = class extends HTMLElement {
    createdCallback() {
        this.appendChild(
            document.importNode(document.querySelector("#micro-image-template").content, true)
        );
        this._data = new micro.bind.Watchable({image: null});
        micro.bind.bind(this.children, this._data);
        this.tabIndex = 0;
        // eslint-disable-next-line no-new
        new micro.keyboard.ShortcutContext(this);
    }

    get image() {
        return this._data.image;
    }

    set image(value) {
        this._data.image = value;
    }
};
document.registerElement("micro-image", micro.components.ImageElement);
