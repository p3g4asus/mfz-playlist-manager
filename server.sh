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
memory_interval=${memory_interval:-300}
memory_log=${memory_log:-$PTH/logs/memory-usage.csv}
memory_monitor=${memory_monitor:-false}
memory_tracemalloc=${memory_tracemalloc:-false}
memory_snapshot_interval=${memory_snapshot_interval:-0}
memory_snapshot_log=${memory_snapshot_log:-$PTH/logs/memory-allocation-diffs.csv}
refresh_diagnostics=${refresh_diagnostics:-false}
refresh_diagnostics_log=${refresh_diagnostics_log:-$PTH/logs/refresh-diagnostics-detailed.csv}
refresh_tracemalloc_snapshot=${refresh_tracemalloc_snapshot:-false}
refresh_snapshot_playlist_ids=${refresh_snapshot_playlist_ids:-}
cd "$PTH/src"
DT=`date "+%Y%m%d"`
mkdir -p "$log_dir"
FILEOUT="${log_dir}/${DT}_pm.out"
args=(
    -m server
    --mediaset-getsmil "$mediaset_getsmil"
    --mediaset-profiledir "$mediaset_profiledir"
    --mediaset-d1 "$mediaset_d1"
    --mediaset-d2 "$mediaset_d2"
    --mediaset-drmurl "$mediaset_drmurl"
    --mediaset-d3 "$mediaset_d3"
    --pid /tmp/pid_mfz_pm.pid
    --dbfile "$dbfile"
    --static ./www
    --port "$http_port"
    --redis "$redis_url"
    --client-id "$g_id"
    --autoupdate "$autopudate"
    --sid "$s_id"
    --telegram "$telegram"
    --pickle "$telegram_persistence"
    --common-dldir "$dldir"
    --localfolder-basedir "$basedir"
    --redirect-files
    -v
)
if [ "$memory_monitor" = true ] || [ "$memory_snapshot_interval" -gt 0 ]; then
    args+=(--memory-monitor --memory-interval "$memory_interval" --memory-log "$memory_log")
    if [ "$memory_tracemalloc" = true ]; then
        args+=(--memory-tracemalloc)
    fi
    if [ "$memory_snapshot_interval" -gt 0 ]; then
        args+=(--memory-snapshot-interval "$memory_snapshot_interval" --memory-snapshot-log "$memory_snapshot_log")
    fi
fi
if [ "$refresh_diagnostics" = true ]; then
    args+=(--refresh-diagnostics --refresh-diagnostics-log "$refresh_diagnostics_log")
    if [ "$refresh_tracemalloc_snapshot" = true ]; then
        args+=(--refresh-tracemalloc-snapshot)
    fi
    if [ -n "$refresh_snapshot_playlist_ids" ]; then
        args+=(--refresh-snapshot-playlist-ids "$refresh_snapshot_playlist_ids")
    fi
fi
if [ "${async}" = true ]; then
    echo "Spawn!"
    ( python3 "${args[@]}" ) > "$FILEOUT" 2>&1 &
else
    ( python3 "${args[@]}" ) > "$FILEOUT" 2>&1
fi
