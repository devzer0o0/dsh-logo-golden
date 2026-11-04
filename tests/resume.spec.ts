// @vitest-environment jsdom
/**
 * The controller's pause / resume path, exercised with a device attached.
 *
 * The previous lifecycle suite never left the "no WebGPU" early exit, so nothing
 * it asserted said anything about a lockup that is actually drawing. This one
 * runs the real controller over a stub device and records every frame it
 * submits — the beam centre and the envelope are read straight out of the
 * uniform write — so "the old highlight is gone" and "the restored frame is the
 * one the clock asks for" are observable facts rather than hopes.
 */
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { BrandSweepController } from '../src/client/overlay.ts'
import { resetDevice } from '../src/client/gpu.ts'
import { shapeGeometryOf } from '../src/client/geometry-mask.ts'
import { buildLayout, type LockupLayout } from '../src/client/layout.ts'
import { MARK_GEOMETRY, NAME_GEOMETRY } from '../src/client/paths.ts'
import { SWEEP_PARAMS } from '../src/client/sweep.ts'
import type { TimelineClock } from '../src/client/timeline.ts'
import { envelopeAt, sampleTrajectory, trajectoryOf } from '../src/client/trajectory.ts'
import type { GpuCanvasContext, GpuDevice } from '../src/client/webgpu.ts'

/** A clock, timer queue and frame loop the test drives by hand. */
class TestClock implements TimelineClock {
  time = 0
  private nextId = 1
  readonly timers = new Map<number, { at: number; handler: () => void }>()
  readonly frames = new Map<number, () => void>()
  maxFrames = 0
  maxTimers = 0
  /** When true, due work stays queued: the host stalled the page. */
  frozen = false

  now(): number {
    return this.time
  }

  setTimeout(handler: () => void, delay: number): number { // test-standards-allow: injected clock, not a test sleep
    const id = this.nextId++
    this.timers.set(id, { at: this.time + Math.max(0, delay), handler })
    this.maxTimers = Math.max(this.maxTimers, this.timers.size)
    return id
  }

  clearTimeout(id: number): void {
    this.timers.delete(id)
  }

  requestAnimationFrame(handler: () => void): number {
    const id = this.nextId++
    this.frames.set(id, handler)
    this.maxFrames = Math.max(this.maxFrames, this.frames.size)
    return id
  }

  cancelAnimationFrame(id: number): void {
    this.frames.delete(id)
  }

  /** Advance time, running due timers and frames unless the host is stalled. */
  advance(ms: number, frameStep = 8): void {
    const target = this.time + ms
    while (this.time < target) {
      const nextTimer = [...this.timers.entries()].sort((a, b) => a[1].at - b[1].at)[0]
      const timerAt = nextTimer === undefined ? Infinity : nextTimer[1].at
      const frameAt = this.frames.size > 0 ? this.time + frameStep : Infinity
      this.time = Math.min(target, timerAt, frameAt)
      if (this.frozen) continue
      if (timerAt !== Infinity && timerAt <= this.time) {
        this.timers.delete(nextTimer![0])
        nextTimer![1].handler()
        continue
      }
      const due = [...this.frames.values()]
      this.frames.clear()
      for (const handler of due) handler()
      if (due.length === 0 && this.time >= target) break
    }
  }

  get pending(): number {
    return this.timers.size + this.frames.size
  }
}

/** One submitted frame, in the terms the shader receives. */
interface Frame {
  /** Clock reading when it was submitted. */
  readonly at: number
  /** Beam centre, device pixels. */
  readonly centerX: number
  /** Sweep envelope; 0 is a fully transparent frame. */
  readonly envelope: number
}

/** Give an element a layout box, which jsdom does not do. */
function place(element: HTMLElement, width: number, height: number, left = 0, top = 0): void {
  element.getBoundingClientRect = () => ({
    x: left, y: top, left, top,
    right: left + width, bottom: top + height,
    width, height, toJSON: () => ({}),
  }) as DOMRect
}

/** Everything the fake host exposes, and the frames it received. */
interface Host {
  readonly clock: TestClock
  readonly frames: Frame[]
  readonly controller: BrandSweepController
  readonly mark: HTMLElement
  readonly name: HTMLElement
  readonly popover: () => HTMLElement | null
  /** Let the async device acquisition and material upload settle. */
  settle(): Promise<void>
}

