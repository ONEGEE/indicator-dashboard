/** JdK 原版 RRG：RS-Ratio / RS-Momentum（中心 100） */

export type PricePoint = [string, number]

export type RrgLevel = 'L1' | 'L2' | 'bench'

export type RrgMode = 'cross_asset' | 'us_gics' | 'cn_sw' | 'country'

export type RrgSeriesMeta = {
  id: string
  name: string
  name_en?: string
  group?: string
  symbol: string
  vehicle?: string
  notes?: string
  benchmark_candidate?: boolean
  level?: RrgLevel | string
  parent_id?: string | null
  points: PricePoint[]
}

export type RrgFreq = 'daily' | 'weekly' | 'monthly' | 'yearly'

export type RrgRangeKey = '1w' | '1m' | '3m' | '6m' | '1y' | '3y' | '5y' | '10y' | 'custom'

export const RRG_FREQ_ORDER: RrgFreq[] = ['daily', 'weekly', 'monthly', 'yearly']

export const RRG_RANGE_OPTIONS: { id: RrgRangeKey; label: string }[] = [
  { id: '1w', label: '1周' },
  { id: '1m', label: '1月' },
  { id: '3m', label: '3月' },
  { id: '6m', label: '6月' },
  { id: '1y', label: '1年' },
  { id: '3y', label: '3年' },
  { id: '5y', label: '5年' },
  { id: '10y', label: '10年' },
  { id: 'custom', label: '自定义' },
]

export type RrgData = {
  generated_at: string
  mode?: RrgMode | string
  title?: string
  description?: string
  taxonomy?: string
  rrg?: {
    method?: string
    base_frequency?: string
    frequency?: string
    frequency_options?: RrgFreq[]
    window?: number
    roc_period?: number
    trail_default?: number | Partial<Record<RrgFreq, number>>
    notes?: string
    default_level?: 'L1' | 'L2'
    require_parent_for_l2?: boolean
    default_cycle?: string
  }
  benchmarks?: { id: string; label: string }[]
  counts: { assets: number }
  series: RrgSeriesMeta[]
}

export const RRG_MODE_OPTIONS: {
  id: RrgMode
  label: string
  url: string
  kicker: string
}[] = [
  {
    id: 'cross_asset',
    label: '大类资产轮动',
    url: 'rrg_prices.json',
    kicker: '跨大类相对动量 · JdK RRG',
  },
  {
    id: 'us_gics',
    label: '美股轮动',
    url: 'rrg_prices_us_gics.json',
    kicker: 'S&P 500 GICS 行业 · JdK RRG',
  },
  {
    id: 'cn_sw',
    label: 'A股轮动',
    url: 'rrg_prices_cn_sw.json',
    kicker: '申万行业指数 · JdK RRG',
  },
  {
    id: 'country',
    label: '国家指数轮动',
    url: 'rrg_prices_country.json',
    kicker: '全球主要国家指数 · JdK RRG',
  },
]

export type RrgModeGuide = {
  /** 是否适合期待顺时针弧线 */
  rotation: 'low' | 'medium' | 'high'
  summary: string
  tips: string[]
}

