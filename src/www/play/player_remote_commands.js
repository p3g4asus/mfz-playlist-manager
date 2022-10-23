let vpc_hexcode = '';
let playlists_arr = [];

function send_remote_command(cmdo) {
    $.get(MAIN_PATH + '/rcmd/' + vpc_hexcode, cmdo, (data, status) => {
        if (cmdo.get == 'vinfo') {
            let $vd = $('#vinfo-div');
            $vd.show();
            $('#vinfo-div dd:nth-child(2)').text(data.vinfo.title);
            $('#vinfo-div dd:nth-child(4)').text(data.vinfo.durs);
            $('#vinfo-div dd:nth-child(6)').text(data.vinfo.tot_n + ' (' + data.vinfo.tot_durs + ')');
        }
        if (!data.queue)
            toast_msg('Status is ' + status +' (' + JSON.stringify(data) + ')', 'info');
        else
            toast_msg('Service unavailable now: added to operations queue (' + data.queue + ')', 'warning');
    }).fail(function(jqXHR, textStatus, errorThrown ) {
        toast_msg('Error is ' + textStatus +' (' + errorThrown + ')', 'danger');
    });
}

$(window).on('load', function() {
    let orig_up = new URLSearchParams(URL_PARAMS);
    vpc_hexcode = orig_up.get('hex');
    playlists_arr = orig_up.getAll('name');
    $('#info_button').click(()=> {
        send_remote_command({
            get: 'vinfo',
        });
    });
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
    function while_mouse_down($e) {
        let cur = $e.data('n');
        if (!cur)
            cur = 10;
        cur ++;
        $e.data('n', cur);
        $e.html($e.html().replace(/[0-9]+/, '' + cur));
    }
    function on_mouse_down(e) {
        let $e = $(e.target);
        clearTimeout($e.data('timer'));
        $e.data('timer', setInterval(() => {
            while_mouse_down($e);
        }, 100));
    }
    function on_mouse_up(e) {
        let $e = $(e.target);
        clearInterval($e.data('timer'));
        send_remote_command({
            cmd: CMD_REMOTEPLAY_JS,
            sub: $e.data('sub'),
            n: $e.data('n') || 10
        });
        $e.data('timer', setTimeout(() => {
            $e.data('n', 9);
            while_mouse_down($e);
        }, 1000));
    }
    let $b = $('#ffw_button');
    $b.data('sub', CMD_REMOTEPLAY_JS_FFW);
    $b.bind('touchend mouseup', on_mouse_up);
    $b.bind('touchstart mousedown', on_mouse_down);
    $b = $('#rew_button');
    $b.data('sub', CMD_REMOTEPLAY_JS_REW);
    $b.bind('touchend mouseup', on_mouse_up);
    $b.bind('touchstart mousedown', on_mouse_down);
    for (let it of playlists_arr) {
        add_playlist_to_button(it, '#playlist_cont', function(e) {
            send_remote_command({
                cmd: CMD_REMOTEPLAY_JS,
                sub: CMD_REMOTEPLAY_JS_GOTO,
                link: window.location.protocol + '//' + window.location.host + MAIN_PATH_S + 'play/workout.htm?name=' + encodeURIComponent(it)
            });
        });
    }
});