/**
 * Build a controller over a stub GPU, already registered and ready.
 * @param clock - the clock to inject.
 * @returns the host.
 */
async function boot(clock: TestClock): Promise<Host> {
  const frames: Frame[] = []
  const context: GpuCanvasContext = {
    configure() {},
    getConfiguration: () => ({ alphaMode: 'premultiplied', toneMapping: { mode: 'extended' }, format: 'rgba16float' }),
    unconfigure() {},
    getCurrentTexture: () => ({ createView: () => ({}), destroy() {} }),
  }
  const device: GpuDevice = {
    createTexture: () => ({ createView: () => ({}), destroy() {} }),
    createBuffer: () => ({ destroy() {} }),
    createShaderModule: () => ({}),
    createRenderPipeline: () => ({ getBindGroupLayout: () => ({}) }),
    createBindGroup: () => ({}),
    createSampler: () => ({}),
    createCommandEncoder: () => ({
      beginRenderPass: () => ({ setPipeline() {}, setBindGroup() {}, draw() {}, end() {} }),
      finish: () => ({}),
    }),
    queue: {
      writeBuffer: (_buffer, _offset, data) => {
        frames.push({ at: clock.now(), centerX: data[0]!, envelope: data[8]! })
      },
      copyExternalImageToTexture: () => {},
      submit: () => {},
    },
    destroy() {},
  }
  vi.stubGlobal('navigator', { ...globalThis.navigator, gpu: { requestAdapter: async () => ({ requestDevice: async () => device }) } })
  vi.stubGlobal('matchMedia', (query: string) => ({
    matches: query.includes('dynamic-range'),
    addEventListener() {},
    removeEventListener() {},
  }))
  // The GPU holder is module-level, so a device acquired by an earlier test
  // would be reused here and its frames would land in the earlier test's log.
  resetDevice()
  vi.stubGlobal('createImageBitmap', async () => ({ width: 8, height: 8, close() {} }))
  // jsdom ships no ImageData; the renderer only needs it to hold the bytes.
  vi.stubGlobal('ImageData', class {
    readonly data: Uint8ClampedArray
    readonly width: number
    readonly height: number
    constructor(data: Uint8ClampedArray, width: number, height: number) {
      this.data = data
      this.width = width
      this.height = height
    }
  })
  vi.stubGlobal('Image', class {
    src = ''
    decode(): Promise<void> {
      return Promise.resolve()
    }
  })

  const canvasContexts = new Map<HTMLCanvasElement, unknown>()
  const getContext = HTMLCanvasElement.prototype.getContext
  HTMLCanvasElement.prototype.getContext = function get(this: HTMLCanvasElement, kind: string) {
    if (kind === 'webgpu') return context
    if (kind === '2d') {
      const existing = canvasContexts.get(this)
      if (existing !== undefined) return existing
      const created = {
        clearRect() {}, save() {}, beginPath() {}, rect() {}, clip() {}, restore() {},
        drawImage() {}, putImageData() {}, imageSmoothingEnabled: true, imageSmoothingQuality: 'high',
      }
      canvasContexts.set(this, created)
      return created
    }
    return getContext.call(this, kind as '2d')
  } as HTMLCanvasElement['getContext']

  Object.defineProperty(HTMLElement.prototype, 'showPopover', { value() {}, configurable: true })
  Object.defineProperty(HTMLElement.prototype, 'hidePopover', { value() {}, configurable: true })

  const mark = document.createElement('span')
  const name = document.createElement('span')
  place(mark, 24, 17.66, 16, 58)
  place(name, 156, 24, 48, 54)
  document.body.append(mark, name)
  const svg = document.createElementNS('http://www.w3.org/2000/svg', 'svg')
  const controller = new BrandSweepController(SWEEP_PARAMS, undefined, undefined, clock)
  controller.register({ id: 'mark', root: mark, svg, geometry: MARK_GEOMETRY })
  controller.register({ id: 'name', root: name, svg, geometry: NAME_GEOMETRY })

  const settle = async (): Promise<void> => {
    for (let round = 0; round < 8; round += 1) await Promise.resolve()
    await new Promise((resolve) => setTimeout(resolve, 0)) // test-standards-allow: flushing microtasks, not a sleep
    for (let round = 0; round < 8; round += 1) await Promise.resolve()
  }
  await settle()
  return {
    clock,
    frames,
    controller,
    mark,
    name,
    popover: () => document.querySelector('[data-dsh-part="brand-sweep"]') as HTMLElement | null,
    settle,
  }
}

