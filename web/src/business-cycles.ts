/**
 * 经济周期划分数据。
 * - 美国：NBER Business Cycle Dating Committee（峰→谷为收缩，谷→下一峰为扩张）
 * - 中国：中国社科院刘树成体系（GDP 增速「谷—谷」增长型周期；无官方等价 NBER 机构）
 *
 * 中国峰位为文献常用近似（增长型周期），用于扩张/收缩底色，非官方法定日期。
 */

export type CycleKind = 'expansion' | 'contraction'

export type CyclePhase = {
  start: string // YYYY-MM-DD
  end: string
  kind: CycleKind
  label: string
}

export type CycleEpisode = {
  id: string
  label: string
  start: string
  end: string
  phases: CyclePhase[]
  /** 是否覆盖「有数据以来」整段并只用于底色 */
  fullHistory?: boolean
}

export type CycleSource = 'nber' | 'cn_cass'

function monthStart(ym: string): string {
  // ym: YYYY-MM
  return `${ym}-01`
}

function monthEnd(ym: string): string {
  const [y, m] = ym.split('-').map(Number)
  const last = new Date(y, m, 0).getDate()
  return `${y}-${String(m).padStart(2, '0')}-${String(last).padStart(2, '0')}`
}

/** NBER 峰月 / 谷月（YYYY-MM），来源 nber.org */
const NBER_TURNS: { peak: string; trough: string }[] = [
  { peak: '1945-02', trough: '1945-10' },
  { peak: '1948-11', trough: '1949-10' },
  { peak: '1953-07', trough: '1954-05' },
  { peak: '1957-08', trough: '1958-04' },
  { peak: '1960-04', trough: '1961-02' },
  { peak: '1969-12', trough: '1970-11' },
  { peak: '1973-11', trough: '1975-03' },
  { peak: '1980-01', trough: '1980-07' },
  { peak: '1981-07', trough: '1982-11' },
  { peak: '1990-07', trough: '1991-03' },
  { peak: '2001-03', trough: '2001-11' },
  { peak: '2007-12', trough: '2009-06' },
  { peak: '2020-02', trough: '2020-04' },
]

const NBER_LABELS: Record<string, string> = {
  '2007-12': '大衰退',
  '2001-03': '科网泡沫后',
  '1990-07': '1990–91 衰退',
  '1981-07': '1981–82 衰退',
  '1980-01': '1980 衰退',
  '1973-11': '石油危机',
  '2020-02': '疫情短衰退',
}

function buildNberPhases(): CyclePhase[] {
  const phases: CyclePhase[] = []
  for (let i = 0; i < NBER_TURNS.length; i++) {
    const { peak, trough } = NBER_TURNS[i]
    const name = NBER_LABELS[peak] ?? `${peak} 收缩`
    phases.push({
      start: monthStart(peak),
      end: monthEnd(trough),
      kind: 'contraction',
      label: name,
    })
    const next = NBER_TURNS[i + 1]
    if (next) {
      // 扩张：本谷次月 → 下一峰月
      const [ty, tm] = trough.split('-').map(Number)
      const nextMonth = tm === 12 ? `${ty + 1}-01` : `${ty}-${String(tm + 1).padStart(2, '0')}`
      phases.push({
        start: monthStart(nextMonth),
        end: monthEnd(next.peak),
        kind: 'expansion',
        label: `${trough}→${next.peak} 扩张`,
      })
    } else {
      // 当前扩张：2020-04 谷之后
      phases.push({
        start: monthStart('2020-05'),
        end: '2099-12-31',
        kind: 'expansion',
        label: '2020 谷后扩张（进行中）',
      })
    }
  }
  return phases
}

