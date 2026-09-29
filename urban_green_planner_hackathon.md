# Hackathon Bari – Progetto Forestazione Urbana

## 1. Contesto

Hackathon di Bari del 1° ottobre 2026.

Obiettivo: realizzare con il team un software/app/dashboard che utilizzi gli open data disponibili per produrre un servizio utile alla Regione Puglia, ai Comuni, ai cittadini e ad altri soggetti del territorio.

L'idea proposta è creare un sistema di supporto alla pianificazione del verde urbano, capace di individuare **quali zone dei centri abitati hanno maggiore priorità per nuovi alberi e piante**.

L'idea iniziale era calcolare dove e in quale quantità piantare alberi per "risanare l'ossigeno". È però più corretto, dal punto di vista scientifico, presentare il progetto come uno strumento per:

- mitigare l'inquinamento atmosferico;
- aumentare il verde urbano;
- ridurre l'esposizione della popolazione a condizioni ambientali sfavorevoli;
- contrastare gli effetti dell'urbanizzazione e dell'impermeabilizzazione del suolo;
- supportare la pianificazione delle nuove piantumazioni.

---

# 2. Idea del progetto

Il sistema combina più fonti di dati geospaziali e ambientali e produce una **mappa delle zone prioritarie per la forestazione urbana**.

La logica generale è:

**Open Data → analisi GIS → normalizzazione → indice di priorità → stima delle piantumazioni → dashboard**

Per l'MVP si è individuata **Bari** come caso di studio particolarmente adatto, perché dispone di diversi dataset complementari:

- aree verdi;
- traffico;
- centraline semaforiche;
- qualità dell'aria;
- centraline ARPA;
- popolazione;
- dati sugli impianti industriali.

---

# 3. Concetto fondamentale: Indice di Priorità di Forestazione (IPF)

L'idea è dividere la città in una griglia geografica, ad esempio celle da 250×250 m o 500×500 m.

Per ogni cella vengono calcolati diversi indicatori:

- quantità di verde presente;
- traffico;
- qualità dell'aria;
- popolazione;
- presenza/pressione industriale;
- eventualmente consumo del suolo;
- eventualmente temperatura/stress termico;
- eventualmente vegetazione rilevata da satellite.

Gli indicatori vengono normalizzati, ad esempio, su una scala 0–100.

Un possibile esempio di formula:

```text
IPF =
  30% × Inquinamento
+ 25% × Carenza di verde
+ 20% × Traffico
+ 15% × Popolazione esposta
+ 10% × Pressione industriale
```

I pesi sono solo un esempio iniziale e dovranno essere definiti/giustificati durante lo sviluppo.

Il risultato potrebbe essere:

```text
Zona A → 87/100 → priorità alta
Zona B → 64/100 → priorità media
Zona C → 25/100 → priorità bassa
```

La dashboard dovrebbe spiegare anche **perché** una zona ha ricevuto quel punteggio, evitando una "scatola nera".

Esempio:

```text
Zona Libertà

Inquinamento       91/100
Traffico           83/100
Carenza verde      89/100
Popolazione        71/100
Industria          63/100

IPF                87/100
```

---

# 4. Dataset Open Data Puglia principali

## 4.1 Aree verdi – Comune di Bari

Dataset:
https://dati.puglia.it/ckan/dataset/aree-verdi

Funzione:

- individuare il verde urbano esistente;
- calcolare la superficie verde per cella;
- stimare la percentuale di copertura verde;
- individuare zone con carenza di verde.

È uno dei dataset principali dell'MVP.

Disponibilità indicata:

- CSV;
- ZIP/cartografia;
- dati georeferenziati in WGS84.

---

## 4.2 Flussi di traffico giornalieri – Comune di Bari

Dataset:
https://dati.puglia.it/v2/dataset/centraline-semaforiche-flussi-di-traffico-giornalieri

Funzione:

- misurare la pressione del traffico;
- calcolare il numero medio di veicoli/giorno;
- associare il traffico alle celle della griglia.

Sono disponibili dati giornalieri per i sensori e il dataset viene aggiornato mensilmente.

Esempi di campi citati:

