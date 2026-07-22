export type MarketCapPoint = [string, number]

export type IndicatorDocumentation = {
  summary?: string
  data_source?: string
  methodology?: string
  frequency?: string
  update_rule?: string
  update_schedule?: string
  last_data_date?: string | null
  last_updated?: string | null
  expected_next_update?: string | null
  notes?: string
}

export type MarketCapSeries = {
  id: string
  name: string
  pillar: string
  pillar_label: string
  method?: string
  authority?: string
  unit?: string
  documentation?: IndicatorDocumentation
  points: MarketCapPoint[]
}

export type MarketCapLatestItem = {
  id: string
  name: string
  pillar: string
  pillar_label: string
  date: string
  value_usd: number
  share: number
}

export type SharePanelMeta = {
  name: string
  pillar: string
  pillar_label: string
  authority?: string
  method?: string
}

/** 预计算月度规模占比面板：按所选区间切片后可再按类别重算占比。 */
export type SharePanel = {
  ids: string[]
  meta: Record<string, SharePanelMeta>
  dates: string[]
  totals: (number | null)[]
  values: (number | null)[][]
  /** @deprecated 占比由前端按所选样本从 values 重算 */
  shares?: (number | null)[][]
  csv?: string
}

export type MarketCapData = {
  generated_at: string
  display_end?: string
  counts: {
    with_marketcap: number
    total_usd_latest: number
    share_months?: number
  }
  series: MarketCapSeries[]
  latest: MarketCapLatestItem[]
  share_panel?: SharePanel
}

export type ShareFrameItem = {
  id: string
  name: string
  pillar: string
  pillar_label: string
  value: number
  share: number
}

export type ShareFrame = {
  date: string
  total: number
  shares: ShareFrameItem[]
}

export const PILLAR_COLORS: Record<string, string> = {
  equity: '#0f5c4c',
  bond: '#3d6b8c',
  precious_metal: '#c9a227',
  commodity: '#8a4b1f',
  crypto: '#f7931a',
  fx: '#6b645a',
  real_estate: '#7b5ea7',
}

export function formatUsd(value: number, compact = true): string {
  if (!Number.isFinite(value)) return '—'
  if (compact) {
    const abs = Math.abs(value)
    if (abs >= 1e12) return `$${(value / 1e12).toFixed(2)}T`
    if (abs >= 1e9) return `$${(value / 1e9).toFixed(1)}B`
    if (abs >= 1e6) return `$${(value / 1e6).toFixed(1)}M`
  }
  return value.toLocaleString('en-US', {
    style: 'currency',
    currency: 'USD',
    maximumFractionDigits: 0,
  })
}

export function formatPct(value: number): string {
  return `${(value * 100).toFixed(1)}%`
}

function ym(date: string): string {
  return date.slice(0, 7)
}

/** 从各资产序列现场对齐计算月度占比（无预计算面板时的回退）。 */
export function buildShareFramesFromSeries(
  series: MarketCapSeries[],
  opts: { start: string; end: string; pillar?: string },
): ShareFrame[] {
  const { start, end, pillar = 'all' } = opts
  const startYm = ym(start)
  const endYm = ym(end)
  const byDate = new Map<string, ShareFrameItem[]>()

  for (const s of series) {
    if (pillar !== 'all' && s.pillar !== pillar) continue
    for (const [date, value] of s.points) {
      if (!Number.isFinite(value) || value <= 0) continue
      const key = ym(date)
      if (key < startYm || key > endYm) continue
      const iso = `${key}-01`
      const list = byDate.get(iso) ?? []
      list.push({
        id: s.id,
        name: s.name,
        pillar: s.pillar,
        pillar_label: s.pillar_label,
        value,
        share: 0,
      })
      byDate.set(iso, list)
    }
  }

  return [...byDate.entries()]
    .sort(([a], [b]) => a.localeCompare(b))
    .map(([date, items]) => {
      const total = items.reduce((sum, x) => sum + x.value, 0)
      const shares = items
        .map((x) => ({ ...x, share: total > 0 ? x.value / total : 0 }))
        .sort((a, b) => b.share - a.share)
      return { date, total, shares }
    })
    .filter((f) => f.shares.length > 0 && f.total > 0)
}

/** 从预计算面板切片，并按可见资产集合重新归一化占比。 */
export function sliceSharePanel(
  panel: SharePanel,
  opts: { start: string; end: string; pillar?: string },
): ShareFrame[] {
  const { start, end, pillar = 'all' } = opts
  const startYm = ym(start)
  const endYm = ym(end)
  const idIndex = panel.ids
    .map((id, i) => ({ id, i, meta: panel.meta[id] }))
    .filter((x) => x.meta && (pillar === 'all' || x.meta.pillar === pillar))

  if (!idIndex.length || !panel.dates?.length) return []

  const frames: ShareFrame[] = []
  for (let row = 0; row < panel.dates.length; row++) {
    const date = panel.dates[row]
    const key = ym(date)
    if (key < startYm || key > endYm) continue
    const items: ShareFrameItem[] = []
    let total = 0
    for (const { id, i, meta } of idIndex) {
      const v = panel.values[row]?.[i]
      if (v == null || !Number.isFinite(v) || v <= 0) continue
      total += v
      items.push({
        id,
        name: meta.name,
        pillar: meta.pillar,
        pillar_label: meta.pillar_label,
        value: v,
        share: 0,
      })
    }
    if (items.length === 0 || total <= 0) continue
    for (const item of items) item.share = item.value / total
    items.sort((a, b) => b.share - a.share)
    frames.push({ date, total, shares: items })
  }
  return frames
}