function buildNberEpisodes(phases: CyclePhase[]): CycleEpisode[] {
  const episodes: CycleEpisode[] = [
    {
      id: 'nber_all',
      label: '全区间（NBER 扩张/收缩底色）',
      start: monthStart('1945-02'),
      end: '2099-12-31',
      phases,
      fullHistory: true,
    },
  ]
  // 每个完整周期：上一谷 → 本谷（含其间扩张+收缩）
  for (let i = 0; i < NBER_TURNS.length; i++) {
    const prevTrough = i === 0 ? '1945-02' : NBER_TURNS[i - 1].trough
    const { peak, trough } = NBER_TURNS[i]
    const start =
      i === 0
        ? monthStart(peak)
        : (() => {
            const [ty, tm] = prevTrough.split('-').map(Number)
            const nextMonth = tm === 12 ? `${ty + 1}-01` : `${ty}-${String(tm + 1).padStart(2, '0')}`
            return monthStart(nextMonth)
          })()
    const end = monthEnd(trough)
    const slice = phases.filter((p) => p.end >= start && p.start <= end)
    const tag = NBER_LABELS[peak] ?? `${peak}→${trough}`
    episodes.push({
      id: `nber_${peak}_${trough}`,
      label: `${tag}（${peak} → ${trough}）`,
      start,
      end,
      phases: slice.map((p) => ({
        ...p,
        start: p.start < start ? start : p.start,
        end: p.end > end ? end : p.end,
      })),
    })
  }
  return episodes
}

/**
 * 中国增长型周期（谷—谷），主要依据刘树成（社科院）及后续延伸。
 * 峰位为文献常用近似，用于底色分段。
 */
const CN_CYCLES: { troughStart: string; peak: string; troughEnd: string; label: string }[] = [
  { troughStart: '1982-01', peak: '1984-12', troughEnd: '1986-12', label: '改革后第2轮' },
  { troughStart: '1987-01', peak: '1988-08', troughEnd: '1990-12', label: '改革后第3轮' },
  { troughStart: '1991-01', peak: '1992-12', troughEnd: '1999-12', label: '软着陆周期' },
  { troughStart: '2000-01', peak: '2007-06', troughEnd: '2009-06', label: '入世—金融危机' },
  { troughStart: '2009-07', peak: '2011-06', troughEnd: '2016-12', label: '四万亿后换挡' },
  { troughStart: '2017-01', peak: '2017-12', troughEnd: '2020-02', label: '疫情前下行' },
  { troughStart: '2020-03', peak: '2021-06', troughEnd: '2024-12', label: '疫情后修复（进行中近似）' },
]

function buildCnPhases(): CyclePhase[] {
  const phases: CyclePhase[] = []
  for (const c of CN_CYCLES) {
    phases.push({
      start: monthStart(c.troughStart),
      end: monthEnd(c.peak),
      kind: 'expansion',
      label: `${c.label}·扩张`,
    })
    const [py, pm] = c.peak.split('-').map(Number)
    const afterPeak = pm === 12 ? `${py + 1}-01` : `${py}-${String(pm + 1).padStart(2, '0')}`
    phases.push({
      start: monthStart(afterPeak),
      end: monthEnd(c.troughEnd),
      kind: 'contraction',
      label: `${c.label}·收缩`,
    })
  }
  // 末轮谷后若数据延续，补一段进行中扩张
  phases.push({
    start: monthStart('2025-01'),
    end: '2099-12-31',
    kind: 'expansion',
    label: '新一轮扩张（进行中近似）',
  })
  return phases
}

function buildCnEpisodes(phases: CyclePhase[]): CycleEpisode[] {
  const episodes: CycleEpisode[] = [
    {
      id: 'cn_all',
      label: '全区间（社科院增长型周期底色）',
      start: monthStart('1982-01'),
      end: '2099-12-31',
      phases,
      fullHistory: true,
    },
  ]
  for (const c of CN_CYCLES) {
    const start = monthStart(c.troughStart)
    const end = monthEnd(c.troughEnd)
    const slice = phases.filter((p) => p.end >= start && p.start <= end)
    episodes.push({
      id: `cn_${c.troughStart}_${c.troughEnd}`,
      label: `${c.label}（${c.troughStart} → ${c.troughEnd}）`,
      start,
      end,
      phases: slice.map((p) => ({
        ...p,
        start: p.start < start ? start : p.start,
        end: p.end > end ? end : p.end,
      })),
    })
  }
  return episodes
}

