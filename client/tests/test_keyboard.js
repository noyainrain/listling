/*
 * keyboard.js
 * Released into the public domain
 * https://github.com/noyainrain/micro/blob/master/client/keyboard.js
 */

/* eslint-env mocha */
/* global chai, expect */
/* eslint-disable no-unused-expressions, prefer-arrow-callback */

"use strict";

window.expect = window.expect || chai.expect;

describe("ShortcutContext", function() {
    function setupDOM(calls) {
        let main = document.querySelector("main");
        main.innerHTML = "<span><input></input></span>";
        main.addEventListener("keydown", event => calls.push(["keydown", event.key]));
        let span = main.firstElementChild;
        span.shortcutContext = new micro.keyboard.ShortcutContext(span);
        span.shortcutContext.add("A", (...args) => calls.push(["shortcut"].concat(args)));
        span.shortcutContext.add("Shift+A", (...args) => calls.push(["shortcut"].concat(args)));
        span.shortcutContext.add("?", (...args) => calls.push(["shortcut"].concat(args)));
        span.shortcutContext.add("B,A", (...args) => calls.push(["shortcut"].concat(args)));
        span.shortcutContext.add(
            "Control+Shift+Enter", (...args) => calls.push(["shortcut"].concat(args))
        );
        return [span, span.firstElementChild];
    }

    describe("on keydown", function() {
        it("should trigger", function() {
            let calls = [];
            let [span] = setupDOM(calls);
            span.dispatchEvent(new KeyboardEvent("keydown", {key: "a", bubbles: true}));
            expect(calls).to.deep.equal([["shortcut", "A", span.shortcutContext]]);
        });

        it("should trigger for modifier", function() {
            const calls = [];
            const [span] = setupDOM(calls);
            span.dispatchEvent(
                new KeyboardEvent("keydown", {key: "A", shiftKey: true, bubbles: true})
            );
            expect(calls).to.deep.equal([["shortcut", "Shift+A", span.shortcutContext]]);
        });

        it("should trigger for shifted symbol", function() {
            const calls = [];
            const [span] = setupDOM(calls);
            span.dispatchEvent(
                new KeyboardEvent("keydown", {key: "?", shiftKey: true, bubbles: true})
            );
            expect(calls).to.deep.equal([["shortcut", "?", span.shortcutContext]]);
        });

        it("should trigger for prefix", function() {
            let calls = [];
            let [span] = setupDOM(calls);
            span.dispatchEvent(new KeyboardEvent("keydown", {key: "b", bubbles: true}));
            span.dispatchEvent(new KeyboardEvent("keydown", {key: "a", bubbles: true}));
            expect(calls).to.deep.equal([["shortcut", "B,A", span.shortcutContext]]);
        });

        it("should do nothing for other key", function() {
            let calls = [];
            let [span] = setupDOM(calls);
            span.dispatchEvent(new KeyboardEvent("keydown", {key: "c", bubbles: true}));
            expect(calls).to.deep.equal([["keydown", "c"]]);
        });

        it("should do nothing in input mode", function() {
            let calls = [];
            let [, input] = setupDOM(calls);
            input.dispatchEvent(new KeyboardEvent("keydown", {key: "a", bubbles: true}));
            expect(calls).to.deep.equal([["keydown", "a"]]);
        });

        it("should trigger for functional key in input mode", function() {
            let calls = [];
            let [span, input] = setupDOM(calls);
            input.dispatchEvent(
                new KeyboardEvent("keydown", {key: "Enter", ctrlKey: true, shiftKey: true, bubbles: true})
            );
            expect(calls).to.deep.equal(
                [["shortcut", "Control+Shift+Enter", span.shortcutContext]]
            );
        });
    });
});

describe("Shortcut", function() {
    function setupDOM(calls) {
        let main = document.querySelector("main");
        main.innerHTML = "<button></button>";
        main.shortcutContext = new micro.keyboard.ShortcutContext(main);
        let button = main.firstElementChild;
        button.shortcut = new micro.keyboard.Shortcut(button, "A");
        button.addEventListener("click", () => calls.push(["click"]));
        return main;
    }

    describe("on shortcut", function() {
        it("should click element", function() {
            let calls = [];
            let main = setupDOM(calls);
            main.shortcutContext.trigger("A");
            expect(calls).to.deep.equal([["click"]]);
        });

        it("should do nothing if elem is invisible", function() {
            let calls = [];
            let main = setupDOM(calls);
            main.style.display = "none";
            main.shortcutContext.trigger("A");
            expect(calls).to.deep.equal([]);
        });
    });
});

describe("quickNavigate", function() {
    function setupDOM(focusIndex) {
        let main = document.querySelector("main");
        main.innerHTML = `
            <div class="micro-quick-nav" tabindex="0"></div>
            <div></div>
            <div class="micro-quick-nav" tabindex="0" style="display: none;"></div>
            <div class="micro-quick-nav" tabindex="0"></div>
        `;
        let elems = Array.from(main.children);
        elems[focusIndex].focus();
        return elems;
    }

    it("should focus next", function() {
        let elems = setupDOM(0);
        micro.keyboard.quickNavigate();
        expect(document.activeElement).to.equal(elems[3]);
    });

    it("should focus body for last element", function() {
        setupDOM(3);
        micro.keyboard.quickNavigate();
        expect(document.activeElement).to.equal(document.body);
    });

    it("should focus previous if dir is prev", function() {
        let elems = setupDOM(3);
        micro.keyboard.quickNavigate("prev");
        expect(document.activeElement).to.equal(elems[0]);
    });
});

describe("watchLifecycle", function() {
    function makeSpan(calls) {
        let span = document.createElement("span");
        micro.keyboard.watchLifecycle(span, {
            onConnect: (...args) => calls.push(["connect"].concat(args)),
            onDisconnect: (...args) => calls.push(["disconnect"].concat(args))
        });
        return span;
    }

    function timeout(delay) {
        return new Promise(resolve => setTimeout(resolve, delay));
    }

    describe("on connect", function() {
        it("should notify watchers", async function() {
            let calls = [];
            let span = makeSpan(calls);
            document.querySelector("main").appendChild(span);
            await timeout();
            expect(calls).to.deep.equal([["connect", span]]);
        });

        it("should do nothing for disconnected elem", async function() {
            let main = document.querySelector("main");
            let calls = [];
            let span = makeSpan(calls);
            main.appendChild(span);
            await timeout();
            span.remove();
            await timeout();
            main.appendChild(span);
            await timeout();
            expect(calls).to.deep.equal([["connect", span], ["disconnect", span]]);
        });
    });
});

describe("enableActivedClass", function() {
    function setupDOM() {
        let main = document.querySelector("main");
        main.innerHTML = "<button></button><button></button>";
        micro.keyboard.enableActivatedClass();
        return Array.from(main.children);
    }

    describe("on click", function() {
        it("should apply activated class", function() {
            let buttons = setupDOM();
            buttons[0].focus();
            buttons[0].click();
            expect(buttons[0].classList.contains("micro-activated")).to.be.true;
        });
    });

    describe("on blur", function() {
        it("should reset activated class", function() {
            let buttons = setupDOM();
            buttons[0].focus();
            buttons[0].click();
            buttons[1].focus();
            buttons[1].click();
            expect(buttons[0].classList.contains("micro-activated")).to.be.false;
        });
    });
});
