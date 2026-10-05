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
| 4 | Stato live in mappa, "dov'è collegato questo PC", login | da fare, piano in `docs/roadmap.md` |

Test: `docker compose exec api pytest` (27 test, compresi quelli con due switch SNMP simulati).

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
- **IP primario**: niente FK `devices.primary_ip_id` (creava un ciclo di FK). C'è `IPAddress.is_primary`;
  l'hook garantisce un solo primario per device togliendo il flag agli altri.
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
- `planner.py`: regole. **Silenziosi**: last_seen_at, oper_status, if_index, sys_name, sys_descr.
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
- Prova dal vivo: nel DB c'è la sede "Laboratorio SNMP (simulato)" con profilo, job e mappa di prova; i due switch
  simulati si avviano nel container worker (snmpsim su 127.0.0.1/.2:11161) e si fermano al riavvio del container.

## Frontend (`frontend/src`)

Stack: Vite 5, React 18, react-router-dom 6, `@xyflow/react` 12 (React Flow). Nessun'altra libreria, CSS semplice.

- `resources.jsx`: **cuore dell'interfaccia**. Per ogni entità: `path`, titoli, `label(o)`, `detail(o)` opzionale,
  `filters`, `columns` (`type`: ref, badge, select, mono, bool, color, oppure `render`), `fields`
  (`type`: text, textarea, lines, number, select, ref, refmulti, bool, color, interface, kv, secret).
  Opzioni dei campi: `required`, `default`, `createOnly` (mostrato disabilitato in modifica e non inviato),
  `dependsOn` + `waitLabel` (es. posizione filtrata per sede, svuotata se cambia la sede), `params`,
  `showIf(values)` + `hiddenValue` (valore inviato quando il campo è nascosto), `freeOnly` (solo porte libere),
  `ordered` (refmulti con numero d'ordine), `savedHint(item)` (segnaposto dei campi `secret` già salvati).
  `NAV` accetta chiavi di risorse oppure pagine speciali `{ to, title, badge }`.
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
  Se nessun device ha una posizione salvata parte la disposizione gerarchica (`map/layout.js`: una riga per
  `DeviceRole.level`, ordinamento per baricentro dei vicini, massimo 8 per riga). I device nuovi finiscono in fila sotto.
  Spostamenti → `dirty` → "Salva disposizione". Aggiungere/togliere un device (mappe manuali) salva subito.
  Collegamento trascinando tra due device → `CableDialog` per scegliere le porte.
  I cavi partono dal device di livello più alto; colore per tipo (`map/cables.js`), spessore per velocità ≥10G,
  tratteggio se pianificati. `deleteKeyCode={null}`: niente cancellazioni accidentali da tastiera.
  `fitView` parte quando `useNodesInitialized()` diventa vero (con un timer fisso non scattava a pagina nascosta).

### Stile

Token in `styles.css` (chiaro/scuro con `prefers-color-scheme`). Palette ispirata ai rack: grigio-azzurro, etichette
bianche, accento acqua come la fibra OM3 (`--accent`). Font IBM Plex Sans + IBM Plex Mono (solo per porte, IP, MAC).
Device in mappa = etichetta da rack con banda colorata del ruolo. Colori cavi da convenzione reale:
rame blu, fibra multimodale acqua, monomodale gialla, DAC grigio scuro.
Testi: italiano, sentence case, frasi semplici, pulsanti che dicono cosa fanno ("Salva disposizione", "Crea collegamento").

## Decisioni già prese con l'utente (non rimetterle in discussione senza chiedere)

- App **separata** dall'inventory, dedicata solo alla rete; in futuro le due app possono parlarsi via API
  (abbinamento device ↔ asset per numero di serie).
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

- I menu a tendina caricano al massimo 1000 elementi per tipo: con reti grandi servirà una select con ricerca lato server.
- Nessun login: da aggiungere prima di esporre l'app oltre la rete interna (vedi roadmap).
- Scansione: non legge ancora VLAN (Q-BRIDGE), tabelle MAC e ARP (servono alla fase 4); i device scoperti
  restano senza ruolo; rame o fibra non si ricava dall'ifType.
