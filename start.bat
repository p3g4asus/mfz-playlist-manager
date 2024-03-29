REM py -3 -m venv %~dp0venv
REM call %~dp0venv\Scripts\activate.bat
REM pip3 install cython
REM pip3 install python-osc
REM pip3 install kivy.deps.sdl2
REM pip3 install kivy.deps.glew
REM pip3 install kivy.deps.gstreamer
REM pip3 install kivy.deps.angle
REM set PATH=C:\Program Files\Java\jdk-13.0.2\bin;C:\Program Files\Java\jdk-13.0.2\bin\server;%PATH%
REM set JAVA_HOME=C:\Program Files\Java\jdk-13.0.2
REM pip install pyjnius
REM pip3 install aiohttp-security[session]
REM pip3 install aiohttp
REM pip3 install cryptography
REM pip3 install aiosqlite
REM set USE_SDL2=1
REM set USE_GSTREAMER=1
REM pip3 install git+https://github.com/kivy/kivy.git@20c14b2a2bac73288a4c2808843910364565f66a
REM pip3 install git+https://github.com/p3g4asus/KivyMD.git@HeaTTheatR-master
REM pause
call %~dp0venv\Scripts\activate.bat
set JAVA_HOME=C:\Program Files\Java\jdk1.8.0_102
set PATH=C:\Program Files\Java\jdk1.8.0_102\jre\bin\server;%PATH%
set KCFG_KIVY_LOG_LEVEL=debug
set KCFG_KIVY_LOG_ENABLE=1
set KCFG_KIVY_LOG_DIR=%~dp0logs
pushd %~dp0src
python -m gui -d > ..\client.txt 2>&1
pause
