let selected_playlist = null;
let playlists_all = [];
let playlist_selected_del_tmr = -1;
let playlist_selected_del_cnt = 5;

function set_button_enabled(btn, enabled) {
    let b = $(btn);
    if (b.prop('tagName') == 'A') {
        if (!enabled)
            b.addClass('disabled');
        else
            b.removeClass('disabled');
    }
    else {
        b.prop('disabled', !enabled);
    }
}

function  playlist_selected_del_restore($ev) {
    $ev.html('<p class="h1"><i class="fas fa-trash-alt"></i></p>');
    $ev.closest('.container-fluid').find('.pl-item-func-iorder').show();
    $ev.removeAttr('data-timer');
}

function playlist_selected_del_tmr_fun() {
    playlist_selected_del_cnt--;
    let waiting_del = $('.pl-item-func-seen').children('a[data-timer]');
    if (playlist_selected_del_cnt) {
        waiting_del.html('<p class="h1"><i class="fas fa-trash-restore"></i>&nbsp;&nbsp;&nbsp;'+ playlist_selected_del_cnt +'</p>');
        playlist_selected_del_tmr = setTimeout(playlist_selected_del_tmr_fun, 1000);
    }
    else {
        playlist_selected_del_restore(waiting_del);
        playlist_selected_del_cnt = 5;
        playlist_selected_del_tmr = -1;
        let lids = [];
        waiting_del.each(function() {
            lids.push(parseInt($(this).data('rowid')));
        });
        let qel = new MainWSQueueElement({cmd: CMD_SEEN, playlistitem:lids, seen:1}, function(msg) {
            return msg.cmd === CMD_SEEN? msg:null;
        }, 20000, 1);
        qel.enqueue().then(function(msg) {
            if (!manage_errors(msg)) {
                let $plitemsTable = $('#playlist-items-table');
                for (let rid of lids) {
                    let row = $plitemsTable.bootstrapTable('getRowByUniqueId', rid);
                    toast_msg('Playlist item ' + row.title+' removed', 'success');
                    $plitemsTable.bootstrapTable('removeByUniqueId', rid);
                    bootstrap_table_pagination_fix();
                    selected_playlist.items.splice(selected_playlist.items.map(function(e) { return e.rowid; }).indexOf(rid), 1);
                }
                playlist_update_in_list(selected_playlist);
            }
        })
            .catch(function(err) {
                console.log(err);
                let errmsg = 'Exception detected: '+err;
                toast_msg(errmsg, 'danger');
            });
        
    }

}

function playlist_item_seen(ev) {
    let $ev = $(ev);
    let tmr = $ev.attr('data-timer');
    playlist_selected_del_cnt = 5;
    let waiting_del = $('.pl-item-func-seen').children('a[data-timer]');
    if (tmr) {
        if (waiting_del.length == 1 && playlist_selected_del_tmr>=0) {
            clearTimeout(playlist_selected_del_tmr);
            playlist_selected_del_tmr = -1;
        }
        playlist_selected_del_restore($ev);
    }
    else {
        if (!waiting_del.length) {
            playlist_selected_del_tmr = setTimeout(playlist_selected_del_tmr_fun, 1000);
        }
        $ev.html('<p class="h1"><i class="fas fa-trash-restore"></i>&nbsp;&nbsp;&nbsp;5</p>');
        $ev.closest('.container-fluid').find('.pl-item-func').hide();
        $ev.attr('data-timer', 1);
    }
}