/**
 * The layout the controller measured: the same boxes the fixture places.
 * @param nameWidth - width of the wordmark's box.
 * @returns the layout the controller should have built.
 */
function layoutOf(nameWidth = 156): LockupLayout {
  return buildLayout(
    new Map([
      ['mark', { left: 16, top: 58, width: 24, height: 17.66 }],
      ['name', { left: 48, top: 54, width: nameWidth, height: 24 }],
    ]),
    new Map([
      ['mark', '0 0 23.16 17.04'],
      ['name', '26 0 156 24'],
    ]),
    1,
    SWEEP_PARAMS,
    new Map([
      ['mark', shapeGeometryOf(MARK_GEOMETRY)],
      ['name', shapeGeometryOf(NAME_GEOMETRY)],
    ]),
  )!
}

/**
 * The pose the clock asks for, at one elapsed time inside a window.
 * @param elapsed - milliseconds from the window's nominal start.
 * @param nameWidth - width the wordmark occupies in the layout under test.
 * @returns the beam centre and the envelope the shader should receive.
 */
function expectedAt(elapsed: number, nameWidth = 156): { centerX: number; envelope: number } {
  return {
    centerX: sampleTrajectory(trajectoryOf(layoutOf(nameWidth), SWEEP_PARAMS), elapsed),
    envelope: envelopeAt(elapsed, SWEEP_PARAMS),
  }
}

let host: Host | undefined

beforeEach(() => {
  host = undefined
})

afterEach(() => {
  host?.controller.dispose()
  host?.mark.remove()
  host?.name.remove()
  resetDevice()
  vi.unstubAllGlobals()
  vi.restoreAllMocks()
})

/**
 * Boot a host and advance to a point inside the first sweep window.
 * @param fraction - position inside the window, 0..1.
 * @returns the host.
 */
async function atWindow(fraction: number): Promise<Host> {
  const clock = new TestClock()
  host = await boot(clock)
  clock.advance(SWEEP_PARAMS.firstDelayMs + SWEEP_PARAMS.sweepMs * fraction)
  return host
}

