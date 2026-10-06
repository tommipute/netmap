# NetMap: istruzioni per Claude Code

Rispondi sempre in **italiano**: l'utente lavora nell'IT aziendale (Windows, Docker Desktop) e legge l'inglese
ma non lo scrive volentieri. Anche i testi dell'interfaccia sono in italiano.

## Cos'è

Documentazione di rete in stile NetBox, separata dall'app inventory dell'utente (stesso stack, progetti indipendenti).
Device, porte, cavi, VLAN, subnet/IP e **mappe di rete** automatiche o disegnate a mano.
Dati inseriti a mano, importati da CSV o trovati dalla **scansione SNMP** (con approvazione).

| Fase | Contenuto | Stato |
|---|---|---|
| 1 | Modello dati + API REST | fatta, verificata |
| 2 | Interfaccia web (elenchi, moduli, scheda device, subnet, mappe) + import/export CSV dei device | fatta, verificata |
| 3 | Scansione SNMP con coda di modifiche da approvare | fatta (sezione "Scansione SNMP") |
| 4 | Stato live, "dov'è collegato?", login e ruoli, vista rack, export mappa, menu con ricerca | fatta, verificata (sezione "Fase 4") |

Test: `docker compose exec api pytest` (41 test, compresi quelli con due switch SNMP simulati).
Idee per dopo in `docs/roadmap.md`. **Niente integrazione con l'app inventory**: NetMap lavora da solo (deciso il 6/10/2026).

### Dove gira (due copie, stesso repository git, branch `main`, niente GitHub)

| Copia | Percorso | Note |
|---|---|---|
| PC Windows | `E:\Claude\NetMap` | Docker Desktop, `FILE_POLLING=true`; remote git `server` (chiave `~/.ssh/proxmox_ed25519` in `core.sshCommand`) |
| Server | LXC 103 "dev" sul Proxmox: `~/progetti/netmap` (utente `tommaso`) | 192.168.1.74 in LAN, NetBird `dev.netbird.cloud` / 100.111.74.88; `FILE_POLLING=false`; sessione Claude remota "dev" parte da `~/progetti` |

Interfaccia da remoto: http://dev.netbird.cloud:5174 (oppure http://100.111.74.88:5174). Ogni copia ha il suo database:
quello del server è nato dal dump del PC il 5/10/2026. Per allineare il codice: `git push server` / `git pull` dal PC;
sul server `receive.denyCurrentBranch=updateInstead` aggiorna la cartella, ma solo se lì non ci sono modifiche non salvate
(se lavori sul server, fai commit lì e dal PC `git pull`). `.env` e `backend/.secrets_key` non sono in git:
la chiave del server è una copia di quella del PC.

## Avvio e comandi

```powershell
copy .env.example .env
docker compose up -d --build
docker compose logs -f api web worker
docker compose exec api python -m app.seed          # rete di esempio + mappa "Sede principale"
docker compose exec api pytest                      # pytest e snmpsim sono già nell'immagine
docker compose exec api alembic revision --autogenerate -m "descrizione"
docker compose exec api alembic upgrade head
docker compose build api worker                     # dopo aver cambiato requirements*.txt
```

| Servizio | Indirizzo | Note |
|---|---|---|
| web (Vite + React) | http://localhost:5174 | proxy verso l'API per `/api`, `/docs`, `/openapi.json` |
| api (FastAPI) | http://localhost:8001/docs | reload automatico, codice montato da `./backend` |
| worker | — | esegue le scansioni in coda; `watchfiles` lo riavvia quando cambia il codice |
| monitor | — | stato live: ping + SNMP ifOperStatus ogni `MONITOR_INTERVAL_SECONDS` (0 = spento) |
| db (Postgres 16) | localhost:5433 | |

Porte scelte apposta per non scontrarsi con l'app inventory: **non cambiarle**.
`backend/start.sh` al primo avvio genera da solo la migration iniziale se `alembic/versions/` è vuota.
`.gitattributes` forza LF su tutti i file (su Windows un CRLF rompe gli `.sh` nei container).
Le immagini installano `requirements-dev.txt` (pytest, snmpsim, pysmi).
La migration `1a6c6b905200_descrizione_modifica` è vuota (nata copiando alla lettera il comando del README): innocua.
Container con `TZ=Europe/Rome`, così gli orari nei log delle scansioni sono locali.

