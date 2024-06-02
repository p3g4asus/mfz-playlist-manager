const PTHREG = /^\/([a-z0-9]+)/.exec(location.pathname);
const TERM = PTHREG?'_' + PTHREG[1]:'';
const COOKIE_LOGIN = 'API_SESSION' + TERM;
const COOKIE_USERID = 'Userid' + TERM;
const COOKIE_SELECTEDPL = 'SelectedPl' + TERM;
const COOKIE_PLAYSETT = 'playsett' + TERM;
const MAIN_PATH_S = location.protocol == 'https:'?(PTHREG?'/' + PTHREG[1] + '-s/':'/pm-s/'):'/static/';
const MAIN_PATH = location.protocol == 'https:'?(PTHREG?'/' + PTHREG[1] + '/':'/pm/'):'/';
const CMD_DEL = 'del';
const CMD_REN = 'ren';
const CMD_DUMP = 'dump';
const CMD_ADD = 'add';
const CMD_MOVE = 'move';
const CMD_SEEN = 'seen';
const CMD_SYNC = 'sync';
const CMD_SORT = 'sort';
const CMD_IORDER = 'iorder';
const CMD_CLOSE = 'close';
const CMD_PING = 'ping';
const CMD_REFRESH = 'refresh';
const CMD_PLAYID = 'playid';
const CMD_PLAYSETT = 'playsett';
const CMD_PLAYITSETT = 'playitsett';
const CMD_REMOTEPLAY = 'remote';
const CMD_REMOTEPLAY_JS = 'remotejs';
const CMD_REMOTEPLAY_JS_PAUSE = 'pause';
const CMD_REMOTEPLAY_JS_NEXT = 'next';
const CMD_REMOTEPLAY_JS_DEL = 'nextdel';
const CMD_REMOTEPLAY_JS_PREV = 'prev';
const CMD_REMOTEPLAY_JS_FFW = 'ffw';
const CMD_REMOTEPLAY_JS_REW = 'rew';
const CMD_REMOTEPLAY_JS_GOTO = 'goto';
const CMD_REMOTEPLAY_JS_SEC = 'sec';
const CMD_REMOTEPLAY_JS_RATE = 'rate';
const CMD_REMOTEPLAY_JS_TELEGRAM = 'telegram';
const CMD_REMOTEPLAY_PUSH = 'remotepush';
const CMD_LS = 'ls';
const CMD_TOKEN = 'token';
const CMD_RAI_CONTENTSET = 'rai.contentset';
const CMD_YT_PLAYLISTCHECK = 'youtube.playlistcheck';
const CMD_MEDIASET_BRANDS = 'mediaset.brands';
const CMD_MEDIASET_LISTINGS = 'mediaset.listings';
const CMD_MEDIASET_KEYS = 'mediaset.keys';
const CMD_RAI_LISTINGS = 'rai.listings';
const CMD_FOLDER_LIST = 'localfolder.folderlist';
const PL_ADD_VIEW_TYPE_CLASS = 'pl-add-view-type-class';
const GOOGLE_CLIENT_ID = '60860343069-fg6qgf1fogpjrb6femd2p7n0l9nsq4vt.apps.googleusercontent.com';
const DOWNLOADED_SUFFIX = '_d';
const WS_URL = location.protocol == 'https:'?'wss://' + location.host + (PTHREG?'/' + PTHREG[1] + '-ws/':'/pm-ws/'):'ws://' + location.host + '/ws';

function pad(num, size) {
    num = num.toString();
    while (num.length < size) num = '0' + num;
    return num;
}

function manage_errors(msg) {
    if (msg.rv) {
        let errmsg = 'E [' + msg.rv + '] ' + msg.err+ '.'; 
        if (msg.rv == 501 || msg.rv == 502)
            errmsg +=' Redirecting to login.';
        toast_msg(errmsg, 'danger');
        if (msg.rv == 501 || msg.rv == 502)
            setTimeout(function() {
                let urlp = window.location.href?('?urlp=' + encodeURIComponent(window.location.href)):URL_PARAMS_APPEND;
                window.location.assign(MAIN_PATH_S + 'login.htm' + urlp);
            }, 5000);
        return errmsg;
    }
    else
        return null;
    
}

