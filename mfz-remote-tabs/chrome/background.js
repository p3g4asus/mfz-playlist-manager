let ping_interval = -1;
let tab_removed_time = 0;
let tab_removed_window = null;
let tab_history = {};

function send_video_info_for_remote_play(w, video_info, exp) {
    let o = {cmd: CMD_REMOTEPLAY_PUSH, what: w};
    o[w] = video_info;
    o.exp = exp;
    let el = new MainWSQueueElement(o, ((msg) => {
        return msg.cmd === CMD_REMOTEPLAY_PUSH? msg:null;
    }), 3000, 1, '$' + w);
    return el.enqueue().then((msg) => {
        if (!msg.rv) {
            console.log('Remoteplay push ok ' + JSON.stringify(msg.what));
        }
        else {
            console.log('Remoteplay push fail: ' + JSON.stringify(msg));
        }
        return msg;
    })
        .catch((err) => {
            if (err)
                console.log('Remoteplay push fail ' + err);
            return err;
        });
}

function sendListTabs(tabs) {
    let lstTabs = [];
    let imgs = {};

    for (let tab of tabs) {
        lstTabs.push({id: tab.id, title: tab.title, url:tab.url, active: tab.active, ico: null});
        imgs['ic' + tab.id] = tab.favIconUrl;
    }
    send_video_info_for_remote_play('tabs', lstTabs);
    send_video_info_for_remote_play('imgs', imgs, true);
}

function getTabId(msgid) {
    if (msgid && msgid !== 'None') {
        if (Array.isArray(msgid)) {
            const out = [];
            for (let i of msgid) {
                out.push(parseInt(i));
            }
            msgid = out;
        } else msgid = parseInt(msgid);
        return Promise.resolve(msgid);
    }
    let ok,ko;
    const p = new Promise((resolve, reject) => {
        ok = resolve;
        ko = reject;
    });
    browser.tabs.query({currentWindow: true, active: true}).then((tabs) => {
        const ids = [];
        for (let tab of tabs) {
            ids.push(tab.id);
        }
        ok(ids);
    }).catch(ko);
    return p;
}

function updateCount(tabId, isOnRemoved) {
    browser.tabs.query({currentWindow: true})
        .then((tabs) => {
            let length = tabs.length;

            // onRemoved fires too early and the count is one too many.
            // see https://bugzilla.mozilla.org/show_bug.cgi?id=1396758
            if (isOnRemoved && tabId && tabs.map((t) => { return t.id; }).includes(tabId)) {
                length--;
            }

            browser.browserAction.setBadgeText({text: length.toString()});
            if (length > 2) {
                browser.browserAction.setBadgeBackgroundColor({'color': 'green'});
            } else {
                browser.browserAction.setBadgeBackgroundColor({'color': 'red'});
            }
            sendListTabs(tabs);
        });
}

function remotejs_process(msg) {
    try {
        if (msg.sub == CMD_REMOTEBROWSER_JS_ACTIVATE) {
            browser.tabs.update(parseInt(msg.id), {active: true}).then(() => {
                console.log(msg.id + ' Tab activate ok');
            }).catch(() => {
                console.warn(msg.id + ' Tab activate fail');
            });
        }
        else if (msg.sub == CMD_REMOTEBROWSER_JS_RELOAD) {
            browser.tabs.reload(parseInt(msg.id)).then(() => {
                console.log(msg.id + ' Tab reload ok');
            }).catch(() => {
                console.warn(msg.id + ' Tab reload fail');
            });
        }
        else if (msg.sub == CMD_REMOTEBROWSER_JS_CLOSE) {
            getTabId(msg.id).then((ids) => {
                browser.tabs.remove(ids).then(() => {
                    console.log(msg.id + ' Tab close ok');
                });
            }).catch(() => {
                console.warn(msg.id + ' Tab close fail');
            });
        }
        else if (msg.sub == CMD_REMOTEBROWSER_JS_GOTO) {
            if (msg.id == 'New') {
                browser.tabs.create({url: msg.url, active: msg.act === 'true' || msg.act === 'True' || msg.act === true}).then(() => {
                    console.log(msg.url + ' Tab create ok');
                }).catch(() => {
                    console.warn(msg.url + ' Tab create fail');
                });
            } else {
                browser.tabs.update(msg.id == 'None'?undefined:parseInt(msg.id), {url: msg.url, active: msg.act === 'true' || msg.act === 'True' || msg.act === true}).then(() => {
                    console.log(msg.id + ' Tab update ok');
                }).catch(() => {
                    console.warn(msg.id + ' Tab update fail');
                });
            }
        }
    }
    catch (e) {
        console.error(e.stack);
    }
    remotejs_enqueue();
}

