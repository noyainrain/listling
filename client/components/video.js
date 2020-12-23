/*
 * micro
 * Copyright (C) 2020 micro contributors
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

/** Video player. */

/* eslint-disable */

"use strict";

self.micro = self.micro || {};
micro.components = micro.components || {};

/**
 * Video player.
 *
 * .. describe:: play
 *
 *    Dispatched when the video has started to play.
 *
 * .. describe:: pause
 *
 *    Dispatched when the video has paused playing. *ended* indicates if the video is over (or an
 *    error occured).
 */
micro.components.VideoElement = class extends HTMLElement {
    createdCallback() {
        this._player = null;

        this.appendChild(
            document.importNode(document.querySelector("#micro-video-template").content, true)
        );
        this._data = new micro.bind.Watchable({
            video: null,
            state: new micro.components.VideoElement._PausedUninitialized(this),
            controlsVisible: true,
            error: null,

            playPause: () => {
                // Wait until button does not touch icon anymore
                setTimeout(() => {
                    if (this._data.state.playing) {
                        this.pause();
                    } else {
                        this.play();
                    }
                }, 0);
            },

            onClick: event => {
                if (!this.querySelector(".micro-video-controls").contains(event.target)) {
                    this._data.controlsVisible = !this._data.controlsVisible;
                }
            },

            onControlFocus: () => {
                this._data.controlsVisible = true;
            }
        });
        micro.bind.bind(this.children, this._data);
    }

    /** ref:`Video` to play. */
    get video() {
        return this._data.video;
    }

    set video(value) {
        this._data.video = value;
    }

    /** Duration of the video in seconds. */
    get duration() {
        return this._data.state.duration;
    }

    /**
     * Current position of the video in seconds.
     *
     * Set to seek to the given time.
     */
    get time() {
        return this._data.state.time;
    }

    set time(value) {
        this._data.state.time = value;
    }

    /** Indicates if the video is paused. */
    get paused() {
        return !this._data.state.playing;
    }

    /** Start playing the video. */
    play() {
        this._data.state.play();
    }

    /** Pause the video. */
    pause() {
        this._data.state.pause();
    }

    _switchPlaying() {
        this._data.controlsVisible = false;
        this.dispatchEvent(new CustomEvent("play"));
    }

    _switchPaused({ended = false} = {}) {
        this._data.controlsVisible = true;
        this.dispatchEvent(new CustomEvent("pause", {detail: {ended}}));
    }

    async _setUpPlayer() {
        function importYT() {
            if (micro.components.VideoElement._yt) {
                return micro.components.VideoElement._yt;
            }

            const p = new Promise((resolve, reject) => {
                window.onYouTubeIframeAPIReady = () => resolve(window.YT);
                micro.util.import("https://www.youtube.com/iframe_api").catch(reject);
            });

            micro.components.VideoElement._yt = p;
            p.catch(() => {
                micro.components.VideoElement._yt = null;
            });
            return p;
        }

        const createPlayer = (elem, options) => {
            const TIMEOUT = 20 * 1000;
            return new Promise((resolve, reject) => {
                const player = new YT.Player(elem, options);
                player.addEventListener("onReady", () => {
                    clearTimeout(timeout);
                    resolve(player);
                });
                // iframe doesn't dispatch error events, so handle error via timeout
                const timeout = setTimeout(() => {
                    player.destroy();
                    reject(Object.assign(new Error(), {data: 0}));
                }, TIMEOUT);
            });
        };

        await importYT();
        const videoId = new URL(this._data.video.url).searchParams.get("v");
        const div = document.createElement("div");
        this.firstElementChild.appendChild(div);
        try {
            const player = await createPlayer(
                div, {videoId, playerVars: {controls: 0, disablekb: 1}}
            );
            player.getIframe().tabIndex = -1;
            player.cleanUp = () => {
                player.destroy();
                div.remove();
            }
            return player;
        } catch (e) {
            if (e.data === 0) {
                div.remove();
                throw new micro.NetworkError(`Error loading YouTube iframe player ${videoId}`);
            }
            throw e;
        }
    }
}

micro.components.VideoElement._State = class {
    constructor(owner) {
        this.owner = owner;
    }
};

