const KEY_EVENT_MAP = {
    '[Backspace]': {'keyCode': 8, 'code': 'Backspace', 'charCode': '⌫'},
    '[Tab]': {'keyCode': 9, 'code': 'Tab', 'charCode': '↹'},
    '[Clear]': {'keyCode': 12, 'code': 'NumLock', 'charCode': '⌧'},
    '[Enter]': {'keyCode': 13, 'code': 'Enter', 'charCode': '↵'},
    '[Pause]': {'keyCode': 19, 'code': 'Pause', 'charCode': ''},
    '[Escape]': {'keyCode': 27, 'code': 'Escape', 'charCode': '⎋'},
    '[ ]': {'keyCode': 32, 'code': 'Space', 'charCode': ' '},
    '[PageUp]': {'keyCode': 33, 'code': 'Numpad9', 'charCode': '⇞'},
    '[PageDown]': {'keyCode': 34, 'code': 'Numpad3', 'charCode': '⇟'},
    '[End]': {'keyCode': 35, 'code': 'Numpad1', 'charCode': ''},
    '[Home]': {'keyCode': 36, 'code': 'Numpad7', 'charCode': '⌂'},
    '[ArrowLeft]': {'keyCode': 37, 'code': 'ArrowLeft', 'charCode': '←'},
    '[ArrowUp]': {'keyCode': 38, 'code': 'ArrowUp', 'charCode': '↑'},
    '[ArrowRight]': {'keyCode': 39, 'code': 'ArrowRight', 'charCode': '→'},
    '[ArrowDown]': {'keyCode': 40, 'code': 'ArrowDown', 'charCode': '↓'},
    '[Insert]': {'keyCode': 45, 'code': 'Numpad0', 'charCode': 'x'},
    '[Delete]': {'keyCode': 46, 'code': 'NumpadDecimal', 'charCode': '⌦'},
    '0': {'keyCode': 48, 'code': 'Digit0', 'charCode': '⓪'},
    '’': {'keyCode': 48, 'code': 'Digit0', 'charCode': '’'},
    'º': {'keyCode': 48, 'code': 'Digit0', 'charCode': 'º'},
    '1': {'keyCode': 49, 'code': 'Digit1', 'charCode': '①'},
    '!': {'keyCode': 49, 'code': 'Digit1', 'charCode': '!'},
    '¡': {'keyCode': 49, 'code': 'Digit1', 'charCode': '¡'},
    '2': {'keyCode': 50, 'code': 'Digit2', 'charCode': '②'},
    '[@]': {'keyCode': 50, 'code': 'Digit2', 'charCode': '@'},
    '²': {'keyCode': 50, 'code': 'Digit2', 'charCode': '²'},
    '™': {'keyCode': 50, 'code': 'Digit2', 'charCode': '™'},
    '3': {'keyCode': 51, 'code': 'Digit3', 'charCode': '③'},
    '#': {'keyCode': 51, 'code': 'Digit3', 'charCode': '#'},
    '³': {'keyCode': 51, 'code': 'Digit3', 'charCode': '³'},
    '£': {'keyCode': 51, 'code': 'Digit3', 'charCode': '£'},
    '4': {'keyCode': 52, 'code': 'Digit4', 'charCode': '④'},
    '¤': {'keyCode': 52, 'code': 'Digit4', 'charCode': '¤'},
    '¢': {'keyCode': 52, 'code': 'Digit4', 'charCode': '¢'},
    '5': {'keyCode': 53, 'code': 'Digit5', 'charCode': '⑤'},
    '%': {'keyCode': 53, 'code': 'Digit5', 'charCode': '%'},
    '€': {'keyCode': 53, 'code': 'Digit5', 'charCode': '€'},
    '∞': {'keyCode': 53, 'code': 'Digit5', 'charCode': '∞'},
    '6': {'keyCode': 54, 'code': 'Digit6', 'charCode': '⑥'},
    '§': {'keyCode': 54, 'code': 'Digit6', 'charCode': '§'},
    '¼': {'keyCode': 54, 'code': 'Digit6', 'charCode': '¼'},
    '7': {'keyCode': 55, 'code': 'Digit7', 'charCode': '⑦'},
    '&': {'keyCode': 55, 'code': 'Digit7', 'charCode': '&'},
    '½': {'keyCode': 55, 'code': 'Digit7', 'charCode': '½'},
    '8': {'keyCode': 56, 'code': 'Digit8', 'charCode': '⑧'},
    '¾': {'keyCode': 56, 'code': 'Digit8', 'charCode': '¾'},
    '•': {'keyCode': 56, 'code': 'Digit8', 'charCode': '•'},
    '9': {'keyCode': 57, 'code': 'Digit9', 'charCode': '⑨'},
    '(': {'keyCode': 57, 'code': 'Digit9', 'charCode': '('},
    '‘': {'keyCode': 57, 'code': 'Digit9', 'charCode': '‘'},
    'ª': {'keyCode': 57, 'code': 'Digit9', 'charCode': 'ª'},
    ':': {'keyCode': 58, 'code': 'Period', 'charCode': ''},
    ';': {'keyCode': 59, 'code': 'Semicolon', 'charCode': ''},
    '[<]': {'keyCode': 60, 'code': 'Backquote', 'charCode': ''},
    '<': {'ctrlKey': true},
    '=': {'keyCode': 61, 'code': 'Equal', 'charCode': ''},
    'ß': {'keyCode': 63, 'code': 'Minus', 'charCode': ''},
    'a': {'keyCode': 65, 'code': 'KeyA', 'charCode': ''},
    'á': {'keyCode': 65, 'code': 'KeyA', 'charCode': 'á'},
    'b': {'keyCode': 66, 'code': 'KeyB', 'charCode': ''},
    '∫': {'keyCode': 66, 'code': 'KeyB', 'charCode': '∫'},
    'c': {'keyCode': 67, 'code': 'KeyC', 'charCode': ''},
    '©': {'keyCode': 67, 'code': 'KeyC', 'charCode': '©'},
    'd': {'keyCode': 68, 'code': 'KeyD', 'charCode': ''},
    'ð': {'keyCode': 68, 'code': 'KeyD', 'charCode': 'ð'},
    '∂': {'keyCode': 68, 'code': 'KeyD', 'charCode': '∂'},
    'e': {'keyCode': 69, 'code': 'KeyE', 'charCode': ''},
    'é': {'keyCode': 69, 'code': 'KeyE', 'charCode': 'é'},
    'f': {'keyCode': 70, 'code': 'KeyF', 'charCode': ''},
    'ƒ': {'keyCode': 70, 'code': 'KeyF', 'charCode': 'ƒ'},
    'g': {'keyCode': 71, 'code': 'KeyG', 'charCode': ''},
    'h': {'keyCode': 72, 'code': 'KeyH', 'charCode': ''},
    '˙': {'keyCode': 72, 'code': 'KeyH', 'charCode': '˙'},
    '˚': {'keyCode': 72, 'code': 'KeyH', 'charCode': '˚'},
    'i': {'keyCode': 73, 'code': 'KeyI', 'charCode': ''},
    '[^]': {'keyCode': 73, 'code': 'KeyI', 'charCode': '^'},
    '^': {'shiftKey': true},
    'í': {'keyCode': 73, 'code': 'KeyI', 'charCode': 'í'},
    'j': {'keyCode': 74, 'code': 'KeyJ', 'charCode': ''},
    '∆': {'keyCode': 74, 'code': 'KeyJ', 'charCode': '∆'},
    'k': {'keyCode': 75, 'code': 'KeyK', 'charCode': ''},
    '°': {'keyCode': 75, 'code': 'KeyK', 'charCode': '°'},
    'l': {'keyCode': 76, 'code': 'KeyL', 'charCode': ''},
    'ø': {'keyCode': 76, 'code': 'KeyL', 'charCode': 'ø'},
    'm': {'keyCode': 77, 'code': 'KeyM', 'charCode': ''},
    'µ': {'keyCode': 77, 'code': 'KeyM', 'charCode': 'µ'},
    'n': {'keyCode': 78, 'code': 'KeyN', 'charCode': ''},
    'ñ': {'keyCode': 78, 'code': 'KeyN', 'charCode': 'ñ'},
    '~': {'keyCode': 78, 'code': 'KeyN', 'charCode': '~'},
    'o': {'keyCode': 79, 'code': 'KeyO', 'charCode': ''},
    'ó': {'keyCode': 79, 'code': 'KeyO', 'charCode': 'ó'},
    'p': {'keyCode': 80, 'code': 'KeyP', 'charCode': ''},
    'ö': {'keyCode': 80, 'code': 'KeyP', 'charCode': 'ö'},
    'π': {'keyCode': 80, 'code': 'KeyP', 'charCode': 'π'},
    'q': {'keyCode': 81, 'code': 'KeyQ', 'charCode': ''},
    'ä': {'keyCode': 81, 'code': 'KeyQ', 'charCode': 'ä'},
    'œ': {'keyCode': 81, 'code': 'KeyQ', 'charCode': 'œ'},
    'r': {'keyCode': 82, 'code': 'KeyR', 'charCode': ''},
    '®': {'keyCode': 82, 'code': 'KeyR', 'charCode': '®'},
    's': {'keyCode': 83, 'code': 'KeyS', 'charCode': ''},
    't': {'keyCode': 84, 'code': 'KeyT', 'charCode': ''},
    'þ': {'keyCode': 84, 'code': 'KeyT', 'charCode': 'þ'},
    '†': {'keyCode': 84, 'code': 'KeyT', 'charCode': '†'},
    'u': {'keyCode': 85, 'code': 'KeyU', 'charCode': ''},
    'ú': {'keyCode': 85, 'code': 'KeyU', 'charCode': 'ú'},
    '¨': {'keyCode': 85, 'code': 'KeyU', 'charCode': '¨'},
    'v': {'keyCode': 86, 'code': 'KeyV', 'charCode': ''},
    '√': {'keyCode': 86, 'code': 'KeyV', 'charCode': '√'},
    'w': {'keyCode': 87, 'code': 'KeyW', 'charCode': ''},
    'å': {'keyCode': 87, 'code': 'KeyW', 'charCode': 'å'},
    'Σ': {'keyCode': 87, 'code': 'KeyW', 'charCode': 'Σ'},
    '∑': {'keyCode': 87, 'code': 'KeyW', 'charCode': '∑'},
    'x': {'keyCode': 88, 'code': 'KeyX', 'charCode': ''},
    '≈': {'keyCode': 88, 'code': 'KeyX', 'charCode': '≈'},
    'y': {'keyCode': 89, 'code': 'KeyY', 'charCode': ''},
    '¥': {'keyCode': 89, 'code': 'KeyY', 'charCode': '¥'},
    'ü': {'keyCode': 89, 'code': 'KeyY', 'charCode': 'ü'},
    'z': {'keyCode': 90, 'code': 'KeyZ', 'charCode': ''},
    'æ': {'keyCode': 90, 'code': 'KeyZ', 'charCode': 'æ'},
    'Ω': {'keyCode': 90, 'code': 'KeyZ', 'charCode': 'Ω'},
    '[ContextMenu]': {'keyCode': 93, 'code': 'ContextMenu', 'charCode': '▤'},
    '*': {'keyCode': 106, 'code': 'NumpadMultiply', 'charCode': '×'},
    '+': {'keyCode': 107, 'code': 'NumpadAdd', 'charCode': ''},
    ',': {'keyCode': 108, 'code': 'NumpadDecimal', 'charCode': ''},
    '-': {'keyCode': 109, 'code': 'NumpadSubtract', 'charCode': ''},
    '.': {'keyCode': 110, 'code': 'NumpadDecimal', 'charCode': ''},
    '/': {'keyCode': 111, 'code': 'NumpadDivide', 'charCode': '÷'},
    '[F1]': {'keyCode': 112, 'code': 'F1', 'charCode': ''},
    '[F2]': {'keyCode': 113, 'code': 'F2', 'charCode': ''},
    '[F3]': {'keyCode': 114, 'code': 'F3', 'charCode': ''},
    '[F4]': {'keyCode': 115, 'code': 'F4', 'charCode': ''},
    '[F5]': {'keyCode': 116, 'code': 'F5', 'charCode': ''},
    '[F6]': {'keyCode': 117, 'code': 'F6', 'charCode': ''},
    '[F7]': {'keyCode': 118, 'code': 'F7', 'charCode': ''},
    '[F8]': {'keyCode': 119, 'code': 'F8', 'charCode': ''},
    '[F9]': {'keyCode': 120, 'code': 'F9', 'charCode': ''},
    '[F10]': {'keyCode': 121, 'code': 'F10', 'charCode': ''},
    '[F11]': {'keyCode': 122, 'code': 'F11', 'charCode': ''},
    '[F12]': {'keyCode': 123, 'code': 'F12', 'charCode': ''},
    '[F13]': {'keyCode': 124, 'code': 'F13', 'charCode': ''},
    '[F14]': {'keyCode': 125, 'code': 'F14', 'charCode': ''},
    '[F15]': {'keyCode': 126, 'code': 'F15', 'charCode': ''},
    '[F16]': {'keyCode': 127, 'code': 'F16', 'charCode': ''},
    '[F17]': {'keyCode': 128, 'code': 'F17', 'charCode': ''},
    '[F18]': {'keyCode': 129, 'code': 'F18', 'charCode': ''},
    '[F19]': {'keyCode': 130, 'code': 'F19', 'charCode': ''},
    '[F20]': {'keyCode': 131, 'code': 'F20', 'charCode': ''},
    '[F21]': {'keyCode': 132, 'code': 'F21', 'charCode': ''},
    '[F22]': {'keyCode': 133, 'code': 'F22', 'charCode': ''},
    '[F23]': {'keyCode': 134, 'code': 'F23', 'charCode': ''},
    '[F24]': {'keyCode': 135, 'code': 'F24', 'charCode': ''},
    '[F25]': {'keyCode': 136, 'code': 'F25', 'charCode': ''},
    '[F26]': {'keyCode': 137, 'code': 'F26', 'charCode': ''},
    '[F27]': {'keyCode': 138, 'code': 'F27', 'charCode': ''},
    '[F28]': {'keyCode': 139, 'code': 'F28', 'charCode': ''},
    '[F29]': {'keyCode': 140, 'code': 'F29', 'charCode': ''},
    '[F30]': {'keyCode': 141, 'code': 'F30', 'charCode': ''},
    '[F31]': {'keyCode': 142, 'code': 'F31', 'charCode': ''},
    '[F32]': {'keyCode': 143, 'code': 'F32', 'charCode': ''},
    '$': {'win': true},
    '[$]': {'keyCode': 164, 'code': 'Backslash', 'charCode': ''},
    ')': {'keyCode': 169, 'code': 'Minus', 'charCode': ''},
    '|': {'keyCode': 172, 'code': '', 'charCode': ''},
    '¶': {'keyCode': 186, 'code': 'Semicolon', 'charCode': '¶'},
    '…': {'keyCode': 186, 'code': 'Semicolon', 'charCode': '…'},
    '±': {'keyCode': 187, 'code': 'Equal', 'charCode': '±'},
    '×': {'keyCode': 187, 'code': 'Equal', 'charCode': '×'},
    '≠': {'keyCode': 187, 'code': 'Equal', 'charCode': '≠'},
    'ç': {'keyCode': 188, 'code': 'Comma', 'charCode': 'ç'},
    '≥': {'keyCode': 188, 'code': 'Comma', 'charCode': '≥'},
    '–': {'keyCode': 189, 'code': 'Minus', 'charCode': '–'},
    '[_]': {'keyCode': 189, 'code': 'Minus', 'charCode': '_'},
    '_': {'metaKey': true},
    '[>]': {'keyCode': 190, 'code': 'Period', 'charCode': '>'},
    '>': {'altKey': true},
    '≤': {'keyCode': 190, 'code': 'Period', 'charCode': '≤'},
    '?': {'keyCode': 191, 'code': 'Slash', 'charCode': '?'},
    '¿': {'keyCode': 191, 'code': 'Slash', 'charCode': '¿'},
    '÷': {'keyCode': 191, 'code': 'Slash', 'charCode': '÷'},
    '`': {'keyCode': 192, 'code': 'Backquote', 'charCode': ''},
    '[': {'keyCode': 219, 'code': 'BracketLeft', 'charCode': ''},
    '{': {'keyCode': 219, 'code': 'BracketLeft', 'charCode': '{'},
    '«': {'keyCode': 219, 'code': 'BracketLeft', 'charCode': '«'},
    '”': {'keyCode': 219, 'code': 'BracketLeft', 'charCode': '”'},
    '“': {'keyCode': 219, 'code': 'BracketLeft', 'charCode': '“'},
    '\\': {'keyCode': 220, 'code': 'Backslash', 'charCode': ''},
    '¬': {'keyCode': 220, 'code': 'Backslash', 'charCode': '¬'},
    ']': {'keyCode': 221, 'code': 'BracketRight', 'charCode': ''},
    '}': {'keyCode': 221, 'code': 'BracketRight', 'charCode': '}'},
    '»': {'keyCode': 221, 'code': 'BracketRight', 'charCode': '»'},
    '\'': {'keyCode': 222, 'code': 'Quote', 'charCode': ''},
    '["]': {'keyCode': 222, 'code': 'Quote', 'charCode': '"'},
    '´': {'keyCode': 222, 'code': 'Quote', 'charCode': '´'}
};

