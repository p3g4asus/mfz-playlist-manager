let login_google_auth2 = null;

function listCookies() {
    var theCookies = document.cookie.split(';');
    var aString = '';
    for (var i = 1 ; i <= theCookies.length; i++) {
        aString += i + ' ' + theCookies[i-1] + '\n';
    }
    return aString;
}

function login_google_init_button_old() {
    gapi.load('auth2', function(){
    // Retrieve the singleton for the GoogleAuth library and set up the client.
        login_google_auth2 = gapi.auth2.init({
            client_id: GOOGLE_CLIENT_ID,
            cookiepolicy: 'single_host_origin',
            // Request scopes in addition to 'profile' and 'email'
            //scope: 'additional_scope'
        });
        login_google_attach_signin(document.getElementById('login-g-submit'));
    });
}

function login_send_id_token(id_token, name) {
    console.log('Google User name ' + name);
    $.ajax({
        url: window.location.origin + MAIN_PATH + 'login_g',
        type: 'post',
        data: $('#remember-me').is(':checked')? {idtoken: id_token, remember: 1}: {idtoken: id_token},
        success: function(data, textStatus, request) {
            console.log(listCookies());
            let orig_up = new URLSearchParams(URL_PARAMS);
            window.location.assign(orig_up.has('urlp')?orig_up.get('urlp'):(MAIN_PATH_S + 'index.htm' + URL_PARAMS_APPEND));
        },
        error: function (request, status, error) {
            toast_msg('Cannot login: please check username and password', 'danger');
        }
    });
    console.log(listCookies());
}

function login_google_attach_signin(element) {
    console.log(element.id);
    login_google_auth2.attachClickHandler(element, {},
        function(googleUser) {
            login_send_id_token(googleUser.getAuthResponse().id_token, googleUser.getBasicProfile().getName());
        }, function(error) {
            toast_msg('Cannot login with google: ' + JSON.stringify(error, undefined, 2), 'danger');
        });
}

function login_init() {
    $('#toggle-link').click(function() {
        var formTitle = $('#form-title');
        var authForm = $('#auth-form');
        var toggleLink = $('#toggle-link');
        var rememberMeGroup = $('#remember-me-group');
        
        if (formTitle.text() === 'Login') {
            formTitle.text('Register');
            toggleLink.text('Already have an account? Login');
            authForm.find('button[type="submit"]').text('Register');
            rememberMeGroup.hide();
        } else {
            formTitle.text('Login');
            toggleLink.text('Do not have an account? Register');
            authForm.find('button[type="submit"]').text('Login');
            rememberMeGroup.show();
        }
    });
    const form = $('#auth-form');

    form.submit(function(event) {
        var usernameInput = $('#username');
        var usernameError = $('#username-error');
        var passwordInput = $('#password');
        var passwordError = $('#password-error');
        var isValid = true;
        event.preventDefault();
        if (usernameInput.val().length < 5) {
            usernameInput.addClass('is-invalid');
            usernameError.show();
            isValid = false;
        } else {
            usernameInput.removeClass('is-invalid');
            usernameError.hide();
        }

        if (passwordInput.val().length < 5) {
            passwordInput.addClass('is-invalid');
            passwordError.show();
            isValid = false;
        } else {
            passwordInput.removeClass('is-invalid');
            passwordError.hide();
        }

        if (isValid) {
            var rememberMe = $('#remember-me').is(':checked');
            if (rememberMe) {
                localStorage.setItem('rememberMe', 'true');
                localStorage.setItem('username', usernameInput.val());
            } else {
                localStorage.removeItem('rememberMe');
                localStorage.removeItem('username');
            }
            var formTitle = $('#form-title');
            if (formTitle.text() === 'Login') {
                $.ajax({
                    url: window.location.origin + MAIN_PATH + 'login',
                    type: 'post',
                    data: form.serialize(),
                    success: function(data, textStatus, request) {
                        console.log(listCookies());
                        let orig_up = new URLSearchParams(URL_PARAMS);
                        window.location.assign(orig_up.has('urlp')?orig_up.get('urlp'):(MAIN_PATH_S + 'index.htm' + URL_PARAMS_APPEND));
                    },
                    error: function (request, status, error) {
                        toast_msg('Cannot login: please check username and password', 'danger');
                    }
                });
            } else {
                $.ajax({
                    url: window.location.origin + MAIN_PATH + 'register',
                    type: 'post',
                    data: form.serialize(),
                    success: function(data, textStatus, request) {
                        setTimeout(function() {
                            let orig_up = new URLSearchParams(URL_PARAMS);
                            const urlp = '?urlp=' + encodeURIComponent(orig_up.has('urlp')?orig_up.get('urlp'):(MAIN_PATH_S + 'index.htm' + URL_PARAMS_APPEND));
                            window.location.assign(MAIN_PATH_S + 'login.htm' + urlp);
                        }, 5000);
                        toast_msg('Register OK: redirecting to login page', 'success');
                    },
                    error: function (request, status, error) {
                        toast_msg('Cannot register: please check username and password (username already taken?)', 'danger');
                    }
                });
            }
        }
    });
    if (localStorage.getItem('rememberMe') === 'true') {
        $('#username').val(localStorage.getItem('username'));
        $('#remember-me').prop('checked', true);
    }
    // deprecated login_google_init_button_old();
}