function playlist_item_move(ev) {
    let $ev = $(ev);
    let $iorder = $ev.closest('.container-fluid').find('.pl-item-func-iorder-sec');
    if ($iorder.is(':visible')) {
        $iorder.hide();
    }
    else {
        let $input = $iorder.children('input');
        let $btn = $iorder.children('a');
        $iorder.show();
        $input.val($ev.text());
        $input.change(function() {
            let nn = parseInt($(this).val());
            set_button_enabled($btn, !isNaN(nn));
        });
        $btn.click(function() {
            $iorder.hide();
            let rid = $btn.data('rowid');
            let qel = new MainWSQueueElement({cmd: CMD_IORDER, playlistitem:parseInt(rid), iorder:parseInt($input.val())}, function(msg) {
                return msg.cmd === CMD_IORDER? msg:null;
            }, 20000, 1);
            qel.enqueue().then(function(msg) {
                if (!manage_errors(msg)) {
                    playlist_dump(selected_playlist.rowid);
                }
            })
                .catch(function(err) {
                    console.log(err);
                    let errmsg = 'Exception detected: '+err;
                    toast_msg(errmsg, 'danger');
                });
            return false;
        });
        $iorder.show();
    }
}

function playlist_total_duration (pl) {
    let durt = 0;
    for (let i of pl.items)
        durt += i.dur;
    return durt;
}

function bootstrap_table_uid_formatter(value, row, index, field) {
    let p = $('<p class="h3">');
    p.text(row.title);
    let p3, dti;
    if (row.datepub && row.datepub.length && !isNaN(dti = Date.parse(row.datepub))) {
        let utcSeconds = Math.round(dti / 1000);
        let d = new Date(0); // The 0 there is the key, which sets the date to the epoch
        d.setUTCSeconds(utcSeconds);
        p3 = 'Date: ' + d.format('yy/mm/dd HH:MM');
    }
    else
        p3 = 'Date: N/A';
    //let p2 = '<p class="h6">Duration: ' + format_duration(row.dur) + '</p>';
    let up = $('<p class="h4">');
    up.text(p3 + ' (' + (row?.conf?.author || 'N/A') + ')');
    return `
        <div class="container-fluid">
            <div class="row">${p.prop('outerHTML')}</div>
            <div class="row">${up.prop('outerHTML')}</div>
            <div class="row row-buffer pl-item-func-seen">
                <a class="btn btn-danger btn-lg col-12 btn-block" data-rowid="${row.rowid}" href="#" role="button" onclick="playlist_item_seen(this); return false;"><p class="h1"><i class="fas fa-trash-alt"></i></p></a>
            </div>
            <div class="row row-buffer pl-item-func pl-item-func-iorder">
                <a class="btn btn-info btn-lg col-12 btn-block" data-rowid="${row.rowid}" href="#" role="button" onclick="playlist_item_move(this); return false;"><p class="h1">${row.iorder}</p></a>
            </div>
            <div class="row row-buffer pl-item-func pl-item-func-iorder-sec" style="display: none;">
                <input type="number" class="col-6 input-lg"/><a class="btn btn-info btn-lg col-6 btn-block" data-rowid="${row.rowid}" href="#" role="button"><p class="h1"><i class="fas fa-dolly"></i></p></a>
            </div>
        </div>
        `;
    //return p.prop('outerHTML') + p3 + up.prop('outerHTML') + '<br />' +
    //'<a class="btn btn-danger btn-lg col-12 btn-block" data-rowid="'+row.rowid+'" href="#" role="button" onclick="playlist_tiem_seen(this); return false;"><p class="h1"><i class="fas fa-trash-alt"></i></p></a><br />' +
    //'<a class="btn btn-info btn-lg col-12 btn-block" data-rowid="'+row.rowid+'" href="#" role="button" onclick="playlist_tiem_move(this); return false;"><p class="h1">'+ row.iorder +'</p></a>';
}

function bootstrap_table_img_formatter(value, row, index, field) {
    return `
    <a href="${row.link}"><div class="thumb-container">
        <img src="${value}" class="thumb-image">
        <div class="thumb-duration-overlay">${format_duration(row.dur)}</div>
    </div></a>
        `;
}

