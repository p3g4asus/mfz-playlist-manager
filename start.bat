REM ~ py -3 -m venv %~dp0venv
REM ~ pip3 install cython
REM ~ pip3 install oscpy
REM ~ pip3 install kivy.deps.sdl2
REM ~ pip3 install kivy.deps.glew
REM ~ pip3 install kivy.deps.gstreamer
REM ~ pip3 install kivy.deps.angle
REM ~ pip3 install jnius
REM ~ pip3 install aiohttp-security[session]
REM ~ pip3 install aiohttp
REM ~ pip3 install cryptography
REM ~ pip3 install aiosqlite
REM ~ pip3 install "C:\Users\Matteo\Downloads\Kivy-2.0.0.dev0-cp37-cp37m-win_amd64.whl"
REM ~ pip3 install git+git://github.com/p3g4asus/KivyMD.git@25b0b7f2df7dba463111543cf526b6cd6b672ace
call %~dp0venv\Scripts\activate.bat
set PATH=C:\Program Files\Java\jre1.8.0_231\bin\server;%PATH%
set KCFG_KIVY_LOG_LEVEL=debug
set KCFG_KIVY_LOG_ENABLE=1
set KCFG_KIVY_LOG_DIR=%~dp0logs
python -m gui -d
pause
