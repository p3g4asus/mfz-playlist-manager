function button_video(el, idx) {
    if (!$(el).hasClass('disabled'))
        go_to_video(idx);
}

function clear_playlist() {
    $('#playlist_items_cont > .dropdown-menu').empty();
}

function add_video_to_button(item) {
    let li = $('<li>');
    let a = $('<a>');
    a.attr('href', '#');
    a.addClass('dropdown-item');
    a.attr('data-uid', item.uid);
    a.text(item.title);
    a.click(function (e) {
        go_to_video(item.uid);
    });
    li.append(a);
    $('#playlist_items_cont > .dropdown-menu').append(li);
}

function set_playlist_button_enabled(enabled) {
    if (!enabled)
        $('#playlist_items').addClass('disabled');
    else
        $('#playlist_items').removeClass('disabled');
}

function remove_playlist_button() {
    $('#playlist_items_cont').remove();
}

function is_pause_function_active() {
    let $pb = $('#pause_button');
    return !$pb.hasClass('disabled') && $pb.data('pause') ;
}

function set_pause_button_enabled(enabled, txt, pause) {
    let $pb = $('#pause_button');
    if (!enabled)
        $pb.addClass('disabled');
    else
        $pb.removeClass('disabled');
    if (txt)
        $pb.html(txt);
    $pb.data('pause', pause?true:false);
}

function set_prev_button_enabled(enabled) {
    if (!enabled)
        $('#prev_button').addClass('disabled');
    else
        $('#prev_button').removeClass('disabled');
}

function set_next_button_enabled(enabled) {
    if (!enabled)
        $('#next_button').addClass('disabled');
    else
        $('#next_button').removeClass('disabled');
}

function set_reload_button_enabled(enabled) {
    if (!enabled)
        $('#reload_button').addClass('disabled');
    else
        $('#reload_button').removeClass('disabled');
}

function set_remove_button_enabled(enabled) {
    if (!enabled)
        $('#remove_button').addClass('disabled');
    else
        $('#remove_button').removeClass('disabled');
}

function set_reset_button_enabled(enabled) {
    if (!enabled)
        $('#reset_button').addClass('disabled');
    else
        $('#reset_button').removeClass('disabled');
}

function set_video_title(title) {
    $('#video_title').text(title);
}

function set_video_enabled(uid) {
    $('#playlist_items_cont > .dropdown-menu a').removeClass('active');
    $('#playlist_items_cont > .dropdown-menu a[data-uid=\'' + uid + '\']').addClass('active');
}

function set_playlist_enabled(uid) {
    $('#playlist_cont > .dropdown-menu a').removeClass('active');
    $('#playlist_cont > .dropdown-menu a[data-pls=\'' + uid + '\']').addClass('active');
}

function playlist_rebuild_player() {
    $('#player-content').empty();
    $('#player-content').append($('<div class="col-12" id="player">'));
}

function page_set_title(title) {
    $(document).prop('title', title);
}

function set_spinner_value(type, val) {
    $('#video-' + type).val(val);
}

function set_selected_mime(type) {
    if (!type || !$('#mime-type option[value="' + type +'"]').length)
        type = $('#mime-type option:first-child').prop('value');
    $('#mime-type').val(type);
}

function get_selected_mime() {
    return $('#mime-type').val();
}

function get_spinner_value(type) {
    return parseInt($('#video-' + type).val());
}

function get_default_check() {
    return $('#default-sett').is(':checked');
}

function get_remove_check() {
    return $('#remove-end').is(':checked');
}

function set_remove_check(v) {
    return $('#remove-end').prop('checked', v);
}

function set_default_check(v) {
    return $('#default-sett').prop('checked', v);
}

function fill_conf_name(obj, sel) {
    let $cname = $('#configuration-name');
    $cname.find('option[value!=""]').remove();
    if (obj) {
        let sel2 = null;
        for (const conf of Object.keys(obj)) {
            if (conf != 'id') {
                $cname.append($('<option>').prop('value', conf).text(conf));
                if (conf == sel)
                    sel2 = sel;
            }
        }
        sel = sel2;
        if (!sel)
            sel = '';
    }
    else
        sel = '';
    set_selected_conf_name(sel);
}

function get_selected_conf_name() {
    let v = $('#configuration-name').find('option:selected').val();
    return v;
}

function get_conf_name(reset) {
    let cnames = get_selected_conf_name(), prom;
    if (reset && !cnames.length)
        prom = Promise.reject();
    else if ((!reset && cnames.length) || (reset && cnames.length))
        prom = Promise.resolve(cnames);
    else {
        let resok, resko;
        prom = new Promise(function(resolve, reject) {
            resok = resolve;
            resko = reject;
        });
        let $modal = $('#configuration-name-modal');
        let modbs = bootstrap.Modal.getOrCreateInstance($modal[0]);
        $modal.off('hidden.bs.modal').on('hidden.bs.modal', () => {
            resko();
            modbs.dispose();
        });
        $modal.off('shown.bs.modal').on('shown.bs.modal', function (event) {
            let $bok = $('#configuration-name-modal-ok');
            $bok.click(() => {
                let $form = $modal.find('form');
                if ($form[0].checkValidity()) {
                    $modal.off('hidden.bs.modal').on('hidden.bs.modal', () => {
                        resok($('#configuration-name-input').val());
                        modbs.dispose();
                    });
                    modbs.hide();
                }
                $form.addClass('was-validated');
            });
        });
        modbs.show();
    }
    return prom;
}

function set_selected_conf_name(name) {
    $('#configuration-name option[value="' + name +'"]').prop('selected','selected');
    conf_button_enable();
}

function conf_button_enable(selval) {
    if (typeof selval == 'undefined') {
        selval = get_selected_conf_name();
    }
    if (!selval.length) {
        $('#remove_button').addClass('disabled');
        $('#reset_button').addClass('disabled');
    }
    else {
        $('#remove_button').removeClass('disabled');
        $('#reset_button').removeClass('disabled');
    }
}

$(window).on('load', function() {
    $('#video-width').inputSpinner();
    $('#video-height').inputSpinner();
    let $cname = $('#configuration-name');
    $cname.on('change', () => {
        let selval = get_selected_conf_name();
        on_conf_name_change(selval);
        conf_button_enable(selval);
    });
    get_startup_settings();
});
