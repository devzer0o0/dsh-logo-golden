/**
 * Regenerate docs/cycle-timing.png from the shipped SWEEP_PARAMS.
 *
 * Run through vitest so the parameters, the trajectory and the envelope all come
 * from the same modules the plugin runs; the figure is written straight to
 * docs/cycle-timing.png.
 */
import { describe, expect, it } from 'vitest'
import fs from 'node:fs'
import { buildLayout } from '../src/client/layout.ts'
import { shapeGeometryOf } from '../src/client/geometry-mask.ts'
import { MARK_GEOMETRY, NAME_GEOMETRY } from '../src/client/paths.ts'
import { SWEEP_PARAMS } from '../src/client/sweep.ts'
import { envelopeAt, sampleTrajectory, trajectoryOf, warpAt } from '../src/client/trajectory.ts'

const W = 1200
const H = 520
const BG = [24, 24, 27]
const INK = [232, 230, 227]
const MUTED = [150, 148, 145]
const GOLD = [232, 188, 102]
const GOLD_LIGHT = [255, 214, 140]
const GOLD_DIM = [200, 170, 120]
const REST = [56, 56, 64]
const NEXT = [120, 98, 52]
const GRID = [58, 58, 66]

const buf = new Uint8Array(W * H * 3)
for (let i = 0; i < W * H; i += 1) {
  buf[i * 3] = BG[0]!
  buf[i * 3 + 1] = BG[1]!
  buf[i * 3 + 2] = BG[2]!
}

function put(x: number, y: number, c: number[]): void {
  if (x < 0 || y < 0 || x >= W || y >= H) return
  const at = (y * W + x) * 3
  buf[at] = c[0]!
  buf[at + 1] = c[1]!
  buf[at + 2] = c[2]!
}

function rect(x0: number, y0: number, w: number, h: number, c: number[], alpha = 1): void {
  for (let y = Math.round(y0); y < Math.round(y0 + h); y += 1) {
    for (let x = Math.round(x0); x < Math.round(x0 + w); x += 1) {
      if (alpha >= 1) { put(x, y, c); continue }
      const at = (y * W + x) * 3
      put(x, y, [
        Math.round(buf[at]! * (1 - alpha) + c[0]! * alpha),
        Math.round(buf[at + 1]! * (1 - alpha) + c[1]! * alpha),
        Math.round(buf[at + 2]! * (1 - alpha) + c[2]! * alpha),
      ])
    }
  }
}

function vline(x: number, y0: number, y1: number, c: number[], alpha = 1): void {
  for (let y = Math.round(y0); y < Math.round(y1); y += 1) rect(x, y, 1, 1, c, alpha)
}

function polyline(points: [number, number][], c: number[]): void {
  for (let i = 1; i < points.length; i += 1) {
    const [x0, y0] = points[i - 1]!
    const [x1, y1] = points[i]!
    const steps = Math.max(1, Math.ceil(Math.max(Math.abs(x1 - x0), Math.abs(y1 - y0)) * 2))
    for (let s = 0; s <= steps; s += 1) {
      const t = s / steps
      rect(x0 + (x1 - x0) * t, y0 + (y1 - y0) * t, 1.6, 1.6, c)
    }
  }
}

