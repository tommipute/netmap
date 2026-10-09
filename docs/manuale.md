# Manuale di NetMap

NetMap tiene la documentazione della rete: apparati (device) con le loro porte, cavi, VLAN, subnet e indirizzi IP,
rack e mappe. I dati si inseriscono a mano, si importano da Excel, da un CSV o da NetBox o arrivano dalla scansione SNMP, che propone le
modifiche e aspetta la tua approvazione. In più NetMap controlla ogni minuto chi risponde, trova su quale porta è
collegato un PC e ti avvisa quando un apparato non risponde.

Questo manuale è per chi usa NetMap. Installazione e aggiornamenti sul server sono nel [README](../README.md).
[English version](manual.md).

## Indice

1. [Primo accesso](#1-primo-accesso)
2. [Come è fatta l'interfaccia](#2-come-è-fatta-linterfaccia)
3. [Da dove cominciare](#3-da-dove-cominciare)
4. [Catalogo: ruoli, produttori, modelli](#4-catalogo-ruoli-produttori-modelli)
5. [Luoghi: sedi, posizioni, rack](#5-luoghi-sedi-posizioni-rack)
6. [Device e porte](#6-device-e-porte)
7. [Cavi](#7-cavi)
8. [Indirizzamento: subnet, IP, VLAN, VRF](#8-indirizzamento-subnet-ip-vlan-vrf)
9. [Import ed export](#9-import-ed-export)
10. [Mappe](#10-mappe)
11. [Vista del rack](#11-vista-del-rack)
12. [Scansione SNMP](#12-scansione-snmp)
13. [Dov'è collegato?](#13-dovè-collegato)
14. [Stato live e avvisi](#14-stato-live-e-avvisi)
15. [Cosa è cambiato e storico](#15-cosa-è-cambiato-e-storico)
16. [Utenti e Active Directory](#16-utenti-e-active-directory)
17. [Backup](#17-backup)
18. [Aggiornamenti e diagnostica](#18-aggiornamenti-e-diagnostica)
19. [Problemi frequenti](#19-problemi-frequenti)
20. [API e script](#20-api-e-script)

## 1. Primo accesso

Apri l'indirizzo di NetMap nel browser (per esempio `https://netmap.azienda.local`). La prima volta la pagina
chiede di creare l'**amministratore**: nome utente, nome, cognome e password (almeno 8 caratteri). Da quel momento
si entra con nome utente e password; la sessione dura 12 ore, poi si rientra.

Nella pagina di accesso e nel menu utente (in alto a destra) scegli:

- **Lingua**: italiano o inglese. Vale per il browser che stai usando.
- **Tema**: chiaro, scuro o automatico (segue il sistema operativo).

Dopo 5 password sbagliate di fila sullo stesso utente bisogna aspettare un minuto, e l'attesa raddoppia a ogni
errore successivo (fino a 15 minuti). È una protezione contro chi prova password a caso: aspetta e riprova.

## 2. Come è fatta l'interfaccia

- **Menu a sinistra**, diviso in sezioni: Rete, Luoghi, Indirizzamento, Catalogo, Scansione SNMP, Attività e (solo
  per gli amministratori) Amministrazione. Su telefono diventa una barra in alto che scorre di lato.
- **Ricerca in alto**: trova device per nome, numero di serie o asset tag, indirizzi IP, MAC address (anche solo
  una parte, anche nel formato Cisco `aabb.ccdd.eeff`) e nomi DNS.
- **Pallini dello stato live** accanto alla ricerca: quanti device rispondono (verde) e quanti no (rosso).
  Cliccandoli apri l'elenco dei device in quello stato.
- **Menu utente** a destra: il tuo ruolo, tema, lingua, cambio password, documentazione delle API, esci.
- In fondo a ogni pagina: la versione installata e il link al codice sorgente.

I **pulsanti con la sola icona** dicono cosa fanno quando ci passi sopra con il mouse (o tieni premuto su
telefono): matita = modifica, cestino = elimina, più = nuovo, e così via.

### Elenchi

Ogni voce del menu apre un elenco con:

- **ricerca** e **filtri** nella barra in alto; i filtri restano nell'indirizzo della pagina, quindi puoi salvare
  il link o mandarlo a un collega;
- **filtri sulle colonne** (pulsante a imbuto): una riga sotto le intestazioni per filtrare colonna per colonna;
  "(vuoto)" trova gli elementi senza quel dato;
- **ordinamento** cliccando l'intestazione di una colonna;
- **colonne** da mostrare, nascondere e riordinare (pulsante "Colonne della tabella"): la scelta resta salvata nel
  browser;
- **selezione multipla** con le caselle a sinistra: poi puoi eliminare o modificare in blocco i selezionati (per
  esempio spostare 20 device in un'altra posizione o cambiare il ruolo a tutti).

Device, porte, cavi e IP hanno nella colonna **Origine** un'icona che dice da dove arrivano: la persona = inseriti a
mano (anche con l'import da CSV o Excel), le onde = trovati dalla scansione SNMP, la spina (viola) = importati da un
altro programma, per esempio NetBox; il nome è nel tooltip. Con i filtri sulle colonne si vedono solo quelli di
un'origine. Nella scheda del device la stessa icona è accanto alle porte che non sono state inserite a mano.

### Moduli

Nei moduli i campi con l'asterisco sono obbligatori. I menu a tendina hanno in fondo la voce **"+ Nuovo …"**: crei
al volo una sede, un rack, un modello o un ruolo che manca, senza perdere quello che stavi scrivendo.
Quasi tutti gli oggetti hanno i **campi personalizzati**: coppie nome/valore libere (es. "Contratto" → "CN-2024-18").

### Stampa

Scheda device, rack e mappa hanno il pulsante **Stampa**: il foglio esce sempre chiaro, senza pulsanti, con data e
nome di chi ha stampato. Dalla finestra di stampa del browser puoi anche salvare in PDF.

## 3. Da dove cominciare

L'ordine che fa risparmiare più tempo:

1. **Catalogo**: i ruoli (switch, router, firewall, access point…) e, se vuoi, produttori e modelli.
2. **Luoghi**: la sede, poi edifici, piani e stanze, poi i rack.
3. **Profili SNMP e una scansione** della rete di management: NetMap trova da solo device, porte, IP, VLAN e i
   cavi tra gli apparati che parlano LLDP o CDP. Tu approvi.
4. Completa a mano quello che la scansione non vede: patch panel, apparati senza SNMP, cavi verso i server.
5. Crea una **mappa** per la sede.

Se hai già un elenco in Excel, puoi partire dall'[import](#device-da-csv-o-excel); se la rete è documentata in
NetBox, la porti in NetMap con l'[import da NetBox](#da-netbox).

## 4. Catalogo: ruoli, produttori, modelli

- **Ruoli**: cosa fa un device (Core, Distribuzione, Accesso, Firewall, Server…). Hanno un **colore** (la banda
  sull'etichetta del device in mappa) e un **livello in mappa**: 0 in alto, poi 1, 2… Nella disposizione
  automatica i firewall a livello 0 stanno sopra i core a livello 1, che stanno sopra gli switch di accesso a 2.
- **Produttori** e **Modelli**: un modello ha l'**altezza in unità** (serve alla vista del rack), il part number,
  il sysObjectID SNMP (la scansione riconosce così il modello) e un **ruolo predefinito**, che viene dato da solo
  ai device di quel modello senza ruolo.

## 5. Luoghi: sedi, posizioni, rack

- **Sedi**: un sito fisico con il suo indirizzo. Device, rack, VLAN e subnet appartengono a una sede.
- **Posizioni**: dentro una sede, ad albero, con quanti livelli vuoi: "Palazzina A" → "Piano 1" → "Sala CED".
  Si vedono con il percorso completo ("Palazzina A › Piano 1 › Sala CED"). Il campo **Piano (quota)** ordina le
  posizioni sorelle dall'alto in basso: nella mappa il piano 2 sta sopra il piano 1.
- **Rack**: con nome, sede, posizione e altezza in unità (42 di solito). Un device messo in un rack prende da solo
  la posizione del rack; spostando il rack in un'altra stanza i suoi device lo seguono.

## 6. Device e porte

Un **device** è un apparato con nome, stato (attivo, pianificato, offline, dismesso), sede, posizione, rack e
unità, ruolo, modello, numero di serie, asset tag e **IP di management**. Quest'ultimo è l'indirizzo con cui
NetMap lo controlla (ping e SNMP): scrivilo con la maschera (`10.0.99.11/24`). NetMap lo mette sulla porta di
management del device, o ne crea una ("mgmt") se manca.

### Scheda del device

Cliccando un device si apre la sua scheda:

- **Porte** (prima quelle di management, poi in ordine naturale: Gi1/0/2 prima di Gi1/0/10), con stato
  operativo, VLAN, IP, cavo e cosa c'è dall'altra parte. Ogni porta ha nome, tipo (rame, fibra, wireless,
  virtuale, LAG), velocità, modalità VLAN (access con una VLAN untagged, trunk con le VLAN tagged), MAC, MTU, LAG di
  cui fa parte, abilitata sì/no, solo management sì/no.
- **Aggiungi porte in blocco**: scrivi un intervallo tra parentesi quadre: `Gi1/0/[1-48]` crea 48 porte,
  `[1-52]` crea le porte da 1 a 52, `Te1/1/[1-4]` le quattro uplink.
- **Collega** (l'icona sulla riga di una porta libera): scegli il device e la porta dall'altra parte e il tipo di
  cavo.
- **Endpoint collegati**: i PC, telefoni e stampanti visti dietro quella porta (vedi [Dov'è collegato?](#13-dovè-collegato)).
- **Dati della scansione** (nei dati del device): ultima volta che la scansione l'ha visto, sysName e descrizione
  SNMP.
- **Stack**: se il device è uno stack di switch, qui ci sono i singoli switch (numero, modello, seriale, unità
  nel rack). Uno stack è **un solo device** con un IP e le porte Gi1/0/x, Gi2/0/x…; la scansione trova da sola i
  membri. Switch in cascata con IP propri restano device separati.
- **Storico**: tutte le modifiche al device, alle sue porte e ai suoi cavi, anche quelle della scansione.

Eliminando un device puoi scegliere se eliminare anche i suoi IP; porte e cavi vanno via con lui.

## 7. Cavi

Un cavo unisce due porte (lato A e lato B) e ha tipo (Cat5e, Cat6, Cat6a, fibra multimodale o monomodale, DAC),
stato (collegato, pianificato, da dismettere), etichetta, colore e lunghezza. Si crea dalla scheda del device
(**Collega**), dalla mappa (trascinando da un device all'altro) o dall'elenco **Cavi**. Una porta ha un solo cavo.
In mappa i colori seguono le convenzioni: rame blu, fibra multimodale acqua, monomodale gialla, DAC grigio scuro;
i pianificati sono tratteggiati.

## 8. Indirizzamento: subnet, IP, VLAN, VRF

- **Subnet**: `10.0.10.0/24` con stato, sede, VLAN e VRF. La pagina della subnet mostra l'**utilizzo** (quanti
  indirizzi sono usati), gli IP registrati e i **primi IP liberi**: cliccandone uno lo assegni.
- **Indirizzi IP**: sempre con la maschera (`10.0.10.25/24`), con stato (attivo, riservato, DHCP, deprecato),
  porta del device a cui appartiene, nome DNS, VRF. Un device ha un solo IP di management.
- **VLAN**: ID e nome, di una sede (o globali se senza sede). Le porte le usano come untagged (access) o tagged
  (trunk). La scansione le legge dagli switch.
- **VRF**: per le reti con tabelle di routing separate; IP e subnet uguali in VRF diverse non si scontrano.

## 9. Import ed export

### Device da CSV o Excel

Nell'elenco **Device**:

- **Esporta in CSV** (si apre con Excel) o **in JSON**: esporta i device con i filtri attivi.
- **Importa**: carica un file CSV o Excel (`.xlsx`) o incolla il testo. **Scarica modello CSV** ti dà un file
  d'esempio con le colonne giuste; le intestazioni possono essere in italiano o in inglese, e vanno bene anche
  quelle dell'export dei device di NetBox (Name, Site, Rack, Position, Type, Primary IPv4…). Sedi, posizioni (anche
  con il percorso "Palazzina A > Piano 1"), rack, produttori, modelli e ruoli che mancano vengono creati.
- Di un file **Excel** si legge il primo foglio che ha la colonna del nome (Nome, Name, Hostname…): le righe vuote
  sopra le intestazioni non danno fastidio, le date diventano `2026-01-31`. Il contenuto finisce nel riquadro di
  testo, dove lo controlli prima di importare. Un vecchio `.xls` va salvato da Excel come `.xlsx` o come CSV.
- **Simulazione**: mostra cosa succederebbe senza scrivere niente. Le righe sbagliate vengono elencate con il
  motivo; le altre vengono importate. Con **Aggiorna i device se già esistenti** un device con lo stesso nome
  nella stessa sede viene aggiornato (solo con le celle compilate), non duplicato.

### Da NetBox

Solo per gli amministratori: **Amministrazione → Import da NetBox**. Copia in NetMap quello che c'è in NetBox
(versione 3.3 o successiva): sedi, posizioni, rack, produttori, ruoli, modelli, VRF, VLAN, subnet, device con porte
e stack, cavi e indirizzi IP.

1. Scrivi l'indirizzo di NetBox (quello che apri nel browser) e un **token API**: basta in sola lettura (in NetBox
   lo crei dal tuo profilo, Token API). NetMap non lo tiene: il worker lo cancella a fine import.
2. **Prova la connessione**: NetMap mostra la versione di NetBox, quanti oggetti ci sono e l'elenco delle sedi.
3. Scegli **Tutte le sedi** o **Solo le sedi scelte**. Gli oggetti che non hanno una sede (VRF, VLAN e subnet
   globali) arrivano sempre; con le sedi scelte arrivano gli IP delle loro porte e quelli liberi dentro le loro subnet.
4. **Simula l'import**: fa tutto il lavoro e alla fine torna indietro, così vedi quanti oggetti verrebbero creati e
   quali problemi ci sono senza cambiare niente. Se i numeri ti convincono, **Importa**.

L'import lo fa il worker, in sottofondo: la pagina mostra il log man mano e alla fine una tabella con gli oggetti
creati, quelli che c'erano già e quelli che non sono passati, con il motivo. Puoi chiudere la pagina: gli ultimi
import restano in **Import precedenti**.

- **Crea solo quello che manca**. Un oggetto che c'è già in NetMap (sede con lo stesso nome, device con lo stesso
  nome nella stessa sede, VLAN con lo stesso numero nella sede, IP con lo stesso indirizzo…) resta com'è, anche se
  in NetBox è diverso. Puoi rilanciare l'import quando vuoi: non crea doppioni.
- Le porte arrivano solo sui device creati dall'import; quelle di un device che c'era già restano come sono, e i
  cavi verso porte che in NetMap non ci sono vengono saltati.
- Uno **stack** di NetBox (virtual chassis) diventa un device solo, con il nome dello stack e i suoi membri, come
  nella scansione SNMP.
- Un cavo che passa da un **patch panel** diventa un cavo diretto tra le due porte, con il patch panel nelle note.
  I cavi verso circuiti, prese elettriche e console non vengono importati: il log dice quanti sono.
- Passano anche stato, seriale, asset tag, campi personalizzati, modo delle porte (access o trunk) con le VLAN,
  MAC, velocità, LAG, colore e lunghezza dei cavi e l'IP di management (il primary IP di NetBox). Un oggetto che
  non supera i controlli di NetMap finisce tra i problemi, gli altri vanno avanti.
- Nello **Storico modifiche** l'import compare con l'origine "Import da NetBox" e il nome di chi l'ha avviato; una
  simulazione non lascia traccia.

## 10. Mappe

Una mappa mostra i device con i cavi tra di loro. Si crea in **Mappe** scegliendo sede ed eventualmente una
posizione (solo quell'edificio o quel piano):

- **Mostra sempre tutti i device** acceso: la mappa contiene da sola tutti i device della sede o della
  posizione, anche quelli aggiunti dopo.
- Spento: scegli tu quali device mettere (**Aggiungi device…**), utile per una mappa del solo core o della sola
  sala server.

### Disposizione

La prima volta i device vengono disposti in automatico: in alto i ruoli con il livello più basso (firewall,
core), sotto gli altri; i device dello stesso rack stanno insieme dentro una **bolla del rack**. Con
**Posizioni** acceso, edifici, piani e stanze diventano riquadri colorati uno dentro l'altro.

Trascina i device dove vuoi e premi **Salva disposizione**. **Disponi automaticamente** ricalcola tutto da capo.
Cliccando il nome di un rack o di una posizione selezioni tutti i suoi device, per spostarli insieme.

### Cavi in mappa

- Per **creare un cavo**, passa sopra un device: compaiono quattro pallini. Trascina da uno di questi a un altro
  device e scegli le porte.
- I cavi girano ad angolo retto e non passano mai sotto un device. **Nomi delle porte** scrive il nome della
  porta dove il cavo entra nel device.
- Per **sistemare un cavo a mano** cliccalo: le barrette sui tratti si trascinano di traverso, i pallini alle
  estremità scorrono sul bordo del device. Poi **Salva disposizione**. **Torna al percorso automatico** annulla.
- Cliccando un cavo vedi i dettagli (porte, tipo, VLAN) e puoi eliminarlo; cliccando un device vedi i dettagli e
  apri la scheda.

### Altre funzioni

- **Cerca nella mappa**: nome o IP di un device, oppure il MAC o l'IP di un PC: NetMap seleziona la porta dello
  switch dove è collegato.
- **Evidenzia una VLAN**: mette in risalto i cavi e i device che portano quella VLAN.
- **Stato live**: il pallino sul device è verde se risponde, rosso se no; la mappa si aggiorna ogni 30 secondi.
- **Esporta**: immagine PNG, disegno SVG, oppure stampa / PDF.

## 11. Vista del rack

Dalla pagina di un rack vedi il fronte con le unità occupate. Con il pulsante più o cliccando un'unità libera
aggiungi un device della sede in quell'unità (NetMap controlla che ci stia, usando l'altezza del modello; se la
sede ha più di 1000 device sopra il menu compare un campo per cercarlo). I device si
**trascinano** su un'altra unità (verde = ci sta, rosso = occupato) o in "Nel rack senza unità"; la X li toglie
dal rack. Gli stack mostrano ogni membro nella sua unità.

## 12. Scansione SNMP

La scansione legge gli apparati con SNMP (v1, v2c o v3): nome, modello, numero di serie, porte, IP, VLAN, membri dello
stack e vicini LLDP/CDP (cioè i cavi tra gli apparati). **Non cambia niente da sola** sui dati inseriti a mano:
propone modifiche che approvi tu.

### Preparazione

1. **Profili SNMP**: le credenziali. Per v1 e v2c la community, per v3 utente, protocollo e chiave di
   autenticazione, protocollo e chiave di cifratura. La v1 serve solo per apparati vecchi che non conoscono la v2c:
   è più lenta e non legge i contatori a 64 bit. Vengono salvate cifrate e non si rileggono: in modifica,
   lascia vuoto il campo per non cambiarle.
2. Sugli apparati: SNMP attivo in sola lettura, e l'indirizzo del server NetMap ammesso nelle ACL. Serve la
   porta UDP 161 aperta dal server NetMap verso gli apparati.

### Scansioni

In **Scansioni** crea una scansione con:

- gli **indirizzi**: una rete `10.0.99.0/24`, un intervallo `10.0.99.1-10.0.99.40` o `10.0.99.1-40`, un singolo
  IP. Dopo ognuno Invio, virgola o spazio lo trasformano in una bolla (si toglie con la ×); si può anche incollare
  un elenco. Le bolle rosse non sono valide; sotto c'è il conteggio degli indirizzi (al massimo 4096);
- i **profili** da provare, in ordine (vince il primo che risponde);
- la **sede dei device nuovi**;
- **Ripeti ogni (ore)**: vuoto = solo quando la avvii tu;
- due interruttori per far aggiungere senza chiedere le **porte nuove** e gli **IP nuovi** dei device già
  censiti.

Apri la scansione e premi **Avvia scansione**: in pochi secondi (qualche minuto per reti grandi) trovi
l'esito e il log nello storico delle esecuzioni.

### Da approvare

La voce **Da approvare** (con il numero accanto) raccoglie quello che la scansione ha trovato, raggruppato per
device: device nuovi con porte e IP, porte e IP nuovi, dati cambiati, cavi visti con LLDP/CDP, VLAN, membri dello
stack, porte sparite. Puoi approvare o rifiutare una modifica alla volta, tutte quelle di un device o tutte.

- Sempre da approvare: device nuovi, cavi, porte sparite, modifiche a dati che hai inserito tu.
- Senza chiedere: lo stato delle porte, l'ultima volta che un device è stato visto e i dati di oggetti creati
  dalla scansione stessa.
- Una modifica rifiutata non viene riproposta finché i dati restano uguali.
- Il nome di un device non viene mai cambiato dalla scansione.

Il trucco per i cavi: approva prima i device nuovi, poi rilancia la scansione. I cavi si vedono solo quando
entrambi gli apparati sono già in NetMap.

## 13. Dov'è collegato?

Dopo ogni scansione NetMap unisce le tabelle MAC degli switch con le tabelle ARP di router e core. In **Dov'è
collegato?** cerchi un PC per MAC, IP o nome DNS e trovi switch, porta, VLAN, sede e stanza. Le porte di uplink
(quelle con un cavo verso un altro switch) vengono scartate, così il risultato è la porta di accesso vera.
Se un PC cambia porta, NetMap si ricorda la porta precedente e quando si è spostato.

## 14. Stato live e avvisi

Ogni minuto NetMap controlla i device **attivi con un IP di management**: uno risponde se risponde al ping o
all'SNMP. Lo stato si vede nei pallini in alto, nell'elenco dei device (colonna e filtro "Stato live"), nella
scheda e in mappa. Nella scheda, **Controlla ora** rifà il controllo subito.

**Avvisi** (Amministrazione → Avvisi) manda un messaggio quando un device non risponde da un certo numero di
minuti, e (se vuoi) quando torna a rispondere. Canali:

- **Email**: server SMTP (STARTTLS 587, SSL 465 o nessuna sicurezza sulla 25), utente, password, mittente,
  destinatari;
- **Webhook**: Teams (con i Workflows, formato "scheda adattiva"), Slack, Mattermost, Google Chat (formato testo);
- **Telegram**: token del bot e chat.

Il **ritardo** evita un avviso per un ping perso; la **lingua** dei messaggi si sceglie per canale. Il pulsante
**Prova** manda un messaggio di prova. Se l'invio fallisce, l'errore resta visibile nell'elenco e NetMap riprova
al giro dopo.

## 15. Cosa è cambiato e storico

- **Cosa è cambiato**: un riepilogo del periodo che scegli (ultime 24 ore, 7 giorni o 30 giorni): modifiche per origine,
  device creati ed eliminati, device che non rispondono e tornati a rispondere, apparecchi nuovi in rete o
  spostati di porta, scansioni (e quelle fallite), modifiche da approvare. Ogni riquadro porta al dettaglio.
- **Storico modifiche**: ogni creazione, modifica ed eliminazione, con chi l'ha fatta (un utente, la scansione,
  un import, Active Directory), quando e cosa è cambiato, campo per campo. Si filtra per tipo di oggetto, origine,
  data e testo. Le password non compaiono mai: solo "cambiata".

## 16. Utenti e Active Directory

Gli **utenti** (Amministrazione → Utenti) hanno un ruolo:

| Ruolo | Cosa può fare |
|---|---|
| Solo lettura | consulta tutto, senza modificare |
| Modifica | modifica i dati e approva le modifiche della scansione |
| Amministratore | tutto, compresi utenti, avvisi, Active Directory, aggiornamenti e backup |

Disattivare un utente chiude subito le sue sessioni, come cambiargli la password. Ognuno può cambiare la propria
password dal menu utente.

### Active Directory

Con Active Directory gli utenti entrano con il nome e la password di Windows (`mario.rossi`,
`AZIENDA\mario.rossi` o `mario.rossi@azienda.local`) e il ruolo viene dai loro gruppi. In **Amministrazione →
Active Directory**:

1. **Dominio** (`azienda.local`) e **domain controller**, con il nome completo che c'è nel loro certificato
   (`dc1.azienda.local`); più domain controller separati da virgola, si usa il primo che risponde.
2. **Sicurezza**: LDAPS (porta 636) o StartTLS (porta 389). Il domain controller deve avere un certificato
   (di solito dai Servizi certificati di Active Directory). Per la verifica incolla o carica il **certificato
   della CA del dominio** (esportato da Windows in formato Base64).
3. **Base di ricerca** (facoltativa): limita l'accesso agli utenti di una OU.
4. **Ruoli dai gruppi**: il gruppo degli amministratori, quello di chi modifica e quello di chi legge. Valgono anche
   i gruppi dentro i gruppi; chi è in più gruppi prende il ruolo più alto. Chi non è in nessun gruppo non entra,
   a meno di scegliere un ruolo per tutti gli altri utenti del dominio.
5. Salva e attiva. **Prova (facoltativa)**, in fondo alla pagina e chiusa finché non la apri: con la password di
   un utente vero (per esempio la tua) vedi se la connessione funziona, che ruolo avrebbe e in quali gruppi l'ha
   trovato, prima di salvare. Senza, salva e prova ad accedere con un utente del dominio.

Non serve un account di servizio: NetMap si collega con le credenziali di chi sta entrando. L'utente NetMap viene
creato al primo accesso e a ogni accesso prende dal dominio il ruolo, il nome e il cognome (i campi Nome e Cognome
dell'utente in Active Directory, oppure il nome visualizzato); per questo password, ruolo, nome e cognome di un
utente di dominio non si cambiano in NetMap (lo si può disattivare). Un utente tolto da tutti i gruppi viene
respinto al tentativo successivo e le sue sessioni si chiudono.

**Tieni sempre un amministratore locale**: gli utenti locali entrano con la loro password anche quando il dominio
non risponde. Se un utente locale e uno del dominio hanno lo stesso nome, vince quello locale.

## 17. Backup

In **Amministrazione → Backup**:

- **Backup ogni notte** all'ora che scegli, tenuti per i giorni che scegli (14 se non cambi niente). Se il server
  era spento a quell'ora, il backup parte appena si riaccende.
- **Backup ora**: un backup subito, per esempio prima di un import grosso.
- Prima di ogni aggiornamento c'è sempre un backup (quanti tenerne si sceglie nella pagina Aggiornamenti).
- **Scarica** un backup sul PC; **Carica un backup** dal PC (anche fatto su un altro server).
- **Ripristina questo backup**: riporta il database a quel momento. Prima NetMap fa un backup di sicurezza dello
  stato attuale; se dopo il ripristino non riparte, torna da solo allo stato di prima. Per qualche minuto NetMap
  non risponde. Un backup fatto da una versione più nuova di quella installata viene rifiutato: aggiorna prima.

### Copie fuori dal server

Un backup che sta solo sul server si perde insieme al server. In **Copie fuori dal server** aggiungi una
**destinazione**:

- **Cartella di rete (SMB)**: un NAS o una condivisione Windows: server, condivisione, cartella, utente (anche
  `DOMINIO\utente`) e password;
- **SFTP**: server, porta, cartella, utente e password o chiave privata. La prima volta NetMap si ricorda la
  chiave del server; se cambia (server reinstallato) la copia si ferma finché non la accetti di nuovo.

**Prova la connessione** prima di salvare. Ogni backup nuovo viene copiato entro un minuto; le copie più vecchie
dei giorni scelti vengono cancellate dalla destinazione. **Backup sulla destinazione** mostra cosa c'è dall'altra
parte e **Riporta sul server** recupera un backup da lì.

### Chiave dei segreti

Password SMTP, community SNMP, password delle destinazioni e simili sono cifrate nel database con una chiave che
sta sul server, **non nel backup**. Scarica la chiave (**Scarica la chiave**) e tienila al sicuro, oppure attiva
**Copia anche la chiave dei segreti** su una destinazione.

**Server nuovo dopo un guasto**: installa NetMap, carica il backup (o aggiungi la destinazione e riportalo da lì),
ripristinalo ed entra con gli utenti di prima. La sezione Chiave dei segreti dice quante password non si
leggono: incolla la chiave del vecchio server (**Usa la chiave del vecchio server**) e tornano leggibili.

## 18. Aggiornamenti e diagnostica

NetMap si aggiorna con uno script che gira sul server, fuori dall'app. In **Amministrazione → Aggiornamenti** vedi
la versione installata e quella disponibile, l'ultimo controllo e lo storico:

- **Controlla ora** e **Aggiorna ora**. Un aggiornamento fa il backup del database, installa la versione nuova e
  aspetta che riparta; se non riparte, torna da solo alla versione di prima (con il database di prima).
- **Aggiornamento automatico**: installa da solo le versioni nuove appena le trova.
- **Canale**: stabile (consigliato: solo le versioni definitive, 1.0.0, 1.0.1, 1.1.0…), beta (anche le versioni di
  prova, es. 1.1.0-rc.1) o, solo se NetMap è installato dal codice con git, sviluppo (ogni modifica appena è su
  GitHub, anche non provata: per un server di prova). Non si torna mai a una versione più vecchia.
- **Log**: cosa ha fatto lo script nell'ultimo aggiornamento.

### Diagnostica

Per segnalare un problema: **Raccogli i log dei container** (lo script li raccoglie entro un minuto), poi
**Scarica il pacchetto diagnostico**. È uno zip con versione, configurazione senza password né chiavi, stato del
database e log. I log possono contenere indirizzi IP, nomi dei device e nomi utente della tua rete: dacci
un'occhiata prima di mandarlo a qualcuno.

## 19. Problemi frequenti

**Il browser dice che il certificato non è valido.** L'installazione standard usa una CA interna. Installa il
certificato della CA nei PC (le istruzioni sono nel README, sezione "Certificato"), oppure usa un certificato
vostro.

**Ho perso la password dell'amministratore.** Sul server, nella cartella di NetMap:
`docker compose exec -it api python -m app.users password admin` (al posto di `admin` il tuo nome utente).

**La scansione non trova niente.** Il log dell'esecuzione dice quanti host hanno risposto. Un apparato che non
risponde ha di solito la community o le credenziali v3 diverse dal profilo, un'ACL SNMP che non ammette il server
NetMap, oppure la porta UDP 161 chiusa da un firewall. Prova da un PC con un client SNMP usando gli stessi dati.

**La scansione non trova i cavi.** Servono LLDP o CDP attivi su entrambi gli apparati, ed entrambi devono essere
già in NetMap: approva i device nuovi e rilancia la scansione.

**Un device è rosso ma funziona.** Il controllo usa l'IP di management: verifica che sia giusto e che il server
NetMap possa fare ping o SNMP verso di lui. Un device senza IP di management non viene controllato.

**Dov'è collegato? non trova un PC.** Il PC deve aver comunicato da poco (le tabelle MAC degli switch si svuotano
dopo qualche minuto di silenzio) e la scansione deve aver letto sia lo switch di accesso sia il router o il core
che ha la tabella ARP.

**Active Directory: "nessun domain controller risponde".** Il server NetMap deve risolvere il nome del domain
controller e raggiungere la porta 636 (o 389). "Certificato intestato a un altro nome": scrivi il domain
controller con il nome completo del certificato. "Non firmato da una CA conosciuta": incolla il certificato della
CA del dominio.

**La pagina Aggiornamenti dice che lo script tace.** Sul server: `systemctl status netmap-updater.timer` e
`journalctl -u netmap-updater`.

## 20. API e script

Tutto quello che fa l'interfaccia passa da un'API REST, documentata in **Documentazione API** nel menu utente
(`/docs`). Per usarla da uno script fai login con `POST /api/auth/login` e usa il token che ricevi con
l'intestazione `Authorization: Bearer <token>`; i permessi sono quelli del ruolo dell'utente. Gli elenchi
accettano `limit`, `offset`, `q`, i filtri e `sort` (es. `GET /api/devices?site_id=1&sort=-name`).
