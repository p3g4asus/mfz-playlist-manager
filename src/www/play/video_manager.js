let playlist_player = null;
let playlist_playerid = null;
let video_manager_obj = null;
let playlist_map = {};
let playlist_arr = [];
let playlists_arr = [];
let playlist_remoteplay = '';
let players_map = {};
let playlists_conf_map = {};

let playlist_play_settings_key = '';
let playlist_play_settings = {};
let playlist_item_play_settings = {};
let playlist_current = null;
let playlist_item_current = null;
let playlist_item_current_oldrowid = -2;
let playlist_item_current_wasplaying = 0;
let playlist_item_current_time_timer = null;
let playlist_item_current_idx = -1;
let playlist_item_current_duration = -1;
let playlist_current_userid = -1;
let playlist_rate = 1;
let playlist_sched = [];

function get_video_params_from_item(idx) {
    playlist_item_current = null;
    playlist_item_play_settings = {};
    let pos;
    if (idx === null) {
        playlist_rate = playlist_current.conf?.play?.rate;
        if (!playlist_rate)
            playlist_rate = 1;
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
        if (playlist_arr[pos].playlist == playlist_current.rowid) {
            playlist_item_current = playlist_arr[pos];
            playlist_item_current_idx = pos;
        } else {
            const nextpls = playlist_sched.shift();
            const plssched = [... playlist_sched];
            playlist_dump(playlist_current_userid, nextpls.name, false, playlist_arr[pos].uid);
            for (const pls of plssched) {
                playlist_dump(playlist_current_userid, pls.name, true);
            }
            return -1;
        }
    }
    let plk = false;
    const default_key = playlist_key_get_suffix(playlist_item_current, 'default');
    if (playlist_item_current && playlist_play_settings[plk = playlist_key_from_item(playlist_item_current)]) {
        playlist_item_play_settings = playlist_play_settings[plk];
        plk = JSON.stringify(playlist_item_play_settings) == JSON.stringify(playlist_play_settings[default_key]);
    }
    else if (playlist_play_settings[default_key]) {
        playlist_item_play_settings = playlist_play_settings[default_key];
        console.log('Using settings from default struct');
        plk = true;
    }
    let old_player = playlist_player;
    let old_width = video_width;
    let old_height = video_height;
    playlist_player = 'youtube';

    if (is_item_downloaded(playlist_item_current) || playlist_current.type == 'localfolder')
        playlist_player = 'html5';
    else if (playlist_current.type == 'youtube') {
        let extr;
        if (playlist_item_current) {
            if (playlist_item_current.link.indexOf('twitch.tv') >= 0)
                playlist_player = 'twitch';
            else if (playlist_item_current.conf && (extr = playlist_item_current.conf.extractor) && extr.indexOf('youtube') < 0 && extr.indexOf('twitch') < 0)
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
                playlist_map[item.playlist + '_' + item.uid] = index;
                add_video_to_button(item);
            });
            set_playlist_button_enabled(true);
        }
    }
    catch (err) {
        console.log('Error parsing playlist ' + err.message);
    }
}

function is_item_downloaded(it) {
    let idx;
    return it?.dl?.length && (idx = it.dl.lastIndexOf('/')) >= 0 && idx < it.dl.length - 1;
}

function playlist_play_current_video() {
    const vid = playlist_item_current.uid;
    const lnk = playlist_item_current.link;
    if (is_item_downloaded(playlist_item_current) || playlist_current.type == 'localfolder')
        video_manager_obj.play_video(MAIN_PATH + 'dl/' + playlist_item_current.rowid);
    /* else if (playlist_item_current.link.charAt(0) == '@')
        video_manager_obj.play_video(MAIN_PATH_S + playlist_item_current.link.substring(1));*/
    else if (vid.length && video_manager_obj.play_video_id)
        video_manager_obj.play_video_id(vid);
    else if (lnk.length && video_manager_obj.play_video)
        video_manager_obj.play_video(MAIN_PATH + 'red?link=' + encodeURIComponent(lnk), Object.assign({}, playlist_item_current.conf, {mime: playlist_item_play_settings?.mime}));
}


