module.exports = {
    'env': {
        'browser': true,
        'es2021': true,
        'commonjs': true,
        'es6': true,
        'jquery': true
    },
    'extends': 'eslint:recommended',
    'parserOptions': {
        'ecmaVersion': 12,
        //'sourceType': 'module'
    },
    'globals': {
        'COOKIE_USERID': true,
        'CMD_REFRESH': true,
        'main_ws_connect': true,
        'main_ws_reconnect': true,
        'MAIN_PATH': true,
        'CMD_PING': true,
        'Playlist': true,
        'CMD_DUMP': true,
        'CMD_YT_PLAYLISTCHECK': true,
        'find_user_cookie': true,
        'MainWSQueueElement': true,
        'search_var': true,
        'PL_ADD_VIEW_TYPE_CLASS': true,
        'CMD_SEEN': true,
        'CMD_MEDIASET_BRANDS': true,
        'host_url': true,
        'CMD_RAI_CONTENTSET': true,
        'playlist_save_prefix': true,
        'dyn_module_load': true,
        'CMD_IORDER': true,
        'CMD_DEL': true,
        'CMD_SORT': true,
        'docCookies': true,
        'CMD_RAI_LISTINGS': true,
        'bootstrapDetectBreakpoint': true,
        'COOKIE_SELECTEDPL': true,
        'CMD_MEDIASET_LISTINGS': true,
        'set_next_button_enabled': true,
        'set_pause_button_enabled': true,
        'get_url_without_file': true,
        'set_prev_button_enabled': true,
        'set_video_title': true,
        'set_video_enabled': true,
        'get_template_name': true,
        'workout_file': true,
        'format_duration': true,
        'toast_msg': true,
        'pad': true,
        'get_search_start_char': true,
        'init_width_height_from_url': true,
        'fetch': true
    },
    'rules': {
        'indent': [
            'error',
            4
        ],
        'linebreak-style': [
            'error',
            'windows'
        ],
        'quotes': [
            'error',
            'single'
        ],
        'semi': [
            'error',
            'always'
        ],
        'no-unused-vars': ['off']
    }
};
