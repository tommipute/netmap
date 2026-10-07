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

Test: `docker compose exec api pytest` (58 test, compresi quelli con due switch SNMP simulati).
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
  IP di una porta eliminata → `interface_id` NULL. `DELETE /api/devices/{id}?with_ips=true` elimina anche gli IP
  (`device_delete_hook`; i delete_hook ricevono i parametri della richiesta). Nel frontend `deleteOptions` della
  risorsa -> `DeleteDialog` con le caselle. Mappe di una sede eliminata → CASCADE.
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
| `GET /api/devices/{id}/ports` | porte (prima quelle di management: `mgmt_only` o nome mgmt/management, poi in ordine naturale) con cavo, device/porta remota, VLAN, IP, stato operativo |
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
- **Ruolo**: `DeviceType.default_role_id`; `device_hook` lo dà ai device senza ruolo alla creazione o quando cambia
  il modello; `device_type_hook` lo dà ai device esistenti senza ruolo quando lo si imposta. Per i modelli nuovi la
  scansione lo indovina (`services/roles.py`: parole della sysDescr -> ruoli esistenti per nome).
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
  `RefSelect` ha in fondo "+ Nuovo …" (solo editor, risorse in `CREATABLE`: sedi, posizioni, rack, ruoli, modelli,
  produttori, VLAN, VRF, profili SNMP): apre `ResourceForm` sopra il modulo con i filtri del menu come valori
  (es. la sede per rack e posizioni) e sceglie l'elemento appena salvato. Menu vuoto → "— nessuna voce in questa
  sede". Finestre una sopra l'altra: `Modal` tiene l'elenco di quelle aperte (Esc chiude solo l'ultima) e
  `ResourceForm` ferma la propagazione dell'invio (con i portali React l'evento arriverebbe al modulo sotto).
  Rack e posizioni sono filtrati per la sede del device: un rack di un'altra sede non compare (scelta voluta).
  **Stampa**: pulsante su scheda device, rack e mappa; in `@media print` il foglio è sempre chiaro (token
  ridefiniti), spariscono pulsanti, colonna azioni, avvisi e ciò che ha `.no-print` (storico del device);
  `PrintFooter` (Bits.jsx, `.print-only`) scrive data e utente. Le unità del rack si stringono a 17 px e il layout a una colonna (il foglio è largo come un telefono) è annullato.
  **Rack** (`RackPage`): "+" e clic su un'unità libera → `AddDeviceDialog` (device della sede del rack, unità con
  controllo delle sovrapposizioni lato client usando l'altezza del modello); i device si trascinano (eventi pointer,
  anche col dito, soglia 5 px: sotto è un clic che apre il device) su un'altra unità (riquadro verde/rosso, unità
  occupate rifiutate) o in "Nel rack senza unità" (unità tolta); X nell'elenco = fuori dal rack. Per i membri
  di uno stack si salva `rack_position` del membro (`member_id` nella vista rack). Uscendo dal rack (o cambiando
  rack) `device_hook` svuota le unità dei membri.
  Mappa: aggiornamento ogni 30 s (senza toccare le posizioni), export PNG/SVG con `html-to-image` (tutta la mappa,
  senza pallini di collegamento; il CSS di Google Fonts ha `crossorigin` apposta per incorporare i font), stampa.
- Verifica nel browser (6/10/2026, Playwright): login admin e sola lettura, filtro "non rispondono",
  "Dov'è collegato?", rack, utenti, export PNG/SVG, logout, schermo da telefono. Corretti: filtro `reachable`
  mancante sui device (il parametro veniva ignorato), font e pallini nell'immagine esportata.

## Stack (`StackMember`, tabella `stack_members`)

- Decisione con l'utente (7/10/2026): **uno stack è un solo device** (un IP, una configurazione, porte Gi1/0/x,
  Gi2/0/x, un nodo in mappa); i singoli switch sono membri del device: numero, modello, seriale, unità nel rack del
  device, note. Switch in cascata con IP propri restano device separati.
