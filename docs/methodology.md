# Metodologia dell'Indice di Priorità di Forestazione (IPF)

> **Lingua**: questo file è scritto e mantenuto **in italiano** (eccezione alla regola "tutto in inglese tranne la UI", vedi `CLAUDE.md`).
> **Stato**: aggiornato alla Fase 3 (frontend), 29 settembre 2026. Build di riferimento: `uv run python -m pipeline build`.
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
| Deficit di verde | quanta poca vegetazione c'è nella cella (satellite Sentinel-2) | 33,3% |
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
| Aree verdi (D1) | Comune di Bari, SHP (593 poligoni) | 2024 | solo contesto: livello sulla mappa e valore descrittivo nella scheda (dalla **Q49**) |
| Sentinel-2 L2A (D11) | Copernicus (UE/ESA), tramite Microsoft Planetary Computer: mediana dell'NDVI di 19 immagini senza nuvole, pixel di 10 m | giugno – agosto 2025 | deficit di verde, stima alberi (**Q49**) |
| Flussi di traffico giornalieri (D2) | Comune di Bari, CSV mensili | set. 2025 – giu. 2026 | traffico |
| Posizione centraline semaforiche (D3) | Comune di Bari, JSON mensili | come D2 | traffico |
| Stazioni qualità dell'aria (D5) | ARPA Puglia, GeoJSON | – | posizione delle 5 stazioni di Bari |
| Medie annuali 2025 (NO₂, PM10, PM2.5) | ARPA Puglia, *Relazione annuale 2025*, trascritte a mano in `data/manual/arpa_annual_2025.csv` | 2025 | inquinamento |
| Popolazione residente (D6) | Comune di Bari, 4 CSV per fascia d'età, per indirizzo | al 6 gennaio 2024 | popolazione |
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

