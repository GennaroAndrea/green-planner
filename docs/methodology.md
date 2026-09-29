# Metodologia dell'Indice di Priorità di Forestazione (IPF)

> **Lingua**: questo file è scritto e mantenuto **in italiano** (eccezione alla regola "tutto in inglese tranne la UI", vedi `CLAUDE.md`).
> **Stato**: aggiornato alla fine della Fase 1 (pipeline completa), 29 settembre 2026. Build di riferimento: `uv run python -m pipeline build`.
> **Scopo**: descrivere *come* è costruito il modello e *perché* abbiamo fatto ogni scelta. È la fonte unica sulla metodologia: da qui nasceranno la pagina "Metodologia e fonti" dell'app (FR-47) e le risposte alle domande della giuria.
>
> Documenti collegati:
> - `docs/requirements_and_plan.md`: requisiti, piano e **registro delle decisioni** (§10.0). I codici tra parentesi (es. **Q8**) rimandano a quel registro.
> - `docs/artefacts.md`: formato dei file prodotti dalla pipeline (colonne, tipi).
> - `config/bari.yaml`: tutti i parametri numerici citati qui.
>
> **Regola di manutenzione**: ogni modifica al modello (codice in `pipeline/` o parametri in `config/bari.yaml`) va riportata in questo file, nella stessa modifica.

---

## 1. In sintesi

Per ogni cella di una griglia regolare su Bari calcoliamo quattro indicatori, li portiamo su una scala 0–100, e li combiniamo con una somma pesata nell'**IPF** (0–100). Più alto è l'IPF, più la zona è prioritaria per nuovi alberi e nuovo verde.

```
dati aperti → pulizia → griglia 250/500 m → indicatori grezzi → area di studio
  → normalizzazione 0–100 → IPF (somma pesata) → classi (quartili)
  → stima alberi → aggregazione per quartiere → verifica di robustezza dei pesi
```

| Indicatore | Cosa misura | Peso effettivo |
|---|---|---|
| Deficit di verde | quanto poco verde pubblico c'è nella cella | 33,3% |
| Inquinamento | NO₂, PM10, PM2.5 rispetto ai limiti UE 2030 | 22,2% |
| Traffico | veicoli giornalieri misurati agli incroci vicini | 22,2% |
| Popolazione | residenti per km² (persone esposte) | 22,2% |
| ~~Pressione industriale~~ | ~~emissioni di impianti vicini~~ | escluso (dati insufficienti, §4.5) |

## 2. Principi

Questi principi vengono dall'idea originale e valgono per tutto il progetto:

1. **Mitigazione, non "ossigeno".** L'obiettivo è ridurre l'esposizione della popolazione a inquinamento e calore e aumentare il verde urbano. Non parliamo di "restituire ossigeno".
2. **Priorità relativa.** L'IPF confronta le zone di Bari tra loro. "Priorità alta" significa "tra le più prioritarie della città", non "sopra una soglia assoluta" (**Q11**).
3. **Spiegabilità.** Ogni punteggio si può ricondurre ai valori degli indicatori e ai pesi: nessuna scatola nera (NFR-02).
4. **Prossimità, non causalità.** Gli impianti industriali indicano una *pressione* vicina, mai la *causa* di un problema.
5. **Stime di modello.** Il numero di alberi è una stima basata su parametri dichiarati, non un valore scientifico assoluto.
6. **Dati ARPA soggetti a validazione.** I dati sulla qualità dell'aria possono essere rivisti dall'ente.
7. **Nessuna chiamata live.** Tutti i dati sono scaricati e pre-elaborati. La demo non dipende da servizi esterni (NFR-03).

## 3. Dati utilizzati

| Dato | Fonte | Periodo | Uso nel modello |
|---|---|---|---|
| Aree verdi (D1) | Comune di Bari, SHP (593 poligoni) | 2024 | deficit di verde, stima alberi |
| Flussi di traffico giornalieri (D2) | Comune di Bari, CSV mensili | set. 2025 – giu. 2026 | traffico |
| Posizione centraline semaforiche (D3) | Comune di Bari, JSON mensili | come D2 | traffico |
| Stazioni qualità dell'aria (D5) | ARPA Puglia, GeoJSON | – | posizione delle 5 stazioni di Bari |
| Medie annuali 2025 (NO₂, PM10, PM2.5) | ARPA Puglia, *Relazione annuale 2025*, trascritte a mano in `data/manual/arpa_annual_2025.csv` | 2025 | inquinamento |
| Popolazione residente (D6) | Comune di Bari, 4 CSV per fascia d'età, per indirizzo | – | popolazione |
| Numeri civici, quartieri, confine comunale (D8) | SIT Comune di Bari | – | posizione dei residenti, quartieri, confine |
| Uso del Suolo 2011, superfici artificiali | Regione Puglia | 2011 | area di studio |
| E-PRTR (D10) | Agenzia Europea dell'Ambiente, v16 | 2007–2024 | pressione industriale (solo contesto) |

