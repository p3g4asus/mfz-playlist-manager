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
const CMD_REMOTEBROWSER_JS = 'remb';
const CMD_REMOTEBROWSER_JS_CLOSE = 'close';
const CMD_REMOTEBROWSER_JS_ACTIVATE = 'on';
const CMD_REMOTEBROWSER_JS_GOTO = 'goto';

const COLORS = {
    'info': ['#fff', '#17a2b8'],
    'danger': ['#fff', '#dc3545'],
    'success': ['#fff', '#28a745'],
    'secondary': ['#fff', '#6c757d'],
    'primary': ['#fff', '#007bff'],
    'light': ['#343a40', '#f8f9fa'],
    'dark': ['#fff', '#343a40'],
    'white': ['#343a40', '#fff'],
};

function toast_msg(msg, type) {
    let col = COLORS[type];
    if (!col) col = COLORS['info'];
    $('#error-msg').append($('<p>').attr('style', `color:${col[0]};background-color:${col[1]}`).text(msg));
    setTimeout(() => {
        $('#error-msg').empty();
    }, 10000);
}

function manage_errors(msg) {
    if (msg.rv) {
        let errmsg = 'E [' + msg.rv + '] ' + msg.err+ '.'; 
        toast_msg(errmsg, 'danger');
        return errmsg;
    }
    else
        return null;
    
}