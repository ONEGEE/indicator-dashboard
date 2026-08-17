/** RRG 右多策略：庙旺得利旅程状态机（月度 L1） */

import {
  computeJdkRrg,
  defaultBenchmarkForMode,
  quadrantOf,
  resamplePrices,
  type RrgData,
  type RrgMode,
  type RrgPoint,
  type RrgSeriesMeta,
} from './rrg-lib'

export type RightLongStage = '利' | '得' | '旺' | '庙'
export type JourneyStatus = 'active' | 'falsified' | 'review'
export type JourneyView = 'active' | 'falsified' | 'all'

export type RightLongParams = {
  liMomMinInWindow: number
  deHoldMonths: number
  wangDistPct: number
  wangRatioMin: number
  miaoLeadingMonths: number
  reviewCapMonths: number
}

export type RightLongPolicy = {
  hardcode: {
    shared: {
      wang_dist_pct: number
      wang_ratio_min: number
      review_cap_months: number
    }
    us_gics: { li_mom_min_in_window: number; de_hold_months: number; miao_leading_months: number }
    cn_sw: { li_mom_min_in_window: number; de_hold_months: number; miao_leading_months: number }
  }
  trade_policy_from_backtest: Record<string, string>
  key_findings?: string[]
}

export type JourneySegment = {
  stage: RightLongStage
  start: string
  end: string
}

export type JourneyEvent = {
  date: string
  type: 'enter' | 'upgrade' | 'falsify' | 'review'
  stage: RightLongStage
  note: string
}

export type Journey = {
  journeyId: number
  assetId: string
  assetName: string
  openedAt: string
  closedAt: string | null
  status: JourneyStatus
  currentStage: RightLongStage | null
  reachedDe: boolean
  reachedMiao: boolean
  falsifiedAt: string | null
  falsifiedReason: string | null
  segments: JourneySegment[]
  events: JourneyEvent[]
  weeklyNote: string
  decisionNote: string
}

export type MonthlyRow = RrgPoint & {
  quadrant: string
  barsInQuadrant: number
  momAbove3: number
  ratioAbove3: number
  distance: number
  distPct: number
}

export const STAGE_COLORS: Record<RightLongStage, string> = {
  利: '#6b8cce',
  得: '#0f5c4c',
  旺: '#c9a227',
  庙: '#9f1239',
}

export const STAGE_LABELS: Record<RightLongStage, string> = {
  利: '利 · 早期观察',
  得: '得 · 强弱确认',
  旺: '旺 · 强度保持',
  庙: '庙 · 持续跑赢',
}

export const RIGHT_LONG_MODES: { id: RrgMode; label: string; url: string }[] = [
  { id: 'us_gics', label: '美股 GICS 一级', url: 'rrg_prices_us_gics.json' },
  { id: 'cn_sw', label: '申万一级', url: 'rrg_prices_cn_sw.json' },
]

export function defaultParams(mode: RrgMode, policy: RightLongPolicy): RightLongParams {
  const spec = policy.hardcode[mode as 'us_gics' | 'cn_sw']
  const shared = policy.hardcode.shared
  return {
    liMomMinInWindow: spec.li_mom_min_in_window,
    deHoldMonths: spec.de_hold_months,
    wangDistPct: shared.wang_dist_pct,
    wangRatioMin: shared.wang_ratio_min,
    miaoLeadingMonths: spec.miao_leading_months,
    reviewCapMonths: shared.review_cap_months,
  }
}

function monthKey(d: string): string {
  return d.slice(0, 7)
}

function momOk(row: MonthlyRow, p: RightLongParams): boolean {
  return row.momAbove3 >= p.liMomMinInWindow
}

function isWang(row: MonthlyRow, p: RightLongParams): boolean {
  return row.rsRatio >= 100 && row.rsMomentum >= 100 && (row.distPct >= p.wangDistPct || row.rsRatio >= p.wangRatioMin)
}

