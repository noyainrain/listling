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

/** Analytics components. */

"use strict";

self.micro = self.micro || {};
micro.components = micro.components || {};
micro.components.analytics = {};

/**
 * Analytics page.
 *
 * .. attribute:: contentNode
 *
 *    Subclass API: Space for further content.
 */
micro.components.analytics.AnalyticsPage = class extends micro.Page {
    static make() {
        if (!ui.staff) {
            return document.createElement("micro-forbidden-page");
        }
        return document.createElement("micro-analytics-page");
    }

    createdCallback() {
        super.createdCallback();
        this.appendChild(
            document.importNode(ui.querySelector("#micro-analytics-page-template").content, true)
        );
        this._data = new micro.bind.Watchable({
            referrals: new micro.Collection("/api/stats/referrals"),
            referralsComplete: false
        });
        micro.bind.bind(this.children, this._data);

        this.contentNode = this.querySelector(".micro-analytics-content");
        this._data.referrals.events.addEventListener("fetch", () => {
            this._data.referralsComplete = this._data.referrals.complete;
        });
    }

    attachedCallback() {
        super.attachedCallback();
        const button = this.querySelector(".micro-analytics-more-referrals");
        this.ready.when(button.trigger().catch(micro.util.catch));
    }
};
document.registerElement("micro-analytics-page", micro.components.analytics.AnalyticsPage);

/**
 * Line chart showing one ore more statistics over time.
 *
 * .. describe:: --micro-chart-palette
 *
 *    Comma-Separated list with a color for each statistic.
 */
micro.components.analytics.Chart = class extends HTMLElement {
    createdCallback() {
        this.appendChild(
            document.importNode(ui.querySelector("#micro-chart-template").content, true)
        );
        this._data = new micro.bind.Watchable({alt: null});
        micro.bind.bind(this.children, this._data);
    }

    attachedCallback() {
        async function importChartjs() {
            const Chart = await micro.util.import(
                document.querySelector("link[rel=chartjs-script]").href, "Chart"
            );

            const style = getComputedStyle(document.documentElement);
            const em = parseInt(style.fontSize) * 0.875;
            const sizeXS = 0.375 * em;
            Object.assign(Chart.defaults.global, {
                maintainAspectRatio: false,
                defaultFontColor: style.getPropertyValue("--micro-color-text-subtle"),
                defaultFontFamily: "Open Sans",
                defaultFontSize: em
            });
            Chart.defaults.global.hover.animationDuration = 0;
            Chart.defaults.global.animation.duration = 0;
            Object.assign(Chart.defaults.global.legend, {
                position: "bottom",
                onClick: () => {}
            });
            Object.assign(Chart.defaults.global.legend.labels, {
                // Line height
                boxWidth: (em - 3) / Math.SQRT2,
                fontColor: style.color,
                usePointStyle: true
            });
            Object.assign(Chart.defaults.global.tooltips, {
                backgroundColor: "rgba(0, 0, 0, 0.66)",
                titleMarginBottom: sizeXS,
                xPadding: sizeXS,
                yPadding: sizeXS,
                cornerRadius: sizeXS / 2,
                displayColors: false
            });
            const scaleDefaults = {
                gridLines: {
                    color: style.getPropertyValue("--micro-color-delimiter"),
                    tickMarkLength: sizeXS,
                    zeroLineColor: style.getPropertyValue("--micro-color-delimiter")
                }
            };
            Chart.scaleService.updateScaleDefaults("linear", scaleDefaults);
            Chart.scaleService.updateScaleDefaults("time", scaleDefaults);

            return Chart;
        }

        (async() => {
            let Chart;
            let statistics;
            try {
                Chart = await importChartjs();
                statistics = await Promise.all(
                    this.statistics.map(topic => ui.call("GET", `/api/stats/statistics/${topic}`))
                );
            } catch (e) {
                ui.handleCallError(e);
                return;
            }

            const {labels} = this;
            const palette = getComputedStyle(this).getPropertyValue("--micro-chart-palette").trim()
                .split(/\s*,\s*/u);
            const datasets = statistics.map((statistic, i) => ({
                label: labels[i],
                data: statistic.items.map(p => ({t: new Date(p.t), y: p.v})),
                borderColor: palette[i],
                backgroundColor: micro.util.withAlpha(palette[i], 0.1),
                pointBackgroundColor: palette[i]
            }));

            this._chart = new Chart(this.querySelector("canvas"), {
                type: "line",
                data: {
                    datasets
                },
                options: {
                    scales: {
                        xAxes: [{
                            type: "time",
                            time: {
                                round: "day",
                                tooltipFormat: "MMM D, YYYY",
                                minUnit: "day"
                            }
                        }],
                        yAxes: [{
                            ticks: {
                                beginAtZero: true
                            }
                        }]
                    },
                    elements: {
                        point: {
                            radius: 0,
                            hitRadius: 4
                        }
                    }
                }
            });

            if (datasets[0].data.length >= 2) {
                const from = micro.bind.transforms.formatDate(
                    null, datasets[0].data[0].t, micro.bind.transforms.SHORT_DATE_FORMAT
                );
                const to = micro.bind.transforms.formatDate(
                    null, datasets[0].data[datasets[0].data.length - 1].t,
                    micro.bind.transforms.SHORT_DATE_FORMAT
                );
                const summary = datasets.map(
                    dataset => `${dataset.label}: ${dataset.data[0].y} - ${dataset.data[dataset.data.length - 1].y}`
                ).join("\n");
                this._data.alt = `Trend from ${from} to ${to}:\n${summary}`;
            }
        })().catch(micro.util.catch);
    }

    /** :class:`Array` of statistic topics to present. */
    get statistics() {
        return this.attributes.statistics.value.trim().split(/\s*,\s*/u);
    }

    /** :class:`Array` with a label for each statistic. */
    get labels() {
        return this.attributes.labels.value.trim().split(/\s*,\s*/u);
    }
};
document.registerElement("micro-chart", micro.components.analytics.Chart);