```text
device_db
device_type
device_id
detector_id
2026-02-01
2026-02-02
2026-02-03
...
```

Il traffico può diventare uno degli input principali dell'IPF.

---

## 4.3 Posizionamento centraline semaforiche – Comune di Bari

Dataset:
https://dati.puglia.it/ckan/dataset/centraline-semaforiche-posizionamento-e-sensoristica-a-bordo

Funzione:

- associare ogni sensore di traffico alla sua posizione geografica;
- collegare il volume di traffico alla cella GIS corrispondente.

Schema:

```text
sensore
  ↓
coordinate
  ↓
traffico rilevato
  ↓
cella geografica
```

Formato indicato: JSON.

---

## 4.4 Qualità dell'aria – ARPA Puglia

Dataset:
https://dati.puglia.it/v2/dataset/dati-qualita-aria

Funzione:

- utilizzare i dati delle stazioni della Rete Regionale di Monitoraggio della Qualità dell'Aria;
- misurare la criticità relativa agli inquinanti;
- alimentare la componente "inquinamento" dell'IPF.

Caratteristiche indicate:

- aggiornamento quotidiano;
- CSV;
- GeoJSON;
- API pubbliche;
- API senza necessità di API key.

Nota: i dati giornalieri hanno superato la validazione giornaliera e possono essere successivamente revisionati. La dashboard dovrebbe quindi indicare che i dati sono soggetti a validazione/revisione.

---

## 4.5 Stazioni di monitoraggio qualità dell'aria – ARPA Puglia

Dataset:
https://dati.puglia.it/ckan/dataset/stazioni-qualita-aria

Funzione:

- ottenere la posizione geografica delle centraline ARPA;
- associare i dati sulla qualità dell'aria alle coordinate;
- trasferire i dati delle centraline sulla griglia GIS.

Campi citati:

```text
id_station
denominazione
comune
provincia
indirizzo
rete
interesse_rete
coordinates
```

Le coordinate comprendono latitudine e longitudine.

---

## 4.6 Popolazione residente – Comune di Bari

Dataset:
https://dati.puglia.it/ckan/dataset/popolazione-residente1

Funzione:

- stimare quante persone vivono in ogni zona;
- stimare la popolazione potenzialmente esposta;
- introdurre una componente sociale nell'indice.

Il dataset contiene dati per civico e fasce di età, con riferimento al 6 gennaio 2024.

Fasce citate:

- Under 14;
- Under 18;
- Under 67;
- Over 67.

Schema concettuale:

```text
popolazione
+
inquinamento
+
traffico
=
potenziale popolazione esposta
```

---

## 4.7 Impianti AIA – Regione Puglia

Dataset:
https://dati.puglia.it/ckan/dataset/aia

AIA = Autorizzazione Integrata Ambientale.

Funzione:

- individuare impianti soggetti ad autorizzazione ambientale;
- introdurre una componente di pressione industriale;
- individuare aree vicine a impianti potenzialmente rilevanti dal punto di vista ambientale.

È disponibile in CSV.

Importante: prima di inserirlo definitivamente nell'algoritmo bisogna controllare le colonne effettive e verificare la presenza di coordinate geografiche utilizzabili.

Non bisogna interpretare automaticamente la presenza di un impianto come causa dell'inquinamento di una determinata zona.

---

# 5. Dataset Puglia utili come supporto

## 5.1 Censimento arboreo – Comune di Copertino

Dataset:
https://dati.puglia.it/ckan/dataset/censimento-arboreo-comune-di-copertino1

Contiene, tra gli altri:

```text
codice
latitudine
longitudine
indirizzo
specie
nome comune
```

Coordinate in WGS84 EPSG:4326.

È molto utile tecnicamente, ma è relativo a **Copertino**, non Bari.

Può essere utilizzato in una seconda fase per dimostrare che il sistema è trasferibile ad altri comuni pugliesi.

---

## 5.2 Piantumazioni realizzate e programmate – Comune di Lecce

Dataset:
https://dati.puglia.it/ckan/dataset/piantumazioni-realizzate-e-programmate-di-alberi-nel-comune-di-lecce

Contiene piantumazioni realizzate e programmate nel Comune di Lecce dal 2019 in poi.