export const RRG_MODE_GUIDES: Record<RrgMode, RrgModeGuide> = {
  cross_asset: {
    rotation: 'low',
    summary:
      '跨股票、债券、商品、外汇的大类相对强弱对比。不同资产驱动逻辑差异大，轨迹通常不会出现行业 RRG 式的整齐顺时针弧线。',
    tips: [
      '重点看象限迁移与尾迹方向，不必强求圆弧形态',
      '建议每次只选 3–6 个可比标的，避免默认全选导致杂乱',
      '默认月度采样；日度适合 1周–6月 短区间，JdK / ROC 会随频率自动匹配',
    ],
  },
  us_gics: {
    rotation: 'high',
    summary:
      'S&P 500 GICS 行业指数相对宽基基准的 JdK 轮动。同质行业组合在完整周期中常呈顺时针迁移：改善 → 领先 → 减弱 → 落后。',
    tips: [
      '基准建议选标普 500；一级行业默认可全选',
      '播放时间轴可观察行业轮动；轨迹长度 12 月与参考站一致',
      '动量由 RS-Ratio 变化率推导，弧线比旧版更平滑',
    ],
  },
  cn_sw: {
    rotation: 'high',
    summary:
      '申万行业指数相对沪深 300 等基准的 JdK 轮动，计算与美股行业模式一致，适合观察 A 股行业轮动。',
    tips: [
      '基准建议选申万A指（801003）或沪深300；申万行业相对申万A指更可比',
      '二级行业需先选一级再下钻，避免一次展示过多轨迹',
      '月度 + JdK 12 / ROC 3 为推荐起点',
      '可与象限筛选配合，只看领先或改善象限',
    ],
  },
  country: {
    rotation: 'medium',
    summary:
      '全球主要国家/地区宽基指数相对 MSCI ACWI 或自选基准。指数同类可比，但各国宏观周期不同步，顺时针形态通常弱于单一市场行业。',
    tips: [
      '按地区分组勾选，同图保持 8 条以内更易读',
      '部分 MSCI 指数使用 ETF 代理，已在数据中标注',
      '与美股行业模式共用同一套标准 JdK 公式',
    ],
  },
}

export type RrgPoint = {
  date: string
  rsRatio: number
  rsMomentum: number
}

export type RrgTrail = {
  id: string
  name: string
  color: string
  points: RrgPoint[]
}

export const GROUP_COLORS: Record<string, string> = {
  equity: '#0f5c4c',
  bond: '#3d6b8c',
  commodity: '#8a4b1f',
  cash: '#6b645a',
  fx: '#b45309',
  china: '#be123c',
  north_america: '#1d4ed8',
  latin_america: '#0e7490',
  europe: '#6d28d9',
  asia_pacific: '#0f766e',
  mea: '#b45309',
  msci: '#7c3aed',
}

/** 同大类内多标的时用相近色区分轨迹 */
export const GROUP_SERIES_COLORS: Record<string, string[]> = {
  equity: ['#0f5c4c', '#14806a', '#0e7490', '#166534', '#115e59', '#047857'],
  bond: ['#3d6b8c', '#4a7fa3', '#2c5282', '#5b8fb0', '#1e4e6b'],
  commodity: ['#8a4b1f', '#a35c28', '#b45309', '#92400e', '#c2410c'],
  cash: ['#6b645a', '#78716c', '#57534e', '#8a8378'],
  fx: ['#b45309', '#c2410c', '#9a3412', '#d97706'],
  china: ['#be123c', '#e11d48', '#9f1239', '#f43f5e', '#881337'],
  north_america: ['#1d4ed8', '#2563eb', '#1e40af', '#3b82f6', '#1e3a8a'],
  latin_america: ['#0e7490', '#0891b2', '#155e75', '#06b6d4', '#164e63'],
  europe: ['#6d28d9', '#7c3aed', '#5b21b6', '#8b5cf6', '#4c1d95'],
  asia_pacific: ['#0f766e', '#14b8a6', '#115e59', '#0d9488', '#134e4a'],
  mea: ['#b45309', '#d97706', '#92400e', '#c2410c', '#9a3412'],
  msci: ['#7c3aed', '#8b5cf6', '#6d28d9', '#a78bfa', '#5b21b6'],
}

export const GROUP_ORDER = [
  'china',
  'north_america',
  'latin_america',
  'europe',
  'asia_pacific',
  'mea',
  'msci',
  'equity',
  'bond',
  'commodity',
  'cash',
  'fx',
] as const

export const GROUP_LABELS: Record<string, string> = {
  equity: '股票',
  bond: '债券',
  commodity: '商品',
  cash: '货币',
  fx: '外汇',
  china: '中国',
  north_america: '北美',
  latin_america: '拉美',
  europe: '欧洲',
  asia_pacific: '亚太',
  mea: '中东非',
  msci: 'MSCI',
}

export function colorForSeries(group: string | undefined, indexInGroup: number): string {
  const palette = GROUP_SERIES_COLORS[group ?? ''] ?? SERIES_PALETTE
  return palette[indexInGroup % palette.length] ?? GROUP_COLORS[group ?? ''] ?? SERIES_PALETTE[0]
}

