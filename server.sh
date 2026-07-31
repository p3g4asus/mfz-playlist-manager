#!/bin/bash
if [ "$( whoami )" = "root" ]; then
    echo -e "\e[31mCannot start as root!\e[0m"
    exit 2
fi
PTH=$( cd "$( dirname "${BASH_SOURCE:-$0}" )" && pwd )
source $PTH/venv/bin/activate
echo $PTH
cd "$PTH"
# Source - https://stackoverflow.com/a/6482403
# Posted by phoxis, modified by community. See post 'Timeline' for change history
# Retrieved 2026-04-20, License - CC BY-SA 4.0

if [ -z "$1" ]
  then
    fl=server.conf
  else
    fl="$1.conf"
fi
echo "Using config file: $fl"
set -a
. $fl
set +a
cd "$PTH/src"
DT=`date "+%Y%m%d"`
mkdir ${log_dir}
FILEOUT="${log_dir}/${DT}_pm.out"
arg="-m server --mediaset-getsmil $mediaset_getsmil --mediaset-d1 $mediaset_d1 --mediaset-d2 $mediaset_d2 --mediaset-drmurl $mediaset_drmurl --mediaset-d3 $mediaset_d3 --pid /tmp/pid_mfz_pm.pid --dbfile $dbfile --static ./www --port $http_port --redis "$redis_url" --client-id "$g_id" --autoupdate $autopudate --sid $s_id --telegram $telegram --pickle "$telegram_persistence" --common-dldir "$dldir" --localfolder-basedir "$basedir" --redirect-files -v"
echo $arg
if [ "${async}" = true ]; then
    echo "Spawn!"
    (  python3 $(echo -n $arg) ) > $FILEOUT 2>&1 &
else
    (  python3 $(echo -n $arg) ) > $FILEOUT 2>&1
fi