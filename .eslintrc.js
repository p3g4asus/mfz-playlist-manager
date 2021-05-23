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
        'lastconf_key': true,
        'host_url': true,
        'go_to_video': true,
        'playlist_save_prefix': true,
        'dyn_module_load': true,
        'CMD_IORDER': true,
        'CMD_DEL': true,
        'CMD_SORT': true,
        'yt_loadPlaylistData': true,
        'clear_playlist': true,
        'bootstrapDetectBreakpoint': true,
        'add_video_to_button': true,
        'set_playlist_button_enabled': true,
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