describe('docs figure', () => {
  it('writes cycle-timing.png for the shipped cadence', () => {
    const { periodMs, entryMs, surfaceMs, exitMs, sweepMs } = SWEEP_PARAMS
    const restMs = periodMs - sweepMs
    const layout = buildLayout(
      new Map([
        ['mark', { left: 16, top: 58, width: 24, height: 17.66 }],
        ['name', { left: 48, top: 54, width: 156, height: 24 }],
      ]),
      new Map([['mark', '0 0 23.16 17.04'], ['name', '26 0 156 24']]),
      2,
      SWEEP_PARAMS,
      new Map([
        ['mark', shapeGeometryOf(MARK_GEOMETRY)],
        ['name', shapeGeometryOf(NAME_GEOMETRY)],
      ]),
    )!
    const points = trajectoryOf(layout, SWEEP_PARAMS)
    const x0 = 96
    const x1 = 1120
    const span = periodMs * 2.05
    const sx = (ms: number): number => x0 + (ms / span) * (x1 - x0)

    // Grid lines every period, labelled.
    for (let k = 0; k <= 2; k += 1) {
      const at = k * periodMs
      vline(sx(at), 80, 470, GRID)
    }
    // Track 1: window and rest, then the following cycle's window.
    rect(sx(0), 100, sx(sweepMs) - sx(0), 36, GOLD)
    rect(sx(sweepMs), 100, sx(periodMs) - sx(sweepMs), 36, REST)
    rect(sx(periodMs), 100, sx(periodMs + sweepMs) - sx(periodMs), 36, NEXT)
    // Track 2: the three stages.
    rect(sx(0), 144, sx(entryMs) - sx(0), 26, GOLD_LIGHT)
    rect(sx(entryMs), 144, sx(entryMs + surfaceMs) - sx(entryMs), 26, GOLD)
    rect(sx(entryMs + surfaceMs), 144, sx(sweepMs) - sx(entryMs + surfaceMs), 26, GOLD_DIM)
    // Track 3: beam centre, from the entry point to the exit point.
    const beam: [number, number][] = []
    for (let ms = 0; ms <= sweepMs; ms += 4) {
      const v = (sampleTrajectory(points, ms) - layout.centerStart) / (layout.centerEnd - layout.centerStart)
      beam.push([sx(ms), 300 - v * 70])
    }
    polyline(beam, GOLD)
    // Track 4: the two amplitudes.
    const env: [number, number][] = []
    const warp: [number, number][] = []
    for (let ms = 0; ms <= sweepMs; ms += 4) {
      env.push([sx(ms), 386 - envelopeAt(ms, SWEEP_PARAMS) * 48])
      warp.push([sx(ms), 462 - warpAt(ms, SWEEP_PARAMS) * 48])
    }
    polyline(env, [126, 196, 232])
    polyline(warp, [150, 150, 210])

    fs.mkdirSync('docs', { recursive: true })
    // Encode by hand: a PNG writer needs zlib, which Node ships.
    // eslint-disable-next-line @typescript-eslint/no-require-imports
    const zlib = require('node:zlib') as typeof import('node:zlib')
    const raw = Buffer.alloc((W * 3 + 1) * H)
    for (let y = 0; y < H; y += 1) {
      raw[y * (W * 3 + 1)] = 0
      Buffer.from(buf.buffer, y * W * 3, W * 3).copy(raw, y * (W * 3 + 1) + 1)
    }
    const idat = zlib.deflateSync(raw, { level: 9 })
    const chunk = (type: string, data: Buffer): Buffer => {
      const head = Buffer.alloc(8)
      head.writeUInt32BE(data.length, 0)
      head.write(type, 4, 'ascii')
      const crc = Buffer.alloc(4)
      crc.writeUInt32BE(crc32(Buffer.concat([Buffer.from(type, 'ascii'), data])) >>> 0, 0)
      return Buffer.concat([head, data, crc])
    }
    const ihdr = Buffer.alloc(13)
    ihdr.writeUInt32BE(W, 0)
    ihdr.writeUInt32BE(H, 4)
    ihdr[8] = 8
    ihdr[9] = 2
    const png = Buffer.concat([
      Buffer.from([0x89, 0x50, 0x4e, 0x47, 0x0d, 0x0a, 0x1a, 0x0a]),
      chunk('IHDR', ihdr),
      chunk('IDAT', idat),
      chunk('IEND', Buffer.alloc(0)),
    ])
    fs.writeFileSync('docs/cycle-timing.png', png)
    console.log('wrote docs/cycle-timing.png', png.length, 'bytes; period', periodMs, 'rest', restMs)
    expect(restMs).toBe(periodMs - sweepMs)
  })
})

/** CRC-32, as PNG requires. */
function crc32(data: Buffer): number {
  let crc = 0xffffffff
  for (const byte of data) {
    crc ^= byte
    for (let bit = 0; bit < 8; bit += 1) crc = crc & 1 ? (crc >>> 1) ^ 0xedb88320 : crc >>> 1
  }
  return (crc ^ 0xffffffff) >>> 0
}