Utilità:

- possibile dataset di validazione;
- confronto tra priorità stimate e interventi effettivamente realizzati;
- dimostrazione della trasferibilità del progetto ad altri comuni.

---

## 5.3 Consumo del suolo dal 2006

Dataset:
https://dati.puglia.it/ckan/dataset/consumo-del-suolo-a-partire-dal-2006

Fonte indicata: ISPRA/IPRES.

Contiene dati comunali dal 2006 al 2024, espressi in ettari e percentuale.

Utilità:

- misurare urbanizzazione e impermeabilizzazione;
- introdurre un parametro di pressione urbana.

Limite:

- ha una granularità geografica inferiore rispetto a dati puntuali come alberi, traffico e centraline.

---

## 5.4 Uso del Suolo 2011 – UDS

Dataset:
https://dati.puglia.it/ckan/dataset/uso-del-suolo-2011-uds

Dataset cartografico SHP.

Distingue categorie come:

- superfici artificiali;
- superfici agricole;
- superfici boscate;
- ambienti naturali;
- zone umide;
- acque.

Utilizza una classificazione CORINE Land Cover con 69 classi.

Utilità:

- analisi GIS;
- capire dove esistono superfici artificiali/naturali;
- supportare l'identificazione delle aree di intervento.

---

## 5.5 Parchi, aree naturali protette e siti di interesse

Dataset:
https://dati.puglia.it/ckan/dataset/parchi-aree-naturali-protette-siti-di-importanza-rilevante

Contiene informazioni su:

- parchi nazionali;
- aree marine protette;
- riserve naturali;
- parchi regionali;
- SIC;
- ZPS;
- IBA;
- zone umide RAMSAR.

Utilità:

- distinguere verde urbano da aree naturali/protette;
- introdurre eventuali vincoli territoriali;
- evitare di suggerire automaticamente interventi in aree già naturali o protette.

---

## 5.6 Parchi e aree a verde – Comune di Lecce

Dataset:
https://dati.puglia.it/ckan/dataset/parchi-e-aree-a-verde

Elenco di parchi e aree verdi di Lecce.

Può essere utilizzato per una futura estensione del progetto ad altri comuni.

---

## 5.7 Popolazione pugliese dal 2002

Dataset:
https://dati.puglia.it/ckan/dataset/popolazione-pugliese-a-partire-dal-2002

Contiene popolazione pugliese con dettaglio comunale dal 2002 al 2025.

Può essere utile per rendere il progetto regionale anziché limitato a Bari.

---

# 6. Altri dataset già individuati a Bari

## Incidenti stradali

Sono presenti nel catalogo Open Data del Comune di Bari dataset sugli incidenti stradali per diversi anni, inclusi 2022, 2023, 2024 e 2025.

Funzione possibile:

- individuare strade particolarmente trafficate/pericolose;
- incrociare traffico, sicurezza e assenza di verde;
- eventualmente individuare assi stradali dove integrare infrastrutture verdi.

Non è però un input prioritario dell'IPF.

---

## Trasporto pubblico / GTFS / AMTAB

Nel catalogo sono presenti dati relativi alla mobilità e al trasporto pubblico, inclusi dati GTFS.

Possibile utilizzo:

```text
traffico elevato
+
fermata autobus
+
molte persone
+
assenza di ombreggiamento
=
possibile priorità per verde/ombreggiamento
```

Potrebbe diventare una funzione aggiuntiva interessante della dashboard.

---

# 7. Dataset esterni a dati.puglia.it

È stato valutato anche l'utilizzo di fonti nazionali ed europee.

## 7.1 European Industrial Emissions Portal / E-PRTR

Fonte:
https://industry.eea.europa.eu/industrial-emissions/dataset

European Environment Agency.

Contiene dati sui grandi complessi industriali europei e sulle emissioni di sostanze inquinanti.

Il dataset spaziale considerato copre il periodo 2007–2024.

Possibili informazioni:

- posizione degli impianti;
- tipo di attività;
- emissioni;
- sostanze emesse, ad esempio NOx e altre sostanze.