let playlist_types = {
    youtube: {
        on_add: function(pl) {
            return pl.conf.playlists.length;
        },
        add: function(pl) {
            let el = $(`
                <div id="pl-add-view-youtube">
                    <div class="row row-buffer pl-add-view-youtube-row1">
                        <div class="col-12">
                            <form id="pl-add-view-youtube-form" class="form">
                                <div class="form-row">
                                    <div class="col-md-12 mb-3">
                                        <label for="pl-add-view-youtube-link">ID or page<br /></label>
                                        <input type="text" class="form-control-plaintext input-lg" id="pl-add-view-youtube-link"/>
                                        <div class="invalid-feedback">
                                            Please insert a valid youtube link or playlist ID
                                        </div>
                                    </div>
                                </div>
                                <div class="form-group">
                                    <div class="form-check custom-control-lg">
                                        <input class="form-check-input custom-control-input" type="checkbox" checked="true" value="" id="pl-add-view-youtube-ordered">
                                        <label class="form-check-label custom-control-label" for="pl-add-view-youtube-ordered">
                                        Ordered
                                        </label>
                                    </div>
                                </div>
                                <div class="form-row">
                                    <div class="col-12">
                                        <a id="pl-add-view-youtube-search" class="btn btn-primary btn-lg col-12 btn-block disabled" href="#" role="button"><p class="h1 font-enlarged"><i class="fas fa-search"></i>&nbsp;&nbsp;Search</p></a>
                                        <div id="pl-add-view-youtube-progress" class="progress bigger-progress">
                                            <div class="progress-bar progress-bar-striped progress-bar-animated" role="progressbar" aria-valuenow="100" aria-valuemin="0" aria-valuemax="100" style="width: 100%"></div>
                                        </div>
                                    </div>
                                </div>
                            </form>
                        </div>
                    </div>
                </div>
            `);
            let single_el = function(c, pl, type) {
                let div = $('<p class="h1">');
                let alert = $(
                    `
                    <div class="row">
                        <div class="col-12 alert alert-${type} alert-dismissible fade show" role="alert">
                            ${div.text(c.title).prop('outerHTML')}
                            <p class="h2">${c.id} (${c.ordered === undefined || c.ordered? 'Ordered': 'Unordered'})</p>
                            <button type="button" data-idpl="${c.id}" class="close" aria-label="Close">
                                <span aria-hidden="true">&times;</span>
                            </button>
                        </div>
                    </div>
                    `);
                alert.find('button').click(function() {
                    let id = $(this).data('idpl');
                    let pls = pl.conf.playlists;
                    for (let i = 0; i<pls.length; i++) {
                        if (pls[i].id == id) {
                            pls.splice(i, 1);
                            break;
                        }
                    }
                    let row = $(this).closest('.row');
                    $(this).closest('.alert').alert('close');
                    row.remove();
                    set_button_enabled('#pl-add-view-add', pls.length);
                });
                alert.children('.alert').alert();
                return alert.addClass(PL_ADD_VIEW_TYPE_CLASS);
            };
            let i = 0;
            let types = ['primary', 'secondary', 'success', 'warning', 'danger', 'info', 'light', 'dark'];
            for(let c2 of pl.conf.playlists) {
                el.append(single_el(c2, pl, types[i%types.length]));
                i++;
            }
            let $link = el.find('#pl-add-view-youtube-link');
            let $progress = el.find('#pl-add-view-youtube-progress');
            $progress.hide();
            let $search = el.find('#pl-add-view-youtube-search');
            $search.click(function() {
                let reqs = $link.val().split(',');
                $search.hide();
                $progress.show();
                let found = {};
                for (let t of reqs) {
                    if (!found[t]) {
                        found[t] = 1;
                        let qel = new MainWSQueueElement({cmd: CMD_YT_PLAYLISTCHECK, text:t}, function(msg) {
                            return msg.cmd === CMD_YT_PLAYLISTCHECK? msg:null;
                        }, 20000, 1);
                        qel.enqueue().then(function(msg) {
                            $progress.hide();
                            $search.show();
                            if (!manage_errors(msg)) {
                                let brandinfo = msg.playlistinfo;
                                for (let p of pl.conf.playlists) {
                                    if (p.id == brandinfo.id) {
                                        toast_msg('Playlist ' + p.title+' already present!', 'warning');
                                        return;
                                    }
                                }
                                toast_msg('Playlist ' + brandinfo.title+' added', 'success');
                                brandinfo.ordered = $('#pl-add-view-youtube-ordered').is(':checked');
                                pl.conf.playlists.push(brandinfo);
                                $($('.pl-add-view-youtube-row1').parents('div')[0]).append(single_el(brandinfo, pl, types[(pl.conf.playlists.length-1)%types.length]));
                                $link.val('');
                                set_button_enabled('#pl-add-view-youtube-search', false);
                                set_button_enabled('#pl-add-view-add', true);
                            }
                        })
                            .catch(function(err) {
                                console.log(err);
                                let errmsg = 'Exception detected: '+err;
                                toast_msg(errmsg, 'danger');
                                $progress.hide();
                                $search.show();
                            });
                    }
                }
            });
            $link.on('input', function() {
                let v = $(this).val();
                let valid =  /[a-zA-Z0-9\\/&\-\\+]+/.exec(v);
                let wasvalid = !$(this).hasClass('is-invalid');
                set_button_enabled('#pl-add-view-youtube-search',valid);
                if (!wasvalid && valid)
                    $(this).removeClass('is-invalid');
                else if (wasvalid && !valid)
                    $(this).addClass('is-invalid');
            });
            set_button_enabled('#pl-add-view-add', pl.conf.playlists.length);
            return el.children().addClass(PL_ADD_VIEW_TYPE_CLASS);
        }
    }
};

