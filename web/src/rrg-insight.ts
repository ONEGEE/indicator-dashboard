/** RRG 特征提取与解读（措辞已按月度回测校准）
 *
 * 回测要点（美股 GICS / 申万 L1 / 国家 / 大类，月度）：
 * - H6 动量领先 Ratio：唯一跨模式强支持 → 可作「早期观察」
 * - 经典「东北买入 / 西南卖出」：未获支持，甚至常反向 → 角度只作轨迹描述
 * - 领先象限内即便西南朝向，短期相对超额仍偏正 → 强弱有延续性
 * - 远距强弱：样本内更像趋势延续而非均值回归
 * - 长尾：部分宇宙后续 |超额| 更大 → 仅提示相对波动升高
 */

import { quadrantOf, type QuadrantKey, type RrgPoint } from './rrg-lib'

export type HeadingSector = 'NE' | 'SE' | 'SW' | 'NW'

export type AssetInsight = {
  id: string
  name: string
  quadrant: QuadrantKey
  prevQuadrant: QuadrantKey | null
  transition: string | null
  rsRatio: number
  rsMomentum: number
  distance: number
  heading: number | null
  headingSector: HeadingSector | null
  velocity: number | null
  pathLen3: number | null
  momAbove3: number
  ratioAbove3: number
  earlyWatch: boolean
  persistenceStrong: boolean
  persistenceWeak: boolean
  longTail: boolean
  stateLine: string
  trailLine: string
  adviceLine: string
  tags: string[]
}

export type ChartInsight = {
  breadthLeading: number
  breadthImproving: number
  breadthWeakening: number
  breadthLagging: number
  n: number
  earlyWatchIds: string[]
  leadingIds: string[]
  laggingIds: string[]
  longTailIds: string[]
  summaryLines: string[]
  cautionLines: string[]
  adviceLines: string[]
}

const Q_CN: Record<QuadrantKey, string> = {
  leading: '领先',
  weakening: '减弱',
  lagging: '落后',
  improving: '改善',
}

const SECTOR_CN: Record<HeadingSector, string> = {
  NE: '东北（强弱与动量同增）',
  SE: '东南（强弱升、动量降）',
  SW: '西南（强弱与动量同减）',
  NW: '西北（强弱降、动量升）',
}

/** 罗盘角：0=正上(动量增)，90=正右(强弱增)，顺时针 */
export function compassHeading(dx: number, dy: number): number {
  let ang = (Math.atan2(dx, dy) * 180) / Math.PI
  if (ang < 0) ang += 360
  return ang
}

export function headingSectorOf(h: number): HeadingSector {
  if (h < 90) return 'NE'
  if (h < 180) return 'SE'
  if (h < 270) return 'SW'
  return 'NW'
}

function lastPoints(pts: RrgPoint[], n: number): RrgPoint[] {
  if (pts.length <= n) return pts
  return pts.slice(-n)
}

