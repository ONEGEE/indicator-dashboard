import { useEffect, useMemo, useRef, useState, type PointerEvent as ReactPointerEvent } from 'react'
import {
  CYCLE_CATALOG,
  getAllPhases,
  getCurrentPhase,
  getEpisode,
  phasesToBands,
  phasesToBandsWithDefault,
  type CycleKind,
  type CyclePhase,
  type CycleSource,
} from './business-cycles'
import {
  QUADRANT_LABELS,
  QUADRANT_ORDER,
  QUADRANT_SHORT,
  FREQ_LABELS,
  FREQ_UNIT,
  RRG_FREQ_ORDER,
  RRG_RANGE_OPTIONS,
  preferWindowSpan,
  trailMaxForFreq,
  jdkMinForFreq,
  GROUP_COLORS,
  GROUP_LABELS,
  GROUP_ORDER,
  RRG_MODE_OPTIONS,
  RRG_MODE_GUIDES,
  jdkParamsFor,
  sectorDefaultBenchmark,
  defaultBenchmarkForMode,
  colorForSeries,
  computeJdkRrg,
  quadrantOf,
  resamplePrices,
  trailDefaultFor,
  smoothTrailForDisplay,
  TRAIL_SMOOTH_OPTIONS,
  RRG_VIEWPORT_OPTIONS,
  collectRrgExtentsFromPaths,
  computeRrgViewport,
  rrgAxisTicks,
  type RrgViewport,
  type QuadrantKey,
  type RrgViewportMode,
  type TrailSmoothSpan,
  type RrgData,
  type RrgFreq,
  type RrgRangeKey,
  type RrgMode,
  type RrgPoint,
  type RrgSeriesMeta,
  type PricePoint,
} from './rrg-lib'
import { publicUrl } from './assets'
import {
  buildChartInsight,
  extractAssetInsight,
  pathLenP80,
  type AssetInsight,
  type ChartInsight,
} from './rrg-insight'

type TrailStyle = 'off' | 'dots' | 'arrows'
type SpeedKey = '0.5x' | '1x' | '2x' | '4x'
type DragMode = 'start' | 'end' | 'move' | null
type SortKey = 'name' | 'symbol' | 'group' | 'price' | 'chg1' | 'chgTrail' | 'rsRatio' | 'rsMomentum' | 'quadrant'
type RangeKey = RrgRangeKey
type CustomMode = 'manual' | CycleSource

type CycleBand = { startIdx: number; endIdx: number; kind: CycleKind; label: string }

function daysAgoDate(days: number, endIso: string): string {
  const end = new Date(`${endIso.slice(0, 10)}T00:00:00`)
  if (Number.isNaN(end.getTime())) return endIso
  end.setDate(end.getDate() - days)
  const y = end.getFullYear()
  const m = String(end.getMonth() + 1).padStart(2, '0')
  const d = String(end.getDate()).padStart(2, '0')
  return `${y}-${m}-${d}`
}

function yearsAgoDate(years: number, endIso: string): string {
  const end = new Date(`${endIso.slice(0, 10)}T00:00:00`)
  if (Number.isNaN(end.getTime())) return endIso
  end.setFullYear(end.getFullYear() - years)
  const y = end.getFullYear()
  const m = String(end.getMonth() + 1).padStart(2, '0')
  const d = String(end.getDate()).padStart(2, '0')
  return `${y}-${m}-${d}`
}

function monthToStart(ym: string): string {
  return ym.length >= 7 ? `${ym.slice(0, 7)}-01` : ym
}

function monthToEnd(ym: string): string {
  if (ym.length < 7) return ym
  const [y, m] = ym.slice(0, 7).split('-').map(Number)
  const last = new Date(y, m, 0).getDate()
  return `${y}-${String(m).padStart(2, '0')}-${String(last).padStart(2, '0')}`
}

function formatPrice(v: number): string {
  if (!Number.isFinite(v)) return '—'
  const abs = Math.abs(v)
  const digits = abs >= 1000 ? 2 : abs >= 10 ? 3 : 4
  return v.toLocaleString('en-US', { maximumFractionDigits: digits })
}

function formatChg(v: number | null): string {
  if (v == null || !Number.isFinite(v)) return '—'
  const sign = v > 0 ? '+' : ''
  return `${sign}${(v * 100).toFixed(2)}%`
}

function ParamHint({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <span className="rrg-param-hint-wrap" tabIndex={0}>
      {label}
      <span className="rrg-param-hint-icon" aria-hidden>
        ?
      </span>
      <span className="rrg-param-hint" role="tooltip">
        {children}
      </span>
    </span>
  )
}

const SPEED_MS: Record<SpeedKey, number> = {
  '0.5x': 800,
  '1x': 400,
  '2x': 200,
  '4x': 100,
}

function colorWithAlpha(hex: string, alpha: number): string {
  const h = hex.replace('#', '')
  const r = parseInt(h.slice(0, 2), 16)
  const g = parseInt(h.slice(2, 4), 16)
  const b = parseInt(h.slice(4, 6), 16)
  return `rgba(${r},${g},${b},${alpha})`
}

function RrgChart({
  trails,
  trailStyle,
  viewport,
  viewportMode,
  width = 720,
  height = 520,
  hoverId,
  onHover,
}: {
  trails: {
    id: string
    name: string
    color: string
    points: RrgPoint[]
    displayPoints: RrgPoint[]
  }[]
  trailStyle: TrailStyle
  viewport: RrgViewport
  viewportMode: RrgViewportMode
  width?: number
  height?: number
  hoverId: string | null
  onHover: (id: string | null) => void
}) {
  const padding = { top: 36, right: 28, bottom: 48, left: 56 }
  const innerW = width - padding.left - padding.right
  const innerH = height - padding.top - padding.bottom

  const { minX, maxX, minY, maxY, anchorX, anchorY } = viewport

  const xTicks = useMemo(() => rrgAxisTicks(minX, maxX), [minX, maxX])
  const yTicks = useMemo(() => rrgAxisTicks(minY, maxY), [minY, maxY])

  const sx = (v: number) => padding.left + ((v - minX) / (maxX - minX || 1)) * innerW
  const sy = (v: number) => padding.top + (1 - (v - minY) / (maxY - minY || 1)) * innerH
  const cx = sx(100)
  const cy = sy(100)

  return (
    <svg className="rrg-chart" viewBox={`0 0 ${width} ${height}`} role="img" aria-label="资本轮动 RRG">
      <rect x={cx} y={padding.top} width={Math.max(0, padding.left + innerW - cx)} height={Math.max(0, cy - padding.top)} fill="var(--rrg-leading)" opacity={0.55} />
      <rect x={cx} y={cy} width={Math.max(0, padding.left + innerW - cx)} height={Math.max(0, padding.top + innerH - cy)} fill="var(--rrg-weakening)" opacity={0.55} />
      <rect x={padding.left} y={cy} width={Math.max(0, cx - padding.left)} height={Math.max(0, padding.top + innerH - cy)} fill="var(--rrg-lagging)" opacity={0.55} />
      <rect x={padding.left} y={padding.top} width={Math.max(0, cx - padding.left)} height={Math.max(0, cy - padding.top)} fill="var(--rrg-improving)" opacity={0.55} />

      <line x1={cx} x2={cx} y1={padding.top} y2={padding.top + innerH} stroke="var(--ink)" strokeWidth={1.2} opacity={0.35} />
      <line x1={padding.left} x2={padding.left + innerW} y1={cy} y2={cy} stroke="var(--ink)" strokeWidth={1.2} opacity={0.35} />

      <text x={cx + 8} y={padding.top + 16} className="rrg-quad-label">
        领先
      </text>
      <text x={cx + 8} y={padding.top + innerH - 10} className="rrg-quad-label">
        减弱
      </text>
      <text x={padding.left + 8} y={padding.top + innerH - 10} className="rrg-quad-label">
        落后
      </text>
      <text x={padding.left + 8} y={padding.top + 16} className="rrg-quad-label">
        改善
      </text>

      <text x={padding.left + innerW / 2} y={height - 12} textAnchor="middle" className="rrg-axis-label">
        JdK RS-Ratio →
      </text>
      <text
        x={16}
        y={padding.top + innerH / 2}
        textAnchor="middle"
        className="rrg-axis-label"
        transform={`rotate(-90 16 ${padding.top + innerH / 2})`}
      >
        JdK RS-Momentum →
      </text>

      {(viewportMode === 'fit' ? xTicks : [...new Set([minX, anchorX, maxX])]).map((v) => (
        <text key={`x-${v}`} x={sx(v)} y={padding.top + innerH + 18} textAnchor="middle" className="rrg-tick">
          {v.toFixed(0)}
        </text>
      ))}
      {(viewportMode === 'fit' ? yTicks : [...new Set([minY, anchorY, maxY])]).map((v) => (
        <text key={`y-${v}`} x={padding.left - 8} y={sy(v) + 4} textAnchor="end" className="rrg-tick">
          {v.toFixed(0)}
        </text>
      ))}

      {trails.map((trail) => {
        const pts = trail.displayPoints
        const landing = trail.points[trail.points.length - 1]
        if (!pts.length || !landing) return null
        const n = pts.length
        const dim = hoverId != null && hoverId !== trail.id

        return (
          <g
            key={trail.id}
            opacity={dim ? 0.18 : 1}
            onMouseEnter={() => onHover(trail.id)}
            onMouseLeave={() => onHover(null)}
            style={{ cursor: 'pointer' }}
          >
            {trailStyle !== 'off' &&
              pts.slice(0, -1).map((p, i) => {
                const q = pts[i + 1]
                const alpha = 0.15 + (0.75 * (i + 1)) / Math.max(n - 1, 1)
                const x1 = sx(p.rsRatio)
                const y1 = sy(p.rsMomentum)
                const x2 = sx(i + 1 === n - 1 ? landing.rsRatio : q.rsRatio)
                const y2 = sy(i + 1 === n - 1 ? landing.rsMomentum : q.rsMomentum)
                if (trailStyle === 'dots') {
                  return (
                    <circle
                      key={`${trail.id}-d-${i}`}
                      cx={x1}
                      cy={y1}
                      r={2.2 + (2.2 * i) / Math.max(n - 1, 1)}
                      fill={colorWithAlpha(trail.color, alpha)}
                    />
                  )
                }
                const ang = Math.atan2(y2 - y1, x2 - x1)
                const ah = 6
                const ax = x2 - Math.cos(ang) * ah
                const ay = y2 - Math.sin(ang) * ah
                const left = `L ${ax + Math.cos(ang + Math.PI / 2) * 3.2} ${ay + Math.sin(ang + Math.PI / 2) * 3.2}`
                const right = `L ${ax + Math.cos(ang - Math.PI / 2) * 3.2} ${ay + Math.sin(ang - Math.PI / 2) * 3.2}`
                return (
                  <g key={`${trail.id}-a-${i}`}>
                    <line
                      x1={x1}
                      y1={y1}
                      x2={x2}
                      y2={y2}
                      stroke={colorWithAlpha(trail.color, alpha)}
                      strokeWidth={1.5 + (1.5 * i) / Math.max(n - 1, 1)}
                      strokeLinecap="round"
                    />
                    <path
                      d={`M ${x2} ${y2} ${left} ${right} Z`}
                      fill={colorWithAlpha(trail.color, Math.min(1, alpha + 0.15))}
                    />
                  </g>
                )
              })}

            {(() => {
              const x = sx(landing.rsRatio)
              const y = sy(landing.rsMomentum)
              return (
                <g>
                  <circle cx={x} cy={y} r={7} fill={trail.color} stroke="var(--panel-solid)" strokeWidth={2} />
                  <text x={x + 10} y={y - 8} className="rrg-point-label" fill={trail.color}>
                    {trail.name}
                  </text>
                </g>
              )
            })()}
          </g>
        )
      })}

      <circle cx={cx} cy={cy} r={4} fill="var(--ink)" opacity={0.55} />
      <text x={cx + 8} y={cy - 8} className="rrg-tick">
        基准 100
      </text>
    </svg>
  )
}

