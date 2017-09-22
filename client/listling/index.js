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
        function makeStartPage() {
            let page = document
                .importNode(ui.querySelector(".listling-start-page-template").content, true)
                .querySelector("div");
            page.querySelector(".micro-logo span").textContent = ui.settings.title;
            page.querySelector(".micro-logo img").src = ui.settings.icon || "";
            return page;
        }

        function makeAboutPage() {
            return document
                .importNode(ui.querySelector(".listling-about-page-template").content, true)
                .querySelector("micro-about-page");
        }

        this.pages = this.pages.concat([
            {url: "^/$", page: makeStartPage},
            {url: "^/about$", page: makeAboutPage}
        ]);
    }
};

document.registerElement("listling-ui", {prototype: listling.UI.prototype, extends: "body"});