export const SERIES_PALETTE = [
  '#0f5c4c',
  '#3d6b8c',
  '#c9a227',
  '#8a4b1f',
  '#7b5ea7',
  '#b45309',
  '#0e7490',
  '#be123c',
  '#166534',
  '#1d4ed8',
  '#a16207',
  '#6d28d9',
  '#0f766e',
  '#9f1239',
  '#365314',
  '#075985',
]

function ema(values: number[], span: number): number[] {
  const alpha = 2 / (span + 1)
  const out: number[] = []
  let prev = values[0]
  for (let i = 0; i < values.length; i++) {
    prev = i === 0 ? values[0] : alpha * values[i] + (1 - alpha) * prev
    out.push(prev)
  }
  return out
}

/** 仅用于图表轨迹展示：对 RS-Ratio / RS-Momentum 做 EMA，不改变原始序列与落点。 */
export function smoothTrailForDisplay(points: RrgPoint[], span = 3): RrgPoint[] {
  if (span <= 1 || points.length < 3) return points
  const rs = ema(
    points.map((p) => p.rsRatio),
    span,
  )
  const mom = ema(
    points.map((p) => p.rsMomentum),
    span,
  )
  const last = points.length - 1
  return points.map((p, i) => ({
    date: p.date,
    // 末点保留原始坐标，与明细表/象限一致
    rsRatio: i === last ? p.rsRatio : rs[i],
    rsMomentum: i === last ? p.rsMomentum : mom[i],
  }))
}

export const TRAIL_SMOOTH_OPTIONS = [
  { value: 0, label: '关' },
  { value: 3, label: '轻' },
  { value: 5, label: '中' },
  { value: 8, label: '强' },
] as const

export type TrailSmoothSpan = (typeof TRAIL_SMOOTH_OPTIONS)[number]['value']

function rollingMeanStd(values: number[], window: number, i: number): { mean: number; std: number } | null {
  if (i + 1 < window) return null
  let sum = 0
  for (let j = i - window + 1; j <= i; j++) sum += values[j]
  const mean = sum / window
  let varSum = 0
  for (let j = i - window + 1; j <= i; j++) {
    const d = values[j] - mean
    varSum += d * d
  }
  const std = Math.sqrt(varSum / (window - 1))
  if (!Number.isFinite(std) || std < 1e-12) return null
  return { mean, std }
}

/**
 * 标准 JdK RRG（公开复现常用形式）：
 * 1) RS = P_asset / P_benchmark
 * 2) JdK_RS = EMA(RS, window)
 * 3) RS-Ratio = 100 + 10 * zscore(JdK_RS, window)
 * 4) ROC = RS-Ratio / RS-Ratio[t-roc] - 1
 * 5) JdK_ROC = EMA(ROC, window)
 * 6) RS-Momentum = 100 + 10 * zscore(JdK_ROC, window)
 */