function remotejs_recog(msg) {
    return msg.cmd === CMD_REMOTEBROWSER_JS? msg:null;
}

function remotejs_enqueue() {
    let el2 = new MainWSQueueElement(null, remotejs_recog, 0, 1, 'remotejs');
    el2.enqueue().then(remotejs_process);
}

function logStorageChange(changes) {
    if (changes.tabControl) {
        console.log('Setting change detected: reconnecting...');
        reconnect_ws(changes.tabControl.newValue);
    }
}

function reconnect_ws_onopen2() {
    updateCount();
    remotejs_enqueue();
    if (ping_interval < 0)
        ping_interval = setInterval(() => {
            send_video_info_for_remote_play('ping', new Date().getTime());
        }, 15000);
    let o = {cmd: CMD_REMOTEPLAY};
    let el = new MainWSQueueElement(o, ((msg) => {
        return msg.cmd === CMD_REMOTEPLAY? msg:null;
    }), 3000, 1, 'remoteplay');
    return el.enqueue().then((msg) => {
        if (!msg.rv) {
            console.log('Remoteplay ok ' + JSON.stringify(msg.what));
        }
        else {
            console.log('Remoteplay fail: ' + JSON.stringify(msg));
        }
        return msg;
    })
        .catch((err) => {
            console.log('Remoteplay fail ' + err);
            return err;
        });
}

function reconnect_ws(tc) {
    let res;
    if (tc?.url && (res = (new RegExp('https://([^/]+)/([^\\-]+)-s/play/player_remote_commands\\.htm\\?hex=([a-f0-9]+)')).exec(tc.url))) {
        const urlws = `wss://${res[1]}/${res[2]}-ws/g${res[3]}`;
        console.log('Asking to reconnect with websocket url ' + urlws);
        main_ws_reconnect(reconnect_ws_onopen2,urlws);
    } else {
        console.log('Invalid url detected: ' + tc?.url);
    }
}

browser.tabs.onRemoved.addListener(
    (tabId, remI) => {
        console.log('[TAB] Removed ' + tabId);
        const wid = remI.windowId;
        if (remI.isWindowClosing) {
            tab_history[wid] = undefined;
        } else {
            const index = !tab_history[wid]?-1:tab_history[wid].indexOf(tabId);
            tab_removed_time = new Date().getTime();
            if (index > -1) { // only splice array when item is found
                tab_history[wid].splice(index, 1); // 2nd parameter means remove one item only
            }
            tab_removed_window = wid;
        }
        updateCount(tabId, true);
    });
browser.tabs.onCreated.addListener(
    (tabId) => {
        console.log('[TAB] Created ' + tabId.id);
        updateCount(tabId, false);
    });
browser.tabs.onActivated.addListener(
    (actI) => {
        const myId = actI.tabId;
        console.log('[TAB] Activated ' + myId);
        let in_tab_hist = true;
        const wid = actI.windowId;
        if (tab_removed_time) {
            if (tab_removed_window == wid) {
                if (tab_history[wid] && tab_history[wid].length) {
                    const hist_id = tab_history[wid][tab_history[wid].length - 1];
                    if (new Date().getTime() - tab_removed_time < 700) {
                        if (myId !== hist_id) {
                            browser.tabs.update(hist_id, {active: true}).then(() => {
                                console.log(hist_id + ' Tab update ok');
                            }).catch(() => {
                                console.warn(hist_id + ' Tab update fail');
                            });
                        }
                        in_tab_hist = false;
                    }
                }
                tab_removed_time = 0;
            }
        }
        if (in_tab_hist) {
            if (!tab_history[wid]) tab_history[wid] = [];
            else {
                const idx = tab_history[wid].indexOf(myId);
                if (idx >= 0)
                    tab_history[wid].splice(idx, 1);
            }
            tab_history[wid].push(myId);
        }
        updateCount(myId, false);
    });
browser.tabs.onUpdated.addListener(
    (tabId) => {
        console.log('[TAB] Updated ' + tabId);
        updateCount(tabId, false);
    });
browser.storage.local.onChanged.addListener(logStorageChange);

browser.storage.local.get().then((restoredSettings) => {
    reconnect_ws(restoredSettings?.tabControl || {});
});
browser.windows.onFocusChanged.addListener(
    (windowId) => { updateCount(null, false); }
);
updateCount();