Potrebbe essere più informativo del semplice dato "presenza di una fabbrica".

Importante: non bisogna affermare automaticamente che un impianto causa l'inquinamento di una specifica cella. Per stabilire un rapporto causale servirebbe un modello di dispersione o un'analisi specifica.

---

## 7.2 ISPRA – consumo del suolo

Fonte:
https://www.isprambiente.gov.it/it/attivita/suolo-e-territorio/suolo/il-consumo-di-suolo/i-dati-sul-consumo-di-suolo

ISPRA mette a disposizione dati e cartografia sul consumo del suolo a livello nazionale, regionale, provinciale e comunale, oltre a dati GIS e servizi OGC.

Può essere utilizzato come fonte complementare al dataset regionale.

---

## 7.3 Copernicus / Sentinel-2

Possibile fonte esterna molto interessante.

I dati satellitari possono permettere di stimare:

- copertura vegetale;
- densità della vegetazione;
- variazione stagionale;
- superfici vegetate;
- superfici artificiali;
- indici di vegetazione come NDVI.

È particolarmente utile perché consente di osservare la vegetazione reale anche dove il Comune non dispone di un censimento dettagliato.

---

## 7.4 Copernicus Land Monitoring Service

Fonte europea per dati di copertura e uso del territorio.

Può fornire una base territoriale omogenea per confrontare zone differenti e comuni differenti.

È interessante soprattutto per la parte GIS.

---

## 7.5 Dati meteorologici / temperatura

È stata individuata come possibile categoria da cercare e integrare.

Possibile utilizzo:

- temperatura;
- stress termico;
- individuazione di aree soggette a forte calore;
- integrazione con consumo del suolo e vegetazione.

Questo permetterebbe di estendere il progetto dal semplice inquinamento alla **resilienza climatica urbana**.

---

# 8. Dataset da privilegiare

Per l'MVP non conviene utilizzare troppi dataset.

La combinazione iniziale consigliata è:

### Open Data Puglia / Bari

1. 🌿 Aree verdi
2. 💨 Qualità dell'aria
3. 📍 Stazioni ARPA
4. 🚗 Flussi di traffico
5. 🚦 Centraline semaforiche
6. 👥 Popolazione
7. 🏭 Impianti AIA

### Fonte esterna principale

8. 🏭 European Industrial Emissions Portal / E-PRTR

### Eventuali estensioni

9. 🛰️ Copernicus/Sentinel-2
10. 🌡️ Dati meteorologici
11. 🏙️ ISPRA consumo/impermeabilizzazione del suolo
12. 🚌 GTFS/AMTAB
13. 🚗 Incidenti stradali

---

# 9. Architettura concettuale dell'MVP

```text
                    OPEN DATA PUGLIA
                           │
       ┌───────────────────┼───────────────────┐
       ↓                   ↓                   ↓
     VERDE               ARIA              TRAFFICO
       │                   │                   │
 Aree verdi          Centraline ARPA       Centraline
       │                   │                   │
       └───────────────────┼───────────────────┘
                           ↓
                      GRIGLIA GIS
                     DELLA CITTÀ
                           │
                  ┌────────┴────────┐
                  ↓                 ↓
             POPOLAZIONE        INDUSTRIA
                  │                 │
                  └────────┬────────┘
                           ↓
                    NORMALIZZAZIONE
                           ↓
                    INDICE IPF 0–100
                           ↓
                    MAPPA PRIORITÀ
                           ↓
                 STIMA PIANTUMAZIONI
                           ↓
                     DASHBOARD
```

---

# 10. Esempio di dashboard

La dashboard potrebbe avere:

```text
┌──────────────────────────────────────────────────────┐
│ 🌳 GREEN PUGLIA                                     │
│                                                      │
│ Comune: [BARI ▼]                                    │
│ Anno:   [2026 ▼]                                    │
├──────────────────────────────────────────────────────┤
│                                                      │
│                     MAPPA                            │
│                                                      │
│       🔴 Zona 1        🟢 Zona 4                    │
│                                                      │
│              🔴 Zona 2                              │
│                                                      │
│       🟠 Zona 3              🟢 Zona 5              │
│                                                      │
├────────────────────┬─────────────────────────────────┤
│ PRIORITÀ           │ ZONA SELEZIONATA                │
│                    │                                 │
│ 🔴 Alta       12   │ Quartiere X                    │
│ 🟠 Media       8   │                                 │
│ 🟢 Bassa      15   │ IPF: 87/100                    │
│                    │                                 │
│                    │ Alberi stimati: 480             │
│                    │ Verde attuale: 8,2%             │
│                    │ Traffico: Alto                  │
│                    │ Qualità aria: Critica            │
└────────────────────┴─────────────────────────────────┘
```

