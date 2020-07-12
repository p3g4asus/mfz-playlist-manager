REM ~ py -3 -m venv %~dp0venv
REM ~ pip3 install cython
REM ~ pip3 install python-osc
REM ~ pip3 install kivy.deps.sdl2
REM ~ pip3 install kivy.deps.glew
REM ~ pip3 install kivy.deps.gstreamer
REM ~ pip3 install kivy.deps.angle
REM ~ pip3 install jnius
REM ~ pip3 install aiohttp-security[session]
REM ~ pip3 install aiohttp
REM ~ set USE_SDL2=1
REM ~ set USE_GSTREAMER=1
REM ~ pip3 install git+git://github.com/kivy/kivy.git@cfa6b78f998abd71cda6ab665fd21b18277199b9
REM ~ pip3 install git+git://github.com/p3g4asus/KivyMD.git@27e7e35576ec14d1fa11973a86d85ed8657eb7ae
call %~dp0venv\Scripts\activate.bat
set PATH=C:\Program Files\Java\jre1.8.0_251\bin\server;%PATH%
set KCFG_KIVY_LOG_LEVEL=debug
set KCFG_KIVY_LOG_ENABLE=1
set KCFG_KIVY_LOG_DIR=%~dp0logs
pushd %~dp0src
python -m server --dbfile "%~dp0maindb.db" -v
pause