export function extractAssetInsight(
  id: string,
  name: string,
  points: RrgPoint[],
  opts?: { pathLenP80?: number },
): AssetInsight | null {
  if (!points.length) return null
  const p = points[points.length - 1]
  const prev = points.length > 1 ? points[points.length - 2] : null
  const q = quadrantOf(p.rsRatio, p.rsMomentum) as QuadrantKey
  const prevQ = prev ? (quadrantOf(prev.rsRatio, prev.rsMomentum) as QuadrantKey) : null

  let heading: number | null = null
  let velocity: number | null = null
  let headingSector: HeadingSector | null = null
  if (prev) {
    const dx = p.rsRatio - prev.rsRatio
    const dy = p.rsMomentum - prev.rsMomentum
    velocity = Math.hypot(dx, dy)
    heading = compassHeading(dx, dy)
    headingSector = headingSectorOf(heading)
  }

  const tail = lastPoints(points, 4)
  let pathLen3 = 0
  for (let i = 1; i < tail.length; i++) {
    pathLen3 += Math.hypot(tail[i].rsRatio - tail[i - 1].rsRatio, tail[i].rsMomentum - tail[i - 1].rsMomentum)
  }
  if (tail.length < 2) pathLen3 = NaN

  const recent = lastPoints(points, 3)
  const momAbove3 = recent.filter((x) => x.rsMomentum >= 100).length
  const ratioAbove3 = recent.filter((x) => x.rsRatio >= 100).length
  const distance = Math.hypot(p.rsRatio - 100, p.rsMomentum - 100)

  // H6：动量持续站上 100，但 Ratio 仍 <100 → 早期观察（回测强支持）
  const earlyWatch = momAbove3 >= 3 && p.rsRatio < 100

  // 样本内：领先侧有相对延续；远距弱势也偏延续
  const persistenceStrong = q === 'leading' || (p.rsRatio >= 100 && distance >= 8)
  const persistenceWeak = q === 'lagging' || (p.rsRatio < 100 && distance >= 8)

  const p80 = opts?.pathLenP80 ?? 6
  const longTail = Number.isFinite(pathLen3) && pathLen3 >= p80

  const transition = prevQ && prevQ !== q ? `${prevQ}->${q}` : null
  const tags: string[] = [Q_CN[q]]
  if (earlyWatch) tags.push('早期观察')
  if (headingSector) tags.push(headingSector)
  if (longTail) tags.push('长尾')
  if (persistenceStrong) tags.push('相对偏强')
  if (persistenceWeak) tags.push('相对偏弱')

  const stateLine = `当前位于「${Q_CN[q]}」象限（RS-Ratio ${p.rsRatio.toFixed(1)} · RS-Momentum ${p.rsMomentum.toFixed(1)}，距中心 ${distance.toFixed(1)}）。`

  let trailLine = '尾迹不足，暂不描述方向。'
  if (heading != null && headingSector && prevQ) {
    const trans =
      prevQ !== q
        ? `由「${Q_CN[prevQ]}」转入「${Q_CN[q]}」`
        : `仍停留在「${Q_CN[q]}」`
    trailLine = `${trans}；最近朝向约 ${heading.toFixed(0)}°（${SECTOR_CN[headingSector]}）${
      velocity != null ? `，单期速度 ${velocity.toFixed(2)}` : ''
    }${longTail ? '，近端尾迹偏长（相对波动偏高）' : ''}。`
  }

  // 建议：只给相对配置语气；不因 NE/SW 喊买卖
  let adviceLine =
    '角度与象限用于描述相对状态，本库月度回测未支持「东北朝向=买入、西南朝向=卖出」。请结合绝对趋势与仓位纪律。'
  if (earlyWatch) {
    adviceLine =
      '动量已连续站上 100 而强弱仍低于 100：回测中这是较可靠的「早期观察」信号（Ratio 有更高概率随后上穿）。可列入观察/小仓相对配置，待 Ratio 确认后再加大权重。'
  } else if (q === 'leading' && headingSector === 'SW') {
    adviceLine =
      '虽朝向西南（动能放缓），但样本内「领先」侧短期相对超额仍常延续。不宜仅因角度转弱立刻低配；可收紧止盈、观察是否跌破 Ratio=100。'
  } else if (q === 'leading') {
    adviceLine =
      '相对强势确立。样本显示领先侧有一定延续性，可维持相对超配观察；若转入减弱并持续跌破 100，再考虑收敛权重。'
  } else if (q === 'improving') {
    adviceLine =
      '相对弱势中动能回升。适合观察名单；若动量未能持续站上 100，暂勿按「必然崛起」加仓。'
  } else if (q === 'weakening') {
    adviceLine =
      '仍跑赢基准但动能转弱。优先做风险预算收缩而非一次性清仓；确认进入落后象限后再系统性低配。'
  } else if (q === 'lagging') {
    adviceLine = persistenceWeak
      ? '相对弱势且距中心较远，样本内弱势亦常延续。默认低配/规避，除非出现「动量持续站上 100」的早期观察信号。'
      : '相对落后。默认低配观察；关注是否出现动量持续改善。'
  }

  return {
    id,
    name,
    quadrant: q,
    prevQuadrant: prevQ,
    transition,
    rsRatio: p.rsRatio,
    rsMomentum: p.rsMomentum,
    distance,
    heading,
    headingSector,
    velocity,
    pathLen3: Number.isFinite(pathLen3) ? pathLen3 : null,
    momAbove3,
    ratioAbove3,
    earlyWatch,
    persistenceStrong,
    persistenceWeak,
    longTail,
    stateLine,
    trailLine,
    adviceLine,
    tags,
  }
}