export function computeJdkRrg(
  assetPrices: PricePoint[],
  benchmarkPrices: PricePoint[],
  opts?: { window?: number; rocPeriod?: number },
): RrgPoint[] {
  const window = opts?.window ?? 14
  const rocPeriod = opts?.rocPeriod ?? 10

  const bMap = new Map(benchmarkPrices.map(([d, v]) => [d, v]))
  const aligned: { date: string; rs: number }[] = []
  for (const [date, px] of assetPrices) {
    const bx = bMap.get(date)
    if (bx == null || bx <= 0 || px <= 0 || !Number.isFinite(px) || !Number.isFinite(bx)) continue
    aligned.push({ date, rs: px / bx })
  }
  if (aligned.length < window + rocPeriod + 5) return []

  const rs = aligned.map((x) => x.rs)
  const jdkRs = ema(rs, window)

  const rsRatio: (number | null)[] = jdkRs.map((_, i) => {
    const st = rollingMeanStd(jdkRs, window, i)
    if (!st) return null
    return 100 + 10 * ((jdkRs[i] - st.mean) / st.std)
  })

  const roc: (number | null)[] = rsRatio.map((v, i) => {
    if (v == null || i < rocPeriod) return null
    const prev = rsRatio[i - rocPeriod]
    if (prev == null || prev === 0) return null
    return v / prev - 1
  })

  const rocFilled: number[] = []
  const rocIndex: number[] = []
  for (let i = 0; i < roc.length; i++) {
    if (roc[i] == null) continue
    rocFilled.push(roc[i] as number)
    rocIndex.push(i)
  }
  if (rocFilled.length < window + 2) return []

  const jdkRocSmooth = ema(rocFilled, window)
  const jdkRocFull: (number | null)[] = Array(aligned.length).fill(null)
  rocIndex.forEach((idx, k) => {
    jdkRocFull[idx] = jdkRocSmooth[k]
  })

  const out: RrgPoint[] = []
  for (let i = 0; i < aligned.length; i++) {
    const ratio = rsRatio[i]
    const smoothedRoc = jdkRocFull[i]
    if (ratio == null || smoothedRoc == null) continue
    const st = rollingMeanStdNullable(jdkRocFull, window, i)
    if (!st) continue
    const mom = 100 + 10 * ((smoothedRoc - st.mean) / st.std)
    if (!Number.isFinite(ratio) || !Number.isFinite(mom)) continue
    out.push({ date: aligned[i].date, rsRatio: ratio, rsMomentum: mom })
  }
  return out
}

function rollingMeanStdNullable(
  values: (number | null)[],
  window: number,
  i: number,
): { mean: number; std: number } | null {
  if (i + 1 < window) return null
  const chunk: number[] = []
  for (let j = i - window + 1; j <= i; j++) {
    const v = values[j]
    if (v == null) return null
    chunk.push(v)
  }
  let sum = 0
  for (const v of chunk) sum += v
  const mean = sum / window
  let varSum = 0
  for (const v of chunk) {
    const d = v - mean
    varSum += d * d
  }
  const std = Math.sqrt(varSum / (window - 1))
  if (!Number.isFinite(std) || std < 1e-12) return null
  return { mean, std }
}

export function quadrantOf(rsRatio: number, rsMomentum: number): string {
  if (rsRatio >= 100 && rsMomentum >= 100) return 'leading'
  if (rsRatio >= 100 && rsMomentum < 100) return 'weakening'
  if (rsRatio < 100 && rsMomentum < 100) return 'lagging'
  return 'improving'
}

export type QuadrantKey = 'leading' | 'weakening' | 'lagging' | 'improving'

export const QUADRANT_ORDER: QuadrantKey[] = ['leading', 'weakening', 'lagging', 'improving']

export const ALL_QUADRANTS: ReadonlySet<QuadrantKey> = new Set(QUADRANT_ORDER)

export const QUADRANT_SHORT: Record<QuadrantKey, string> = {
  leading: '领先',
  weakening: '减弱',
  lagging: '落后',
  improving: '改善',
}

export const QUADRANT_LABELS: Record<string, string> = {
  leading: '领先 Leading',
  weakening: '减弱 Weakening',
  lagging: '落后 Lagging',
  improving: '改善 Improving',
}

export const FREQ_LABELS: Record<RrgFreq, string> = {
  daily: '日度',
  weekly: '周度',
  monthly: '月度',
  yearly: '年度',
}

export const FREQ_UNIT: Record<RrgFreq, string> = {
  daily: '日',
  weekly: '周',
  monthly: '月',
  yearly: '年',
}

export const DEFAULT_TRAIL: Record<RrgFreq, number> = {
  daily: 20,
  weekly: 26,
  monthly: 12,
  yearly: 5,
}

/** 各采样频率下的标准 JdK 默认参数（日 20/10，周 14/10，月 12/3，年 6/2） */
export const DEFAULT_JDK_PARAMS: Record<RrgFreq, { window: number; rocPeriod: number }> = {
  daily: { window: 20, rocPeriod: 10 },
  weekly: { window: 14, rocPeriod: 10 },
  monthly: { window: 12, rocPeriod: 3 },
  yearly: { window: 6, rocPeriod: 2 },
}

