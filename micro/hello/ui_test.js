/*
 * micro
 * Copyright (C) 2018 micro contributors
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

/* eslint-env mocha, node */
/* eslint-disable no-invalid-this, prefer-arrow-callback */

"use strict";

let {exec, spawn} = require("child_process");
const {mkdtemp} = require("fs").promises;
const {tmpdir} = require("os");
let {promisify} = require("util");

let {until} = require("selenium-webdriver");

const {getWithServiceWorker, startBrowser, untilElementTextLocated} =
    require("@noyainrain/micro/test");

const URL = "http://localhost:8081";

describe("UI", function() {
    let server;
    let browser;
    let timeout;

    this.timeout(5 * 60 * 1000);

    beforeEach(async function() {
        await promisify(exec)("redis-cli -n 15 flushdb");
        const filesPath = await mkdtemp(`${tmpdir()}/`);
        server = spawn(
            "python3",
            ["-m", "hello", "--port", "8081", "--redis-url", "15", "--files-path", filesPath],
            {stdio: "inherit"}
        );
        browser = startBrowser(this.currentTest, "micro");
        timeout = browser.remote ? 10 * 1000 : 1000;
    });

    afterEach(async function() {
        if (server) {
            server.kill();
        }
        if (browser) {
            await browser.quit();
        }
    });

    it("should work for a user", async function() {
        let form;
        let input;

        // View start page
        await getWithServiceWorker(browser, `${URL}/`);
        await browser.wait(
            untilElementTextLocated({css: ".micro-logo"}, "Hello"), timeout);

        // Create greeting
        // form = await browser.findElement({css: "hello-start-page form"});
        // input = await form.findElement({name: "text"});
        // await input.sendKeys("Meow!");
        // await form.findElement({css: "button"}).click();
        // await browser.wait(
        //     untilElementTextLocated({css: ".hello-start-greetings > li > p"}, "Meow!"), timeout
        // )

        // Edit user
        await browser.findElement({css: ".micro-ui-header-user"}).click();
        await browser.findElement({css: ".micro-ui-edit-user"}).click();
        await browser.wait(
            untilElementTextLocated({css: "micro-edit-user-page h1"}, "Edit user settings"),
            timeout);
        form = await browser.findElement({css: ".micro-edit-user-edit"});
        input = await form.findElement({name: "name"});
        await input.clear();
        await input.sendKeys("Happy");
        await form.findElement({css: "button"}).click();
        await browser.wait(
            until.elementTextContains(
                await browser.findElement({css: ".micro-ui-header micro-user"}),
                "Happy"),
            timeout);

        // View about page
        await browser.findElement({css: ".micro-ui-header-menu"}).click();
        await browser.findElement({css: ".micro-ui-about"}).click();
        await browser.wait(
            untilElementTextLocated({css: "micro-about-page h1"}, "About Hello"), timeout);
    });

    it("should work for staff", async function() {
        // Edit site settings
        await browser.get(`${URL}/`);
        let menu = await browser.wait(until.elementLocated({css: ".micro-ui-header-menu"}),
                                      timeout);
        await browser.wait(until.elementIsVisible(menu), timeout);
        await menu.click();
        await browser.findElement({css: ".micro-ui-edit-settings"}).click();
        await browser.wait(
            untilElementTextLocated({css: "micro-edit-settings-page h1"}, "Edit site settings"),
            timeout);
        let form = await browser.findElement({css: ".micro-edit-settings-edit"});
        let input = await form.findElement({name: "title"});
        await input.clear();
        await input.sendKeys("CatApp");
        await form.findElement({name: "icon"}).sendKeys("/static/images/icon.svg");
        await form.findElement({name: "icon_small"}).sendKeys("/static/images/icon-small.png");
        await form.findElement({name: "icon_large"}).sendKeys("/static/images/icon-large.png");
        await form.findElement({name: "provider_name"}).sendKeys("Happy");
        await form.findElement({name: "provider_url"}).sendKeys("https://happy.example.org/");
        await form.findElement({name: "feedback_url"}).sendKeys("https://feedback.example.org/");
        await form.findElement({css: "button"}).click();
        await browser.wait(
            until.elementTextContains(await browser.findElement({css: ".micro-ui-logo"}),
                                      "CatApp"),
            timeout);

        // View analytics page
        await menu.click();
        await browser.findElement({css: ".micro-ui-analytics"}).click();
        await browser.wait(
            untilElementTextLocated({css: "micro-analytics-page h1"}, "Analytics"), timeout
        );

        // View activity page
        await menu.click();
        await browser.findElement({css: ".micro-ui-activity"}).click();
        await browser.wait(
            untilElementTextLocated({css: "micro-activity-page .micro-timeline li"},
                                    "site settings"),
            timeout);
    });
});