function playlist_update(playlist) {
    let utcSeconds = Math.round(playlist.dateupdate / 1000);
    let d = new Date(0); // The 0 there is the key, which sets the date to the epoch
    d.setUTCSeconds(utcSeconds);
    $('#pl-update-view-date-start').val(d.format('yyyy-mm-dd'));
    $('#pl-update-view-date-end').val(new Date().format('yyyy-mm-dd'));
    $('#pl-update-view-progress').hide();
    $('#pl-update-view-update').show();
}

function playlist_add(playlist) {
    let tp = $('#pl-add-view-type');
    if (playlist.type)
        tp.val(playlist.type);
    else
        tp.val('');
    playlist_change_type(playlist, playlist.type || '');
    $('#pl-add-view-name').val(playlist.name);
    $('#pl-add-view-autoupdate').prop('checked', playlist.autoupdate);
    
}

function playlist_change_type(pl, tp) {
    current_playlist = pl;
    $('#pl-add-view-container').find('.' + PL_ADD_VIEW_TYPE_CLASS).remove();
    if (tp.length)
        $('#pl-add-view-container').append(playlist_types[tp].add(current_playlist));
}

let current_playlist = null;


function playlist_add_button_change_function(func)  {
    if (func == 'add')
        $('#add-button').removeClass('btn-secondary').addClass('btn-success').html('<p class="h1 font-enlarged"><i class="fas fa-plus"></i>&nbsp;&nbsp;Add</p>').data('func', func);
    else 
        $('#add-button').removeClass('btn-success').addClass('btn-secondary').html('<p class="h1 font-enlarged"><i class="fas fa-arrow-left"></i>&nbsp;&nbsp;Back</p>').data('func', func);
}

function bootstrap_table_show_pagination(sel, val) {
    if (val)
        $(sel).closest('.bootstrap-table').find('.fixed-table-pagination').show();
    else
        $(sel).closest('.bootstrap-table').find('.fixed-table-pagination').fadeOut(1000);
}

