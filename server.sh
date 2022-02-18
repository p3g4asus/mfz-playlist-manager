PTH=$( cd "$( dirname "${BASH_SOURCE:-$0}" )" && pwd )
source $PTH/venv/bin/activate
cd "$PTH/src"
FILEOUT=$PTH/logs/`date "+%Y%m%d"`_pm.out
( python -m server --dbfile ../main.sqlite --static ./www --port 5802 --client_id "60860343069-fg6qgf1fogpjrb6femd2p7n0l9nsq4vt.apps.googleusercontent.com" --autoupdate 3 -v ) > $FILEOUT 2>&1