La funzione importante è mostrare **"Perché questa zona è prioritaria?"**.

---

# 11. Stima del numero di alberi

È stato deciso di non formulare il problema come:

> "Quanti alberi servono per ripristinare l'ossigeno?"

Questa formulazione sarebbe scientificamente troppo semplicistica.

È preferibile usare:

> **"Quante nuove piantumazioni sono stimate necessarie per raggiungere il target di copertura verde definito dal modello?"**

Esempio:

```text
Zona: Libertà

Verde attuale:      8,2%
Target:            15,0%

Superficie utile:  42.000 m²
Alberi esistenti:  213

Nuovi alberi stimati: 480

Priorità: ALTA
```

Il numero deve essere presentato come **stima del modello**, non come un valore scientifico assoluto.

---

# 12. Possibile evoluzione: Urban Green Planner

Il progetto potrebbe essere presentato non semplicemente come:

> "un sistema che dice dove piantare alberi"

ma come:

# Urban Green Planner

Una piattaforma di supporto alle decisioni per la pianificazione del verde urbano.

Esempio:

```text
Zona Libertà – Bari

Priorità: 87/100

Motivazioni:
- alta concentrazione di traffico;
- qualità dell'aria critica;
- bassa presenza di verde;
- elevata densità abitativa;
- elevata superficie impermeabilizzata;
- sorgenti emissive nelle vicinanze.

Intervento suggerito:
- aumento della copertura vegetale;
- nuove piantumazioni;
- priorità alle zone maggiormente esposte;
- eventuale attenzione alle fermate del trasporto pubblico.
```

La piattaforma dovrebbe mostrare i dati che hanno portato alla priorità, rendendo il risultato interpretabile.

---

# 13. Limiti e attenzioni

## Granularità geografica

Non tutti i dataset hanno la stessa granularità.

Esempi:

- alberi/centraline → dati puntuali;
- aree verdi → dati spaziali;
- traffico → sensori;
- popolazione → civici;
- consumo del suolo → può essere comunale.

Per questo è consigliabile creare una **griglia GIS comune** e riportare tutti i dati sulla stessa unità spaziale.

## Causalità

La presenza di una fabbrica o di un impianto AIA non dimostra automaticamente che quell'impianto causi l'inquinamento di una zona.

È corretto parlare di:

- prossimità;
- pressione;
- correlazione;
- sorgenti emissive;

e non di causalità, a meno di disporre di un modello appropriato.

## Qualità dell'aria

I dati ARPA giornalieri possono essere soggetti a successiva revisione.

## Stima alberi

Il numero di alberi deve essere presentato come risultato di un modello e non come una quantità scientificamente certa.

---

# 14. MVP consigliato per l'hackathon

La versione minima funzionante potrebbe essere:

### Input

- Aree verdi;
- Traffico;
- Qualità aria;
- Popolazione;
- Impianti AIA.

### Processing

1. Caricamento dei dataset.
2. Pulizia e normalizzazione.
3. Conversione delle coordinate.
4. Creazione griglia GIS.
5. Associazione dei dati alle celle.
6. Normalizzazione 0–100.
7. Calcolo IPF.
8. Classificazione:
   - verde = bassa priorità;
   - giallo = media;
   - arancione = medio-alta;
   - rosso = alta.

### Output

Dashboard con:

- mappa interattiva;
- heatmap;
- indice IPF;
- motivazioni;
- dati della zona selezionata;
- stima delle nuove piantumazioni.

---

# 15. Priorità dei prossimi lavori

Il prossimo lavoro tecnico dovrebbe essere:

