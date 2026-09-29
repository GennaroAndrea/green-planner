import { Dialog, DialogPanel, DialogTitle } from '@headlessui/react'
import type { ReactNode } from 'react'
import type { IndicatorKey, SensitivitySummary } from '../api/types'
import { DISCLAIMERS, DROPPED_REASON, INDICATOR_LABEL } from '../i18n/it'
import { INDICATOR_COLORS } from '../lib/colors'
import { date, fmt, month, pct } from '../lib/format'
import { useApp } from '../state'
import { Icon } from './ui'
import { ICONS } from '../lib/ui'

/** Data sources as used by the model (methodology §3). Licences from the CKAN catalogues and the EEA catalogue. */
const SOURCES: { key: string | null; name: string; owner: string; period: string; licence: string | null; url: string }[] = [
  { key: 'sentinel2_ndvi', name: 'Sentinel-2 L2A, vegetazione (NDVI) da satellite', owner: 'Copernicus (UE/ESA), tramite Microsoft Planetary Computer', period: 'giugno – agosto 2025', licence: 'dati Copernicus, liberi e aperti', url: 'https://planetarycomputer.microsoft.com/dataset/sentinel-2-l2a' },
  { key: 'green_areas', name: 'Aree verdi (solo contesto)', owner: 'Comune di Bari', period: '2024', licence: 'CC BY', url: 'https://dati.puglia.it/ckan/dataset/aree-verdi' },
  { key: 'traffic_flows', name: 'Centraline semaforiche, flussi di traffico giornalieri', owner: 'Comune di Bari', period: 'traffic', licence: 'CC BY', url: 'https://dati.puglia.it/v2/dataset/centraline-semaforiche-flussi-di-traffico-giornalieri' },
  { key: 'traffic_controllers', name: 'Centraline semaforiche, posizionamento', owner: 'Comune di Bari', period: 'traffic', licence: 'CC BY', url: 'https://dati.puglia.it/ckan/dataset/centraline-semaforiche-posizionamento-e-sensoristica-a-bordo' },
  { key: 'air_stations', name: 'Stazioni di monitoraggio della qualità dell’aria', owner: 'ARPA Puglia', period: '–', licence: 'CC BY 4.0', url: 'https://dati.puglia.it/ckan/dataset/stazioni-qualita-aria' },
  { key: null, name: 'Medie annuali NO₂, PM10, PM2.5 (Relazione annuale 2025, trascritte a mano)', owner: 'ARPA Puglia', period: '2025', licence: null, url: 'https://www.arpa.puglia.it/pagina2873_report-annuali-e-mensili-qualit-dellaria-rrqa.html' },
  { key: 'population', name: 'Popolazione residente per indirizzo e fascia d’età', owner: 'Comune di Bari', period: 'al 6 gennaio 2024', licence: 'CC BY-SA', url: 'https://dati.puglia.it/ckan/dataset/popolazione-residente1' },
  { key: 'sit', name: 'Numeri civici, quartieri, confine comunale', owner: 'SIT Comune di Bari (Civilario Unico Comunale)', period: '–', licence: 'CC BY', url: 'https://sit.egov.ba.it' },
  { key: 'land_use_2011', name: 'Uso del Suolo 2011 (superfici artificiali)', owner: 'Regione Puglia', period: '2011', licence: 'IODL 2.0', url: 'https://dati.puglia.it/ckan/dataset/uso-del-suolo-2011-uds' },
  { key: 'eprtr', name: 'E-PRTR, impianti industriali (solo contesto)', owner: 'Agenzia Europea dell’Ambiente', period: '2007–2024', licence: 'CC BY 4.0', url: 'https://www.eea.europa.eu/en/datahub' },
]

