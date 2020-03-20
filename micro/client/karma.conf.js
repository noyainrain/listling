/* eslint-env node */

"use strict";

module.exports = function(config) {
    let tag = process.env.SUBJECT ? ` [${process.env.SUBJECT}]` : "";
    config.set({
        frameworks: ["mocha"],
        files: [
            "node_modules/webcomponents.js/webcomponents-lite.min.js",
            "node_modules/event-source-polyfill/src/eventsource.min.js",
            "node_modules/chai/chai.js",
            "bind.js",
            "keyboard.js",
            "util.js",
            "index.js",
            "components/contextual.js",
            "components/stats.js",
            "!(node_modules)/**/test*.js",
            {pattern: "templates.html", type: "dom"}
        ],
        sauceLabs: {
            testName: `[micro]${tag} Unit tests`
        },
        customLaunchers: {
            "sauce-chrome": {
                base: "SauceLabs",
                browserName: "chrome",
                platform: "Windows 10"
            },
            "sauce-edge": {
                base: "SauceLabs",
                browserName: "MicrosoftEdge",
                platform: "Windows 10"
            },
            "sauce-firefox": {
                base: "SauceLabs",
                browserName: "firefox",
                platform: "Windows 10"
            },
            "sauce-safari": {
                base: "SauceLabs",
                browserName: "safari",
                platform: "macOS 10.13"
            }
        },
        browsers: ["FirefoxHeadless"]
    });
};