- CRUD `/api/stack-members?device_id=` (`stack_member_hook`: numero unico nello stack, unità solo se il device è in
  un rack). Nel frontend la risorsa `stack-members` non ha voce di menu: sezione "Stack" nella scheda device
  (compare se ci sono membri; pulsante con l'icona `stack` nella testata per aggiungere il primo).
- Scansione: `_chassis` in `snmp.py` legge tutti gli chassis della ENTITY-MIB (numero = entPhysicalParentRelPos,
  altrimenti l'ordine) → `HostData.members` (vuoto se c'è un solo chassis). Planner `_stack`: membri nuovi
  automatici, seriale/modello cambiati automatici se il membro è `snmp` (o vuoto), altrimenti da approvare;
  membro sparito → `stale` da approvare. Device nuovo: i membri arrivano con lui (`stack_members` nei dati).
  Nei dati simulati il quarto valore di `entities` è il numero del membro (core del laboratorio e SW1 dei test: 2).
- Vista rack: se almeno un membro ha l'unità, il device compare una volta per membro (`member` nella risposta).
  Mappa: `stack_size` nei nodi → etichetta "stack ×N". Ricerca: seriale di un membro → device dello stack.

## Storico modifiche (`services/audit.py`, tabella `audit_log`)

- Scritto da solo all'evento `after_flush` di ogni sessione (registrato importando il modulo in `database.py`):
  vale per API, modifiche in blocco, scansione, import. Righe nella stessa transazione (rollback = spariscono).
- Chi: `session.info["audit_user"]` (lo mette `current_user` in `api/auth.py`), `session.info["audit_source"]`
  (`scansione` in `execute_run` e `apply_change`, `import` nell'import CSV; altrimenti `utente`/`sistema`).
- Non registra i campi in `IGNORED` (stato live, last_seen, if_index...), i segreti (solo "cambiata"), né porte e
  IP creati insieme al loro device nella stessa transazione. I riferimenti (`*_id`) si salvano con il nome.
- `device_id`/`device_id_2` (cavi) per lo storico nella scheda del device, anche dopo l'eliminazione.
- API `GET /api/audit-log`; pagina "Storico modifiche" (`/history`) e sezione nella scheda device.
- **Nelle prove**: dopo aver usato un utente di prova cancellare anche le sue righe di storico.
- **Cosa è cambiato** (`services/summary.py`, `GET /api/whats-changed?hours=|since=`, pagina `/whats-changed`):
  conteggi dello storico per origine e azione, device creati/eliminati, giù adesso (`new` = caduti nel periodo),
  tornati su, endpoint nuovi (`first_seen_at`) e spostati (`moved_at`), scansioni (fallite) e modifiche da approvare.
  Nella pagina le liste dei device mostrano gli ultimi 5 ("Mostra tutti"); i riquadri portano alla pagina giusta
  (Modifiche → `/history?since=` dello stesso periodo) o scorrono alla loro sezione.
- Vite in sviluppo a volte resta con una versione a metà di un file modificato più volte di fila ("does not provide
  an export named 'default'", pagina bianca): `docker compose restart web`.

## Avvisi (`services/alerts.py`, tabelle `alert_channels`, `alert_states`)

- Canali email (smtplib), webhook (JSON `{"text"}` o scheda adattiva per i Workflows di Teams), Telegram; invio con
  la libreria standard. Segreto unico cifrato `secret_enc` (password SMTP / URL webhook / token), input
  `smtp_password`/`webhook_url`/`telegram_token` gestiti da `alert_channel_hook`. Solo amministratori.
- `process_alerts` gira nel monitor dopo ogni controllo: per canale, un messaggio con i device giù da almeno
  `delay_minutes` (una volta, stato in `alert_states`) e uno con quelli tornati. Invio fallito → `last_error`,
  si riprova al giro dopo. `POST /api/alert-channels/{id}/test` per la prova. Nei test: `sender` finto.

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
- **Tabelle degli elenchi** (`components/TableTools.jsx`): colonne da mostrare/nascondere e riordinare (pulsante
  "Colonne della tabella", salvate in localStorage `netmap.table.<risorsa>`; colonne con `hidden: true` partono
  nascoste), riga di filtri sotto le intestazioni (pulsante a imbuto; spegnendola i filtri si svuotano) e ordinamento
  cliccando l'intestazione. Il filtro si ricava dal tipo della colonna (testo → `__contains`, ref/badge/select/bool
  → `__eq` con la voce "(vuoto)" → `__isnull`); le colonne con `render` lo dichiarano con `filter` (o `false`)
  e `sortField`. L'API (`api/crud.py`, `apply_column_filters`) accetta `<campo>__contains|__eq|__isnull` e
  `sort=[-]campo` per tutte le entità; anche l'export dei device usa gli stessi filtri.
- Elenchi (`ResourcePage`): i filtri della barra stanno nell'indirizzo (`?site_id=…&reachable=…`, cambiati con
  `replace`): un link alla stessa pagina con altri filtri aggiorna l'elenco (prima venivano letti solo all'apertura).
