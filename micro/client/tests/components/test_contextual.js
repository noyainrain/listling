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

/* eslint-env mocha */
/* global chai, expect */
/* eslint-disable no-unused-expressions, prefer-arrow-callback */

"use strict";

self.expect = self.expect || chai.expect;

describe("ContextualElement", function() {
    let elem;
    let wrapper;
    let calls;

    beforeEach(async function() {
        const main = document.querySelector("main");
        main.innerHTML = `
            <div>
                <p></p>
                <micro-contextual><a href="#"></a></micro-contextual>
            </div>
        `;
        // Custom elements are upgraded in the next iteration
        await new Promise(resolve => setTimeout(resolve, 0));
        elem = main.querySelector("micro-contextual");
        wrapper = main.querySelector("div");
        calls = [];
        elem.addEventListener("activate", () => calls.push("activate"));
        elem.addEventListener("deactivate", () => calls.push("deactivate"));
    });

    describe("on hover", function() {
        it("should activate", function() {
            wrapper.dispatchEvent(new MouseEvent("mouseenter"));
            expect(elem.active).to.be.true;
            expect(elem.classList.contains("micro-contextual-active")).to.be.true;
            expect(calls).to.deep.equal(["activate"]);
        });
    });

    describe("on hover off", function() {
        it("should deactivate", function() {
            wrapper.dispatchEvent(new MouseEvent("mouseenter"));
            wrapper.dispatchEvent(new MouseEvent("mouseleave"));
            expect(elem.active).to.be.false;
            expect(elem.classList.contains("micro-contextual-active")).to.be.false;
            expect(calls).to.deep.equal(["activate", "deactivate"]);
        });
    });

    describe("on a click", function() {
        it("should deactivate", function() {
            wrapper.dispatchEvent(new MouseEvent("mouseenter"));
            elem.querySelector("a").click();
            expect(elem.active).to.be.false;
        });
    });
});