function playlist_interface_manage(func) {
    if (func == 'add') {
        $('.pl-select-view').hide();
        $('.pl-list-view').fadeIn(1000);
        playlist_add_button_change_function(func);
    }
    else if (func == 'back-playlist-add') {
        $('.pl-select-view').hide();
        $('.pl-edit-view').hide();
        $('.pl-add-view').fadeIn(1000);
        playlist_add_button_change_function(func);
    }
    else if (func == 'back-playlist-update') {
        $('.pl-select-view').hide();
        $('.pl-add-view').hide();
        $('.pl-update-view').fadeIn(1000);
        playlist_add_button_change_function(func);
    }
    else if (func == 'back-list-update') {
        $('.pl-list-view').hide();
        $('.pl-add-view').hide();
        $('.pl-select-view').hide();
        $('.pl-update-view').fadeIn(1000);
        playlist_add_button_change_function(func);
    }
    else if (func == 'back-list-add') {
        $('.pl-list-view').hide();
        $('.pl-update-view').hide();
        $('.pl-select-view').hide();
        $('.pl-add-view').fadeIn(1000);
        playlist_add_button_change_function(func);
    }
    else if (func == 'back-list') {
        $('.pl-list-view').hide();
        $('.pl-add-view').hide();
        $('.pl-update-view').hide();
        $('.pl-select-view').fadeIn(1000);
        playlist_add_button_change_function(func);
    }
}

function playlist_sort() {
    let qel = new MainWSQueueElement({cmd: CMD_SORT, playlist:selected_playlist.rowid}, function(msg) {
        return msg.cmd === CMD_SORT? msg:null;
    }, 20000, 1);
    qel.enqueue().then(function(msg) {
        if (!manage_errors(msg)) {
            playlist_dump(selected_playlist.rowid);
        }
    })
        .catch(function(err) {
            console.log(err);
            let errmsg = 'Exception detected: '+err;
            toast_msg(errmsg, 'danger');
        });
}

function playlist_remove(ev) {
    let $ev = $(ev);
    let tmr = $ev.data('timer');
    let restoreDelButton = function($ev) {
        $ev.removeData('timer');
        $ev.removeData('countdown');
        $ev.html('<p class="h1 font-enlarged"><i class="fas fa-minus"></i>&nbsp;&nbsp;Remove</p>');
        $ev.closest('.container-fluid').find('.pl-select-func').show();
    };
    if (tmr !== undefined && tmr!==null) {
        clearTimeout(parseInt(tmr));
        restoreDelButton($ev);
    }
    else {
        $ev.html('<p class="h1 font-enlarged"><i class="fas fa-trash-restore"></i>&nbsp;&nbsp;&nbsp;5</p>');
        $ev.closest('.container-fluid').find('.pl-select-func').hide();
        let funDel = function() {
            let sec = parseInt(this.data('countdown')) - 1;
            if (sec) {
                this.html('<p class="h1 font-enlarged"><i class="fas fa-trash-restore"></i>&nbsp;&nbsp;&nbsp;'+ sec +'</p>');
                this.data('countdown', sec);
                this.data('timer', setTimeout(funDel.bind(this), 1000));
            }
            else {
                restoreDelButton(this);
                let qel = new MainWSQueueElement({cmd: CMD_DEL, playlist:selected_playlist.rowid}, function(msg) {
                    return msg.cmd === CMD_DEL? msg:null;
                }, 20000, 1);
                qel.enqueue().then(function(msg) {
                    if (!manage_errors(msg)) {
                        playlists_all.splice(playlists_all.map(function(e) { return e.rowid; }).indexOf(selected_playlist.rowid), 1);
                        $('#output-table').bootstrapTable('removeByUniqueId', selected_playlist.rowid);
                        bootstrap_table_pagination_fix();
                        selected_playlist = null;
                        docCookies.setItem(COOKIE_SELECTEDPL, -1);
                        playlist_interface_manage('add');
                    }
                })
                    .catch(function(err) {
                        console.log(err);
                        let errmsg = 'Exception detected: '+err;
                        toast_msg(errmsg, 'danger');
                    });
            }
        };
        $ev.data('countdown', 5);
        $ev.data('timer', setTimeout(funDel.bind($ev), 1000));
    }
}