function isMiao(row: MonthlyRow, p: RightLongParams): boolean {
  return (
    row.quadrant === 'leading' &&
    row.rsRatio >= 100 &&
    row.barsInQuadrant >= p.miaoLeadingMonths &&
    row.ratioAbove3 >= 3
  )
}

function classifyStage(row: MonthlyRow, p: RightLongParams, reachedDe: boolean): RightLongStage | null {
  if (isMiao(row, p) && reachedDe) return '庙'
  if (isWang(row, p) && reachedDe) return '旺'
  if (row.rsRatio >= 100 && row.rsMomentum >= 100 && reachedDe) return '得'
  if (momOk(row, p) && row.rsRatio < 100) return '利'
  if (reachedDe && row.rsRatio >= 100) return '得'
  return null
}

function canOpen(row: MonthlyRow, p: RightLongParams): RightLongStage | null {
  if (momOk(row, p) && row.rsRatio < 100) return '利'
  if (row.rsRatio >= 100 && row.rsMomentum >= 100) {
    if (isMiao(row, p)) return '庙'
    if (isWang(row, p)) return '旺'
    return '得'
  }
  return null
}

function appendSegment(j: Journey, date: string, stage: RightLongStage) {
  const last = j.segments[j.segments.length - 1]
  if (last && last.stage === stage) {
    last.end = date
  } else {
    j.segments.push({ stage, start: date, end: date })
    if (last) {
      j.events.push({ date, type: 'upgrade', stage, note: `${last.stage} → ${stage}` })
    }
  }
  j.currentStage = stage
}

function weeklyTexture(asset: RrgSeriesMeta, bench: RrgSeriesMeta): string {
  const wAsset = resamplePrices(asset.points, 'weekly')
  const wBench = resamplePrices(bench.points, 'weekly')
  const pts = computeJdkRrg(wAsset, wBench, { window: 14, rocPeriod: 10 })
  if (pts.length < 4) return '周度数据不足'
  const tail = pts.slice(-4)
  const momWeeks = tail.filter((x) => x.rsMomentum >= 100).length
  const ratioAbove = tail[tail.length - 1].rsRatio >= 100
  return `近4周 Mom≥100 共 ${momWeeks} 周；最新 Ratio ${ratioAbove ? '已' : '未'}站上 100`
}

function decisionNote(stage: RightLongStage | null, status: JourneyStatus, policy: RightLongPolicy): string {
  if (status === 'falsified') return '已证伪：不加仓，保留记录'
  if (status === 'review') return policy.trade_policy_from_backtest['庙'] + '（满复审期，请人工复审）'
  if (!stage) return '—'
  return policy.trade_policy_from_backtest[stage] ?? ''
}

