PTH=$( cd "$( dirname "${BASH_SOURCE:-$0}" )" && pwd )
source $PTH/venv/bin/activate
apik=$(head -n 1 "$PTH/youtube-apikey.txt")
cid=$(head -n 1 "$PTH/google-client-id.txt")
cd "$PTH/src"
FILEOUT=$PTH/logs/`date "+%Y%m%d"`_pm.out
( python -m server --dbfile ../main.sqlite --static ./www --port 5802 --client-id "$cid" --youtube-apikey "$apik" --autoupdate 3 -v ) > $FILEOUT 2>&1