function add_playlist_to_button(item, selector, onclick) {
    let li = $('<li>');
    let a = $('<a>');
    a.attr('href', '#');
    a.attr('data-pls', item?item:' ');
    a.addClass('dropdown-item');
    a.text(item?item:'Home');
    a.click(onclick?onclick:function (e) {
        window.location.assign(MAIN_PATH_S + (item?'play/workout.htm?name=' + encodeURIComponent(item): 'index.htm'));
    });
    li.append(a);
    $((selector?selector:'#playlist_cont') + ' > .dropdown-menu').append(li);
}

function toast_msg(msg, type, html) {
    let div = $('<p class="h5">');
    let v5 = jQuery.fn.tooltip.Constructor.VERSION.startsWith('5.');
    let el = $(
        `
        <div class="col-md-12 alert alert-${type} alert-dismissible fade show" role="alert">
            ${(html?div.html(msg):div.text(msg)).prop('outerHTML')}
            <button type="button" class="${v5?'btn-':''}close" data${v5?'-bs':''}-dismiss="alert" aria-label="Close">
                ${v5?'':'<span aria-hidden="true">&times;</span>'}
            </button>
        </div>
        `);
    el.alert();
    $('#alert-row').empty().append(el);
    setTimeout(function() {
        el.alert('close');
    }, 10000);
}

function find_user_cookie() {
    let rid;/* = docCookies.getItem(COOKIE_USERID);
    if (rid !== null)
        return Promise.resolve(parseInt(rid));
    else*/ {
        let okf, failf;
        let p = new Promise(function(resolve, reject) {
            okf = resolve;
            failf = reject;
        });
        $.get(MAIN_PATH, function() {
            rid = docCookies.getItem(COOKIE_USERID);
            if (rid === null)
                failf();
            else
                okf(parseInt(rid));
        }).fail(failf);
        return p;
    }
}

function format_duration(secs) {
    let hh = Math.floor(secs / 3600);
    let rem = secs % 3600;
    let mm = Math.floor(rem / 60);
    let ss = rem % 60;
    if (hh > 0) {
        return '' + hh +'h ' + pad(mm, 2) + 'm ' + pad(ss, 2) + 's';
    }
    else if (mm > 0) {
        return mm + 'm ' + pad(ss, 2) + 's';
    }
    else
        return ss + 's';
}

function bootstrapDetectBreakpoint() {
    const breakpointNames = ['xl', 'lg', 'md', 'sm', 'xs'];
    let breakpointValues = [];
    for (const breakpointName of breakpointNames) {
        breakpointValues[breakpointName] = window.getComputedStyle(document.documentElement).getPropertyValue('--breakpoint-' + breakpointName);
    }
    let i = breakpointNames.length;
    for (const breakpointName of breakpointNames) {
        i--;
        if (window.matchMedia('(min-width: ' + breakpointValues[breakpointName] + ')').matches) {
            return {name: breakpointName, index: i};
        }
    }
    return null;
}

function generate_rand_string(nchars) {
    if (window.crypto && window.crypto.getRandomValues) {
        nchars = nchars || 16;
        var rnd = new Uint8Array(nchars);
        window.crypto.getRandomValues(rnd);
        var cpn = '';
        for (var c = 0; c < nchars; c++)
            cpn += 'ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789-_'.charAt(rnd[c] & 63);
        return cpn;
    }
    return '';
}

let URL_PARAMS_APPEND = location.protocol.startsWith('file')?window.location.hash:window.location.search;
let URL_PARAMS = URL_PARAMS_APPEND.substring(1);
let URL_PARAMS_SEPARATOR = location.protocol.startsWith('file')?'#':'?';