export function buildMonthlyRows(
  data: RrgData,
  benchmarkId: string,
  level: 'L1' | 'L2' = 'L1',
): Map<string, MonthlyRow[]> {
  const bench = data.series.find((s) => s.id === benchmarkId)
  if (!bench) return new Map()

  const assets = data.series.filter((s) => {
    if (s.id === benchmarkId || s.level === 'bench') return false
    if (level === 'L1') return s.level === 'L1' || s.level == null
    return s.level === level
  })

  const monthlyByAsset: { id: string; pts: RrgPoint[] }[] = []
  for (const s of assets) {
    const m = resamplePrices(s.points, 'monthly')
    const b = resamplePrices(bench.points, 'monthly')
    const pts = computeJdkRrg(m, b, { window: 12, rocPeriod: 3 })
    if (pts.length >= 8) monthlyByAsset.push({ id: s.id, pts })
  }

  const allByDate = new Map<string, number[]>()
  const draft = new Map<string, MonthlyRow[]>()

  for (const { id, pts } of monthlyByAsset) {
    const rows: MonthlyRow[] = []
    let prevQ = ''
    let bars = 0
    for (let i = 0; i < pts.length; i++) {
      const p = pts[i]
      const q = quadrantOf(p.rsRatio, p.rsMomentum)
      bars = i > 0 && q === prevQ ? bars + 1 : 1
      prevQ = q
      const dist = Math.hypot(p.rsRatio - 100, p.rsMomentum - 100)
      const mk = monthKey(p.date)
      if (!allByDate.has(mk)) allByDate.set(mk, [])
      allByDate.get(mk)!.push(dist)
      rows.push({
        ...p,
        quadrant: q,
        barsInQuadrant: bars,
        momAbove3: 0,
        ratioAbove3: 0,
        distance: dist,
        distPct: 0.5,
      })
    }
    draft.set(id, rows)
  }

  for (const rows of draft.values()) {
    for (const r of rows) {
      const pool = [...(allByDate.get(monthKey(r.date)) ?? [])].sort((a, b) => a - b)
      const idx = pool.findIndex((d) => d >= r.distance)
      r.distPct = idx < 0 ? 1 : (idx + 1) / Math.max(pool.length, 1)
    }
    for (let i = 0; i < rows.length; i++) {
      let ma = 0
      let ra = 0
      for (let j = Math.max(0, i - 2); j <= i; j++) {
        if (rows[j].rsMomentum >= 100) ma++
        if (rows[j].rsRatio >= 100) ra++
      }
      rows[i].momAbove3 = ma
      rows[i].ratioAbove3 = ra
    }
  }

  return draft
}

export function simulateJourneys(
  monthlyByAsset: Map<string, MonthlyRow[]>,
  assetNames: Map<string, string>,
  params: RightLongParams,
  policy: RightLongPolicy,
  weeklyCtx: Map<string, string>,
): Journey[] {
  const journeys: Journey[] = []
  let jid = 0

  for (const [assetId, rows] of monthlyByAsset) {
    let active: Journey | null = null
    let crossIdx: number | null = null
    let deConfirmed = false
    let monthsInMiao = 0

    for (let i = 0; i < rows.length; i++) {
      const row = rows[i]
      const prev = i > 0 ? rows[i - 1] : null
      const date = row.date

      if (prev && prev.rsRatio < 100 && row.rsRatio >= 100 && row.rsMomentum >= 100) {
        crossIdx = i
        deConfirmed = false
      }
      if (crossIdx != null && !deConfirmed && i >= crossIdx + params.deHoldMonths - 1) {
        let ok = true
        for (let j = crossIdx; j <= i; j++) {
          if (rows[j].rsRatio < 100) ok = false
        }
        if (ok && row.rsMomentum >= 100) deConfirmed = true
      }

      if (!active) {
        const open = canOpen(row, params)
        if (!open) continue
        jid += 1
        active = {
          journeyId: jid,
          assetId,
          assetName: assetNames.get(assetId) ?? assetId,
          openedAt: date,
          closedAt: null,
          status: 'active',
          currentStage: open,
          reachedDe: open !== '利',
          reachedMiao: open === '庙',
          falsifiedAt: null,
          falsifiedReason: null,
          segments: [],
          events: [{ date, type: 'enter', stage: open, note: `进入${open}` }],
          weeklyNote: weeklyCtx.get(assetId) ?? '',
          decisionNote: '',
        }
        appendSegment(active, date, open)
        monthsInMiao = open === '庙' ? 1 : 0
        continue
      }

      if (active.status !== 'active') continue

      if (!active.reachedDe && !deConfirmed) {
        if (!momOk(row, params)) {
          active.status = 'falsified'
          active.falsifiedAt = date
          active.falsifiedReason = '利：动能回落，未出现得'
          active.closedAt = date
          active.events.push({ date, type: 'falsify', stage: active.currentStage ?? '利', note: active.falsifiedReason })
          appendSegment(active, date, active.currentStage ?? '利')
          active.decisionNote = decisionNote(null, 'falsified', policy)
          journeys.push(active)
          active = null
          crossIdx = null
          deConfirmed = false
          monthsInMiao = 0
          continue
        }
      } else {
        if (row.rsRatio < 100) {
          active.status = 'falsified'
          active.falsifiedAt = date
          active.falsifiedReason = 'Ratio 跌破 100'
          active.closedAt = date
          active.events.push({ date, type: 'falsify', stage: active.currentStage ?? '得', note: active.falsifiedReason })
          if (active.currentStage) appendSegment(active, date, active.currentStage)
          active.decisionNote = decisionNote(null, 'falsified', policy)
          journeys.push(active)
          active = null
          crossIdx = null
          deConfirmed = false
          monthsInMiao = 0
          continue
        }
      }

      if (deConfirmed) active.reachedDe = true
      const stage = classifyStage(row, params, active.reachedDe || deConfirmed)
      if (stage === '庙') {
        active.reachedMiao = true
        monthsInMiao += 1
      } else if (active.reachedMiao) {
        monthsInMiao = 0
      }

      if (active.reachedMiao && monthsInMiao >= params.reviewCapMonths) {
        active.status = 'review'
        active.closedAt = date
        active.events.push({ date, type: 'review', stage: '庙', note: '满 12 个月复审' })
      }

      if (stage) appendSegment(active, date, stage)
      else if (active.currentStage) appendSegment(active, date, active.currentStage)

      active.weeklyNote = weeklyCtx.get(assetId) ?? active.weeklyNote
      active.decisionNote = decisionNote(active.currentStage, active.status, policy)
    }

    if (active) {
      active.decisionNote = decisionNote(active.currentStage, active.status, policy)
      journeys.push(active)
    }
  }

  return journeys.sort((a, b) => b.openedAt.localeCompare(a.openedAt))
}