*Perché*: lo strumento confronta le zone della città costruita. Senza questa maschera, campagne e aree agricole entrerebbero nel confronto con i quartieri urbani. (All'inizio il motivo principale era che le aree verdi del Comune coprono solo il verde pubblico, e le campagne sarebbero risultate "senza verde"; dalla **Q49** il verde si misura da satellite, ma la maschera resta.)

- La soglia di 800/km² equivale a **50 residenti in una cella da 250 m** (valore deciso in **Q6**), espressa come densità (**Q22**). Così la stessa regola vale per le celle da 500 m (200 residenti) e per le celle di bordo ritagliate.
- **Torre a Mare è esclusa**: non compare nei dati di popolazione, quindi il suo punteggio di popolazione sarebbe falsamente zero (**Q4a**).
- Risultato a 250 m: **1.127 celle analizzate** su 2.006, con il 99,5% dei residenti. Delle 1.127 celle, 449 superano entrambe le soglie, 6 solo quella di popolazione, **672 solo quella di superficie artificiale** (zone industriali, porto, infrastrutture, servizi: il 45% di queste ha zero residenti).
- **Celle non residenziali** (**Q50**): 302 celle analizzate a 250 m (30 a 500 m) non hanno residenti (conteggio arrotondato, come appare nella scheda). Restano analizzate e hanno la loro classe di priorità, ma i loro alberi sono contati a parte nei totali dei quartieri (§9, §10) e il simulatore non vi pianta alberi (§10.1).

## 5. Indicatori

### 5.1 Deficit di verde
- **Valore grezzo** (**Q49**): quota della cella coperta da **vegetazione vista da satellite** (`veg_share`, 0–1).
  - Fonte: Sentinel-2 L2A (Copernicus), pixel di 10 m. Per ogni pixel si calcola l'NDVI (indice di verde: circa 0 per cemento e acqua, oltre 0,4 per vegetazione rigogliosa) in ciascuna delle **19 immagini senza nuvole** (copertura < 1%) di **giugno–agosto 2025**, escludendo nuvole, ombre e acqua (classificazione SCL), e se ne prende la **mediana**.
  - Un pixel è vegetato se la mediana è almeno **0,30**. La vegetazione di una cella è il numero di pixel vegetati il cui centro cade nella cella, per 100 m².
  - Il composito è scaricato una volta da `pipeline download` (Microsoft Planetary Computer, senza account) e salvato in `data/raw/`, con l'elenco delle immagini nel manifest. Il 99,97% dei pixel delle celle analizzate ha un valore valido.
- **Punteggio**: `deficit = 100 − punteggio normalizzato della copertura`. Più vegetazione c'è, più il punteggio è basso.
- *Perché il satellite (Q49)*: con le sole aree verdi del Comune il 49% delle celle analizzate non aveva alcun verde e otteneva deficit 100: l'indicatore funzionava quasi come un sì/no. Con la vegetazione da satellite le celle con deficit 100 sono 117 (10%). Inoltre i poligoni del Comune spesso non sono vegetati visti dall'alto: nelle alberate stradali (il poligono include la strada) l'NDVI mediano è 0,11 e solo il 5% dei pixel supera 0,30; nei cimiteri 0,16 (3%); nei campi sportivi 0,13 (7%); in Lama Balice 0,26 (36%). Le due misure sono di fatto indipendenti (Spearman 0,00 sulle celle analizzate).
- *Perché l'estate e la soglia 0,30*: in Puglia erba e colture sono verdi in primavera e secche d'estate. La mediana estiva conta la vegetazione che resta verde quando fa caldo (alberi, arbusti, prati irrigati), cioè quella che fa ombra quando serve. Con soglia 0,40 il 33% delle celle risulterebbe senza vegetazione (l'indicatore tornerebbe a saturare); usando il massimo dell'anno le aree agricole ai margini sembrerebbero molto verdi.
- Le aree verdi del Comune restano sulla mappa come **livello di contesto** e la loro quota compare nella scheda come valore descrittivo.

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
| Copertura di vegetazione | 0% (quindi deficit 100) | ≥ 25,6% (quindi deficit 0) |
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
Quattro classi (**Q11**), **bassa / media / medio-alta / alta**, colorate dal giallo chiaro al rosso scuro (`#FAC775`, `#F0997B`, `#D85A30`, `#993C1D`, **Q46**), con confini ai **quartili** dell'IPF delle celle analizzate. Per i quartieri si usano i quartili dei 16 quartieri analizzati.

- Confini a 250 m: 46,4 / 60,2 / 75,6.
- Confini per i quartieri: 70,3 / 79,3 / 87,5.
- *Perché i quartili*: lo scopo dello strumento è ordinare le zone per decidere dove intervenire prima, e i quartili danno sempre una mappa leggibile. Con soglie fisse (25/50/75) le celle rosse potrebbero essere pochissime o nessuna.
- La UI deve dire "priorità relativa rispetto al resto della città".

## 9. Aggregazione per quartiere
Per ogni quartiere si usano le sue celle analizzate della griglia da 250 m:

- i **punteggi** sono la **media pesata sulla popolazione** dei punteggi delle celle (FR-09);
- l'IPF del quartiere è la media pesata sulla popolazione degli IPF delle celle, e resta lineare nei pesi, quindi il backend può ricalcolarlo direttamente;
- residenti, verde pubblico e vegetazione sono **somme** su tutte le celle analizzate; densità e quote si riferiscono alla superficie delle celle analizzate;
- deficit di verde, superficie piantabile e alberi sono **somme sulle sole celle abitate**; gli alberi delle celle non residenziali sono riportati a parte (`trees_new_nonres`, **Q50**). Le celle senza residenti hanno comunque peso 0 nelle medie pesate sulla popolazione, quindi non influiscono sui punteggi del quartiere.

*Perché pesare sulla popolazione*: la priorità di un quartiere deve riflettere dove vivono le persone. Una cella industriale senza residenti non deve pesare quanto un isolato densamente abitato.

## 10. Stima del numero di alberi
```
verde_obiettivo_m2   = quota_obiettivo × area_cella
deficit_m2           = max(0, verde_obiettivo_m2 − vegetazione_m2)       (vegetazione da satellite, Q49)
piantabile_m2        = deficit_m2 × frazione_piantabile
nuovi_alberi         = parte_intera(piantabile_m2 / area_chioma)
```

| Parametro (**Q12**) | Valore | Motivazione |
|---|---|---|
| Quota obiettivo di verde | **15%** | Dall'idea originale; dalla **Q49** si applica alla vegetazione vista da satellite. La pagina metodologica cita anche la regola 3-30-300 (30% di chioma arborea, Konijnendijk 2021). |
| Frazione piantabile del deficit | **25%** | Pura ipotesi: non esistono dati sullo spazio piantabile a Bari (edifici, strade, sottoservizi). Mostrata nella pagina metodologica, non modificabile nell'app (**Q43**): per esplorare scenari c'è il simulatore (§10.1). |
| Area di chioma per albero | **30 m²** | Albero di taglia media, chioma di circa 6 m. |

- Esempio: una cella intera da 250 m (62.500 m²) senza vegetazione ha un obiettivo di 9.375 m² e 2.344 m² piantabili, quindi **78 alberi**.
- Totale per le celle analizzate (250 m): **45.278 alberi**, di cui 12.345 in celle non residenziali. I totali dei quartieri contano solo le celle abitate: 32.933 alberi (**Q50**).
- È una **stima di modello**, e la UI lo dichiara sempre.

### 10.1 Simulatore ("cosa succede se pianto N alberi?")
Per una cella o un quartiere analizzato, il simulatore stima l'effetto di N nuovi alberi (**Q37**):

```
vegetazione_dopo_m2 = vegetazione_m2 + N × area_chioma          (30 m² per albero)
quota_verde_dopo    = vegetazione_dopo_m2 / area
punteggio_deficit  = 100 − minmax(quota_verde_dopo)              (stessi limiti p5–p95 del calcolo, §6)
IPF_dopo           = IPF_prima + peso_verde × (punteggio_deficit_dopo − punteggio_deficit_prima)
```

- **Cambia solo l'indicatore del verde.** Inquinamento, traffico e popolazione restano invariati: è una simulazione semplificata e la UI lo dichiara.
- **Classe e posizione** del risultato sono calcolate rispetto al resto della città, che resta com'è (stessi confini di classe dello scenario corrente).
- **Quartieri**: gli N alberi sono ripartiti tra le celle **abitate** analizzate da 250 m del quartiere (**Q50**) **in proporzione al loro deficit di verde** (in proporzione all'area se nessuna cella ha deficit). Poi il punteggio del quartiere si ricalcola come media pesata sulla popolazione (§9).
- Il simulatore mostra due riferimenti:
  - la **stima del modello** (`nuovi_alberi`, §10), che considera solo la quota piantabile (25%) del deficit;
  - gli **alberi necessari per il 15%**, cioè `deficit_m2 / area_chioma`, arrotondato per eccesso.

  Il secondo numero è di solito circa 4 volte il primo: raggiungere l'obiettivo richiederebbe più spazio di quello stimato come piantabile.
- *Nota sui quartieri*: il deficit è la somma dei deficit delle singole celle. Un quartiere può quindi avere una quota media di verde superiore al 15% e comunque un deficit, se il verde è concentrato in poche celle. Con la vegetazione da satellite nessun quartiere supera in media il 15% (il più alto è Carrassi, 11,4%).
- **Crescita nel tempo** (**Q37b**): il simulatore ha anche un cursore "Anni dalla piantumazione". La chioma di un albero appena piantato cresce **linearmente fino alla maturità** (15 anni, `trees.growth_years_maturity`): all'anno *t* il contributo di ogni albero è `area_chioma × min(1, t/15)`. Per le celle il simulatore riporta inoltre in quanti anni si raggiunge il 15% di vegetazione (`anni_al_bersaglio`) e in quanti anni la classe di priorità scende (`anni_al_cambio_classe`), se succede entro la maturità. È un modello semplificato (media tra specie, niente mortalità né potatura): la UI lo presenta come stima del modello.
- *Nella scheda del quartiere* (**Q42**) non si mostra "quota attuale → 15%", ma la quota media e il numero di celle sotto l'obiettivo, contando solo le celle abitate, ad esempio *"Vegetazione media 3,0% · 25 celle abitate su 27 sotto il 15%"* (Libertà; Murat 21 su 22, San Paolo 49 su 56). Nella scheda della cella resta "quota attuale → 15%".
- *Esempio* (Libertà, pesi predefiniti):
  - IPF 91,5, classe alta, 4° posto;
  - con i 1.678 alberi stimati: IPF 87,1, classe medio-alta, 4° posto;
  - con i 6.763 alberi necessari per il 15% in ogni cella abitata: IPF 73,9, classe media, 11° posto.

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
| Quartieri (16) | 1,00 | 9,62 su 10 | 15 su 16 (90% del top 10) |
| Celle 250 m (1.127) | 0,99 | 108 su 113 | 75% (90% del top 10%) |
| Celle 500 m (315) | 0,99 | 31 su 32 | 74% (91% del top 10%) |

- Nel test uno alla volta il top 10 dei quartieri cambia al massimo di un quartiere (9 su 10 mantenuti in 4 test su 8).
- L'unico quartiere "sensibile" è San Paolo, al 10° posto, sul confine del top 10 (tra il 9° e l'11° posto).
- Nelle celle, l'instabilità si concentra ai confini tra le classi, com'è naturale.

## 13. Risultati principali (quartieri, pesi predefiniti)

| Pos. | Quartiere | IPF | Classe | Intervallo posizione | Robusto | Vegetazione | Nuovi alberi (celle abitate) | + aree non residenziali |
|---|---|---|---|---|---|---|---|---|
| 1 | Madonnella | 97,0 | alta | 1–1 | sì | 1,9% | 508 | 0 |
| 2 | Murat | 95,9 | alta | 2–2 | sì | 2,3% | 1.397 | 74 |
| 3 | San Nicola | 95,2 | alta | 3–3 | sì | 2,1% | 400 | 363 |
| 4 | Libertà | 91,5 | alta | 4–4 | sì | 3,0% | 1.678 | 113 |
| 5 | San Pasquale | 86,2 | medio-alta | 5–5 | sì | 9,5% | 1.952 | 196 |
| 6 | Japigia | 85,5 | medio-alta | 6–6 | sì | 6,2% | 4.639 | 807 |
| 7 | Carrassi | 83,9 | medio-alta | 7–7 | sì | 11,4% | 1.361 | 156 |
| 8 | Picone | 82,1 | medio-alta | 8–8 | sì | 10,9% | 4.005 | 705 |
| 9 | Marconi – San Girolamo – Fesca | 76,5 | media | 9–10 | sì | 8,3% | 2.605 | 451 |
| 10 | San Paolo | 74,8 | media | 9–11 | no | 7,5% | 2.983 | 1.089 |
| 11 | Stanic | 74,5 | media | 10–11 | sì | 9,1% | 4.666 | 2.138 |
| 12 | Santo Spirito | 71,3 | media | 12–12 | sì | 9,0% | 1.714 | 504 |
| 13 | Palese – Macchie | 67,2 | bassa | 13–13 | sì | 6,3% | 1.776 | 3.940 |
| 14 | Ceglie del Campo | 60,3 | bassa | 14–15 | sì | 7,2% | 807 | 593 |
| 15 | Carbonara | 57,7 | bassa | 15–16 | sì | 11,2% | 2.157 | 1.071 |
| 16 | Loseto | 55,5 | bassa | 14–16 | sì | 6,7% | 285 | 145 |
| – | Torre a Mare | – | non analizzato | – | – | – | – | – |

**Lettura**:
- In testa ci sono i quartieri centrali densi, con pochissima vegetazione (2–3% della superficie).
- In fondo ci sono le frazioni esterne, con inquinamento e traffico misurati più bassi e più vegetazione.
- L'area industriale ASI (Stanic, San Paolo) è analizzata per la sua superficie artificiale, ma ha punteggio di popolazione vicino a 0; molti dei suoi alberi finiscono nella colonna delle aree non residenziali (2.138 a Stanic, 3.940 a Palese – Macchie).
- Gli alberi nelle aree abitate sono più numerosi nei quartieri grandi con poca vegetazione (Stanic, Japigia, Picone). La priorità più alta è invece nei quartieri piccoli e densi del centro.

## 14. Limiti noti
1. **Vegetazione da satellite a 10 m** (**Q49**). Alberi isolati, siepi e aiuole più piccoli di un pixel possono sfuggire, e un pixel misto (metà chioma, metà asfalto) può restare sotto la soglia. È la situazione dell'estate 2025; la soglia NDVI 0,30 è una scelta dichiarata (§5.1).
2. **Area di studio dominata dalle superfici artificiali.** 672 delle 1.127 celle sono analizzate solo per la soglia del 30% di superficie artificiale: zone industriali, porto, infrastrutture. L'Uso del Suolo è del 2011. Le 302 celle senza residenti restano in classifica (di solito in basso), ma i loro alberi sono contati a parte (**Q50**).
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
| Vegetazione da satellite | `sources.sentinel2_ndvi`, `vegetation.ndvi_threshold` | `pipeline/satellite.py` (download del composito e conteggio per cella) |

## 16. Storico delle modifiche
- **2026-09-29**: prima versione, alla fine della Fase 1. Include le decisioni Q20–Q29 prese durante l'implementazione.
- **2026-09-29** (Fase 2, backend): regole dei pesi personalizzati (§7, **Q30**) e verifica di robustezza con pesi pari a 0 o troppo concentrati (§12, **Q31**). Nessun cambiamento ai risultati con i pesi predefiniti.
- **2026-09-29** (Fase 3.0, confronto con il prototipo UI): pesi personalizzati normalizzati sul totale (§7, **Q36**); nuovo simulatore alberi (§10.1, **Q37**). Confermate le 4 classi a quartili (**Q34**) e l'esclusione dell'industria dall'indice (**Q35**). Nessun cambiamento ai risultati con i pesi predefiniti.
- **2026-09-29** (Fase 3.0): la frazione piantabile non è modificabile nell'app (§10, **Q43**); nella scheda del quartiere si mostra il numero di celle sotto l'obiettivo del 15% (§10.1, **Q42**).
- **2026-09-29** (Fase 3, frontend): colori delle classi presi dalla palette del prototipo (§8, **Q46**; prima "verde / giallo / arancione / rosso"). Nessun cambiamento al modello né ai risultati.
- **2026-09-29** (Fase 3): indicata la data di riferimento della popolazione (6 gennaio 2024, dal portale open data del Comune di Bari) nella tabella dei dati (§3).
- **2026-09-29** (Fase 3, prima della demo, **Q33** risolta): il deficit di verde e la stima degli alberi usano la **vegetazione da satellite** Sentinel-2 (mediana NDVI estate 2025, soglia 0,30) al posto delle aree verdi del Comune, che restano come contesto (§3, §5.1, §10, **Q49**). Le **celle senza residenti** restano analizzate ma i loro alberi sono contati a parte e il simulatore non vi pianta alberi (§4.4, §9, §10.1, **Q50**). Cambiano punteggi, classi, classifica e alberi: risultati aggiornati in §6, §8, §10, §12, §13.
