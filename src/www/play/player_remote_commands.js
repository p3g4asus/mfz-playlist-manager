let vpc_hexcode = '';
let playlists_arr = [];

function send_remote_command(cmdo) {
    $.get(MAIN_PATH + '/rcmd/' + vpc_hexcode, cmdo, (data, status) => {
        if (cmdo.get) {
            if (data.vinfo || data.pinfo) {
                let $vd = $('#vinfo-div');
                $vd.show();
                if (data.vinfo) {
                    $('#vinfo-div dd:nth-child(2)').text(data.vinfo.title);
                    $('#vinfo-div dd:nth-child(4)').text(data.vinfo.durs);
                    $('#vinfo-div dd:nth-child(6)').text(data.vinfo.tot_n + ' (' + data.vinfo.tot_durs + ')');
                    const $tb = $('#vinfo-div dl');
                    const clickfn = (e) => {
                        const $e = $(e.target);
                        const v = $e.data('timer');
                        send_remote_command({
                            cmd: CMD_REMOTEPLAY_JS,
                            sub: CMD_REMOTEPLAY_JS_SEC,
                            n: v
                        });
                        return false;
                    };
                    $('#vinfo-div dd.chapter-sect, #vinfo-div dt.chapter-sect').remove();
                    for (let ch of data.vinfo.chapters) {
                        const $a0 = $('<a />');
                        const tm = parseInt(ch.start_time);
                        $a0.prop('href','#').data('timer', tm).text(ch.title).on('click', clickfn);
                        const $ch0 = $('<dt class="col-sm-3 chapter-sect"></dt>').text(format_duration(tm));
                        const $ch1 = $('<dd class="col-sm-9 chapter-sect"></dd>').append($a0);
                        $tb.append($ch0);
                        $tb.append($ch1);
                    }
                }
                if (data.pinfo) {
                    $('#vinfo-div dt:nth-child(7)').text(format_duration(Math.round(data.pinfo.sec)));
                    $('#pinfo-range').prop('max', data.vinfo.duri).val(data.pinfo.sec);
                }
                else {
                    $('#vinfo-div dt:nth-child(7)').text(format_duration(0));
                    $('#pinfo-range').prop('max', data.vinfo.duri).val(0);
                }
            }
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
    $(document).on('visibilitychange', ()=> {
        if (!document.hidden && $('#vinfo-div').is(':visible')) {
            $('#info_button').click();
        }
    });
    $('#info_button').click(()=> {
        send_remote_command({
            'get': ['vinfo', 'pinfo'],
        });
    });
    $('#collapse_button').click(()=> {
        let $vd = $('#vinfo-div');
        $vd.toggle();
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
    let $rng = $('#pinfo-range');
    $rng.on('input', () => {
        let v = $rng.val();
        $('#vinfo-div dt:nth-child(7)').text(format_duration(v));
    });
    $rng.on('change', () => {
        let v = $rng.val();
        send_remote_command({
            cmd: CMD_REMOTEPLAY_JS,
            sub: CMD_REMOTEPLAY_JS_SEC,
            n: v
        });
        $('#vinfo-div dt:nth-child(7)').text(format_duration(v));
    });
    function while_rwfw_mouse_down($e) {
        let cur = $e.data('n');
        if (!cur)
            cur = 10;
        cur ++;
        $e.data('n', cur);
        $e.html($e.html().replace(/[0-9]+/, '' + cur));
    }
    function on_rwfw_mouse_down(e) {
        let $e = $(e.target);
        $e.data('timer', setInterval(() => {
            while_rwfw_mouse_down($e);
        }, 100));
    }
    function on_rwfw_mouse_up(e) {
        let $e = $(e.target);
        clearInterval($e.data('timer'));
        send_remote_command({
            cmd: CMD_REMOTEPLAY_JS,
            sub: $e.data('sub'),
            n: $e.data('n') || 10
        });
        $e.data('timer', setTimeout(() => {
            $e.data('n', 9);
            while_rwfw_mouse_down($e);
            $e.removeData('timer');
        }, 1000));
    }
    function on_rwfw_click(e) {
        let $e = $(e.target);
        let tim = $e.data('timer');
        if (typeof(tim) == 'undefined')
            on_rwfw_mouse_down(e);
        else
            on_rwfw_mouse_up(e);
    }
    let $b = $('#ffw_button');
    $b.data('sub', CMD_REMOTEPLAY_JS_FFW);
    $b.click(on_rwfw_click);
    $b = $('#rew_button');
    $b.data('sub', CMD_REMOTEPLAY_JS_REW);
    $b.click(on_rwfw_click);
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