function on_play_finished(event) {
    let dir = event && typeof(event.dir) !== 'undefined'? event.dir:10535;
    let index;
    let vid = '';
    if (typeof(dir) == 'string') {
        if (dir != playlist_item_current.playlist + '_' + playlist_item_current.uid) {
            if (typeof(playlist_map[dir]) == 'undefined') {
                const newItem = {
                    rowid: -Math.floor(Math.random() * 1000000) - 1,
                    title: dir,
                    playlist: playlist_current.rowid,
                    uid: dir,
                    link: dir,
                    datepub: '1999-01-01 19:00:00',
                    conf: {sec: 0}
                };
                dir = (playlist_item_current_idx + 1) + '_' + dir;
                playlist_arr.splice(playlist_map[dir] = playlist_item_current_idx + 1, 0, newItem);
            }
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
            if (playlist_item_current.rowid >= 0 && ((playlist_item_play_settings?.remove_end && Date.parse(playlist_item_current.datepub) <= new Date()) || dir == 10536)) {
                let title = playlist_item_current.title;
                let cel = playlist_item_current;
                let qel = new MainWSQueueElement({cmd: CMD_SEEN, playlistitem:cel.rowid, seen:1}, function(msg) {
                    return msg.cmd === CMD_SEEN? msg:null;
                }, 5000, 1, 'seen');
                qel.enqueue().then(function(msg) {
                    if (!manage_errors(msg)) {
                        cel.conf = {};
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
    playlist_adjust_gui(index);
    vid = playlist_item_current.uid;
    playlist_item_current_duration = -1;
    playlist_play_current_video();
    save_playlist_settings(vid);
}

function playlist_adjust_gui(index) {
    console.log('Index found is ' + index);
    set_next_button_enabled(index < playlist_arr.length - 1);
    set_prev_button_enabled(index > 0);
    set_video_title(playlist_item_current.title);
    set_video_enabled(playlist_item_current.rowid);
}

function get_item_playlist_identity(pl, it)  {
    const tp = pl.type;
    if (tp == 'mediaset') {
        return 'b' + it.conf.brand + 's' + it.conf.subbrand;
    } else if (tp == 'rai') {
        return 'b' + it.conf.progid + 's' + it.conf.set;
    } else if (tp == 'youtube') {
        return it.conf.playlist;
    } else if (tp == 'local') {
        return it.link;
    } else return '';
}

function on_player_state_changed(player, event) {
    console.log('Player state changed: new ' + event);
    if (event == VIDEO_STATUS_UNSTARTED || event == VIDEO_STATUS_PAUSED || event === VIDEO_STATUS_CUED)
        set_pause_button_enabled(true, '<i class="fas fa-play"></i>&nbsp;&nbsp;Play', true);
    else if (event == VIDEO_STATUS_CANNOT_PLAY) {
        set_pause_button_enabled(true, '<i class="fas fa-play"></i>&nbsp;&nbsp;Play', true);
        if (playlist_current.conf?._drm_i.indexOf(get_item_playlist_identity(playlist_current, playlist_item_current)) >= 0) {
            if (playlist_current.type == 'mediaset') {
                let qel = new MainWSQueueElement({cmd: CMD_MEDIASET_KEYS, playlistitem:playlist_item_current.rowid, smil:'0'}, function(msg) {
                    if (msg.cmd == CMD_PING)
                        return 0;
                    return msg.cmd === CMD_MEDIASET_KEYS? msg:null;
                }, 40000, 1, 'keys');
                qel.enqueue().then(function(msg) {
                    if (!manage_errors(msg)) {
                        playlist_item_current.conf = msg.playlistitem.conf;
                        playlist_play_current_video();
                    }
                });
            }
        }
    }
    else if (event == VIDEO_STATUS_PLAYING) {
        set_pause_button_enabled(true, '<i class="fas fa-pause"></i>&nbsp;&nbsp;Pause');
        if (playlist_item_current_oldrowid !== playlist_item_current.rowid) {
            playlist_item_current_oldrowid = playlist_item_current.rowid;
            playlist_item_current_duration = video_manager_obj.duration();
            playlist_item_current_wasplaying = new Date().getTime();
            if (playlist_item_current.conf.sec) {
                video_manager_obj.currenttime(playlist_item_current.conf.sec);
                send_video_info_for_remote_play('pinfo', {sec: playlist_item_current.conf.sec});
            } else 
                send_video_info_for_remote_play('pinfo', {sec: 0});
            on_video_info_change(playlist_item_current_idx, playlist_item_current.conf.sec);
            video_manager_obj.rate(playlist_rate);
        }
        if (playlist_item_current_time_timer == null) {
            playlist_item_current_time_timer = setInterval(function() {
                let tm = video_manager_obj.currenttime();
                if (tm >= 5)
                    save_playlist_item_settings({sec: playlist_item_current.conf.sec = tm}, 'pinfo');
            }, 30000);
        }
        return;
    }
    else
        set_pause_button_enabled(false);
    if (playlist_item_current_time_timer !== null) {
        clearInterval(playlist_item_current_time_timer);
        playlist_item_current_time_timer = null;
        let tm = video_manager_obj.currenttime();
        if (tm >= 5 && new Date().getTime() - playlist_item_current_wasplaying >= 5000)
            save_playlist_item_settings({sec: tm}, 'pinfo');
    }
}

function get_video_info(idx) {
    let tot_dur = 0;
    let tot_played = 0;
    let tot_n = 0;
    let video_info = {tot_n: 0};
    for (let i = idx; i<playlist_arr.length; i++) {
        let video = playlist_arr[i];
        if (video.playlist != playlist_current.rowid) break;
        let sdur = video?.length || video?.dur || 0;
        if (i == idx && playlist_item_current) {
            sdur = Math.max(sdur, playlist_item_current_duration) / playlist_rate;
            video_info.duri = sdur;
            video_info.durs = format_duration(sdur);
            video_info.rate = playlist_rate;
            video_info.idx = idx;
            video_info.title = video?.title || 'N/A';
            video_info.chapters = video?.conf?.chapters || [];
        } else {
            sdur = sdur / playlist_rate;
            let splayed = (video?.conf?.sec || 0) / playlist_rate;
            if (splayed > sdur) splayed = sdur;
            tot_played += splayed;
        }
        tot_dur += sdur;
    }
    tot_n = playlist_arr.length - idx;
    for (const pls of playlist_sched) {
        const rate = pls.conf?.play?.rate || 1;
        const first = pls.conf?.play?.id;
        let tdur = 0;
        let tplay = 0;
        let nvid = 0;
        for (const it of pls.items) {
            if (it.uid == first) {
                tdur = 0;
                tplay = 0;
                nvid = 0;
            }
            const sdur = it?.length || it?.dur || 0;
            tdur += sdur;
            let splayed = it?.conf?.sec || 0;
            if (splayed > sdur) splayed = sdur;
            tplay += splayed;
            nvid++;
        }
        tot_n += nvid;
        tot_dur += tdur / rate;
        tot_played += tplay / rate;
    }
    video_info.tot_n = tot_n;
    video_info.tot_played = tot_played;
    video_info.tot_dur = tot_dur;
    video_info.tot_durs = format_duration(tot_dur);
    return video_info;
}

function on_video_info_change(idx, isat) {
    let video_info =  get_video_info(idx);
    if (video_info.title) {
        isat = (isat || 0) / playlist_rate;
        toast_msg('Video duration is ' + video_info.durs + ' (' + format_duration(video_info.duri - isat) +'). Remaining videos are ' + video_info.tot_n + ' [' + video_info.tot_durs +  ' (' + format_duration(video_info.tot_dur - isat - video_info.tot_played) +')] @ ' + playlist_rate.toFixed(2) + 'x.', 'info');
    }
    send_video_info_for_remote_play('vinfo', video_info);
}

function on_player_load(name, manager_obj) {
    players_map[name] = manager_obj;
    video_manager_obj = manager_obj;
    video_manager_obj.on_play_finished = on_play_finished;
    video_manager_obj.on_state_changed = on_player_state_changed;
    let event = {dir: playlist_item_current.playlist + '_' + playlist_item_current.uid};
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

// eslint-disable-next-line no-unused-vars
function go_to_video(mydir) {
    if (video_manager_obj)
        on_play_finished({dir: mydir});
}

function save_playlist_settings(vid, key) {
    if (playlist_item_current.rowid < 0) return;
    if (!key)
        key = 'playid';
    let objsource = {
        cmd: CMD_PLAYID,
        playlist: playlist_current.rowid
    };
    objsource[key] = vid;
    let el = new MainWSQueueElement(objsource, function(msg) {
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

function save_playlist_item_settings(sett, push_for_remote_play) {
    if (playlist_item_current.rowid < 0) return;
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
            if (push_for_remote_play && push_for_remote_play.length) {
                send_video_info_for_remote_play(push_for_remote_play, sett);
            }
        }
        else {
            console.log('Playlist item settings NOT saved ' + JSON.stringify(msg));
        }
    })
        .catch(function(err) {
            console.log('Playlist item settings NOT saved ' + err);
        });
}

function send_video_info_for_remote_play(w, video_info) {
    let o = {cmd: CMD_REMOTEPLAY_PUSH, what: w};
    o[w] = video_info;
    let el = new MainWSQueueElement(o, function(msg) {
        return msg.cmd === CMD_REMOTEPLAY_PUSH? msg:null;
    }, 3000, 1, w);
    return el.enqueue().then(function(msg) {
        if (!manage_errors(msg)) {
            console.log('Remoteplay push ok ' + JSON.stringify(msg.what));
        }
        else {
            console.log('Remoteplay push fail: ' + JSON.stringify(msg));
        }
        return msg;
    })
        .catch(function(err) {
            console.log('Remoteplay push fail ' + err);
            return err;
        });
}

function playlist_dump_refresh_sched() {
    for (const ppp of playlist_sched) {
        playlist_dump(playlist_current_userid, ppp.name, true);
    }
    playlist_sched.length = 0;
}

function playlist_dump(useri, plid, sched, overwrite_play_id) {
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
                    const pls = msg.playlists[0];
                    if (sched && playlist_item_current && playlist_current.name !== plid) {
                        if (playlist_sched.map(function(e) { return e.name; }).indexOf(plid) < 0) {
                            playlist_sched.push(pls);
                            const first = pls.conf?.play?.id;
                            let itemstoadd;
                            if (!first)
                                itemstoadd = pls.items;
                            else {
                                itemstoadd = [];
                                for (const it of pls.items) {
                                    if (it.uid == first)
                                        itemstoadd.length = 0;
                                    itemstoadd.push(it);
                                }
                            }
                            playlist_arr.push(...itemstoadd);
                            send_video_info_for_remote_play('ilst', playlist_arr);
                            parse_list(playlist_arr);
                            playlist_adjust_gui(playlist_item_current_idx);
                        } else playlist_dump_refresh_sched();
                        on_video_info_change(playlist_item_current_idx, video_manager_obj?.currenttime() || playlist_item_current?.conf?.sec || 0);
                        return;
                    } else if (!playlist_current || playlist_current.name != plid) {
                        playlist_sched.length = 0;
                    }
                    let playlist_has_changed = false;
                    if (playlist_current?.name != plid) {
                        if (playlist_current) {
                            playlist_item_current_oldrowid = -1;
                            playlist_has_changed = true;
                        }
                        window.history.replaceState(null, '', MAIN_PATH_S + 'play/workout.htm?name=' + plid);
                    } else if (playlist_sched.length) {
                        playlist_dump_refresh_sched();
                    }
                    playlist_current = pls;
                    if (overwrite_play_id) {
                        if (playlist_current.conf && !playlist_current.conf.play)
                            playlist_current.conf.play = {id: overwrite_play_id};
                        else if (playlist_current.conf)
                            playlist_current.conf.play.id = overwrite_play_id;
                        else
                            playlist_current.conf = {play: {id: overwrite_play_id}};
                    }
                    playlist_arr = playlist_current.items;
                    send_video_info_for_remote_play('ilst', playlist_arr);
                    parse_list(playlist_arr);
                    page_set_title(playlist_current.name);
                    if (playlist_item_current_oldrowid == -2) {
                        init_video_manager();
                        playlist_item_current_oldrowid = -1;
                    }
                    else {
                        let pos;
                        if (playlist_has_changed)
                            init_playlist_play_settings();
                        if (playlist_item_current && playlist_item_current.uid == playlist_current.conf?.play?.id && (pos = playlist_arr.map(function(e) { return e.rowid; }).indexOf(playlist_item_current.rowid)) >= 0) {
                            playlist_item_current = playlist_arr[pos];
                            playlist_item_current_idx = pos;
                            playlist_adjust_gui(playlist_item_current_idx);
                            on_video_info_change(playlist_item_current_idx, video_manager_obj.currenttime());
                        } else {
                            let vid = playlist_current.conf?.play?.id;
                            let i = 0;
                            for (let it of playlist_arr) {
                                if (it.uid == vid) {
                                    if (it.rowid == playlist_item_current_oldrowid) {
                                        if (playlist_arr.length > i + 1) {
                                            if (playlist_current.conf.play)
                                                playlist_current.conf.play.id = playlist_arr[i + 1].uid;
                                            else {
                                                playlist_current.conf = {play: {id: playlist_arr[i + 1].uid}};
                                            }
                                        } else {
                                            i = -1;
                                        }
                                    }
                                    break;
                                }
                                i++;
                            }
                            if (i >= 0) playlist_start_playing(null);
                        }
                    }
                    set_playlist_enabled(plid);
                }
                else {
                    clear_playlist_from_button();
                    add_playlist_to_button();
                    playlists_conf_map = {};
                    const gotopl = (e) => {
                        playlist_process_f5pl($(e.target).data('pls'));
                    };
                    for (let it of msg.playlists) {
                        add_playlist_to_button(it.name, null, gotopl);
                        let obj = it?.conf?.play;
                        if (obj) {
                            for (const conf of Object.keys(obj)) {
                                playlists_conf_map[conf] = true;
                            }
                        }
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

function playlist_prrocess_key(ke) {
    let dgt;
    if (ke.key == 'k' || ke.key == ' ') {
        on_play_finished({dir: null});
        ke.preventDefault();
    } else if (ke.key == 'N' && ke.shiftKey) {
        go_to_next_video();
        ke.preventDefault();
    } else if (ke.key == 'P' && ke.shiftKey) {
        go_to_prev_video();
        ke.preventDefault();
    } else if (ke.key == 'I' && ke.shiftKey) {
        playlist_process_info();
    } else if (ke.key == 'X' && ke.shiftKey) {
        on_play_finished({dir: 10536});
        ke.preventDefault();
    } else if ((dgt = /^Digit([2-9])$/.exec(ke.code)) && ke.shiftKey) {
        playlist_process_rate(1 + parseInt(dgt[1]) * 0.1);
        ke.preventDefault();
    } else if (ke.code == 'Digit0' && ke.shiftKey) {
        playlist_process_rate(2.0);
        ke.preventDefault();
    } else if (ke.code == 'Digit1' && ke.shiftKey) {
        playlist_process_rate(1.0);
        ke.preventDefault();
    } else if (ke.key == 'ArrowLeft') {
        playlist_process_rew(ke.shiftKey?30:15);
        ke.preventDefault();
    } else if (ke.key == 'ArrowDown') {
        playlist_process_rew(ke.shiftKey?90:60);
        ke.preventDefault();
    } else if (ke.key == 'ArrowRight') {
        playlist_process_ffw(ke.shiftKey?30:15);
        ke.preventDefault();
    } else if (ke.key == 'ArrowUp') {
        playlist_process_ffw(ke.shiftKey?90:60);
        ke.preventDefault();
    }
}

function playlist_process_rate(v) {
    save_playlist_settings(playlist_rate = parseFloat(v), 'playrate');
    video_manager_obj.rate(playlist_rate);
    on_video_info_change(playlist_item_current_idx, video_manager_obj.currenttime());
}

function playlist_process_info() {
    let ss;
    save_playlist_item_settings({sec: ss = video_manager_obj.currenttime()}, 'pinfo');
    on_video_info_change(playlist_item_current_idx, ss);
}

function playlist_process_rew(v) {
    video_manager_obj.rew(parseInt(v));
    save_playlist_item_settings({sec: video_manager_obj.currenttime()}, 'pinfo');
}

function playlist_process_sched(v) {
    if (video_manager_obj)
        on_play_finished({dir: v});
}

function playlist_process_item(v) {
    if (video_manager_obj)
        playlist_start_playing(v - playlist_item_current_idx);
}

function playlist_process_ffw(v) {
    video_manager_obj.ffw(parseInt(v));
    save_playlist_item_settings({sec: video_manager_obj.currenttime()}, 'pinfo');
}

function playlist_process_f5pl(pls, sched) {
    if (playlist_current) {
        playlist_dump(playlist_current_userid);
        playlist_dump(playlist_current_userid, pls.length?pls:playlist_current.name, sched && sched.toLowerCase() == 'true');
    }
}

function remotejs_recog(msg) {
    return msg.cmd === CMD_REMOTEPLAY_JS? msg:null;
}

function remotejs_process(msg) {
    remotejs_enqueue();
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
        else if (msg.sub == CMD_REMOTEPLAY_JS_RATE) {
            playlist_process_rate(msg.n);
        }
        else if (msg.sub == CMD_REMOTEPLAY_JS_F5PL) {
            playlist_process_f5pl(msg.n, msg.sched);
        }
        else if (msg.sub == CMD_REMOTEPLAY_JS_INFO) {
            playlist_process_info();
        }
        else if (msg.sub == CMD_REMOTEPLAY_JS_SEC) {
            video_manager_obj.currenttime(parseInt(msg.n));
            save_playlist_item_settings({sec: video_manager_obj.currenttime()}, 'pinfo');
        }
        else if (msg.sub == CMD_REMOTEPLAY_JS_FFW) {
            playlist_process_ffw(msg.n);
        }
        else if (msg.sub == CMD_REMOTEPLAY_JS_REW) {
            playlist_process_rew(msg.n);
        }
        else if (msg.sub == CMD_REMOTEPLAY_JS_SCHED) {
            playlist_process_sched(msg.n);
        }
        else if (msg.sub == CMD_REMOTEPLAY_JS_ITEM) {
            playlist_process_item(msg.n);
        }
        else if (msg.sub == CMD_REMOTEPLAY_JS_TELEGRAM) {
            let modvisible = is_telegram_token_visible();
            if (!modvisible && msg.act == 'start') {
                let token = generate_rand_string(5);
                let expire = new Date().getTime() + 60000;
                send_video_info_for_remote_play('token_info', {'token': token, 'exp': expire, 'username': msg.username}).then((msgrp) => {
                    if (!manage_errors(msgrp)) {
                        show_telegram_token(token, msg.username, expire - new Date().getTime());
                    }
                });
            }
            else if (modvisible && msg.act == 'finish') {
                hide_telegram_token();
            }
        }
        else if (msg.sub == CMD_REMOTEPLAY_JS_GOTO) {
            window.location.assign(msg.link);
        }
    }
    catch (e) {
        console.error(e.stack);
    }
}

function remotejs_enqueue() {
    if (!main_ws_qel_exists('remotejs')) {
        let el2 = new MainWSQueueElement(null, remotejs_recog, 0, 1, 'remotejs');
        el2.enqueue().then(remotejs_process);
    }
}

function get_remoteplay_link() {
    remotejs_enqueue();
    if (!main_ws_qel_exists('remoteplay')) {
        playlist_playerid = docCookies.getItem(COOKIE_PLAYERID + playlist_current_userid);
        let el = new MainWSQueueElement(
            {cmd: CMD_REMOTEPLAY, host: window.location.protocol + '//' + window.location.host + MAIN_PATH, sh: playlist_playerid},
            function(msg) {
                return msg.cmd === CMD_REMOTEPLAY? msg:null;
            }, 5000, 3, 'remoteplay');
        el.enqueue().then(function(msg) {
            if (!manage_errors(msg)) {
                if (!playlist_playerid) {
                    docCookies.setItem(COOKIE_PLAYERID + playlist_current_userid, playlist_playerid = msg.hex, Infinity);
                }
                playlist_remoteplay = msg.url;
                let lnk = playlist_remoteplay + '?red='+encodeURIComponent(window.location.protocol + '//' + window.location.host + MAIN_PATH_S + 'play/player_remote_commands.htm');
                const namelst = [];
                for (let it of playlists_arr) {
                    lnk += '&name='+encodeURIComponent(it.name);
                    namelst.push(it.name);
                }
                send_video_info_for_remote_play('plst', namelst);
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
                set_telegram_link(msg.telegram);
            }
        })
            .catch(function(err) {
                console.log(err);
                let errmsg = 'Exception detected: '+err;
                toast_msg(errmsg, 'danger');
            });
    }
}

// eslint-disable-next-line no-unused-vars
function get_startup_settings() {
    let orig_up = new URLSearchParams(URL_PARAMS);
    let plnames;
    if (orig_up.has('name') && (plnames = orig_up.getAll('name')).length) {
        find_user_cookie().then(function (useri) {
            main_ws_reconnect(get_remoteplay_link, WS_URL);
            playlist_current_userid = useri;
            playlist_dump(useri);
            playlist_dump(useri, plnames[0]);
            for (let i = 1; i < plnames.length; i++) {
                playlist_dump(useri, plnames[i], true);
            }
        }).catch(function() {
            manage_errors({rv: 501, err: 'Cannot find user cookie!'});
        });
    }
    else {
        manage_errors({rv: 101, err: 'Please specify a playlist name'});
    }
}

function playlist_key_get_suffix(ci, prefix) {
    return (prefix || '') + (is_item_downloaded(ci)?DOWNLOADED_SUFFIX:'');
}

function playlist_key_from_item(ci) {
    const conf = ci.conf;
    const sfx = playlist_key_get_suffix(ci);
    if (conf.playlist)
        return conf.playlist + sfx;
    else if (conf.progid)
        return conf.progid + sfx;
    else if (conf.brand && conf.subbrand)
        return '' + conf.brand + '_' + conf.subbrand + sfx;
    else
        return 'boh';
}

function playlist_rebuild_reconstruct_player() {
    playlist_rebuild_player();
    let pthis;
    if ((pthis = players_map[playlist_player])) {
        if (pthis.destroy)
            pthis.destroy();
        new pthis.constructor(video_width, video_height);
        return true;
    }
    else
        return false;
}

function playlist_start_playing(idx) {
    let rebuild = get_video_params_from_item(idx);
    if (rebuild === -1) return;
    set_save_conf_button_enabled(playlist_item_current != null);
    set_remove_button_enabled(playlist_item_current != null);
    if (playlist_item_current) {
        if (rebuild || !players_map[playlist_player]) {
            if (!playlist_rebuild_reconstruct_player())
                dyn_module_load('./' + playlist_player + '_player.js?reload=' + (new Date().getTime()));
        }
        else
            on_player_load(playlist_player, video_manager_obj);
    }
    else {
        playlist_rebuild_reconstruct_player();
        set_video_title('No video loaded');
        toast_msg('No more video in playlist', 'warning');
        on_video_info_change(playlist_item_current_idx);
    }
}

// eslint-disable-next-line no-unused-vars
function playlist_del_current_video() {
    if (playlist_item_current) {
        let cel = playlist_item_current;
        let qel = new MainWSQueueElement({cmd: CMD_SEEN, playlistitem:cel.rowid, seen:1}, function(msg) {
            return msg.cmd === CMD_SEEN? msg:null;
        }, 5000, 1, 'seen');
        qel.enqueue().then(function(msg) {
            if (!manage_errors(msg)) {
                cel.conf = {};
                toast_msg('Successfully deleted ' + cel.title + '!', 'success');
            }
        });
    }
}

// eslint-disable-next-line no-unused-vars
function playlist_reload_settings(reset) {
    //vedi nome da gui se reset falso: se nome vuoto non fare niente. Se pieno procedi
    get_conf_name(reset).then(([cname, oldv]) => {
        if (playlist_item_current && playlist_item_current.rowid >= 0) {
            oldv = !oldv?'':oldv;
            let el = new MainWSQueueElement({
                cmd: CMD_PLAYSETT,
                playlist: playlist_current.rowid,
                set: reset?'':playlist_key_from_item(playlist_item_current),
                key: cname,
                oldkey: oldv,
                playid: playlist_item_current.uid,
                default: get_default_check()?playlist_key_get_suffix(playlist_item_current, 'default'):false,
                content: (reset & 2)? null: (reset?'':{
                    width: get_spinner_value('width'),
                    height: get_spinner_value('height'),
                    remove_end: get_remove_check(),
                    mime: get_selected_mime()
                })
            }, function(msg) {
                return msg.cmd === CMD_PLAYSETT? msg:null;
            }, 3000, 1, 'playsett');
            el.enqueue().then(function(msg) {
                if (!manage_errors(msg)) {
                    //rimuovi da select se reset e setta la key a vuota
                    //aggiungi in select se non reset e non presente: setta key a nome
                    playlists_conf_map[oldv] = false;
                    playlists_conf_map[cname] = !(reset & 2);
                    fill_conf_name(playlists_conf_map, playlist_play_settings_key = (reset & 2)?'':cname);
                    playlist_current.conf.play = msg.playlist.conf.play;
                    on_conf_name_change(playlist_play_settings_key);
                }
                else {
                    toast_msg('Cannot reload playlist!! ' + playlist_current.name + ' from ' + playlist_item_current.uid , 'danger');
                }
            })
                .catch(function(err) {
                    toast_msg('Cannot reload playlist: ' + err, 'danger');
                });
        }
    });
}

function on_conf_name_change(newconf) {
    docCookies.setItem(COOKIE_PLAYSETT + playlist_current_userid, newconf, Infinity);
    playlist_play_settings_key = newconf;
    if (playlist_current.conf.play && playlist_current.conf.play[playlist_play_settings_key]) {
        playlist_play_settings = playlist_current.conf.play[playlist_play_settings_key];
    }
    else
        playlist_play_settings = {};
    restart_playing();
}

function restart_playing() {
    if (!is_pause_function_active())
        video_manager_obj.togglePause();
    playlist_item_current_oldrowid = -1;
    playlist_item_current_duration = -1;
    setTimeout(() => {playlist_start_playing(0); }, 800);
}

function init_playlist_play_settings() {
    if (playlist_current.conf.play && playlist_current.conf.play[playlist_play_settings_key]) {
        playlist_play_settings = playlist_current.conf.play[playlist_play_settings_key];
    } else {
        playlist_play_settings = {};
    }
}

function init_video_manager() {
    $(document).on('keydown', playlist_prrocess_key);
    fill_conf_name(playlists_conf_map);
    playlist_play_settings_key = docCookies.getItem(COOKIE_PLAYSETT + playlist_current_userid);
    if (!playlist_play_settings_key) {
        playlist_play_settings_key = '';
    }
    else {
        init_playlist_play_settings();
    }
    set_selected_conf_name(playlist_play_settings_key);
    playlist_start_playing(null);
}
