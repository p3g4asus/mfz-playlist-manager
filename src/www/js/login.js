let login_google_auth2 = null;

function listCookies() {
    var theCookies = document.cookie.split(';');
    var aString = '';
    for (var i = 1 ; i <= theCookies.length; i++) {
        aString += i + ' ' + theCookies[i-1] + '\n';
    }
    return aString;
}

function login_google_init_button() {
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

function login_google_attach_signin(element) {
    console.log(element.id);
    login_google_auth2.attachClickHandler(element, {},
        function(googleUser) {
            console.log('Google User name ' + googleUser.getBasicProfile().getName());
            $.ajax({
                url: window.location.origin + MAIN_PATH + 'login_g',
                type: 'post',
                data: 'idtoken=' + googleUser.getAuthResponse().id_token,
                success: function(data, textStatus, request) {
                    console.log(listCookies());
                    window.location.assign(MAIN_PATH_S + 'index.htm');

                },
                error: function (request, status, error) {
                    toast_msg('Cannot login: please check username and password', 'danger');
                }
            });
            console.log(listCookies());
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
                    window.location.assign(MAIN_PATH_S + 'index.htm');

                },
                error: function (request, status, error) {
                    toast_msg('Cannot login: please check username and password', 'danger');
                }
            });
        }
        form.addClass('was-validated');
    });
    
    login_google_init_button();
}

$(window).on('load', function () {
    login_init();
});