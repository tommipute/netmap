# NetMap

Documentazione di rete in stile NetBox: device, porte, cavi, VLAN, subnet e mappe di rete
automatiche o disegnate a mano.

- **Fase 1** ✔ modello dati + API REST
- **Fase 2** ✔ interfaccia web: elenchi e moduli per tutto, scheda device con le porte, subnet con IP liberi, mappe,
  import/export CSV dei device
- **Fase 3** ✔ scansione SNMP (v2c e v3: interfacce, IP, seriale, vicini LLDP/CDP) con modifiche da approvare
- Fase 4: stato live sulla mappa e ricerca "dov'è collegato questo PC" (tabelle MAC e ARP), login

## Avvio

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
e il container `api` genera da solo la migration iniziale dai modelli
(la trovi poi in `backend/alembic/versions/`). Per seguire l'avvio: `docker compose logs -f`.

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

## Test del backend

```powershell
docker compose exec api pytest
```

Comprendono una scansione vera contro due switch simulati (snmpsim, già installato nell'immagine).

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
- Non c'è ancora login: per ora usala solo in rete interna.