Fonti, URL e date di download sono registrati in `data/raw/manifest.json` e riportati in `metadata.json`.

## 4. Unità spaziale e area di studio

### 4.1 Sistema di riferimento
Tutti i calcoli avvengono in **EPSG:32633 (WGS84 / UTM 33N)**, un sistema metrico, per avere aree in m² e distanze in metri. I dati per il web sono esportati in **EPSG:4326**. Nota: lo shapefile delle aree verdi è già in UTM 33N, anche se il catalogo lo descrive in WGS84.

### 4.2 Griglia
- Due griglie quadrate, **250 m** (predefinita) e **500 m** (**Q7**). L'origine è allineata a multipli di 1.000 m, quindi ogni cella da 500 m contiene esattamente quattro celle da 250 m.
- Le celle sono **ritagliate sul confine comunale** (e quindi sulla costa).
- I **frammenti** più piccoli del 10% di una cella intera (6.250 m² a 250 m) sono eliminati (**Q28**). *Perché*: su superfici così piccole le percentuali (quota di verde, densità) diventano estreme e senza significato.
- Risultato: 2.006 celle a 250 m, 528 a 500 m.

### 4.3 Quartieri
- Unità di sintesi: i **17 quartieri del SIT** (**Q16**), fusi in un poligono per quartiere. Coincidono con i 16 valori `RIONE` dei dati di popolazione, più Torre a Mare.
- Ogni cella appartiene al quartiere che contiene il suo **centro** (**Q27**). *Perché*: è semplice e l'effetto è piccolo. L'alternativa (dividere la cella in proporzione all'area) è più precisa ma più complessa.
- I valori di quartiere sono calcolati dalla griglia da **250 m**, la più fine (**Q27**).

### 4.4 Area di studio (celle analizzate)
Una cella è analizzata se:

- il suo quartiere è coperto dai dati di popolazione, **e**
- ha una densità di almeno **800 residenti/km²**, **oppure** almeno il **30%** della sua superficie è "superficie artificiale" (classe 1 dell'Uso del Suolo 2011) (**Q6**).

*Perché*: il dato delle aree verdi copre solo il **verde pubblico urbano**. Senza questa maschera, campagne e aree agricole risulterebbero "senza verde" e avrebbero una priorità falsamente alta.

- La soglia di 800/km² equivale a **50 residenti in una cella da 250 m** (valore deciso in **Q6**), espressa come densità (**Q22**). Così la stessa regola vale per le celle da 500 m (200 residenti) e per le celle di bordo ritagliate.
- **Torre a Mare è esclusa**: non compare nei dati di popolazione, quindi il suo punteggio di popolazione sarebbe falsamente zero (**Q4a**).
- Risultato a 250 m: **1.127 celle analizzate** su 2.006, con il 99,5% dei residenti. Delle 1.127 celle, 449 superano entrambe le soglie, 6 solo quella di popolazione, **672 solo quella di superficie artificiale** (zone industriali, porto, infrastrutture, servizi: il 45% di queste ha zero residenti).

## 5. Indicatori

### 5.1 Deficit di verde
- **Valore grezzo**: quota della cella coperta da aree verdi pubbliche (`green_share`, 0–1). I poligoni vengono prima uniti, così le sovrapposizioni contano una sola volta.
- **Punteggio**: `deficit = 100 − punteggio normalizzato della copertura`. Più verde c'è, più il punteggio è basso.
- **Nota**: il 49% delle celle analizzate non contiene alcun verde pubblico mappato, quindi ha deficit 100 (vedi §13).

### 5.2 Traffico
Il traffico si misura solo agli incroci con centralina, quindi va "stimato" per le celle intorno.

**Passo 1: pulizia delle letture giornaliere** (**Q8**):
- Il mese di **agosto 2025 è escluso** (il traffico estivo non è rappresentativo). Restano 10 mesi, da settembre 2025 a giugno 2026.
- Una lettura pari a **0 è considerata dato mancante**, non "zero veicoli". I file finiscono spesso con serie di zeri che indicano mancanza di dati.
- Una lettura **superiore a 50.000 veicoli/giorno** per singolo sensore è considerata un errore e trattata come mancante (**Q25**). *Perché*: un sensore misura una sola corsia, e una corsia porta al massimo circa 2.000 veicoli/ora, cioè circa 48.000 al giorno. Le letture escluse sono picchi isolati di un solo giorno sulla centralina BG022 (Via Giovanni XXIII – O. Flacco), tra letture normali dello stesso sensore. Per esempio: 451 (3 ott.), **131.674** (13 ott.), 519 (23 ott.). Sul totale dei dati, il 99,9% delle letture è sotto i 21.000. L'unico sensore stabilmente alto (30–38 mila al giorno, controller 35) non viene toccato.

**Passo 2: traffico medio per incrocio** (**Q8a**, **Q29**):
- Ogni sensore viene mediato sui giorni in cui ha funzionato; poi si **sommano le medie** dei sensori dell'incrocio.
- *Perché*: se sommassimo i sensori giorno per giorno, un giorno con un sensore guasto sembrerebbe un giorno con meno traffico.
- La somma può contare più volte gli stessi veicoli (entrata e uscita dallo stesso incrocio). Per questo è un indice di pressione relativo, non un conteggio esatto.
- Su 83 centraline, **66 hanno dati validi**. Le altre 17 riportano solo zeri, quindi nessun dato; una di queste non ha nemmeno una posizione valida.

**Passo 3: diffusione alle celle** (**Q8d**, **Q24**):
- Ogni cella riceve una parte del traffico di ogni incrocio, che diminuisce con la distanza secondo una curva gaussiana con **σ = 300 m**.
- I contributi sotto l'**1%** sono azzerati, il che corrisponde a circa **910 m** (**Q24**).
- Valore grezzo della cella: `traffic_index = Σ traffico_incrocio × peso(distanza)`.

| Distanza dall'incrocio | Quota ricevuta |
|---|---|
| 0 m | 100% |
| 300 m | 61% |
| 600 m | 14% |
| 900 m | 1,1% |
| oltre ~910 m | 0 |

*Perché il taglio all'1% (Q24)*: il punteggio usa una scala logaritmica (§6), che amplifica i valori piccoli. Senza taglio, la "coda" della gaussiana dava punteggi medi a celle lontane da qualsiasi sensore. Per esempio, a 900 m da un incrocio da 20.000 veicoli la cella riceve l'1% del traffico ma otteneva 51/100. Il punteggio misurava soprattutto la distanza dal sensore più vicino. Con il taglio, le celle a più di ~910 m da ogni sensore hanno traffico 0: "nessun traffico misurato nelle vicinanze". È il 31% delle celle analizzate.

### 5.3 Inquinamento atmosferico
- **Valore grezzo** (**Q3**, **Q19**): per ogni stazione, media dei rapporti `media annuale 2025 / valore limite` per NO₂, PM10 e PM2.5. I limiti sono quelli della **Direttiva UE 2024/2881**, in vigore dal 2030: NO₂ 20, PM10 20, PM2.5 10 µg/m³.
- *Perché questi limiti (Q19)*: con i limiti in vigore oggi (D.Lgs. 155/2010: 40/40/25) tutte le stazioni sarebbero ben sotto 1 e il segnale sarebbe debole. I limiti 2030 sono il riferimento legale europeo imminente e sono più vicini alle evidenze sanitarie. Poiché l'indice è relativo, conta soprattutto l'equilibrio tra gli inquinanti.
- *Perché le medie annuali (Q3b)*: i limiti UE sono medie annuali, e l'API ARPA fornisce solo il giorno precedente, che dipende troppo dal meteo.
- Se una stazione non misura un inquinante, la media si fa sugli inquinanti disponibili. Carbonara e CUS non misurano il PM2.5.

| Stazione | NO₂ | PM10 | PM2.5 | Rapporto medio |
|---|---|---|---|---|
| Bari – Cavour | 26 | 22 | 11 | 1,17 |
| Bari – Caldarola | 22 | 22 | 11 | 1,10 |
| Bari – Kennedy | 21 | 20 | 11 | 1,05 |
| Bari – CUS | 17 | 21 | – | 0,95 |
| Bari – Carbonara | 15 | 19 | – | 0,85 |

- **Diffusione alle celle**: interpolazione **IDW** (media delle stazioni pesata sull'inverso della distanza) con **potenza 2** (**Q26**). *Perché*: è il valore standard. Ogni zona segue soprattutto la stazione più vicina, con transizioni morbide. Con potenza 1 la mappa si appiattirebbe sulla media cittadina; con potenza 3 apparirebbero "isole" nette intorno alle stazioni.
- **Limite**: con sole 5 stazioni, questo strato è un gradiente molto liscio e poco dettagliato. Per questo il suo peso è stato ridotto dal 30% dell'idea originale al 20% (**Q10**).

### 5.4 Popolazione
- **Totali**: i file sono fasce d'età **cumulative** (under14 ⊂ under18 ⊂ under67), quindi:
  - residenti totali = `under67 + over67` = 261.399;
  - residenti vulnerabili = `under14 + over67`.
- **Indicatore IPF**: residenti **totali** (**Q20**), espressi come **densità** (residenti/km²) (**Q21**).
  - *Perché i totali*: l'indicatore rappresenta la popolazione esposta, e i vulnerabili sono mostrati come informazione nel dettaglio della zona.
  - *Perché la densità*: le celle di bordo ritagliate non vengono penalizzate per la superficie più piccola. Per le celle intere, densità e conteggio sono equivalenti.
- **Posizionamento dei residenti** (**Q4b**, **Q23**). I dati hanno solo l'indirizzo, quindi ogni indirizzo viene collegato a un numero civico del SIT (punto con coordinate). Nomi di strada e numeri sono normalizzati: maiuscole, niente accenti né punteggiatura.
  1. Corrispondenza esatta via + numero + esponente (es. "12/A"): **92,2%** dei residenti.
  2. Corrispondenza via + numero, ignorando l'esponente: +0,2%.
  3. I residenti rimanenti (**7,7%**) sono distribuiti in parti uguali sui numeri civici del loro quartiere (**Q23**). *Perché*: così finiscono dove ci sono edifici, e il risultato non dipende dalla dimensione della griglia. Nessun residente va perso.
- **Limite**: il dataset conta circa 261 mila residenti contro i circa 316 mila ufficiali di Bari (−17%), e Torre a Mare è assente (§4.4).

### 5.5 Pressione industriale (esclusa)
- **Regola** (**Q5**, **Q18**): impianti E-PRTR entro **10 km** dal confine, con rilasci in aria di NOₓ o PM10, che hanno dichiarato dati **negli ultimi 5 anni** di rendicontazione (2020–2024). L'indicatore si usa solo se ci sono **almeno 3** impianti.
- **Dati**: entro 10 km ci sono 4 impianti, ma solo 2 hanno dichiarato di recente: Centrale a ciclo combinato di Modugno (2024) e O-I Manufacturing, Bari (2022). Gli altri due sono la centrale termoelettrica di Bari (2008) e Powerflor, Molfetta (2017).
- **Risultato**: l'indicatore è **escluso**, e il suo 10% è ridistribuito in proporzione sugli altri (§7). Gli impianti restano visibili sulla mappa come **livello di contesto**, sempre come "pressione", mai come "causa".
- *Perché si escludono le dichiarazioni vecchie (Q18)*: metterebbero "pressione" dove l'impianto potrebbe non esistere più.
- *Perché non usare i dati AIA*: il CSV regionale è un elenco di procedimenti autorizzativi, senza coordinate né identificativo dell'impianto.

## 6. Normalizzazione (0–100)
Metodo **min–max robusto** (**Q9**), calcolato solo sulle celle analizzate:

- i valori sotto il **5° percentile** valgono 0;
- quelli sopra il **95° percentile** valgono 100;
- in mezzo, la scala è lineare.

Per traffico e popolazione si applica prima una trasformazione **logaritmica** (`log(1 + x)`).

- *Perché il min–max robusto*: mantiene le distanze reali tra le zone, e pochi valori estremi (per esempio un incrocio molto trafficato) non schiacciano tutti gli altri. L'alternativa, il rango percentile, esagererebbe differenze minime.
- *Perché il logaritmo*: traffico e densità variano di diversi ordini di grandezza. In scala lineare conterebbero solo i pochissimi valori più alti. In scala logaritmica ogni moltiplicazione per 10 vale lo stesso numero di punti (circa 21 per il traffico).

Estremi usati (griglia 250 m):

| Indicatore | 0 punti | 100 punti |
|---|---|---|
| Inquinamento (rapporto) | ≤ 0,90 | ≥ 1,10 |
| Copertura verde | 0% (quindi deficit 100) | ≥ 46,8% (quindi deficit 0) |
| Traffico (indice) | 0 | ≥ 44.200 |
| Densità di popolazione | 0 | ≥ 18.800 ab./km² |

## 7. IPF e pesi

```
IPF = Σ pesoᵢ × punteggioᵢ        (Σ pesoᵢ = 1, punteggioᵢ ∈ [0, 100])
```

| | Inquinamento | Deficit verde | Traffico | Popolazione | Industria |
|---|---|---|---|---|---|
| Pesi configurati (**Q10**) | 20 | 30 | 20 | 20 | 10 |
| Pesi effettivi (industria esclusa) | 22,2 | 33,3 | 22,2 | 22,2 | – |

- *Perché questi pesi*: il deficit di verde è lo strato più diretto e affidabile, quindi ha il peso maggiore. L'inquinamento è il più debole (5 stazioni), quindi passa da 30 (idea originale) a 20.
- Il peso dell'indicatore escluso è ridistribuito **in proporzione** agli altri.
- Ogni **contributo** `pesoᵢ × punteggioᵢ` è salvato separatamente. La somma dei contributi è esattamente l'IPF, e questo è la base della spiegazione (§11).
- L'utente può cambiare i pesi nell'app (FR-45). L'IPF si ricalcola con le stesse formule (`pipeline/model.py`, condiviso con il backend).
- **Pesi personalizzati** (scenario): l'utente indica un valore per ciascun indicatore attivo, tra 0 e 100. I valori sono **normalizzati sul loro totale** (che deve essere positivo), quindi non devono sommare a 100 (**Q36**). Un peso diverso da 0 per un indicatore escluso (industria) viene rifiutato (**Q30**). Con i pesi personalizzati si ricalcolano IPF, classi (quartili), posizioni in classifica e verifica di robustezza. Punteggi, alberi e aggregazione per quartiere non dipendono dai pesi e restano invariati.

## 8. Classi di priorità
Quattro classi (**Q11**), **bassa / media / medio-alta / alta** (verde / giallo / arancione / rosso), con confini ai **quartili** dell'IPF delle celle analizzate. Per i quartieri si usano i quartili dei 16 quartieri analizzati.

- Confini a 250 m: 53,8 / 65,4 / 77,9.
- Confini per i quartieri: 72,3 / 78,9 / 86,2.
- *Perché i quartili*: lo scopo dello strumento è ordinare le zone per decidere dove intervenire prima, e i quartili danno sempre una mappa leggibile. Con soglie fisse (25/50/75) le celle rosse potrebbero essere pochissime o nessuna.
- La UI deve dire "priorità relativa rispetto al resto della città".

## 9. Aggregazione per quartiere
Per ogni quartiere si usano le sue celle analizzate della griglia da 250 m:

- i **punteggi** sono la **media pesata sulla popolazione** dei punteggi delle celle (FR-09);
- l'IPF del quartiere è la media pesata sulla popolazione degli IPF delle celle, e resta lineare nei pesi, quindi il backend può ricalcolarlo direttamente;
- residenti, verde, deficit e alberi sono **somme**; densità e quota di verde si riferiscono alla superficie delle celle analizzate.

*Perché pesare sulla popolazione*: la priorità di un quartiere deve riflettere dove vivono le persone. Una cella industriale senza residenti non deve pesare quanto un isolato densamente abitato.

## 10. Stima del numero di alberi
```
verde_obiettivo_m2   = quota_obiettivo × area_cella
deficit_m2           = max(0, verde_obiettivo_m2 − verde_attuale_m2)
piantabile_m2        = deficit_m2 × frazione_piantabile
nuovi_alberi         = parte_intera(piantabile_m2 / area_chioma)
```

| Parametro (**Q12**) | Valore | Motivazione |
|---|---|---|
| Quota obiettivo di verde | **15%** | Dall'idea originale. La pagina metodologica cita anche la regola 3-30-300 (30% di chioma arborea, Konijnendijk 2021), precisando che "chioma" e "aree verdi mappate" non sono la stessa cosa. |
| Frazione piantabile del deficit | **25%** | Pura ipotesi: non esistono dati sullo spazio piantabile a Bari (edifici, strade, sottoservizi). Mostrata nella pagina metodologica, non modificabile nell'app (**Q43**): per esplorare scenari c'è il simulatore (§10.1). |
| Area di chioma per albero | **30 m²** | Albero di taglia media, chioma di circa 6 m. |

- Esempio: una cella intera da 250 m (62.500 m²) senza verde ha un obiettivo di 9.375 m² e 2.344 m² piantabili, quindi **78 alberi**.
- Totale per le celle analizzate (250 m): circa **54.900 alberi**.
- È una **stima di modello**, e la UI lo dichiara sempre.

### 10.1 Simulatore ("cosa succede se pianto N alberi?")
Per una cella o un quartiere analizzato, il simulatore stima l'effetto di N nuovi alberi (**Q37**):

```
verde_dopo_m2      = verde_attuale_m2 + N × area_chioma          (30 m² per albero)
quota_verde_dopo   = verde_dopo_m2 / area
punteggio_deficit  = 100 − minmax(quota_verde_dopo)              (stessi limiti p5–p95 del calcolo, §6)
IPF_dopo           = IPF_prima + peso_verde × (punteggio_deficit_dopo − punteggio_deficit_prima)
```

- **Cambia solo l'indicatore del verde.** Inquinamento, traffico e popolazione restano invariati: è una simulazione semplificata e la UI lo dichiara.
- **Classe e posizione** del risultato sono calcolate rispetto al resto della città, che resta com'è (stessi confini di classe dello scenario corrente).
- **Quartieri**: gli N alberi sono ripartiti tra le celle analizzate da 250 m del quartiere **in proporzione al loro deficit di verde** (in proporzione all'area se nessuna cella ha deficit). Poi il punteggio del quartiere si ricalcola come media pesata sulla popolazione (§9).
- Il simulatore mostra due riferimenti:
  - la **stima del modello** (`nuovi_alberi`, §10), che considera solo la quota piantabile (25%) del deficit;
  - gli **alberi necessari per il 15%**, cioè `deficit_m2 / area_chioma`, arrotondato per eccesso.

  Il secondo numero è di solito circa 4 volte il primo: raggiungere l'obiettivo richiederebbe più spazio di quello stimato come piantabile.
- *Nota sui quartieri*: il deficit è la somma dei deficit delle singole celle. Un quartiere può quindi avere una quota media di verde superiore al 15% e comunque un deficit, se il verde è concentrato in poche celle. Con i dati attuali succede per Murat (16,3%), Libertà (20,9%) e San Paolo (23,2%).
- *Nella scheda del quartiere* (**Q42**) non si mostra "quota attuale → 15%", ma la quota media e il numero di celle sotto l'obiettivo, ad esempio *"Verde pubblico medio 20,9% · 14 celle su 29 sotto il 15%"* (Libertà; Murat 13 su 25, San Paolo 46 su 82). Nella scheda della cella resta "8,2% → 15%".
- *Esempio* (Libertà, pesi predefiniti):
  - IPF 86,3, classe alta, 4° posto;
  - con i 601 alberi stimati: IPF 85,1, classe medio-alta, 5° posto;
  - con i 2.432 alberi necessari per il 15% in ogni cella: IPF 81,6, 6° posto.

## 11. Spiegazione ("Perché questa zona è prioritaria?")
- Per ogni zona si ordinano i contributi `pesoᵢ × punteggioᵢ` e si mostrano i **3 principali**. Esempio: *"Traffico elevato (83/100): contribuisce per 18 punti all'indice."*
- Il backend restituisce solo chiavi e numeri. Le frasi in italiano stanno nel frontend. Così la spiegazione è sempre esattamente coerente con la formula.

## 12. Verifica di robustezza dei pesi
*Scopo*: dimostrare che la classifica non è un artefatto dei pesi scelti. È la risposta all'obiezione "i vostri pesi sono arbitrari" (**Q17**).

**Metodo Monte Carlo**:
1. Si estraggono **1.000 vettori di pesi** da una distribuzione di Dirichlet centrata sui pesi predefiniti. La concentrazione (α₀ = 73,1) dà in media circa **±5 punti percentuali** di variazione per peso, e ogni vettore ha somma 1.
2. Per ogni vettore si ricalcolano l'IPF e la classifica di tutte le celle e di tutti i quartieri.
3. Per ogni zona si registrano:
   - l'**intervallo di posizione** (5°–95° percentile del rango);
   - la **frequenza nel top N** (top 10 quartieri; top 10% delle celle);
   - la **stabilità di classe** (quota di estrazioni in cui la zona mantiene la sua classe).
4. Una zona è **"robusta"** se:
   - è nel top N e ci resta in almeno l'**80%** delle estrazioni, oppure
   - non è nel top N e mantiene la sua classe in almeno l'80% delle estrazioni.

   Altrimenti è **"sensibile ai pesi"**.
5. **Riepilogo cittadino**: correlazione di Spearman media tra la classifica predefinita e quelle perturbate, e sovrapposizione del top N.
6. **Test uno alla volta**: ogni peso viene spostato di ±10 punti (gli altri riscalati in proporzione) per vedere da quale indicatore la classifica dipende di più.
7. **Pesi personalizzati** (**Q31**): la stessa verifica viene eseguita su richiesta attorno ai pesi scelti dall'utente, con lo stesso seme. Un indicatore con **peso 0 resta a 0** in tutte le estrazioni ("ignorare il traffico" significa ignorarlo): si perturbano solo i pesi diversi da 0, e la concentrazione è calibrata su di essi per mantenere circa ±5 punti. Se non c'è nulla da perturbare (un solo indicatore diverso da 0, o pesi troppo concentrati per ±5 punti), la classifica viene comunque calcolata e la robustezza è indicata come **non applicabile**. Con i pesi predefiniti (tutti diversi da 0) il risultato è identico a quello precalcolato.

**Risultati** (pesi predefiniti):

| | Spearman medio | Top N mantenuto (media) | Zone robuste |
|---|---|---|---|
| Quartieri (16) | 0,98 | 9,98 su 10 | 14 su 16 (100% del top 10) |
| Celle 250 m (1.127) | 0,98 | 101 su 113 | 72% (77% del top 10%) |
| Celle 500 m (315) | 0,98 | 27 su 32 | 63% (69% del top 10%) |

- Nel test uno alla volta, **il top 10 dei quartieri non cambia mai**.
- I due quartieri "sensibili" sono Palese – Macchie e Loseto, al 12° e 13° posto, vicini al confine tra due classi.
- Nelle celle, l'instabilità si concentra ai confini tra le classi, com'è naturale.

## 13. Risultati principali (quartieri, pesi predefiniti)

| Pos. | Quartiere | IPF | Classe | Intervallo posizione | Robusto | Nuovi alberi |
|---|---|---|---|---|---|---|
| 1 | Madonnella | 95,0 | alta | 1–1 | sì | 353 |
| 2 | Murat | 87,5 | alta | 2–4 | sì | 381 |
| 3 | San Pasquale | 87,0 | alta | 2–4 | sì | 2.755 |
| 4 | Libertà | 86,3 | alta | 2–5 | sì | 601 |
| 5 | San Nicola | 86,2 | medio-alta | 3–5 | sì | 480 |
| 6 | Carrassi | 83,2 | medio-alta | 6–6 | sì | 1.813 |
| 7 | Picone | 80,2 | medio-alta | 7–9 | sì | 6.850 |
| 8 | Japigia | 79,4 | medio-alta | 7–10 | sì | 4.617 |
| 9 | Marconi – San Girolamo – Fesca | 78,4 | media | 7–10 | sì | 3.820 |
| 10 | Stanic | 77,3 | media | 8–10 | sì | 11.482 |
| 11 | Santo Spirito | 72,9 | media | 11–13 | sì | 3.080 |
| 12 | Palese – Macchie | 72,7 | media | 11–13 | no | 8.221 |
| 13 | Loseto | 71,3 | bassa | 11–13 | no | 394 |
| 14 | San Paolo | 65,7 | bassa | 14–16 | sì | 2.571 |
| 15 | Ceglie del Campo | 63,5 | bassa | 14–16 | sì | 2.139 |
| 16 | Carbonara | 63,5 | bassa | 14–16 | sì | 5.298 |
| – | Torre a Mare | – | non analizzato | – | – | – |

**Lettura**:
- In testa ci sono i quartieri centrali densi con poco verde pubblico.
- In fondo ci sono le frazioni esterne, con inquinamento e traffico misurati più bassi.
- L'area industriale ASI (Stanic, San Paolo) è analizzata per la sua superficie artificiale, ma ha punteggio di popolazione vicino a 0.
- Gli alberi sono più numerosi nei quartieri grandi con molte celle a basso verde (Stanic, Palese, Picone). La priorità più alta è invece nei quartieri piccoli e densi.

## 14. Limiti noti
1. **Solo verde pubblico.** Il 49% delle celle analizzate non ha verde pubblico mappato e ottiene deficit 100: giardini privati, verde agricolo e alberi stradali non mappati sono invisibili. Estensione possibile: NDVI da Sentinel-2.
2. **Area di studio dominata dalle superfici artificiali.** 672 delle 1.127 celle sono analizzate solo per la soglia del 30% di superficie artificiale: zone industriali, porto, infrastrutture. L'Uso del Suolo è del 2011.
3. **Traffico noto solo vicino alle centraline.** 66 incroci con dati. Oltre ~910 m da ogni centralina il traffico è 0, cioè *non misurato*, non necessariamente *assente* (31% delle celle). A ~910 m il punteggio scende bruscamente a 0.
4. **Inquinamento da 5 stazioni.** Gradiente molto liscio, dati ARPA soggetti a validazione.
5. **Popolazione incompleta.** Circa il 17% dei residenti manca dai dati; il 7,7% è posizionato per quartiere e non per indirizzo; Torre a Mare è esclusa.
6. **Somma dei sensori.** Il traffico di un incrocio può contare più volte gli stessi veicoli: è un indice relativo.
7. **Pressione industriale esclusa.** Il metodo di diffusione spaziale per l'industria non è ancora definito. Se in futuro ci fossero abbastanza impianti, la pipeline si ferma con un errore finché non viene deciso.
8. **Priorità relativa.** Le classi dicono dove intervenire *prima*, non se una zona è "buona" o "cattiva" in assoluto.
9. **Alberi come stima.** Frazione piantabile e chioma sono ipotesi, non misure.

## 15. Dove si trovano parametri e codice

| Passo | Parametri (`config/bari.yaml`) | Codice |
|---|---|---|
| Caricamento e pulizia | `sources`, `traffic.*`, `air.*`, `industry.*` | `pipeline/loaders.py` |
| Griglia | `grid.*`, `urban_mask.min_cell_area_share` | `pipeline/grid.py` |
| Indicatori | `traffic.kernel_*`, `air.idw_power` | `pipeline/indicators.py` |
| Area di studio | `urban_mask.*` | `pipeline/build.py` |
| Quartieri | `zones.*` | `pipeline/loaders.py`, `pipeline/build.py` |
| Normalizzazione, IPF, classi, alberi | `normalisation.*`, `weights`, `classes.*`, `trees.*` | `pipeline/model.py` |
| Robustezza | `sensitivity.*` | `pipeline/sensitivity.py` |
| Ricalcolo con pesi personalizzati (API) | `metadata.json` (pesi predefiniti, `sensitivity`) | `backend/store.py` |
| Simulatore alberi | `trees.crown_area_m2`, limiti di normalizzazione in `metadata.json` | `pipeline/model.py` (`green_deficit_score`, `spread_trees`), `backend/store.py` |

## 16. Storico delle modifiche
- **2026-09-29**: prima versione, alla fine della Fase 1. Include le decisioni Q20–Q29 prese durante l'implementazione.
- **2026-09-29** (Fase 2, backend): regole dei pesi personalizzati (§7, **Q30**) e verifica di robustezza con pesi pari a 0 o troppo concentrati (§12, **Q31**). Nessun cambiamento ai risultati con i pesi predefiniti.
- **2026-09-29** (Fase 3.0, confronto con il prototipo UI): pesi personalizzati normalizzati sul totale (§7, **Q36**); nuovo simulatore alberi (§10.1, **Q37**). Confermate le 4 classi a quartili (**Q34**) e l'esclusione dell'industria dall'indice (**Q35**). Nessun cambiamento ai risultati con i pesi predefiniti.
- **2026-09-29** (Fase 3.0): la frazione piantabile non è modificabile nell'app (§10, **Q43**); nella scheda del quartiere si mostra il numero di celle sotto l'obiettivo del 15% (§10.1, **Q42**).
