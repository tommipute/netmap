# Roadmap NetMap

## Fase 3: discovery SNMP

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

## Fase 4

- **Stato live**: controllo periodico (ping ICMP e/o SNMP `ifOperStatus`), colonne `reachable` e `last_check` sui device,
  colori di stato in mappa e porte su/giù nella scheda device.
- **"Dov'è collegato?"**: tabella `endpoints` (MAC, IP da ARP, porta switch, VLAN, prima/ultima volta visto) dalla
  tabella MAC degli switch, scartando le porte di uplink (quelle con cavo verso altri switch).
  Ricerca per MAC/IP/nome che risponde "switch X, porta Y, piano Z".
- **Login e permessi**: autenticazione (JWT) e ruoli, prima di esporre l'app fuori dalla rete interna.
- **Esportazione mappa** in SVG/PNG e stampa.
- **Integrazione con l'app inventory**: abbinamento device ↔ asset per numero di serie via API.
- Select con ricerca lato server per superare il limite dei 1000 elementi nei menu.
- Vista frontale dei rack.