/** 动画/重置时默认展示的轨迹窗口跨度（期数上限） */
export function preferWindowSpan(freq: RrgFreq, maxEnd: number, trailLen?: number): number {
  const cap = trailLen ?? DEFAULT_TRAIL[freq]
  return Math.min(cap, Math.max(0, maxEnd))
}

export function trailMaxForFreq(freq: RrgFreq): number {
  if (freq === 'daily') return 120
  if (freq === 'yearly') return 20
  return 52
}

export function jdkMinForFreq(freq: RrgFreq): number {
  if (freq === 'yearly') return 3
  if (freq === 'daily') return 10
  return 8
}

export function sectorDefaultBenchmark(
  mode: RrgMode,
  industryLevel: 'L1' | 'L2',
  parentId: string,
  firstParentId: string,
): string | null {
  if (mode !== 'us_gics' && mode !== 'cn_sw') return null
  const l1Bench = mode === 'us_gics' ? 'us_sp500' : 'cn_sw_a'
  if (industryLevel === 'L2') return parentId || firstParentId || l1Bench
  return l1Bench
}

export function defaultBenchmarkForMode(mode: RrgMode, data: RrgData | null): string {
  if (!data) return ''
  if (mode === 'country') {
    return data.benchmarks?.find((b) => b.id === 'cn_csi300')?.id ?? data.benchmarks?.[0]?.id ?? ''
  }
  if (mode === 'cn_sw') {
    return data.benchmarks?.find((b) => b.id === 'cn_sw_a')?.id ?? data.benchmarks?.[0]?.id ?? ''
  }
  if (mode === 'us_gics') {
    return data.benchmarks?.find((b) => b.id === 'us_sp500')?.id ?? data.benchmarks?.[0]?.id ?? ''
  }
  return data.benchmarks?.[0]?.id ?? data.series[0]?.id ?? ''
}

export function jdkParamsFor(_data: RrgData | null, freq: RrgFreq): { window: number; rocPeriod: number } {
  return DEFAULT_JDK_PARAMS[freq]
}

export type RrgViewportMode = 'centered' | 'max' | 'fit'

export const RRG_VIEWPORT_OPTIONS: { id: RrgViewportMode; label: string; hint: string }[] = [
  { id: 'centered', label: '居中', hint: '以基准 100 为中心，按区间数据最大值对称定界；时间滑动时视窗不变' },
  { id: 'max', label: '最大值', hint: '以区间数据最大 RS 为中心对称缩放；时间滑动时视窗不变' },
  { id: 'fit', label: '适配数据', hint: '按区间极值铺满视窗；时间滑动时视窗不变' },
]

export type RrgViewport = {
  minX: number
  maxX: number
  minY: number
  maxY: number
  /** 视窗对称中心（居中=100，最大值=数据峰值） */
  anchorX: number
  anchorY: number
}

type RrgExtentInput = { displayPoints: RrgPoint[]; points: RrgPoint[] }

export function collectRrgExtents(trails: RrgExtentInput[]): { xs: number[]; ys: number[] } {
  const xs: number[] = []
  const ys: number[] = []
  for (const t of trails) {
    for (const p of t.displayPoints) {
      xs.push(p.rsRatio)
      ys.push(p.rsMomentum)
    }
    const last = t.points[t.points.length - 1]
    if (last) {
      xs.push(last.rsRatio)
      ys.push(last.rsMomentum)
    }
  }
  return { xs, ys }
}

/** 从完整 RRG 序列收集区间极值（用于固定视窗，不随播放窗口滑动） */
export function collectRrgExtentsFromPaths(
  paths: Iterable<RrgPoint[]>,
  startDate: string,
  endDate: string,
): { xs: number[]; ys: number[] } {
  const xs: number[] = []
  const ys: number[] = []
  for (const pts of paths) {
    for (const p of pts) {
      if (p.date >= startDate && p.date <= endDate) {
        xs.push(p.rsRatio)
        ys.push(p.rsMomentum)
      }
    }
  }
  return { xs, ys }
}