const LIMITS = [
  'Vegetazione da satellite a 10 m: alberi isolati, siepi e aiuole più piccoli di un pixel possono sfuggire; l’immagine è dell’estate 2025.',
  'Molte celle sono analizzate solo perché urbanizzate (zone industriali, porto, infrastrutture); l’Uso del Suolo è del 2011.',
  'Traffico noto solo vicino alle centraline: oltre ~910 m da ogni centralina il traffico è 0, cioè non misurato, non necessariamente assente.',
  'Inquinamento da sole 5 stazioni: il gradiente è molto liscio e i dati ARPA sono soggetti a validazione.',
  'Popolazione incompleta: circa il 17% dei residenti manca dai dati; il 7,7% è posizionato per quartiere e non per indirizzo; Torre a Mare è esclusa.',
  'Il traffico di un incrocio è la somma dei suoi sensori e può contare più volte gli stessi veicoli: è un indice relativo.',
  'Priorità relativa: le classi dicono dove intervenire prima, non se una zona è “buona” o “cattiva” in assoluto.',
  'Alberi come stima: frazione piantabile e chioma sono ipotesi, non misure.',
]

export default function Methodology() {
  const { meta, methodologyOpen, setMethodologyOpen, active, weights } = useApp()
  const traffic = meta.inputs.traffic
  const trafficPeriod = `${month(traffic.months_used[0])} – ${month(traffic.months_used[traffic.months_used.length - 1])}`
  const all = meta.indicators.all
  const total = active.reduce((a, k) => a + (weights[k] ?? 0), 0)
  const custom = active.some((k) => weights[k] !== meta.weights.configured_pp[k])
  const g250 = meta.grids['250']
  const veg = meta.inputs.vegetation
  const g500 = meta.grids['500']

  return (
    <Dialog open={methodologyOpen} onClose={() => setMethodologyOpen(false)} className="relative z-50">
      <div className="fixed inset-0 bg-black/40" aria-hidden />
      <div className="fixed inset-0 flex items-end justify-center sm:items-center sm:p-6">
        <DialogPanel className="flex max-h-[92dvh] w-full max-w-3xl flex-col rounded-t-2xl bg-surface-1 text-ink shadow-xl sm:rounded-2xl">
          <div className="flex items-center justify-between border-b border-line px-5 py-3">
            <DialogTitle className="font-serif text-xl font-medium">Metodologia e fonti</DialogTitle>
            <button
              type="button"
              onClick={() => setMethodologyOpen(false)}
              aria-label="Chiudi"
              className="-mr-2 flex size-11 items-center justify-center rounded-lg text-ink-2 hover:bg-surface-2"
            >
              <Icon d={ICONS.close} />
            </button>
          </div>
          <div className="space-y-7 overflow-y-auto px-5 py-5 text-[14px] leading-relaxed">
            <Section title="In sintesi">
              <p>
                Per ogni cella di una griglia regolare su Bari (250 m, oppure 500 m) calcoliamo quattro indicatori, li portiamo su una scala 0–100
                e li combiniamo con una somma pesata: l’<b>Indice di Priorità di Forestazione (IPF)</b>, da 0 a 100. Più è alto, più la zona è
                prioritaria per nuovi alberi e nuovo verde. L’obiettivo è mitigare l’esposizione a inquinamento e calore e aumentare il verde
                urbano.
              </p>
              <pre className="mt-3 overflow-x-auto rounded-lg bg-surface-2 px-3 py-2 font-mono text-[12px]">IPF = Σ pesoᵢ × punteggioᵢ   (Σ pesoᵢ = 1, punteggioᵢ da 0 a 100)</pre>
              <table className="mt-3 w-full text-[13px]">
                <thead>
                  <tr className="text-left text-ink-2">
                    <Th>Indicatore</Th>
                    <Th right>Peso configurato</Th>
                    <Th right>Peso effettivo</Th>
                    {custom && <Th right>Scenario attuale</Th>}
                  </tr>
                </thead>
                <tbody>
                  {all.map((k) => (
                    <tr key={k} className="border-t border-line">
                      <Td>
                        <span className="mr-1.5 inline-block size-2 rounded-sm" style={{ background: INDICATOR_COLORS[k] }} />
                        {INDICATOR_LABEL[k]}
                      </Td>
                      <Td right mono>{meta.weights.configured_pp[k]}</Td>
                      <Td right mono>
                        {meta.weights.effective[k] !== undefined ? pct(meta.weights.effective[k], 1) : '–'}
                      </Td>
                      {custom && <Td right mono>{active.includes(k) && total > 0 ? pct((weights[k] ?? 0) / total, 1) : '–'}</Td>}
                    </tr>
                  ))}
                </tbody>
              </table>
              {(Object.entries(meta.indicators.dropped) as [IndicatorKey, string][]).map(([k, r]) => (
                <p key={k} className="mt-2 text-[13px] text-ink-2">
                  {INDICATOR_LABEL[k]}: {DROPPED_REASON[r] ?? r}. Entro 10 km ci sono {meta.inputs.industry.facilities_in_radius} impianti E-PRTR, ma
                  solo {meta.inputs.industry.facilities_recent} hanno dichiarato dati negli ultimi 5 anni (ne servono almeno 3). Il suo peso è
                  ridistribuito in proporzione sugli altri.
                </p>
              ))}
            </Section>

            <Section title="Gli indicatori">
              <dl className="space-y-3">
                <Ind k="green_deficit">
                  Quota della superficie coperta da vegetazione vista dal satellite Sentinel-2: pixel di 10 m con NDVI (indice di verde) di almeno{' '}
                  {fmt(veg.ndvi_threshold, 2)} nella mediana delle {veg.scenes.length} immagini senza nuvole dell’estate 2025. Conta alberi, arbusti e
                  prati irrigati, pubblici e privati; l’erba secca d’estate no: resta la vegetazione che fa ombra quando serve. Il punteggio è 100 meno
                  la copertura normalizzata. Le aree verdi del Comune restano sulla mappa come contesto: molte (alberate stradali, cimiteri, campi
                  sportivi) viste dall’alto non sono vegetate.
                </Ind>
                <Ind k="pollution">
                  Media dei rapporti tra la media annuale 2025 e il limite UE 2030 (Direttiva 2024/2881: NO₂ 20, PM10 20, PM2.5 10 µg/m³) nelle{' '}
                  {meta.inputs.air.stations} stazioni ARPA di Bari, interpolata con IDW (potenza {meta.inputs.air.idw_power}).
                </Ind>
                <Ind k="traffic">
                  Veicoli giornalieri medi agli incroci con centralina ({traffic.controllers_with_data} con dati validi, {trafficPeriod}, agosto
                  escluso), diffusi alle celle vicine con una curva gaussiana (σ = {traffic.kernel_sigma_m} m) e azzerati oltre ~910 m.
                </Ind>
                <Ind k="population">
                  Residenti per km², dagli indirizzi collegati ai numeri civici ({pct(meta.inputs.population.match_rate, 1)} per indirizzo, il resto
                  distribuito sui civici del quartiere).
                </Ind>
              </dl>
              <p className="mt-3 text-[13px] text-ink-2">
                Normalizzazione 0–100 con min–max robusto: sotto il {meta.normalisation.lower_percentile}° percentile vale 0, sopra il{' '}
                {meta.normalisation.upper_percentile}° vale 100. Traffico e popolazione passano prima per una scala logaritmica, perché variano di
                diversi ordini di grandezza.
              </p>
            </Section>

            <Section title="Area di studio e quartieri">
              <p>
                L’analisi riguarda la città costruita, non le campagne: una cella è analizzata solo se ha almeno {fmt(meta.urban_mask.min_resident_density_km2)} residenti/km² oppure almeno il{' '}
                {pct(meta.urban_mask.min_artificial_share, 0)} di superficie urbanizzata (Uso del Suolo 2011). A 250 m sono analizzate{' '}
                {fmt(g250.cells_analysed)} celle su {fmt(g250.cells)}, a 500 m {fmt(g500.cells_analysed)} su {fmt(g500.cells)}.
              </p>
              <p className="mt-2">
                I valori dei {meta.zones.zones_analysed} quartieri analizzati sono medie delle loro celle da 250 m pesate sulla popolazione: la
                priorità riflette dove vivono le persone. Alberi e deficit di verde sono somme. {DISCLAIMERS.population_coverage}
              </p>
              <p className="mt-2">
                <b className="font-medium">Aree non residenziali.</b> {fmt(veg.nonresidential_cells)} celle analizzate a 250 m non hanno residenti
                (zone industriali, porto, infrastrutture). Restano sulla mappa con la loro priorità, ma i loro alberi sono contati a parte nei totali
                dei quartieri, e il simulatore distribuisce gli alberi solo tra le celle abitate.
              </p>
            </Section>

            <Section title="Classi di priorità">
              <p>
                Quattro classi (bassa, media, medio-alta, alta) con confini ai quartili dell’IPF: ogni classe contiene circa un quarto delle zone.
                Confini per le celle da 250 m: {g250.class_edges.map((e) => fmt(e, 1)).join(' / ')}; per i quartieri:{' '}
                {meta.zones.class_edges.map((e) => fmt(e, 1)).join(' / ')}. {DISCLAIMERS.relative_priority}
              </p>
            </Section>

            <Section title="Stima del numero di alberi">
              <pre className="overflow-x-auto rounded-lg bg-surface-2 px-3 py-2 font-mono text-[12px]">
                {`deficit     = max(0, ${pct(meta.trees.target_green_share, 0)} × area − vegetazione attuale)
piantabile  = deficit × ${pct(meta.trees.plantable_fraction, 0)}
alberi      = piantabile ÷ ${fmt(meta.trees.crown_area_m2)} m² di chioma`}
              </pre>
              <table className="mt-3 w-full text-[13px]">
                <tbody>
                  <Param label="Quota obiettivo di verde" value={pct(meta.trees.target_green_share, 0)} note="Dall’idea originale, applicata alla vegetazione vista da satellite. La regola 3-30-300 indica il 30% di chioma arborea." />
                  <Param label="Frazione piantabile del deficit" value={pct(meta.trees.plantable_fraction, 0)} note="Ipotesi: non esistono dati sullo spazio piantabile a Bari (edifici, strade, sottoservizi)." />
                  <Param label="Area di chioma per albero" value={`${fmt(meta.trees.crown_area_m2)} m²`} note="Albero di taglia media, chioma di circa 6 m." />
                </tbody>
              </table>
              <p className="mt-2 text-[13px] text-ink-2">
                I parametri non sono modificabili nell’app; per esplorare scenari c’è il simulatore (“Simula intervento” nella scheda di una zona).
                Il simulatore cambia solo l’indicatore del verde. {DISCLAIMERS.model_estimate}
              </p>
            </Section>

            <Section title="Robustezza rispetto ai pesi">
              <p>
                Per verificare che la classifica non sia un artefatto dei pesi scelti, ricalcoliamo tutto con {fmt(meta.sensitivity.runs)} vettori di
                pesi estratti intorno a quelli predefiniti (circa ±{meta.sensitivity.spread_pp} punti per peso). Una zona è “robusta” se resta nel top
                (10 quartieri, o 10% delle celle) in almeno l’{pct(meta.sensitivity.robust_threshold, 0)} degli scenari, oppure, se non è nel top,
                se mantiene la sua classe in almeno l’{pct(meta.sensitivity.robust_threshold, 0)} degli scenari.
              </p>
              <div className="mt-3 overflow-x-auto">
                <table className="w-full min-w-[440px] text-[13px]">
                  <thead>
                    <tr className="text-left text-ink-2">
                      <Th>Pesi predefiniti</Th>
                      <Th right>Correlazione media</Th>
                      <Th right>Top N mantenuto</Th>
                      <Th right>Zone robuste</Th>
                    </tr>
                  </thead>
                  <tbody>
                    <SensRow label={`Quartieri (${meta.zones.sensitivity.n})`} s={meta.zones.sensitivity} />
                    <SensRow label={`Celle 250 m (${fmt(g250.sensitivity.n)})`} s={g250.sensitivity} />
                    <SensRow label={`Celle 500 m (${fmt(g500.sensitivity.n)})`} s={g500.sensitivity} />
                  </tbody>
                </table>
              </div>
              <p className="mt-2 text-[13px] text-ink-2">
                Spostando un peso alla volta di ±{meta.sensitivity.one_at_a_time_delta_pp} punti, il top 10 dei quartieri mantiene in media{' '}
                {fmt(
                  meta.zones.sensitivity.one_at_a_time.reduce((a, r) => a + r.top_n_kept, 0) / meta.zones.sensitivity.one_at_a_time.length,
                  1,
                )}{' '}
                zone su 10. Con pesi personalizzati, il pulsante “Verifica robustezza” ripete la verifica intorno ai pesi scelti.
              </p>
            </Section>

            <Section title="Fonti dei dati">
              <ul className="space-y-2.5">
                {SOURCES.map((s) => {
                  const src = s.key ? meta.sources[s.key] : undefined
                  return (
                    <li key={s.name} className="text-[13px]">
                      <a href={s.url} target="_blank" rel="noreferrer" className="font-medium underline decoration-line-strong underline-offset-2 hover:decoration-ink">
                        {s.name}
                      </a>
                      <span className="block text-ink-2">
                        {s.owner} · {s.period === 'traffic' ? trafficPeriod : s.period}
                        {s.licence && ` · licenza ${s.licence}`}
                        {src?.downloaded_at && ` · scaricato il ${date(src.downloaded_at)}`}
                      </span>
                    </li>
                  )
                })}
              </ul>
              <p className="mt-3 text-[13px] text-ink-2">
                Mappa di base © OpenStreetMap contributors © CARTO. Dati elaborati il {date(meta.built_at)}.
              </p>
            </Section>

            <Section title="Limiti noti">
              <ul className="list-disc space-y-1.5 pl-5">
                {LIMITS.map((l) => (
                  <li key={l}>{l}</li>
                ))}
              </ul>
            </Section>

            <Section title="Avvertenze">
              <ul className="list-disc space-y-1.5 pl-5">
                {meta.disclaimers.map((k) => (
                  <li key={k}>{DISCLAIMERS[k] ?? k}</li>
                ))}
              </ul>
            </Section>
          </div>
        </DialogPanel>
      </div>
    </Dialog>
  )
}

