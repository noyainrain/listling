/*
 * bind.js
 * Released into the public domain
 * https://github.com/noyainrain/micro/blob/master/client/bind.js
 */

/* eslint-env mocha */
/* global chai, expect */
/* eslint-disable no-unused-expressions, prefer-arrow-callback */

"use strict";

window.expect = window.expect || chai.expect;

describe("Watchable", function() {
    describe("on set", function() {
        it("should notify watchers", function() {
            let object = new micro.bind.Watchable();
            let calls = [];
            object.watch("foo", (...args) => calls.push(args));
            object.foo = 42;
            expect(object.foo).to.equal(42);
            expect(calls).to.deep.equal([["foo", 42]]);
        });
    });

    describe("splice()", function() {
        it("should notify watchers", function() {
            let arr = new micro.bind.Watchable(["a", "b", "c", "d"]);
            let calls = [];
            arr.watch(Symbol.for("+"), (...args) => calls.push(["+"].concat(args)));
            arr.watch(Symbol.for("-"), (...args) => calls.push(["-"].concat(args)));
            arr.splice(1, 2, "x", "y");
            expect(arr).to.deep.equal(["a", "x", "y", "d"]);
            expect(calls).to.deep.equal([["-", "2", "c"], ["-", "1", "b"], ["+", "1", "x"],
                                         ["+", "2", "y"]]);
        });
    });

    describe("push()", function() {
        it("should notify watchers", function() {
            let arr = new micro.bind.Watchable(["a", "b"]);
            let calls = [];
            arr.watch(Symbol.for("+"), (...args) => calls.push(args));
            arr.push("c");
            expect(arr).to.deep.equal(["a", "b", "c"]);
            expect(calls).to.deep.equal([["2", "c"]]);
        });
    });
});

describe("filter()", function() {
    function makeArrays() {
        let arr = new micro.bind.Watchable(["a1", "b1", "a2", "b2"]);
        return [arr, micro.bind.filter(arr, item => item.startsWith("a"))];
    }

    describe("on arr set", function() {
        it("should update item if item still passes", function() {
            let [arr, filtered] = makeArrays();
            arr[2] = "ax";
            expect(filtered).to.deep.equal(["a1", "ax"]);
        });

        it("should include item if item passes now", function() {
            let [arr, filtered] = makeArrays();
            arr[1] = "ax";
            expect(filtered).to.deep.equal(["a1", "ax", "a2"]);
        });

        it("should exclude item if item does not pass anymore", function() {
            let [arr, filtered] = makeArrays();
            arr[0] = "bx";
            expect(filtered).to.deep.equal(["a2"]);
        });

        it("should have no effect if item still does not pass", function() {
            let [arr, filtered] = makeArrays();
            arr[1] = "bx";
            expect(filtered).to.deep.equal(["a1", "a2"]);
        });
    });

    describe("on arr splice", function() {
        it("should update filtered array", function() {
            let [arr, filtered] = makeArrays();
            arr.splice(1, 2, "ax", "bx");
            expect(filtered).to.deep.equal(["a1", "ax"]);
        });
    });
});

describe("map()", function() {
    function makeArray() {
        let arr = new micro.bind.Watchable(["a", "b", "c"]);
        let mapped = micro.bind.map(arr, item => item + item);
        return [arr, mapped];
    }

    describe("on arr set", function() {
        it("should update mapped array", function() {
            let [arr, mapped] = makeArray();
            arr[1] = "x";
            expect(mapped).to.deep.equal(["aa", "xx", "cc"]);
        });
    });

    describe("on arr splice", function() {
        it("should update mapped array", function() {
            let [arr, mapped] = makeArray();
            arr.splice(1, 1, "x");
            expect(mapped).to.deep.equal(["aa", "xx", "cc"]);
        });
    });
});

