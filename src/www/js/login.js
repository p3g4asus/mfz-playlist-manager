function listCookies() {
    var theCookies = document.cookie.split(';');
    var aString = '';
    for (var i = 1 ; i <= theCookies.length; i++) {
        aString += i + ' ' + theCookies[i-1] + '\n';
    }
    return aString;
}

function login_init() {
    $('#login-submit').click(function() {
        let form = $('form');
        if (form[0].checkValidity()) {
            $.ajax({
                url: window.location.origin + '/login',
                type: 'post',
                data: form.serialize(),
                success: function(data, textStatus, request) {
                    console.log(listCookies());
                    window.location.assign(MAIN_PATH + 'index.htm');

                },
                error: function (request, status, error) {
                    toast_msg('Cannot login: please check username and password', 'danger');
                }
            });
        }
        form.addClass('was-validated');
    });
}

$(window).on('load', function () {
    login_init();
});