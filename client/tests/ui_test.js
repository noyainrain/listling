/*
 * Open Listling
 * Copyright (C) 2021 Open Listling contributors
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
/* eslint-disable no-invalid-this, no-unused-expressions, prefer-arrow-callback */

"use strict";

let {exec, spawn} = require("child_process");
const {mkdtemp} = require("fs").promises;
const {hostname, tmpdir} = require("os");
let {promisify} = require("util");

let {expect} = require("chai");
let {until} = require("selenium-webdriver");

const {getWithServiceWorker, startBrowser, untilElementAttributeMatches, untilElementTextLocated} =
    require("@noyainrain/micro/test");

const URL = "http://localhost:8081";

describe("UI", function() {
    let server;
    let browser;
    let timeout;

    this.timeout(10 * 60 * 1000);

    async function createExampleList() {
        await browser.findElement({css: ".micro-ui-menu"}).click();
        await browser.findElement({css: ".listling-ui-intro"}).click();
        await browser.findElement({css: ".listling-intro-create-example"}).click();
        await browser.wait(until.elementLocated({css: "listling-list-page"}));
    }

    async function readItemPlayPause(item) {
        await item.findElement({css: ".listling-item-menu"}).click();
        const text = await item.findElement({css: ".listling-item-play-pause"}).getText();
        await item.click();
        // Work around Safari not collapsing line breaks (see
        // https://bugs.webkit.org/show_bug.cgi?id=174617)
        return text.trim();
    }

    beforeEach(async function() {
        await promisify(exec)("redis-cli -n 15 flushdb");
        const filesPath = await mkdtemp(`${tmpdir()}/`);
        server = spawn(
            "python3",
            ["-m", "listling", "--port", "8081", "--redis-url", "15", "--files-path", filesPath],
            {cwd: "..", stdio: "inherit"}
        );
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

        // View intro page
        // Work around Sauce Labs buffering on localhost
        await browser.get(`http://${hostname()}:8081/`);
        await browser.wait(
            untilElementTextLocated({css: ".micro-logo"}, "My Open Listling"), timeout);
        const menu = await browser.findElement({css: ".micro-ui-menu"});

        // Create list
        await browser.findElement({css: ".listling-intro-create-list"}).click();
        await browser.wait(
            untilElementTextLocated({css: "listling-list-page h1"}, "New to-do list"), timeout
        );

        // View start page
        await browser.findElement({css: ".micro-ui-logo"}).click();
        await browser.wait(
            untilElementTextLocated({css: ".listling-start-lists .link"}, "New to-do list"), timeout
        );

        // Create list
        await browser.findElement({css: ".listling-start-create .action"}).click();
        await browser.findElement({css: ".listling-start-create li:last-child"})
            .click();
        await browser.wait(
            untilElementTextLocated({css: "listling-list-page h1"}, "New list"), timeout
        );

        // Create example list
        await createExampleList();
        let title = (await browser.findElement({css: "listling-list-page h1"}).getText()).trim();
        expect(title).to.equal("Project tasks");

        // Edit list
        await browser.findElement({css: ".listling-list-menu"}).click();
        await browser.findElement({css: ".listling-list-edit"}).click();
        await browser.findElement({css: ".listling-list-settings button"}).click();
        form = await browser.findElement({css: "listling-list-page form"});
        input = await form.findElement({name: "title"});
        await input.clear();
        await input.sendKeys("Cat colony tasks");
        await form.findElement({name: "description"}).sendKeys("What has to be done!");
        await form.findElement({name: "assign-by-default"}).click();
        await form.findElement({css: "[name=features][value=vote]"}).click();
        await form.findElement({css: "[name=features][value=value]"}).click();
        await form.findElement({name: "value-unit"}).sendKeys("min");
        await form.findElement({css: "[name=features][value=time]"}).click();
        await form.findElement({css: "[name=features][value=play]"}).click();
        await browser.executeScript(
            () => document.querySelector("listling-list-page button:not([type])").scrollIntoView());
        await form.findElement({css: "button:not([type])"}).click();
        await browser.wait(
            untilElementTextLocated({css: "listling-list-page h1"}, "Cat colony tasks"));
        // Work around Edge not firing blur event when a button gets disabled
        await browser.findElement({css: ".listling-list-menu"}).click();

        // Create item
        await browser.findElement({css: ".listling-list-create-item button"}).click();
        await browser.executeScript(() => scroll(0, document.scrollingElement.scrollHeight));
        form = await browser.findElement({css: ".listling-list-create-item form"});
        await form.findElement({name: "title"}).sendKeys("Sleep");
        await form.findElement({name: "value"}).sendKeys("60");
        await browser.executeScript(() => {
            document.querySelector(".listling-list-create-item micro-datetime-input").value =
                "2015-08-27T12:00:00.000Z";
        });
        await form.findElement({css: ".micro-content-input-text"}).sendKeys("Very important!");
        // Work around Safari 13 missing elements on click (see
        // https://bugs.webkit.org/show_bug.cgi?id=202589)
        await browser.executeScript(
            () => document.querySelector(".listling-list-create-item button:not([type])").click()
        );
        await browser.wait(
            untilElementTextLocated({css: "[is=listling-item]:last-child h1"}, "Sleep"), timeout
        );
        const td = browser.findElement({css: ".listling-list-value-summary td:last-child"});
        // Work around Safari not collapsing line breaks (see
        // https://bugs.webkit.org/show_bug.cgi?id=174617)
        await browser.wait(until.elementTextMatches(td, /60\s+min/u), timeout);

        // Edit item
        await browser.executeScript(() => scroll(0, 0));
        itemMenu = await browser.findElement({css: ".listling-item-menu"});
        await itemMenu.click();
        await browser.findElement({css: ".listling-item-edit"}).click();
        form = await browser.findElement({css: "[is=listling-item] form"});
        input = await form.findElement({name: "title"});
        await input.clear();
        await input.sendKeys("Research");
        await form.findElement({name: "value"}).sendKeys("15");
        await browser.executeScript(() => {
            document.querySelector("[is=listling-item] micro-datetime-input").value = "2015-08-27";
        });
        await form.findElement({css: "button:not([type])"}).click();
        await browser.wait(untilElementTextLocated({css: "[is=listling-item] h1"}, "Research"),
                           timeout);

        // Trash item
        await itemMenu.click();
        // Work around Safari 13 missing elements on click (see
        // https://bugs.webkit.org/show_bug.cgi?id=202589)
        await browser.executeScript(
            () => document.querySelector(".listling-item-trash .action").click()
        );
        await browser.wait(
            until.elementIsVisible(await browser.findElement({css: ".listling-list-trash .link"})),
            timeout
        );

        // Restore item
        await browser.executeScript(() => scroll(0, document.scrollingElement.scrollHeight));
        await browser.findElement({css: ".listling-list-trash .link"}).click();
        // Work around Safari 13 missing elements on click (see
        // https://bugs.webkit.org/show_bug.cgi?id=202589)
        await browser.executeScript(
            () => document.querySelector(".listling-list-trash .listling-item-restore").click()
        );
        await browser.wait(untilElementTextLocated({css: "[is=listling-item] h1"}, "Research"),
                           timeout);

        // Uncheck item
        await browser.executeScript(() => scroll(0, 0));
        const checkIcon = await browser.findElement({css: ".listling-item-check i"});
        await checkIcon.click();
        await browser.wait(
            untilElementAttributeMatches(checkIcon, "className", /fa-square/u), timeout
        );

        // Check item
        await checkIcon.click();
        await browser.wait(
            untilElementAttributeMatches(checkIcon, "className", /fa-check-square/u), timeout
        );

        // Assign to item
        await browser.findElement({css: ".listling-item-menu"}).click();
        await browser.findElement({css: ".listling-item-assign"}).click();
        await browser.wait(
            until.elementLocated({css: "[name=assignee] + micro-options li"}), timeout
        ).click();
        await browser.wait(
            untilElementTextLocated({css: ".listling-assign-assignees p"}, "Guest"),
            timeout
        );

        // Unassign from item
        await browser.findElement({css: ".listling-assign-remove"}).click();
        const ul = await browser.findElement({css: ".listling-assign-assignees"});
        await browser.wait(until.elementTextIs(ul, ""), timeout);
        await browser.findElement({css: ".listling-assign-close"}).click();
        // Work around Edge not firing blur event when a button gets disabled
        await browser.findElement({css: ".listling-item-menu"}).click();

        // Vote for item
        const voteButton = await browser.findElement({css: ".listling-item-vote"});
        const votesP = await browser.findElement({css: ".listling-item-votes > p"});
        await voteButton.click();
        await browser.wait(until.elementTextIs(votesP, "1"), timeout);

        // Unvote item
        await voteButton.click();
        await browser.wait(until.elementTextIs(votesP, "0"), timeout);

        // View item details
        await browser.findElement({css: "[is=listling-item]"}).click();
        const footerVisible =
            await browser.findElement({css: ".listling-item-footer"}).isDisplayed();
        expect(footerVisible).to.be.true;

        // Play list
        await browser.findElement({css: ".listling-list-play-pause"}).click();
        let item = await browser.findElement({css: "[is=listling-item]:nth-child(2)"});
        let text = await readItemPlayPause(item);
        expect(text).to.equal("Pause");

        // Play next of list
        // Work around Safari 13 missing elements on click (see
        // https://bugs.webkit.org/show_bug.cgi?id=202589)
        await browser.executeScript(
            () => document.querySelector(".listling-list-play-next").click()
        );
        item = await browser.findElement({css: "[is=listling-item]:nth-child(3)"});
        text = await readItemPlayPause(item);
        expect(text).to.equal("Pause");

        // Pause list
        // Work around Safari 13 missing elements on click (see
        // https://bugs.webkit.org/show_bug.cgi?id=202589)
        await browser.executeScript(
            () => document.querySelector(".listling-list-play-pause").click()
        );
        text = await readItemPlayPause(item);
        expect(text).to.equal("Play");

        // View presentation mode
        await browser.executeScript(() => scroll(0, 0));
        await browser.findElement({css: ".listling-list-menu"}).click();
        await browser.findElement({css: ".listling-list-enter-presentation"}).click();
        await browser.wait(until.elementLocated({css: ".listling-list-exit-presentation"}), timeout)
            .click();
        await browser.wait(until.elementIsVisible(menu), timeout);

        // View about page
        await menu.click();
        await browser.findElement({css: ".micro-ui-about"}).click();
        await browser.wait(
            untilElementTextLocated({css: "micro-about-page h1"}, "About My Open Listling"),
            timeout);
    });

    it("should work for staff", async function() {
        await getWithServiceWorker(browser, `${URL}/`);
        await browser.wait(until.elementLocated({css: "listling-intro-page"}), timeout);
        await createExampleList();

        // View activity page
        await browser.findElement({css: ".micro-ui-menu"}).click();
        await browser.findElement({css: ".micro-ui-activity"}).click();
        await browser.wait(
            untilElementTextLocated({css: "micro-activity-page .micro-timeline li"},
                                    "Project tasks"),
            timeout);
    });
});