describe("bind()", function() {
    function setupDOM(expr, data = {}) {
        let main = document.querySelector("main");
        main.innerHTML = `<span data-result="${expr}"></span>`;
        let span = main.firstElementChild;
        micro.bind.bind(span, data);
        return span;
    }

    function setupDOMWithList() {
        let main = document.querySelector("main");
        main.innerHTML = `
            <ul data-content="list items 'item'">
                <template><li data-content="item"></li></template>
            </ul>
        `;
        let ul = main.firstElementChild;
        let arr = new micro.bind.Watchable(["a", "b", "c"]);
        micro.bind.bind(ul, {items: arr});
        return [arr, ul];
    }

    function setupDOMWithSwitch(state, defaultTemplate = true) {
        let main = document.querySelector("main");
        main.innerHTML = `
            <p data-content="switch state 'a' 'b'">
                <template>1: <span data-content="state"></span></template>
                <template>2: <span data-content="state"></span></template>
                <template>Default: <span data-content="state"></span></template>
            </p>
        `;
        let p = main.firstElementChild;
        if (!defaultTemplate) {
            p.lastElementChild.remove();
        }
        micro.bind.bind(p, {state});
        return p;
    }

    function setupDOMWithRender() {
        let main = document.querySelector("main");
        main.innerHTML = `
            <p data-content="render template">
                <template><span data-content="value"></span> (fallback)</template>
            </p>
            <template><span data-content="value"></span></template>
        `;
        let elem = main.firstElementChild;
        let template = main.lastElementChild;
        return [elem, template];
    }

    it("should update DOM", function() {
        let span = setupDOM("value", {value: "Purr"});
        expect(span.result).to.equal("Purr");
    });

    it("should update DOM with multiple elements", function() {
        let main = document.querySelector("main");
        main.innerHTML = '<span data-title="value"></span><span data-id="value"></span>';
        let elems = main.children;
        micro.bind.bind(elems, {value: "Purr"});
        expect(elems[0].title).to.equal("Purr");
        expect(elems[1].id).to.equal("Purr");
    });

    it("should update DOM with content", function() {
        let main = document.querySelector("main");
        main.innerHTML = '<span data-content="value"></span>';
        let span = main.firstElementChild;
        micro.bind.bind(span, {value: "Purr"});
        expect(span.textContent).to.equal("Purr");
    });

    it("should update DOM with class", function() {
        let main = document.querySelector("main");
        main.innerHTML = '<span data-class-cat-paw="value"></span>';
        let span = main.firstElementChild;
        micro.bind.bind(span, {value: true});
        expect(span.className).to.equal("cat-paw");
    });

    it("should update DOM with new", function() {
        let span = setupDOM("new Date", {Date});
        expect(span.result).to.be.instanceof(Date);
    });

    it("should update DOM with eq", function() {
        let span = setupDOM("eq 'same' 'same'");
        expect(span.result).to.be.true;
    });

    it("should update DOM with or", function() {
        let span = setupDOM("or '' 42");
        expect(span.result).to.equal(42);
    });

    it("should update DOM with not", function() {
        let span = setupDOM("not true");
        expect(span.result).to.be.false;
    });

    it("should update DOM with bind", function() {
        let calls = [];
        function f(...args) {
            calls.push(args);
        }
        let span = setupDOM("bind f 'Purr'", {f});
        span.result(42);
        expect(calls).to.deep.equal([["Purr", 42]]);
    });

    it("should update DOM with format", function() {
        let span = setupDOM("format 'Cat: {msg}' 'msg' 'Purr'");
        expect(span.result).to.equal("Cat: Purr");
    });

    it("should update DOM with formatPlural", function() {
        let span = setupDOM("formatPlural 'Singular {n}' 'Plural {n}' 'n' 2");
        expect(span.result).to.equal("Plural 2");
    });

    it("should update DOM with join", function() {
        let main = document.querySelector("main");
        main.innerHTML = `
            <p data-content="join items 'item'">
                <template><span data-content="item"></span></template>
            </p>
        `;
        let p = main.firstElementChild;
        micro.bind.bind(p, {items: ["a", "b", "c"]});
        let nodes = Array.from(p.childNodes, n => n.textContent);
        expect(nodes).to.deep.equal(["a", ", ", "b", ", ", "c"]);
    });

    it("should update DOM with switch", function() {
        let p = setupDOMWithSwitch("b");
        expect(p.textContent).to.equal("2: b");
    });

    it("should update DOM with switch for non-matching value and default template", function() {
        let p = setupDOMWithSwitch("x");
        expect(p.textContent).to.equal("Default: x");
    });

    it("should update DOM with switch for non-matching value and no default template", function() {
        let p = setupDOMWithSwitch("x", false);
        expect(p.textContent).to.be.empty;
    });

    it("should update DOM with render", function() {
        let [elem, template] = setupDOMWithRender();
        micro.bind.bind(elem, {template, value: "Purr"});
        expect(elem.textContent).to.equal("Purr");
    });

    it("should update DOM with render for null template", function() {
        let [elem] = setupDOMWithRender();
        micro.bind.bind(elem, {template: null, value: "Purr"});
        expect(elem.textContent).to.equal("Purr (fallback)");
    });

    it("should update DOM with nested binding", function() {
        let main = document.querySelector("main");
        main.innerHTML = '<p data-title="outer"><span data-title="inner"></span></p>';
        let p = main.firstElementChild;
        let span = document.querySelector("span");
        micro.bind.bind(span, {inner: "Inner"});
        micro.bind.bind(p, {outer: "Outer"});
        expect(span.title).to.equal("Inner");
        expect(p.title).to.equal("Outer");
    });

    it("should fail if reference is undefined", function() {
        let main = document.querySelector("main");
        main.innerHTML = '<span data-title="value"></span>';
        let span = main.firstElementChild;
        expect(() => micro.bind.bind(span, {})).to.throw(ReferenceError);
    });

    it("should fail if transform is not a function", function() {
        let main = document.querySelector("main");
        main.innerHTML = '<span data-title="value 42"></span>';
        let span = main.firstElementChild;
        let data = {value: true};
        expect(() => micro.bind.bind(span, data)).to.throw(TypeError);
    });

    describe("on data set", function() {
        it("should update DOM", function() {
            let main = document.querySelector("main");
            main.innerHTML = '<span data-title="value"></span>';
            let span = main.firstElementChild;
            let data = new micro.bind.Watchable({value: null});
            micro.bind.bind(span, data);
            data.value = "Purr";
            expect(span.title).to.equal("Purr");
        });
    });

    describe("on data arr set", function() {
        it("should update DOM with list", function() {
            let [arr, ul] = setupDOMWithList();
            arr[1] = "x";
            expect(Array.from(ul.children, c => c.textContent)).to.deep.equal(["a", "x", "c"]);
        });
    });

    describe("on data arr splice", function() {
        it("should update DOM with list", function() {
            let [arr, ul] = setupDOMWithList();
            arr.splice(1, 1, "x", "y");
            expect(Array.from(ul.children, c => c.textContent)).to.deep.equal(["a", "x", "y", "c"]);
        });
    });
});

describe("parse()", function() {
    it("should parse expression", function() {
        let args = micro.bind.parse("true false null undefined 'word word' 42 x.y");
        expect(args).to.deep.equal([true, false, null, undefined, "word word", 42,
                                    {name: "x.y", tokens: ["x", "y"]}]);
    });
});

describe("transforms", function() {
    describe("includes()", function() {
        it("should return true for searchElement in arr", function() {
            let includes = micro.bind.transforms.includes(null, ["a", "b"], "b");
            expect(includes).to.be.true;
        });
    });
});

describe("dash()", function() {
    it("should convert to dashed style", function() {
        let dashed = micro.bind.dash("OneTwoAThree");
        expect(dashed).to.equal("one-two-a-three");
    });
});
