let main_ws = null;
let main_ws_queue = [];

class MainWSQueueElement {
    constructor(msg_to_send, _inner_process, timeout, retry_num, name) {
        this.msg_to_send = msg_to_send;
        this.needs_to_send = msg_to_send != null;
        this.timeout = timeout;
        this.name = name;
        this.retry_num = retry_num || 1;
        this.timer = null;
        this.resolve = null;
        this.reject = null;
        this._inner_process = _inner_process;
    }

    inner_process_msg(msg) {
        if (this._inner_process)
            return this._inner_process(msg);
        else
            return {};
    }

    process_arrived_msg(msg) {
        let out = this.inner_process_msg(msg);
        // con out = 0 non far scattare il timeout e continua ad aspettare riarmando il timeout
        if (out || out === 0) {
            let rearm = false;
            if (this.timer !==null) {
                clearTimeout(this.timer);
                this.timer = null;
                rearm = true;
            }
            if (this.resolve && out)
                setTimeout(function() { this.resolve(out); }.bind(this), 0);
            else if (!out && rearm && this.timeout)
                this.timer = setTimeout(this.timeout_action.bind(this), this.timeout);
        }
        return out;
    }

    timeout_action() {
        this.timer = null;
        if (this.retry_num == 0) {
            main_ws_dequeue(this);
            if (this.reject) {
                this.reject(new Error('Timeout error detected: queue ' + this.name));
            }
        }
        else {
            this.needs_to_send = true;
            main_ws_enqueue();
        }
    }

    enqueue() {
        main_ws_enqueue(this);
        return new Promise(function(resolve, reject) {
            this.resolve = resolve;
            this.reject = reject;
        }.bind(this));
    }

    pop_msg_to_send() {
        if (this.needs_to_send) {
            this.needs_to_send = false;
            if ((this.retry_num < 0 || this.retry_num > 0) && this.timeout)
                this.timer = setTimeout(this.timeout_action.bind(this), this.timeout);
            if (this.retry_num > 0)
                this.retry_num--;
            return this.msg_to_send;
        }
        else
            return null;
    }
}

function main_ws_dequeue(el) {
    let idx = main_ws_queue.indexOf(el);
    if (idx >= 0) {
        main_ws_queue.splice(idx, 1);
    }
}
function main_ws_qel_exists(name) {
    if (!name)
        return false;
    for (let el of main_ws_queue)
        if (el.name == name)
            return true;
    return false;
}

function main_ws_enqueue(el) {
    if (el)
        main_ws_queue.push(el);
    if (main_ws)
        main_ws_queue_process();
}

function main_ws_queue_process(msg) {
    if (!main_ws)
        return;
    let jsonobj;
    for (let i = 0; i < main_ws_queue.length; i++) {
        let el = main_ws_queue[i];
        if ((jsonobj = el.pop_msg_to_send())) {
            let logString = JSON.stringify(jsonobj);
            main_ws.send(logString);
            console.log('WS >> ' + logString);
        }
        else if (msg) {
            if (el.process_arrived_msg(msg)) {
                main_ws_queue.splice(i, 1);
                i--;
                msg = null;
            }
        }
    }
}

function main_ws_reconnect(onopen2) {
    if (main_ws) {
        main_ws.close();
        main_ws = null;
    }
    else {
        main_ws_connect(onopen2);
    }
}


function main_ws_connect(onopen2) {
    let socket = new WebSocket(location.protocol == 'https:'?'wss://' + location.host + (PTHREG?'/' + PTHREG[1] + '-ws/':'/pm-ws/'):'ws://' + location.host + '/ws');
    socket.onopen = function (event) {
        console.log('Upgrade HTTP connection OK');
        main_ws = socket;
        main_ws_queue_process();
        if (onopen2)
            onopen2();
    };
    socket.onclose = function(e) {
        main_ws = null;
        console.log('Socket is closed. Reconnect will be attempted in 10 second.', e.reason);
        setTimeout(function() {
            main_ws_connect(onopen2);
        }, 10000);
    };

    socket.onerror = function(err) {
        main_ws = null;
        console.error('Socket encountered error: ', err.message, 'Closing socket');
        socket.close();
    };
    socket.onmessage = function (event) {
        console.log(event.data);
        let msg = JSON.parse(event.data);
        main_ws_queue_process(msg);
    };
}
