# Novità di NetMap

Ogni release ha qui la sua sezione: il workflow di GitHub la copia nelle note della release e si ferma se manca.
Formato: `## [X.Y.Z] - AAAA-MM-GG` (pre-release: `X.Y.Z-rc.N`, `X.Y.Z-beta.N`), poi gli elenchi
Novità / Modifiche / Correzioni. Le modifiche non ancora rilasciate vanno sotto `## [Non rilasciato]`.

## [Non rilasciato]

### Novità

- Utenti: nome e cognome in due campi separati (anche nella creazione dell'amministratore). Gli utenti di dominio
  li prendono da Active Directory (Nome e Cognome, oppure il nome visualizzato); quelli esistenti sono stati divisi
  alla prima parola e si correggono dalla pagina Utenti.
- Profili SNMP: anche SNMP v1, per gli apparati vecchi che non conoscono la v2c (le tabelle si leggono con
  GETNEXT, una riga alla volta).
- Indirizzi delle scansioni e destinatari email degli avvisi a "bolle": Invio, virgola o spazio dopo ognuno, si può
  incollare un elenco, le bolle non valide sono rosse e sotto gli indirizzi c'è quanti ne verranno scansionati.
- Colonna "Origine" in device, porte, cavi e IP: un'icona dice se sono stati inseriti a mano, trovati dalla
  scansione o importati da un altro programma (con filtro); la stessa icona nella scheda del device e accanto alle
  porte. Gli oggetti importati da NetBox d'ora in poi hanno origine "NetBox" (per la scansione contano sempre come
  inseriti a mano).
- Avvisi: ogni canale può seguire solo alcune sedi, posizioni, ruoli o device scelti (o tutti, come prima), e
  anche le porte: quelle con un cavo collegato oppure porte scelte una per una, con un avviso quando vanno giù
  mentre il device risponde. Il testo dei messaggi si può cambiare con i segnaposto ({device}, {ip}, {sede},
  {posizione}, {durata}, {porta}…), con l'anteprima nel modulo del canale.
- Campi personalizzati veri (Amministrazione → Campi personalizzati): l'amministratore sceglie etichetta, tipo
  (testo, testo lungo, numero, sì/no, data, scelta da un elenco, link), oggetti a cui si applicano, se sono
  obbligatori e l'ordine. Nei moduli hanno il controllo adatto; negli elenchi sono colonne con filtro e ordinamento;
  si trovano con la ricerca ed escono nell'export dei device. I campi liberi nome/valore restano.
- Pagina **Import** unica (Amministrazione → Import, al posto di "Import da NetBox"): si sceglie la sorgente tra
  CSV o Excel, NetBox, Zabbix, LibreNMS, Observium, PRTG, GLPI e Lansweeper. Dagli altri programmi arrivano i
  device con IP di management, produttore, modello, ruolo, seriale e posizione e, dove il programma li conosce,
  porte, indirizzi IP e cavi (vicini LLDP/CDP di LibreNMS, collegamenti tra porte di GLPI); con prova della
  connessione, scelta di gruppi o sedi, simulazione, log e "crea solo quello che manca", come per NetBox.
- Scansione: per i modelli nuovi riconosce il tipo di apparato (stampante, UPS, PDU, NAS, telecamera, telefono,
  access point, controller wireless, firewall, router, switch, server) dalle MIB delle stampanti e degli UPS, dalla
  descrizione SNMP, dal produttore, dalle capacità LLDP e da sysServices, e lo mostra nella proposta con il motivo.
  Se non c'è un ruolo adatto ne propone uno nuovo, che si crea (con colore e livello in mappa) approvando il device.
- Il log delle scansioni dice perché un indirizzo non si è letto: risponde al ping ma non a SNMP, risponde con un
  errore SNMP v3 (utente sconosciuto, password o protocollo sbagliati) o non risponde a niente; per gli apparati
  letti, le tabelle che non si sono lette.
