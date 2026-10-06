# Roadmap NetMap

## Fase 3: discovery SNMP — fatta (5/10/2026)

Fatto: profili v2c/v3 con segreti cifrati, job con intervalli e pianificazione, worker, lettura di sistema,
IF-MIB, IP-MIB (anche IPv6), ENTITY-MIB, LLDP e CDP, abbinamento, regole di applicazione, pagina "Da approvare",
test con due switch simulati (snmpsim). Dettagli tecnici in `CLAUDE.md`, sezione "Scansione SNMP".

Differenze rispetto al piano qui sotto:
- **Niente Redis/ARQ**: la coda è la tabella `discovery_runs` (un worker che la legge con `SKIP LOCKED`).
  Meno servizi da gestire; se un giorno servissero più worker o code diverse si può passare ad ARQ.
- `discovery_jobs` non ha "regole di applicazione" generiche ma due interruttori: porte nuove e IP nuovi.
- Porte sparite: si propone l'eliminazione già alla prima scansione che non le vede (non dopo N scansioni);
  se la porta ricompare la proposta sparisce da sola.
- Non ancora letti: VLAN (Q-BRIDGE `dot1qVlanStaticName`, `dot1qPvid`), tabelle MAC e ARP. Le ultime due servono
  alla fase 4 ("dov'è collegato?").

Possibili miglioramenti: ruolo proposto in base al modello o al sysObjectID, abbinamento device ↔ modello esistente
senza sysObjectID (proporre di collegarli), fibra/rame dai transceiver (ENTITY-MIB), pulsante "Prova profilo" su un IP.

Il piano originale, per riferimento:

Obiettivo: trovare device, porte, IP e collegamenti con SNMP e proporli come **modifiche da approvare**,
senza mai sovrascrivere da soli i dati inseriti a mano.

### Infrastruttura

- Servizio `redis` + servizio `worker` in `docker-compose.yml` (stessa immagine del backend, comando diverso).
- Coda lavori: **ARQ** (asincrono, leggero) oppure Celery se serve di più. Le scansioni non girano mai dentro una richiesta HTTP.
- Libreria SNMP: `pysnmp` nella versione mantenuta da lextudio (7.x, API asyncio `pysnmp.hlapi.v3arch.asyncio`).
  L'API è cambiata tra le versioni: verifica sulla documentazione della versione installata.
- Concorrenza limitata (es. semaforo da 50 host), timeout brevi sul primo `get` per scartare subito chi non risponde.

### Nuove tabelle

- `snmp_profiles`: nome, versione (`v2c`/`v3`), community oppure utente v3 + protocolli auth/priv + chiavi, porta, timeout,
  tentativi. **Segreti cifrati** con Fernet (`cryptography`), chiave in `.env` (`SECRETS_KEY`).
  Nelle risposte API i segreti non tornano mai (campi solo scrittura).
- `discovery_jobs`: nome, intervalli da scansionare (CIDR o IP singoli), profili da provare in ordine, sede di default
  per i device nuovi, pianificazione (ogni N ore o manuale), attivo sì/no, regole di applicazione automatica.
- `discovery_runs`: job, inizio/fine, stato, contatori (host provati/risposto, modifiche proposte), log.
- `discovery_changes`: run, tipo oggetto (device/interface/ip/cable/vlan), azione (create/update/stale),
  id dell'oggetto esistente, dati proposti (JSON), differenze campo per campo (vecchio → nuovo),
  stato (`pending`, `approved`, `rejected`, `applied`), date.

### Cosa leggere

