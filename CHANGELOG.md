# Novità di NetMap

Ogni release ha qui la sua sezione: il workflow di GitHub la copia nelle note della release e si ferma se manca.
Formato: `## [X.Y.Z] - AAAA-MM-GG` (pre-release: `X.Y.Z-rc.N`, `X.Y.Z-beta.N`), poi gli elenchi
Novità / Modifiche / Correzioni. Le modifiche non ancora rilasciate vanno sotto `## [Non rilasciato]`.

## [Non rilasciato]

### Novità
- Test automatici su GitHub a ogni push: backend, migration, interfaccia, script e una prova completa come la fa
  un utente (installazione dell'ultima versione pubblicata, aggiornamento al codice nuovo, giro nel browser).

### Modifiche
- Accesso più protetto: dopo 5 password sbagliate sullo stesso utente si aspetta un minuto, e ogni errore in più
  raddoppia l'attesa fino a 15 minuti; 20 errori dallo stesso indirizzo lo bloccano per 15 minuti. I tentativi
  falliti finiscono nel log dell'API con l'indirizzo di provenienza.
- I log dei container non crescono più all'infinito: al massimo 30 MB per servizio.

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
