let selected_playlist = null;
let playlists_all = [];
let playlist_user = null;
let playlist_selected_del_tmr = -1;
let playlist_selected_del_cnt = 5;
let back_list_scroll_top = 0;
const bootstrap_styles = ['primary', 'secondary', 'success', 'warning', 'danger', 'info', 'light', 'dark'];
let bootstrap_breakpoint = {name: 'xs'};
let xl = '';

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
    $ev.each(function() {
        let ths = $(this);
        let seen = ths.data('seen');
        if (seen)
            seen = parseInt(seen);
        ths.html(bootstrap_wrap_button(seen ? 'fas fa-trash-restore': 'fas fa-trash-alt', '', xl ? 'h3':''));
        ths.closest('.container-fluid').find('.pl-item-func-iorder').show();
        ths.removeAttr('data-timer');
    });
}

function playlist_selected_del_tmr_fun() {
    playlist_selected_del_cnt--;
    let waiting_del = $('.pl-item-func-seen').children('a[data-timer]');
    if (waiting_del.length && playlist_selected_del_cnt) {
        waiting_del.each(function() {
            let ths = $(this);
            let seen = ths.data('seen');
            if (seen)
                seen = parseInt(seen);
            ths.html(bootstrap_wrap_button(seen ? 'fas fa-trash-alt': 'fas fa-trash-restore', '' + playlist_selected_del_cnt, xl ? 'h3':''));
        });
        
        playlist_selected_del_tmr = setTimeout(playlist_selected_del_tmr_fun, 1000);
    }
    else {
        playlist_selected_del_restore(waiting_del);
        playlist_selected_del_cnt = 5;
        playlist_selected_del_tmr = -1;
        let $plitemsTable = $('#playlist-items-table');
        if (waiting_del.length) {
            let lids = [];
            let seens = [];
            waiting_del.each(function() {
                let ths = $(this);
                let seen = ths.data('seen');
                if (seen)
                    seen = parseInt(seen);
                let rid = parseInt(ths.data('rowid'));
                lids.push(rid);
                seens.push(seen? 0:1);
            });
            let qel = new MainWSQueueElement({cmd: CMD_SEEN, playlistitem:lids, seen:seens}, function(msg) {
                return msg.cmd === CMD_SEEN? msg:null;
            }, 20000, 1);
            qel.enqueue().then(function(msg) {
                if (!manage_errors(msg)) {
                    for (let rid of lids) {
                        let row = $plitemsTable.bootstrapTable('getRowByUniqueId', rid);
                        toast_msg('Playlist item ' + row.title+ (row.seen?' restored': ' removed'), 'success');
                        let rowcp = {... row};
                        if (rowcp.seen)
                            rowcp.seen = null;
                        else
                            rowcp.seen =  new Date().format('yyyy-mm-dd HH:MM:ss');
                        let pos = selected_playlist.items.map(function(e) { return e.rowid; }).indexOf(rid);
                        $plitemsTable.bootstrapTable('updateRow', {index:pos, row:rowcp, replace:true});
                        selected_playlist.items[pos] = rowcp;
                    }
                    set_button_enabled('#play-button', selected_playlist.items.length);
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
        let seen = $ev.data('seen');
        if (seen)
            seen = parseInt(seen);
        $ev.html(bootstrap_wrap_button(seen?'fas fa-trash-alt': 'fas fa-trash-restore', '5', xl ? 'h3':''));
        $ev.closest('.container-fluid').find('.pl-item-func').hide();
        $ev.attr('data-timer', 1);
    }
}

function playlist_item_movepls(ev) {
    let $ev = $(ev);
    let rid = $ev.data('rowid');
    let plid = $ev.data('plid');
    let qel = new MainWSQueueElement({cmd: CMD_MOVE, playlistitem:parseInt(rid), playlist: parseInt(plid)}, function(msg) {
        return msg.cmd === CMD_MOVE? msg:null;
    }, 20000, 1);
    qel.enqueue().then(function(msg) {
        if (!manage_errors(msg)) {
            playlist_dump(plid);
            playlist_dump(selected_playlist.rowid);
        }
    })
        .catch(function(err) {
            console.log(err);
            let errmsg = 'Exception detected: '+err;
            toast_msg(errmsg, 'danger');
        });
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
    for (let i of pl.items) {
        if (!i.seen)
            durt += i.dur;
    }
    return durt;
}

function bootstrap_wrap_button(ivalue, tvalue, classv) {
    let tag = '';
    if (classv.length) {
        tag += `<p class="${classv}">`;
    }
    if (ivalue.length) {
        tag += `<i class="${ivalue}"></i>`;
    }
    if (tvalue.length) {
        if (ivalue.length)
            tvalue = '&nbsp;&nbsp;' + $('<div>').text(tvalue).html();
        tag += tvalue;
    }
    if (classv.length)
        tag += '</p>';
    return tag;
}

function bootstrap_table_uid_formatter(value, row, index, field) {
    let seen = row.seen?1:0;
    let style = seen?' style="color:red;">':'>';
    let p = $((xl?'<p class="h1"':'<p class="h6"') + style);
    p.text(row.title);
    let up = bootstrap_table_date_uploader_formatter(row, 'h2');
    let s = xl?`<div class="row">${up.prop('outerHTML')}</div>`:'';
    let other_pls = '';
    playlists_all.map(function(e) { 
        if (e.rowid != row.playlist) {
            other_pls += $('<a class="dropdown-item" onclick="playlist_item_movepls(this); return false;" href="#">').attr('data-plid', e.rowid).attr('data-rowid', row.rowid).text(e.name).prop('outerHTML');
        }
    });
    return `
        <div class="container-fluid">
            <div class="row">${p.prop('outerHTML')}</div>
            ${s}
            <div class="row row-buffer pl-item-func-seen">
                <a class="btn btn-danger col-12 btn-block" data-rowid="${row.rowid}" data-seen="${seen}" href="#" role="button" onclick="playlist_item_seen(this); return false;">${bootstrap_wrap_button(seen? 'fas fa-trash-restore': 'fas fa-trash-alt', '', xl?'h3':'')}</a>
            </div>
            <div class="row row-buffer pl-item-func pl-item-func-iorder">
                <a class="btn btn-info col-12 btn-block" data-rowid="${row.rowid}" data-seen="${seen}" href="#" role="button" onclick="playlist_item_move(this); return false;">${bootstrap_wrap_button('', '' + row.iorder, xl?'h3':'')}</a>
            </div>
            <div class="row row-buffer pl-item-func pl-item-func-iorder-sec" style="display: none;">
                <input type="number" class="col-6"/><a class="btn btn-info col-6 btn-block" data-rowid="${row.rowid}" data-seen="${seen}" href="#" role="button">${bootstrap_wrap_button('fas fa-dolly', '', xl?'h3':'')}</a>
            </div>
            <div class="row row-buffer pl-item-func pl-item-func-move">
                <div class="btn-group col-12">
                    <button type="button" class="btn btn-info ${xl?'btn-lg':''} dropdown-toggle" data-toggle="dropdown" aria-haspopup="true" aria-expanded="false">
                    ${bootstrap_wrap_button('fas fa-truck-moving', '', '')}
                    </button>
                    <div class="dropdown-menu">
                    ${other_pls}
                    </div>
                </div>
            </div>
        </div>
        `;
    //return p.prop('outerHTML') + p3 + up.prop('outerHTML') + '<br />' +
    //'<a class="btn btn-danger col-12 btn-block" data-rowid="'+row.rowid+'" href="#" role="button" onclick="playlist_tiem_seen(this); return false;"><p class="h1"><i class="fas fa-trash-alt"></i></p></a><br />' +
    //'<a class="btn btn-info col-12 btn-block" data-rowid="'+row.rowid+'" href="#" role="button" onclick="playlist_tiem_move(this); return false;"><p class="h1">'+ row.iorder +'</p></a>';
}

function bootstrap_table_date_uploader_formatter(row, classv) {
    let p3, dto = null, style = '', dti;
    if (row.seen) {
        style = ' style="color:red;"';
        p3 = 'Del: ';
        dto = row.seen;
    }
    else {
        dto = row.datepub;
        p3 = 'Date: ';
    }
    if (dto && !isNaN(dti = Date.parse(dto))) {
        let utcSeconds = Math.round(dti / 1000);
        let d = new Date(0); // The 0 there is the key, which sets the date to the epoch
        d.setUTCSeconds(utcSeconds);
        p3 += d.format('yy/mm/dd HH:MM');
    }
    else
        p3 += 'N/A';
    //let p2 = '<p class="h6">Duration: ' + format_duration(row.dur) + '</p>';
    let up = $(`<p class="${classv}"${style}>`);
    up.text(p3 + ' (' + (row.conf && row.conf.author?row.conf.author:'N/A') + ')');
    return up;
}

function playlist_transform_thumbnail_path(dbpath) {
    return dbpath[0] == '?'?MAIN_PATH + 'img' + dbpath:(dbpath[0] == '@'?MAIN_PATH_S + dbpath.substring(1):dbpath);
}

function playlist_transform_video_path(dbpath) {
    return dbpath[0] == '@'?MAIN_PATH_S + dbpath.substring(1):dbpath;
}

function bootstrap_table_img_formatter(value, row, index, field) {
    let up = bootstrap_table_date_uploader_formatter(row, 'h5 font-reduced');
    let s = xl?'':up.prop('outerHTML');
    return `
    <a href="${playlist_transform_video_path(row.link)}"><div class="thumb-container">
        <img src="${playlist_transform_thumbnail_path(value)}" class="thumb-image">
        <div class="thumb-duration-overlay-${bootstrap_breakpoint.name}">${format_duration(row.dur)}</div>
    </div></a>
    ${s}
        `;
}

function playlist_medrai_listings_formatter(value, row, index, field, type) {
    return `
    <a data-id="${row.id}" data-type="${type}" href="#" onclick="playlist_listings_select(this); return false;">
    ${playlist_medrai_brands_formatter(value, row, index, field, type)}
    </a>`;
}

function playlist_localfolder_listings_formatter_main(value, row, index, field) {
    return playlist_medrai_brands_formatter(value, row, index, field, 'localfolder');
}

function playlist_localfolder_listings_formatter_chk(value, row, index, field) {
    return current_playlist?.conf?.playlists[row.id]?true:false;
}

function playlist_mediaset_listings_formatter(value, row, index, field) {
    return playlist_medrai_listings_formatter(value, row, index, field, 'mediaset');
}

function playlist_rai_listings_formatter(value, row, index, field) {
    return playlist_medrai_listings_formatter(value, row, index, field, 'rai');
}

function playlist_medrai_brands_formatter(value, row, index, field, type) {
    return `
        <span class="col-12 badge badge-${bootstrap_styles[index%bootstrap_styles.length]}">
            <p class="h5">${row.desc?row.desc:(row.description?row.description:(row.title?row.title:'N/A'))}</p>
            <p class="h6">${(row.desc?row.title + '/':'') + row.id}</p>
        </span>`;
}

function playlist_rai_brands_formatter(value, row, index, field) {
    return playlist_medrai_brands_formatter(value, row, index, field, 'rai');
}

function playlist_mediaset_brands_formatter(value, row, index, field) {
    return playlist_medrai_brands_formatter(value, row, index, field, 'mediaset');
}

function playlist_medrai_get_subbrands(brandid, type) {
    let msg_obj = {};
    current_playlist.conf.subbrands = [];
    $('#pl-add-view-medrai-brands-table').bootstrapTable('removeAll');
    
    if (type == 'mediaset') {
        msg_obj = {
            cmd: CMD_MEDIASET_BRANDS,
            brand: parseInt(brandid)
        };
    }
    else {
        msg_obj = {
            cmd: CMD_RAI_CONTENTSET,
            brand: brandid
        };
    }
    let $progress = $('#pl-add-view-medrai-progress');
    let $search = $('#pl-add-view-medrai-search');
    $progress.show();
    $search.hide();
    let qel = new MainWSQueueElement(msg_obj, function(msg) {
        if (msg.cmd == CMD_PING)
            return 0;
        else if (msg.cmd == msg_obj.cmd)
            return msg;
        else
            return null;
    }, 50000, 1);
    qel.enqueue().then(function(msg) {
        $progress.hide();
        $search.show();
        if (!manage_errors(msg)) {
            $('#pl-add-view-medrai-brands-table').bootstrapTable('load', msg.brands);
        }
    })
        .catch(function(err) {
            $progress.hide();
            $search.show();
            console.log(err);
            let errmsg = 'Exception detected: '+err;
            toast_msg(errmsg, 'danger');
        });
}

function playlist_localfolder_check_react() {
    const $listingsTable = $('#pl-add-view-localfolder-listings-table');
    const sels = $listingsTable.bootstrapTable('getSelections');
    current_playlist.conf.playlists = {};
    for (let sel of sels) {
        current_playlist.conf.playlists[sel.id] = current_playlist.conf.folders[sel.id];
    }
    set_button_enabled('#pl-add-view-add', playlist_types['localfolder'].on_add(current_playlist));
}

function playlist_localfolder_load_listings_table(pl, folders) {
    const $listingsTable = $('#pl-add-view-localfolder-listings-table');
    const $progress = $('#pl-add-view-localfolder-progress');
    const $search = $('#pl-add-view-localfolder-search');
    $listingsTable.bootstrapTable('removeAll');
    $listingsTable.bootstrapTable('load', folders);
    const pls = Object.values(pl.conf.playlists);
    for (let p of pls) {
        if (!pl.conf.folders[p.id]) {
            delete pl.conf.playlists[p.id];
        }
    }
    set_button_enabled('#pl-add-view-add', playlist_types['localfolder'].on_add(pl));
    $progress.hide();
    $search.show();
}

function playlist_localfolder_get_listings_ws() {
    const $listingsTable = $('#pl-add-view-localfolder-listings-table');
    const $progress = $('#pl-add-view-localfolder-progress');
    const $search = $('#pl-add-view-localfolder-search');
    $listingsTable.bootstrapTable('removeAll');
    $progress.show();
    $search.hide();
    let qel = new MainWSQueueElement({cmd: CMD_FOLDER_LIST}, function(msg) {
        if (msg.cmd == CMD_PING)
            return 0;
        else if (msg.cmd == CMD_FOLDER_LIST)
            return msg;
        else
            return null;
    }, 50000, 1);
    qel.enqueue().then(function(msg) {
        let errmsg;
        $progress.hide();
        $search.show();
        if (!(errmsg = manage_errors(msg))) {
            const arr = Object.values(current_playlist.conf.folders = msg.folders);
            playlist_localfolder_load_listings_table(current_playlist, arr);
        }
    })
        .catch(function(err) {
            $progress.hide();
            $search.show();
            console.log(err);
            let errmsg = 'Exception detected: '+err;
            toast_msg(errmsg, 'danger');
        });
}

function playlist_medrai_get_listings_ws(listings_cmd, params) {
    let $listingsTable = $('#pl-add-view-medrai-listings-table');
    $listingsTable.bootstrapTable('removeAll');
    let $progress = $('#pl-add-view-medrai-progress');
    let $search = $('#pl-add-view-medrai-search');
    $progress.show();
    $search.hide();
    let qel = new MainWSQueueElement(listings_cmd, function(msg) {
        if (msg.cmd == CMD_PING)
            return 0;
        else if (msg.cmd == listings_cmd.cmd)
            return msg;
        else
            return null;
    }, 50000, 1);
    qel.enqueue().then(function(msg) {
        let $progress = $('#pl-add-view-medrai-progress');
        let $search = $('#pl-add-view-medrai-search');
        let errmsg;
        $progress.hide();
        $search.show();
        if ((errmsg = manage_errors(msg))) {
            if (params)
                params.error(errmsg);
        }
        else {
            if (params)
                params.success({
                    rows: msg.brands,
                    total: msg.brands.length
                });
            else {
                $listingsTable.bootstrapTable('load', msg.brands);
            }
        }
    })
        .catch(function(err) {
            let $progress = $('#pl-add-view-medrai-progress');
            let $search = $('#pl-add-view-medrai-search');
            $progress.hide();
            $search.show();
            console.log(err);
            let errmsg = 'Exception detected: '+err;
            toast_msg(errmsg, 'danger');
            if (params)
                params.error(errmsg);
        });
}

function playlist_rai_get_listings_ws(params) {
    playlist_medrai_get_listings_ws({cmd: CMD_RAI_LISTINGS}, params);
}

function playlist_mediaset_get_listings_ws(params) {
    playlist_medrai_get_listings_ws({cmd: CMD_MEDIASET_LISTINGS, datestart: new Date().getTime()}, params);
}

function playlist_listings_select(ael) {
    let $ael = $(ael);
    let did = $ael.data('id');
    let $man = $('#pl-add-view-medrai-manual');
    current_playlist.conf.brand = {id: did};
    $man.val(did);

    playlist_medrai_get_subbrands(did, $ael.data('type'));
}

let playlist_types = {
    medrai: {
        on_add: function(pl) {
            return pl.conf.subbrands && pl.conf.subbrands.length;
        },
        add: function(pl, type) {
            let el = $(`
                <div id="pl-add-view-medrai">
                    <div class="row row-buffer">
                        <div class="col-12">
                            <form id="pl-add-view-medrai-form" class="form">
                                <div class="form-row">
                                    <div class="col-md-12 mb-3">
                                        <label for="pl-add-view-medrai-manual">Program ID<br /></label>
                                        <input type="text" class="form-control-plaintext input-lg" id="pl-add-view-medrai-manual" required/>
                                        <div class="invalid-feedback">
                                            Please insert a valid Program ID
                                        </div>
                                    </div>
                                </div>
                                <div class="form-row">
                                    <div class="col-12">
                                        <a id="pl-add-view-medrai-search" class="btn btn-primary col-12 btn-block disabled" href="#" role="button"><p class="h3"><i class="fas fa-search"></i>&nbsp;&nbsp;Search</p></a>
                                        <div id="pl-add-view-medrai-progress" class="progress bigger-progress">
                                            <div class="progress-bar progress-bar-striped progress-bar-animated" role="progressbar" aria-valuenow="100" aria-valuemin="0" aria-valuemax="100" style="width: 100%"></div>
                                        </div>
                                        <!--<div class="container" id="pl-add-view-medrai-progress">
                                            <div class="row">
                                            <span></span>
                                            <span class="col-2"></span>
                                            <span class="col-2"></span>
                                            <span class="col-2"></span>
                                            <span class="col-2"></span>
                                            <span class="col-2"></span>
                                            </div>
                                        </div>-->
                                    </div>
                                </div>
                                <div class="form-row" id="pl-add-view-medrai-append">
                                </div>
                                <div class="form-row">
                                    <div class="col-12">
                                        <table id="pl-add-view-medrai-listings-table" data-maintain-meta-data="true" data-page-size="10" data-pagination="true" data-show-header="false" data-classes="table table-borderless table-hover table-condensed" data-single-select="true" data-search="true" data-ajax="playlist_${type}_get_listings_ws">
                                            <thead>
                                                <tr>
                                                    <th data-field="id" data-visible="true" data-formatter="playlist_${type}_listings_formatter">Name</th>
                                                </tr>
                                            </thead>
                                        </table>
                                    </div>
                                </div>
                                <div class="form-row">
                                    <div class="col-12">
                                        <table id="pl-add-view-medrai-brands-table" data-page-size="10" data-pagination="true" data-show-header="false" data-classes="table table-borderless table-hover table-condensed" data-click-to-select="true">
                                            <thead>
                                                <tr>
                                                    <th data-field="state" data-checkbox="true"></th>
                                                    <th data-field="id" data-visible="true" data-formatter="playlist_${type}_brands_formatter">Name</th>
                                                </tr>
                                            </thead>
                                        </table>
                                    </div>
                                </div>
                            </form>
                        </div>
                    </div>
                </div>
            `);
            let $man = el.find('#pl-add-view-medrai-manual');
            $man.on('input', function() {
                let v = $(this).val();
                let valid =  playlist_types[type].brand_regexp().exec(v);
                let wasvalid = !$(this).hasClass('is-invalid');
                set_button_enabled('#pl-add-view-medrai-search',valid);
                if (!wasvalid && valid)
                    $(this).removeClass('is-invalid');
                else if (wasvalid && !valid)
                    $(this).addClass('is-invalid');
            });
            let $brandsTable = el.find('#pl-add-view-medrai-brands-table');
            $brandsTable.bootstrapTable().on('check.bs.table uncheck.bs.table ' +
                'check-all.bs.table uncheck-all.bs.table', function() {
                let sels = $brandsTable.bootstrapTable('getSelections');
                pl.conf.brand = {id: playlist_types[type].id_convert($man.val())};
                pl.conf.subbrands = [...sels];
            });
            let $app = playlist_types[type].append_row();
            let $appTo = el.find('#pl-add-view-medrai-append');
            if ($app)
                $appTo.append($app);
            else
                $appTo.remove();
            let $listingsTable = el.find('#pl-add-view-medrai-listings-table');
            $listingsTable.bootstrapTable();
            $man.val(pl.conf.brand?pl.conf.brand.id:'');
            $brandsTable.bootstrapTable('load', pl.conf.subbrands?pl.conf.subbrands:[]);
            $brandsTable.bootstrapTable('checkAll');

            let $search = el.find('#pl-add-view-medrai-search');
            $search.hide();
            $search.click(function() {
                playlist_medrai_get_subbrands($man.val(), type);
                return false;
            });
            return el.children().addClass(PL_ADD_VIEW_TYPE_CLASS);
        }
    },
    rai: {
        on_add: function(pl) {
            return playlist_types.medrai.on_add(pl);
        },
        add: function(pl) {
            return playlist_types.medrai.add(pl, 'rai');
        },
        brand_regexp() {
            return /^[a-zA-Z0-9_&\-\\+]+$/;
        },
        append_row() {
            return null;
        },
        id_convert(id) {
            return id;
        }
    },
    mediaset: {
        on_add: function(pl) {
            return playlist_types.medrai.on_add(pl);
        },
        add: function(pl) {
            return playlist_types.medrai.add(pl, 'mediaset');
        },
        brand_regexp() {
            return /^[0-9]+$/;
        },
        append_row() {
            return $('<div>').datepicker({
                todayHighlight: true
            }).datepicker('update', new Date()).on('changeDate', function(e) {
                playlist_medrai_get_listings_ws({cmd: CMD_MEDIASET_LISTINGS, datestart: e.date.getTime()}, null);
                return false;
            });
        },
        id_convert(id) {
            return parseInt(id);
        }
    },
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
                                        <a id="pl-add-view-youtube-search" class="btn btn-primary col-12 btn-block disabled" href="#" role="button"><p class="h3"><i class="fas fa-search"></i>&nbsp;&nbsp;Search</p></a>
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
                let div = $('<p class="h5">');
                let alert = $(
                    `
                    <div class="row">
                        <div class="col-12 alert alert-${type} alert-dismissible fade show" role="alert">
                            ${div.text(c.title).prop('outerHTML')}
                            <p class="h6">${c.id} (${c.ordered === undefined || c.ordered? 'Ordered': 'Unordered'})${c.params && Object.keys(c.params).length?' [' + JSON.stringify(c.params, undefined, 2) + ']':''}</p>
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
            for(let c2 of pl.conf.playlists) {
                el.append(single_el(c2, pl, bootstrap_styles[i%bootstrap_styles.length]));
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
                                $($('.pl-add-view-youtube-row1').parents('div')[0]).append(single_el(brandinfo, pl, bootstrap_styles[(pl.conf.playlists.length-1)%bootstrap_styles.length]));
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
    },
    localfolder: {
        on_add: function(pl) {
            return pl.conf.playlists && Object.keys(pl.conf.playlists).length;
        },
        add: function(pl) {
            let el = $(`
                <div id="pl-add-view-localfolder">
                    <div class="row row-buffer">
                        <div class="col-12">
                            <form id="pl-add-view-localfolder-form" class="form">
                                <div class="form-row">
                                    <div class="col-12">
                                        <a id="pl-add-view-localfolder-search" class="btn btn-primary col-12 btn-block" href="#" role="button"><p class="h3"><i class="fas fa-redo-alt"></i>&nbsp;&nbsp;Refresh</p></a>
                                        <div id="pl-add-view-localfolder-progress" class="progress bigger-progress">
                                            <div class="progress-bar progress-bar-striped progress-bar-animated" role="progressbar" aria-valuenow="100" aria-valuemin="0" aria-valuemax="100" style="width: 100%"></div>
                                        </div>
                                    </div>
                                </div>
                                <div class="form-row">
                                    <div class="col-12">
                                        <table id="pl-add-view-localfolder-listings-table" data-maintain-meta-data="true" data-page-size="10" data-pagination="true" data-show-header="false" data-classes="table table-borderless table-hover table-condensed" data-click-to-select="true" data-search="true">
                                            <thead>
                                                <tr>
                                                    <th data-field="state" data-checkbox="true" data-formatter="playlist_localfolder_listings_formatter_chk"></th>
                                                    <th data-field="id" data-visible="true" data-formatter="playlist_localfolder_listings_formatter_main">Name</th>
                                                </tr>
                                            </thead>
                                        </table>
                                    </div>
                                </div>
                            </form>
                        </div>
                    </div>
                </div>
            `);
            const $listingsTable = el.find('#pl-add-view-localfolder-listings-table');
            const $search = el.find('#pl-add-view-localfolder-search');
            $listingsTable.bootstrapTable().on('check.bs.table uncheck.bs.table ' +
                'check-all.bs.table uncheck-all.bs.table', playlist_localfolder_check_react);
            if (!pl.conf.folders) {
                pl.conf.folders = {};
                pl.conf.playlists = {};
            } else if (!pl.conf.playlists)
                pl.conf.playlists = {};
            const arr = pl.conf.folders?Object.values(pl.conf.folders):null;
            if (arr && arr.length) {
                setTimeout(() => playlist_localfolder_load_listings_table(pl, arr, el), 500);
            } else {
                playlist_localfolder_get_listings_ws();
            }
            
            $search.click(function() {
                playlist_localfolder_get_listings_ws();
            });
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
    playlist_update_destroy_wake();
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
        $('#add-button').removeClass('btn-secondary').addClass('btn-success').html('<p class="h3"><i class="fas fa-plus"></i>&nbsp;&nbsp;Add</p>').data('func', func);
    else 
        $('#add-button').removeClass('btn-success').addClass('btn-secondary').html('<p class="h3"><i class="fas fa-arrow-left"></i>&nbsp;&nbsp;Back</p>').data('func', func);
}

function playlist_show_button_change_function(func)  {
    let $plitemsTable = $('#playlist-items-table');
    let fn;
    if (!func && !(fn = $('#show-button').data('func')))
        func = 'show';
    else if (!func) {
        func = fn == 'show'?'hide':'show';
    }
    else if (func == 'same') {
        func = $('#show-button').data('func');
    }
    if (func == 'show' || !selected_playlist) {
        $('#show-button').html('<p class="h3"><i class="fas fa-eye"></i>&nbsp;&nbsp;Show Deleted</p>').data('func', func);
        if (selected_playlist) {
            $plitemsTable.bootstrapTable('filterBy', 'custom', {'filterAlgorithm': function(row) { return row.seen == null; }});
        }
    }
    else {
        $('#show-button').html('<p class="h3"><i class="fas fa-eye-slash"></i>&nbsp;&nbsp;Hide Deleted</p>').data('func', func);
        $plitemsTable.bootstrapTable('filterBy', {}, {'filterAlgorithm': 'and'});
    }
}

function playlist_interface_manage(func) {
    if (func == 'add') {
        $('.pl-select-view').hide();
        $('.pl-add-view').hide();
        $('.' + PL_ADD_VIEW_TYPE_CLASS).remove();
        $('.pl-list-view').fadeIn(1000);
        playlist_add_button_change_function(func);
        $(window).scrollTop(back_list_scroll_top);
        back_list_scroll_top = 0;
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
        $('.' + PL_ADD_VIEW_TYPE_CLASS).remove();
        $('.pl-update-view').fadeIn(1000);
        playlist_add_button_change_function(func);
    }
    else if (func == 'back-list-update') {
        $('.pl-list-view').hide();
        $('.pl-add-view').hide();
        $('.' + PL_ADD_VIEW_TYPE_CLASS).remove();
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
        back_list_scroll_top = $(window).scrollTop();
        playlist_add_button_change_function(func);
        $('.pl-list-view').hide();
        $('.pl-add-view').hide();
        $('.' + PL_ADD_VIEW_TYPE_CLASS).remove();
        $('.pl-update-view').hide();
        $('.pl-select-view').fadeIn(1000);
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
        $ev.html('<p class="h3"><i class="fas fa-minus"></i>&nbsp;&nbsp;Remove</p>');
        $ev.closest('.container-fluid').find('.pl-select-func').show();
    };
    if (tmr !== undefined && tmr!==null) {
        clearTimeout(parseInt(tmr));
        restoreDelButton($ev);
    }
    else {
        $ev.html('<p class="h3"><i class="fas fa-trash-restore"></i>&nbsp;&nbsp;&nbsp;5</p>');
        $ev.closest('.container-fluid').find('.pl-select-func').hide();
        let funDel = function() {
            let sec = parseInt(this.data('countdown')) - 1;
            if (sec) {
                this.html('<p class="h3"><i class="fas fa-trash-restore"></i>&nbsp;&nbsp;&nbsp;'+ sec +'</p>');
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
                        selected_playlist = null;
                        docCookies.setItem(COOKIE_SELECTEDPL, -1, Infinity);
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

function playlist_update_in_list(p) {
    let idxof = playlists_all.map(function(e) { return e.rowid; }).indexOf(p.rowid);
    if (idxof >= 0)
        $('#output-table').bootstrapTable('updateRow', {index: idxof, row: p, replace: true});
    return idxof;
}

function playlist_update_create_wake() {
    let $vid_row = $(`
        <video id="pl-update-view-wake" loop="1" style="display: none;">
            <source src="data:video/mp4;base64, AAAAHGZ0eXBNNFYgAAACAGlzb21pc28yYXZjMQAAAAhmcmVlAAAGF21kYXTeBAAAbGliZmFhYyAxLjI4AABCAJMgBDIARwAAArEGBf//rdxF6b3m2Ui3lizYINkj7u94MjY0IC0gY29yZSAxNDIgcjIgOTU2YzhkOCAtIEguMjY0L01QRUctNCBBVkMgY29kZWMgLSBDb3B5bGVmdCAyMDAzLTIwMTQgLSBodHRwOi8vd3d3LnZpZGVvbGFuLm9yZy94MjY0Lmh0bWwgLSBvcHRpb25zOiBjYWJhYz0wIHJlZj0zIGRlYmxvY2s9MTowOjAgYW5hbHlzZT0weDE6MHgxMTEgbWU9aGV4IHN1Ym1lPTcgcHN5PTEgcHN5X3JkPTEuMDA6MC4wMCBtaXhlZF9yZWY9MSBtZV9yYW5nZT0xNiBjaHJvbWFfbWU9MSB0cmVsbGlzPTEgOHg4ZGN0PTAgY3FtPTAgZGVhZHpvbmU9MjEsMTEgZmFzdF9wc2tpcD0xIGNocm9tYV9xcF9vZmZzZXQ9LTIgdGhyZWFkcz02IGxvb2thaGVhZF90aHJlYWRzPTEgc2xpY2VkX3RocmVhZHM9MCBucj0wIGRlY2ltYXRlPTEgaW50ZXJsYWNlZD0wIGJsdXJheV9jb21wYXQ9MCBjb25zdHJhaW5lZF9pbnRyYT0wIGJmcmFtZXM9MCB3ZWlnaHRwPTAga2V5aW50PTI1MCBrZXlpbnRfbWluPTI1IHNjZW5lY3V0PTQwIGludHJhX3JlZnJlc2g9MCByY19sb29rYWhlYWQ9NDAgcmM9Y3JmIG1idHJlZT0xIGNyZj0yMy4wIHFjb21wPTAuNjAgcXBtaW49MCBxcG1heD02OSBxcHN0ZXA9NCB2YnZfbWF4cmF0ZT03NjggdmJ2X2J1ZnNpemU9MzAwMCBjcmZfbWF4PTAuMCBuYWxfaHJkPW5vbmUgZmlsbGVyPTAgaXBfcmF0aW89MS40MCBhcT0xOjEuMDAAgAAAAFZliIQL8mKAAKvMnJycnJycnJycnXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXiEASZACGQAjgCEASZACGQAjgAAAAAdBmjgX4GSAIQBJkAIZACOAAAAAB0GaVAX4GSAhAEmQAhkAI4AhAEmQAhkAI4AAAAAGQZpgL8DJIQBJkAIZACOAIQBJkAIZACOAAAAABkGagC/AySEASZACGQAjgAAAAAZBmqAvwMkhAEmQAhkAI4AhAEmQAhkAI4AAAAAGQZrAL8DJIQBJkAIZACOAAAAABkGa4C/AySEASZACGQAjgCEASZACGQAjgAAAAAZBmwAvwMkhAEmQAhkAI4AAAAAGQZsgL8DJIQBJkAIZACOAIQBJkAIZACOAAAAABkGbQC/AySEASZACGQAjgCEASZACGQAjgAAAAAZBm2AvwMkhAEmQAhkAI4AAAAAGQZuAL8DJIQBJkAIZACOAIQBJkAIZACOAAAAABkGboC/AySEASZACGQAjgAAAAAZBm8AvwMkhAEmQAhkAI4AhAEmQAhkAI4AAAAAGQZvgL8DJIQBJkAIZACOAAAAABkGaAC/AySEASZACGQAjgCEASZACGQAjgAAAAAZBmiAvwMkhAEmQAhkAI4AhAEmQAhkAI4AAAAAGQZpAL8DJIQBJkAIZACOAAAAABkGaYC/AySEASZACGQAjgCEASZACGQAjgAAAAAZBmoAvwMkhAEmQAhkAI4AAAAAGQZqgL8DJIQBJkAIZACOAIQBJkAIZACOAAAAABkGawC/AySEASZACGQAjgAAAAAZBmuAvwMkhAEmQAhkAI4AhAEmQAhkAI4AAAAAGQZsAL8DJIQBJkAIZACOAAAAABkGbIC/AySEASZACGQAjgCEASZACGQAjgAAAAAZBm0AvwMkhAEmQAhkAI4AhAEmQAhkAI4AAAAAGQZtgL8DJIQBJkAIZACOAAAAABkGbgCvAySEASZACGQAjgCEASZACGQAjgAAAAAZBm6AnwMkhAEmQAhkAI4AhAEmQAhkAI4AhAEmQAhkAI4AhAEmQAhkAI4AAAAhubW9vdgAAAGxtdmhkAAAAAAAAAAAAAAAAAAAD6AAABDcAAQAAAQAAAAAAAAAAAAAAAAEAAAAAAAAAAAAAAAAAAAABAAAAAAAAAAAAAAAAAABAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAwAAAzB0cmFrAAAAXHRraGQAAAADAAAAAAAAAAAAAAABAAAAAAAAA+kAAAAAAAAAAAAAAAAAAAAAAAEAAAAAAAAAAAAAAAAAAAABAAAAAAAAAAAAAAAAAABAAAAAALAAAACQAAAAAAAkZWR0cwAAABxlbHN0AAAAAAAAAAEAAAPpAAAAAAABAAAAAAKobWRpYQAAACBtZGhkAAAAAAAAAAAAAAAAAAB1MAAAdU5VxAAAAAAALWhkbHIAAAAAAAAAAHZpZGUAAAAAAAAAAAAAAABWaWRlb0hhbmRsZXIAAAACU21pbmYAAAAUdm1oZAAAAAEAAAAAAAAAAAAAACRkaW5mAAAAHGRyZWYAAAAAAAAAAQAAAAx1cmwgAAAAAQAAAhNzdGJsAAAAr3N0c2QAAAAAAAAAAQAAAJ9hdmMxAAAAAAAAAAEAAAAAAAAAAAAAAAAAAAAAALAAkABIAAAASAAAAAAAAAABAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAGP//AAAALWF2Y0MBQsAN/+EAFWdCwA3ZAsTsBEAAAPpAADqYA8UKkgEABWjLg8sgAAAAHHV1aWRraEDyXyRPxbo5pRvPAyPzAAAAAAAAABhzdHRzAAAAAAAAAAEAAAAeAAAD6QAAABRzdHNzAAAAAAAAAAEAAAABAAAAHHN0c2MAAAAAAAAAAQAAAAEAAAABAAAAAQAAAIxzdHN6AAAAAAAAAAAAAAAeAAADDwAAAAsAAAALAAAACgAAAAoAAAAKAAAACgAAAAoAAAAKAAAACgAAAAoAAAAKAAAACgAAAAoAAAAKAAAACgAAAAoAAAAKAAAACgAAAAoAAAAKAAAACgAAAAoAAAAKAAAACgAAAAoAAAAKAAAACgAAAAoAAAAKAAAAiHN0Y28AAAAAAAAAHgAAAEYAAANnAAADewAAA5gAAAO0AAADxwAAA+MAAAP2AAAEEgAABCUAAARBAAAEXQAABHAAAASMAAAEnwAABLsAAATOAAAE6gAABQYAAAUZAAAFNQAABUgAAAVkAAAFdwAABZMAAAWmAAAFwgAABd4AAAXxAAAGDQAABGh0cmFrAAAAXHRraGQAAAADAAAAAAAAAAAAAAACAAAAAAAABDcAAAAAAAAAAAAAAAEBAAAAAAEAAAAAAAAAAAAAAAAAAAABAAAAAAAAAAAAAAAAAABAAAAAAAAAAAAAAAAAAAAkZWR0cwAAABxlbHN0AAAAAAAAAAEAAAQkAAADcAABAAAAAAPgbWRpYQAAACBtZGhkAAAAAAAAAAAAAAAAAAC7gAAAykBVxAAAAAAALWhkbHIAAAAAAAAAAHNvdW4AAAAAAAAAAAAAAABTb3VuZEhhbmRsZXIAAAADi21pbmYAAAAQc21oZAAAAAAAAAAAAAAAJGRpbmYAAAAcZHJlZgAAAAAAAAABAAAADHVybCAAAAABAAADT3N0YmwAAABnc3RzZAAAAAAAAAABAAAAV21wNGEAAAAAAAAAAQAAAAAAAAAAAAIAEAAAAAC7gAAAAAAAM2VzZHMAAAAAA4CAgCIAAgAEgICAFEAVBbjYAAu4AAAADcoFgICAAhGQBoCAgAECAAAAIHN0dHMAAAAAAAAAAgAAADIAAAQAAAAAAQAAAkAAAAFUc3RzYwAAAAAAAAAbAAAAAQAAAAEAAAABAAAAAgAAAAIAAAABAAAAAwAAAAEAAAABAAAABAAAAAIAAAABAAAABgAAAAEAAAABAAAABwAAAAIA
AAABAAAACAAAAAEAAAABAAAACQAAAAIAAAABAAAACgAAAAEAAAABAAAACwAAAAIAAAABAAAADQAAAAEAAAABAAAADgAAAAIAAAABAAAADwAAAAEAAAABAAAAEAAAAAIAAAABAAAAEQAAAAEAAAABAAAAEgAAAAIAAAABAAAAFAAAAAEAAAABAAAAFQAAAAIAAAABAAAAFgAAAAEAAAABAAAAFwAAAAIAAAABAAAAGAAAAAEAAAABAAAAGQAAAAIAAAABAAAAGgAAAAEAAAABAAAAGwAAAAIAAAABAAAAHQAAAAEAAAABAAAAHgAAAAIAAAABAAAAHwAAAAQAAAABAAAA4HN0c3oAAAAAAAAAAAAAADMAAAAaAAAACQAAAAkAAAAJAAAACQAAAAkAAAAJAAAACQAAAAkAAAAJAAAACQAAAAkAAAAJAAAACQAAAAkAAAAJAAAACQAAAAkAAAAJAAAACQAAAAkAAAAJAAAACQAAAAkAAAAJAAAACQAAAAkAAAAJAAAACQAAAAkAAAAJAAAACQAAAAkAAAAJAAAACQAAAAkAAAAJAAAACQAAAAkAAAAJAAAACQAAAAkAAAAJAAAACQAAAAkAAAAJAAAACQAAAAkAAAAJAAAACQAAAAkAAACMc3RjbwAAAAAAAAAfAAAALAAAA1UAAANyAAADhgAAA6IAAAO+AAAD0QAAA+0AAAQAAAAEHAAABC8AAARLAAAEZwAABHoAAASWAAAEqQAABMUAAATYAAAE9AAABRAAAAUjAAAFPwAABVIAAAVuAAAFgQAABZ0AAAWwAAAFzAAABegAAAX7AAAGFwAAAGJ1ZHRhAAAAWm1ldGEAAAAAAAAAIWhkbHIAAAAAAAAAAG1kaXJhcHBsAAAAAAAAAAAAAAAALWlsc3QAAAAlqXRvbwAAAB1kYXRhAAAAAQAAAABMYXZmNTUuMzMuMTAw">
            <source src="data:video/ogg;base64, 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AAAAAAAAJE0DLE8DNM8DAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAEDSNEDzPEDzPAAAAAAAAADQPA/wPBHwRBEAAAAAAAAALM8DNNEDPFEEAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAEDSNEDzPEDzPAAAAAAAAACwPA/wRBHQPBEAAAAAAAAALM8DPFEEPNEDAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAQAAAQ4AAAEGAhFBqyIgCIEwBwSBIkCZIEzQNIlgVNg6bBNAGSZUHToGkwTQAAAAAAAAAAAAAk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" type="video/ogg">
            <source src="data:video/webm;base64, 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" type="video/webm">                             
        </video>
    `);
    $('body').append($vid_row);
    $vid_row.trigger('play');
}

function playlist_update_destroy_wake() {
    let $row = $('#pl-update-view-wake');
    $row.trigger('pause');
    $row.remove();
}

function index_global_init() {
    $('#playlist-items-table').bootstrapTable({showHeader: false});
    $('.pl-select-view').hide();
    $('.pl-add-view').hide();
    $('.pl-update-view').hide();
    let $table =  $('#output-table');
    $table.bootstrapTable({showHeader: false});
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
            docCookies.setItem(COOKIE_SELECTEDPL, -1, Infinity);
            playlist_interface_manage('add');
        }
        else if (func == 'back-playlist-update')
            playlist_interface_manage('back-list');
        else if (func == 'back-list') {
            selected_playlist = null;
            docCookies.setItem(COOKIE_SELECTEDPL, -1, Infinity);
            playlist_interface_manage('add');
        }
        else if (func == 'back-list-add') {
            selected_playlist = null;
            docCookies.setItem(COOKIE_SELECTEDPL, -1, Infinity);
            playlist_interface_manage('add');
        }
        else {
            playlist_interface_manage('back-list-add');
            playlist_add(new Playlist(null, playlist_user));
        }
        return false;
    });
    $('#remove-button').click(function() {
        playlist_remove(this);
        return false;
    });
    playlist_show_button_change_function();
    $('#show-button').click(function() {
        playlist_show_button_change_function();
        return false;
    });
    $('#play-button').click(function() {
        if (!$('#play-button').hasClass('disabled') && selected_playlist.items.length)
            window.location.assign(MAIN_PATH_S + 'play/workout.htm?name=' + selected_playlist.name);
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
        playlist_change_type(new Playlist(null, playlist_user), $(this).val());
    });
    $('#pl-update-view-update').click(function () {
        $('#pl-update-view-progress').show();
        playlist_update_create_wake();
        $('#pl-update-view-update').hide();
        let qel = new MainWSQueueElement({
            cmd: CMD_REFRESH, 
            playlist:current_playlist,
            datefrom:Date.parse($('#pl-update-view-date-start').val()),
            dateto:Date.parse($('#pl-update-view-date-end').val()) + 86399999,
        }, function(msg) {
            if (msg.cmd == CMD_PING)
                return 0;
            else if (msg.cmd == CMD_REFRESH)
                return msg;
            else
                return null;
        }, 50000, 1);
        qel.enqueue().then(function(msg) {
            $('#pl-update-view-progress').hide();
            playlist_update_destroy_wake();
            $('#pl-update-view-update').show();
            if (!manage_errors(msg)) {
                if (!msg.n_new)
                    toast_msg('No new video found', 'warning');
                else
                    toast_msg('I have found ' + msg.n_new +' new video(s).', 'success');
                if (selected_playlist) {
                    let idx = playlist_update_in_list(msg.playlist);
                    playlists_all[idx] = selected_playlist = msg.playlist;
                    $('#playlist-items-table').bootstrapTable('load', [...selected_playlist.items]);
                    playlist_show_button_change_function('same');
                    set_button_enabled('#play-button', selected_playlist.items.length);
                }
                else {
                    playlists_all.push(msg.playlist);
                    $('#output-table').bootstrapTable('append', [msg.playlist]);
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
                playlist_update_destroy_wake();
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
    const urlParams = new URLSearchParams(URL_PARAMS);
    let tmpi, el = new MainWSQueueElement({
        cmd: CMD_DUMP,
        useri:playlist_user,
        playlist: plid,
        load_all: urlParams.has('all') && !isNaN(tmpi = parseInt(urlParams.get('all'))) && tmpi? 1: 0,
    }, function(msg) {
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


function playlists_dump(params, fast_videoidx, fast_videostep) {
    let urlParams = new URLSearchParams(URL_PARAMS);
    let tmpi;
    let content_obj = {
        cmd: CMD_DUMP,
        playlist: null,
        useri: playlist_user,
        load_all: urlParams.has('all') && !isNaN(tmpi = parseInt(urlParams.get('all'))) && tmpi? 1: 0,
        fast_videoidx: fast_videoidx == undefined?(urlParams.has('vidx') && isNaN(tmpi = parseInt(urlParams.get('vidx')))? null: (urlParams.has('vidx')? tmpi: -9)):fast_videoidx + fast_videostep //zip: alternativamente fast_videoidx===undefined? /*0 per load a pezzi: null per load tutto in una botta*/ 0:fast_videoidx + fast_videostep
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
            if (!Array.isArray(msg.playlists)) {
                // Pako magic
                let arr        = pako.inflate(new Uint8Array(atob(msg.playlists).split('').map(function(x){return x.charCodeAt(0);})));

                // Convert gunzipped byteArray back to ascii string:
                let s = '';
                for(let i = 0; i< arr.length; i+=4096) {
                    let end = i + 4096;
                    if (end > arr.length)
                        end = arr.length;
                    s += String.fromCharCode(... arr.slice(i, end));
                }
                msg.playlists     = JSON.parse(s);
            }
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
                if (msg.fast_videostep && p.items.length === msg.fast_videostep)
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
                playlists_dump(null, msg.fast_videoidx, msg.fast_videostep);
            }
        }
    })
        .catch(function(err) {
            console.log(err);
            let errmsg = 'Exception detected: '+err;
            if (params)
                params.error(errmsg);
            toast_msg(errmsg, 'danger');
            bootstrap_table_get_data_ws(params);
        });
}

function bootstrap_table_get_data_ws(params) {
    find_user_cookie().then(function(useri) {
        playlist_user = useri;
        main_ws_reconnect();
        playlists_all = [];
        playlists_dump(params);
    }).catch(function() {
        manage_errors({rv: 501, err: 'Cannot find user cookie!'});
    });
}

function playlist_select(ev) {
    if (ev.rowid !== undefined) {
        selected_playlist = ev;
    }
    else {
        let rid = parseInt($(ev).data('rowid'));
        playlist_interface_manage('back-list');
        $(window).scrollTop(0);
        selected_playlist = playlists_all[playlists_all.map(function(e) { return e.rowid; }).indexOf(rid)];
    }
    set_button_enabled('#play-button', selected_playlist.items.length);
    $('#playlist-items-table').bootstrapTable('load', [...selected_playlist.items]);
    playlist_show_button_change_function('show');
    docCookies.setItem(COOKIE_SELECTEDPL, selected_playlist.rowid, Infinity);
}

function bootstrap_table_name_formatter(value, row, index, field) {
    let unseen = null;
    for (let r of row.items) {
        if (!r.seen) {
            unseen = r;
            break;
        }
    }
    return `
    <a data-rowid="${row.rowid}" href="#" onclick="playlist_select(this); return false;"><div class="thumb-container">
        <img src="${unseen?playlist_transform_thumbnail_path(unseen.img):'./img/no-videos.png'}" class="thumb-image">
        <div class="thumb-name-overlay-${bootstrap_breakpoint.name}">${value}</div>
    </div></a>
        ` + '<br />' + bootstrap_table_info_formatter(value, row, index, field);
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
    else if (row.type == 'mediaset')
        tpstr += '<span class="badge badge-secondary even-larger-badge">mediaset</span>&nbsp;&nbsp;';
    else
        tpstr += '<span class="badge badge-warning even-larger-badge">localfolder</span>&nbsp;&nbsp;';
    let nitems = 0;
    for (let r of row.items) {
        if (!r.seen)
            nitems ++;
    }
    let nm;
    let large = bootstrap_breakpoint && ((nm = bootstrap_breakpoint.name) == 'xl' || nm=='lg' || nm == 'xxl');
    tpstr += `
    <p class="${large?'h3':'h6'}">
    Last Updated: ${d.format('yyyy/mm/dd')} (${nitems} items - ${format_duration(playlist_total_duration(row))}) - AutoUpdate ${row.autoupdate?'<i class="fas fa-check">':'<i class="fas fa-times">'}</i></p>`;
    return tpstr;
}

$(window).on('load', function() {
    bootstrap_breakpoint =  bootstrapDetectBreakpoint();
    xl = bootstrap_breakpoint && bootstrap_breakpoint.name == 'xl';
    console.log('BP = ' + JSON.stringify(bootstrap_breakpoint));
    if (bootstrap_breakpoint && bootstrap_breakpoint.name && (bootstrap_breakpoint.name == 'xs' || bootstrap_breakpoint.name == 'sm')) {
        $('th[data-field="img"]').addClass('col-7');
    }
    console.log(new Date().format('yyyy/mm/dd'));
    index_global_init();
});