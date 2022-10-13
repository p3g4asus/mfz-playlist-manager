let vpc_hexcode = '';
let playlists_arr = [];

function send_remote_command(cmdo) {
    $.get(MAIN_PATH + '/rcmd/' + vpc_hexcode, cmdo, (data, status) => {
        toast_msg('Status is ' + status +' (' + JSON.stringify(data) + ')', 'info');
    });
}

$(window).on('load', function() {
    let orig_up = new URLSearchParams(URL_PARAMS);
    vpc_hexcode = orig_up.get('hex');
    playlists_arr = orig_up.getAll('name');
    $('#next_button').click(()=> {
        send_remote_command({
            cmd: CMD_REMOTEPLAY_JS,
            sub: CMD_REMOTEPLAY_JS_NEXT,
        });
    });
    $('#pause_button').click(()=> {
        send_remote_command({
            cmd: CMD_REMOTEPLAY_JS,
            sub: CMD_REMOTEPLAY_JS_PAUSE,
        });
    });
    $('#del_button').click(()=> {
        send_remote_command({
            cmd: CMD_REMOTEPLAY_JS,
            sub: CMD_REMOTEPLAY_JS_DEL,
        });
    });
    $('#prev_button').click(()=> {
        send_remote_command({
            cmd: CMD_REMOTEPLAY_JS,
            sub: CMD_REMOTEPLAY_JS_PREV,
        });
    });
    $('#ffw_button').click(()=> {
        send_remote_command({
            cmd: CMD_REMOTEPLAY_JS,
            sub: CMD_REMOTEPLAY_JS_FFW,
            n: 10
        });
    });
    $('#rew_button').click(()=> {
        send_remote_command({
            cmd: CMD_REMOTEPLAY_JS,
            sub: CMD_REMOTEPLAY_JS_REW,
            n: 10
        });
    });
    for (let it of playlists_arr) {
        add_playlist_to_button(it, '#playlist_cont', function(e) {
            send_remote_command({
                cmd: CMD_REMOTEPLAY_JS,
                sub: CMD_REMOTEPLAY_JS_GOTO,
                link: window.location.protocol + '//' + window.location.host + '/' + MAIN_PATH_S + 'play/workout.htm?name=' + encodeURIComponent(it)
            });
        });
    }
});