export function computeRrgViewport(
  xs: number[],
  ys: number[],
  mode: RrgViewportMode = 'centered',
): RrgViewport {
  if (!xs.length) return { minX: 90, maxX: 110, minY: 90, maxY: 110, anchorX: 100, anchorY: 100 }

  if (mode === 'fit') {
    const loX = Math.min(...xs, 100)
    const hiX = Math.max(...xs, 100)
    const loY = Math.min(...ys, 100)
    const hiY = Math.max(...ys, 100)
    const padX = Math.max((hiX - loX) * 0.06, 1.2)
    const padY = Math.max((hiY - loY) * 0.06, 1.2)
    return {
      minX: loX - padX,
      maxX: hiX + padX,
      minY: loY - padY,
      maxY: hiY + padY,
      anchorX: 100,
      anchorY: 100,
    }
  }

  const pad = 2
  const loX = Math.min(...xs, 100)
  const hiX = Math.max(...xs, 100)
  const loY = Math.min(...ys, 100)
  const hiY = Math.max(...ys, 100)
  const anchorX = mode === 'max' ? Math.max(...xs) : 100
  const anchorY = mode === 'max' ? Math.max(...ys) : 100
  // 居中/最大值：以中心到区间极值的最大距离对称定界，使数据最大值落在视窗边界
  const dx = Math.max(anchorX - loX, hiX - anchorX, 6) + pad
  const dy = Math.max(anchorY - loY, hiY - anchorY, 6) + pad
  return { minX: anchorX - dx, maxX: anchorX + dx, minY: anchorY - dy, maxY: anchorY + dy, anchorX, anchorY }
}

/** 生成坐标轴刻度（去重、含基准 100 时保留） */
export function rrgAxisTicks(min: number, max: number, center = 100): number[] {
  const ticks = [min, max]
  if (center >= min && center <= max) ticks.push(center)
  return [...new Set(ticks.map((v) => Math.round(v * 10) / 10))].sort((a, b) => a - b)
}

/** 日频 → 日/周/月/年（日度取原始日收盘，其余取区间末） */
export function resamplePrices(points: PricePoint[], freq: RrgFreq): PricePoint[] {
  if (!points.length) return []
  if (freq === 'daily') {
    const buckets = new Map<string, PricePoint>()
    for (const [date, value] of points) {
      const key = date.slice(0, 10)
      buckets.set(key, [key, value])
    }
    return [...buckets.entries()].sort((a, b) => a[0].localeCompare(b[0])).map(([, p]) => p)
  }
  if (freq === 'weekly') {
    // 按周：对齐到当周周五，取该周最后观测
    const buckets = new Map<string, PricePoint>()
    for (const [date, value] of points) {
      const d = new Date(`${date}T00:00:00`)
      if (Number.isNaN(d.getTime())) continue
      const day = d.getDay() // 0 Sun .. 6 Sat
      const delta = day === 0 ? -2 : day === 6 ? -1 : 5 - day
      const fri = new Date(d)
      fri.setDate(d.getDate() + delta)
      const key = `${fri.getFullYear()}-${String(fri.getMonth() + 1).padStart(2, '0')}-${String(fri.getDate()).padStart(2, '0')}`
      buckets.set(key, [key, value])
    }
    return [...buckets.entries()].sort((a, b) => a[0].localeCompare(b[0])).map(([, p]) => p)
  }
  if (freq === 'monthly') {
    const buckets = new Map<string, PricePoint>()
    for (const [date, value] of points) {
      const key = `${date.slice(0, 7)}-01`
      buckets.set(key, [key, value])
    }
    return [...buckets.entries()].sort((a, b) => a[0].localeCompare(b[0])).map(([, p]) => p)
  }
  // yearly
  const buckets = new Map<string, PricePoint>()
  for (const [date, value] of points) {
    const key = `${date.slice(0, 4)}-12-31`
    buckets.set(key, [key, value])
  }
  return [...buckets.entries()].sort((a, b) => a[0].localeCompare(b[0])).map(([, p]) => p)
}

export function trailDefaultFor(data: RrgData | null, freq: RrgFreq): number {
  const td = data?.rrg?.trail_default
  if (td == null) return DEFAULT_TRAIL[freq]
  if (typeof td === 'number') return td
  return td[freq] ?? DEFAULT_TRAIL[freq]
}
