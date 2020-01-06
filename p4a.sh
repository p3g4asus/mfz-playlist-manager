# p4a clean_builds && p4a clean_dists
p4a apk --private /home/matteo/python-for-android/mfz-playlist-manager/src --package=org.kivymfz.playlistmanager --name "PlsManager" --version 1.0 --bootstrap=sdl2 --requirements=libffi,python3,certifi,python-osc,kivy,setuptools,cryptography,kivymd,aiohttp,aiohttp-session,aiohttp-security,aiosqlite --debug --permission INTERNET --permission WRITE_EXTERNAL_STORAGE --permission READ_EXTERNAL_STORAGE --permission FOREGROUND_SERVICE --dist-name playlistmanager_apk --service=HttpServerService:./server/server.py

# cd /home/matteo/.local/share/python-for-android/dists/playlistmanager_apk && /home/matteo/.local/share/python-for-android/dists/playlistmanager_apk/gradlew assembleDebug
