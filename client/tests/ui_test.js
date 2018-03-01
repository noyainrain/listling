/*
 * Open Listling
 * Copyright (C) 2018 Open Listling contributors
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

/* eslint-env mocha, node */
/* eslint-disable no-invalid-this, prefer-arrow-callback */

"use strict";

let {exec, spawn} = require("child_process");
let {promisify} = require("util");

let {expect} = require("chai");
let {until} = require("selenium-webdriver");

let {startBrowser, untilElementTextLocated} = require("@noyainrain/micro/test");

const URL = "http://localhost:8081";

describe("UI", function() {
    let server;
    let browser;
    let timeout;

    this.timeout(5 * 60 * 1000);

    async function createExampleList() {
        await browser.findElement({css: ".micro-ui-logo"}).click();
        await browser.findElement({css: ".listling-start-create-example button"}).click();
        await browser.wait(until.elementLocated({css: "listling-list-page"}));
    }

    beforeEach(async function() {
        await promisify(exec)("redis-cli -n 15 flushdb");
        server = spawn("python3", ["-m", "listling", "--port", "8081", "--redis-url", "15"],
                       {cwd: "..", stdio: "inherit"});
        browser = startBrowser(this.currentTest, "Open Listling");
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
        let itemMenu;

        // View start page
        await browser.get(`${URL}/`);
        await browser.wait(
            untilElementTextLocated({css: ".micro-logo"}, "My Open Listling"), timeout);

        // Create list
        await browser.findElement({css: ".listling-start-create-list"}).click();
        await browser.wait(
            untilElementTextLocated({css: "listling-list-page h1"}, "New to-do list"), timeout);

        // Create example list
        await createExampleList();
        let title = (await browser.findElement({css: "listling-list-page h1"}).getText()).trim();
        expect(title).to.equal("Project tasks");

        // Edit list
        await browser.findElement({css: ".listling-list-edit"}).click();
        form = await browser.findElement({css: "listling-list-page form"});
        input = await form.findElement({name: "title"});
        await input.clear();
        await input.sendKeys("Cat colony tasks");
        await form.findElement({name: "description"}).sendKeys("What has to be done!");
        await form.findElement({css: "button:not([type])"}).click();
        await browser.wait(
            untilElementTextLocated({css: "listling-list-page h1"}, "Cat colony tasks"));

        // Create item
        await browser.findElement({css: ".listling-list-create-item button"}).click();
        form = await browser.findElement({css: ".listling-list-create-item form"});
        await form.findElement({name: "title"}).sendKeys("Sleep");
        await form.findElement({name: "text"}).sendKeys("Very important!");
        await form.findElement({css: "button:not([type])"}).click();
        await browser.wait(
            untilElementTextLocated({css: "[is=listling-item]:last-child h1"}, "Sleep"), timeout);

        // Edit item
        itemMenu = await browser.findElement({css: ".listling-item-menu li:last-child"});
        await itemMenu.click();
        await browser.findElement({css: ".listling-item-edit"}).click();
        form = await browser.findElement({css: "[is=listling-item] form"});
        input = await form.findElement({name: "title"});
        await input.clear();
        await input.sendKeys("Research");
        await form.findElement({css: "button:not([type])"}).click();
        await browser.wait(untilElementTextLocated({css: "[is=listling-item] h1"}, "Research"),
                           timeout);

        // Trash item
        await itemMenu.click();
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
        let checkSelector =
            {css: ".listling-list-items > li:first-child .listling-item-check .action"};
        let uncheckSelector =
            {css: ".listling-list-items > li:first-child .listling-item-uncheck .action"};
        await browser.findElement(uncheckSelector).click();
        let checkButton = await browser.wait(until.elementLocated(checkSelector), timeout);

        // Check item
        await checkButton.click();
        await browser.wait(until.elementLocated(uncheckSelector), timeout);

        // View about page
        await browser.findElement({css: ".micro-ui-header-menu"}).click();
        await browser.findElement({css: ".micro-ui-about"}).click();
        await browser.wait(
            untilElementTextLocated({css: "micro-about-page h1"}, "About My Open Listling"),
            timeout);
    });

    it("should work for staff", async function() {
        await browser.get(`${URL}/`);
        await browser.wait(until.elementLocated({css: "listling-start-page"}), timeout);
        await createExampleList();

        // View activity page
        await browser.findElement({css: ".micro-ui-header-menu"}).click();
        await browser.findElement({css: ".micro-ui-activity"}).click();
        await browser.wait(
            untilElementTextLocated({css: "micro-activity-page .micro-timeline li"},
                                    "Project tasks"),
            timeout);
    });
});
