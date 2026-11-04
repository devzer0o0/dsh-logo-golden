/**
 * Coverage of a slanted stroke: the mask must light the **inside** of every
 * metal pixel, and the reference here is the original vector outline, not the
 * rasterizer under test.
 *
 * The bug this covers: the scanline rasterizer used an edge *endpoint*'s X as
 * the crossing on every row instead of interpolating, so a slanted edge shifted
 * the coverage boundary by its whole horizontal span. The "k" diagonal lost 46
 * of its 87 full interior pixels at DPR 2 while the vertical bar (an axis-
 * aligned edge, where taking the endpoint is accidentally right) stayed whole.
 *
 * Nothing below filters candidate pixels through the mask: "full interior" is
 * decided by sampling the flattened outline at sub-sample centres, so the
 * assertions are about the shape, not about what the rasterizer already
 * believed.
 */
import { describe, expect, it } from 'vitest'
import {
  SURFACE_NONE,
  SURFACE_PLATE,
  buildMaskImage,
  flattenPath,
  shapeGeometryOf,
  type Poly,
  type ShapeGeometry,
} from '../src/client/geometry-mask.ts'
import { buildLayout, type Box, type LockupLayout } from '../src/client/layout.ts'
import { MARK_GEOMETRY, NAME_GEOMETRY, WORDMARK_PATHS } from '../src/client/paths.ts'
import { SWEEP_PARAMS } from '../src/client/sweep.ts'

/** The "k": a vertical bar and one path carrying both of its diagonals. */
const K_VERTICAL = WORDMARK_PATHS[7]!
const K_DIAGONALS = WORDMARK_PATHS[8]!

const shapes = new Map([
  ['mark', shapeGeometryOf(MARK_GEOMETRY)],
  ['name', shapeGeometryOf(NAME_GEOMETRY)],
])

const viewBoxes = new Map([
  ['mark', '0 0 23.16 17.04'],
  ['name', '26 0 156 24'],
])

/**
 * Winding number of a polygon set, written from the definition.
 *
 * Deliberately a second implementation: the reference may not borrow the
 * rasterizer's own arithmetic, or it would agree with a wrong answer.
 *
 * @param polys - closed polygons in viewBox units.
 * @param x - sample point.
 * @param y - sample point.
 * @returns the summed winding number.
 */
function windingAt(polys: readonly Poly[], x: number, y: number): number {
  let total = 0
  for (const poly of polys) {
    const count = poly.length / 2
    for (let at = 0; at < count; at += 1) {
      const ax = poly[at * 2]!
      const ay = poly[at * 2 + 1]!
      const bx = poly[((at + 1) % count) * 2]!
      const by = poly[((at + 1) % count) * 2 + 1]!
      if (ay === by) continue
      const side = (bx - ax) * (y - ay) - (x - ax) * (by - ay)
      if (ay <= y && by > y && side > 0) total += 1
      else if (by <= y && ay > y && side < 0) total -= 1
    }
  }
  return total
}

/** Bounds of a polygon list, in its own units. */
function polyBoundsOf(polys: readonly Poly[]): { minX: number; minY: number; maxX: number; maxY: number } {
  let minX = Infinity
  let minY = Infinity
  let maxX = -Infinity
  let maxY = -Infinity
  for (const poly of polys) {
    for (let at = 0; at + 1 < poly.length; at += 2) {
      const x = poly[at]!
      const y = poly[at + 1]!
      if (x < minX) minX = x
      if (y < minY) minY = y
      if (x > maxX) maxX = x
      if (y > maxY) maxY = y
    }
  }
  return { minX, minY, maxX, maxY }
}

/** The shipped wordmark box, optionally scaled and displaced by a fraction. */
function nameBox(scale = 1, shiftX = 0, shiftY = 0): Box {
  return { left: 48 + shiftX, top: 54 + shiftY, width: 156 * scale, height: 24 * scale }
}

/**
 * Share of one device pixel of the wordmark that belongs to a reference shape.
 * @param layout - the measured lockup.
 * @param index - device pixel index.
 * @param polys - the reference shape, in viewBox units.
 * @param samples - sub-samples per axis.
 * @returns the share, 0..1.
 */