function bootstrap_table_pagination_fix() {
    $('.fixed-table-pagination').addClass('input-lg');
    $('.page-size').addClass('input-lg');
    $('.page-list').find('.dropdown-menu').addClass('input-lg');
}

function playlist_update_in_list(p) {
    let idxof = playlists_all.map(function(e) { return e.rowid; }).indexOf(p.rowid);
    if (idxof >= 0)
        $('#output-table').bootstrapTable('updateRow', {index: idxof, row: p, replace: true});
    return idxof;
}

function index_global_init() {
    $('#playlist-items-table').bootstrapTable({showHeader: false}).on('load-success.bs.table page-change.bs.table', function() {
        bootstrap_table_pagination_fix();
    });
    $('.pl-select-view').hide();
    $('.pl-add-view').hide();
    $('.pl-update-view').hide();
    let $table =  $('#output-table');
    $table.bootstrapTable({showHeader: false});
    $table.on('load-success.bs.table page-change.bs.table', function() {
        bootstrap_table_pagination_fix();
    });
    $('#update-button').click(function() {
        playlist_interface_manage('back-playlist-update');
        playlist_update(current_playlist = selected_playlist);
        return;
    });
    $('#sort-button').click(function() {
        playlist_sort();
        return false;
    });
    $('#add-button').click(function() {
        let func = $(this).data('func');
        if (func == 'back-playlist-add')
            playlist_interface_manage('back-list');
        else if (func == 'back-list-update') {
            selected_playlist = null;
            docCookies.setItem(COOKIE_SELECTEDPL, -1);
            playlist_interface_manage('add');
        }
        else if (func == 'back-playlist-update')
            playlist_interface_manage('back-list');
        else if (func == 'back-list') {
            selected_playlist = null;
            docCookies.setItem(COOKIE_SELECTEDPL, -1);
            playlist_interface_manage('add');
        }
        else if (func == 'back-list-add') {
            selected_playlist = null;
            docCookies.setItem(COOKIE_SELECTEDPL, -1);
            playlist_interface_manage('add');
        }
        else {
            playlist_interface_manage('back-list-add');
            playlist_add(new Playlist(null, find_user_cookie()));
        }
        return false;
    });
    $('#remove-button').click(function() {
        playlist_remove(this);
        return false;
    });
    $('#edit-button').click(function() {
        let pl = {};
        $.extend(true, pl, selected_playlist);
        playlist_interface_manage('back-playlist-add');
        playlist_add(pl);
        return false;
    });
    $('#pl-update-view-datepicker').datepicker({
        format: 'yyyy/mm/dd',
        todayHighlight: true
    });
    $('#pl-add-view-type').change(function () {
        playlist_change_type(new Playlist(null, find_user_cookie()), $(this).val());
    });
    $('#pl-update-view-update').click(function () {
        $('#pl-update-view-progress').show();
        $('#pl-update-view-update').hide();
        let qel = new MainWSQueueElement({
            cmd: CMD_REFRESH, 
            playlist:current_playlist,
            datefrom:Date.parse($('#pl-update-view-date-start').val()),
            dateto:Date.parse($('#pl-update-view-date-end').val()),
        }, function(msg) {
            if (msg.cmd == CMD_PING)
                return 0;
            else if (msg.cmd == CMD_REFRESH)
                return msg;
            else
                return null;
        }, 45000, 1);
        qel.enqueue().then(function(msg) {
            if (manage_errors(msg)) {
                $('#pl-update-view-progress').hide();
                $('#pl-update-view-update').show();
            }
            else {
                if (!msg.n_new)
                    toast_msg('No new video found', 'warning');
                else
                    toast_msg('I have found ' + msg.n_new +' new video(s).', 'success');
                if (selected_playlist) {
                    let idx = playlist_update_in_list(msg.playlist);
                    playlists_all[idx] = selected_playlist = msg.playlist;
                    $('#playlist-items-table').bootstrapTable('load', [...selected_playlist.items]);
                    bootstrap_table_pagination_fix();
                }
                else {
                    playlists_all.push(msg.playlist);
                    $('#output-table').bootstrapTable('append', [msg.playlist]);
                    bootstrap_table_pagination_fix();
                    playlist_select(msg.playlist);
                }
                playlist_interface_manage('back-list');
            }
        })
            .catch(function(err) {
                console.log(err);
                let errmsg = 'Exception detected: '+err;
                toast_msg(errmsg, 'danger');
                $('#pl-update-view-progress').hide();
                $('#pl-update-view-update').show();
            });
    });
    $('#pl-add-view-add').click(function () {
        let form = $('#pl-add-view-form'), type;
        if (form[0].checkValidity() && playlist_types[type = $('#pl-add-view-type').val()].on_add(current_playlist)) {
            current_playlist.name = $('#pl-add-view-name').val();
            current_playlist.type = type;
            current_playlist.autoupdate = $('#pl-add-view-autoupdate').is(':checked');
            playlist_interface_manage(selected_playlist? 'back-playlist-update': 'back-list-update');
            playlist_update(current_playlist);
        }
        else {
            toast_msg('Please add at least a playlist and make sure tu specify a valid name', 'warning');
        }
        form.addClass('was-validated'); 
    });

}