function login_google_new(obj) {
    console.log(JSON.stringify(obj));
    if (obj.credential && obj.credential.length) {
        // Questo cookie va eliminato per un bug in aiohttp che fa un casino bestiale se si lascia questo cookie 
        // (forse perchè il suo valore contiene parentesi graffe non tra virgolette??)
        document.cookie = 'g_state=; expires=Thu, 21 Aug 2014 20:00:00 UTC; path=/';
        login_send_id_token(obj.credential, obj.clientId);
    }
}

function token_refresh(refresh) {
    let el = new MainWSQueueElement(
        {cmd: CMD_TOKEN, refresh: refresh},
        function(msg) {
            return msg.cmd === CMD_TOKEN? msg:null;
        }, 30000, 1);
    el.enqueue().then(function(msg) {
        if (msg.rv == 501 || msg.rv == 502) {
            $('.login').show();
        }
        else {
            $('#token-input-value').val(msg.token);
        }
    });
}

function playlist_dump(useri) {
    let el = new MainWSQueueElement(
        {cmd: CMD_DUMP, useri:useri, load_all: -1},
        function(msg) {
            return msg.cmd === CMD_DUMP? msg:null;
        }, 30000, 1);
    el.enqueue().then(function(msg) {
        $('.loading').hide();
        if (msg.rv == 501 || msg.rv == 502) {
            $('.login').show();
        }
        else {    
            let orig_up = new URLSearchParams(URL_PARAMS);
            let plname = null;
            if (!msg.playlists)
                msg.playlists = [];
            if (orig_up.has('urlp') && (plname = orig_up.get('urlp')).length)
                window.location.assign(plname);
            else if (msg.playlists.length && orig_up.has('name') && (plname = orig_up.get('name')).length)
                window.location.assign(MAIN_PATH_S + 'play/workout.htm?name=' + encodeURIComponent(plname));
            else {
                $('#playlist-button').click(function() {
                    window.location.assign(MAIN_PATH_S + 'index.htm');
                    return false;
                });
                $('#logout-button').click(function() {
                    $.get( MAIN_PATH + 'logout', function( data ) {
                        window.location.assign(MAIN_PATH_S + 'login.htm');
                    });
                    return false;
                });
                $('#logged-in-p').text('Logged in' + (msg.playlists.length?'  as ' + msg.playlists[0].user:''));
                if (localStorage.getItem('rememberMe') === 'true' && msg.playlists.length) {
                    localStorage.setItem('username', msg.playlists[0].user);
                }
                for (let it of msg.playlists) {
                    add_playlist_to_button(it.name);
                }
                let $bc = $('#token-button-copy');
                $bc.click(() => {
                    let lnk = $('#token-input-value').val();
                    if (lnk && lnk.length) {
                        navigator.clipboard.writeText(lnk).then(function() {
                            console.log('Async: Copying to clipboard was successful!');
                            let $tct = $('#token-copy-tool');
                            let tooltip = bootstrap.Tooltip.getOrCreateInstance($tct.get(0), {
                                'container': $bc.get(0),
                                'title': 'Copied!'
                            }); 
                            tooltip.show();
                            $tct.on('shown.bs.tooltip', () => {
                                setTimeout(() => tooltip.dispose(), 5000);
                            });
                        }, function(err) {
                            console.error('Async: Could not copy text: ', err);
                        });
                    }
                });
                $('#token-button-refresh').click(() => {
                    token_refresh(1);
                });
                token_refresh(0);
                $('.logout').show();
            }
        }
    })
        .catch(function(err) {
            console.log(err);
            let errmsg = 'Exception detected: '+err;
            toast_msg(errmsg, 'danger');
        });
}

$(window).on('load', function () {
    find_user_cookie().then(function (uid) {
        main_ws_reconnect(null, WS_URL);
        playlist_dump(uid);
    }).catch(function() {
        $('.loading').hide();
        $('.login').show();
        login_init();
    });
});