export function buildJourneysFromRrg(
  data: RrgData,
  mode: RrgMode,
  params: RightLongParams,
  policy: RightLongPolicy,
): Journey[] {
  const benchId = defaultBenchmarkForMode(mode, data)
  const bench = data.series.find((s) => s.id === benchId)
  if (!bench) return []

  const level = (data.rrg?.default_level as 'L1' | 'L2') ?? 'L1'
  const assets = data.series.filter((s) => s.id !== benchId && s.level !== 'bench' && (s.level === level || !s.level))
  const assetNames = new Map(assets.map((s) => [s.id, s.name]))
  const weeklyCtx = new Map<string, string>()
  for (const s of assets) {
    weeklyCtx.set(s.id, weeklyTexture(s, bench))
  }

  const monthlyByAsset = buildMonthlyRows(data, benchId, level)
  return simulateJourneys(monthlyByAsset, assetNames, params, policy, weeklyCtx)
}

export function timelineMonths(journeys: Journey[], count = 18): string[] {
  const keys = new Set<string>()
  for (const j of journeys) {
    for (const s of j.segments) {
      keys.add(monthKey(s.start))
      keys.add(monthKey(s.end))
    }
  }
  const sorted = [...keys].sort()
  if (sorted.length <= count) return sorted
  return sorted.slice(-count)
}

export function segmentAtMonth(j: Journey, ym: string): RightLongStage | null {
  for (const s of j.segments) {
    if (monthKey(s.start) <= ym && monthKey(s.end) >= ym) return s.stage
  }
  return null
}

export function filterJourneys(
  journeys: Journey[],
  view: JourneyView,
  deOnly: boolean,
): Journey[] {
  let list = journeys
  if (view === 'active') list = list.filter((j) => j.status === 'active' || j.status === 'review')
  else if (view === 'falsified') list = list.filter((j) => j.status === 'falsified')

  if (deOnly) list = list.filter((j) => j.reachedDe && (j.status === 'active' || j.status === 'review'))

  if (view === 'all') {
    const live = list.filter((j) => j.status !== 'falsified')
    const dead = list.filter((j) => j.status === 'falsified')
    return [...live, ...dead]
  }
  return list
}