Object.assign(micro.components.VideoElement, {
    _yt: null,

    _PausedUninitialized: class extends micro.components.VideoElement._State {
        play() {
            this.owner._playerSetup = (micro.util.abortable(async signal => {
                try {
                    const player = await this.owner._setUpPlayer();
                    if (signal.aborted) {
                        player.cleanUp();
                        return;
                    }
                    this.owner._data.state.onSetUp(player);
                } catch (e) {
                    if (e instanceof micro.NetworkError) {
                        if (signal.aborted) {
                            return;
                        }
                        this.owner._data.state.onSetUpError();
                    } else {
                        throw e;
                    }
                }
            })());
            this.owner._data.error = null;
            this.owner._data.state =
                new micro.components.VideoElement._PlayingInitializing(this.owner);
            this.owner._switchPlaying();
        }

        pause() {}

        get playing() {
            return false;
        }

        get duration() {
            return 0;
        }

        get time() {
            return 0;
        }

        set time(value) {}
    },

    _PlayingInitializing: class extends micro.components.VideoElement._State {
        play() {}

        pause() {
            this.owner._playerSetup.abort();
            this.owner._data.state =
                new micro.components.VideoElement._PausedUninitialized(this.owner);
            this.owner._switchPaused();
        }

        onSetUp(player) {
            this.owner._player = player;
            this.owner._player.addEventListener("onStateChange", event => {
                if (event.data === YT.PlayerState.ENDED) {
                    this.owner._data.state.onEnd();
                }
            });
            this.owner._player.addEventListener(
                "onError", event => this.owner._data.state.onError(event.data)
            );
            this.owner._player.playVideo();
            this.owner._data.state =
                new micro.components.VideoElement._PlayingInitialized(this.owner);
        }

        onSetUpError() {
            this.owner._data.error = "Oops, there was a problem communicating with YouTube. Please try again in a few moments.";
            this.owner._data.state =
                new micro.components.VideoElement._PausedUninitialized(this.owner);
            this.owner._switchPaused({ended: true});
        }

        get playing() {
            return true;
        }

        get duration() {
            return 0;
        }

        get time() {
            return 0;
        }

        set time(value) {}
    },

    _PlayingInitialized: class extends micro.components.VideoElement._State {
        play() {}

        pause() {
            this.owner._player.pauseVideo();
            this.owner._data.state =
                new micro.components.VideoElement._PausedInitialized(this.owner);
            this.owner._switchPaused();
        }

        onEnd() {
            this.owner._player.cleanUp();
            this.owner._data.state =
                new micro.components.VideoElement._PausedUninitialized(this.owner);
            this.owner._switchPaused({ended: true});
        }

        onError(code) {
            switch (code) {
                case 5:
                    this.owner._data.error = "Oops, there was a problem communicating with YouTube! Please try again in a few moments.";
                    break;
                case 100:
                case 101:
                case 150:
                    this.owner._data.error = "Oops, the video is no longer available!";
                    break;
                default:
                    throw new Error(code);
            }
            this.owner._player.cleanUp();
            this.owner._data.state =
                new micro.components.VideoElement._PausedUninitialized(this.owner);
            this.owner._switchPaused({ended: true});
        }

        get playing() {
            return true;
        }

        get duration() {
            return this.owner._player.getDuration();
        }

        get time() {
            return this.owner._player.getCurrentTime();
        }

        set time(value) {
            this.owner._player.seekTo(value);
        }
    },

    _PausedInitialized: class extends micro.components.VideoElement._State {
        play() {
            this.owner._player.playVideo();
            this.owner._data.state =
                new micro.components.VideoElement._PlayingInitialized(this.owner);
            this.owner._switchPlaying();
        }

        pause() {}

        get playing() {
            return false;
        }

        get duration() {
            return this.owner._player.getDuration();
        }

        get time() {
            return this.owner._player.getCurrentTime();
        }

        set time(value) {
            if (value === 0) {
                this.owner._player.cleanUp();
                this.owner._data.state =
                    new micro.components.VideoElement._PausedUninitialized(this.owner);
                return;
            }
            this.owner._player.seekTo(value);
        }
    }
});
document.registerElement("micro-video", micro.components.VideoElement);
