# mfz-playlist-mannager
Client-Server playlist manager written in python/kivy/asyncio

## Monitoraggio della memoria del server

Il server registra un campione ogni 5 minuti in `logs/memory-usage.csv` (gli
script di avvio eseguono il server dalla cartella `src`). Il CSV include RSS e
memoria virtuale/privata del processo, task asyncio, thread e dimensioni della
cache Telegram (utenti, playlist ed elementi). I campioni vengono aggiunti al
file a ogni intervallo.

Il monitor è disattivato per impostazione predefinita. Per abilitarlo con
`server.sh`, imposta `memory_monitor=true` nel file locale `server.conf`; il
percorso, l'intervallo in secondi e il tracciamento Python si configurano
rispettivamente con `memory_log`, `memory_interval` e `memory_tracemalloc`
(`true` o `false`). Da riga di comando si abilita con `--memory-monitor`.

Per cambiare frequenza o percorso del file:

```sh
python -m server --memory-interval 600 --memory-log ../logs/memory-usage.csv
```

Per registrare anche le allocazioni Python tracciate da `tracemalloc` (con un
po' di overhead aggiuntivo), aggiungere `--memory-tracemalloc`. I campi
`python_current_bytes` e `python_peak_bytes` nel CSV aiutano a distinguere la
crescita degli oggetti Python dalla memoria RSS, che include anche librerie native.
