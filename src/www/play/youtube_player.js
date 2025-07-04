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
    }

    onPlayerReady(event) {
        on_player_load('youtube', this);
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
        if (event.data == VIDEO_STATUS_ENDED && this.on_play_finished) { // ended
            this.on_play_finished(this);
        }
        if (this.on_state_changed)
            this.on_state_changed(this, event.data);
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
