# MFZ Remote Desktop

Client desktop multipiattaforma per ricevere comandi remoti MFZ tramite WebSocket.

## Avvio in sviluppo

Richiede Python 3.10 o superiore.

```sh
python -m venv .venv
.venv\Scripts\pip install -r requirements.txt
.venv\Scripts\python main.py
```

Su Linux/macOS, sostituire `Scripts` con `bin`.

Per avviare direttamente nell'area di notifica: `python main.py --minimized`. Dal menu dell'icona scegliere **Mostra** per aprire la finestra.

Il file `.mfz-remote-desktop.json` viene salvato per impostazione predefinita nella directory corrente. Per scegliere un'altra cartella: `python main.py --config-dir "C:\\percorso\\config"`.

La cartella dei log può essere impostata direttamente nel file di configurazione con la chiave `log_directory`. Sono ammessi percorsi assoluti o relativi alla cartella della configurazione:

```json
{
  "log_directory": "logs"
}
```

Se la chiave non è presente, i log vengono salvati in `log/` nella directory corrente.

Incollare nel campo il collegamento remoto, nella forma:

`https://host/nome-s/play/player_remote_commands.htm?hex=abcdef`

Il pulsante **Connect** diventa **Stop trying** mentre sta tentando la connessione e **Disconnect** quando è connessa. L'URL viene salvato alla pressione di Connect e dopo ogni connessione riuscita; se è disponibile all'avvio, l'app avvia automaticamente i tentativi.

L'applicazione prova a riconnettersi ogni dieci secondi e invia un `remoteping` ogni dieci secondi quando è connessa. Se il ping non riceve risposta entro tre secondi, la connessione viene chiusa e ricreata. Rete, ricezione, invio, ping e riconnessione sono eseguiti come coroutine in un loop `asyncio` dedicato.

Ogni pressione di Connect (e l'avvio automatico) crea un file di log in `log/` nella cartella corrente, con data e ora nel nome. Lo stesso log viene mostrato nella finestra.

I comandi applicativi hanno `cmd: "remd"` e sono selezionati dal campo `sub`. Per ogni comando in ingresso con `__id`, la risposta usa `cmd: "remote"`, copia `__id` e `sub`, e contiene `rv` (oltre agli eventuali campi propri del comando). Un sottocomando non configurato risponde con `rv: 501`. Il ping inviato è `{ "cmd": "remoteping", "t": <secondi Unix> }`.

Il pulsante **Comandi** permette di visualizzare, aggiungere, modificare ed eliminare i comandi. Ogni comando ha un nome (`sub`), un tipo e una lista di parametri tipizzati (`integer`, `floating point`, `string`). Al momento è disponibile il tipo `launch`, che richiede i parametri stringa `exe`, `line` e `dir`: avvia l'eseguibile con gli argomenti di `line` e la cartella di lavoro `dir`. Il sottocomando riservato `__list` risponde con `rv: 0` e il campo `commands`, contenente i nomi dei comandi configurati.

I processi avviati da `launch` sono separati dal client (processo detached e tentativo di breakaway dal job su Windows; nuova sessione su Linux/macOS), quindi restano attivi dopo la chiusura di MFZ Remote Desktop, anche durante l'uso del debugger quando Windows lo consente. L'eseguibile viene comunque invocato direttamente, preservando il comportamento single-instance dell'applicazione.

Ad ogni connessione, e dopo ogni modifica all'elenco, il client invia `{"cmd":"remotepush","what":"commands","commands":[...]}`. Dopo una nuova connessione i ping iniziano solo quando il server conferma quel messaggio con `rv: 0`; in caso contrario (o dopo tre secondi senza risposta) l'invio della lista viene ritentato ogni dieci secondi.

## Creare un eseguibile

```sh
python -m PyInstaller --noconfirm --onefile --windowed --name mfz-remote-desktop main.py
```

L'eseguibile risultante è in `dist/`. Creare il pacchetto sulla piattaforma di destinazione (Windows, Linux oppure macOS).

Su Windows l'app imposta un identificativo dedicato per mostrare l'icona del monitor anche nella barra delle applicazioni durante l'avvio da VS Code. Per personalizzare anche l'icona incorporata nel file `.exe` distribuito, aggiungere `--icon percorso\icona.ico` al comando PyInstaller.

## Comportamento in background

Con `pystray` installato, chiudere la finestra la nasconde nell'area di notifica; usare **Mostra** o **Esci** dall'icona. L'app continua a mantenere la connessione. Se l'ambiente desktop non supporta l'area di notifica, il pulsante **Nascondi** mantiene comunque la finestra nascosta e l'app può essere terminata dal task manager.