/** 基准折线 + 整段时间窗刷选（可拖动整体跨度 / 拖边调整） */
function BenchmarkBrush({
  prices,
  timeline,
  winStart,
  winEnd,
  onWindowChange,
  name,
  cycleBands,
  rangeLabel,
  showCycleLegend,
}: {
  prices: PricePoint[]
  timeline: string[]
  winStart: number
  winEnd: number
  onWindowChange: (start: number, end: number) => void
  name: string
  cycleBands?: CycleBand[]
  rangeLabel?: string
  showCycleLegend?: boolean
}) {
  const ref = useRef<HTMLDivElement | null>(null)
  const drag = useRef<{ mode: DragMode; originX: number; originStart: number; originEnd: number } | null>(null)
  const width = 720
  const height = 120
  const pad = { top: 12, right: 12, bottom: 22, left: 12 }
  const innerW = width - pad.left - pad.right
  const innerH = height - pad.top - pad.bottom

  const priceByDate = useMemo(() => new Map(prices.map(([d, v]) => [d, v])), [prices])
  const series = useMemo(() => {
    return timeline
      .map((d) => {
        const v = priceByDate.get(d)
        return v != null ? ([d, v] as PricePoint) : null
      })
      .filter((x): x is PricePoint => x != null)
  }, [timeline, priceByDate])

  const values = series.map((p) => p[1])
  const minV = values.length ? Math.min(...values) : 0
  const maxV = values.length ? Math.max(...values) : 1
  const spanV = maxV - minV || 1

  const xAt = (i: number) => pad.left + (timeline.length <= 1 ? 0 : (i / (timeline.length - 1)) * innerW)
  const bandXStart = (i: number) => {
    if (timeline.length <= 1) return pad.left
    if (i <= 0) return pad.left
    return (xAt(i - 1) + xAt(i)) / 2
  }
  const bandXEnd = (i: number) => {
    if (timeline.length <= 1) return pad.left + innerW
    if (i >= timeline.length - 1) return pad.left + innerW
    return (xAt(i) + xAt(i + 1)) / 2
  }
  const yAt = (v: number) => pad.top + innerH - ((v - minV) / spanV) * innerH

  const path = useMemo(() => {
    if (series.length < 2 || timeline.length < 2) return ''
    const dateIndex = new Map(timeline.map((d, i) => [d, i]))
    return series
      .map((p, i) => {
        const idx = dateIndex.get(p[0]) ?? i
        const x = xAt(idx)
        const y = yAt(p[1])
        return `${i === 0 ? 'M' : 'L'} ${x.toFixed(1)} ${y.toFixed(1)}`
      })
      .join(' ')
  }, [series, timeline, minV, spanV])

  const left = timeline.length > 1 ? (winStart / (timeline.length - 1)) * 100 : 0
  const right = timeline.length > 1 ? (winEnd / (timeline.length - 1)) * 100 : 100
  const widthPct = Math.max(0, right - left)

  const idxFromClientX = (clientX: number) => {
    const el = ref.current
    if (!el || timeline.length < 2) return 0
    const rect = el.getBoundingClientRect()
    const t = Math.min(1, Math.max(0, (clientX - rect.left) / rect.width))
    return Math.round(t * (timeline.length - 1))
  }

  const onPointerMove = (e: ReactPointerEvent) => {
    const state = drag.current
    if (!state?.mode || timeline.length < 2) return
    const idx = idxFromClientX(e.clientX)
    if (state.mode === 'start') {
      onWindowChange(Math.min(idx, winEnd - 1), winEnd)
    } else if (state.mode === 'end') {
      onWindowChange(winStart, Math.max(idx, winStart + 1))
    } else if (state.mode === 'move') {
      const span = state.originEnd - state.originStart
      const el = ref.current
      if (!el) return
      const rect = el.getBoundingClientRect()
      const deltaT = (e.clientX - state.originX) / rect.width
      const deltaIdx = Math.round(deltaT * (timeline.length - 1))
      let ns = state.originStart + deltaIdx
      let ne = state.originEnd + deltaIdx
      if (ns < 0) {
        ne -= ns
        ns = 0
      }
      if (ne > timeline.length - 1) {
        ns -= ne - (timeline.length - 1)
        ne = timeline.length - 1
      }
      ns = Math.max(0, ns)
      ne = Math.min(timeline.length - 1, Math.max(ns + Math.max(span, 1), ne))
      onWindowChange(ns, ne)
    }
  }

  const stopDrag = () => {
    drag.current = null
  }

  return (
    <div className="rrg-brush-wrap">
      <div className="rrg-brush-head">
        <strong>基准走势 · {name}</strong>
        <span>
          范围 {rangeLabel ?? '—'} · 窗口 {timeline[winStart]?.slice(0, 10) ?? '—'} →{' '}
          {timeline[winEnd]?.slice(0, 10) ?? '—'}（{Math.max(0, winEnd - winStart + 1)} 期）
        </span>
      </div>
      <div
        ref={ref}
        className="rrg-brush"
        onPointerMove={onPointerMove}
        onPointerUp={stopDrag}
        onPointerLeave={stopDrag}
      >
        <svg viewBox={`0 0 ${width} ${height}`} className="rrg-brush-svg" preserveAspectRatio="none">
          {(cycleBands ?? []).map((b, i) => {
            const x1 = bandXStart(b.startIdx)
            const x2 = bandXEnd(b.endIdx)
            return (
              <rect
                key={`${b.kind}-${b.startIdx}-${b.endIdx}-${i}`}
                x={x1}
                y={pad.top}
                width={Math.max(0, x2 - x1)}
                height={innerH}
                fill={b.kind === 'expansion' ? 'var(--cycle-expansion)' : 'var(--cycle-contraction)'}
              >
                <title>
                  {b.label}（{b.kind === 'expansion' ? '扩张' : '收缩'}）
                </title>
              </rect>
            )
          })}
          <path d={path} fill="none" stroke="var(--accent)" strokeWidth="1.6" />
          {timeline.length > 1 && (
            <>
              <text x={pad.left} y={height - 6} className="rrg-tick">
                {timeline[0].slice(0, 10)}
              </text>
              <text x={width - pad.right} y={height - 6} textAnchor="end" className="rrg-tick">
                {timeline[timeline.length - 1].slice(0, 10)}
              </text>
            </>
          )}
        </svg>
        <div className="rrg-brush-dim left" style={{ width: `${left}%` }} />
        <div className="rrg-brush-dim right" style={{ width: `${100 - right}%` }} />
        <div
          className="rrg-brush-window"
          style={{ left: `${left}%`, width: `${widthPct}%` }}
          onPointerDown={(e) => {
            drag.current = {
              mode: 'move',
              originX: e.clientX,
              originStart: winStart,
              originEnd: winEnd,
            }
            ;(e.target as HTMLElement).setPointerCapture(e.pointerId)
          }}
        />
        <button
          type="button"
          className="rrg-slider-thumb start"
          style={{ left: `${left}%` }}
          onPointerDown={(e) => {
            e.stopPropagation()
            drag.current = { mode: 'start', originX: e.clientX, originStart: winStart, originEnd: winEnd }
            ;(e.target as HTMLElement).setPointerCapture(e.pointerId)
          }}
          aria-label="窗口起点"
        />
        <button
          type="button"
          className="rrg-slider-thumb end"
          style={{ left: `${right}%` }}
          onPointerDown={(e) => {
            e.stopPropagation()
            drag.current = { mode: 'end', originX: e.clientX, originStart: winStart, originEnd: winEnd }
            ;(e.target as HTMLElement).setPointerCapture(e.pointerId)
          }}
          aria-label="窗口终点"
        />
      </div>
      {showCycleLegend ? (
        <div className="rrg-cycle-legend">
          <span>
            <i className="rrg-cycle-swatch expansion" /> 扩张
          </span>
          <span>
            <i className="rrg-cycle-swatch contraction" /> 收缩
          </span>
        </div>
      ) : null}
      <p className="rrg-brush-hint">
        上方时间范围限制可拖动与动画的最大区间；拖动中间阴影块平移窗口，拖两端调整跨度。动画仅在该范围内滑动。
      </p>
    </div>
  )
}

