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
/* eslint-disable prefer-arrow-callback */

"use strict";

self.expect = self.expect || chai.expect;

describe("URLDetection", function() {
    let input;
    let calls;

    beforeEach(function() {
        const main = document.querySelector("main");
        main.innerHTML = '<input value="See https://example.org/." />';
        input = main.firstElementChild;
        // eslint-disable-next-line no-new
        new micro.components.contentinput.URLDetection(input);
        calls = [];
        input.addEventListener("urlinput", event => calls.push(event.detail.url));
        input.focus();
    });

    describe("on input", function() {
        it("should detect URL", function() {
            input.value = "See https://example.org/ or https://example.com/.";
            input.dispatchEvent(new Event("input"));
            expect(calls).to.deep.equal(["https://example.com/"]);
        });

        it("should not detect selected URL", function() {
            input.value = "See https://example.org/ or https://example.com/";
            input.dispatchEvent(new Event("input"));
            expect(calls).to.deep.equal([]);
        });

        it("should detect deselected URL", function() {
            input.value = "See https://example.org/ or https://example.com/";
            input.dispatchEvent(new Event("input"));
            input.value = "See https://example.org/ or https://example.com/.";
            input.dispatchEvent(new Event("input"));
            expect(calls).to.deep.equal(["https://example.com/"]);
        });
    });
});
