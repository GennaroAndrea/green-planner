import type { Feature, Geometry, Position } from 'geojson'

type Bounds = [[number, number], [number, number]]

function visit(coords: unknown, acc: number[]): void {
  if (typeof (coords as Position)[0] === 'number') {
    const [x, y] = coords as Position
    if (x < acc[0]) acc[0] = x
    if (y < acc[1]) acc[1] = y
    if (x > acc[2]) acc[2] = x
    if (y > acc[3]) acc[3] = y
    return
  }
  for (const c of coords as unknown[]) visit(c, acc)
}

/** Bounding box of a set of features, as MapLibre `fitBounds` expects it. */
export function bboxOf(features: Feature<Geometry | null>[]): Bounds {
  const acc = [Infinity, Infinity, -Infinity, -Infinity]
  for (const f of features) {
    const g = f.geometry
    if (!g) continue
    if (g.type === 'GeometryCollection') g.geometries.forEach((gg) => 'coordinates' in gg && visit(gg.coordinates, acc))
    else visit(g.coordinates, acc)
  }
  return [
    [acc[0], acc[1]],
    [acc[2], acc[3]],
  ]
}
