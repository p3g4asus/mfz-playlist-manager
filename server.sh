#!/bin/bash

PTH=$( cd "$( dirname "${BASH_SOURCE:-$0}" )" && pwd )
source $PTH/venv/bin/activate
echo $PTH
cd "$PTH"
set -a
. server.conf
set +a
cd "$PTH/src"
DT=`date "+%Y%m%d"`
FILEOUT="${log_dir}/${DT}_pm.out"
arg="-m server --pid /tmp/pid_mfz_pm.pid --dbfile ../main.sqlite --static ./www --port $http_port --redis "$redis_url" --client-id "$g_id" --youtube-apikey "$y_key" --autoupdate $autopudate --sid $s_id -v"
echo $arg
if [ "${async}" = true ]; then
    echo "Spawn!"
    (  python3 $(echo -n $arg) ) > $FILEOUT 2>&1 &
else
    (  python3 $(echo -n $arg) ) > $FILEOUT 2>&1
fi