let playlist_player = null;
let video_manager_obj = null;
let playlist_map = {};
let playlist_arr = [];
let players_map = {};

let playlist_play_settings_key = '';
let playlist_play_settings = {};
let playlist_item_play_settings = {};
let playlist_current = null;
let playlist_item_current = null;
let playlist_item_current_idx = -1;

function get_video_params_from_item(idx) {
    let vid = null;
    playlist_item_current = null;
    playlist_item_play_settings = {};
    playlist_item_current_idx = -1;
    if (idx === null) {
        vid = playlist_current.conf?.play?.id;
        if (!vid || !vid.length) {
            if (!playlist_arr.length)
                vid = 'wP6l4MD1tTc';
            else
                vid = playlist_arr[0].uid;
        }
        let i = 0;
        for (let it of playlist_arr) {
            if (it.uid == vid) {
                playlist_item_current = it;
                playlist_item_current_idx = i;
                break;
            }
            i++;
        }
        if (playlist_arr.length && !playlist_item_current)
            playlist_item_current = playlist_arr[playlist_item_current_idx = 0];
    }
    else if (playlist_arr.length) {
        let pos = playlist_item_current_idx + idx;
        if (pos >= playlist_arr.length)
            pos = playlist_arr.length - 1;
        else if (pos < 0)
            pos = 0;
        playlist_item_current = playlist_arr[pos];
        playlist_item_current_idx = pos;
    }
    let plk;
    if (playlist_item_current && playlist_play_settings[plk = playlist_key_from_item(playlist_item_current.conf)])
        playlist_item_play_settings = playlist_play_settings[plk];
    else if (playlist_play_settings.default)
        playlist_item_play_settings = playlist_play_settings.default;
    playlist_player = 'youtube';

    if (playlist_current.type == 'youtube') {
        if (playlist_item_current) {
            if (playlist_item_current.link.indexOf('twitch.tv') >= 0)
                playlist_player = 'twitch';
        }
    }
    else if (playlist_current.type == 'mediaset')
        playlist_player = 'dash';
    else if (playlist_current.type == 'rai')
        playlist_player = 'videojs';
    video_height = playlist_item_play_settings?.height? playlist_item_play_settings.height: 1200;    
    video_width = playlist_item_play_settings?.width? playlist_item_play_settings.width: 1880;
    set_spinner_value('width', video_width);
    set_spinner_value('height', video_height);
}

function parse_list(json_list) {
    try {
        playlist_map = {};
        clear_playlist();
        if (json_list) {
            json_list.forEach(function(item, index) {
                playlist_map[item.uid] = index;
                add_video_to_button(item);
            });
            set_playlist_button_enabled(true);
        }
    }
    catch (err) {
        console.log('Error parsing playlist ' + err.message);
    }
}


function on_play_finished(event) {
    let dir = event && typeof(event.dir) !== 'undefined'? event.dir:1;
    let index;
    let vid = '';
    if (typeof(dir) == 'string') {
        if (dir != playlist_item_current.uid) {
            playlist_start_playing(playlist_map[dir] - playlist_item_current_idx);
            return;
        }
        else {
            index = playlist_map[dir];
        }
    }
    else if (dir === null) {
        video_manager_obj.togglePause();
        return;
    }
    else {
        playlist_start_playing(dir);
        return;
    }
    let lnk = '';
    let title = '';
    console.log('Index found is ' + index);
    if (index < playlist_arr.length) {
        set_next_button_enabled(index < playlist_arr.length - 1);
        set_prev_button_enabled(index > 0);
        vid = playlist_item_current.uid;
        lnk = playlist_item_current.link;
        title = playlist_item_current.title;
        set_video_title(title);
        set_video_enabled(vid);
        print_duration(index);
    }
    if (vid.length && video_manager_obj.play_video_id)
        video_manager_obj.play_video_id(vid);
    else if (lnk.length && video_manager_obj.play_video)
        video_manager_obj.play_video(MAIN_PATH + 'red?link=' + encodeURIComponent(lnk));

    save_playlist_settings(vid);
}

function on_player_state_changed(player, event) {
    if (event == VIDEO_STATUS_UNSTARTED || event == VIDEO_STATUS_PAUSED || event === VIDEO_STATUS_CUED)
        set_pause_button_enabled(true, '<i class="fas fa-play"></i>&nbsp;&nbsp;Play');
    else if (event == VIDEO_STATUS_PLAYING)
        set_pause_button_enabled(true, '<i class="fas fa-pause"></i>&nbsp;&nbsp;Pause');
    else
        set_pause_button_enabled(false);
}

function print_duration(idx) {
    let tot_dur = 0;
    let duration1 = '';
    for (let i = idx; i<playlist_arr.length; i++) {
        let video = playlist_arr[i];
        let durationi = video?.length || video?.dur || 0;
        if (i == idx) {
            duration1 = format_duration(durationi);
        }
        tot_dur += durationi;
    }
    if (duration1.length) {
        toast_msg('Video duration is ' + duration1 + '. Remaining videos are ' + (playlist_arr.length - idx) + ' [' + format_duration(tot_dur) + '].', 'info');
    }
}