function Section({ title, children }: { title: string; children: ReactNode }) {
  return (
    <section>
      <h3 className="mb-2 border-b-[1.5px] border-ink pb-1 font-serif text-lg font-medium">{title}</h3>
      {children}
    </section>
  )
}

function Ind({ k, children }: { k: IndicatorKey; children: ReactNode }) {
  return (
    <div>
      <dt className="flex items-center gap-1.5 font-medium">
        <span className="size-2.5 rounded-sm" style={{ background: INDICATOR_COLORS[k] }} />
        {INDICATOR_LABEL[k]}
      </dt>
      <dd className="mt-0.5 text-[13px] text-ink-2">{children}</dd>
    </div>
  )
}

function Th({ children, right }: { children: ReactNode; right?: boolean }) {
  return <th className={`py-1.5 pr-2 font-normal ${right ? 'text-right' : ''}`}>{children}</th>
}

function Td({ children, right, mono }: { children: ReactNode; right?: boolean; mono?: boolean }) {
  return <td className={`py-1.5 pr-2 ${right ? 'text-right' : ''} ${mono ? 'font-mono text-[12px]' : ''}`}>{children}</td>
}

function Param({ label, value, note }: { label: string; value: string; note: string }) {
  return (
    <tr className="border-t border-line align-top">
      <td className="py-1.5 pr-2">{label}</td>
      <td className="py-1.5 pr-2 text-right font-mono text-[12px] whitespace-nowrap">{value}</td>
      <td className="py-1.5 text-[12px] text-ink-2">{note}</td>
    </tr>
  )
}

function SensRow({ label, s }: { label: string; s: SensitivitySummary }) {
  return (
    <tr className="border-t border-line">
      <Td>{label}</Td>
      <Td right mono>{fmt(s.spearman_mean, 2)}</Td>
      <Td right mono>
        {fmt(s.top_n_overlap_mean, s.top_n >= 100 ? 0 : 2)} su {fmt(s.top_n)}
      </Td>
      <Td right mono>{pct(s.robust_share, 0)}</Td>
    </tr>
  )
}