## Backend (`backend/app`)

Stack: Python 3.12, FastAPI, SQLAlchemy 2 (sincrono), Alembic, Pydantic 2, psycopg 3, Postgres, pysnmp 7, cryptography.

- `models/`: `base.py` (Base con naming convention dei vincoli, mixin), `enums.py`, `dcim.py` (Site, Location,
  Rack, Manufacturer, DeviceType, DeviceRole, Device, Interface, Cable), `ipam.py` (VRF, VLAN, Prefix, IPAddress),
  `maps.py` (NetworkMap, MapNode), `discovery.py` (SnmpProfile, DiscoveryJob, DiscoveryRun, DiscoveryChange).
- `schemas/`: input/output Pydantic. `views.py` contiene le risposte calcolate (porte, topologia, ricerca, import).
- `api/crud.py`: **generatore di endpoint CRUD**. `api/routes.py` registra ogni entità con una riga di config.
  `api/extra.py` contiene gli endpoint non-CRUD, `api/discovery.py` quelli della scansione.
- `services/rules.py`: regole di coerenza come **hook** chiamati prima del salvataggio (anche cifratura dei segreti SNMP).
  `services/topology.py`: porte, topologia, mappe, ricerca. `services/ipam.py`: utilizzo e IP liberi.
  `services/device_import_export.py`: export CSV/JSON e import CSV dei device (ogni riga in un SAVEPOINT: le righe
  sbagliate finiscono negli errori e le altre passano; il dry-run dà gli stessi errori e poi fa rollback).
- `core/net.py`: normalizzazione MAC/IP/prefissi e chiavi di ordinamento. `core/secrets.py`: cifratura Fernet.
- `discovery/`: scansione SNMP (sezione dedicata). `worker.py`: processo del container worker.

### Convenzioni da rispettare

- **Stati e tipi sono stringhe** nel DB (`String(20)`), validate da `StrEnum` in `models/enums.py`.
  Negli schemi input c'è `use_enum_values=True` + `validate_default=True` così al DB arrivano sempre `str`
  (psycopg 3 serializzerebbe gli Enum Python per nome). Nei default dei modelli usa `.value`.
- **Schemi**: `XBase` = campi modificabili, `XCreate(XBase)` = + campi fissi dopo la creazione
  (es. `site_id` di Location/Rack/Map, `device_id` di Interface), `XUpdate = make_partial(XBase)` per PATCH,
  `XRead(XCreate, [DiscoveryRead], ReadSchema)`. Gli input hanno `extra="forbid"`: un campo non previsto dà 422.
  `make_partial` copia solo annotazioni e metadata: le validazioni vanno messe nei tipi (`Annotated[..., AfterValidator]`),
  non in `@field_validator`, altrimenti nei PATCH si perdono.
- Campi di input che non sono colonne (es. `tagged_vlan_ids`, `community`) vengono saltati da `apply_data` e gestiti dall'hook.
- **Ogni entità principale** ha `custom_fields` (JSON). Device, Interface, Cable, IPAddress hanno anche
  `source` (`manual`/`snmp`) e `last_seen_at`, usati dalla scansione: non toglierli.
- **IP**: `address` con maschera (`10.0.0.5/24`), `host` senza, `sort_key` binaria (versione + 16 byte) per ordinare
  correttamente e cercare per intervallo (`between`) sia su Postgres che su SQLite.
- **IP di management** (= primario): niente FK `devices.primary_ip_id` (creava un ciclo di FK). C'è
  `IPAddress.is_primary`, **uno solo per device**: `ip_hook` rifiuta (422) un secondo flag invece di spostarlo.
  Si cambia dal campo `management_ip` del device (input non colonna; assente = invariato, vuoto = nessuno):
  `rules.set_management_ip`, usata anche dall'import CSV, mette l'IP sulla porta di quello attuale, poi su una
  porta di management, altrimenti crea "mgmt"; il vecchio IP resta senza flag. In lettura `Device.management_ip`
  è una `column_property` (definita in `models/__init__.py`) e le interfacce espongono `device_management_ip`,
  che nel modulo degli IP blocca la casella (`lockedBy` dei campi bool in ResourceForm).
