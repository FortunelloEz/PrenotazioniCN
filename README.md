# PrenotazioniCN

App desktop per Windows di Cascina Nascosta. Prende le prenotazioni (da PDF, immagine, CSV, TXT o dallo scarico di Superb)
e prepara il messaggio WhatsApp giusto per ogni cliente.

Versione attuale: **2.2.1**.

## Cosa fa
- **Fonti delle prenotazioni**
  - File PDF con testo selezionabile. Un PDF scansionato viene rifiutato con un avviso: va salvato come PNG o JPG.
  - Immagini PNG, JPG e WEBP, lette dall'AI. Il formato TIFF non è supportato.
  - File CSV e TXT.
  - Scarico diretto da **Superb** per una data scelta.
- **Estrazione**: un modello OpenAI (predefinito `gpt-4o-2024-08-06`, cambiabile con `OPENAI_MODEL` / `OPENAI_VISION_MODEL`)
  ricava nome, telefono, giorno, orario, persone, stato e note.
- **Normalizzazione**
  - Telefoni: `+` e `00` indicano un numero internazionale. Un numero di 10 cifre che inizia per 3, o che inizia con un solo 0,
    riceve `+39`.
  - Pasto dedotto dall'orario: pranzo 11–15, aperitivo 16–18, cena 19–23. Si può correggere riga per riga.
- **Tabella**
  - Le righe sono modificabili, con lo stato a colori (C, N, A, S, PS) e le note di ogni prenotazione.
  - L'app avvisa prima di uscire o di caricare un altro file se ci sono modifiche non salvate.
- **Giorno nei messaggi**: con «Automatico» si usa la data trovata nel file. Si può anche scegliere un giorno uguale per
  tutti i messaggi. «Oggi» diventa «di oggi», oppure «di questa sera» per la cena.
- **Template WhatsApp**
  - Variabili disponibili: `{nome}`, `{giorno}`, `{pasto}`, `{ospiti}`, `{persone}`, `{orario}`.
  - Il template viene controllato prima del salvataggio. Si conservano gli ultimi 20 backup ed è possibile ripristinare
    il template di fabbrica.
- **Invio**
  - Chat singola: apre WhatsApp con il messaggio già scritto.
  - Apertura in blocco delle chat visibili: chiede conferma e fa una pausa tra una chat e l'altra.
  - Le righe a cui manca un dato richiesto dal template vengono escluse dall'invio in blocco. Per la chat singola l'app
    chiede conferma.
  - Una chat viene segnata come «aperta» solo se l'apertura è riuscita.
- **Export HTML**: genera una pagina con la tabella e i link WhatsApp, che si apre nel browser.
- **Chiusura protetta**: se ci sono modifiche in sospeso, l'app chiede conferma prima di chiudersi.

## Dati e privacy
- I dati stanno in `%APPDATA%\PrenotazioniCN\`. Al primo avvio della 2.x vengono copiati da `C:\CascinaNascosta\config`
  e la copia viene verificata. L'originale non viene cancellato.
- La configurazione si salva in modo atomico: un file danneggiato non viene sovrascritto con una configurazione vuota.
- La chiave OpenAI è cifrata con Windows DPAPI e funziona solo con lo stesso utente sullo stesso PC.
- Il testo delle prenotazioni (nomi e telefoni dei clienti) viene inviato a OpenAI per l'estrazione.
- **Licenza**: disattivata dalla 2.2.0. Il codice è ancora presente ma non viene usato all'avvio. L'indirizzo del server
  licenze non è scritto nel repository: si legge dalla variabile `PRENOTAZIONICN_LICENSE_URL`.

## Installare (uso normale)
1. Apri la pagina **Releases** del repository e scarica `PrenotazioniCNSetup_<versione>.exe` (l'ultima).
2. Avvia l'installer. L'app va in `C:\CascinaNascosta`, i dati in `%APPDATA%\PrenotazioniCN\`.
3. Al primo avvio inserisci nell'app:
   - la tua **chiave ChatGPT (OpenAI)**, che serve per leggere i file delle prenotazioni. Viene salvata cifrata e funziona
     solo con il tuo utente Windows;
   - se usi Superb, la **sessione** e l'**ID ristorante** di Superb.

Chiavi e credenziali non sono nel repository: ognuno usa le proprie.

## Avviare dal codice sorgente
Serve Python 3.13 su Windows (la finestra usa WebView2, che su Windows 11 c'è già).
```
py -3.13 -m venv .venv
.venv\Scripts\python -m pip install -r requirements.txt
xcopy installer_files\config config\ /E /I
.venv\Scripts\python main.py
```
In sviluppo i dati (`config\`) stanno nella cartella del progetto. La variabile `PRENOTAZIONICN_DATA_DIR` permette di
spostarli altrove. Il comando `xcopy` crea `config\` con i file di partenza (config vuota e template): senza
questi file l'app non ha un template per i messaggi.

## Costruire l'installer
```
py -3.13 -m venv %TEMP%\cn_build_venv
%TEMP%\cn_build_venv\Scripts\python -m pip install -r requirements.txt pyinstaller
%TEMP%\cn_build_venv\Scripts\python -m PyInstaller --noconfirm PrenotazioniCN.spec
```
Poi compila `CN.iss` con Inno Setup. L'installer finisce in `Output\`.

## Test e controlli
```
.venv\Scripts\python -m pip install -r requirements-dev.txt
npm install
.venv\Scripts\python -m pytest -q tests
.venv\Scripts\ruff check .
npx eslint assets tools
node tools/verifica_visiva.mjs
```
I test non usano la rete: OpenAI, Superb e WhatsApp sono simulati e i dati sono inventati.
Qualità dell'estrazione con LLM finto (deve dare 100%): `.venv\Scripts\python tools\qualita_estrazione.py`.