| Dato | MIB / oggetti |
|---|---|
| Identità | SNMPv2-MIB `sysName`, `sysDescr`, `sysObjectID` (→ `DeviceType.sys_object_id`), `sysLocation` |
| Seriale | ENTITY-MIB `entPhysicalSerialNum` della voce con `entPhysicalClass` = chassis (3) |
| Porte | IF-MIB `ifName`, `ifDescr`, `ifAlias`, `ifType`, `ifHighSpeed`, `ifPhysAddress`, `ifMtu`, `ifAdminStatus`, `ifOperStatus` |
| IP | IP-MIB `ipAddrTable` (IPv4: indirizzo, ifIndex, maschera) e `ipAddressTable` per IPv6 |
| Vicini LLDP | LLDP-MIB `lldpLocPortTable`, `lldpRemTable` (chassis id, port id e suo sottotipo, sysName, port desc), `lldpRemManAddrTable` |
| Vicini CDP | CISCO-CDP-MIB `cdpCacheDeviceId`, `cdpCacheDevicePort`, `cdpCacheAddress` |
| Tabella MAC | BRIDGE-MIB `dot1dBasePortIfIndex` + `dot1dTpFdbPort`; Q-BRIDGE-MIB `dot1qTpFdbPort` (per VLAN) |
| ARP | IP-MIB `ipNetToMediaPhysAddress` (MAC → IP, dai router/core) |
| VLAN | Q-BRIDGE-MIB `dot1qVlanStaticName`, `dot1qPvid` (VLAN untagged per porta); le egress bitmap più avanti |

### Abbinamento con i dati esistenti

- Device: numero di serie → `sys_name` (senza dominio, senza maiuscole) → IP già registrato su una sua porta.
- Modello: `sysObjectID` → `DeviceType.sys_object_id`; se manca, la modifica propone di crearlo.
- Porta: (device, `if_index`) → (device, nome).
- Cavo da LLDP/CDP: device remoto per chassis id (MAC), sysName o indirizzo di management; porta remota per
  `lldpRemPortId` confrontato con ifName/ifDescr/MAC secondo il sottotipo. Un cavo si propone solo se
  entrambe le porte sono note e libere; se esiste già un cavo diverso si propone la modifica, non la si applica.
- Oggetti non più visti: aggiorna solo `last_seen_at`; dopo N scansioni senza vederli propone "stale", non elimina.

### Regole di applicazione

- Sempre automatico: `last_seen_at`, `oper_status`, `if_index`, `sys_descr`.
- Automatico solo se attivato nel job: porte nuove su device già esistenti, IP nuovi su porte note.
- Sempre da approvare: device nuovi, cavi nuovi o diversi, qualunque campo di un oggetto con `source = manual`.
- Applicando una modifica, gli oggetti creati hanno `source = "snmp"`.

### Interfaccia

- Sezione "Scansioni": profili SNMP, job (con "Avvia ora"), storico esecuzioni con log.
- Pagina "Da approvare": elenco raggruppato per device, differenze vecchio → nuovo, approva/rifiuta singolo o in blocco,
  badge col numero di modifiche in attesa nella barra laterale.

### Test

- Le risposte SNMP vanno simulate (fixture con le tabelle già lette) per testare abbinamento e generazione delle modifiche
  senza apparati veri. Volendo, `snmpsim` per test d'integrazione.

## Fase 4 — fatta (6/10/2026)

Fatto: stato live (servizio `monitor`: ping + SNMP ifOperStatus, colori in mappa, rack, elenco e scheda device),
"Dov'è collegato?" (tabella `endpoints` da tabelle MAC/ARP, scartando gli uplink; ricerca per MAC, IP, DNS),
login con ruoli admin/editor/viewer, vista frontale dei rack, export della mappa in PNG/SVG e stampa,
menu con ricerca lato server oltre i 1000 elementi. Dettagli in `CLAUDE.md`, sezione "Fase 4".

Differenze rispetto al piano: niente libreria JWT (token firmato con `hmac` della libreria standard);
lo stato delle porte lo aggiorna il monitor, non solo la scansione.

## Da fare

NetMap lavora da solo: l'integrazione con l'app inventory è stata scartata (6/10/2026).


- HTTPS (reverse proxy) prima di esporre l'app fuori dalla rete interna.
- Avvisi quando un device smette di rispondere (mail o webhook).
