class YoutubePlayer {
    constructor(video_width, video_height) {
        this.player = new YT.Player('player', {
            width: video_width <= 0?'' + (-video_width) + '%':video_width,
            height: video_height <= 0?'' + (-video_height) + '%':video_height,
            videoId: 'M7lc1UVf-VE',
            events: {
                'onReady': this.onPlayerReady.bind(this),
                'onStateChange': this.onPlayerStateChange.bind(this)
            }
        });
        this.video_width = video_width;
        this.video_height = video_height;
        this.on_play_finished = null;
        this.on_state_changed = null;
        this.end_watch_timer = null;
        this.last_player_time = null;
        this.last_player_duration = 0;
        this.end_notified = false;
        this.end_check_suppressed_until = 0;
    }

    onPlayerReady(event) {
        on_player_load('youtube', this);
        this.end_watch_timer = setInterval(this.check_for_unreported_end.bind(this), 250);
    }

    
    resize(width, height) {
        if (!width) width = this.video_width;
        if (!height) height = this.video_height;
        this.player.setSize(width, height);
        this.video_width = width;
        this.video_height = height;
    }

    /*
    -1 (unstarted)
    0 (ended)
    1 (playing)
    2 (paused)
    3 (buffering)
    5 (video cued).*/
    onPlayerStateChange(event) {
        if (event.data == VIDEO_STATUS_UNSTARTED) {
            this.last_player_time = null;
            this.last_player_duration = 0;
            this.end_notified = false;
        }
        if (event.data == VIDEO_STATUS_ENDED) {
            this.finish_playback();
        }
        if (this.on_state_changed)
            this.on_state_changed(this, event.data);
    }

    finish_playback() {
        if (this.end_notified)
            return;
        this.end_notified = true;
        if (this.on_play_finished)
            this.on_play_finished(this);
    }

    check_for_unreported_end() {
        if (!this.player)
            return;
        let current_time;
        let duration;
        let state;
        try {
            current_time = this.player.getCurrentTime();
            duration = this.player.getDuration();
            state = this.player.getPlayerState();
        } catch (_) {
            return;
        }
        if (!Number.isFinite(current_time) || !Number.isFinite(duration) || duration <= 0)
            return;

        if (state === VIDEO_STATUS_ENDED) {
            this.finish_playback();
            return;
        } else if (Date.now() >= this.end_check_suppressed_until &&
                this.last_player_time !== null &&
                this.last_player_duration > 0 &&
                Math.abs(duration - this.last_player_duration) < 1 &&
                this.last_player_time >= duration - Math.max(3, Math.min(10, duration * 0.05)) &&
                current_time < 1.5) {
            // Alcuni Shorts ripartono senza notificare ENDED: prima vanno in
            // buffering e il tempo torna vicino a zero. Trattiamo il rollover
            // dalla fine all'inizio come la fine del video.
            this.finish_playback();
            return;
        }
        this.last_player_time = current_time;
        this.last_player_duration = duration;
    }

    destroy() {
        if (this.end_watch_timer) {
            clearInterval(this.end_watch_timer);
            this.end_watch_timer = null;
        }
        if (this.player && this.player.destroy)
            this.player.destroy();
        this.player = null;
    }

    rate(v) {
        this.player.setPlaybackRate(v);
    }

    play_video_id(vid) {
        if (vid.startsWith('https:')) {
            const rx = /^.*(?:(?:youtu\.be\/|v\/|vi\/|u\/\w\/|embed\/|shorts\/|live\/)|(?:(?:watch)?\?v(?:i)?=|&v(?:i)?=))([^#&?]*).*/;
            vid = vid.match(rx);
            if (!vid || !(vid = vid[1])) return;
        }
        this.last_player_time = null;
        this.last_player_duration = 0;
        this.end_notified = false;
        this.end_check_suppressed_until = 0;
        this.player.loadVideoById({videoId:vid});
    }

    currenttime(newtime) {
        if (typeof newtime == 'number')
            this.ffw_rew(newtime, true);
        else
            return this.player.getCurrentTime();
    }

    ffw_rew(secs, absolute) {
        let d = this.player.getDuration();
        let ct = absolute?secs:this.player.getCurrentTime() + secs;
        this.last_player_time = null;
        this.end_check_suppressed_until = Date.now() + 1500;
        this.player.seekTo(ct<0?0:(ct >= d?d: ct) , true);
    }

    ffw(secs) {
        this.ffw_rew(secs);
    }

    rew(secs) {
        this.ffw_rew(-secs);
    }

    duration() {
        return this.player.getDuration();
    }

    togglePause() {
        if (this.player.getPlayerState() == VIDEO_STATUS_PLAYING)
            this.player.pauseVideo();
        else
            this.player.playVideo();
    }
}

// 3. This function creates an <iframe> (and YouTube player)
//    after the API code downloads.
function onYouTubeIframeAPIReady() {
    new YoutubePlayer(video_width, video_height);
}

dyn_module_load('https://www.youtube.com/iframe_api');
