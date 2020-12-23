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

window.expect = window.expect || chai.expect;

describe("dispatchEvent()", function() {
    it("should dispatch event", function() {
        let calls = [];
        let span = document.createElement("span");
        span.addEventListener("poke", event => calls.push(["listener", event.type]));
        span.onpoke = event => calls.push(["on", event.type]);
        micro.util.dispatchEvent(span, new CustomEvent("poke"));
        expect(calls).to.deep.equal([["listener", "poke"], ["on", "poke"]]);
    });
});

describe("makeOnEvent()", function() {
    describe("on event", function() {
        it("should call handler", function() {
            let calls = [];
            let elem = document.createElement("span");
            Object.defineProperty(elem, "onmeow", micro.util.makeOnEvent("meow"));
            elem.onmeow = () => calls.push("onmeow");
            elem.dispatchEvent(new CustomEvent("meow"));
            expect(calls).to.deep.equal(["onmeow"]);
        });
    });
});

describe("parseCoords()", function() {
    it("should parse", function() {
        const coords = micro.util.parseCoords("52°6′3.6″N 13°12′7.2″W");
        expect(coords).to.deep.equal([52.101, -13.202]);
    });

    it("should parse decimal str", function() {
        const coords = micro.util.parseCoords("-52.101 13.202");
        expect(coords).to.deep.equal([-52.101, 13.202]);
    });

    it("should parse approximate str", function() {
        const coords = micro.util.parseCoords(" 52.9 30x -13 S");
        expect(coords).to.deep.equal([53.4, 13]);
    });

    it("should fail for bad str format", function() {
        expect(() => micro.util.parseCoords("42")).to.throw(SyntaxError);
    });

    it("should fail for out of range str coordinates", function() {
        expect(() => micro.util.parseCoords("92 -182")).to.throw(RangeError);
    });
});
