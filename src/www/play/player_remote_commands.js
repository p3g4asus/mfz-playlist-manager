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
            sub: 'next',
        });
    });
    $('#pause_button').click(()=> {
        send_remote_command({
            cmd: CMD_REMOTEPLAY_JS,
            sub: 'pause',
        });
    });
    $('#del_button').click(()=> {
        send_remote_command({
            cmd: CMD_REMOTEPLAY_JS,
            sub: 'nextdel',
        });
    });
    $('#prev_button').click(()=> {
        send_remote_command({
            cmd: CMD_REMOTEPLAY_JS,
            sub: 'prev',
        });
    });
    for (let it of playlists_arr) {
        add_playlist_to_button(it, '#playlist_cont', function(e) {
            send_remote_command({
                cmd: CMD_REMOTEPLAY_JS,
                sub: 'goto',
                link: window.location.protocol + '//' + window.location.host + '/' + MAIN_PATH_S + 'play/workout.htm?name=' + encodeURIComponent(it)
            });
        });
    }
});
