# NetMap

Documentazione di rete in stile NetBox: device, porte, cavi, VLAN, subnet e mappe di rete
automatiche o disegnate a mano.

- **Fase 1** ✔ modello dati + API REST
- **Fase 2** ✔ interfaccia web: elenchi e moduli per tutto, scheda device con le porte, subnet con IP liberi, mappe,
  import/export CSV dei device
- **Fase 3** ✔ scansione SNMP (v2c e v3: interfacce, IP, seriale, vicini LLDP/CDP) con modifiche da approvare
- **Fase 4** ✔ stato live sulla mappa e ricerca "dov'è collegato questo PC" (tabelle MAC e ARP), login con ruoli
  (anche con Active Directory), storico delle modifiche, avvisi, backup

**Manuale d'uso**: [docs/manuale.md](docs/manuale.md) · English: [docs/manual.md](docs/manual.md)
(nell'app: menu utente → Manuale).

## Licenza

NetMap è software libero: [GNU Affero General Public License v3.0](LICENSE) (AGPL-3.0-only).
Puoi usarlo, studiarlo, modificarlo e ridistribuirlo; se lo modifichi e lo fai usare ad altri via rete
(anche solo dentro un'azienda o come servizio), devi mettere a loro disposizione il codice delle tue modifiche
con la stessa licenza. Ogni pagina ha in basso il link al codice della versione installata.

Copyright © 2026 Tommaso (tommipute) e contributori.

## Installazione su un server (immagini pronte)

Per usare NetMap su un proprio server Linux con Docker, senza codice sorgente né build:

```bash
docker run --rm ghcr.io/tommipute/netmap-backend:stable cat /app/deploy/install.sh > install-netmap.sh
sudo bash install-netmap.sh                       # oppure: --address https://netmap.azienda.local
```

Finché non esce la 1.0.0 ci sono solo pre-release: usa `netmap-backend:beta` nel primo comando e aggiungi
`--channel beta` al secondo. Serve Docker con il plugin compose (per esempio da https://get.docker.com).

L'installer (`deploy/install.sh`, anche allegato a ogni [release su GitHub](https://github.com/tommipute/netmap/releases)) installa `jq` se manca, scarica
l'ultima versione stabile, crea `/opt/netmap` con `.env` (password del database casuale), avvia NetMap dietro
HTTPS e installa l'updater (timer systemd). Opzioni: `--address`, `--tls`, `--dir`, `--channel beta`, `--image`,
`--user`; rilanciarlo su un'installazione esistente non tocca `.env`, database e backup.

| Cosa | Dove |
|---|---|
| Interfaccia | `https://<server>` (al primo accesso si crea l'amministratore); http reindirizza a https |
| Impostazioni | `/opt/netmap/.env` (indirizzo, certificato, porte), poi `docker compose up -d` |
| Aggiornamenti e backup | NetMap → Amministrazione (canale stabile o beta) |
| Da tenere al sicuro | `.env`, `data/` (chiave delle credenziali SNMP) e `backups/` |

**Certificato** (`NETMAP_TLS` nel `.env`, letto da `deploy/Caddyfile`):

- `tls internal` (predefinito): CA interna di Caddy. Il browser avvisa finché non installi la CA nei PC:
  `docker compose cp caddy:/data/caddy/pki/authorities/local/root.crt netmap-ca.crt`, poi su Windows
  *Installa certificato → Computer locale → Autorità di certificazione radice attendibili* (o con un GPO).
- `tls admin@azienda.it`: Let's Encrypt, solo se il server è raggiungibile da Internet sulle porte 80 e 443.
- `tls /certs/netmap.crt /certs/netmap.key`: certificato vostro, file in `/opt/netmap/certs/`.
- Senza HTTPS: `NETMAP_SCHEME=http`, `NETMAP_TLS=` vuoto e `COOKIE_SECURE=false` (solo per prove).

Le immagini stanno su `ghcr.io/tommipute/netmap-backend` e `-web` (pubbliche, senza login).
Per togliere tutto: `cd /opt/netmap && docker compose down -v && sudo updater/install.sh --uninstall`.

## Avvio (sviluppo)

```powershell
copy .env.example .env      # poi cambia la password dentro .env
docker compose up -d --build
docker compose exec api python -m app.seed    # facoltativo: rete di esempio con una mappa
```

| Cosa | Indirizzo |
|---|---|
| Interfaccia web | http://localhost:5174 |
| API e documentazione (Swagger) | http://localhost:8001/docs |
| Postgres | `localhost:5433` |

Le porte sono diverse dai default così l'app può girare insieme all'app inventory.

Il primo avvio richiede qualche minuto: il container `web` scarica le dipendenze del frontend
e il container `api` crea le tabelle applicando le migration di `backend/alembic/versions/`.
Per seguire l'avvio: `docker compose logs -f`.

## Come si usa

1. **Catalogo**: crea ruoli (con colore e livello in mappa), produttori e modelli.
2. **Luoghi**: crea la sede, poi edifici/piani/stanze e i rack.
3. **Device**: crea il device, poi nella sua scheda aggiungi le porte. Per uno switch usa
   *Aggiungi in blocco* con un intervallo, es. `Gi1/0/[1-48]` oppure `[1-52]`.
4. **Cavi**: dalla scheda device clicca *Collega* su una porta, oppure disegnali sulla mappa.
5. **Mappe**: crea una mappa per la sede. All'apertura i device vengono disposti in automatico
   per livello del ruolo (0 in alto); puoi spostarli e salvare la disposizione.
   - Per creare un cavo sulla mappa trascina dal pallino di un device a quello di un altro e scegli le porte.
   - Clicca un cavo per vederne i dettagli o eliminarlo, clicca un device per aprirne la scheda.
   - Una mappa con "Mostra sempre tutti i device" include da sola i device nuovi della sede;
     senza, scegli tu quali device mettere (utile per mappe parziali, es. solo il core).
   - I colori dei cavi seguono le convenzioni reali: rame blu, fibra multimodale acqua, monomodale gialla.

La barra di ricerca in alto trova device, IP e MAC (anche nel formato Cisco `aabb.ccdd.eeff`).

### Import ed export dei device

Nell'elenco **Device**: *Esporta CSV* (apribile in Excel) o *Esporta JSON* rispettano i filtri attivi.
*Importa* accetta un file o testo incollato, con intestazioni in italiano o inglese (*Scarica modello CSV* ne dà
un esempio). Sedi, posizioni, rack, produttori, modelli e ruoli mancanti vengono creati. Con *Simulazione*
vedi cosa succederebbe senza scrivere niente; le righe sbagliate vengono elencate e le altre importate.

### Scansione SNMP

1. **Profili SNMP**: crea le credenziali (community per v2c, utente e chiavi per v3). Vengono salvate cifrate
   e non si possono rileggere: in modifica lascia vuoto il campo per non cambiarle.
2. **Scansioni**: indica gli indirizzi (uno per riga: `10.10.99.0/24`, `10.10.98.1-20`, `10.10.1.1`),
   i profili da provare in ordine, la sede dove mettere i device nuovi e, se vuoi, ogni quante ore ripeterla.
3. Apri la scansione e premi **Avvia scansione**: il servizio `worker` la esegue in pochi secondi;
   nello storico trovi il log di ogni esecuzione.
4. In **Da approvare** (il numero accanto alla voce di menu) vedi cosa ha trovato, raggruppato per device:
   device nuovi con porte e IP, porte e IP nuovi, dati diversi, cavi visti via LLDP/CDP, porte sparite.
   Approva o rifiuta una per una, per device o tutte. Niente cambia finché non approvi, e una modifica
   rifiutata non torna finché i dati restano uguali.
5. Nel job puoi far aggiungere da sola le porte nuove e gli IP nuovi dei device già censiti. Device nuovi, cavi
   e modifiche ai dati inseriti a mano restano sempre da approvare.

La chiave che cifra le credenziali sta in `SECRETS_KEY` (file `.env`) oppure, se è vuota, in `backend/.secrets_key`
creato al primo uso: non cancellarlo, altrimenti i profili SNMP vanno reinseriti.

### Utenti e accesso con Active Directory

Al primo avvio la pagina di accesso chiede di creare l'amministratore; gli altri utenti si creano in **Utenti**
con un ruolo: solo lettura, modifica (dati e approvazioni della scansione) o amministratore (anche utenti e
impostazioni). Se si perde l'accesso: `docker compose exec -it api python -m app.users password admin`.

Con **Active Directory** (menu Amministrazione) gli utenti di Windows entrano con il loro nome (`mario.rossi`,
`AZIENDA\mario.rossi` o `mario.rossi@azienda.local`) e la password del dominio:

- servono il dominio (`azienda.local`) e i domain controller con il nome completo, quello del loro certificato;
  la connessione è LDAPS (636) o StartTLS (389), quindi il domain controller deve avere un certificato (Servizi
  certificati di Active Directory). Per verificarlo incolla il certificato della CA del dominio esportato in
  Base64. Il server di NetMap deve risolvere quei nomi e raggiungere la porta;
- niente account di servizio: NetMap si collega con le credenziali di chi entra e legge i suoi gruppi;
- il ruolo viene da tre gruppi (amministratori, modifica, solo lettura), anche con gruppi dentro i gruppi; chi è
  in più gruppi prende il ruolo più alto, chi non è in nessuno non entra (oppure entra con il ruolo scelto per
  tutti gli altri). La base di ricerca, se indicata, limita l'accesso agli utenti di quella OU;
- l'utente NetMap si crea al primo accesso e a ogni accesso prende ruolo e nome dal dominio: password e ruolo non
  si cambiano in NetMap. Disattivato in NetMap non entra nemmeno con la password giusta. Tolto da tutti i gruppi,
  al tentativo successivo viene respinto e le sue sessioni si chiudono; altrimenti una sessione dura al massimo
  `SESSION_HOURS` (12 ore);
- *Prova con questo utente* controlla le impostazioni (anche non salvate) con un utente vero e mostra ruolo e
  gruppi trovati;
- gli utenti locali entrano sempre con la loro password: tieni almeno un amministratore locale per quando il
  dominio non risponde. `python -m app.users password <nome>` trasforma un utente di dominio in locale.

### Rete di laboratorio (apparati finti)

Per provare scansione, cavi trovati da soli, "Dov'è collegato?" e stato live senza toccare la rete vera:

```powershell
docker compose --profile lab up -d                  # 5 apparati finti nella rete 172.31.250.0/24
docker compose exec api python -m app.lab prepara   # sede, profilo SNMP, scansione e mappa "Laboratorio"
docker compose exec api python -m app.lab elenco    # apparati e IP
```

| Apparato | IP | Cosa simula |
|---|---|---|
| fw-lab-01 | 172.31.250.10 | FortiGate 100F, collegato al core (LLDP) |
| core-lab-01 | 172.31.250.11 | Catalyst 9300, VLAN 10/20/99, tabella ARP di PC, telefono, stampante, AP |
| sw-lab-p1 | 172.31.250.21 | HPE 2930F: due PC e una stampante |
| sw-lab-p2 | 172.31.250.22 | HPE 2930F: telefono IP con un PC dietro (due MAC sulla stessa porta) |
| sw-lab-p3 | 172.31.250.23 | Catalyst 1000 visto solo via CDP: un PC e un access point con tre client Wi-Fi |

Poi in NetMap: **Scansioni → Laboratorio di rete → Avvia scansione**, approva i 5 device, scansiona di nuovo e
approva i 4 cavi. Un guasto si simula fermando un apparato (`docker compose stop lab-sw-p3`, oppure Stop in
Docker Desktop): entro un minuto risulta "Non risponde". `docker compose start lab-sw-p3` lo riaccende.
Senza `--profile lab` gli apparati non partono; per spegnerli tutti: `docker compose --profile lab stop`.

## Rilasci (per chi sviluppa)

Versioni semver con tag git: `1.2.0` stabile, `1.2.0-rc.1` / `1.2.0-beta.1` pre-release. Per pubblicarne una:

1. In `CHANGELOG.md` sposta le voci di `## [Non rilasciato]` in una sezione `## [1.2.0] - AAAA-MM-GG`.
2. `git tag v1.2.0 && git push origin main v1.2.0`

Il workflow `.github/workflows/release.yml` fa girare i test, costruisce le immagini con `deploy/build-images.sh`
(versione e commit scritti dentro, pacchetto d'installazione in `/app/deploy`), le pubblica su ghcr.io con i tag
dei canali (stabile: `1.2.0`, `1.2`, `stable`, `beta`, `latest`; pre-release: `1.2.0-rc.1`, `beta`) e crea la
release su GitHub con le note del CHANGELOG e `install.sh` allegato. Le installazioni con l'aggiornamento
automatico acceso la installano entro l'intervallo impostato; le altre la vedono nella pagina Aggiornamenti.
Prova locale: `deploy/build-images.sh 1.2.0-rc.1 localhost:5000/netmap --push` verso un registro di prova.

Una versione nuova deve funzionare partendo da qualsiasi versione vecchia: le migration vanno in catena e il
`.env` delle installazioni non si tocca (un'impostazione nuova deve avere un valore predefinito nel compose).

## Aggiornamenti automatici

L'updater ha tre modalità: **image** (installazioni fatte con `install.sh`: scarica le immagini del canale scelto,
mai versioni più vecchie di quella installata, e prende dall'immagine nuova anche `docker-compose.yml`,
`Caddyfile` e sé stesso), **docker** (server con il repo git, come la VM di produzione: segue un branch e
ricostruisce le immagini) e **vm** (senza Docker). Quello che segue vale per tutte e tre; dove si parla di
git e deploy key riguarda solo docker e vm.

Sul server di produzione NetMap si aggiorna da GitHub con lo script `updater/updater.sh`, che gira **sull'host**
(fuori dai container) ogni minuto grazie a un timer systemd. L'app non si aggiorna da sola: niente socket Docker nel
container e niente credenziali GitHub nell'app. App e script si parlano solo con la cartella `updater-data/`,
montata nel container `api` come `/updater-data`:

| File | Chi scrive | Chi legge | Cosa contiene |
|---|---|---|---|
| `settings.json` | app | script | aggiornamento automatico sì/no, branch, ogni quanto controllare, backup (notturno, ora, quanti tenere) |
| `request.json` | app | script (poi lo svuota) | "Controlla ora", "Aggiorna ora", "Backup ora", "Ripristina" o "Raccogli i log dei container" |
| `status.json` | script | app | versione installata e disponibile, ultimo controllo, attività in corso, storico (ultimi 20) |
| `updater.log` | script | app | log dell'ultimo aggiornamento e dei controlli successivi |
| `diagnostics/host.txt` | script | app | disco, memoria, container e loro log, per il pacchetto diagnostico |

A ogni aggiornamento lo script fa il backup del database (`backups/`, tiene gli ultimi N), si segna il commit attuale,
scarica quello nuovo, riavvia l'app e aspetta che `/api/health` risponda "ok" **con il commit nuovo**. Se qualcosa va
storto torna al commit precedente, ripristina il backup se le migration avevano già cambiato il database e riavvia.
Un commit fallito non viene riprovato in automatico (si può forzare con "Aggiorna ora").
Tutto si vede e si comanda come amministratore in **Amministrazione → Aggiornamenti**.

### 1. Accesso al repository

Il repository è pubblico: clonandolo con l'indirizzo https l'updater lo legge senza credenziali e questo passo
non serve. La deploy key serve solo per una copia privata del repository (un fork o un mirror interno).

Sul server, con l'utente che farà girare lo script:

```bash
ssh-keygen -t ed25519 -N "" -C "netmap-updater" -f ~/.ssh/netmap_deploy
cat ~/.ssh/netmap_deploy.pub
```

Su GitHub: repo → **Settings → Deploy keys → Add deploy key**, incolla la chiave pubblica e lascia **spenta**
"Allow write access". Poi di' a ssh di usarla per GitHub, aggiungendo a `~/.ssh/config`:

```
Host github.com
  IdentityFile ~/.ssh/netmap_deploy
  IdentitiesOnly yes
```

La chiave sta solo sul server, mai nell'app né nel repo.

### 2. Installazione

```bash
git clone https://github.com/tommipute/netmap.git /opt/netmap   # repo privato con deploy key: git@github.com:…
cd /opt/netmap
cp .env.example .env        # cambia POSTGRES_PASSWORD; FILE_POLLING=false; togli il # da COMPOSE_FILE
sudo updater/install.sh     # modalità docker
docker compose up -d --build
```

`install.sh` controlla i programmi necessari (git, jq, curl, flock, docker compose), crea `updater/updater.conf`,
le cartelle `updater-data/` e `backups/`, il file `version.env` (commit installato, letto dall'app) e il timer
systemd `netmap-updater.timer` (cron se systemd non c'è). Se la deploy key non funziona ancora, spiega cosa fare.
L'utente che lancia `sudo` deve essere nel gruppo `docker`. Per toglierlo: `sudo updater/install.sh --uninstall`.

Controlli utili: `systemctl list-timers netmap-updater.timer`, `journalctl -u netmap-updater`,
`cat updater-data/updater.log`.

### Modalità docker e vm

- **docker** (consigliata): `docker compose up -d --build`; siccome `version.env` cambia, compose ricrea i container
  dell'app e l'`api` applica le migration all'avvio.
- **vm** (`sudo updater/install.sh --mode vm`): per un server senza Docker. In `updater/updater.conf` imposta
  `VM_DEPLOY_CMD` (installa le dipendenze e riavvia i servizi), `VM_STOP_CMD` e `VM_DATABASE_URL` (per `pg_dump`,
  `psql` e `pg_restore`); i servizi devono leggere `version.env` (systemd: `EnvironmentFile=`). Esempi in
  `updater/updater.conf.example`.

### Produzione dal repo (`docker-compose.prod.yml`)

Con `COMPOSE_FILE=docker-compose.yml:docker-compose.prod.yml` nel `.env` del server, `docker compose` usa la
configurazione di produzione: il codice sta dentro le immagini (`netmap-backend`, `netmap-web`), l'interfaccia è
compilata e servita da nginx sulla porta 5174 (che passa `/api` e `/docs` all'API), le immagini non contengono
pytest né il simulatore SNMP e la porta 8001 dell'API risponde solo sul server stesso (serve all'updater).
La chiave dei segreti, se `SECRETS_KEY` è vuota, sta in `data/secrets_key`: tienila insieme ai backup, senza di
lei i profili SNMP di un database ripristinato vanno reinseriti.
HTTPS anche qui con lo stesso Caddy delle installazioni con le immagini: nel `.env` `COMPOSE_PROFILES=https`,
`NETMAP_HOST`, `NETMAP_TLS` e `COOKIE_SECURE=true` (vedi `.env.example`).

### Backup del database

Oltre a quello prima di ogni aggiornamento, lo script fa un backup ogni notte (02:30, se il server era spento parte
appena si riaccende) e quando lo chiedi da **Amministrazione → Backup → Backup ora**. I file stanno in `backups/`:
`daily-…`, `manual-…`, `before-restore-…` (backup di sicurezza fatto prima di un ripristino) e `imported-…`
(caricati dalla pagina o riportati da una copia esterna) restano per i giorni impostati (14); `netmap-…` (prima
degli aggiornamenti) sono gli ultimi N.

Dalla pagina **Backup** (solo amministratori):

- **Scarica** un backup sul PC o **caricane** uno (un `.dump` fatto da NetMap, anche su un altro server).
- **Ripristina**: lo script fa prima un backup di sicurezza dello stato attuale, ferma NetMap per circa un minuto,
  ripristina e riavvia. Se NetMap non riparte rimette da solo lo stato di prima; un backup di una versione più
  nuova di quella installata non si ripristina (prima aggiorna). Dopo il ripristino valgono gli utenti del backup.
- **Copie fuori dal server**: una cartella di rete (NAS o server Windows, SMB 2/3) o un server SFTP. Il worker
  copia ogni backup nuovo entro un minuto (se la destinazione non risponde riprova ogni 15 minuti e la pagina
  mostra l'errore), cancella dalla destinazione le copie più vecchie dei giorni impostati (solo i file di NetMap)
  e da lì un backup si può **riportare sul server**. Usa una cartella per ogni installazione. SFTP accetta
  password o chiave privata (OpenSSH o PEM senza passphrase); la chiave del server SFTP si registra alla prima
  connessione e, se cambia, le copie si fermano finché non la accetti nel modulo della destinazione.
- **Chiave dei segreti**: le password dei profili SNMP, dei canali di avviso e delle destinazioni sono cifrate con
  la chiave in `data/secrets_key` (o `SECRETS_KEY` nel `.env`), che non sta nel database. Scaricala e tienila al
  sicuro, oppure attiva *Copia anche la chiave dei segreti* su una destinazione protetta.

I container `api` e `worker` montano `backups/` come `/backups` (già nei file compose del repo e dell'installazione;
se cambi `BACKUP_DIR` in `updater/updater.conf`, monta quella cartella).

**Server nuovo dopo un guasto**: installa NetMap (stessa versione o più nuova), carica il backup dalla pagina
Backup (o aggiungi la destinazione e riportalo da lì), ripristinalo ed entra con gli utenti di prima; poi in
*Chiave dei segreti* incolla la chiave del vecchio server (o usa quella copiata sulla destinazione): password e
community salvate tornano leggibili.

Senza interfaccia (NetMap non parte): `updater/updater.sh restore backups/NOME.dump` (ferma l'app, ripristina, riavvia).

### Migration

L'`api` all'avvio esegue `alembic upgrade head`: applica solo le migration mancanti, tutte in un'unica transazione
(o passano tutte o nessuna), con un lock che impedisce due esecuzioni insieme. Se una migration fallisce l'API non
parte, l'health check fallisce e lo script torna indietro ripristinando il backup.

### Rollback manuale

Se anche il rollback automatico non riesce (lo stato nella pagina è "Errore" e il messaggio lo dice):

```bash
cd /opt/netmap
sudo systemctl stop netmap-updater.timer          # ferma i giri dello script
cat updater-data/previous_commit                  # commit di prima dell'ultimo aggiornamento
git checkout -B main $(cat updater-data/previous_commit)
updater/updater.sh version-env                    # l'app saprà quale commit è installato
ls -t backups/                                    # il backup più recente è quello fatto prima dell'aggiornamento
updater/updater.sh restore backups/netmap-AAAAMMGG-HHMMSS-xxxxxxx.dump   # ferma l'app, ripristina, riavvia
sudo systemctl start netmap-updater.timer
```

Con l'aggiornamento automatico acceso, lo script non riprova il commit fallito; se vuoi restare sulla versione
vecchia anche quando ne esce una nuova, spegnilo dalla pagina Aggiornamenti.

### Pacchetto diagnostico

Per segnalare un problema senza entrare sul server: **Aggiornamenti → Diagnostica**. "Raccogli i log dei
container" chiede allo script (entro un minuto) di scrivere spazio su disco, memoria, stato dei container e le
loro ultime 500 righe di log; "Scarica il pacchetto diagnostico" scarica uno zip con:

- `netmap.json`: versione, migration, configurazione dell'app, versione e dimensione del database con le righe di
  ogni tabella, utenti per ruolo (senza nomi), Active Directory, avvisi, copie dei backup, ultime scansioni;
- `api.log`: le ultime righe di log dell'API (dall'ultimo riavvio);
- `updater/`: stato, impostazioni e log dello script, e i log dei container se sono stati raccolti.

Password, chiavi e token non ci sono (nemmeno quelli di `.env` e `updater.conf`, che finiscono nel file con il
valore nascosto), ma **i log possono contenere indirizzi IP, nomi dei device e nomi utente**: guardalo prima di
mandarlo a qualcuno. Dal server, senza l'app: `updater/updater.sh diagnostics > diagnostica.txt`.

## Test

```powershell
docker compose exec api pytest
```

Comprendono una scansione vera contro due switch simulati (snmpsim, già installato nell'immagine).

Su GitHub il workflow **Test** (`.github/workflows/test.yml`) gira a ogni push e pull request: pytest,
`alembic check` (migration allineate ai modelli), build dell'interfaccia, sintassi degli script e file compose.
Poi `e2e/upgrade-test.sh` fa quello che farebbe un utente: installa con `install.sh` l'ultima versione
pubblicata, ci mette dei dati, costruisce le immagini del codice nuovo in un registro locale, chiede
l'aggiornamento come la pagina Aggiornamenti e controlla esito, versione e dati; poi fa un backup, lo scarica, lo
ricarica e lo ripristina come la pagina Backup. Infine i test nel browser
(`e2e/tests`, Playwright) girano su quell'installazione. A mano, su una macchina di prova con Docker e sudo
(non su un server con NetMap installato):

```bash
e2e/upgrade-test.sh                                  # installazione + aggiornamento
cd e2e && npm ci && npx playwright install chromium
set -a && . ./.upgrade-test.env && set +a && npx playwright test
../e2e/upgrade-test.sh --clean                       # toglie l'installazione di prova
```

I test nel browser girano anche contro lo sviluppo: `NETMAP_URL=http://localhost:5174 NETMAP_USER=... NETMAP_PASSWORD=... npx playwright test`
(creano i loro dati con il prefisso `e2e-` e li cancellano alla fine).

## Modifiche ai modelli

```powershell
docker compose exec api alembic revision --autogenerate -m "aggiunto campo xyz"   # descrivi cosa cambia
docker compose exec api alembic upgrade head
```

Lancia `revision` solo dopo aver cambiato un modello: senza modifiche crea una migration vuota.

## Struttura

```
backend/
  app/
    models/      tabelle (dcim.py infrastruttura, ipam.py indirizzamento, maps.py mappe)
    schemas/     validazione input/output
    api/         crud.py generatore endpoint, routes.py elenco entità, extra.py endpoint speciali
    services/    rules.py regole di coerenza, ipam.py, topology.py (porte, topologia, mappe, ricerca),
                 device_import_export.py
    discovery/   scansione SNMP: lettura (snmp.py), confronto (planner.py), applicazione, coda (runner.py)
    worker.py    processo che esegue le scansioni
    seed.py      dati di esempio
  alembic/       migration
  tests/
frontend/
  src/
    resources.jsx   colonne e campi di ogni entità: per aggiungere un campo al modulo basta qui
    pages/          elenco generico, scheda device, subnet, ricerca, editor mappa, scansioni, da approvare
    components/     moduli, selettore porte, finestre
    map/            nodo device, disposizione automatica, colori dei cavi
```

## Limiti noti

- I menu a tendina caricano al massimo 1000 elementi per tipo (sedi, device, VLAN...).