function shareOf(layout: LockupLayout, index: number, polys: readonly Poly[], samples = 8): number {
  const geometry = shapes.get('name')!
  const transform = layout.parts.get('name')!
  const px = index % layout.width
  const py = Math.floor(index / layout.width)
  const step = 1 / samples
  let hits = 0
  for (let sy = 0; sy < samples; sy += 1) {
    for (let sx = 0; sx < samples; sx += 1) {
      const x = geometry.viewBox[0] + (px + (sx + 0.5) * step - transform.offsetX) / transform.scale
      const y = geometry.viewBox[1] + (py + (sy + 0.5) * step - transform.offsetY) / transform.scale
      if (windingAt(polys, x, y) !== 0) hits += 1
    }
  }
  return hits / (samples * samples)
}

/**
 * Every pixel near a reference shape, classified against it.
 * @param dpr - device pixels per CSS pixel.
 * @param box - the wordmark part's rendered box.
 * @param polys - the reference shape, in viewBox units.
 * @param samples - sub-samples per axis of the reference.
 * @returns the mask, its layout and the interior / rim / exterior pixel lists.
 */
function scan(
  dpr: number,
  box: Box,
  polys: readonly Poly[],
  samples = 8,
): {
  mask: NonNullable<ReturnType<typeof buildMaskImage>>
  layout: LockupLayout
  full: number[]
  edge: number[]
  outside: number[]
} {
  const layout = buildLayout(new Map([['name', box]]), viewBoxes, dpr, SWEEP_PARAMS, shapes)!
  const mask = buildMaskImage(layout, shapes)!
  const transform = layout.parts.get('name')!
  const viewBox = shapes.get('name')!.viewBox
  const full: number[] = []
  const edge: number[] = []
  const outside: number[] = []
  const step = 1 / samples
  const total = samples * samples
  // Only the neighbourhood of the shape is classified: far from every vertex no
  // sample can be inside it, and a full-canvas sweep at N samples per pixel is
  // minutes of work, not a test.
  const bounds = polyBoundsOf(polys)
  const deviceLeft = transform.offsetX - viewBox[0] * transform.scale
  const deviceTop = transform.offsetY - viewBox[1] * transform.scale
  const pad = 2
  const firstX = Math.max(0, Math.floor(bounds.minX * transform.scale + deviceLeft) - pad)
  const lastX = Math.min(layout.width - 1, Math.ceil(bounds.maxX * transform.scale + deviceLeft) + pad)
  const firstY = Math.max(0, Math.floor(bounds.minY * transform.scale + deviceTop) - pad)
  const lastY = Math.min(layout.height - 1, Math.ceil(bounds.maxY * transform.scale + deviceTop) + pad)
  for (let py = firstY; py <= lastY; py += 1) {
    for (let px = firstX; px <= lastX; px += 1) {
      let hits = 0
      for (let sy = 0; sy < samples && hits < total; sy += 1) {
        for (let sx = 0; sx < samples; sx += 1) {
          const x = viewBox[0] + (px + (sx + 0.5) * step - transform.offsetX) / transform.scale
          const y = viewBox[1] + (py + (sy + 0.5) * step - transform.offsetY) / transform.scale
          if (windingAt(polys, x, y) !== 0) hits += 1
        }
      }
      const index = py * layout.width + px
      if (hits === total) full.push(index)
      else if (hits === 0) outside.push(index)
      else edge.push(index)
    }
  }
  return { mask, layout, full, edge, outside }
}

