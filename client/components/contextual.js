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

/** Contextual content. */

"use strict";

self.micro = self.micro || {};
micro.components = micro.components || {};
micro.components.contextual = {};

/**
 * Contextual content, i.e. additional information for an element.
 *
 * It is collapsed by default and expanded with user focus (or hover).
 *
 * Contextual content and context element are coupled by a common wrapper, e.g.::
 *
 *    <div>
 *        <p tabindex="0">Cat</p>
 *        <micro-contextual>Small carnivorous mammal</micro-contextual>
 *    </div>
 *
 * The element is automatically deactivated on interaction with children marked with
 * ``.micro-contextual-deactivate`` and also any ``a`` child.
 *
 * .. attribute:: active
 *
 *    Indicates if the element is active, i.e. presented to the user.
 *
 * .. attribute:: onactivate
 *
 *    Event handler for ``activate``, dispatched when the element is activated.
 *
 * .. attribute:: ondeactivate
 *
 *    Event handler for ``deactivate``, dispatched when the element is deactivated.
 *
 * .. describe:: .micro-contextual-active
 *
 *    Indicates that the element is :attr:`active`.
 *
 * .. describe:: .micro-contextual-deactivate
 *
 *    Indicates that the element is deactivated on interaction with the child.
 */
micro.components.contextual.ContextualElement = class extends HTMLElement {
    createdCallback() {
        this.active = false;
        this._wrapper = null;
        this._hovered = false;
        this._focused = false;
        Object.defineProperty(this, "onactivate", micro.util.makeOnEvent("activate"));
        Object.defineProperty(this, "ondeactivate", micro.util.makeOnEvent("deactivate"));

        this.addEventListener("click", event => {
            const elem = event.composedPath().slice(0, -2).find(
                e => e.classList.contains("micro-contextual-deactivate") || e.tagName === "A"
            );
            if (elem) {
                if (this._focused) {
                    document.activeElement.blur();
                }
                if (this._hovered) {
                    // As soon as the element is deactivated, the pointer will not hover over it
                    // anymore
                    this._hovered = false;
                    this._update();
                }
            }
        });
    }

    attachedCallback() {
        this._wrapper = this.parentElement;
        this._wrapper.classList.add("micro-contextual-wrapper");
        this._onMouseEnter = () => {
            this._hovered = true;
            this._update();
        };
        this._onMouseLeave = () => {
            this._hovered = false;
            this._update();
        };
        this._onFocusIn = () => {
            this._focused = true;
            this._update();
        };
        this._onFocusOut = () => {
            this._focused = false;
            this._update();
        };
        this._wrapper.addEventListener("mouseenter", this._onMouseEnter);
        this._wrapper.addEventListener("mouseleave", this._onMouseLeave);
        this._wrapper.addEventListener("focusin", this._onFocusIn);
        this._wrapper.addEventListener("focusout", this._onFocusOut);
    }

    detachedCallback() {
        this._wrapper.classList.remove("micro-contextual-wrapper");
        this._wrapper.removeEventListener("mouseenter", this._onMouseEnter);
        this._wrapper.removeEventListener("mouseleave", this._onMouseLeave);
        this._wrapper.removeEventListener("focusin", this._onFocusIn);
        this._wrapper.removeEventListener("focusout", this._onFocusOut);
    }

    _update() {
        const lastActive = this.active;
        this.active = this._hovered || this._focused;
        this.classList.toggle("micro-contextual-active", this.active);
        if (this.active !== lastActive) {
            this.dispatchEvent(new CustomEvent(this.active ? "activate" : "deactivate"));
        }
    }
};
document.registerElement("micro-contextual", micro.components.contextual.ContextualElement);