const NBER_PHASES = buildNberPhases()
const CN_PHASES = buildCnPhases()

function currentNberPhase(): CyclePhase {
  return NBER_PHASES[NBER_PHASES.length - 1]
}

function currentCnPhase(asOf: string): CyclePhase {
  for (let i = CN_PHASES.length - 1; i >= 0; i--) {
    const p = CN_PHASES[i]
    if (asOf >= p.start && asOf <= p.end) return p
  }
  return CN_PHASES[CN_PHASES.length - 1]
}

export function getCurrentPhase(source: CycleSource, asOf: string): CyclePhase {
  const phases = source === 'nber' ? NBER_PHASES : CN_PHASES
  for (let i = phases.length - 1; i >= 0; i--) {
    const p = phases[i]
    if (asOf >= p.start && asOf <= p.end) return p
  }
  return phases[phases.length - 1]
}

export function getAllPhases(source: CycleSource): CyclePhase[] {
  return source === 'nber' ? NBER_PHASES : CN_PHASES
}

export const CYCLE_CATALOG: Record<CycleSource, { title: string; note: string; episodes: CycleEpisode[] }> = {
  nber: {
    title: '美国 NBER',
    note: '来源：NBER Business Cycle Dating Committee。收缩=峰→谷，扩张=谷→下一峰。',
    episodes: [
      {
        id: 'nber_current',
        label: '当前周期（进行中）',
        start: currentNberPhase().start,
        end: '2099-12-31',
        phases: [currentNberPhase()],
      },
      ...buildNberEpisodes(NBER_PHASES),
    ],
  },
  cn_cass: {
    title: '中国社科院（刘树成）',
    note: '来源：刘树成等「谷—谷」增长型周期划分（非官方法定日期）。峰位为文献常用近似，用于扩张/收缩底色。',
    episodes: [
      {
        id: 'cn_current',
        label: '当前周期（进行中）',
        start: currentCnPhase('2099-01-01').start,
        end: '2099-12-31',
        phases: [CN_PHASES[CN_PHASES.length - 1]],
      },
      ...buildCnEpisodes(CN_PHASES),
    ],
  },
}

export function getEpisode(source: CycleSource, id: string): CycleEpisode | undefined {
  return CYCLE_CATALOG[source].episodes.find((e) => e.id === id)
}

export function phasesToBands(
  phases: CyclePhase[],
  timeline: string[],
): { startIdx: number; endIdx: number; kind: CycleKind; label: string }[] {
  if (!timeline.length || !phases.length) return []
  const first = timeline[0]
  const last = timeline[timeline.length - 1]
  const bands: { startIdx: number; endIdx: number; kind: CycleKind; label: string }[] = []
  for (const p of phases) {
    if (p.end < first || p.start > last) continue
    let startIdx = timeline.findIndex((d) => d >= p.start)
    if (startIdx < 0) startIdx = 0
    let endIdx = timeline.length - 1
    for (let i = timeline.length - 1; i >= 0; i--) {
      if (timeline[i] <= p.end) {
        endIdx = i
        break
      }
    }
    if (endIdx < startIdx) continue
    bands.push({ startIdx, endIdx, kind: p.kind, label: p.label })
  }
  return bands
}

/** 若区间内无匹配阶段，默认整段视为扩张（便于「当前周期」视图） */
export function phasesToBandsWithDefault(
  phases: CyclePhase[],
  timeline: string[],
  defaultKind: CycleKind = 'expansion',
): { startIdx: number; endIdx: number; kind: CycleKind; label: string }[] {
  const bands = phasesToBands(phases, timeline)
  if (bands.length || !timeline.length) return bands
  return [
    {
      startIdx: 0,
      endIdx: timeline.length - 1,
      kind: defaultKind,
      label: defaultKind === 'expansion' ? '扩张（默认）' : '收缩（默认）',
    },
  ]
}