describe('slanted stroke coverage', () => {
  it('operator gets every full interior pixel of both k strokes fully lit', () => {
    // Given: the k's vertical bar and its diagonals as reference shapes, and the
    // shipped lockup at DPR 2, where the reported reproduction ran.
    const diagonal = scan(2, nameBox(), flattenPath(K_DIAGONALS))
    const vertical = scan(2, nameBox(), flattenPath(K_VERTICAL))
    // Then: the reference finds a real interior in both strokes — the sizes the
    // reproduction reported — and the mask covers all of it.
    expect(diagonal.full.length).toBe(87)
    expect(vertical.full.length).toBe(108)
    for (const index of diagonal.full) expect(diagonal.mask.coverage[index]!).toBeGreaterThanOrEqual(0.999)
    for (const index of vertical.full) expect(vertical.mask.coverage[index]!).toBeGreaterThanOrEqual(0.999)
    // No interior pixel is left in the dark, which is the shape of the original
    // defect rather than a rounding difference.
    expect(diagonal.full.filter((index) => (diagonal.mask.coverage[index] ?? 0) < 0.99)).toEqual([])
  })

  it('operator gets the same completeness at DPR 1, 2 and 3', () => {
    // Given: the same lockup rasterized at three device pixel ratios.
    // When: every full interior pixel of the diagonals is read back.
    for (const dpr of [1, 2, 3]) {
      const result = scan(dpr, nameBox(), flattenPath(K_DIAGONALS))
      // Then: the reference still has an interior, and the mask covers it.
      expect(result.full.length).toBeGreaterThan(10)
      for (const index of result.full) expect(result.mask.coverage[index]!).toBeGreaterThanOrEqual(0.999)
    }
  })

  it('operator gets the same completeness at a scaled size and a fractional position', () => {
    // Given: a 1.75x lockup placed on fractional device boundaries, where the
    // sample grid no longer lines up with the pixel grid.
    const result = scan(2, nameBox(1.75, 0.37, 0.61), flattenPath(K_DIAGONALS))
    // Then: the diagonal is still fully lit inside.
    expect(result.full.length).toBeGreaterThan(100)
    for (const index of result.full) expect(result.mask.coverage[index]!).toBeGreaterThanOrEqual(0.999)
  })

  it('operator keeps antialiased edges partial and lets nothing bleed past the outline', () => {
    // Given: the diagonal stroke at DPR 2.
    const result = scan(2, nameBox(), flattenPath(K_DIAGONALS))
    // When: the rim and the pixels wholly outside the outline are read back.
    const rim = result.edge.filter((index) => (result.mask.coverage[index] ?? 0) > 0)
    const outside = result.outside.map((index) => result.mask.coverage[index] ?? 0)
    // Then: the rim is a thin edge, not a filled bounding box, and no pixel the
    // stroke does not reach is painted as if it were surface — only the
    // sub-sample disagreement between the two sampling grids survives.
    expect(rim.length).toBeGreaterThan(0)
    expect(rim.length).toBeLessThan(result.full.length)
    expect(Math.max(...outside)).toBeLessThanOrEqual(0.25)
  })
})

