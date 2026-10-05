# NetMap: istruzioni per Claude Code

Rispondi sempre in **italiano**: l'utente lavora nell'IT aziendale (Windows, Docker Desktop) e legge l'inglese
ma non lo scrive volentieri. Anche i testi dell'interfaccia sono in italiano.

## Cos'è

Documentazione di rete in stile NetBox, separata dall'app inventory dell'utente (stesso stack, progetti indipendenti).
Device, porte, cavi, VLAN, subnet/IP e **mappe di rete** automatiche o disegnate a mano.
Dati inseriti a mano oggi, da **scansione SNMP** nella fase 3.

| Fase | Contenuto | Stato |
|---|---|---|
| 1 | Modello dati + API REST | scritta, **mai eseguita** |
| 2 | Interfaccia web (elenchi, moduli, scheda device, subnet, mappe) | scritta, **mai eseguita** |
| 3 | Discovery SNMP con coda di modifiche da approvare | da fare, piano in `docs/roadmap.md` |
| 4 | Stato live in mappa, "dov'è collegato questo PC", login | da fare |

### ⚠️ Primo compito

Il codice è stato scritto in un ambiente senza rete: il Python è stato solo compilato (`py_compile`) e il frontend
solo impacchettato con esbuild (sintassi e import OK). **Nessun test, nessun avvio reale.**
Prima di aggiungere funzioni: avvia tutto, leggi i log, correggi gli errori, fai passare `pytest`,
prova l'interfaccia con i dati di esempio. Punti più a rischio in fondo a questo file.

## Avvio e comandi

```powershell
copy .env.example .env
docker compose up -d --build
docker compose logs -f api web
docker compose exec api python -m app.seed          # rete di esempio + mappa "Sede principale"
docker compose exec api pip install -r requirements-dev.txt
docker compose exec api pytest
docker compose exec api alembic revision --autogenerate -m "descrizione"
docker compose exec api alembic upgrade head
```

| Servizio | Indirizzo | Note |
|---|---|---|
| web (Vite + React) | http://localhost:5174 | proxy verso l'API per `/api`, `/docs`, `/openapi.json` |
| api (FastAPI) | http://localhost:8001/docs | reload automatico, codice montato da `./backend` |
| db (Postgres 16) | localhost:5433 | |

Porte scelte apposta per non scontrarsi con l'app inventory: **non cambiarle**.
`backend/start.sh` al primo avvio genera da solo la migration iniziale se `alembic/versions/` è vuota.
`.gitattributes` forza LF sugli `.sh` (su Windows un CRLF rompe lo script).

## Backend (`backend/app`)

Stack: Python 3.12, FastAPI, SQLAlchemy 2 (sincrono), Alembic, Pydantic 2, psycopg 3, Postgres.

- `models/`: `base.py` (Base con naming convention dei vincoli, mixin), `enums.py`, `dcim.py` (Site, Location,
  Rack, Manufacturer, DeviceType, DeviceRole, Device, Interface, Cable), `ipam.py` (VRF, VLAN, Prefix, IPAddress),
  `maps.py` (NetworkMap, MapNode).
- `schemas/`: input/output Pydantic. `views.py` contiene le risposte calcolate (porte, topologia, ricerca).
- `api/crud.py`: **generatore di endpoint CRUD**. `api/routes.py` registra ogni entità con una riga di config.
  `api/extra.py` contiene gli endpoint non-CRUD.
- `services/rules.py`: regole di coerenza come **hook** chiamati prima del salvataggio.
  `services/topology.py`: porte, topologia, mappe, ricerca. `services/ipam.py`: utilizzo e IP liberi.
- `core/net.py`: normalizzazione MAC/IP/prefissi e chiavi di ordinamento.

### Convenzioni da rispettare

- **Stati e tipi sono stringhe** nel DB (`String(20)`), validate da `StrEnum` in `models/enums.py`.
  Negli schemi input c'è `use_enum_values=True` + `validate_default=True` così al DB arrivano sempre `str`
  (psycopg 3 serializzerebbe gli Enum Python per nome). Nei default dei modelli usa `.value`.
- **Schemi**: `XBase` = campi modificabili, `XCreate(XBase)` = + campi fissi dopo la creazione
  (es. `site_id` di Location/Rack/Map, `device_id` di Interface), `XUpdate = make_partial(XBase)` per PATCH,
  `XRead(XCreate, [DiscoveryRead], ReadSchema)`. Gli input hanno `extra="forbid"`: un campo non previsto dà 422.
- Campi di input che non sono colonne (es. `tagged_vlan_ids`) vengono saltati da `apply_data` e gestiti dall'hook.
- **Ogni entità principale** ha `custom_fields` (JSON). Device, Interface, Cable, IPAddress hanno anche
  `source` (`manual`/`snmp`) e `last_seen_at`: servono alla fase 3, non toglierli.
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
- Per aggiungere un'entità: modello → import in `models/__init__.py` → schemi → riga in `api/routes.py`
  (+ hook se servono regole) → migration autogenerate → voce in `frontend/src/resources.jsx` → test.
- Test: `tests/` con SQLite in memoria e `PRAGMA foreign_keys=ON`. Aggiungi un test per ogni nuova regola.

