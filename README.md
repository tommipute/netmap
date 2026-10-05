# NetMap

Documentazione di rete in stile NetBox: device, porte, cavi, VLAN, subnet e mappe di rete
automatiche o disegnate a mano.

- **Fase 1** ✔ modello dati + API REST
- **Fase 2** ✔ interfaccia web: elenchi e moduli per tutto, scheda device con le porte, subnet con IP liberi, mappe
- Fase 3: discovery SNMP (LLDP/CDP, IF-MIB, ARP, tabelle MAC) con coda di modifiche da approvare
- Fase 4: stato live sulla mappa e ricerca "dov'è collegato questo PC"

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

## Test del backend

```powershell
docker compose exec api pip install -r requirements-dev.txt
docker compose exec api pytest
```

## Modifiche ai modelli

```powershell
docker compose exec api alembic revision --autogenerate -m "descrizione modifica"
docker compose exec api alembic upgrade head
```

## Struttura

```
backend/
  app/
    models/      tabelle (dcim.py infrastruttura, ipam.py indirizzamento, maps.py mappe)
    schemas/     validazione input/output
    api/         crud.py generatore endpoint, routes.py elenco entità, extra.py endpoint speciali
    services/    rules.py regole di coerenza, ipam.py, topology.py (porte, topologia, mappe, ricerca)
    seed.py      dati di esempio
  alembic/       migration
  tests/
frontend/
  src/
    resources.jsx   colonne e campi di ogni entità: per aggiungere un campo al modulo basta qui
    pages/          elenco generico, scheda device, subnet, ricerca, editor mappa
    components/     moduli, selettore porte, finestre
    map/            nodo device, disposizione automatica, colori dei cavi
```

## Limiti noti

- I menu a tendina caricano al massimo 1000 elementi per tipo (sedi, device, VLAN...).
- Non c'è ancora login: per ora usala solo in rete interna.