function on_player_load(name, manager_obj) {
    players_map[name] = manager_obj;
    video_manager_obj = manager_obj;
    video_manager_obj.on_play_finished = on_play_finished;
    video_manager_obj.on_state_changed = on_player_state_changed;
    let event = {dir: playlist_item_current.uid};
    on_play_finished(event);
}

function go_to_next_video() {
    if (video_manager_obj)
        on_play_finished(null);
}
function go_to_prev_video() {
    if (video_manager_obj)
        on_play_finished({dir: -1});
}

function go_to_video(mydir) {
    if (video_manager_obj)
        on_play_finished({dir: mydir});
}

function save_playlist_settings(vid) {
    let el = new MainWSQueueElement({
        cmd: CMD_PLAYID,
        playlist: playlist_current.rowid,
        playid: vid
    }, function(msg) {
        return msg.cmd === CMD_PLAYID? msg:null;
    }, 3000, 1);
    el.enqueue().then(function(msg) {
        if (!manage_errors(msg)) {
            console.log('Playlist state saved ' + JSON.stringify(msg.playlistitem));
        }
        else {
            console.log('Settings NOT saved ' + JSON.stringify(msg));
        }
    })
        .catch(function(err) {
            console.log('Settings NOT saved ' + err);
        });
}


function playlist_dump(plid) {
    let useri = find_user_cookie();
    let el = new MainWSQueueElement({cmd: CMD_DUMP, useri:useri, name: plid}, function(msg) {
        return msg.cmd === CMD_DUMP? msg:null;
    }, 30000, 1);
    el.enqueue().then(function(msg) {
        if (!manage_errors(msg)) {
            if (msg.playlists.length) {
                playlist_current = msg.playlists[0];
                playlist_arr = playlist_current.items;
                parse_list(playlist_arr);
                page_set_title(playlist_current.name);
                init_video_manager();
            }
            else {
                manage_errors({rv: 102, err: 'Playlist '+ plid +' not found!'});
            }
        }
    })
        .catch(function(err) {
            console.log(err);
            let errmsg = 'Exception detected: '+err;
            toast_msg(errmsg, 'danger');
        });
}

function get_startup_settings() {
    let orig_up = new URLSearchParams(URL_PARAMS);
    let plname;
    main_ws_reconnect();
    if (orig_up.has('name') && (plname = orig_up.get('name')).length) {
        playlist_dump(plname);
    }
    else {
        manage_errors({rv: 101, err: 'Please specify a playlist name'});
    }
}

function playlist_key_from_item(conf) {
    if (conf.playlist)
        return conf.playlist;
    else if (conf.progid)
        return playlist_item_current.conf.progid;
    else if (conf.brand && conf.subbrand)
        return '' + conf.brand + '_' + conf.subbrand;
    else
        return 'boh';
}

function playlist_start_playing(idx) {
    get_video_params_from_item(idx);
    set_reload_button_enabled(playlist_item_current != null);
    if (playlist_item_current) {
        $('#player-content').empty();
        $('#player-content').append($('<div class="col-12" id="player">'));
        let pthis;
        if ((pthis = players_map[playlist_player])) {
            if (pthis.destroy)
                pthis.destroy();
            new pthis.constructor(video_width, video_height);
        }
        else
            dyn_module_load('./' + playlist_player + '_player.js');
    }
    else {
        toast_msg('No more video in playlist', 'warning');
    }
}

function playlist_reload() {
    if (playlist_item_current) {
        let el = new MainWSQueueElement({
            cmd: CMD_PLAYSETT,
            playlist: playlist_current.rowid,
            set: playlist_key_from_item(playlist_item_current.conf),
            key: playlist_play_settings_key,
            playid: playlist_item_current.uid,
            default: get_default_check(),
            content: {
                width: get_spinner_value('width'),
                height: get_spinner_value('height')
            }
        }, function(msg) {
            return msg.cmd === CMD_PLAYSETT? msg:null;
        }, 3000, 1);
        el.enqueue().then(function(msg) {
            if (!manage_errors(msg)) {
                playlist_current.conf.play = msg.playlist.conf.play;
                playlist_play_settings = msg.playlist.conf.play[playlist_play_settings_key];
                playlist_start_playing(0);
            }
            else {
                toast_msg('Cannot reload playlist!! ' + playlist_current.name + ' from ' + playlist_item_current.uid , 'danger');
            }
        })
            .catch(function(err) {
                toast_msg('Cannot reload playlist: ' + err, 'danger');
            });
    }
}

function init_video_manager() {
    playlist_play_settings_key = docCookies.getItem(COOKIE_PLAYSETT);
    if (!playlist_play_settings_key) {
        playlist_play_settings_key = generate_rand_string(16);
        docCookies.setItem(COOKIE_PLAYSETT, playlist_play_settings_key, Infinity);
    }
    else {
        if (playlist_current.conf.play && playlist_current.conf.play[playlist_play_settings_key])
            playlist_play_settings = playlist_current.conf.play[playlist_play_settings_key];
    }
    playlist_start_playing(null);
}
