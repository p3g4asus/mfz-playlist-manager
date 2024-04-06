class DashPlayer {
    constructor(video_width, video_height) {
        let $vid = $(
            `<video style="margin-left: auto; margin-right: auto; display: block;" height="${video_height <= 0?'' + (-video_height) + '%':video_height}" width="${video_width <= 0?'' + (-video_width) + '%':video_width}" controls="true" preload="auto">
        `);
        this.player = dashjs.MediaPlayer().create();
        this.player.updateSettings({ 'debug': { 'logLevel': dashjs.Debug.LOG_LEVEL_NONE }});
        this.player.on(dashjs.MediaPlayer.events['PLAYBACK_PLAYING'], this.onPlayerStateChange.bind(this));
        this.player.on(dashjs.MediaPlayer.events['PLAYBACK_ERROR'], this.onPlayerStateChange.bind(this));
        this.player.on(dashjs.MediaPlayer.events['PLAYBACK_PAUSED'], this.onPlayerStateChange.bind(this));
        this.player.on(dashjs.MediaPlayer.events['PLAYBACK_ENDED'], this.onPlayerStateChange.bind(this));
        this.player.on(dashjs.MediaPlayer.events['PLAYBACK_WAITING'], this.onPlayerStateChange.bind(this));
        this.on_play_finished = null;
        this.on_state_changed = null;
        this.first_load = true;
        this.state = VIDEO_STATUS_UNSTARTED;
        $('#player').append($vid);
        on_player_load('dash', this);
    }

    /*
    -1 (unstarted)
    0 (ended)
    1 (playing)
    2 (paused)
    3 (buffering)
    5 (video cued).*/
    onPlayerStateChange(event) {
        if (event.type == 'canPlay') {
            this.player.off(dashjs.MediaPlayer.events['CAN_PLAY'], this.onPlayerStateChange.bind(this));
            this.player.play();
        }
        else {
            if (event.type == 'playbackEnded' && this.on_play_finished) { // ended
                this.on_play_finished(this);
            }
            if (this.on_state_changed) {
                if (event.type == 'playbackEnded')
                    this.state = VIDEO_STATUS_ENDED;
                else if (event.type == 'playbackPaused')
                    this.state = VIDEO_STATUS_PAUSED;
                else if (event.type == 'playbackError')
                    this.state = VIDEO_STATUS_BUFFERING;
                else if (event.type == 'playbackWaiting')
                    this.state = VIDEO_STATUS_BUFFERING;
                else if (event.type == 'playbackPlaying')
                    this.state = VIDEO_STATUS_PLAYING;
                this.on_state_changed(this, this.state);
            }
        }
    }

    destroy() {
        this.player.reset();
    }

    play_video(url, conf) {
        if (this.first_load) {
            this.player.on(dashjs.MediaPlayer.events['CAN_PLAY'], this.onPlayerStateChange.bind(this));
            this.player.initialize();
            this.player.setAutoPlay(true);
            this.player.attachView(document.querySelector('video'));
            this.first_load = false;
        }
        let protData = null;
        if (conf._drm_m) {
            let p = conf._drm_p;
            let a = conf._drm_a;
            let t = conf._drm_t;
            url = conf._drm_m;
            const lurl = location.origin + MAIN_PATH + 'proxy?p=' + encodeURIComponent(p) + '&a=' + encodeURIComponent(a) + '&t=' + encodeURIComponent(t);
            console.log(lurl + ' ' +lurl.length);
            protData = {
                'com.widevine.alpha': {
                    'serverURL': lurl
                }
            };
        }
        this.player.setProtectionData(protData);
        this.player.attachSource(url);
        this.player.play();
    }

    togglePause() {
        if (this.state == VIDEO_STATUS_PLAYING)
            this.player.pause();
        else
            this.player.play();
    }

    currenttime(newtime) {
        if (typeof newtime == 'number')
            this.player.seek(newtime);
        else
            return this.player.time();
    }

    ffw(secs) {
        this.player.seek(this.player.time() + secs);
    }

    rew(secs) {
        this.player.seek(this.player.time() - secs);
    }
}

// dyn_module_load('./dash_sost.js', function() {

// });

dyn_module_load('https://cdn.dashjs.org/latest/dash.all.debug.js', function() {
    new DashPlayer(video_width, video_height);
});

