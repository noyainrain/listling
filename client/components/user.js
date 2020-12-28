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

/** Page to edit the user. */

"use strict";

micro.components = micro.components || {};
micro.components.user = {};

/** Page to edit the user. */
micro.components.user.EditUserPage = class extends micro.Page {
    static async make(url, id) {
        id = id || ui.user.id;
        const user = await ui.call("GET", `/api/users/${id}`);
        if (user.id !== ui.user.id) {
            return document.createElement("micro-forbidden-page");
        }
        const page = document.createElement("micro-edit-user-page");
        page.user = user;
        return page;
    }

    createdCallback() {
        super.createdCallback();
        this.caption = "Edit user settings";

        this.appendChild(
            document.importNode(
                document.querySelector("#micro-edit-user-page-template").content, true
            )
        );
        this._form = this.querySelector("form");

        this._data = new micro.bind.Watchable({
            user: null,

            edit: async() => {
                await micro.editUser({name: this._form.elements.name.value});
            },

            setEmail: () => {
                ui.dialog = document.createElement("micro-set-email-dialog");
                (async () => {
                    const user = await ui.dialog.result;
                    if (user) {
                        this._data.user = user;
                    }
                })().catch(micro.util.catch);
            }
        });
        micro.bind.bind(this.children, this._data);
    }

    attachedCallback() {
        super.attachedCallback();
        this._form.elements.name.value = this._data.user.name;
        this._form.elements.name.focus();
    }

    /** :ref:`User` to edit. */
    get user() {
        return this._data.user;
    }

    set user(value) {
        this._data.user = value;
    }
};
document.registerElement("micro-edit-user-page", micro.components.user.EditUserPage);

micro.components.user.AuthRequestDialog = class extends micro.core.Dialog {
    createdCallback() {
        super.createdCallback();
        this._authRequest = null;

        const titleContent = this.querySelector("[slot=title]");
        const requestContent = this.querySelector("[slot=request]");
        const preContent = this.querySelector("[slot=pre]");
        this.appendChild(
            document.importNode(
                document.querySelector("#micro-auth-request-dialog-template").content, true
            )
        );

        this._data = new micro.bind.Watchable({
            titleContent,
            requestContent,
            preContent,
            step: "request",

            request: async () => {
                try {
                    this._authRequest = await this.request(
                        this.querySelector("[name=email]").value);
                    this._data.step = "verify";
                    this.querySelector("[name=code]").focus();
                } catch (e) {
                    ui.handleCallError(e);
                    this.result.when(null);
                }
            },

            verify: async () => {
                try {
                    const result = await this.verify(
                        this._authRequest, this.querySelector("[name=code]").value.toUpperCase()
                    );
                    this.result.when(result);
                } catch (e) {
                    if (typeof e === "string") {
                        ui.notify(e);
                    } else if (e instanceof micro.APIError && e.error.__type__ === "ValueError") {
                        if (e.error.message.includes("code")) {
                            ui.notify("The verification code is incorrect. Please try again.");
                        } else if (e.error.message.includes("auth_request")) {
                            ui.notify("The verification code is expired. Please try again.");
                        } else {
                            throw e;
                        }
                    } else {
                        ui.handleCallError(e);
                    }
                    this.result.when(null);
                }
            },

            close: () => this.result.when(null)
        });
        micro.bind.bind(this.children, this._data);
    }

    attachedCallback() {
        this.querySelector("[name=email]").focus();
    }

    // eslint-disable-next-line no-unused-vars -- part of API
    request(email) {}

    // eslint-disable-next-line no-unused-vars -- part of API
    verify(authRequest) {}
};

/** Dialog to set the user's *email* address. */
micro.components.user.SetEmailDialog = class extends micro.components.user.AuthRequestDialog {
    createdCallback() {
        this.appendChild(
            document.importNode(
                document.querySelector("#micro-set-email-dialog-template").content, true
            )
        );
        super.createdCallback();
    }

    request(email) {
        return ui.call("POST", `/api/users/${ui.user.id}/set-email`, {email});
    }

    async verify(authRequest, code) {
        try {
            const user = await ui.call(
                "POST", `/api/users/${ui.user.id}/finish-set-email`,
                {auth_request_id: authRequest.id, auth: code}
            );
            ui.dispatchEvent(new CustomEvent("user-edit", {detail: {user}}));
            return user;
        } catch (e) {
            if (
                e instanceof micro.APIError && e.error.__type__ === "ValueError" &&
                e.error.message.includes("email")
            ) {
                // eslint-disable-next-line no-throw-literal -- internal shortcut
                throw "The given email address is already in use by another user.";
            }
            throw e;
        }
    }
};
document.registerElement("micro-set-email-dialog", micro.components.user.SetEmailDialog);
