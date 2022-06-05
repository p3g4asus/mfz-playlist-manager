var video_auto_next = true;

//debug 'grabber=youtube&par=UUXDorkXBjDsh0wNethPe-zQ&grabber=youtube&par=wP6l4MD1tTc&grabber=personal&par=subs'
const VIDEO_STATUS_UNSTARTED = -1;
const VIDEO_STATUS_ENDED = 0;
const VIDEO_STATUS_PLAYING = 1;
const VIDEO_STATUS_PAUSED = 2;
const VIDEO_STATUS_BUFFERING = 3;
const VIDEO_STATUS_CUED = 5;
const workout_file = 'workout.htm';
const lastconf_key = 'lastconf';
const TWITCH_CLIENT_ID = '318czv1wdow8qwvx5offlit5ul8klg';
const TWITCH_VIDEO_ID_PRE = '____';
var urlParams = null;
var video_width = null;
var video_height = null;
const host_url = (!location.host || location.host.length == 0)?'192.168.25.24:7666':location.host;
let search_var = (location.protocol.startsWith('file')?window.location.hash:window.location.search).substring(1);


function dyn_module_load(link, onload, type) {
    let tag;
    if (type == 'css') {
        tag = document.createElement('link');
        tag.setAttribute('rel', 'stylesheet');
        tag.setAttribute('type', 'text/css');
        tag.setAttribute('href', link);
    }
    else {
        tag = document.createElement('script');
        tag.type = 'text/javascript';
        
        if (link.startsWith('//'))
            tag.text = link.substring(2);
        else
            tag.src = link;
    }
    if (onload) {
        tag.addEventListener('load', function(event) {
            console.log('script loaded ' + link);
            onload();
        });
    }
    let firstScriptTag = document.getElementsByTagName('script')[0];
    firstScriptTag.parentNode.insertBefore(tag, firstScriptTag);
}