describe('pause and resume with a live device', () => {
  it('operator never sees the old highlight after the page is hidden', async () => {
    // Given: a sweep in full flight.
    const live = await atWindow(0.5)
    expect(live.frames.some((frame) => frame.envelope > 0.9)).toBe(true)
    // When: the page is hidden.
    Object.defineProperty(document, 'hidden', { value: true, configurable: true })
    window.dispatchEvent(new Event('visibilitychange'))
    // Then: a transparent frame was submitted and the overlay is hidden, so
    // nothing can show the highlight that was there a moment ago.
    const last = live.frames[live.frames.length - 1]!
    expect(last.envelope).toBe(0)
    expect(live.popover()!.style.visibility).toBe('hidden')
    // And the loop and the timer are gone.
    expect(live.clock.frames.size).toBe(0)
    expect(live.clock.timers.size).toBe(0)
    Object.defineProperty(document, 'hidden', { value: false, configurable: true })
  })

  it('operator gets the frame the clock asks for on the first restore', async () => {
    // Given: a sweep interrupted in the middle of its window.
    const live = await atWindow(0.5)
    Object.defineProperty(document, 'hidden', { value: true, configurable: true })
    window.dispatchEvent(new Event('visibilitychange'))
    Object.defineProperty(document, 'hidden', { value: false, configurable: true })
    // When: the page comes back 100 ms later, still inside the same window.
    live.clock.advance(100)
    live.frames.length = 0
    window.dispatchEvent(new Event('visibilitychange'))
    // Then: the very first frame submitted is the pose at the current elapsed
    // time, not the frame from before the pause and not a resting frame.
    const first = live.frames[0]!
    const elapsed = live.clock.now() - live.controller.originAt
    const pose = expectedAt(elapsed)
    expect(first.envelope).toBeGreaterThan(0.9)
    expect(first.centerX).toBeCloseTo(pose.centerX, 1)
    // The overlay is visible again and a loop is running.
    expect(live.popover()!.style.visibility).not.toBe('hidden')
    expect(live.controller.sweeping).toBe(true)
  })

  it('operator gets the resting state, and no fresh delay, when the page returns in the gap', async () => {
    // Given: a pause taken in the 300 ms rest between two sweeps.
    const clock = new TestClock()
    const live = (host = await boot(clock))
    clock.advance(SWEEP_PARAMS.firstDelayMs + SWEEP_PARAMS.sweepMs + 50)
    Object.defineProperty(document, 'hidden', { value: true, configurable: true })
    window.dispatchEvent(new Event('visibilitychange'))
    Object.defineProperty(document, 'hidden', { value: false, configurable: true })
    live.frames.length = 0
    const origin = live.controller.originAt
    // When: it returns inside the same gap.
    clock.advance(100)
    window.dispatchEvent(new Event('visibilitychange'))
    // Then: a transparent frame is shown at once, the origin did not move, and
    // the next sweep is the next grid point — not a first delay away.
    expect(live.frames[0]!.envelope).toBe(0)
    expect(live.controller.originAt).toBe(origin)
    expect(live.controller.sweeping).toBe(false)
    const next = origin + SWEEP_PARAMS.periodMs
    expect(next - clock.now()).toBeLessThan(SWEEP_PARAMS.periodMs)
    clock.advance(next - clock.now() + 1)
    expect(live.controller.sweeping).toBe(true)
    Object.defineProperty(document, 'hidden', { value: false, configurable: true })
  })

  it('operator gets only the cycles after the pause, never the missed ones', async () => {
    // Given: a paused page.
    const clock = new TestClock()
    const live = (host = await boot(clock))
    clock.advance(SWEEP_PARAMS.firstDelayMs + 500)
    Object.defineProperty(document, 'hidden', { value: true, configurable: true })
    window.dispatchEvent(new Event('visibilitychange'))
    Object.defineProperty(document, 'hidden', { value: false, configurable: true })
    const origin = live.controller.originAt
    // When: it returns ten periods later.
    clock.advance(SWEEP_PARAMS.periodMs * 10)
    window.dispatchEvent(new Event('visibilitychange'))
    const afterReturn = live.frames.length
    // Then: at most one cycle is live at that instant; the ten missed ones are
    // not replayed, and the grid is unchanged.
    expect(live.controller.originAt).toBe(origin)
    expect(live.clock.maxFrames).toBeLessThanOrEqual(1)
    clock.advance(SWEEP_PARAMS.periodMs * 2)
    expect(live.frames.length).toBeGreaterThan(afterReturn)
    expect(live.clock.maxTimers).toBeLessThanOrEqual(1)
  })

  it('operator gets an idempotent restore from a burst of callbacks', async () => {
    // Given: a sweep in flight.
    const live = await atWindow(0.4)
    const origin = live.controller.originAt
    const before = live.frames.length
    // When: visibility, focus and resize all fire in the same instant.
    for (let index = 0; index < 8; index += 1) {
      window.dispatchEvent(new Event('visibilitychange'))
      window.dispatchEvent(new Event('focus'))
      window.dispatchEvent(new Event('resize'))
    }
    // Then: one loop, one origin, and the running cycle was not cancelled or
    // restarted.
    expect(live.controller.originAt).toBe(origin)
    expect(live.controller.sweeping).toBe(true)
    expect(live.clock.maxFrames).toBeLessThanOrEqual(1)
    expect(live.clock.maxTimers).toBeLessThanOrEqual(1)
    expect(live.frames.length - before).toBeLessThan(40)
  })

  it('operator never gets a pause from losing focus while still visible', async () => {
    // Given: a sweep in flight and a visible page.
    const live = await atWindow(0.3)
    const origin = live.controller.originAt
    // When: the window merely loses focus, which is not a visibility change.
    window.dispatchEvent(new Event('blur'))
    live.clock.advance(100)
    // Then: the sweep carries on.
    expect(live.controller.sweeping).toBe(true)
    expect(live.controller.originAt).toBe(origin)
    expect(live.popover()!.style.visibility).not.toBe('hidden')
  })

  it('operator keeps a running sweep across a rebuild that changed nothing', async () => {
    // Given: a sweep in flight.
    const live = await atWindow(0.6)
    const origin = live.controller.originAt
    // When: observers fire repeatedly while the layout is identical.
    for (let index = 0; index < 6; index += 1) {
      live.controller.rebuild('resize')
      window.dispatchEvent(new Event('resize'))
      window.dispatchEvent(new Event('scroll'))
      live.clock.advance(10)
    }
    // Then: the cycle was never cancelled and the grid never moved.
    expect(live.controller.sweeping).toBe(true)
    expect(live.controller.originAt).toBe(origin)
  })

describe('resource swaps on a visible page', () => {
  it('operator gets the live window repainted, and revealed only once it is correct', async () => {
    // Given: a sweep in full flight over the shipped lockup.
    const live = await atWindow(0.5)
    const before = live.frames.length
    // When: the lockup is resized, which re-uploads the material and the mask.
    place(live.name, 150, 24, 48, 54)
    live.controller.rebuild('resize')
    // Then: the previous picture is hidden at once — an upload can take a frame
    // or several, and the highlight that was on screen no longer describes the
    // resources being replaced.
    expect(live.popover()!.style.visibility).toBe('hidden')
    await live.settle()
    // And once the new resources are in, the overlay is visible again holding
    // the frame the clock asks for, not the transparent upload frame.
    expect(live.popover()!.style.visibility).not.toBe('hidden')
    expect(live.controller.sweeping).toBe(true)
    expect(live.frames.length).toBeGreaterThan(before)
    const elapsed = live.clock.now() - live.controller.originAt
    const pose = expectedAt(elapsed % SWEEP_PARAMS.periodMs, 150)
    const last = live.frames[live.frames.length - 1]!
    expect(last.envelope).toBeCloseTo(pose.envelope, 3)
    expect(last.centerX).toBeCloseTo(pose.centerX, 1)
  })

  it('operator never gets a frozen highlight when the page hides in the middle of an upload', async () => {
    // Given: an upload that has started but not finished.
    const live = await atWindow(0.5)
    place(live.name, 150, 24, 48, 54)
    live.controller.rebuild('resize')
    // When: the page is hidden before the resources land.
    Object.defineProperty(document, 'hidden', { value: true, configurable: true })
    window.dispatchEvent(new Event('visibilitychange'))
    const afterHide = live.frames.length
    await live.settle()
    // Then: nothing but transparent frames was submitted while hidden, so no
    // highlight can be left standing on a page that is about to be shown.
    for (const frame of live.frames.slice(afterHide)) expect(frame.envelope).toBe(0)
    Object.defineProperty(document, 'hidden', { value: false, configurable: true })
    // And the restore reveals the picture the clock asks for.
    window.dispatchEvent(new Event('visibilitychange'))
    expect(live.popover()!.style.visibility).not.toBe('hidden')
    const elapsed = live.clock.now() - live.controller.originAt
    const pose = expectedAt(elapsed % SWEEP_PARAMS.periodMs, 150)
    const last = live.frames[live.frames.length - 1]!
    expect(last.envelope).toBeCloseTo(pose.envelope, 3)
  })
})

  it('operator gets the animation back in step after a stalled frame callback', async () => {
    // Given: a sweep in flight.
    const live = await atWindow(0.3)
    const origin = live.controller.originAt
    // When: the host stops calling the animation frame for longer than a window,
    // without any visibility event.
    live.clock.frozen = true
    live.clock.advance(SWEEP_PARAMS.periodMs * 3)
    live.clock.frozen = false
    window.dispatchEvent(new Event('focus'))
    // Then: the stale frame is not replayed; the next submitted frame belongs to
    // the window the clock is in now, and the grid did not move.
    live.frames.length = 0
    live.clock.advance(16)
    const first = live.frames[0]
    expect(first).toBeDefined()
    const elapsed = live.clock.now() - origin
    const within = elapsed % SWEEP_PARAMS.periodMs
    if (first!.envelope > 0) {
      const pose = expectedAt(within % SWEEP_PARAMS.periodMs)
      expect(Math.abs(first!.centerX - pose.centerX)).toBeLessThan(30)
    } else {
      expect(first!.envelope).toBe(0)
    }
    expect(live.controller.originAt).toBe(origin)
  })
})
