try {
    importScripts('const.js', 'main_ws_manager.js', 'ffx-chrome-wrapper.js', 'kvm_manager.js');
    importScripts('background.js');
} catch (error) {
    console.error(error);

}