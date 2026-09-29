import type { FeatureCollection } from 'geojson'
import { setWorkerUrl, type ExpressionSpecification, type FilterSpecification } from 'maplibre-gl'
import 'maplibre-gl/dist/maplibre-gl.css'
// maplibre-gl 6 looks for its worker next to its own module file, which bundling breaks:
// let Vite bundle the worker (with its shared chunk) and pass its URL explicitly.
import maplibreWorkerUrl from 'maplibre-gl/dist/maplibre-gl-worker.mjs?worker&url'
import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import MapGL, {
  Layer,
  NavigationControl,
  Popup,
  Source,
  type MapLayerMouseEvent,
  type MapRef,
} from 'react-map-gl/maplibre'
import { api } from '../api/client'
import type { MapCollection } from '../api/types'
import { CLASS_COLORS, GREEN, INDICATOR_COLORS, SCORE_RAMP } from '../lib/colors'
import { useFetch } from '../lib/hooks'
import { useApp } from '../state'
import { bboxOf } from '../lib/geo'
import { PopupContent, type PopupInfo } from './MapPopup'

setWorkerUrl(maplibreWorkerUrl)

const STYLE_LIGHT = 'https://basemaps.cartocdn.com/gl/positron-gl-style/style.json'
const STYLE_DARK = 'https://basemaps.cartocdn.com/gl/dark-matter-gl-style/style.json'
const INITIAL_VIEW = { longitude: 16.86, latitude: 41.1, zoom: 11 }

const FILL = 'choropleth-fill'
const GREEN_LAYER = 'layer-green-fill'

interface Props {
  dark: boolean
  data: MapCollection | undefined
  /** Map area covered by overlays (px): controls on top, the bottom sheet (peek / open) on phones. */
  insets: { top: number; bottom: number; bottomOpen: number }
}

