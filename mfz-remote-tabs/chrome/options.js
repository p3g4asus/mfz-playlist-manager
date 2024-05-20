const urlInput = document.querySelector('#url');



/*

Store the currently selected settings using browser.storage.local.

*/

function storeSettings() {

    browser.storage.local.set({

        tabControl: {

            url: urlInput.value

        }

    });

}



/*

Update the options UI with the settings values retrieved from storage,

or the default settings if the stored settings are empty.

*/

function updateUI(restoredSettings) {

    urlInput.value = restoredSettings?.tabControl?.url || '';

}



function onError(e) {

    console.error(e);

}



/*

On opening the options page, fetch stored settings and update the UI with them.

*/

const gettingStoredSettings = browser.storage.local.get();

gettingStoredSettings.then(updateUI, onError);



/*

On blur, save the currently selected settings.

*/

urlInput.addEventListener('blur', storeSettings);

