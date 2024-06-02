class Html5Player {
    constructor(video_width, video_height) {
        let $vid = $(`
            <video id="video-vid-id" controls="controls" playsinline autoplay preload="auto" style="margin-left: auto; margin-right: auto; display: block;" height="${video_height <= 0?'' + (-video_height) + '%':video_height}" width="${video_width <= 0?'' + (-video_width) + '%':video_width}">
        `);
        $('#player').append($vid);
        this.$player = $vid;
        this.player = $vid[0];
        this.$player.on('ended', this.onPlayerStateChange.bind(this));
        this.$player.on('pause', this.onPlayerStateChange.bind(this));
        this.$player.on('play', this.onPlayerStateChange.bind(this));
        this.$player.on('playing', this.onPlayerStateChange.bind(this));
        this.$player.on('stalled', this.onPlayerStateChange.bind(this));
        this.$player.on('waiting', this.onPlayerStateChange.bind(this));
        this.$player.on('error', this.onPlayerStateChange.bind(this));
        this.on_play_finished = null;
        this.on_state_changed = null;
        this.state = VIDEO_STATUS_UNSTARTED;
        on_player_load('html5', this);
    }

    /*
    -1 (unstarted)
    0 (ended)
    1 (playing)
    2 (paused)
    3 (buffering)
    5 (video cued).*/
    onPlayerStateChange(event) {
        if (event.type == 'ended' && this.on_play_finished) { // ended
            this.on_play_finished(this);
        }
        if (this.on_state_changed) {
            if (event.type == 'ended')
                this.state = VIDEO_STATUS_ENDED;
            else if (event.type == 'error' || event.type == 'abort')
                this.state = VIDEO_STATUS_UNSTARTED;
            else if (event.type == 'waiting')
                this.state = VIDEO_STATUS_BUFFERING;
            else if (!this.player.paused)
                this.state = VIDEO_STATUS_PLAYING;
            else
                this.state = VIDEO_STATUS_PAUSED;
            this.on_state_changed(this, this.state);
            console.log('New state event ' + event.type);
        }
    }

    destroy() {
        this.player.pause();
        this.player.removeAttribute('src'); // empty source
        this.player.load();
    }

    rate(v) {
        this.player.playbackRate = v;
    }

    play_video(url, typeV) {
        this.$player.attr('src', url);
        this.player.play();
    }

    togglePause() {
        if (!this.player.paused)
            this.player.pause();
        else
            this.player.play();
    }

    currenttime(newtime) {
        if (typeof newtime == 'number')
            this.player.currentTime = newtime;
        else
            return this.player.currentTime;
    }

    ffw(secs) {
        this.player.currentTime = this.player.currentTime + secs;
    }

    rew(secs) {
        this.player.currentTime = this.player.currentTime - secs;
    }
}

new Html5Player(video_width, video_height);