- **Unicità con NULL** (VLAN globale, VRF globale): Postgres considera i NULL diversi, quindi i controlli sono negli hook.
- **Eliminazioni**: sede/ruolo/modello/VRF in uso → RESTRICT (l'API risponde 409). Device → porte → cavi in CASCADE.
  IP di una porta eliminata → `interface_id` NULL. Mappe di una sede eliminata → CASCADE.
- **Errori API**: 404 non trovato, 422 dati non validi o id collegato inesistente (`check_foreign_keys`),
  409 duplicato o elemento in uso (IntegrityError). Messaggi in italiano, leggibili dall'utente.
- Relazioni `lazy="joined"`: `Interface.device`, `Cable.a_interface/b_interface`, `IPAddress.interface`.
  Le letture espongono nomi già risolti (`device_name`, `a_device_name`, `interface_name`...).
- **JSONB riordina le chiavi**: se l'ordine conta, salva una lista (es. `DiscoveryChange.diff`), non un dict.
- Per aggiungere un'entità: modello → import in `models/__init__.py` → schemi → riga in `api/routes.py`
  (+ hook se servono regole) → migration autogenerate → voce in `frontend/src/resources.jsx` → test.
- Test: `tests/` con SQLite in memoria e `PRAGMA foreign_keys=ON`; `conftest.py` sistema i SAVEPOINT di pysqlite
  e usa una chiave Fernet usa e getta. Fixture: `client`, `session_factory`. Aggiungi un test per ogni nuova regola.

### Endpoint non-CRUD

| Endpoint | Uso |
|---|---|
| `GET /api/devices/{id}/ports` | porte in ordine naturale con cavo, device/porta remota, VLAN, IP, stato operativo |
| `GET /api/devices/{id}/neighbors` | device collegati via cavo |
| `GET /api/prefixes/{id}/utilization` · `/ip-addresses` · `/available-ips?limit=` | IPAM |
| `GET /api/topology?site_id=&location_id=` | nodi + cavi di un ambito |
| `GET /api/maps/{id}/view` | device in mappa con posizioni salvate (o `null`), cavi, device aggiungibili |
| `PUT /api/maps/{id}/nodes` | sostituisce l'elenco `[{device_id, x, y}]` della mappa |
| `GET /api/search?q=` | device (nome, seriale, asset tag), MAC anche parziale/formato Cisco, IP, DNS |
| `GET /api/devices/export?format=csv\|json&<filtri>` · `GET /api/devices/import/template` · `POST /api/devices/import` | import/export dei device |
| `POST /api/discovery-jobs/{id}/run` | mette in coda una scansione (409 se ce n'è già una in coda o in corso) |
| `GET /api/discovery-runs?job_id=` · `/discovery-runs/{id}` | storico delle scansioni con log |
| `GET /api/discovery-changes?status=&job_id=&device_id=` · `/discovery-changes/count` | modifiche proposte, contatore |
| `POST /api/discovery-changes/approve` · `/reject` con `{ids}` | applica (ognuna in un SAVEPOINT) / rifiuta |
| `GET /api/endpoints?q=&device_id=&interface_id=` | "dov'è collegato": MAC/IP/DNS → switch, porta, VLAN, luogo |
| `GET /api/status/summary` · `POST /api/devices/{id}/check` | riepilogo su/giù · controllo immediato di un device |
| `GET /api/racks/{id}/elevation` | vista frontale: device con unità, altezza, sovrapposizioni |
| `/api/auth/status` · `/setup` · `/login` · `/logout` · `/me` · `/password` | login (sempre accessibili) |

Elenchi CRUD: `GET /api/<entità>?limit=&offset=&q=&<filtri>` → `{total, items}`; `limit` massimo 1000.
Anche `/snmp-profiles` e `/discovery-jobs` sono CRUD generati.

## Scansione SNMP (fase 3, `backend/app/discovery/`)

Flusso: job → riga `queued` in `discovery_runs` (la coda è il database, niente Redis/ARQ) → il worker la prende
(`FOR UPDATE SKIP LOCKED`) → `snmp.collect_all` legge gli host → `Planner` confronta col database →
`runner.record` salva le modifiche → l'utente approva in "Da approvare" → `apply.apply_change`.

- `targets.py`: `10.0.0.0/24`, `10.0.0.5`, `10.0.0.1-10.0.0.20`, `10.0.0.1-20`; massimo `discovery_max_hosts` (4096).
- `snmp.py`: pysnmp **7.x** (lextudio), `pysnmp.hlapi.v3arch.asyncio`: `get_cmd`, `bulk_walk_cmd`
  (`lexicographicMode=False, lookupMib=False`), `await UdpTransportTarget.create(...)`, `engine.close_dispatcher()`.
  Profili provati in ordine: vince il primo che risponde al get di sistema. Legge system, IF-MIB (ifTable + ifXTable),
  IP-MIB (ipAddrTable + ipAddressTable per IPv6), ENTITY-MIB (seriale e modello dello chassis), LLDP (le porte
  locali si abbinano per nome/MAC perché `lldpLocPortNum` non sempre è l'ifIndex; il mgmt address sta nell'indice)
  e CDP. Restituisce `HostData` (dataclass) e non tocca il database. Attenzione: il pacchetto `snmpsim-lextudio`
  installa il vecchio `pysnmp-lextudio` in conflitto; usare `snmpsim` >= 1.2.
- `matching.py`: device = seriale → sysName senza dominio → IP registrato → MAC di una porta;
  porte con `norm_ifname` ("GigabitEthernet1/0/1" = "Gi1/0/1"); `ifType` → tipo (ethernet resta `copper`).
- `planner.py`: regole. **VLAN**: quelle lette (Q-BRIDGE: nomi, PVID, bitmap egress/untagged; Cisco:
  CISCO-VTP-MIB nomi e trunk, CISCO-VLAN-MEMBERSHIP-MIB access; 1 e 1002-1005 ignorate) diventano VLAN della sede
  (`vlan/create`, automatiche con `auto_new_interfaces`); le porte prendono modo access/trunk, untagged e tagged
  (proposta `interface:vlans:<id>` con i VID, risolti in VLAN all'applicazione). **Silenziosi**: last_seen_at, oper_status, if_index, sys_name, sys_descr.
  **Automatici se attivati nel job**: porte nuove su device noti, IP nuovi su porte note.
  **Automatici**: campi di oggetti con `source = snmp`. **Sempre da approvare**: device nuovi (porte e IP compresi,
  in un'unica modifica), cavi nuovi o diversi (verso fisso: porta con id minore = lato A), porte sparite
  (`stale`, approvare = eliminare), campi di oggetti inseriti a mano. Il nome di un device non viene mai cambiato.
- `runner.py`: `record` deduplica per `key` (la stessa modifica aggiorna la riga pending), non ripropone una modifica
  rifiutata con gli stessi dati, cancella le pending dello stesso job+host che la scansione non vede più;
  un'applicazione automatica fallita resta pending con l'errore. Ogni host in un SAVEPOINT.
  `schedule_due_jobs`, `claim_next_run`, `recover_interrupted` (all'avvio del worker: running → failed).
- `apply.py`: una funzione per (oggetto, azione); riusa gli hook di `rules.py`; errori → `ApplyError` leggibile.
- Segreti: community e chiavi cifrate con Fernet, chiave da `SECRETS_KEY` oppure generata in `backend/.secrets_key`
  (gitignored, condivisa da api e worker: **non cancellarla**, altrimenti i profili vanno reinseriti).
  Le API non restituiscono mai i segreti, solo `has_community`, `has_auth_key`, `has_priv_key`.
  Campo segreto assente nel PATCH = invariato, `null` o vuoto = cancellato.
- Test: `tests/snmp_devices.py` definisce due switch finti (file snmprec per snmpsim + `host_data()` = risultato atteso).
  `test_discovery.py` usa un collector finto; `test_snmp_collect.py` avvia snmpsim su 127.0.0.1/.2:11161
  (snmpsim non gira come root: `--process-user=nobody` e dati in una cartella leggibile; gli serve `pysmi`;
  in SNMPv3 sceglie i dati dal context name, quindi nel test `context="public"`).
- **Rete di laboratorio** (`app/lab/`, profilo compose `lab`): un container per apparato (`lab-fw`, `lab-core`,
  `lab-sw-p1..p3`, stessa immagine del worker) con IP fisso in 172.31.250.0/24; ognuno esegue
  `python -m app.lab agent <nome>` = snmpsim su 0.0.0.0:161, community `public`, e risponde al ping.
  Dati in `app/lab/devices.py` (stesso formato di `tests/snmp_devices.py`; il generatore `.snmprec` è
  `app/lab/snmprec.py`). api, worker e monitor sono anche sulla rete `lab`. `python -m app.lab prepara` crea sede,
  profilo, scansione (172.31.250.10-30, .1 è il gateway) e mappa. Verificato: lettura identica ai dati, 5 device,
  4 cavi (anche da CDP), endpoint con VLAN, guasto simulato con `docker compose stop lab-sw-p3`.
- Prova dal vivo: nel DB c'è la sede "Laboratorio SNMP (simulato)" con profilo, job e mappa di prova; i due switch
  simulati si avviano nel container worker (snmpsim su 127.0.0.1/.2:11161) e si fermano al riavvio del container.

## Fase 4: stato live, dov'è collegato, login, rack

- **Login** (`api/auth.py`, `core/auth.py`, `models/auth.py`): password scrypt, token JWT HS256 fatto in casa
  (niente librerie), in cookie httpOnly o `Authorization: Bearer`. `token_version` sull'utente: cambiare password
  o disattivarlo chiude le sessioni. Ruoli `viewer` (legge), `editor` (scrive e approva), `admin` (anche `/users`).
  Il controllo è una dipendenza sul router `protected` in `api/routes.py`: i metodi non GET richiedono editor/admin.
  Primo avvio senza utenti → la pagina di login crea l'amministratore. Riga di comando:
  `docker compose exec api python -m app.users list|create|password <utente>` (chiede la password: serve `-it`).
  `AUTH_ENABLED=false` toglie il login (solo prove in locale); nei test `conftest.py` lo gestisce.
- **Stato live** (`services/monitor.py`, `monitor.py`): device attivi con IP primario; raggiungibile se risponde
  al ping o all'SNMP. Colonne `reachable` (NULL = mai controllato), `last_check_at`, `reachable_changed_at`, `rtt_ms`;
  `oper_status` delle porte da ifOperStatus (abbinate per `if_index`).
- **Endpoint** (`services/endpoints.py`, tabella `endpoints`): dopo ogni scansione unisce tabelle MAC
  (BRIDGE/Q-BRIDGE), PVID/nomi VLAN e ARP; scarta gli uplink; tiene porta precedente e data dello spostamento.
- Frontend: `auth.jsx` (`useAuth()` → `canEdit`, `isAdmin`; con login spento tutto permesso), `LoginPage`,
  `PasswordDialog`, `EndpointsPage` (`/where`), `RackPage` (`/racks/:id`), voce `NAV` con `admin: true`.
  **Ogni pulsante che scrive va nascosto con `canEdit`** (il backend risponde comunque 403).
  Un 401 dall'API (fuori da `/auth/`) emette `netmap:unauthorized` e riporta al login.
  `RefSelect`/`RefLabel` usano `useOptionsPage`: oltre i 1000 elementi diventano una ricerca lato server.
  Mappa: aggiornamento ogni 30 s (senza toccare le posizioni), export PNG/SVG con `html-to-image` (tutta la mappa,
  senza pallini di collegamento; il CSS di Google Fonts ha `crossorigin` apposta per incorporare i font), stampa.
- Verifica nel browser (6/10/2026, Playwright): login admin e sola lettura, filtro "non rispondono",
  "Dov'è collegato?", rack, utenti, export PNG/SVG, logout, schermo da telefono. Corretti: filtro `reachable`
  mancante sui device (il parametro veniva ignorato), font e pallini nell'immagine esportata.

## Frontend (`frontend/src`)

Stack: Vite 5, React 18, react-router-dom 6, `@xyflow/react` 12 (React Flow), `html-to-image` (export mappa). CSS semplice.

- `resources.jsx`: **cuore dell'interfaccia**. Per ogni entità: `path`, titoli, `label(o)`, `detail(o)` opzionale,
  `filters`, `columns` (`type`: ref, badge, select, mono, bool, color, oppure `render`), `fields`
  (`type`: text, textarea, lines, number, select, ref, refmulti, bool, color, interface, kv, secret).
  Opzioni dei campi: `required`, `default`, `createOnly` (mostrato disabilitato in modifica e non inviato),
  `dependsOn` + `waitLabel` (es. posizione filtrata per sede, svuotata se cambia la sede), `params`,
  `showIf(values)` + `hiddenValue` (valore inviato quando il campo è nascosto), `freeOnly` (solo porte libere),
  `ordered` (refmulti con numero d'ordine), `savedHint(item)` (segnaposto dei campi `secret` già salvati).
  `NAV` accetta chiavi di risorse oppure pagine speciali `{ to, title, badge }`.
- Elenchi (`ResourcePage`): selezione multipla con eliminazione in blocco; modifica in blocco se la risorsa ha
  `bulkFields` (`components/BulkEditDialog.jsx`, una PATCH per elemento, riusa `FieldControl` del modulo).
- `components/ResourceForm.jsx`: in creazione non invia i `null` (valgono i default del backend),
  in modifica li invia per svuotare i campi; un `secret` vuoto in modifica non viene inviato.
- `hooks.js`: `useApi(url)` con `reload`, `useOptions(path, params)` per i menu a tendina (cache condivisa),
  `invalidate()` da chiamare dopo **ogni** scrittura, `usePendingCount()` per il contatore di "Da approvare".
- `pages/`: `ResourcePage` (elenco generico, montato con `key` per entità; per i device anche export/import),
  `DevicePage` (porte, aggiunta in blocco con `Gi1/0/[1-48]`, collega/scollega, dati della scansione),
  `PrefixPage`, `SearchPage`, `MapEditor`, `DiscoveryJobPage` (avvio e storico con log, aggiornato ogni 2 s
  mentre una scansione è in corso), `ChangesPage` (Da approvare, raggruppata per device; filtri in query string
  `status`, `job_id`, `device_id`).
- **Mappa** (`pages/MapEditor.jsx`, `map/`): posizione = quella corrente > quella salvata > calcolata.
  Se nessun device ha una posizione salvata parte la disposizione gerarchica (`map/layout.js`): i device dello
  stesso rack formano un blocco, impilati per unità (la più alta in cima); un blocco per colonna, una riga per
  `DeviceRole.level` del suo device più in alto, ordinamento per baricentro dei vicini, massimo 8 blocchi per riga;
  una riga che va a capo lascia un corridoio libero sotto i device sopra. I device nuovi finiscono in fila sotto.
  **Bolle dei rack** (`map/RackNode.jsx`, `rackBubbles()` in MapEditor): nodi `type: 'rack'` calcolati a ogni render
  dai device con `rack_id` (non stanno nello stato `nodes`, quindi non si salvano), `zIndex: -1`, nome in basso
  (in alto c'è la linea dei cavi). Clic sul nome = seleziona i device del rack per spostarli insieme.
  Spostamenti → `dirty` → "Salva disposizione". Aggiungere/togliere un device (mappe manuali) salva subito.
  Collegamento trascinando tra due device → `CableDialog` per scegliere le porte.
  **Cavi** (`map/geometry.js`, calcolata in MapEditor per tutta la mappa; `map/CableEdge.jsx` disegna soltanto):
  punti di attacco in `map/anchors.js` (lato scelto da solo: sotto/sopra o destra/sinistra se affiancati; sullo
  stesso lato i cavi dello stesso tipo condividono il punto, tipi diversi e cavi verso lo stesso device, es. LAG,
  hanno punti separati). Ad angolo (predefinito) con `map/routing.js`: A* su griglia, **mai sotto un device né
  dentro la bolla di un altro rack**, riga orizzontale preferita 28 px sopra il device di arrivo; tratti di
  uscita/entrata più corti tra device vicini. Oppure dritti (scelta in localStorage).
  **Nomi delle porte mai sovrapposti**: piazzati uno alla volta (prima i cavi corti), ognuno vicino al suo device
  fuori dal tratto condiviso; se non c'è posto un'etichetta unica "porta – porta", altrimenti niente (si vede
  cliccando il cavo). Ostacoli per le etichette: device, altre etichette, nome del rack nella bolla.
  **Evidenza**: con un device, un cavo o un rack selezionato, il resto prende `is-faded` / `cable--faded`.
  I pallini (4, per collegare trascinando) si vedono solo passando sopra il device o se è selezionato.
  I cavi partono dal device di livello più alto; colore per tipo (`map/cables.js`), spessore per velocità ≥10G,
  tratteggio se pianificati. `deleteKeyCode={null}`: niente cancellazioni accidentali da tastiera.
  `fitView` parte quando tutti i device hanno `measured` (con un timer fisso non scattava a pagina nascosta;
  `useNodesInitialized()` non va bene perché le bolle dei rack hanno già le misure).

### Stile

Token in `styles.css` (chiaro/scuro con `prefers-color-scheme`). Palette ispirata ai rack: grigio-azzurro, etichette
bianche, accento acqua come la fibra OM3 (`--accent`). Font IBM Plex Sans + IBM Plex Mono (solo per porte, IP, MAC).
Device in mappa = etichetta da rack con banda colorata del ruolo. Colori cavi da convenzione reale:
rame blu, fibra multimodale acqua, monomodale gialla, DAC grigio scuro.
Testi: italiano, sentence case, frasi semplici, pulsanti che dicono cosa fanno ("Salva disposizione", "Crea collegamento").
**Pulsanti solo con icona** (scelta dell'utente), anche Nuovo…, Salva disposizione, Approva/Rifiuta, Avvia scansione:
`IconButton` / `IconLink` di `components/Icon.jsx` (SVG a mano, niente librerie); il testo va in `label`, che diventa
tooltip e `aria-label`. Restano scritti solo i pulsanti dentro le finestre (Annulla, Crea, Salva modifiche, Accedi…).
Icona nuova = un path in `PATHS`.

## Decisioni già prese con l'utente (non rimetterle in discussione senza chiedere)

- App **separata** dall'inventory, dedicata solo alla rete, e **non deve integrarsi** con lei: lavora da sola.
- Mappe sia automatiche sia manuali: `NetworkMap.auto_include` (tutti i device della sede/posizione) oppure scelti a mano.
- La scansione **non sovrascrive** i dati inseriti a mano: propone modifiche che l'utente approva.
- Custom fields liberi su tutte le entità principali.

## Verifiche fatte (5/10/2026)

I 7 punti a rischio della prima stesura (scritta senza poterla eseguire) sono verificati: migration
(`alembic check` pulito), filtri in `/docs`, validazioni nei PATCH (test), join annidati con paginazione,
React Flow (fitView, MiniMap, connessioni), reload di uvicorn e Vite su Windows, seed (test).
Bug trovati e corretti: import CSV (errore 500 su CSV vuoto, una riga sbagliata bloccava tutto, stato azzerato
negli aggiornamenti, IP spostati in silenzio da un altro device) e `remote_interface` mancante nelle porte.

## Limiti noti

- Login senza HTTPS: prima di esporre l'app fuori dalla rete interna mettere un reverse proxy HTTPS e `COOKIE_SECURE=true`.
- Scansione: i device scoperti restano senza ruolo; un trunk Cisco senza VTP mostra solo le VLAN che lo switch conosce;
  rame o fibra non si ricava dall'ifType.
