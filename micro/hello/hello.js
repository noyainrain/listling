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

/**
 * Hello UI.
 */

"use strict";

window.hello = {};

/**
 * Hello UI.
 */
hello.UI = class extends micro.UI {
    init() {
        function makeAboutPage() {
            return document.importNode(ui.querySelector(".hello-about-page-template").content, true)
                .querySelector("micro-about-page");
        }

        this.pages = this.pages.concat([
            {url: "^/$", page: "hello-start-page"},
            {url: "^/about$", page: makeAboutPage}
        ]);
    }
};

/**
 * Start page.
 */
hello.StartPage = class extends micro.Page {
    createdCallback() {
        super.createdCallback();
        this._activity = null;

        this.appendChild(
            document.importNode(ui.querySelector(".hello-start-page-template").content, true));
        this._data = new micro.bind.Watchable({
            settings: ui.settings,
            greetings: new micro.Collection("/api/greetings"),

            createGreeting: async() => {
                const input = this.querySelector("micro-content-input");
                try {
                    const {text, resource} = input.valueAsObject;
                    await ui.onboard();
                    const greeting = await ui.call(
                        "POST", "/api/greetings", {text, resource: resource && resource.url}
                    );
                    input.valueAsObject = {text: null, resource: null};
                    this._activity.events.dispatchEvent(
                        {type: "greetings-create", object: null, detail: {greeting}}
                    );
                } catch (e) {
                    if (
                        e instanceof micro.APIError &&
                        [
                            "CommunicationError", "NoResourceError", "ForbiddenResourceError",
                            "BrokenResourceError"
                        ].includes(e.error.__type__)
                    ) {
                        // Delete the resource if it is no longer retrievable
                        input.valueAsObject = {text: input.valueAsObject.text, resource: null};
                    } else {
                        ui.handleCallError(e);
                    }
                }
            },

            makeGreetingHash(ctx, greeting) {
                return `greetings-${greeting.id.split(":")[1]}`;
            }
        });
        micro.bind.bind(this.children, this._data);
    }

    attachedCallback() {
        super.attachedCallback();
        this.ready.when((async() => {
            try {
                await this._data.greetings.fetch();
                this._activity = await micro.Activity.open("/api/activity/stream");
                this._activity.events.addEventListener("greetings-create", event => {
                    if (
                        !this._data.greetings.items.find(
                            greeting => greeting.id === event.detail.event.detail.greeting.id
                        )
                    ) {
                        this._data.greetings.items.unshift(event.detail.event.detail.greeting);
                    }
                });
            } catch (e) {
                ui.handleCallError(e);
            }
        })().catch(micro.util.catch));
    }

    detachedCallback() {
        if (this._activity) {
            this._activity.close();
        }
    }
};

document.registerElement("hello-ui", {prototype: hello.UI.prototype, extends: "body"});
document.registerElement("hello-start-page", hello.StartPage);
