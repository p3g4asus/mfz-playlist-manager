let playlist_player = null;
let video_manager_obj = null;
let playlist_map = {};
let playlist_arr = [];
let playlists_arr = [];
let playlist_remoteplay = '';
let players_map = {};

let playlist_play_settings_key = '';
let playlist_play_settings = {};
let playlist_item_play_settings = {};
let playlist_current = null;
let playlist_item_current = null;
let playlist_item_current_oldrowid = null;
let playlist_item_current_time_timer = null;
let playlist_item_current_idx = -1;

function get_video_params_from_item(idx) {
    playlist_item_current = null;
    playlist_item_play_settings = {};
    let pos;
    if (idx === null) {
        let vid = playlist_current.conf?.play?.id;
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
    else if (playlist_arr.length && (pos = playlist_item_current_idx + idx) < playlist_arr.length) {
        if (pos < 0)
            pos = 0;
        playlist_item_current = playlist_arr[pos];
        playlist_item_current_idx = pos;
    }
    let plk = false;
    if (playlist_item_current && playlist_play_settings[plk = playlist_key_from_item(playlist_item_current.conf)]) {
        playlist_item_play_settings = playlist_play_settings[plk];
        plk = JSON.stringify(playlist_item_play_settings) == JSON.stringify(playlist_play_settings.default);
    }
    else if (playlist_play_settings.default) {
        playlist_item_play_settings = playlist_play_settings.default;
        console.log('Using settings from default struct');
        plk = true;
    }
    let old_player = playlist_player;
    let old_width = video_width;
    let old_height = video_height;
    playlist_player = 'youtube';

    if (playlist_current.type == 'youtube') {
        let extr;
        if (playlist_item_current) {
            if (playlist_item_current.link.indexOf('twitch.tv') >= 0)
                playlist_player = 'twitch';
            else if (playlist_item_current.conf && (extr = playlist_item_current.conf.extractor) && extr != 'youtube' && extr != 'twitch')
                playlist_player = 'videojs';
        }
    }
    else if (playlist_current.type == 'mediaset')
        playlist_player = 'dash';
    else if (playlist_current.type == 'rai')
        playlist_player = 'videojs';
    console.log('Using those settings ' + JSON.stringify(playlist_item_play_settings));
    video_height = playlist_item_play_settings?.height? playlist_item_play_settings.height: 1200;    
    video_width = playlist_item_play_settings?.width? playlist_item_play_settings.width: 1880;
    set_spinner_value('width', video_width);
    set_spinner_value('height', video_height);
    set_selected_mime(playlist_item_play_settings?.mime);
    set_remove_check(playlist_item_play_settings?.remove_end?true:false);
    set_default_check(plk === true);
    return old_height != video_height || old_width != video_width || old_player != playlist_player;
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
    let dir = event && typeof(event.dir) !== 'undefined'? event.dir:10535;
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
        if (dir == 10535 || dir == 10536) {
            if (playlist_item_play_settings?.remove_end || dir == 10536) {
                let title = playlist_item_current.title;
                let qel = new MainWSQueueElement({cmd: CMD_SEEN, playlistitem:playlist_item_current.rowid, seen:1}, function(msg) {
                    return msg.cmd === CMD_SEEN? msg:null;
                }, 5000, 1, 'seen');
                qel.enqueue().then(function(msg) {
                    if (!manage_errors(msg)) {
                        console.log('Item deleted ' + title + '!');
                    }
                    else {
                        console.log('Cannot delete item ' + title + '!');
                    }
                });
            }
            dir = 1;
        }
        playlist_start_playing(dir);
        return;
    }
    let lnk = '';
    let title = '';
    console.log('Index found is ' + index);
    set_next_button_enabled(index < playlist_arr.length - 1);
    set_prev_button_enabled(index > 0);
    vid = playlist_item_current.uid;
    lnk = playlist_item_current.link;
    title = playlist_item_current.title;
    set_video_title(title);
    set_video_enabled(vid);
    let video_info =  print_duration(index);
    send_video_info_for_remote_play(video_info);
    if (vid.length && video_manager_obj.play_video_id)
        video_manager_obj.play_video_id(vid);
    else if (lnk.length && video_manager_obj.play_video)
        video_manager_obj.play_video(MAIN_PATH + 'red?link=' + encodeURIComponent(lnk), playlist_item_play_settings?.mime);
    save_playlist_settings(vid);
}