export default function MapView({ dark, data: fetched, insets }: Props) {
  const app = useApp()
  const { level, tab, layers, selection, select, selectAndFly, flyRequest } = app
  // Right after a zone ↔ cell switch the previous level's data is still loaded: don't draw it.
  const data = fetched && (fetched.features[0]?.properties.cell_id === undefined) === (level === 'zone') ? fetched : undefined
  const mapRef = useRef<MapRef>(null)
  const [beforeId, setBeforeId] = useState<string | undefined>()
  const [popup, setPopup] = useState<PopupInfo | null>(null)
  const [cursor, setCursor] = useState<string>('')
  const hovered = useRef<string | number | null>(null)

  const idProp: 'zone_id' | 'cell_id' = level === 'zone' ? 'zone_id' : 'cell_id'
  const noData = dark ? '#4a4640' : '#cfcac0'
  const edge = dark ? '#141311' : '#ffffff'
  const ink = dark ? '#eeebe4' : '#25221d'

  // Context layers are loaded once, on first use.
  const showIndustry = layers.has('industry') || tab === 'industry'
  const green = useFetch<FeatureCollection>(layers.has('green') ? api.layer('green') : null)
  const traffic = useFetch<FeatureCollection>(layers.has('traffic') ? api.layer('traffic') : null)
  const air = useFetch<FeatureCollection>(layers.has('air') ? api.layer('air') : null)
  const industry = useFetch<FeatureCollection>(showIndustry ? api.layer('industry') : null)

  const fillColor = useMemo<ExpressionSpecification>(() => {
    if (tab === 'priority' || tab === 'industry') {
      return ['match', ['get', 'ipf_class'], 1, CLASS_COLORS[1], 2, CLASS_COLORS[2], 3, CLASS_COLORS[3], 4, CLASS_COLORS[4], noData]
    }
    const prop = `score_${tab}`
    return [
      'case',
      ['==', ['get', prop], null],
      noData,
      ['interpolate', ['linear'], ['get', prop], ...SCORE_RAMP.flat()] as ExpressionSpecification,
    ]
  }, [tab, noData])

  const selectedFilter = useMemo<FilterSpecification>(
    () => ['==', ['to-string', ['get', idProp]], selection && selection.level === level ? selection.id : '__none__'],
    [idProp, selection, level],
  )

  const onStyle = useCallback(() => {
    const map = mapRef.current?.getMap()
    if (!map) return
    // Draw the data above roads and buildings, below the labels: the first symbol layer after the
    // last non-symbol one (CARTO puts a water label early, under the roads).
    const layers = map.getStyle().layers ?? []
    const lastShape = layers.findLastIndex((l) => l.type !== 'symbol')
    setBeforeId(layers.slice(lastShape + 1).find((l) => l.type === 'symbol')?.id)
  }, [])

  // Fly to the selection when asked (ranking click), and fit Bari on first data load.
  const fitted = useRef(false)
  useEffect(() => {
    const map = mapRef.current
    if (!map || !data) return
    if (!fitted.current) {
      fitted.current = true
      const pad = { top: insets.top + 10, left: 20, right: 20, bottom: insets.bottom + 20 }
      map.fitBounds(bboxOf(data.features.filter((f) => f.properties.analysed)), { padding: pad, duration: 0 })
    }
  }, [data, insets])

  const flown = useRef(0)
  useEffect(() => {
    const map = mapRef.current
    if (!map || !data || !flyRequest || flyRequest.n === flown.current || flyRequest.level !== level) return
    const f = data.features.find((ft) => String(ft.properties[idProp]) === flyRequest.id)
    if (!f) return // the map data for this level is still loading: retry when it arrives
    flown.current = flyRequest.n
    const pad = { top: insets.top + 20, left: 40, right: 40, bottom: insets.bottomOpen + 20 }
    const bounds = bboxOf([f])
    if (flyRequest.zoom) {
      map.fitBounds(bounds, { padding: pad, maxZoom: level === 'zone' ? 13.5 : 15, duration: 700 })
    } else {
      const center: [number, number] = [(bounds[0][0] + bounds[1][0]) / 2, (bounds[0][1] + bounds[1][1]) / 2]
      map.easeTo({ center, padding: pad, duration: 500 })
    }
  }, [flyRequest, data, level, idProp, insets])

  const setHover = (id: string | number | null) => {
    const map = mapRef.current?.getMap()
    if (!map || !map.getSource('choropleth')) return
    if (hovered.current === id) return
    if (hovered.current !== null) map.setFeatureState({ source: 'choropleth', id: hovered.current }, { hover: false })
    hovered.current = id
    if (id !== null) map.setFeatureState({ source: 'choropleth', id }, { hover: true })
  }

  const onClick = (e: MapLayerMouseEvent) => {
    const f = e.features?.[0]
    if (!f) {
      setPopup(null)
      return
    }
    if (f.layer.id === FILL) {
      const p = f.properties as Record<string, unknown>
      if (p.analysed === true) {
        setPopup(null)
        const s = { level, id: String(p[idProp]) }
        // On phones the opening sheet would hide the tapped item: pan it into view.
        if (insets.bottomOpen > insets.bottom) selectAndFly(s, false)
        else select(s)
      } else {
        setPopup({ kind: 'not_analysed', lng: e.lngLat.lng, lat: e.lngLat.lat, props: p, level })
      }
      return
    }
    const kind = f.layer.id.replace('layer-', '').replace('-fill', '') as PopupInfo['kind']
    setPopup({ kind, lng: e.lngLat.lng, lat: e.lngLat.lat, props: f.properties as Record<string, unknown>, level })
  }

  const interactive = [FILL, ...(layers.has('green') ? [GREEN_LAYER] : [])]
  if (layers.has('traffic')) interactive.push('layer-traffic')
  if (layers.has('air')) interactive.push('layer-air')
  if (showIndustry) interactive.push('layer-industry')

  return (
    <MapGL
      ref={mapRef}
      initialViewState={INITIAL_VIEW}
      mapStyle={dark ? STYLE_DARK : STYLE_LIGHT}
      onLoad={onStyle}
      onStyleData={onStyle}
      interactiveLayerIds={interactive}
      onClick={onClick}
      onMouseMove={(e) => {
        const f = e.features?.[0]
        setCursor(f ? 'pointer' : '')
        setHover(f && f.layer.id === FILL ? (f.id ?? null) : null)
      }}
      onMouseLeave={() => {
        setCursor('')
        setHover(null)
      }}
      cursor={cursor}
      dragRotate={false}
      touchPitch={false}
      pitchWithRotate={false}
      maxZoom={17}
      minZoom={9}
      attributionControl={{ compact: true }}
      style={{ width: '100%', height: '100%' }}
    >
      <NavigationControl position="bottom-right" showCompass={false} />

      {data && (
        // Keyed by level: react-map-gl doesn't update `promoteId` on an existing source.
        <Source key={level} id="choropleth" type="geojson" data={data} promoteId={idProp}>
          <Layer
            id={FILL}
            type="fill"
            beforeId={beforeId}
            paint={{
              'fill-color': fillColor,
              'fill-opacity': ['case', ['get', 'analysed'], level === 'zone' ? 0.72 : 0.78, 0.3],
            }}
          />
          <Layer
            id="choropleth-line"
            type="line"
            beforeId={beforeId}
            paint={{
              'line-color': ['case', ['boolean', ['feature-state', 'hover'], false], ink, edge],
              // Zoom must be the top-level input: the hover case goes inside each stop.
              'line-width': [
                'interpolate',
                ['linear'],
                ['zoom'],
                11,
                ['case', ['boolean', ['feature-state', 'hover'], false], 2, level === 'zone' ? 1.2 : 0.2],
                14,
                ['case', ['boolean', ['feature-state', 'hover'], false], 2.5, level === 'zone' ? 1.5 : 0.8],
              ],
              'line-opacity': level === 'zone' ? 0.9 : 0.7,
            }}
          />
          <Layer
            id="choropleth-selected"
            type="line"
            filter={selectedFilter}
            paint={{ 'line-color': ink, 'line-width': 3 }}
          />
        </Source>
      )}

      {layers.has('green') && green.data && (
        <Source id="green" type="geojson" data={green.data}>
          <Layer id={GREEN_LAYER} type="fill" paint={{ 'fill-color': GREEN, 'fill-opacity': 0.6 }} />
          <Layer
            id="layer-green-line"
            type="line"
            paint={{ 'line-color': dark ? '#97C459' : '#3B6D11', 'line-width': 0.6 }}
          />
        </Source>
      )}

      {layers.has('traffic') && traffic.data && (
        <Source id="traffic" type="geojson" data={traffic.data}>
          <Layer
            id="layer-traffic"
            type="circle"
            paint={{
              'circle-radius': [
                'case',
                ['to-boolean', ['get', 'has_data']],
                ['interpolate', ['linear'], ['sqrt', ['coalesce', ['get', 'vehicles_day'], 0]], 0, 3, 100, 6, 200, 11],
                4,
              ],
              'circle-color': ['case', ['to-boolean', ['get', 'has_data']], INDICATOR_COLORS.traffic, 'rgba(0,0,0,0)'],
              'circle-stroke-color': dark ? '#eeebe4' : '#25221d',
              'circle-stroke-width': 1,
              'circle-opacity': 0.85,
            }}
          />
        </Source>
      )}

      {layers.has('air') && air.data && (
        <Source id="air" type="geojson" data={air.data}>
          <Layer
            id="layer-air"
            type="circle"
            paint={{
              'circle-radius': 9,
              'circle-color': INDICATOR_COLORS.pollution,
              'circle-stroke-color': '#ffffff',
              'circle-stroke-width': 2,
            }}
          />
        </Source>
      )}

      {showIndustry && industry.data && (
        <Source id="industry" type="geojson" data={industry.data}>
          <Layer
            id="layer-industry"
            type="circle"
            paint={{
              'circle-radius': 9,
              'circle-color': ['case', ['to-boolean', ['get', 'recent']], '#57534e', 'rgba(0,0,0,0)'],
              'circle-stroke-color': dark ? '#eeebe4' : '#57534e',
              'circle-stroke-width': 2.5,
            }}
          />
        </Source>
      )}

      {popup && (
        <Popup
          longitude={popup.lng}
          latitude={popup.lat}
          onClose={() => setPopup(null)}
          closeOnClick={false}
          maxWidth="280px"
        >
          <PopupContent info={popup} />
        </Popup>
      )}
    </MapGL>
  )
}