function kvm_init() {
    let oo = '^(';
    for (const ii of Object.keys(KEY_EVENT_MAP).filter((v) => v.length > 1 && v.charAt(0) == '[')) {
        KEY_EVENT_MAP[ii].rk = ii.substring(1, ii.length - 1);
        KEY_EVENT_MAP[ii.toLowerCase()] = KEY_EVENT_MAP[ii];
        oo += ii.replace(new RegExp('([\\[\\]])','g'), '\\$1')  + '|';
    }
    return oo.substring(0, oo.length - 1) + ')';
}
const SPECIAL_KEYS_REGEXP = new RegExp(kvm_init(), 'i');
const ADD_KEY_REGEXP = new RegExp('^([_<>\\^\\$])');
const CARD_REGEXP = new RegExp('^@([0-9]+)');

function kvm_process_string(s) {
    let keyOut = {}, mix = null;
    let rexp, quit, remove;
    let card = 1;
    for (;;) {
        quit = true;
        rexp = null;
        remove = '5';
        if ((rexp = ADD_KEY_REGEXP.exec(s))) {
            quit = false;
        } else if ((rexp = /^"([^"]+)"/.exec(s))) {
            const val = rexp[1];
            rexp = new RegExp('^([^/]+)/([0-9]+)/([^/]*)$').exec(val);
            if (rexp) {
                mix = {'keyCode': parseInt(rexp[2]), 'key': rexp[1], 'code': rexp[3]};
                rexp = [0, val + '55'];
            } else {
                keyOut = Object.assign(keyOut, {'obj': val});
                remove = val + '55';
                rexp = null;
            }
        } else if ((rexp = SPECIAL_KEYS_REGEXP.exec(s)));
        else if (KEY_EVENT_MAP[s.charAt(0)]) {
            rexp = [0, s.charAt(0)];
        }
        if (rexp) {
            if (!mix) {
                mix = Object.assign({}, KEY_EVENT_MAP[rexp[1]]);
                if (mix.code) {
                    mix.key = mix.rk || rexp[1];
                }
            }
            mix.which = mix.keyCode;
            mix.bubbles = true;
            const cards = CARD_REGEXP.exec(s.substring(rexp[1].length));
            if (cards) {
                card = parseInt(cards[1]);
                rexp[1] += cards[0];
            }
            keyOut = Object.assign(keyOut, mix);
            mix = null;
        } else {
            rexp = [0, remove];
            quit = false;
        }
        s = s.substring(rexp[1].length);
        if (quit || !s.length) {
            if (keyOut.shiftKey && keyOut.key) {
                keyOut.key = keyOut.key.toUpperCase();
            }
            return [s, keyOut, card];
        }
    }
}