export default function RrgView() {
  const [mode, setMode] = useState<RrgMode>('cross_asset')
  const [data, setData] = useState<RrgData | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [benchmarkId, setBenchmarkId] = useState('us_sp500')
  const [selected, setSelected] = useState<Set<string>>(new Set())
  const [industryLevel, setIndustryLevel] = useState<'L1' | 'L2'>('L1')
  const [parentId, setParentId] = useState<string>('')
  const [trailStyle, setTrailStyle] = useState<TrailStyle>('arrows')
  const [trailSmooth, setTrailSmooth] = useState<TrailSmoothSpan>(0)
  const [viewportMode, setViewportMode] = useState<RrgViewportMode>('centered')
  const [freq, setFreq] = useState<RrgFreq>('monthly')
  const [trailLen, setTrailLen] = useState(12)
  const [jdkWindow, setJdkWindow] = useState(12)
  const [rocPeriod, setRocPeriod] = useState(3)
  const [winStart, setWinStart] = useState(0)
  const [winEnd, setWinEnd] = useState(0)
  const [playing, setPlaying] = useState(false)
  const [speed, setSpeed] = useState<SpeedKey>('1x')
  const [hoverId, setHoverId] = useState<string | null>(null)
  const [sortKey, setSortKey] = useState<SortKey>('rsRatio')
  const [sortAsc, setSortAsc] = useState(false)
  const [rangeKey, setRangeKey] = useState<RangeKey>('5y')
  const [customMode, setCustomMode] = useState<CustomMode>('nber')
  const [customStart, setCustomStart] = useState('2015-01')
  const [customEnd, setCustomEnd] = useState(() => {
    const d = new Date()
    return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}`
  })
  const [cycleEpisodeId, setCycleEpisodeId] = useState('nber_current')
  const [quadrantFilter, setQuadrantFilter] = useState<Set<QuadrantKey>>(() => new Set(QUADRANT_ORDER))
  const spanRef = useRef(0)

  const isSectorMode = mode === 'us_gics' || mode === 'cn_sw'
  const isCountryMode = mode === 'country'
  const modeMeta = RRG_MODE_OPTIONS.find((m) => m.id === mode) ?? RRG_MODE_OPTIONS[0]
  const modeGuide = RRG_MODE_GUIDES[mode]

  useEffect(() => {
    let cancelled = false
    setData(null)
    setError(null)
    setPlaying(false)
    const url = modeMeta.url
    fetch(publicUrl(url))
      .then((r) => {
        if (!r.ok) {
          const hint =
            mode === 'cross_asset'
              ? 'python scripts/fetch_rrg.py --mode cross_asset'
              : `python scripts/fetch_rrg.py --mode ${mode}`
          throw new Error(`加载失败 ${r.status}（请运行 ${hint}）`)
        }
        return r.json()
      })
      .then((d: RrgData) => {
        if (cancelled) return
        setData(d)
        const jdk = jdkParamsFor(d, 'monthly')
        setJdkWindow(jdk.window)
        setRocPeriod(jdk.rocPeriod)
        setTrailLen(trailDefaultFor(d, 'monthly'))
        setIndustryLevel((d.rrg?.default_level as 'L1' | 'L2') || 'L1')
        setParentId('')
        setBenchmarkId(defaultBenchmarkForMode(mode, d))
        const cycle = d.rrg?.default_cycle
        if (cycle === 'cn' || cycle === 'cn_cass') {
          setCustomMode('cn_cass')
          setCycleEpisodeId('cn_current')
        } else {
          setCustomMode('nber')
          setCycleEpisodeId('nber_current')
        }
      })
      .catch((e: Error) => {
        if (!cancelled) setError(e.message)
      })
    return () => {
      cancelled = true
    }
  }, [mode, modeMeta.url])

  const colorOf = (s: RrgSeriesMeta) => {
    const g = s.group ?? ''
    const peers = data?.series.filter((x) => (x.group ?? '') === g) ?? []
    const idx = Math.max(0, peers.findIndex((x) => x.id === s.id))
    return colorForSeries(g, idx)
  }
  const seriesById = useMemo(() => {
    const m = new Map<string, RrgSeriesMeta>()
    data?.series.forEach((s) => m.set(s.id, s))
    return m
  }, [data])

  const l1Parents = useMemo(() => {
    if (!data) return [] as RrgSeriesMeta[]
    return data.series.filter((s) => s.level === 'L1')
  }, [data])

  const firstParentId = l1Parents[0]?.id ?? ''

  useEffect(() => {
    if (!isSectorMode || industryLevel !== 'L2' || !firstParentId) return
    if (!parentId || !l1Parents.some((p) => p.id === parentId)) {
      setParentId(firstParentId)
    }
  }, [isSectorMode, industryLevel, firstParentId, parentId, l1Parents])

  useEffect(() => {
    if (!isSectorMode || !data) return
    const next = sectorDefaultBenchmark(mode, industryLevel, parentId, firstParentId)
    if (next) setBenchmarkId(next)
  }, [isSectorMode, data, mode, industryLevel, parentId, firstParentId])

  const visibleSeries = useMemo(() => {
    if (!data) return [] as RrgSeriesMeta[]
    if (!isSectorMode) return data.series
    const benchIds = new Set((data.benchmarks ?? []).map((b) => b.id))
    const benches = data.series.filter((s) => benchIds.has(s.id) || s.level === 'bench')
    if (industryLevel === 'L1') {
      return [...benches, ...data.series.filter((s) => s.level === 'L1')]
    }
    const activeParent = parentId || firstParentId
    if (!activeParent) return benches
    return [...benches, ...data.series.filter((s) => s.level === 'L2' && s.parent_id === activeParent)]
  }, [data, isSectorMode, industryLevel, parentId, firstParentId])

  const plottableSeries = useMemo(() => {
    if (!isSectorMode) return visibleSeries
    return visibleSeries.filter((s) => s.level !== 'bench' && !(data?.benchmarks ?? []).some((b) => b.id === s.id))
  }, [visibleSeries, isSectorMode, data])

  const plottableKey = plottableSeries.map((s) => s.id).join('|')

  useEffect(() => {
    if (!data) return
    const ids = plottableKey ? plottableKey.split('|') : []
    const next = new Set(ids)
    if (benchmarkId) next.add(benchmarkId)
    setSelected(next)
  }, [data, industryLevel, parentId, benchmarkId, plottableKey])

  const groupedSeries = useMemo(() => {
    if (!data) return [] as { group: string; label: string; items: RrgSeriesMeta[] }[]
    const map = new Map<string, RrgSeriesMeta[]>()
    for (const s of plottableSeries) {
      const g = s.group ?? 'other'
      if (!map.has(g)) map.set(g, [])
      map.get(g)!.push(s)
    }
    if (isSectorMode) {
      return [...map.entries()].map(([g, items]) => {
        const parent = l1Parents.find((p) => p.group === g)
        return {
          group: g,
          label: parent?.name ?? GROUP_LABELS[g] ?? g,
          items,
        }
      })
    }
    const ordered: { group: string; label: string; items: RrgSeriesMeta[] }[] = GROUP_ORDER.filter(
      (g) => map.has(g),
    ).map((g) => ({
      group: g,
      label: GROUP_LABELS[g] ?? g,
      items: map.get(g)!,
    }))
    for (const [g, items] of map) {
      if ((GROUP_ORDER as readonly string[]).includes(g)) continue
      ordered.push({ group: g, label: GROUP_LABELS[g] ?? g, items })
    }
    return ordered
  }, [data, plottableSeries, isSectorMode, l1Parents])

  const groupSelectState = useMemo(() => {
    const out: Record<string, 'all' | 'some' | 'none'> = {}
    for (const { group, items } of groupedSeries) {
      const ids = items.filter((s) => s.id !== benchmarkId).map((s) => s.id)
      if (!ids.length) {
        out[group] = 'none'
        continue
      }
      const on = ids.filter((id) => selected.has(id)).length
      out[group] = on === 0 ? 'none' : on === ids.length ? 'all' : 'some'
    }
    return out
  }, [groupedSeries, selected, benchmarkId])

  const resampled = useMemo(() => {
    if (!data) return new Map<string, PricePoint[]>()
    const m = new Map<string, PricePoint[]>()
    for (const s of data.series) {
      m.set(s.id, resamplePrices(s.points, freq))
    }
    return m
  }, [data, freq])

  const fullRrg = useMemo(() => {
    if (!data) return new Map<string, RrgPoint[]>()
    const benchPts = resampled.get(benchmarkId)
    if (!benchPts?.length) return new Map<string, RrgPoint[]>()
    const map = new Map<string, RrgPoint[]>()
    const universe = isSectorMode ? plottableSeries : data.series.filter((s) => s.id !== benchmarkId)
    for (const s of universe) {
      if (s.id === benchmarkId) continue
      const pts = resampled.get(s.id)
      if (!pts?.length) continue
      const rrg = computeJdkRrg(pts, benchPts, { window: jdkWindow, rocPeriod })
      if (rrg.length) map.set(s.id, rrg)
    }
    return map
  }, [data, benchmarkId, plottableSeries, isSectorMode, jdkWindow, rocPeriod, resampled])

  const fullTimeline = useMemo(() => {
    const set = new Set<string>()
    for (const pts of fullRrg.values()) pts.forEach((p) => set.add(p.date))
    const bench = resampled.get(benchmarkId) ?? []
    bench.forEach(([d]) => set.add(d))
    return [...set].sort()
  }, [fullRrg, resampled, benchmarkId])

  const activeEpisode = useMemo(() => {
    if (rangeKey !== 'custom') return null
    if (customMode !== 'nber' && customMode !== 'cn_cass') return null
    const ep = getEpisode(customMode, cycleEpisodeId)
    if (!ep) return null
    if (ep.id === 'nber_current' || ep.id === 'cn_current') {
      const asOf = fullTimeline.at(-1) ?? ''
      if (!asOf) return ep
      const phase = getCurrentPhase(customMode, asOf)
      return {
        ...ep,
        start: phase.start,
        phases: [phase],
        label: `当前周期 · ${phase.label}`,
      }
    }
    return ep
  }, [rangeKey, customMode, cycleEpisodeId, fullTimeline])

  const currentCyclePhase = useMemo((): CyclePhase | null => {
    if (customMode !== 'nber' && customMode !== 'cn_cass') return null
    const asOf = fullTimeline.at(-1) ?? ''
    if (!asOf) return null
    return getCurrentPhase(customMode, asOf)
  }, [customMode, fullTimeline])

  const rangeBounds = useMemo(() => {
    if (!fullTimeline.length) return { start: '', end: '', label: '—' }
    const dataEnd = fullTimeline[fullTimeline.length - 1]
    const dataStart = fullTimeline[0]

    if (
      rangeKey === '1w' ||
      rangeKey === '1m' ||
      rangeKey === '3m' ||
      rangeKey === '6m'
    ) {
      const days =
        rangeKey === '1w' ? 7 : rangeKey === '1m' ? 30 : rangeKey === '3m' ? 91 : 182
      const label =
        rangeKey === '1w' ? '近1周' : rangeKey === '1m' ? '近1月' : rangeKey === '3m' ? '近3月' : '近6月'
      const start = daysAgoDate(days, dataEnd)
      const clipped = start < dataStart ? dataStart : start
      return { start: clipped, end: dataEnd, label }
    }

    if (rangeKey === '1y' || rangeKey === '3y' || rangeKey === '5y' || rangeKey === '10y') {
      const years = rangeKey === '1y' ? 1 : rangeKey === '3y' ? 3 : rangeKey === '5y' ? 5 : 10
      const start = yearsAgoDate(years, dataEnd)
      const clipped = start < dataStart ? dataStart : start
      return {
        start: clipped,
        end: dataEnd,
        label: `近${years}年`,
      }
    }

    if (customMode === 'manual') {
      let start = monthToStart(customStart)
      let end = monthToEnd(customEnd)
      if (start > end) [start, end] = [end, start]
      start = start < dataStart ? dataStart : start
      end = end > dataEnd ? dataEnd : end
      return {
        start,
        end,
        label: `自定义 ${start.slice(0, 7)} → ${end.slice(0, 7)}`,
      }
    }

    const ep = activeEpisode
    if (!ep) {
      return { start: dataStart, end: dataEnd, label: '自定义' }
    }

    // 全区间：可用数据内的完整时间轴 + 全周期底色
    if (ep.fullHistory) {
      return {
        start: dataStart,
        end: dataEnd,
        label: ep.label,
      }
    }

    // 当前周期 / 特定周期：严格限定在周期段内（与上方选择一致）
    let start = ep.start < dataStart ? dataStart : ep.start
    let end = ep.end > dataEnd ? dataEnd : ep.end
    if (ep.id === 'nber_current' || ep.id === 'cn_current') {
      end = dataEnd
    }
    if (start > end) {
      start = dataStart
      end = dataEnd
    }
    return {
      start,
      end,
      label: ep.label,
    }
  }, [fullTimeline, rangeKey, customMode, customStart, customEnd, activeEpisode])

  const timeline = useMemo(() => {
    if (!fullTimeline.length || !rangeBounds.start) return []
    return fullTimeline.filter((d) => d >= rangeBounds.start && d <= rangeBounds.end)
  }, [fullTimeline, rangeBounds])

  const quadrantAtEnd = useMemo(() => {
    const m = new Map<string, QuadrantKey>()
    if (!timeline.length) return m
    const endDate = timeline[Math.max(0, Math.min(winEnd, timeline.length - 1))]
    for (const [id, pts] of fullRrg) {
      const last = pts.filter((p) => p.date <= endDate).at(-1)
      if (!last) continue
      m.set(id, quadrantOf(last.rsRatio, last.rsMomentum) as QuadrantKey)
    }
    return m
  }, [fullRrg, timeline, winEnd])

  const allQuadrantsOn = quadrantFilter.size === QUADRANT_ORDER.length

  const passesQuadrantFilter = (id: string) => {
    if (allQuadrantsOn) return true
    if (!quadrantFilter.size) return false
    const q = quadrantAtEnd.get(id)
    return q != null && quadrantFilter.has(q)
  }

  const toggleQuadrantFilter = (key: QuadrantKey) => {
    setQuadrantFilter((prev) => {
      const next = new Set(prev)
      if (next.has(key)) next.delete(key)
      else next.add(key)
      return next
    })
  }

  const selectAllQuadrants = () => setQuadrantFilter(new Set(QUADRANT_ORDER))

  const sectorAssetsSorted = useMemo(() => {
    if (!isSectorMode) return plottableSeries
    const rank = (id: string) => {
      const q = quadrantAtEnd.get(id)
      return q ? QUADRANT_ORDER.indexOf(q) : QUADRANT_ORDER.length
    }
    return [...plottableSeries].sort((a, b) => {
      const dr = rank(a.id) - rank(b.id)
      if (dr !== 0) return dr
      return a.name.localeCompare(b.name, 'zh-CN')
    })
  }, [isSectorMode, plottableSeries, quadrantAtEnd])

  const cyclePhasesForBrush = useMemo(() => {
    if (rangeKey !== 'custom') return [] as CyclePhase[]
    if (customMode !== 'nber' && customMode !== 'cn_cass') return []
    if (!activeEpisode) return []
    if (activeEpisode.fullHistory) return getAllPhases(customMode)
    return activeEpisode.phases
  }, [rangeKey, customMode, activeEpisode])

  const cycleBands = useMemo(() => {
    if (!timeline.length || !cyclePhasesForBrush.length) return [] as CycleBand[]
    const isCurrentOnly = activeEpisode?.id === 'nber_current' || activeEpisode?.id === 'cn_current'
    if (isCurrentOnly) {
      return phasesToBandsWithDefault(cyclePhasesForBrush, timeline, 'expansion')
    }
    return phasesToBands(cyclePhasesForBrush, timeline)
  }, [cyclePhasesForBrush, timeline, activeEpisode])

  // 范围/频率/基准变化时：刷选轴=时间范围；窗口默认取范围内一段（便于动画滑动）
  useEffect(() => {
    if (!timeline.length) return
    const end = timeline.length - 1
    const preferSpan = preferWindowSpan(freq, end, trailLen)
    const start = Math.max(0, end - preferSpan)
    setWinStart(start)
    setWinEnd(end)
    spanRef.current = end - start
    setPlaying(false)
  }, [timeline.length, timeline[0], timeline[timeline.length - 1], benchmarkId, jdkWindow, rocPeriod, freq, rangeKey, customMode, cycleEpisodeId, customStart, customEnd])

  const trails = useMemo(() => {
    if (!timeline.length || !data) return []
    const startDate = timeline[Math.max(0, Math.min(winStart, timeline.length - 1))]
    const endDate = timeline[Math.max(0, Math.min(winEnd, timeline.length - 1))]
    const out: {
      id: string
      name: string
      color: string
      points: RrgPoint[]
      displayPoints: RrgPoint[]
    }[] = []
    for (const s of data.series) {
      if (!selected.has(s.id) || s.id === benchmarkId) continue
      if (!passesQuadrantFilter(s.id)) continue
      const pts = fullRrg.get(s.id)
      if (!pts?.length) continue
      const inRange = pts.filter((p) => p.date >= startDate && p.date <= endDate)
      if (!inRange.length) continue
      const raw = inRange.slice(-Math.max(1, trailLen))
      out.push({
        id: s.id,
        name: s.name,
        color: colorOf(s),
        points: raw,
        displayPoints: trailSmooth > 0 ? smoothTrailForDisplay(raw, trailSmooth) : raw,
      })
    }
    return out
  }, [data, selected, benchmarkId, fullRrg, timeline, winStart, winEnd, trailLen, trailSmooth, allQuadrantsOn, quadrantFilter, quadrantAtEnd])

  const rrgViewport = useMemo(() => {
    if (!timeline.length || !data) return computeRrgViewport([], [], viewportMode)
    const startDate = timeline[0]
    const endDate = timeline[timeline.length - 1]
    const paths: RrgPoint[][] = []
    for (const s of data.series) {
      if (!selected.has(s.id) || s.id === benchmarkId) continue
      const pts = fullRrg.get(s.id)
      if (pts?.length) paths.push(pts)
    }
    const { xs, ys } = collectRrgExtentsFromPaths(paths, startDate, endDate)
    return computeRrgViewport(xs, ys, viewportMode)
  }, [data, selected, benchmarkId, fullRrg, timeline, viewportMode])

  const assetInsights = useMemo(() => {
    if (!trails.length) return [] as AssetInsight[]
    const p80 = pathLenP80(trails.map((t) => t.points))
    const out: AssetInsight[] = []
    for (const t of trails) {
      const ins = extractAssetInsight(t.id, t.name, t.points, { pathLenP80: p80 })
      if (ins) out.push(ins)
    }
    return out
  }, [trails])

  const chartInsight = useMemo((): ChartInsight => {
    return buildChartInsight(assetInsights, { modeLabel: modeMeta.label })
  }, [assetInsights, modeMeta.label])

  const focusInsight = useMemo(() => {
    if (!assetInsights.length) return null as AssetInsight | null
    if (hoverId) {
      const hit = assetInsights.find((a) => a.id === hoverId)
      if (hit) return hit
    }
    // 优先展示早期观察，否则展示距中心最远者
    const early = assetInsights.find((a) => a.earlyWatch)
    if (early) return early
    return [...assetInsights].sort((a, b) => b.distance - a.distance)[0] ?? null
  }, [assetInsights, hoverId])

  // 动画：仅在当前时间范围内滑动固定跨度窗口
  useEffect(() => {
    if (!playing || timeline.length < 2) return
    const timer = globalThis.setInterval(() => {
      setWinEnd((prevEnd) => {
        const span = Math.max(1, spanRef.current)
        const nextEnd = prevEnd + 1
        if (nextEnd >= timeline.length) {
          setPlaying(false)
          return timeline.length - 1
        }
        setWinStart(Math.max(0, nextEnd - span))
        return nextEnd
      })
    }, SPEED_MS[speed])
    return () => globalThis.clearInterval(timer)
  }, [playing, speed, timeline.length])

  const tableRows = useMemo(() => {
    if (!data || !timeline.length) return []
    const endDate = timeline[Math.max(0, Math.min(winEnd, timeline.length - 1))]
    const startDate = timeline[Math.max(0, Math.min(winStart, timeline.length - 1))]

    const rows = (isSectorMode ? plottableSeries : data.series).map((s) => {
      const prices = resampled.get(s.id) ?? []
      // 在窗口终点取最近可用价
      let price: number | null = null
      let prevPrice: number | null = null
      let trailAgoPrice: number | null = null
      const dated = prices.filter(([d]) => d <= endDate)
      if (dated.length) {
        price = dated[dated.length - 1][1]
        if (dated.length >= 2) prevPrice = dated[dated.length - 2][1]
        const trailIdx = Math.max(0, dated.length - 1 - trailLen)
        trailAgoPrice = dated[trailIdx][1]
      }
      const chg1 = price != null && prevPrice != null && prevPrice !== 0 ? price / prevPrice - 1 : null
      const chgTrail =
        price != null && trailAgoPrice != null && trailAgoPrice !== 0 ? price / trailAgoPrice - 1 : null

      const isBench = s.id === benchmarkId
      let rsRatio: number | null = null
      let rsMomentum: number | null = null
      let quadrant = '—'
      if (!isBench) {
        const pts = fullRrg.get(s.id) ?? []
        const inRange = pts.filter((p) => p.date >= startDate && p.date <= endDate)
        const last = inRange.at(-1) ?? pts.filter((p) => p.date <= endDate).at(-1)
        if (last) {
          rsRatio = last.rsRatio
          rsMomentum = last.rsMomentum
          quadrant = QUADRANT_LABELS[quadrantOf(last.rsRatio, last.rsMomentum)]
        }
      }

      return {
        id: s.id,
        name: s.name,
        symbol: s.symbol,
        group: s.group ?? '',
        groupLabel: GROUP_LABELS[s.group ?? ''] ?? s.group ?? '—',
        vehicle: s.vehicle ?? '—',
        isBench,
        visible: selected.has(s.id),
        price,
        chg1,
        chgTrail,
        rsRatio,
        rsMomentum,
        quadrant,
        color: colorOf(s),
      }
    })

    const dir = sortAsc ? 1 : -1
    const numKeys = new Set<SortKey>(['price', 'chg1', 'chgTrail', 'rsRatio', 'rsMomentum'])
    rows.sort((a, b) => {
      if (a.isBench !== b.isBench) return a.isBench ? -1 : 1
      if (numKeys.has(sortKey)) {
        const av = a[sortKey] as number | null
        const bv = b[sortKey] as number | null
        if (av == null && bv == null) return 0
        if (av == null) return 1
        if (bv == null) return -1
        return (av - bv) * dir
      }
      const av = String(a[sortKey] ?? '')
      const bv = String(b[sortKey] ?? '')
      return av.localeCompare(bv, 'zh-CN') * dir
    })
    return rows
  }, [
    data,
    timeline,
    winStart,
    winEnd,
    resampled,
    fullRrg,
    benchmarkId,
    selected,
    trailLen,
    sortKey,
    sortAsc,
    isSectorMode,
    plottableSeries,
  ])

  const toggleSort = (key: SortKey) => {
    if (sortKey === key) setSortAsc((v) => !v)
    else {
      setSortKey(key)
      setSortAsc(key === 'name' || key === 'symbol' || key === 'group' || key === 'quadrant')
    }
  }

  const onWindowChange = (start: number, end: number) => {
    const s = Math.max(0, Math.min(start, end - 1))
    const e = Math.min(timeline.length - 1, Math.max(end, s + 1))
    setWinStart(s)
    setWinEnd(e)
    spanRef.current = e - s
    setPlaying(false)
  }

  const setFrequency = (f: RrgFreq) => {
    setFreq(f)
    setTrailLen(trailDefaultFor(data, f))
    const jdk = jdkParamsFor(data, f)
    setJdkWindow(jdk.window)
    setRocPeriod(jdk.rocPeriod)
    setPlaying(false)
  }

  const toggle = (id: string) => {
    setSelected((prev) => {
      const next = new Set(prev)
      if (next.has(id)) next.delete(id)
      else next.add(id)
      return next
    })
  }

  const toggleGroup = (group: string) => {
    if (!data) return
    const ids = plottableSeries.filter((s) => (s.group ?? '') === group && s.id !== benchmarkId).map((s) => s.id)
    if (!ids.length) return
    const allOn = ids.every((id) => selected.has(id))
    setSelected((prev) => {
      const next = new Set(prev)
      if (allOn) ids.forEach((id) => next.delete(id))
      else ids.forEach((id) => next.add(id))
      return next
    })
  }

  const selectOnlyGroup = (group: string) => {
    if (!data) return
    setSelected(
      new Set(
        plottableSeries.filter((s) => (s.group ?? '') === group || s.id === benchmarkId).map((s) => s.id),
      ),
    )
  }

  if (error) {
    return (
      <div className="rrg-page">
        <div className="rrg-mode-tabs" role="tablist" aria-label="轮动类型">
          {RRG_MODE_OPTIONS.map((opt) => (
            <button
              key={opt.id}
              type="button"
              role="tab"
              aria-selected={mode === opt.id}
              className={`rrg-mode-tab ${mode === opt.id ? 'active' : ''}`}
              onClick={() => setMode(opt.id)}
            >
              {opt.label}
            </button>
          ))}
        </div>
        <p className="empty">{error}</p>
      </div>
    )
  }
  if (!data) {
    return (
      <div className="rrg-page">
        <div className="rrg-mode-tabs" role="tablist" aria-label="轮动类型">
          {RRG_MODE_OPTIONS.map((opt) => (
            <button
              key={opt.id}
              type="button"
              role="tab"
              aria-selected={mode === opt.id}
              className={`rrg-mode-tab ${mode === opt.id ? 'active' : ''}`}
              onClick={() => setMode(opt.id)}
            >
              {opt.label}
            </button>
          ))}
        </div>
        <p className="empty">正在加载{modeMeta.label}数据…</p>
      </div>
    )
  }

  const benchMeta = seriesById.get(benchmarkId)
  const benchPrices = resampled.get(benchmarkId) ?? []
  const unit = FREQ_UNIT[freq]
  const heroLede =
    mode === 'country'
      ? '全球主要国家/地区宽基指数同图比较相对强弱与动量；基准可在列表中任选。MSCI 系列在数据源无纯指数时使用 ETF 代理并标注。'
      : mode === 'us_gics'
        ? 'S&P 500 GICS 一级行业默认展示；二级需先选一级再下钻。跟踪官方行业指数，相对可选基准看强弱与动量。'
        : mode === 'cn_sw'
          ? '申万一级行业默认展示；二级需先选一级再下钻。跟踪申万行业指数，相对可选基准看强弱与动量。'
          : '股票、债券、商品、货币与外汇同图观察相对基准的强弱与动量；重点看象限迁移与尾迹方向。'

  return (
    <div className="rrg-page">
      <header className="hero rrg-hero">
        <div>
          <p className="meta-row" style={{ marginBottom: 8 }}>
            <span>{modeMeta.kicker}</span>
          </p>
          <h1 className="brand">{data.title ?? modeMeta.label}</h1>
        </div>
        <p className="lede rrg-hero-lede">{data.description ?? heroLede}</p>
      </header>

      <div className="rrg-mode-tabs" role="tablist" aria-label="轮动类型">
        {RRG_MODE_OPTIONS.map((opt) => (
          <button
            key={opt.id}
            type="button"
            role="tab"
            aria-selected={mode === opt.id}
            className={`rrg-mode-tab ${mode === opt.id ? 'active' : ''}`}
            onClick={() => setMode(opt.id)}
          >
            {opt.label}
          </button>
        ))}
      </div>

      <aside className={`rrg-mode-guide rrg-mode-guide-${modeGuide.rotation}`} aria-label="模式说明">
        <div className="rrg-mode-guide-head">
          <strong>模式说明</strong>
          <span className={`rrg-mode-guide-badge rot-${modeGuide.rotation}`}>
            {modeGuide.rotation === 'high'
              ? '适合观察顺时针轮动'
              : modeGuide.rotation === 'medium'
                ? '部分标的可见弧线'
                : '重点看象限，非圆弧'}
          </span>
        </div>
        <p>{modeGuide.summary}</p>
        <ul>
          {modeGuide.tips.map((tip) => (
            <li key={tip}>{tip}</li>
          ))}
        </ul>
      </aside>

      <div className="rrg-controls">
        <section className="rrg-ctrl-section">
          <div className="rrg-ctrl-head">
            <h3>图表与计算</h3>
            <p>
              相对 <strong>{benchMeta?.name ?? benchmarkId}</strong> 的 JdK 强弱/动量（中心 100）· 展示{' '}
              <strong>{trails.length}</strong> 条轨迹
            </p>
          </div>
          <div className="rrg-ctrl-row">
            {isSectorMode && (
              <>
                <div className="rrg-field rrg-field-inline">
                  <span>行业层级</span>
                  <div className="rrg-freq-tabs">
                    <button
                      type="button"
                      className={`mc-tab ${industryLevel === 'L1' ? 'active' : ''}`}
                      onClick={() => {
                        setIndustryLevel('L1')
                        setParentId('')
                        setPlaying(false)
                      }}
                    >
                      一级行业
                    </button>
                    <button
                      type="button"
                      className={`mc-tab ${industryLevel === 'L2' ? 'active' : ''}`}
                      onClick={() => {
                        setIndustryLevel('L2')
                        setParentId(firstParentId)
                        setPlaying(false)
                      }}
                    >
                      二级行业
                    </button>
                  </div>
                </div>
                {industryLevel === 'L2' && (
                  <label className="rrg-field">
                    所属一级
                    <select
                      value={parentId || firstParentId}
                      onChange={(e) => {
                        setParentId(e.target.value)
                        setPlaying(false)
                      }}
                    >
                      {l1Parents.map((p) => (
                        <option key={p.id} value={p.id}>
                          {p.name}
                        </option>
                      ))}
                    </select>
                  </label>
                )}
              </>
            )}
            <div className="rrg-field rrg-field-inline rrg-quadrant-field">
              <span>象限筛选</span>
              <div className="rrg-freq-tabs rrg-quadrant-tabs">
                <button
                  type="button"
                  className={`mc-tab ${allQuadrantsOn ? 'active' : ''}`}
                  onClick={selectAllQuadrants}
                >
                  全部
                </button>
                {QUADRANT_ORDER.map((q) => (
                  <button
                    key={q}
                    type="button"
                    className={`mc-tab rrg-quadrant-tab q-${q} ${quadrantFilter.has(q) ? 'active' : ''}`}
                    onClick={() => toggleQuadrantFilter(q)}
                  >
                    {QUADRANT_SHORT[q]}
                  </button>
                ))}
              </div>
            </div>
            <label className="rrg-field">
              参考基准
              <select value={benchmarkId} onChange={(e) => setBenchmarkId(e.target.value)}>
                {(data.benchmarks ?? []).map((b) => (
                  <option key={b.id} value={b.id}>
                    {b.label}
                  </option>
                ))}
                {isSectorMode &&
                  industryLevel === 'L2' &&
                  l1Parents.map((p) => (
                    <option key={p.id} value={p.id}>
                      {p.name}（一级）
                    </option>
                  ))}
                {!isSectorMode &&
                  !isCountryMode &&
                  data.series
                    .filter((s) => !(data.benchmarks ?? []).some((b) => b.id === s.id))
                    .map((s) => (
                      <option key={`extra-${s.id}`} value={s.id}>
                        {s.name} ({s.symbol})
                      </option>
                    ))}
              </select>
            </label>
            <div className="rrg-field rrg-field-inline">
              <span>采样频率</span>
              <div className="rrg-freq-tabs">
                {RRG_FREQ_ORDER.map((f) => (
                  <button
                    key={f}
                    type="button"
                    className={`mc-tab ${freq === f ? 'active' : ''}`}
                    onClick={() => setFrequency(f)}
                  >
                    {FREQ_LABELS[f]}
                  </button>
                ))}
              </div>
            </div>
            <div className="rrg-field rrg-field-inline">
              <span>视窗</span>
              <div className="rrg-freq-tabs">
                {RRG_VIEWPORT_OPTIONS.map((opt) => (
                  <button
                    key={opt.id}
                    type="button"
                    className={`mc-tab ${viewportMode === opt.id ? 'active' : ''}`}
                    title={opt.hint}
                    onClick={() => setViewportMode(opt.id)}
                  >
                    {opt.label}
                  </button>
                ))}
              </div>
            </div>
            <label className="rrg-field">
              轨迹平滑
              <select
                value={trailSmooth}
                onChange={(e) => setTrailSmooth(Number(e.target.value) as TrailSmoothSpan)}
                title="仅平滑图表轨迹展示，不改变明细表与落点数值"
              >
                {TRAIL_SMOOTH_OPTIONS.map((opt) => (
                  <option key={opt.value} value={opt.value}>
                    {opt.label}
                  </option>
                ))}
              </select>
            </label>
            <label className="rrg-field">
              轨迹样式
              <select value={trailStyle} onChange={(e) => setTrailStyle(e.target.value as TrailStyle)}>
                <option value="off">不显示</option>
                <option value="arrows">箭头</option>
                <option value="dots">圆点</option>
              </select>
            </label>
            <label className="rrg-field">
              轨迹长度
              <input
                type="range"
                min={2}
                max={trailMaxForFreq(freq)}
                value={trailLen}
                onChange={(e) => setTrailLen(Number(e.target.value))}
              />
              <em>
                {trailLen} {unit}
              </em>
            </label>
            <label className="rrg-field rrg-field-narrow">
              <ParamHint label="JdK">
                <strong>JdK 平滑窗口</strong>
                <p>
                  对相对强弱 RS 做指数移动平均，并作为 RS-Ratio 滚动 z-score 的窗口（单位：{unit}）。切换采样频率时会自动匹配推荐值（日 20 / 周 14 / 月 12 / 年 6）。
                </p>
                <p>
                  <strong>调大</strong>：轨迹更平滑、反应更慢。
                </p>
                <p>
                  <strong>调小</strong>：更灵敏、波动更大。
                </p>
              </ParamHint>
              <input
                type="number"
                min={jdkMinForFreq(freq)}
                max={30}
                value={jdkWindow}
                onChange={(e) => setJdkWindow(Number(e.target.value))}
                title={`JdK 平滑窗口（${unit}）。调大会平滑轨迹、调小会更灵敏，并重算横纵轴与象限。`}
              />
            </label>
            <label className="rrg-field rrg-field-narrow">
              <ParamHint label="ROC">
                <strong>ROC 动量回溯期</strong>
                <p>
                  基于 <strong>RS-Ratio</strong>（非原始价格）计算变化率，再平滑后映射为纵轴 RS-Momentum。推荐值：日 10 / 周 10 / 月 3 / 年 2。
                </p>
                <p>
                  <strong>调大</strong>：动量看更长周期，纵轴摆动更缓。
                </p>
                <p>
                  <strong>调小</strong>：更关注短期强弱加速/减速。
                </p>
              </ParamHint>
              <input
                type="number"
                min={2}
                max={26}
                value={rocPeriod}
                onChange={(e) => setRocPeriod(Number(e.target.value))}
                title={`ROC 回溯期（${unit}）。主要影响纵轴动量；调大更平滑、调小更灵敏。`}
              />
            </label>
          </div>
        </section>

        <section className="rrg-ctrl-section">
          <div className="rrg-ctrl-head">
            <h3>时间范围</h3>
            <p className="rrg-ctrl-summary">
              {rangeBounds.label}
              {timeline.length
                ? ` · ${timeline[0]?.slice(0, 10)} → ${timeline.at(-1)?.slice(0, 10)}（${timeline.length} 期）`
                : ''}
            </p>
          </div>
          <div className="rrg-ctrl-row">
            <div className="rrg-range-tabs">
              {RRG_RANGE_OPTIONS.map(({ id, label }) => (
                <button
                  key={id}
                  type="button"
                  className={`mc-tab ${rangeKey === id ? 'active' : ''}`}
                  onClick={() => {
                    setRangeKey(id)
                    setPlaying(false)
                  }}
                >
                  {label}
                </button>
              ))}
            </div>
            {rangeKey === 'custom' && (
              <>
                <label className="rrg-field">
                  自定义
                  <select
                    value={customMode}
                    onChange={(e) => {
                      const mode = e.target.value as CustomMode
                      setCustomMode(mode)
                      setPlaying(false)
                      if (mode === 'nber') setCycleEpisodeId('nber_current')
                      else if (mode === 'cn_cass') setCycleEpisodeId('cn_current')
                    }}
                  >
                    <option value="manual">手动起止</option>
                    <option value="nber">美国 NBER 经济周期</option>
                    <option value="cn_cass">中国社科院（刘树成）周期</option>
                  </select>
                </label>
                {customMode === 'manual' ? (
                  <>
                    <label className="rrg-field rrg-field-narrow">
                      起
                      <input type="month" value={customStart} onChange={(e) => setCustomStart(e.target.value)} />
                    </label>
                    <label className="rrg-field rrg-field-narrow">
                      止
                      <input type="month" value={customEnd} onChange={(e) => setCustomEnd(e.target.value)} />
                    </label>
                  </>
                ) : (
                  <label className="rrg-field">
                    周期段
                    <select
                      value={cycleEpisodeId}
                      onChange={(e) => {
                        setCycleEpisodeId(e.target.value)
                        setPlaying(false)
                      }}
                    >
                      {CYCLE_CATALOG[customMode].episodes.map((ep) => (
                        <option key={ep.id} value={ep.id}>
                          {ep.label}
                        </option>
                      ))}
                    </select>
                  </label>
                )}
              </>
            )}
          </div>
        </section>

        <section className="rrg-ctrl-section rrg-assets-section">
          <div className="rrg-ctrl-head">
            <h3>展示标的</h3>
            <div className="rrg-assets-actions">
              <button
                type="button"
                className="mc-tab"
                onClick={() => setSelected(new Set([...plottableSeries.map((s) => s.id), benchmarkId]))}
              >
                全选
              </button>
              <button type="button" className="mc-tab" onClick={() => setSelected(new Set([benchmarkId]))}>
                仅基准
              </button>
              <span className="rrg-group-hint">
                {isSectorMode
                  ? '单击开关 · 标签为当前象限'
                  : isCountryMode
                    ? '地区：单击开关 · 双击仅看该地区'
                    : '大类：单击开关 · 双击仅看该类'}
              </span>
            </div>
          </div>
          {isSectorMode ? (
            <div className="rrg-assets-grid rrg-assets-flat">
              {sectorAssetsSorted.map((s) => {
                const qKey = quadrantAtEnd.get(s.id)
                const qLabel = qKey ? QUADRANT_SHORT[qKey] : null
                const on = selected.has(s.id)
                const filtered = !passesQuadrantFilter(s.id)
                return (
                  <button
                    key={s.id}
                    type="button"
                    className={`rrg-asset-chip ${on ? 'on' : ''} ${filtered ? 'filtered' : ''}`}
                    onClick={() => toggle(s.id)}
                    title={s.symbol}
                  >
                    <span className="rrg-swatch" style={{ background: colorOf(s) }} />
                    <span className="rrg-asset-chip-name">{s.name}</span>
                    {qLabel ? <em className={`rrg-q-badge q-${qKey}`}>{qLabel}</em> : null}
                  </button>
                )
              })}
            </div>
          ) : (
            <>
          <div className="rrg-group-chips rrg-group-chips-inline">
            {groupedSeries.map(({ group, label, items }) => {
              const state = groupSelectState[group] ?? 'none'
              const n = items.filter((s) => s.id !== benchmarkId && selected.has(s.id)).length
              return (
                <button
                  key={group}
                  type="button"
                  className={`rrg-group-chip ${state}`}
                  style={{ ['--group-color' as string]: GROUP_COLORS[group] ?? 'var(--accent)' }}
                  onClick={() => toggleGroup(group)}
                  onDoubleClick={() => selectOnlyGroup(group)}
                  title={`单击切换 ${label}；双击仅看 ${label}`}
                >
                  <span className="rrg-group-dot" />
                  {label}
                  <em>{n}</em>
                </button>
              )
            })}
          </div>
          <div className="rrg-assets-grid">
            {groupedSeries.map(({ group, label, items }) => (
              <div className="rrg-assets-group" key={group}>
                <span className="rrg-assets-group-label">
                  <span className="rrg-group-dot" style={{ background: GROUP_COLORS[group] ?? 'var(--muted)' }} />
                  {label}
                </span>
                <div className="rrg-assets-chips">
                  {items.map((s) => {
                    const disabled = s.id === benchmarkId
                    const pts = fullRrg.get(s.id)
                    const last = pts?.at(-1)
                    const on = selected.has(s.id)
                    const q =
                      last && !disabled
                        ? QUADRANT_LABELS[quadrantOf(last.rsRatio, last.rsMomentum)].split(' ')[0]
                        : null
                    return (
                      <button
                        key={s.id}
                        type="button"
                        className={`rrg-asset-chip ${on ? 'on' : ''} ${disabled ? 'bench' : ''}`}
                        disabled={disabled}
                        onClick={() => !disabled && toggle(s.id)}
                        title={disabled ? '当前为基准' : s.symbol}
                      >
                        <span className="rrg-swatch" style={{ background: colorOf(s) }} />
                        <span className="rrg-asset-chip-name">{s.name}</span>
                        {disabled ? <em>基准</em> : q ? <em>{q}</em> : null}
                      </button>
                    )
                  })}
                </div>
              </div>
            ))}
          </div>
            </>
          )}
        </section>
      </div>

      <section className="rrg-main">
          <div className="rrg-chart-head">
            <h2 className="mc-section-title">Relative Rotation Graph</h2>
            <p className="mc-section-sub">
              {timeline[winStart]?.slice(0, 10) ?? '—'} → {timeline[winEnd]?.slice(0, 10) ?? '—'} · {FREQ_LABELS[freq]} ·
              相对 {benchMeta?.name ?? benchmarkId} · 轨迹 {trailLen}
              {unit}
            </p>
          </div>
          {trails.length ? (
            <RrgChart
              trails={trails}
              trailStyle={trailStyle}
              viewport={rrgViewport}
              viewportMode={viewportMode}
              hoverId={hoverId}
              onHover={setHoverId}
            />
          ) : !trails.length && !quadrantFilter.size ? (
            <p className="empty">请至少选择一个象限以展示轨迹。</p>
          ) : (
            <p className="empty">当前选择下可计算轨迹不足，请勾选更多标的、扩大时间窗口或更换基准/频率。</p>
          )}

          {trails.length > 0 && (
            <aside className="rrg-insight-panel" aria-label="RRG 解读">
              <div className="rrg-insight-head">
                <h3>RRG 解读</h3>
                <span className="rrg-insight-badge">月度回测校准 · 相对配置语气</span>
              </div>
              <div className="rrg-insight-grid">
                <div className="rrg-insight-block">
                  <h4>全图摘要</h4>
                  <ul>
                    {chartInsight.summaryLines.map((line) => (
                      <li key={line}>{line}</li>
                    ))}
                  </ul>
                  {chartInsight.cautionLines.length > 0 && (
                    <>
                      <h4 className="rrg-insight-sub">需留意</h4>
                      <ul className="rrg-insight-caution">
                        {chartInsight.cautionLines.map((line) => (
                          <li key={line}>{line}</li>
                        ))}
                      </ul>
                    </>
                  )}
                  <h4 className="rrg-insight-sub">配置提示</h4>
                  <ul>
                    {chartInsight.adviceLines.map((line) => (
                      <li key={line}>{line}</li>
                    ))}
                  </ul>
                </div>
                <div className="rrg-insight-block">
                  <h4>
                    单标的{hoverId ? '（悬停）' : focusInsight?.earlyWatch ? '（早期观察）' : '（焦点）'}
                  </h4>
                  {focusInsight ? (
                    <>
                      <div className="rrg-insight-asset-title">
                        <strong>{focusInsight.name}</strong>
                        <span className="rrg-insight-tags">
                          {focusInsight.tags.map((t) => (
                            <em key={t}>{t}</em>
                          ))}
                        </span>
                      </div>
                      <p>{focusInsight.stateLine}</p>
                      <p>{focusInsight.trailLine}</p>
                      <p className="rrg-insight-advice">{focusInsight.adviceLine}</p>
                    </>
                  ) : (
                    <p className="empty">将鼠标移到轨迹上可查看单标的解读。</p>
                  )}
                </div>
              </div>
            </aside>
          )}

          {timeline.length > 1 && (
            <>
              {currentCyclePhase && (customMode === 'nber' || customMode === 'cn_cass') && rangeKey === 'custom' ? (
                <div className={`rrg-current-cycle ${currentCyclePhase.kind}`}>
                  <span className="rrg-current-cycle-kicker">{CYCLE_CATALOG[customMode].title} · 当前所处阶段</span>
                  <strong>{currentCyclePhase.label}</strong>
                  <span>
                    {currentCyclePhase.kind === 'expansion' ? '扩张' : '收缩'} ·{' '}
                    {currentCyclePhase.start.slice(0, 7)} →{' '}
                    {currentCyclePhase.end.startsWith('2099') ? '至今' : currentCyclePhase.end.slice(0, 7)}
                  </span>
                </div>
              ) : null}
              <BenchmarkBrush
                prices={benchPrices}
                timeline={timeline}
                winStart={winStart}
                winEnd={winEnd}
                onWindowChange={onWindowChange}
                name={benchMeta?.name ?? benchmarkId}
                cycleBands={cycleBands}
                rangeLabel={rangeBounds.label}
                showCycleLegend={cyclePhasesForBrush.length > 0}
              />
            </>
          )}

          <div className="rrg-play-bar">
            <button
              type="button"
              className="mc-tab"
              onClick={() => {
                if (playing) {
                  setPlaying(false)
                  return
                }
                spanRef.current = Math.max(1, winEnd - winStart)
                // 若已在范围末尾，从范围起点重新滑动
                if (winEnd >= timeline.length - 1) {
                  const span = spanRef.current
                  setWinStart(0)
                  setWinEnd(Math.min(timeline.length - 1, span))
                }
                setPlaying(true)
              }}
            >
              {playing ? '暂停' : '动画播放'}
            </button>
            <button
              type="button"
              className="mc-tab"
              onClick={() => {
                setPlaying(false)
                const end = timeline.length - 1
                const preferSpan = preferWindowSpan(freq, end, trailLen)
                const start = Math.max(0, end - preferSpan)
                setWinStart(start)
                setWinEnd(end)
                spanRef.current = end - start
              }}
            >
              重置窗口
            </button>
            <div className="rrg-speed">
              {(['0.5x', '1x', '2x', '4x'] as SpeedKey[]).map((s) => (
                <button
                  key={s}
                  type="button"
                  className={`mc-tab ${speed === s ? 'active' : ''}`}
                  onClick={() => setSpeed(s)}
                >
                  {s}
                </button>
              ))}
            </div>
          </div>
      </section>

      <section className="rrg-table-section">
        <h2 className="mc-section-title">明细表</h2>
        <p className="mc-section-sub">
          对应窗口终点 {timeline[winEnd]?.slice(0, 10) ?? '—'} · {FREQ_LABELS[freq]} · 相对基准{' '}
          {benchMeta?.name ?? benchmarkId} · 点击表头排序 · 勾选「显示」控制图中轨迹
        </p>
        <div className="table-wrap">
          <table className="rrg-table">
            <thead>
              <tr>
                <th>显示</th>
                <th>颜色</th>
                <th className="sortable" onClick={() => toggleSort('symbol')}>
                  代码{sortKey === 'symbol' ? (sortAsc ? ' ↑' : ' ↓') : ''}
                </th>
                <th className="sortable" onClick={() => toggleSort('name')}>
                  名称{sortKey === 'name' ? (sortAsc ? ' ↑' : ' ↓') : ''}
                </th>
                <th className="sortable" onClick={() => toggleSort('group')}>
                  类别{sortKey === 'group' ? (sortAsc ? ' ↑' : ' ↓') : ''}
                </th>
                <th>品种</th>
                <th className="sortable num" onClick={() => toggleSort('price')}>
                  价格{sortKey === 'price' ? (sortAsc ? ' ↑' : ' ↓') : ''}
                </th>
                <th className="sortable num" onClick={() => toggleSort('chg1')}>
                  本期涨跌{sortKey === 'chg1' ? (sortAsc ? ' ↑' : ' ↓') : ''}
                </th>
                <th className="sortable num" onClick={() => toggleSort('chgTrail')}>
                  轨迹期涨跌{sortKey === 'chgTrail' ? (sortAsc ? ' ↑' : ' ↓') : ''}
                </th>
                <th className="sortable num" onClick={() => toggleSort('rsRatio')}>
                  RS-Ratio{sortKey === 'rsRatio' ? (sortAsc ? ' ↑' : ' ↓') : ''}
                </th>
                <th className="sortable num" onClick={() => toggleSort('rsMomentum')}>
                  RS-Mom{sortKey === 'rsMomentum' ? (sortAsc ? ' ↑' : ' ↓') : ''}
                </th>
                <th className="sortable" onClick={() => toggleSort('quadrant')}>
                  象限{sortKey === 'quadrant' ? (sortAsc ? ' ↑' : ' ↓') : ''}
                </th>
                <th>轨迹</th>
              </tr>
            </thead>
            <tbody>
              {tableRows.map((row) => (
                <tr
                  key={row.id}
                  className={`${row.isBench ? 'bench-row' : 'clickable'} ${hoverId === row.id ? 'selected' : ''}`}
                  onMouseEnter={() => !row.isBench && setHoverId(row.id)}
                  onMouseLeave={() => setHoverId(null)}
                  onClick={() => {
                    if (!row.isBench) setHoverId(row.id)
                  }}
                >
                  <td>
                    <input
                      type="checkbox"
                      checked={row.visible}
                      disabled={row.isBench}
                      onChange={() => toggle(row.id)}
                      onClick={(e) => e.stopPropagation()}
                      aria-label={`显示 ${row.name}`}
                    />
                  </td>
                  <td>
                    <span className="rrg-swatch" style={{ background: row.color, display: 'inline-block' }} />
                  </td>
                  <td>
                    <code>{row.symbol}</code>
                  </td>
                  <td className="name-cell">
                    <strong>{row.name}</strong>
                    {row.isBench ? <span>基准</span> : null}
                  </td>
                  <td>
                    <span className="badge" style={{ borderColor: GROUP_COLORS[row.group] ?? 'var(--line)' }}>
                      <span className="rrg-group-dot" style={{ background: GROUP_COLORS[row.group] ?? 'var(--muted)' }} />
                      {row.groupLabel}
                    </span>
                  </td>
                  <td>{row.vehicle}</td>
                  <td className="num">{row.price == null ? '—' : formatPrice(row.price)}</td>
                  <td
                    className={`num ${row.chg1 != null && row.chg1 > 0 ? 'up' : ''} ${row.chg1 != null && row.chg1 < 0 ? 'down' : ''}`}
                  >
                    {formatChg(row.chg1)}
                  </td>
                  <td
                    className={`num ${row.chgTrail != null && row.chgTrail > 0 ? 'up' : ''} ${row.chgTrail != null && row.chgTrail < 0 ? 'down' : ''}`}
                  >
                    {formatChg(row.chgTrail)}
                  </td>
                  <td className="num">{row.rsRatio == null ? '—' : row.rsRatio.toFixed(2)}</td>
                  <td className="num">{row.rsMomentum == null ? '—' : row.rsMomentum.toFixed(2)}</td>
                  <td>{row.isBench ? '—' : row.quadrant}</td>
                  <td>{row.isBench ? '—' : `${trailLen}${unit}`}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
        <p className="notes">
          注：价格与涨跌按当前{FREQ_LABELS[freq]}采样（JdK {jdkWindow} / ROC {rocPeriod}，随频率自动推荐）；本期涨跌为相对上一期，轨迹期涨跌为相对 {trailLen}
          {unit}前。RS-Momentum 由 RS-Ratio 变化率推导（标准 JdK）。颜色按大类区分，同大类内用相近色标示不同标的。
        </p>
      </section>
    </div>
  )
}