function playlist_dump(plid) {
    let useri = find_user_cookie();
    let el = new MainWSQueueElement({cmd: CMD_DUMP, useri:useri, playlist: plid}, function(msg) {
        return msg.cmd === CMD_DUMP? msg:null;
    }, 30000, 1);
    el.enqueue().then(function(msg) {
        let errmsg;
        if (!manage_errors(msg)) {
            if (msg.playlists.length) {
                let idx = playlist_update_in_list(msg.playlists[0]);
                playlists_all[idx] = msg.playlists[0];
                playlist_select(msg.playlists[0]);
            }
        }
    })
        .catch(function(err) {
            console.log(err);
            let errmsg = 'Exception detected: '+err;
            toast_msg(errmsg, 'danger');
        });
}


function playlists_dump(params, useri, fast_videoidx, fast_videostep, multicmd) {
    if (useri === undefined) {
        useri = find_user_cookie();
        if (useri === null) {
            if (params)
                params.error('No User Cookie Found. Redirecting to login');
            toast_msg('No User Cookie Found. Redirecting to login', 'danger');
            setTimeout(function() {
                window.location.assign(MAIN_PATH + 'login.htm');
            }, 5000);
            return;
        }
    }
    let content_obj = {
        cmd: CMD_DUMP,
        multicmd: multicmd || 0,
        playlist: null,
        useri: useri,
        fast_videoidx: fast_videoidx===undefined? /*0 per load a pezzi: null per load tutto in una botta*/ 0:fast_videoidx + fast_videostep
    };
    let $table = $('#output-table');
    let $plitemsTable = $('#playlist-items-table');
    let el = new MainWSQueueElement(content_obj, function(msg) {
        return msg.cmd === CMD_DUMP? msg:null;
    }, 30000, 1);
    el.enqueue().then(function(msg) {
        let errmsg;
        if ((errmsg = manage_errors(msg))) {
            if (params)
                params.error(errmsg);
        }
        else {
            let no_more = true;
            for (let p of msg.playlists) {
                let pos = playlists_all.map(function(e) { return e.rowid; }).indexOf(p.rowid);
                if (pos >= 0) {
                    playlists_all[pos].items.push(...p.items);
                    $table.bootstrapTable('updateRow', {index:pos, row:playlists_all[pos], replace:true});
                    if (selected_playlist && selected_playlist.rowid == playlists_all[pos].rowid) {
                        $plitemsTable.bootstrapTable('append', p.items);
                    }
                }
                else
                    playlists_all.push(p);
                if (p.items.length === msg.fast_videostep)
                    no_more = false;
            }
            if (params) {
                let rid = docCookies.getItem(COOKIE_SELECTEDPL);
                params.success({
                    rows: msg.playlists,
                    total: msg.playlists.length
                });
                if (rid !== null) {
                    let idxOf = msg.playlists.map(function(e) { return e.rowid; }).indexOf(parseInt(rid));
                    if (idxOf >= 0) {
                        playlist_select(msg.playlists[idxOf]);
                        playlist_interface_manage('back-list');
                    }
                }
            }
            if (!no_more) {
                console.log('More items to come...');
                if (!msg.multicmd) {
                    msg.multicmd = new Date().getTime();
                }
                playlists_dump(null, useri, msg.fast_videoidx, msg.fast_videostep, msg.multicmd);
            }
        }
    })
        .catch(function(err) {
            console.log(err);
            let errmsg = 'Exception detected: '+err;
            if (params)
                params.error(errmsg);
            toast_msg(errmsg, 'danger');
        });
}

