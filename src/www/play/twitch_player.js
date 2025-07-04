class TwitchPlayer {
    constructor(video_width, video_height) {
        let $vid = $(
            
            `<div id="twitch-video"></div>
        `);
        let options = {
            width: video_width <= 0?'' + (-video_width) + '%':video_width,
            height: video_height <= 0?'' + (-video_height) + '%':video_height,
            autoplay: false,
            muted: false,
            channel: 'p3g4asus',
            // only needed if your site is also embedded on embed.example.com and othersite.example.com
            parent: [window.location.host]
        };
        $('#player').append($vid);
        this.on_play_finished = null;
        this.on_state_changed = null;
        this.next_channel = null;
        this.next_channel_timer = null;
        this.is_orig_channel = true;
        this.vid = TWITCH_VIDEO_ID_PRE;
        this.state = VIDEO_STATUS_UNSTARTED;
        this.embed = this.player = null;
        this.embed = new Twitch.Embed('twitch-video', options);
        this.player = this.embed.getPlayer();
        this.cur_dur = null;
        this.embed.addEventListener(Twitch.Embed.VIDEO_READY, function() {
            this.connect_embed_events();
            on_player_load('twitch', this);
        }.bind(this));
    }

    connect_embed_events() {
        let f = function(ev) {
            return function(x) {
                this.onPlayerStateChange({type: ev});
            }.bind(this);
        }.bind(this);
        let addev = function(ev) {
            this.embed.addEventListener(ev, f(ev));
        }.bind(this);
        addev(Twitch.Embed.PLAY);
        addev(Twitch.Player.ENDED);
        addev(Twitch.Player.PAUSE);
        addev(Twitch.Player.PLAYING);
        addev(Twitch.Player.PLAYBACK_BLOCKED);
        addev(Twitch.Player.OFFLINE);
    }

    resize(width, height) {
        let $v = $('#twitch-video iframe');
        if (width)
            $v.width(width);
        if (height)
            $v.height(height);
    }

    /*
    -1 (unstarted)
    0 (ended)
    1 (playing)
    2 (paused)
    3 (buffering)
    5 (video cued).*/
    onPlayerStateChange(event) {
        console.log('[twitch] state changed to ' + event.type);
        if (this.is_orig_channel) {
            clearTimeout(this.next_channel_timer);
            this.is_orig_channel = false;
            this.play_video_id(this.next_channel);
        } else {
            let ct = this.currenttime();
            console.log('[twitch] event ' + event.type + ' current time is ' + ct + ', duration is ' + this.duration() + ', cur_dur is ' + this.cur_dur + ' df is ' + (this.cur_dur - ct));
            if (((event.type == Twitch.Player.OFFLINE && !this.vid.startsWith(TWITCH_VIDEO_ID_PRE)) ||  event.type == Twitch.Player.ENDED  || (this.cur_dur > 0 && event.type == Twitch.Player.PAUSE && (this.cur_dur <= ct || (this.cur_dur - ct < 5 && this.cur_dur < this.duration())))) && this.on_play_finished) { // ended
                this.on_play_finished(this);
            }
            if (event.type == Twitch.Player.OFFLINE ||  event.type == Twitch.Player.ENDED)
                this.state = VIDEO_STATUS_ENDED;
            else if (event.type == Twitch.Player.PLAYBACK_BLOCKED || event.type == Twitch.Player.PAUSE)
                this.state = VIDEO_STATUS_PAUSED;
            else if (event.type == Twitch.Player.PLAY)
                this.state = VIDEO_STATUS_BUFFERING;
            else if (event.type == Twitch.Player.PLAYING || event.type == Twitch.Embed.PLAY) {
                if (this.cur_dur  < 0) {
                    this.cur_dur = this.player.getDuration();
                }
                this.state = VIDEO_STATUS_PLAYING;
            }
            if (this.on_state_changed) {
                this.on_state_changed(this, this.state);
            }
        }
    }

    rate(v) {
        try {
            const num = parseInt((v - 1) / 0.1 + 0.5);
            let s_all = '?id=' + encodeURIComponent('"' + document.title + '"') + '&cmd=' + CMD_REMOTEBROWSER_JS + '&sub=' + CMD_REMOTEBROWSER_JS_KEY + '&comp=g';
            for (let i = 0; i < num; i++) s_all += 'd';
            const lnk = MAIN_PATH + 'rcmd/g' + playlist_playerid + s_all;
            console.log('Getting ' + lnk);
            $.get(lnk, function( data ) {});
        }
        catch (e) {
            console.log(e);
        }
    }

    play_video_id(vid) {
        if (this.is_orig_channel) {
            this.next_channel = vid;
            this.next_channel_timer = setTimeout((() => {
                this.onPlayerStateChange(null);
            }).bind(this), 700);
        } else {
            this.vid = vid;
            this.onPlayerStateChange({type: Twitch.Player.PAUSE});
            if (vid.startsWith(TWITCH_VIDEO_ID_PRE)) {
                this.cur_dur = -1; // -1 means unknown duration
                this.player.setChannel(null);
                this.player.setVideo(vid.substring(TWITCH_VIDEO_ID_PRE.length),5);
            } else if (/^[0-9]{7,}$/i.exec(vid)) {
                this.cur_dur = -1; // -1 means unknown duration
                this.vid = TWITCH_VIDEO_ID_PRE + vid;
                this.player.setChannel(null);
                this.player.setVideo(vid, 5);
            } else {
                this.cur_dur = 0;
                this.player.setVideo(null,5);
                this.player.setChannel(vid);
            }
            setTimeout((() => {
                this.player.play();
                console.log('[twitch] play called for ' + vid);
            }).bind(this), 700);
        }
    }

    togglePause() {
        if (this.state != VIDEO_STATUS_PLAYING)
            this.player.play();
        else
            this.player.pause();
    }

    currenttime(newtime) {
        if (typeof newtime == 'number')
            this.player.seek(newtime);
        else
            return this.player.getCurrentTime();
    }

    ffw(secs) {
        this.player.seek(this.player.getCurrentTime() + secs);
    }

    rew(secs) {
        this.player.seek(this.player.getCurrentTime() - secs);
    }

    duration() {
        return this.player.getDuration();
    }
}

// dyn_module_load('./dash_sost.js', function() {

// });

dyn_module_load('https://embed.twitch.tv/embed/v1.js', function() {
    new TwitchPlayer(video_width, video_height);
});