## 1. Scaricare i dataset

Verificare i file reali e non soltanto le descrizioni del catalogo.

## 2. Analizzare le colonne

Per ogni dataset identificare:

- nome campo;
- tipo;
- coordinate;
- unità di misura;
- frequenza temporale;
- livello geografico.

## 3. Verificare le coordinate

Portare tutti i dati in un sistema geografico comune, ad esempio WGS84/EPSG:4326, quando appropriato.

## 4. Creare la griglia GIS

Ad esempio:

```text
500m × 500m
```

come prima ipotesi.

## 5. Aggregare i dati

Per ogni cella:

```text
verde
traffico
inquinamento
popolazione
industria
```

## 6. Definire e testare l'IPF

Stabilire i pesi e verificare che il risultato abbia senso su Bari.

## 7. Costruire la dashboard

Visualizzare:

```text
mappa → zona → IPF → motivazioni → intervento suggerito
```

---

# 16. Concetto sintetico da presentare al team

> **Urban Green Planner è una piattaforma GIS che combina Open Data Puglia, dati ambientali, traffico, popolazione e informazioni territoriali per individuare le aree urbane che presentano la maggiore necessità di interventi di forestazione e infrastruttura verde. Il sistema calcola un Indice di Priorità di Forestazione, visualizza le zone critiche su una mappa e fornisce una stima delle possibili nuove piantumazioni, spiegando quali dati hanno determinato la priorità.**

---

# 17. Fonti principali

- Open Data Regione Puglia: https://dati.puglia.it/
- Aree verdi Bari: https://dati.puglia.it/ckan/dataset/aree-verdi
- Flussi traffico Bari: https://dati.puglia.it/v2/dataset/centraline-semaforiche-flussi-di-traffico-giornalieri
- Centraline semaforiche Bari: https://dati.puglia.it/ckan/dataset/centraline-semaforiche-posizionamento-e-sensoristica-a-bordo
- Qualità aria ARPA: https://dati.puglia.it/v2/dataset/dati-qualita-aria
- Stazioni qualità aria: https://dati.puglia.it/ckan/dataset/stazioni-qualita-aria
- Popolazione Bari: https://dati.puglia.it/ckan/dataset/popolazione-residente1
- Impianti AIA: https://dati.puglia.it/ckan/dataset/aia
- Censimento arboreo Copertino: https://dati.puglia.it/ckan/dataset/censimento-arboreo-comune-di-copertino1
- Piantumazioni Lecce: https://dati.puglia.it/ckan/dataset/piantumazioni-realizzate-e-programmate-di-alberi-nel-comune-di-lecce
- Consumo del suolo: https://dati.puglia.it/ckan/dataset/consumo-del-suolo-a-partire-dal-2006
- Uso del Suolo 2011: https://dati.puglia.it/ckan/dataset/uso-del-suolo-2011-uds
- Aree protette: https://dati.puglia.it/ckan/dataset/parchi-aree-naturali-protette-siti-di-importanza-rilevante
- Parchi e aree verdi Lecce: https://dati.puglia.it/ckan/dataset/parchi-e-aree-a-verde
- Popolazione pugliese: https://dati.puglia.it/ckan/dataset/popolazione-pugliese-a-partire-dal-2002
- EEA European Industrial Emissions Portal: https://industry.eea.europa.eu/industrial-emissions/dataset
- ISPRA – Dati sul consumo di suolo: https://www.isprambiente.gov.it/it/attivita/suolo-e-territorio/suolo/il-consumo-di-suolo/i-dati-sul-consumo-di-suolo

---

# 18. Stato attuale dell'idea

La direzione individuata è:

**Bari come primo caso di studio → griglia GIS → integrazione di verde + traffico + aria + popolazione + industria → IPF → heatmap → stima delle piantumazioni → dashboard esplicativa.**

Come estensioni future:

- Copernicus/Sentinel-2 per vegetazione;
- dati meteorologici e temperatura;
- ISPRA per impermeabilizzazione;
- trasporto pubblico;
- incidenti stradali;
- estensione ad altri comuni pugliesi;
- eventuale validazione tramite dati storici sulle piantumazioni di Lecce.
