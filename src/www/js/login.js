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
        data: 'idtoken=' + id_token,
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
    $('#login-submit').click(function() {
        let form = $('form');
        if (form[0].checkValidity()) {
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
        }
        form.addClass('was-validated');
    });
    
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

$(window).on('load', function () {
    login_init();
});