export function buildChartInsight(
  assets: AssetInsight[],
  opts?: { modeLabel?: string },
): ChartInsight {
  const n = assets.length
  const empty: ChartInsight = {
    breadthLeading: 0,
    breadthImproving: 0,
    breadthWeakening: 0,
    breadthLagging: 0,
    n: 0,
    earlyWatchIds: [],
    leadingIds: [],
    laggingIds: [],
    longTailIds: [],
    summaryLines: ['当前无可解读轨迹。'],
    cautionLines: [],
    adviceLines: [],
  }
  if (!n) return empty

  const cnt = { leading: 0, improving: 0, weakening: 0, lagging: 0 }
  for (const a of assets) cnt[a.quadrant]++

  const earlyWatchIds = assets.filter((a) => a.earlyWatch).map((a) => a.id)
  const leadingIds = assets.filter((a) => a.quadrant === 'leading').map((a) => a.id)
  const laggingIds = assets.filter((a) => a.quadrant === 'lagging').map((a) => a.id)
  const longTailIds = assets.filter((a) => a.longTail).map((a) => a.id)

  const pct = (x: number) => `${((x / n) * 100).toFixed(0)}%`
  const nameOf = (id: string) => assets.find((a) => a.id === id)?.name ?? id

  const summaryLines: string[] = [
    `共 ${n} 条轨迹：领先 ${cnt.leading}（${pct(cnt.leading)}）· 改善 ${cnt.improving}（${pct(cnt.improving)}）· 减弱 ${cnt.weakening}（${pct(cnt.weakening)}）· 落后 ${cnt.lagging}（${pct(cnt.lagging)}）。`,
  ]

  const up = cnt.leading + cnt.improving
  const down = cnt.lagging + cnt.weakening
  if (up >= n * 0.55) {
    summaryLines.push('广度偏强：多数标的处于领先/改善，相对基准的参与面较广。')
  } else if (down >= n * 0.55) {
    summaryLines.push('广度偏弱：多数标的处于落后/减弱，相对轮动整体偏防守。')
  } else if (cnt.leading <= Math.max(1, Math.floor(n * 0.2)) && cnt.leading > 0) {
    summaryLines.push('行情可能偏窄：仅少数标的处于领先，注意集中度风险（广度不足）。')
  } else {
    summaryLines.push('象限分布较分散，轮动尚未形成一边倒格局。')
  }

  if (earlyWatchIds.length) {
    const names = earlyWatchIds.slice(0, 4).map(nameOf).join('、')
    summaryLines.push(
      `早期观察（动量已稳、强弱未确认）：${names}${earlyWatchIds.length > 4 ? ' 等' : ''}——回测中此项证据最强。`,
    )
  }

  const cautionLines: string[] = [
    '月度回测未支持「东北朝向必然跑赢、西南朝向必然跑输」；角度仅描述轨迹，不作买卖指令。',
  ]
  if (longTailIds.length >= Math.max(2, Math.floor(n * 0.25))) {
    cautionLines.push('多条长尾并存：相对波动偏高，调仓节奏宜放缓、单笔权重宜克制。')
  }
  if (opts?.modeLabel?.includes('大类')) {
    cautionLines.push('大类资产同质性低，顺时针弧线与行业轮动规律更弱，优先看象限与早期观察信号。')
  }

  const adviceLines: string[] = []
  if (earlyWatchIds.length) {
    adviceLines.push('优先跟踪「早期观察」名单，等待 Ratio 上穿 100 再提高相对权重。')
  }
  if (leadingIds.length) {
    adviceLines.push(
      `领先组（${leadingIds.slice(0, 3).map(nameOf).join('、')}${leadingIds.length > 3 ? '…' : ''}）样本内有一定相对延续性，可维持观察型超配，但需配合绝对趋势过滤。`,
    )
  }
  if (laggingIds.length && laggingIds.length >= n * 0.4) {
    adviceLines.push('落后面较宽，组合层面宜控制进攻仓位，避免在弱势簇中抄底式加仓。')
  }
  if (!adviceLines.length) {
    adviceLines.push('当前无显著早期信号：以描述性跟踪为主，保持基准中性或沿用既有配置。')
  }

  return {
    breadthLeading: cnt.leading / n,
    breadthImproving: cnt.improving / n,
    breadthWeakening: cnt.weakening / n,
    breadthLagging: cnt.lagging / n,
    n,
    earlyWatchIds,
    leadingIds,
    laggingIds,
    longTailIds,
    summaryLines,
    cautionLines,
    adviceLines,
  }
}

export function pathLenP80(pointsList: RrgPoint[][]): number {
  const lens: number[] = []
  for (const pts of pointsList) {
    if (pts.length < 2) continue
    const tail = lastPoints(pts, 4)
    let L = 0
    for (let i = 1; i < tail.length; i++) {
      L += Math.hypot(tail[i].rsRatio - tail[i - 1].rsRatio, tail[i].rsMomentum - tail[i - 1].rsMomentum)
    }
    lens.push(L)
  }
  if (!lens.length) return 6
  lens.sort((a, b) => a - b)
  return lens[Math.floor(lens.length * 0.8)] ?? 6
}
