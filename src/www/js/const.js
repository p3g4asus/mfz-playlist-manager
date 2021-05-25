const COOKIE_LOGIN = 'API_SESSION';
const COOKIE_USERID = 'Userid';
const COOKIE_SELECTEDPL = 'SelectedPl';
const MAIN_PATH = '/static/';
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
    let cookies = document.cookie.split(';');
    for (let c of cookies) {
        console.log('cccc ' + c);
        let splt = c.trim().split('=');
        if (splt[0] == COOKIE_USERID)
            return parseInt(splt[1]);
    }
    return null;
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