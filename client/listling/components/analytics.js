/* TODO */

"use strict";

self.listling = self.listling || {};
listling.components = listling.components || {};
listling.components.analytics = {};

/** TODO */
listling.components.analytics.AnalyticsPage = class extends micro.components.analytics.AnalyticsPage {
    static make() {
        if (!ui.staff) {
            return document.createElement("micro-forbidden-page");
        }
        return document.createElement("listling-analytics-page");
    }

    createdCallback() {
        super.createdCallback();
        this.contentNode.appendChild(
            document.importNode(ui.querySelector("#listling-analytics-page-template").content, true)
        );
    }
};

document.registerElement("listling-analytics-page", listling.components.analytics.AnalyticsPage);