- Elenchi (`ResourcePage`): selezione multipla (le azioni prendono il posto del conteggio nella riga dei filtri,
  così la tabella non si sposta) con eliminazione in blocco; modifica in blocco se la risorsa ha
  `bulkFields` (`components/BulkEditDialog.jsx`, una PATCH per elemento, riusa `FieldControl` del modulo): device,
  modelli, porte, cavi, posizioni, rack, ruoli, subnet, IP, VLAN. I campi che dipendono dalla sede usano la sede
  nuova o quella comune agli elementi, anche se la sede non è modificabile in blocco (rack, posizioni).
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
  Livelli (`effectiveLevels` in layout.js, usati anche per il verso dei cavi): quello del ruolo; senza ruolo un
  livello sotto il device con ruolo più vicino, e in un gruppo tutto senza ruoli in alto va il device con più cavi.
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
  uscita/entrata più corti tra device vicini. Solo cavi ad angolo: l'opzione "cavi dritti" è stata tolta (scelta
  dell'utente). Un device nel margine della partenza/arrivo di un cavo diventa ostacolo senza margine (prima veniva
  ignorato e il cavo gli passava sotto); senza strada si riprova con margini di 3 px. Partenza e arrivo della
  ricerca arrotondati a mezzo pixel come la griglia (un tratto lungo quanto il nome della porta faceva partire la
  ricerca da un'altra cella: tratti storti). **Raddrizzamento** (fine di `assignAnchors`): capi quasi allineati
  (< 24 px) tra lati che si guardano → si sposta il capo con meno cavi sul suo lato, se resta a ≥ 18 px dagli altri.
  **Connettore** (`Plug` in CableEdge): blocchetto del colore del cavo sul bordo del device dove entra il cavo
  (`geometry.ends`), così un cavo che passa vicino non sembra collegato; i nomi delle porte partono dopo di lui.
  Il nome del rack nella bolla va a destra se in basso a sinistra passa un cavo (`labelSide` in MapEditor).
  **Nomi delle porte** (`map/geometry.js`): sul bordo del device, non a metà cavo. Con i nomi attivi ogni cavo ha il
  suo punto di attacco; il tratto dritto in uscita si allunga quanto il nome, scritto lungo il tratto (verticale se
  il cavo esce da sopra/sotto, `CableEdge` lo ruota). Tra due device vicini e allineati i nomi vanno in orizzontale
  accanto al cavo, solo se in fila non ci stanno. Un device con tanti cavi sopra o sotto si allarga quanto serve (`nodeWidths` in geometry.js ->
  `data.width`); "Disponi" lo tiene centrato e allontana i vicini nella fila. Se sopra/sotto un device c'è subito un altro device (rack impilati) il cavo esce di lato
  (`sideIfBlocked` in anchors.js).
  **Cavi sistemati a mano** (tabella `map_cable_routes`, per mappa e cavo: `points` = spigoli dal lato A al lato B,
  `ends` = `{a, b: {side, f}}`; `view.routes` con `a_end`/`b_end`, `PUT /api/maps/{id}/routes` insieme a "Salva
  disposizione"). Scelta dell'utente: niente punti liberi né "+" (provati e scartati), si **spostano i tratti**.
  Cavo selezionato (solo editor, `zIndex` 10): `CableEdge` disegna una barretta su ogni tratto interno (si sposta
  solo di traverso: `moveSegment`, i tratti attaccati ai device restano lunghi almeno quanto il nome della porta)
  e un pallino su ogni estremità (scorre sul bordo del device, anche su un altro lato: `endOnRect` → anchors.js
  la tiene fissa). Su un cavo automatico i tratti sono quelli del percorso calcolato. Con spigoli salvati il
  percorso è `connect` in geometry.js (primo/ultimo spigolo riallineati al lato; se stanno dietro il lato il cavo
  esce dritto e gira attorno). Solo estremità spostate = percorso ancora automatico. Il clic che chiude un trascinamento non arriva alla mappa. "Torna al percorso automatico".
  **Evidenza**: con un device, un cavo o un rack selezionato, il resto prende `is-faded` / `cable--faded`.
  **Ricerca nella mappa** (`map/MapSearch.jsx`): nome/IP dei device in mappa subito, poi `/search` (MAC, IP,
  endpoint; i risultati hanno `interface_id`); il risultato seleziona il cavo della porta trovata (o il device),
  lo centra e scrive "Trovato" nel pannello. **Vista VLAN**: menu con le VLAN della mappa (`view.vlans`); evidenzia i
  cavi con la VLAN (`edge.vlan_ids`: quelle in comune ai due lati, o quelle dell'unico lato documentato), i device
  che l'hanno su una porta (`node.vlan_ids`) e quelli in fondo a quei cavi.
  I pallini (4, per collegare trascinando) si vedono solo passando sopra il device o se è selezionato.
  I cavi partono dal device di livello più alto; colore per tipo (`map/cables.js`), spessore per velocità ≥10G,
  tratteggio se pianificati. `deleteKeyCode={null}`: niente cancellazioni accidentali da tastiera.
  `fitView` parte quando tutti i device hanno `measured` (con un timer fisso non scattava a pagina nascosta;
  `useNodesInitialized()` non va bene perché le bolle dei rack hanno già le misure).

### Stile

Token in `styles.css`. Tema chiaro/scuro: segue il sistema (`prefers-color-scheme`, regola su
`:root:not([data-theme="light"])`) oppure la scelta nel menu utente (`theme.js`, localStorage `netmap.theme`,
`:root[data-theme]`; `index.html` lo applica prima del primo disegno; la mappa passa il tema a React Flow
come `colorMode`; la stampa usa selettori con la stessa specificità per restare chiara).
Barra in alto: ricerca (300 px), pallini dello stato live con i soli numeri (verde → `?reachable=true`, rosso →
`?reachable=false`), menu utente a destra (iniziali + nome: ruolo e cosa può fare, tema, cambia password,
documentazione API, esci). Con il login spento il menu resta, con il solo tema. Palette ispirata ai rack: grigio-azzurro, etichette
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
- Scansione: un trunk Cisco senza VTP mostra solo le VLAN che lo switch conosce;
  rame o fibra non si ricava dall'ifType.