describe('holes, gaps and the HARNESS ink', () => {
  it('operator gets every metal pixel of the lockup lit and every gap unlit', () => {
    // Given: each part's mask at DPR 2 compared with a definition-level reading
    // of the same canvas — metal is a part's outline minus the punched lettering
    // — inside that part's own clip. The parts are rasterized one at a time so a
    // neighbour's stroke cannot be mistaken for this one's metal.
    const boxes = new Map([
      ['mark', { left: 16, top: 58, width: 24, height: 17.66 }],
      ['name', nameBox()],
    ])
    const layout = buildLayout(boxes, viewBoxes, 2, SWEEP_PARAMS, shapes)!
    const samples = 4
    const step = 1 / samples
    const total = samples * samples
    let checked = 0
    let gaps = 0
    for (const [id, geometry] of shapes) {
      const solo = buildMaskImage(layout, new Map([[id, geometry]]))!
      const transform = layout.parts.get(id)!
      const left = Math.max(0, Math.floor(transform.clip.left))
      const right = Math.min(layout.width - 1, Math.ceil(transform.clip.left + transform.clip.width))
      const top = Math.max(0, Math.floor(transform.clip.top))
      const bottom = Math.min(layout.height - 1, Math.ceil(transform.clip.top + transform.clip.height))
      for (let py = top; py <= bottom; py += 1) {
        for (let px = left; px <= right; px += 1) {
          let metal = 0
          for (let sy = 0; sy < samples; sy += 1) {
            for (let sx = 0; sx < samples; sx += 1) {
              const x = geometry.viewBox[0] + (px + (sx + 0.5) * step - transform.offsetX) / transform.scale
              const y = geometry.viewBox[1] + (py + (sy + 0.5) * step - transform.offsetY) / transform.scale
              if (windingAt(geometry.outline, x, y) === 0) continue
              if (geometry.exclusions.length > 0 && windingAt(geometry.exclusions, x, y) !== 0) continue
              metal += 1
            }
          }
          const index = py * layout.width + px
          const coverage = solo.coverage[index]!
          const share = metal / total
          checked += 1
          // A pixel the shape fills completely is lit completely: this is the
          // assertion the diagonal used to fail.
          if (share === 1 && coverage < 0.999) {
            throw new Error('dropped interior pixel at ' + px + ',' + py + ' of ' + id + ': ' + coverage)
          }
          // A pixel the shape does not reach is dark, and is not classed metal.
          if (share === 0) {
            gaps += 1
            // A pixel whose 4x4 grid misses the contour can still be clipped by
            // the mask's own grid; anything above a third is a real leak.
            if (coverage > 0.35) {
              throw new Error('lit non-metal pixel at ' + px + ',' + py + ' of ' + id + ': ' + coverage)
            }
            // A pixel with no coverage at all is not metal in either reading. A
            // rim pixel may be classed metal by the mask's own grid even when
            // this one misses it, which is why the class is only checked here.
            if (coverage === 0 && solo.surface[index] !== SURFACE_NONE) {
              throw new Error('metal class on an empty pixel at ' + px + ',' + py + ' of ' + id)
            }
          }
          // An edge pixel agrees with the outline to within the one sub-sample
          // the two different sample grids can disagree by.
          if (Math.abs(coverage - share) > 0.5) {
            throw new Error('coverage disagrees with the outline at ' + px + ',' + py + ' of ' + id
              + ': mask ' + coverage + ' vs reference ' + share)
          }
        }
      }
    }
    // The scan covered both parts and a lot of air between and inside them.
    expect(checked).toBeGreaterThan(8000)
    expect(gaps).toBeGreaterThan(1000)
  })

  it('operator gets no highlight in the whale cut-outs or the plate lettering', () => {
    // Given: the mask of the shipped lockup and its reference reading.
    const boxes = new Map([
      ['mark', { left: 16, top: 58, width: 24, height: 17.66 }],
      ['name', nameBox()],
    ])
    const layout = buildLayout(boxes, viewBoxes, 2, SWEEP_PARAMS, shapes)!
    const mask = buildMaskImage(layout, shapes)!
    /** Device pixel index of a viewBox point of one part. */
    const pixelOf = (id: string, x: number, y: number): number => {
      const geometry = shapes.get(id)!
      const transform = layout.parts.get(id)!
      const px = Math.round(transform.offsetX + (x - geometry.viewBox[0]) * transform.scale)
      const py = Math.round(transform.offsetY + (y - geometry.viewBox[1]) * transform.scale)
      return py * layout.width + px
    }
    // When: points inside the whale's cut-outs and on a letter stroke of the
    // plate are read — each one first confirmed against the reference, so the
    // test is about the mask and not about a lucky coordinate.
    const counters = [
      { x: 3.5, y: 6.5 },
      { x: 5.5, y: 8.5 },
      { x: 12.4, y: 8.3 },
    ]
    // Then: the point is air, and its device pixel is mostly air too — never a
    // lit surface painted over the whale's own gaps.
    for (const point of counters) {
      expect(windingAt(shapes.get('mark')!.outline, point.x, point.y)).toBe(0)
      const index = pixelOf('mark', point.x, point.y)
      const whale = shapes.get('mark')!
      const transform = layout.parts.get('mark')!
      const px = index % layout.width
      const py = Math.floor(index / layout.width)
      let hits = 0
      for (let sy = 0; sy < 8; sy += 1) {
        for (let sx = 0; sx < 8; sx += 1) {
          const x = whale.viewBox[0] + (px + (sx + 0.5) / 8 - transform.offsetX) / transform.scale
          const y = whale.viewBox[1] + (py + (sy + 0.5) / 8 - transform.offsetY) / transform.scale
          if (windingAt(whale.outline, x, y) !== 0) hits += 1
        }
      }
      expect(mask.coverage[index]!).toBeLessThanOrEqual(hits / 64 + 0.3)
    }
    // The punched HARNESS lettering is the same story on the plate: the ink is
    // air, the plate beside it is metal of the plate class.
    const onInk = pixelOf('name', 133.2, 12.5)
    expect(shareOf(layout, onInk, flattenPath(WORDMARK_PATHS[0]!))).toBe(0)
    expect(mask.surface[onInk]!).not.toBe(SURFACE_PLATE)
    const onPlate = pixelOf('name', 131, 17.5)
    expect(mask.coverage[onPlate]!).toBeGreaterThan(0.9)
    expect(mask.surface[onPlate]!).toBe(SURFACE_PLATE)
  })
})

