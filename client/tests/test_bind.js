/* TODO */

let expect = chai.expect;

describe("Watchable", function() {
    describe("set()", function() {
        it("should notify watchers", function() {
            let object = new micro.bind.Watchable();
            let calls = [];
            object.watch("foo", (...args) => calls.push(args));
            object.foo = "bar";
            expect(object.foo).to.equal("bar");
            expect(calls).to.deep.equal([["foo", "bar"]]);
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
    function f() {
        let arr = new micro.bind.Watchable(["a1", "x1", "a2", "x2"]);
        return [arr, micro.bind.filter(arr, v => v.startsWith("a"))];
    }

    describe("on source set", function() {
        it("should include item if item passes now", function() {
            let [arr, filtered] = f();
            arr[1] = "aa";
            expect(filtered).to.deep.equal(["a1", "aa", "a2"]);
        });

        it("should exclude item if item does not pass anymore", function() {
            let [arr, filtered] = f();
            arr[0] = "xx";
            expect(filtered).to.deep.equal(["a2"]);
        });

        it("should update item if item still passes", function() {
            let [arr, filtered] = f();
            arr[2] = "aa";
            expect(filtered).to.deep.equal(["a1", "aa"]);
        });

        it("should have no effect if item still does not pass", function() {
            let [arr, filtered] = f();
            arr[1] = "xx";
            expect(filtered).to.deep.equal(["a1", "a2"]);
        });
    });

    describe("on source splice", function() {
        it("should update filtered array", function() {
            let [arr, filtered] = f();
            arr.splice(1, 2, "aa", "xx");
            expect(filtered).to.deep.equal(["a1", "aa"]);
        });
    });
});

describe("bind()", function() {
    function f() {
        let arr = new micro.bind.Watchable(["a", "b", "c"]);
        document.body.innerHTML = `
            <ul>
                <template><li></li></template>
            </ul>
        `;
        let elem = document.querySelector("ul");
        elem.appendChild(micro.bind.list(elem, arr, "item"));
        return [arr, elem];
    }

    describe("on update", function() {
        it("should update DOM with join", function() {
            let arr = ["a", "b", "c"];
            document.body.innerHTML = `
                <p>
                    <template><span></span></template>
                </p>
            `;
            let elem = document.querySelector("p");
            elem.appendChild(micro.bind.join(elem, arr, "item"));
            let nodes = Array.from(elem.childNodes, n => n.nodeType === Node.ELEMENT_NODE ? n.item : n.nodeValue);
            expect(nodes).to.deep.equal(["a", ", ", "b", ", ", "c"]);
        });
    });

    describe("on array update", function() {
        it("should update DOM with list", function() {
            let [arr, elem] = f();
            arr[1] = "x";
            let children = Array.from(elem.children, c => c.item);
            expect(children).to.deep.equal(["a", "x", "c"]);
        });
    });

    describe("on array splice", function() {
        it("should update DOM with list", function() {
            let [arr, elem] = f();
            arr.splice(1, 1, "x", "y");
            let children = Array.from(elem.children, c => c.item);
            expect(children).to.deep.equal(["a", "x", "y", "c"]);
        });
    });
});