function bootstrap_table_get_data_ws(params) {
    main_ws_connect();
    playlists_all = [];
    playlists_dump(params);
}

function playlist_select(ev) {
    if (ev.rowid !== undefined) {
        selected_playlist = ev;
    }
    else {
        let rid = parseInt($(ev).data('rowid'));
        playlist_interface_manage('back-list');
        selected_playlist = playlists_all[playlists_all.map(function(e) { return e.rowid; }).indexOf(rid)];
    }
    $('#playlist-items-table').bootstrapTable('load', [...selected_playlist.items]);
    docCookies.setItem(COOKIE_SELECTEDPL, selected_playlist.rowid);
    bootstrap_table_pagination_fix();
}

function manage_errors(msg) {
    if (msg.rv) {
        let errmsg = 'E [' + msg.rv + '] ' + msg.err+ '.'; 
        if (msg.rv == 501 || msg.rv == 502)
            errmsg +=' Redirecting to login.';
        toast_msg(errmsg, 'danger');
        if (msg.rv == 501 || msg.rv == 502)
            setTimeout(function() {
                window.location.assign(MAIN_PATH + 'login.htm');
            }, 5000);
        return errmsg;
    }
    else
        return null;
    
}

function bootstrap_table_name_formatter(value, row, index, field) {
    if (row.items.length) {
        return `
        <a data-rowid="${row.rowid}" href="#" onclick="playlist_select(this); return false;"><div class="thumb-container">
            <img src="${row.items[0].img}" class="thumb-image">
            <div class="thumb-name-overlay">${value}</div>
        </div></a>
            ` + '<br />' + bootstrap_table_info_formatter(value, row, index, field);
    }
    else
        return value;
}

function bootstrap_table_info_formatter(value, row, index, field) {
    let utcSeconds = Math.round(row.dateupdate / 1000);
    let d = new Date(0); // The 0 there is the key, which sets the date to the epoch
    d.setUTCSeconds(utcSeconds);
    let tpstr = '';
    if (row.type == 'youtube')
        tpstr += '<span class="badge badge-danger even-larger-badge">youtube</span>&nbsp;&nbsp;';
    else if (row.type == 'rai')
        tpstr += '<span class="badge badge-primary even-larger-badge">rai</span>&nbsp;&nbsp;';
    else
        tpstr += '<span class="badge badge-secondary even-larger-badge">mediaset</span>&nbsp;&nbsp;';
    tpstr += '<p class="h1">Last Updated: ' + d.format('yyyy/mm/dd') + ' (' +row.items.length + ' items - '+format_duration(playlist_total_duration(row)) +') - AutoUpdate ' + (row.autoupdate?'<i class="fas fa-check">':'<i class="fas fa-times">')+ '</i></p>';
    return tpstr;
}

$(window).on('load', function() {
    let bp =  bootstrapDetectBreakpoint();
    console.log('BP = ' + JSON.stringify(bp));
    if (bp && bp.name && (bp.name == 'xs' || bp.name == 'sm')) {
        $('th[data-field="img"]').addClass('col-10');
    }
    console.log(new Date().format('yyyy/mm/dd'));
    index_global_init();
});