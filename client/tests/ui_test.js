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

"use strict";

let {exec, spawn} = require("child_process");
let {promisify} = require("util");

let {until} = require("selenium-webdriver");

let {startBrowser, untilElementTextLocated} = require("@noyainrain/micro/test");

describe("UI", function() {
    let server;
    let browser;
    let timeout;

    this.timeout(5 * 60 * 1000);

    beforeEach(async function() {
        await promisify(exec)("redis-cli -n 15 flushdb");
        server = spawn("python3", ["-m", "listling", "--port", "8081", "--redis-url", "15"],
                       {cwd: "..", stdio: "inherit"});
        browser = startBrowser(this.currentTest, "listling");
        timeout = browser.remote ? 10 * 1000 : 1000;
    });

    afterEach(async function() {
        if (browser) {
            await browser.quit();
        }
        if (server) {
            server.kill();
        }
    });

    it("should work for a user", async function() {
        let form;
        let input;

        // View start page
        await browser.get("http://localhost:8081/");
        await browser.wait(untilElementTextLocated({css: ".micro-logo"}, "My Open Listling"),
                           timeout)

        // Create list
        await browser.findElement({css: ".listling-use-case-create-list"}).click();
        form = await browser.findElement({css: "listling-list-page form"});
        await form.findElement({name: "title"}).sendKeys("Colony tasks");
        await form.findElement({name: "description"}).sendKeys("What has to be done!");
        await form.findElement({css: "button:not([type])"}).click();
        await browser.wait(untilElementTextLocated({css: "listling-list-page h1"}, "Colony tasks"),
                           timeout);

        // Create example list
        await browser.findElement({css: ".micro-ui-logo"}).click();
        await browser.findElement({css: ".listling-use-case-create-example"}).click();
        await browser.wait(untilElementTextLocated({css: "listling-list-page h1"}, "Project tasks"),
                           timeout);

        // Edit list
        await browser.findElement({css: ".listling-list-edit"}).click();
        form = await browser.findElement({css: "listling-list-page form"});
        input = await form.findElement({name: "title"});
        await input.clear();
        await input.sendKeys("Colony tasks");
        await form.findElement({css: "button:not([type])"}).click();
        await browser.wait(untilElementTextLocated({css: "listling-list-page h1"}, "Colony tasks"));

        // Add item
        await browser.findElement({css: ".listling-list-create-item button"}).click();
        form = await browser.findElement({css: ".listling-list-create-item form"});
        await form.findElement({name: "title"}).sendKeys("Sleep");
        await form.findElement({name: "description"}).sendKeys("FOOTODO");
        await form.findElement({css: "button:not([type])"}).click();
        await browser.wait(
            untilElementTextLocated({css: "[is=listling-item]:last-child h1"}, "Sleep"), timeout);

        // Edit item
        await browser.findElement({css: ".listling-item-edit"}).click();
        form = await browser.findElement({css: "[is=listling-item] form"});
        input = await form.findElement({name: "title"});
        await input.clear();
        await input.sendKeys("Research");
        await form.findElement({css: "button:not([type])"}).click();
        await browser.wait(untilElementTextLocated({css: "[is=listling-item] h1"}, "Research"),
                           timeout);

        // Trash item
        await browser.findElement({css: "[is=listling-item] [is=micro-menu]:last-child li:last-child"})
            .click();
        await browser.findElement({css: ".listling-item-trash"}).click();
        await browser.wait(
            until.elementIsVisible(await browser.findElement({css: ".listling-list-trash p"})),
            timeout);

        // Restore item
        await browser.findElement({css: ".listling-list-trash button"}).click();
        await browser.findElement({css: ".listling-list-trash .listling-item-restore"}).click();
        await browser.wait(untilElementTextLocated({css: "[is=listling-item] h1"}, "Research"),
                           timeout);

        // Uncheck item
        let checkButton = await browser.findElement({css: ".listling-item-check .action"});
        let uncheckButton = await browser.findElement({css: ".listling-item-uncheck .action"});
        await uncheckButton.click();
        await browser.wait(until.elementIsVisible(checkButton), timeout);

        // Check item
        await checkButton.click();
        await browser.wait(until.elementIsVisible(uncheckButton), timeout);

        // View about
        // TODO
        await browser.sleep(2000);
    });
});
