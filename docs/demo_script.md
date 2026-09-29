# Copione della demo (~3 minuti)

> Documento in italiano per scelta (Q52): è un supporto per chi presenta a una giuria di Bari. I numeri sono quelli dei pesi predefiniti, verificati sull'API il 2026-09-29 (dati `built_at` 2026-09-29T20:33). Se si ricostruiscono i dati (`pipeline build`), vanno ricontrollati.

## Prima della demo (10 minuti prima)

1. `make demo` sul portatile (dati → build → backend su :8080 → ngrok). Attendere la riga `started tunnel`.
2. Aprire **https://green-planner.ngrok.io** sul portatile **e** su un telefono (rete mobile, non il Wi-Fi della sala).
3. **Riserva Render**: aprire l'URL Render una volta per svegliarlo (piano gratuito: si addormenta dopo 15 minuti senza traffico e impiega circa un minuto a ripartire). Lasciare la scheda aperta.
4. Ricaricare la pagina sul portatile: vista **Quartieri**, scheda **Priorità**, nessuna zona selezionata, pesi predefiniti.
5. Tema chiaro per il proiettore (pulsante luna/sole in alto a destra).

## Copione

### 0:00 – Il problema (20 s)
> "Bari deve piantare alberi, ma *dove* prima? Abbiamo combinato gli open data di Comune, ARPA, SIT e il satellite Copernicus in un unico indice, l'**IPF, Indice di Priorità di Forestazione**, da 0 a 100."

Mostrare la mappa dei quartieri: i quattro in rosso scuro sono in classe **alta**.

### 0:20 – La zona più prioritaria: Madonnella (40 s)
Toccare **Madonnella** sulla mappa (o dalla lista "Le 5 zone più prioritarie").
- **97,0 / 100**, 1° su 16 quartieri, **"sempre 1° posto variando i pesi di ±5 punti"**: la priorità è robusta.
- "Perché questa zona è prioritaria?": carenza di vegetazione (93/100), inquinamento (100/100), densità (99/100).
- Solo l'**1,9%** della superficie è vegetata (satellite, estate 2025). Circa **508 alberi** stimati, 9 celle abitate su 9 sotto il 15% di vegetazione.

> "Ogni numero ha una spiegazione in parole: niente scatola nera."

### 1:00 – Il caso che racconta perché serve il satellite: Libertà (50 s)
Toccare **Libertà**: **91,5**, 4° su 16, classe alta, sempre 4°.
- Principali fattori: carenza di vegetazione (94/100), densità (~20.200 ab./km²), traffico (92/100).
- Il Comune censisce il **20,9%** di verde pubblico, ma dal satellite la superficie vegetata è solo il **3,0%**: molte aree "verdi" in mappa (viali alberati, campi sportivi) dall'alto non sono vegetate.
- Premere **"Simula intervento"**: con i **1.678 alberi** stimati l'indice scende a **87,1** (classe medio-alta). Portare il cursore al **15%** (6.763 alberi): **73,9**, classe media, 11° posto.

> "Lo strumento non dice solo dove, ma anche quanto intervento serve per cambiare la situazione."

### 1:50 – Il contrasto: Loseto (20 s)
Toccare **Loseto**: **55,5**, 16° su 16, classe bassa. Pochi residenti (~290 ab./km²), inquinamento basso (32/100), più vegetazione (6,7%).

### 2:10 – Pesi e robustezza (30 s)
Scheda **"Pesi e classifica"**. Portare **Carenza verde** a 60 e Inquinamento e Traffico a 10: la mappa si aggiorna, i primi quattro restano Madonnella, San Nicola, Murat e Libertà. Premere **"Verifica robustezza"**.
> "I pesi sono una scelta politica, e la giuria può cambiarli. Ma la classifica è stabile: con 1.000 combinazioni di pesi la correlazione media è 0,997, e 15 zone su 16 sono robuste."

Premere **"Ripristina"**.

### 2:40 – Chiusura (20 s)
Passare a **Celle 250 m**: la stessa analisi su 1.127 celle, per decidere via per via. Aprire **"Metodologia e fonti"**: fonti, licenze e limiti sono tutti dichiarati.
> "In totale stimiamo circa **33.000 alberi** nelle celle abitate dei quartieri, più 12.345 in aree non residenziali. Il metodo è configurabile per altri comuni: Copertino e Lecce sono i prossimi."

## Se qualcosa va storto
- **ngrok non risponde**: usare l'URL Render (già svegliato). Stessi dati (snapshot `deploy/data/`).
- **Niente internet in sala**: `make demo-local` e proiettare http://localhost:8080. Serve comunque internet per lo sfondo della mappa (CARTO); senza, i quartieri restano visibili su fondo vuoto.

## Domande probabili della giuria

| Domanda | Risposta breve |
|---|---|
| Perché questi pesi? | Carenza verde 33%, gli altri 22% ciascuno (industria esclusa per ora). Sono modificabili dal pannello, e la verifica di robustezza mostra che la classifica cambia poco (Spearman medio 0,997). |
| Perché non usate il verde pubblico del Comune? | Dal satellite molte aree censite non sono vegetate (viali alberati: NDVI mediano 0,11). La correlazione tra verde pubblico e vegetazione misurata è 0,00. Il verde pubblico resta come livello di contesto. |
| Come stimate gli alberi? | Mancanza rispetto al 15% di vegetazione × 25% di superficie piantabile ÷ 30 m² di chioma per albero. È una stima di ordine di grandezza, i parametri sono ipotesi dichiarate. |
| L'inquinamento con 5 stazioni? | Il gradiente è liscio, e i dati ARPA sono soggetti a validazione. Per questo l'inquinamento pesa meno della carenza di verde. |
| Il traffico? | 66 incroci con centraline. Oltre ~910 m da ogni centralina il traffico è *non misurato* (31% delle celle), non assente. |
| E l'industria? | Mostriamo gli impianti E-PRTR nella scheda *Industria*, ma non entrano nell'indice: il metodo di diffusione spaziale non è ancora definito, e non si vuole suggerire un nesso causale. |
| Le celle senza residenti? | Restano in mappa e in classifica (area non residenziale), ma i loro alberi sono contati a parte. |
| Si può usare in un altro comune? | Tutti i parametri e le fonti sono in un file di configurazione per comune (`config/bari.yaml`). I selettori Comune/Anno sono già nell'interfaccia. |
