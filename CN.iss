; PrenotazioniCN.iss

[Setup]
;fisso, così tutte le versioni sono la stessa app
AppId=PrenotazioniCN            
AppName=PrenotazioniCN

;QUI alzi la versione quando fai un update
AppVersion=2.0.0

; installazione proposta in C:\CascinaNascosta
DefaultDirName={sd}\CascinaNascosta
DefaultGroupName=Prenotazioni CN
OutputBaseFilename=PrenotazioniCNSetup_2_0_0
Compression=lzma
SolidCompression=yes
DisableDirPage=yes              
DisableProgramGroupPage=yes
UninstallDisplayIcon={app}\PrenotazioniCN.exe

[Files]
Source: "dist\PrenotazioniCN\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

; Template utente modificabile (non sovrascrivere se già esiste)
Source: "installer_files\config\template.txt"; DestDir: "{app}\config"; Flags: ignoreversion onlyifdoesntexist

; Template di fabbrica (solo se non esiste)
Source: "installer_files\config\template_default.txt"; DestDir: "{app}\config"; Flags: ignoreversion onlyifdoesntexist

; Config runtime
Source: "installer_files\config\config.json"; DestDir: "{app}\config"; Flags: ignoreversion onlyifdoesntexist uninsneveruninstall

[Run]
Filename: "{app}\PrenotazioniCN.exe"; Description: "Avvia PrenotazioniCN"; Flags: nowait postinstall skipifsilent