- **Prova indirizzi** (lente nelle Scansioni): interroga subito fino a 256 indirizzi con i profili scelti, senza
  salvare niente, e per ognuno mostra ping, esito di ogni profilo con il motivo e, per chi risponde, modello, tipo,
  quante porte, IP e vicini si leggerebbero e se il device c'è già in NetMap.

### Modifiche

- Active Directory: la prova con un utente è in fondo alla pagina, chiusa ("Prova (facoltativa)"): serve solo se si
  conosce la password di un utente del dominio.
- API degli import: `/api/imports` (prova, coda, stato) vale per tutte le sorgenti; `/api/netbox/*` resta. Nella
  risposta `source_version` prende il posto di `netbox_version` (che c'è ancora per gli import da NetBox).

## [1.0.0] - 2026-10-09

Prima versione stabile: la 1.0.0-rc.3 con le correzioni qui sotto. Da qui i numeri seguono il versionamento
semantico: 1.0.1 per le correzioni, 1.1.0 per le funzioni nuove, 2.0.0 per i cambiamenti incompatibili.

### Novità
- Scelta del canale anche per le installazioni dal codice (con git): Stabile, Beta o Sviluppo (ogni modifica di
  `main` appena è su GitHub, anche non provata). Prende il posto del campo Branch da scrivere a mano.

### Modifiche
- Le installazioni dal codice mostrano la versione della release, o tra una release e l'altra l'ultima release più
  le modifiche successive (es. 1.0.0+3), al posto del numero con la data.
- Le installazioni dal codice seguono il canale Stabile, se non se ne sceglie un altro: per ricevere ogni modifica
  di `main` come prima, scegli Sviluppo nella pagina Aggiornamenti.

### Correzioni
- Menu delle colonne delle tabelle: il pulsante restava evidenziato anche con le colonne tornate come quelle
  predefinite, e le frecce che non si possono usare sembravano selezionate.
- Il backup notturno non salta più quando, all'ora del backup, il database non è ancora acceso (subito dopo
  l'installazione o un riavvio del server): lo script aspetta che risponda.
- Installazioni dal codice (modalità docker): il link «Codice sorgente» e la pagina Aggiornamenti mostravano l'ultimo
  tag anche per i commit successivi, quindi il link portava a un codice diverso da quello installato.

## [1.0.0-rc.3] - 2026-10-09

Accesso con Active Directory, copie dei backup fuori dal server, import da Excel e da NetBox, manuale d'uso.

### Novità
- Test automatici su GitHub a ogni push: backend, migration, interfaccia, script e una prova completa come la fa
  un utente (installazione dell'ultima versione pubblicata, aggiornamento al codice nuovo, ripristino di un
  backup, giro nel browser).
- Ripristino di un backup dalla pagina Backup, con backup di sicurezza prima e ritorno allo stato di prima se
  NetMap non riparte; un backup di una versione più nuova di quella installata viene rifiutato.
- Backup scaricabili sul PC e caricabili dal PC (anche fatti su un altro server).
- Copie dei backup fuori dal server: cartella di rete (NAS o server Windows, SMB) o server SFTP. Ogni backup nuovo
  viene copiato entro un minuto, le copie vecchie si cancellano dopo i giorni scelti e un backup si può riportare
  sul server dalla destinazione.
- Chiave dei segreti scaricabile (o copiata insieme ai backup): dopo un ripristino su un altro server la pagina
  dice quante password non si leggono e le ricifra con la chiave del vecchio server.
- Accesso con Active Directory: gli utenti di Windows entrano con la password del dominio e il ruolo viene dai
  gruppi (anche annidati) a ogni accesso. LDAPS o StartTLS con verifica del certificato, più domain controller,
  nessun account di servizio, prova con un utente vero prima di salvare. Gli utenti locali entrano sempre.
- Nello storico anche avvisi, destinazioni dei backup e impostazioni di Active Directory tra i tipi filtrabili.
- Manuale d'uso in italiano e in inglese (`docs/manuale.md`, `docs/manual.md`), aperto dal menu utente nella
  versione che corrisponde a quella installata.
- Import dei device da Excel (`.xlsx`): si legge il primo foglio con la colonna del nome e lo si controlla nel
  riquadro prima di importare. Accettate anche le intestazioni dell'export dei device di NetBox e quelle con gli
  accenti ("Unità").
- Import da NetBox (3.3 o successivo, Amministrazione → Import da NetBox): sedi, posizioni, rack, catalogo, VRF,
  VLAN, subnet, device con porte e stack, cavi (anche attraverso i patch panel) e IP, di tutte le sedi o di quelle
  scelte. Basta un token in sola lettura, che non resta salvato; simulazione prima di importare; crea solo quello
  che manca, quindi si può rilanciare senza doppioni.
- Pacchetto diagnostico nella pagina Aggiornamenti: uno zip con versione, configurazione senza password, stato del
  database e log dell'API, dello script e (se raccolti) dei container, da allegare a una segnalazione.

### Modifiche
- Accesso più protetto: dopo 5 password sbagliate sullo stesso utente si aspetta un minuto, e ogni errore in più
  raddoppia l'attesa fino a 15 minuti; 20 errori dallo stesso indirizzo lo bloccano per 15 minuti. I tentativi
  falliti finiscono nel log dell'API con l'indirizzo di provenienza.
- I log dei container non crescono più all'infinito: al massimo 30 MB per servizio.
- Più veloce con migliaia di device (provato con 2900 device e mappe da 290 device e 540 cavi): la vista
  topologia passa da 7 secondi a meno di uno, spostare un device in una mappa grande da 2 secondi a meno di un
  decimo per movimento, "Disponi" da 6 a poco più di un secondo; elenco dei device ordinato o cercato per IP in
  pochi centesimi di secondo.
- Elenco dei device ordinato per IP di management in ordine numerico (10.0.0.2 prima di 10.0.0.10).
- Aggiungere un device a un rack in una sede con più di 1000 device: la finestra ha un campo di ricerca (prima
  mostrava solo i primi 1000).
- "Da approvare" dice quante modifiche mostra quando sono più di 5000.

### Correzioni
- Alcune frasi della pagina rack e di "Da approvare" restavano in italiano con l'interfaccia in inglese.

## [1.0.0-rc.2] - 2026-10-09

NetMap diventa software libero: codice e immagini pubblici su GitHub.

### Novità
- Licenza AGPL-3.0 e link al codice sorgente della versione installata in fondo a ogni pagina.

### Modifiche
- Immagini scaricabili senza login; l'updater in modalità docker accetta il repository clonato in https
  (la deploy key serve solo per una copia privata).
- Se manca ancora una versione stabile, l'installer suggerisce `--channel beta`.

## [1.0.0-rc.1] - 2026-10-08

Prima versione installabile con le immagini già pronte (`deploy/install.sh`).

### Novità
- Installazione con un comando su qualsiasi server Linux con Docker: immagini pronte dal registro, password del
  database generata, HTTPS incluso (Caddy: CA interna, Let's Encrypt o certificato vostro).
- Aggiornamenti dalla pagina Aggiornamenti per canale (stabile o beta), mai verso versioni più vecchie, con backup
  del database prima di ogni aggiornamento e ritorno automatico alla versione precedente se qualcosa va storto.
- Backup notturno del database e "Backup ora" (pagina Backup).
- Documentazione di rete: device, porte, cavi, VLAN, subnet e IP, rack, stack, posizioni ad albero.
- Mappe automatiche o disegnate a mano, con bolle di rack e posizioni, ricerca e vista per VLAN, export PNG/SVG.
- Scansione SNMP v2c/v3 (interfacce, IP, VLAN, seriali, vicini LLDP/CDP) con modifiche da approvare.
- Stato live (ping e SNMP), "Dov'è collegato?" (tabelle MAC e ARP), avvisi via email, webhook e Telegram.
- Login con ruoli (lettura, modifica, amministratore), storico delle modifiche, "Cosa è cambiato".
- Interfaccia in italiano e inglese, tema chiaro e scuro, stampa di scheda device, rack e mappa.
- Import/export CSV dei device.