### Endpoint non-CRUD

| Endpoint | Uso |
|---|---|
| `GET /api/devices/{id}/ports` | porte in ordine naturale con cavo, device/porta remota, VLAN, IP |
| `GET /api/devices/{id}/neighbors` | device collegati via cavo |
| `GET /api/prefixes/{id}/utilization` · `/ip-addresses` · `/available-ips?limit=` | IPAM |
| `GET /api/topology?site_id=&location_id=` | nodi + cavi di un ambito |
| `GET /api/maps/{id}/view` | device in mappa con posizioni salvate (o `null`), cavi, device aggiungibili |
| `PUT /api/maps/{id}/nodes` | sostituisce l'elenco `[{device_id, x, y}]` della mappa |
| `GET /api/search?q=` | device (nome, seriale, asset tag), MAC anche parziale/formato Cisco, IP, DNS |

Elenchi CRUD: `GET /api/<entità>?limit=&offset=&q=&<filtri>` → `{total, items}`; `limit` massimo 1000.

## Frontend (`frontend/src`)

Stack: Vite 5, React 18, react-router-dom 6, `@xyflow/react` 12 (React Flow). Nessun'altra libreria, CSS semplice.

- `resources.jsx`: **cuore dell'interfaccia**. Per ogni entità: `path`, titoli, `label(o)`, `detail(o)` opzionale,
  `filters`, `columns` (`type`: ref, badge, select, mono, bool, color, oppure `render`), `fields`
  (`type`: text, textarea, number, select, ref, refmulti, bool, color, interface, kv).
  Opzioni dei campi: `required`, `default`, `createOnly` (mostrato disabilitato in modifica e non inviato),
  `dependsOn` + `waitLabel` (es. posizione filtrata per sede, svuotata se cambia la sede), `params`,
  `showIf(values)` + `hiddenValue` (valore inviato quando il campo è nascosto), `freeOnly` (solo porte libere).
- `components/ResourceForm.jsx`: in creazione non invia i `null` (valgono i default del backend),
  in modifica li invia per svuotare i campi.
- `hooks.js`: `useApi(url)` con `reload`, `useOptions(path, params)` per i menu a tendina (cache condivisa),
  `invalidate()` da chiamare dopo **ogni** scrittura.
- `pages/`: `ResourcePage` (elenco generico, montato con `key` per entità), `DevicePage` (porte, aggiunta in blocco
  con `Gi1/0/[1-48]`, collega/scollega), `PrefixPage`, `SearchPage`, `MapEditor`.
- **Mappa** (`pages/MapEditor.jsx`, `map/`): posizione = quella corrente > quella salvata > calcolata.
  Se nessun device ha una posizione salvata parte la disposizione gerarchica (`map/layout.js`: una riga per
  `DeviceRole.level`, ordinamento per baricentro dei vicini, massimo 8 per riga). I device nuovi finiscono in fila sotto.
  Spostamenti → `dirty` → "Salva disposizione". Aggiungere/togliere un device (mappe manuali) salva subito.
  Collegamento trascinando tra due device → `CableDialog` per scegliere le porte.
  I cavi partono dal device di livello più alto; colore per tipo (`map/cables.js`), spessore per velocità ≥10G,
  tratteggio se pianificati. `deleteKeyCode={null}`: niente cancellazioni accidentali da tastiera.

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
- La scansione **non sovrascrive** i dati inseriti a mano: propone modifiche che l'utente approva (fase 3).
- Custom fields liberi su tutte le entità principali.

## Punti da verificare per primi (scritti senza poterli eseguire)

1. Migration autogenerate: che renderizzi bene `JSON().with_variant(JSONB, "postgresql")`, i `CheckConstraint`
   con nome e i default `sa.true()/false()`. Se l'import `postgresql` manca nel file generato, aggiungilo.
2. `api/crud.py`: filtri dell'elenco generati con `inspect.Signature` assegnata a `list_items.__signature__`.
   Controlla che compaiano in `/docs` e che filtrino davvero.
3. `schemas/common.py` → `make_partial`: ricostruisce `Annotated[...]` dai `metadata` per tenere le validazioni
   nei PATCH. Verifica un PATCH con MAC non valido (deve dare 422) e uno con un solo campo.
4. Caricamenti `joined` annidati (Cable → Interface → Device) negli elenchi e nella paginazione con `count`.
5. React Flow 12: `fitView` chiamato con `setTimeout` dopo il caricamento; colore dei nodi in MiniMap;
   collegamento tra due pallini con `ConnectionMode.Loose`.
6. `docker compose` su Windows: reload di uvicorn (`WATCHFILES_FORCE_POLLING`) e di Vite (`CHOKIDAR_USEPOLLING`).
7. Seed: carica 4 device, 3 cavi, 3 VLAN, 3 subnet, 1 mappa; la mappa deve aprirsi già disposta.

## Limiti noti

- I menu a tendina caricano al massimo 1000 elementi per tipo: con reti grandi servirà una select con ricerca lato server.
- Nessun login: da aggiungere prima di esporre l'app oltre la rete interna (vedi roadmap).
