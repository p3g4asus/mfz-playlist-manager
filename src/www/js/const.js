const COOKIE_LOGIN = 'API_SESSION';
const COOKIE_USERID = 'Userid';
const COOKIE_SELECTEDPL = 'SelectedPl';
const MAIN_PATH_S = location.protocol == 'https:'?(location.href.indexOf('tst') > 0?'/tst-s/':'/pm-s/'):'/static/';
const MAIN_PATH = location.protocol == 'https:'?(location.href.indexOf('tst') > 0?'/tst-n/':'/pm/'):'/';
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
const CMD_LS = 'ls';
const CMD_RAI_CONTENTSET = 'rai.contentset';
const CMD_YT_PLAYLISTCHECK = 'youtube.playlistcheck';
const CMD_MEDIASET_BRANDS = 'mediaset.brands';
const CMD_MEDIASET_LISTINGS = 'mediaset.listings';
const CMD_RAI_LISTINGS = 'rai.listings';
const PL_ADD_VIEW_TYPE_CLASS = 'pl-add-view-type-class';
const GOOGLE_CLIENT_ID = '60860343069-fg6qgf1fogpjrb6femd2p7n0l9nsq4vt.apps.googleusercontent.com';

function pad(num, size) {
    num = num.toString();
    while (num.length < size) num = '0' + num;
    return num;
}

function toast_msg(msg, type, html) {
    let div = $('<p class="h5">');
    let el = $(
        `
        <div class="col-md-12 alert alert-${type} alert-dismissible fade show" role="alert">
            ${(html?div.html(msg):div.text(msg)).prop('outerHTML')}
            <button type="button" class="close" data-dismiss="alert" aria-label="Close">
                <span aria-hidden="true">&times;</span>
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
    let rid = docCookies.getItem(COOKIE_USERID);
    return rid !== null?parseInt(rid):null;
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

let URL_PARAMS_APPEND = location.protocol.startsWith('file')?window.location.hash:window.location.search;
let URL_PARAMS = URL_PARAMS_APPEND.substring(1);
let URL_PARAMS_SEPARATOR = location.protocol.startsWith('file')?'#':'?';