describe('the k as one shape', () => {
  it('operator gets the vertical bar, both diagonals and their junction fully lit', () => {
    // Given: the k's two paths as one reference shape — the junction between the
    // bar and the diagonals is only inside the union, never inside either path.
    const union = [...flattenPath(K_VERTICAL), ...flattenPath(K_DIAGONALS)]
    // When: the union is rasterized at the three shipped device ratios.
    for (const dpr of [1, 2, 3]) {
      const result = scan(dpr, nameBox(), union)
      // Then: every pixel the union fills completely is fully lit, junction
      // included. (The rim of *other* glyphs is not asserted here: the mask is
      // the whole wordmark and a neighbouring letter legitimately covers pixels
      // the k alone does not reach.)
      expect(result.full.length).toBeGreaterThan(20)
      for (const index of result.full) expect(result.mask.coverage[index]!).toBeGreaterThanOrEqual(0.999)
    }
  })
})

describe('fast and fallback rasterizers', () => {
  /** The same geometry without its precomputed edge cache. */
  function withoutEdges(id: string): ShapeGeometry {
    const full = shapes.get(id)!
    return {
      viewBox: full.viewBox,
      outline: full.outline,
      plates: full.plates,
      exclusions: full.exclusions,
      bounds: full.bounds,
    }
  }

  it('operator gets the same mask from both rasterizer paths', () => {
    // Given: the wordmark geometry with and without its edge cache, which is
    // what sends a part down the fallback path.
    const layout = buildLayout(new Map([['name', nameBox()]]), viewBoxes, 2, SWEEP_PARAMS, shapes)!
    // When: both paths build the mask of the same layout.
    const fast = buildMaskImage(layout, new Map([['name', shapes.get('name')!]]))!
    const fallback = buildMaskImage(layout, new Map([['name', withoutEdges('name')]]))!
    // Then: they describe the same surface: identical dimensions, and coverage
    // that agrees to within one sub-sample almost everywhere.
    expect(fallback.width).toBe(fast.width)
    expect(fallback.height).toBe(fast.height)
    let differing = 0
    for (let index = 0; index < fast.coverage.length; index += 1) {
      if (Math.abs(fast.coverage[index]! - fallback.coverage[index]!) > 0.26) differing += 1
    }
    expect(differing).toBeLessThanOrEqual(fast.coverage.length * 0.002 + 1)
  })

  it('operator gets the k diagonal fully covered by the fallback path too', () => {
    // Given: the wordmark geometry with no edge cache at all.
    const layout = buildLayout(new Map([['name', nameBox()]]), viewBoxes, 2, SWEEP_PARAMS, shapes)!
    const mask = buildMaskImage(layout, new Map([['name', withoutEdges('name')]]))!
    // When: every full interior pixel of the diagonals is read from it.
    const reference = scan(2, nameBox(), flattenPath(K_DIAGONALS))
    // Then: the fallback path — the one that used to stop at its first
    // horizontal hit and still divide by sixteen — covers all of them.
    expect(reference.full.length).toBe(87)
    for (const index of reference.full) expect(mask.coverage[index]!).toBeGreaterThanOrEqual(0.999)
  })
})