function on_player_state_changed(player, event) {
    if (event == VIDEO_STATUS_UNSTARTED || event == VIDEO_STATUS_PAUSED || event === VIDEO_STATUS_CUED)
        set_pause_button_enabled(true, '<i class="fas fa-play"></i>&nbsp;&nbsp;Play');
    else if (event == VIDEO_STATUS_PLAYING) {
        set_pause_button_enabled(true, '<i class="fas fa-pause"></i>&nbsp;&nbsp;Pause');
        if (playlist_item_current_oldrowid !== playlist_item_current.rowid && playlist_item_current.conf.sec) {
            playlist_item_current_oldrowid = playlist_item_current.rowid;
            video_manager_obj.currenttime(playlist_item_current.conf.sec);
        }
        if (playlist_item_current_time_timer == null) {
            playlist_item_current_time_timer = setInterval(function() {
                save_playlist_item_settings({sec: video_manager_obj.currenttime()});
            }, 30000);
        }
        return;
    }
    else
        set_pause_button_enabled(false);
    if (playlist_item_current_time_timer !== null) {
        clearInterval(playlist_item_current_time_timer);
        playlist_item_current_time_timer = null;
        save_playlist_item_settings({sec: video_manager_obj.currenttime()});
    }
}

function print_duration(idx) {
    let tot_dur = 0;
    let duration1 = '';
    let video_info = {tot_n: playlist_arr.length - idx};
    for (let i = idx; i<playlist_arr.length; i++) {
        let video = playlist_arr[i];
        let durationi = video?.length || video?.dur || 0;
        if (i == idx) {
            duration1 = format_duration(durationi);
            video_info.duri = durationi;
            video_info.durs = duration1;
            video_info.title = video?.title || 'N/A';
        }
        tot_dur += durationi;
    }
    if (duration1.length) {
        let tot_dur_s = format_duration(tot_dur);
        video_info.tot_dur = tot_dur;
        video_info.tot_durs = tot_dur_s;
        toast_msg('Video duration is ' + duration1 + '. Remaining videos are ' + (playlist_arr.length - idx) + ' [' + tot_dur_s + '].', 'info');
    }
    return video_info;
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
        on_play_finished({dir: 1});
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
    }, 3000, 1, 'playid');
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

function save_playlist_item_settings(sett) {
    if (!playlist_item_current.conf)
        playlist_item_current.conf = {};
    Object.assign(playlist_item_current.conf, sett);
    let el = new MainWSQueueElement({
        cmd: CMD_PLAYITSETT,
        playlistitem: playlist_item_current.rowid,
        conf: playlist_item_current.conf
    }, function(msg) {
        return msg.cmd === CMD_PLAYITSETT? msg:null;
    }, 3000, 1, 'playitsett');
    el.enqueue().then(function(msg) {
        if (!manage_errors(msg)) {
            console.log('Playlist item state saved ' + JSON.stringify(msg.playlistitem));
        }
        else {
            console.log('Playlist item settings NOT saved ' + JSON.stringify(msg));
        }
    })
        .catch(function(err) {
            console.log('Playlist item settings NOT saved ' + err);
        });
}

function send_video_info_for_remote_play(video_info) {
    let el = new MainWSQueueElement({
        cmd: CMD_REMOTEPLAY_PUSH,
        what: 'vinfo',
        vinfo: video_info
    }, function(msg) {
        return msg.cmd === CMD_REMOTEPLAY_PUSH? msg:null;
    }, 3000, 1, 'remoteplay_vinfo');
    el.enqueue().then(function(msg) {
        if (!manage_errors(msg)) {
            console.log('Remoteplay push ok ' + JSON.stringify(msg.what));
        }
        else {
            console.log('Remoteplay push fail: ' + JSON.stringify(msg));
        }
    })
        .catch(function(err) {
            console.log('Remoteplay push fail ' + err);
        });
}


