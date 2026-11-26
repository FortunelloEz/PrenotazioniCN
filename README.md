# PrenotazioniCN

App desktop per Windows di Cascina Nascosta. Prende le prenotazioni (da PDF, immagine, CSV, TXT o dallo scarico di Superb)
e prepara il messaggio WhatsApp giusto per ogni cliente.

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

Le regole di lavoro complete sono in `CLAUDE.md`.