function playlist_dump(useri, plid) {
    let el = new MainWSQueueElement(
        plid?{cmd: CMD_DUMP, useri:useri, name: plid}: {cmd: CMD_DUMP, useri:useri, load_all: -1},
        function(msg) {
            return msg.cmd === CMD_DUMP? msg:null;
        }, 30000, 1, 'dump ' + plid);
    el.enqueue().then(function(msg) {
        if (!manage_errors(msg)) {
            if (!msg.playlists)
                msg.playlists = [];
            if (msg.playlists.length) {
                if (plid) {
                    playlist_current = msg.playlists[0];
                    playlist_arr = playlist_current.items;
                    parse_list(playlist_arr);
                    page_set_title(playlist_current.name);
                    init_video_manager();
                    set_playlist_enabled(plid);
                }
                else {
                    add_playlist_to_button();
                    for (let it of msg.playlists) {
                        add_playlist_to_button(it.name);
                    }
                    playlists_arr = msg.playlists;
                    get_remoteplay_link();
                }
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


function remotejs_recog(msg) {
    return msg.cmd === CMD_REMOTEPLAY_JS? msg:null;
}

function remotejs_process(msg) {
    try {
        if (msg.sub == CMD_REMOTEPLAY_JS_DEL) {
            on_play_finished({dir: 10536});
        } 
        else if (msg.sub == CMD_REMOTEPLAY_JS_NEXT) {
            go_to_next_video();
        }
        else if (msg.sub == CMD_REMOTEPLAY_JS_PREV) {
            go_to_prev_video();
        }
        else if (msg.sub == CMD_REMOTEPLAY_JS_PAUSE) {
            on_play_finished({dir: null});
        }
        else if (msg.sub == CMD_REMOTEPLAY_JS_FFW) {
            video_manager_obj.ffw(parseInt(msg.n));
            save_playlist_item_settings({sec: video_manager_obj.currenttime()});
        }
        else if (msg.sub == CMD_REMOTEPLAY_JS_REW) {
            video_manager_obj.rew(parseInt(msg.n));
            save_playlist_item_settings({sec: video_manager_obj.currenttime()});
        }
        else if (msg.sub == CMD_REMOTEPLAY_JS_GOTO) {
            window.location.assign(msg.link);
        }
    }
    catch (e) {
        console.error(e.stack);
    }
    remotejs_enqueue();
}

function remotejs_enqueue() {
    let el2 = new MainWSQueueElement(null, remotejs_recog, 0, 1, 'remotejs');
    el2.enqueue().then(remotejs_process);
}

function get_remoteplay_link() {
    if (!main_ws_qel_exists('remoteplay')) {
        let el = new MainWSQueueElement(
            {cmd: CMD_REMOTEPLAY, host: window.location.protocol + '//' + window.location.host + MAIN_PATH},
            function(msg) {
                return msg.cmd === CMD_REMOTEPLAY? msg:null;
            }, 5000, 3, 'remoteplay');
        el.enqueue().then(function(msg) {
            if (!manage_errors(msg)) {
                playlist_remoteplay = msg.url;
                let lnk = playlist_remoteplay + '?red='+encodeURIComponent(window.location.protocol + '//' + window.location.host + MAIN_PATH_S + 'play/player_remote_commands.htm');
                for (let it of playlists_arr) {
                    lnk += '&name='+encodeURIComponent(it.name);
                }
                let $rpc = $('#qr-remote-play-content');
                let $a = $('<a>').prop('href', lnk).prop('target', '_blank');
                let $rp = $('<canvas>');
                $a.append($rp);
                QRCode.toCanvas($rp[0], lnk, function (error) {
                    if (error)
                        console.error('QRCODE ' + error);
                    console.log('QRCODE success!');
                });
                $rpc.empty().append($a);
                remotejs_enqueue();
            }
        })
            .catch(function(err) {
                console.log(err);
                let errmsg = 'Exception detected: '+err;
                toast_msg(errmsg, 'danger');
            });
    }
}

function get_startup_settings() {
    let orig_up = new URLSearchParams(URL_PARAMS);
    let plname;
    if (orig_up.has('name') && (plname = orig_up.get('name')).length) {
        find_user_cookie().then(function (useri) {
            main_ws_reconnect(get_remoteplay_link);
            playlist_dump(useri);
            playlist_dump(useri, plname);
        }).catch(function() {
            manage_errors({rv: 501, err: 'Cannot find user cookie!'});
        });
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
    let rebuild = get_video_params_from_item(idx);
    set_reload_button_enabled(playlist_item_current != null);
    set_remove_button_enabled(playlist_item_current != null);
    set_reset_button_enabled(playlist_item_current != null);
    if (playlist_item_current) {
        if (rebuild) {
            playlist_rebuild_player();
            let pthis;
            if ((pthis = players_map[playlist_player])) {
                if (pthis.destroy)
                    pthis.destroy();
                new pthis.constructor(video_width, video_height);
            }
            else
                dyn_module_load('./' + playlist_player + '_player.js?reload=' + (new Date().getTime()));
        }
        else
            on_player_load(playlist_player, video_manager_obj);
    }
    else {
        toast_msg('No more video in playlist', 'warning');
    }
}

function playlist_del_current_video() {
    if (playlist_item_current) {
        let qel = new MainWSQueueElement({cmd: CMD_SEEN, playlistitem:playlist_item_current.rowid, seen:1}, function(msg) {
            return msg.cmd === CMD_SEEN? msg:null;
        }, 5000, 1, 'seen');
        qel.enqueue().then(function(msg) {
            if (!manage_errors(msg)) {
                toast_msg('Successfully deleted ' + playlist_item_current.title + '!', 'success');
            }
        });
    }
}

function playlist_reload_settings(reset) {
    if (playlist_item_current) {
        let el = new MainWSQueueElement({
            cmd: CMD_PLAYSETT,
            playlist: playlist_current.rowid,
            set: reset?'':playlist_key_from_item(playlist_item_current.conf),
            key: playlist_play_settings_key,
            playid: playlist_item_current.uid,
            default: get_default_check(),
            content: reset?null: {
                width: get_spinner_value('width'),
                height: get_spinner_value('height'),
                remove_end: get_remove_check(),
                mime: get_selected_mime()
            }
        }, function(msg) {
            return msg.cmd === CMD_PLAYSETT? msg:null;
        }, 3000, 1, 'playsett');
        el.enqueue().then(function(msg) {
            if (!manage_errors(msg)) {
                playlist_current.conf.play = msg.playlist.conf.play;
                playlist_play_settings = reset?{}:msg.playlist.conf.play[playlist_play_settings_key];
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
