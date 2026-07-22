import { useEffect, useMemo, useRef, useState, type MouseEvent } from 'react'
import { publicUrl } from './assets'
import type { MarketCapData, MarketCapSeries, ShareFrame } from './marketcap-types'
import { PILLAR_COLORS, formatPct, formatUsd, sliceSharePanel, buildShareFramesFromSeries } from './marketcap-types'

type RangeKey = '1y' | '3y' | '5y' | '10y' | 'custom'

function monthsAgo(n: number): string {
  const d = new Date()
  d.setMonth(d.getMonth() - n)
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}-01`
}

function clampEnd(end: string, displayEnd?: string): string {
  if (!displayEnd) return end
  return end > displayEnd ? displayEnd : end
}

function StackedShareChart({
  frames,
  width = 920,
  height = 420,
}: {
  frames: ShareFrame[]
  width?: number
  height?: number
}) {
  const padding = { top: 20, right: 16, bottom: 36, left: 48 }
  const innerW = width - padding.left - padding.right
  const innerH = height - padding.top - padding.bottom
  const svgRef = useRef<SVGSVGElement | null>(null)
  const [hoverIdx, setHoverIdx] = useState<number | null>(null)

  const activeIdx = hoverIdx ?? (frames.length ? frames.length - 1 : 0)
  const active = frames[activeIdx] ?? null

  const orderedIds = useMemo(() => {
    if (!frames.length) return [] as string[]
    const seen = new Set<string>()
    // 区间内出现过的资产都参与堆积，避免因区间末缺数导致前期留白
    for (const f of frames) {
      for (const s of f.shares) seen.add(s.id)
    }
    const last = frames[frames.length - 1]
    const rank = new Map(last.shares.map((s, i) => [s.id, i]))
    return [...seen].sort((a, b) => (rank.get(a) ?? 999) - (rank.get(b) ?? 999))
  }, [frames])

  const colorOf = (id: string, pillar: string) => {
    const idx = orderedIds.indexOf(id)
    const base = PILLAR_COLORS[pillar] ?? '#0f5c4c'
    const shades = [1, 0.85, 0.7, 0.55]
    return { base, alpha: shades[Math.max(0, idx) % shades.length] }
  }

  const layers = useMemo(() => {
    if (frames.length < 2) return [] as { id: string; name: string; pillar: string; path: string }[]
    const nameOf = new Map<string, { name: string; pillar: string }>()
    for (const f of frames) {
      for (const s of f.shares) nameOf.set(s.id, { name: s.name, pillar: s.pillar })
    }

    const stacks = frames.map((f) => {
      const map = new Map(f.shares.map((s) => [s.id, s]))
      // 仅用本月有值的资产重算占比，保证当月堆积恒为 100%
      let monthTotal = 0
      const present: { id: string; value: number }[] = []
      for (const id of orderedIds) {
        const v = map.get(id)?.value ?? 0
        if (v > 0) {
          present.push({ id, value: v })
          monthTotal += v
        }
      }
      const shareMap = new Map<string, number>()
      for (const p of present) shareMap.set(p.id, monthTotal > 0 ? p.value / monthTotal : 0)

      let y0 = 0
      const bands: { id: string; name: string; pillar: string; y0: number; y1: number }[] = []
      for (const id of orderedIds) {
        const share = shareMap.get(id) ?? 0
        const y1 = y0 + share
        const meta = nameOf.get(id)
        bands.push({
          id,
          name: meta?.name ?? id,
          pillar: meta?.pillar ?? 'equity',
          y0,
          y1,
        })
        y0 = y1
      }
      return bands
    })

    return orderedIds.map((id) => {
      const top: string[] = []
      const bottom: string[] = []
      stacks.forEach((bands, i) => {
        const b = bands.find((x) => x.id === id)!
        const x = padding.left + (i / Math.max(frames.length - 1, 1)) * innerW
        const yTop = padding.top + innerH * (1 - b.y1)
        const yBot = padding.top + innerH * (1 - b.y0)
        top.push(`${i === 0 ? 'M' : 'L'} ${x.toFixed(1)} ${yTop.toFixed(1)}`)
        bottom.push(`L ${x.toFixed(1)} ${yBot.toFixed(1)}`)
      })
      // 勿原地 reverse，避免后续逻辑踩到已反转数组
      const path = `${top.join(' ')} ${[...bottom].reverse().join(' ')} Z`
      const sample = stacks[stacks.length - 1].find((x) => x.id === id)!
      return { id, name: sample.name, pillar: sample.pillar, path }
    })
  }, [frames, orderedIds, innerH, innerW, padding.left, padding.top])

  const xLabels = useMemo(() => {
    if (!frames.length) return [] as { x: number; label: string }[]
    const picks = [0, Math.floor(frames.length / 2), frames.length - 1]
    return [...new Set(picks)].map((i) => ({
      x: padding.left + (i / Math.max(frames.length - 1, 1)) * innerW,
      label: frames[i].date.slice(0, 7),
    }))
  }, [frames, innerW, padding.left])

  const hoverX =
    frames.length > 1 && activeIdx >= 0
      ? padding.left + (activeIdx / (frames.length - 1)) * innerW
      : null

  const onMove = (e: MouseEvent<SVGSVGElement>) => {
    if (frames.length < 2 || !svgRef.current) return
    const rect = svgRef.current.getBoundingClientRect()
    const x = ((e.clientX - rect.left) / rect.width) * width
    const t = (x - padding.left) / innerW
    const idx = Math.round(Math.min(1, Math.max(0, t)) * (frames.length - 1))
    setHoverIdx(idx)
  }

  const legend = active?.shares ?? []

  return (
    <div className="mc-stack-wrap">
      <div className="mc-stack-chart-box">
        <svg
          ref={svgRef}
          className="mc-chart mc-stack-chart"
          viewBox={`0 0 ${width} ${height}`}
          role="img"
          aria-label="规模占比堆积图"
          onMouseMove={onMove}
          onMouseLeave={() => setHoverIdx(null)}
        >
          {[0, 0.25, 0.5, 0.75, 1].map((v) => {
            const y = padding.top + innerH * (1 - v)
            return (
              <g key={v}>
                <line
                  x1={padding.left}
                  x2={width - padding.right}
                  y1={y}
                  y2={y}
                  stroke="var(--line)"
                  strokeDasharray="4 4"
                />
                <text x={padding.left - 8} y={y + 4} textAnchor="end" className="mc-chart-label">
                  {(v * 100).toFixed(0)}%
                </text>
              </g>
            )
          })}
          {layers.map((layer) => {
            const { base, alpha } = colorOf(layer.id, layer.pillar)
            return <path key={layer.id} d={layer.path} fill={base} opacity={alpha} stroke="none" />
          })}
          {hoverX != null && (
            <line
              x1={hoverX}
              x2={hoverX}
              y1={padding.top}
              y2={padding.top + innerH}
              stroke="var(--ink, #1a1a1a)"
              strokeWidth={1.25}
              strokeDasharray="3 3"
              pointerEvents="none"
            />
          )}
          {xLabels.map((l) => (
            <text key={`${l.label}-${l.x}`} x={l.x} y={height - 10} textAnchor="middle" className="mc-chart-label">
              {l.label}
            </text>
          ))}
        </svg>
        {active && (
          <div className="mc-stack-tooltip">
            <strong>{active.date.slice(0, 7)}</strong>
            <span>合计 {formatUsd(active.total)}</span>
            {hoverIdx == null ? <em>区间末 · 移入查看各月</em> : <em>悬停月份占比</em>}
          </div>
        )}
      </div>
      <div className="mc-stack-legend">
        <div className="mc-stack-legend-head">
          {active ? active.date.slice(0, 7) : '—'} 占比
        </div>
        {legend.map((item) => {
          const color = PILLAR_COLORS[item.pillar] ?? '#0f5c4c'
          return (
            <div key={item.id} className="mc-stack-legend-item" title={`${formatUsd(item.value, false)}`}>
              <span className="mc-dot" style={{ background: color }} />
              <strong>{item.name}</strong>
              <em>{formatPct(item.share)}</em>
            </div>
          )
        })}
      </div>
    </div>
  )
}

function LineChart({
  series,
  width = 720,
  height = 260,
}: {
  series: MarketCapSeries
  width?: number
  height?: number
}) {
  const padding = { top: 16, right: 16, bottom: 32, left: 72 }
  const innerW = width - padding.left - padding.right
  const innerH = height - padding.top - padding.bottom

  const { path, yTicks, xLabels } = useMemo(() => {
    const pts = series.points
    if (pts.length < 2) {
      return { path: '', yTicks: [] as number[], xLabels: [] as { x: number; label: string }[] }
    }
    const values = pts.map((p) => p[1])
    const minV = Math.min(...values)
    const maxV = Math.max(...values)
    const span = maxV - minV || 1

    const coords = pts.map((p, i) => {
      const x = padding.left + (i / (pts.length - 1)) * innerW
      const y = padding.top + innerH - ((p[1] - minV) / span) * innerH
      return { x, y, date: p[0] }
    })

    const d = coords.map((c, i) => `${i === 0 ? 'M' : 'L'} ${c.x.toFixed(1)} ${c.y.toFixed(1)}`).join(' ')
    const yTicks = [minV, minV + span * 0.5, maxV]
    const xLabels = [
      { x: coords[0].x, label: coords[0].date.slice(0, 7) },
      { x: coords[Math.floor(coords.length / 2)].x, label: coords[Math.floor(coords.length / 2)].date.slice(0, 7) },
      { x: coords[coords.length - 1].x, label: coords[coords.length - 1].date.slice(0, 7) },
    ]
    return { path: d, yTicks, xLabels }
  }, [series, innerH, innerW, padding.left, padding.top])

  const color = PILLAR_COLORS[series.pillar] ?? '#0f5c4c'

  return (
    <svg className="mc-chart" viewBox={`0 0 ${width} ${height}`} role="img" aria-label={`${series.name}规模走势`}>
      {yTicks.map((v) => {
        const y = padding.top + innerH - ((v - yTicks[0]) / (yTicks[2] - yTicks[0] || 1)) * innerH
        return (
          <g key={v}>
            <line
              x1={padding.left}
              x2={width - padding.right}
              y1={y}
              y2={y}
              stroke="var(--line)"
              strokeDasharray="4 4"
            />
            <text x={padding.left - 8} y={y + 4} textAnchor="end" className="mc-chart-label">
              {formatUsd(v)}
            </text>
          </g>
        )
      })}
      <path d={path} fill="none" stroke={color} strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round" />
      {xLabels.map((l) => (
        <text key={`${l.label}-${l.x}`} x={l.x} y={height - 8} textAnchor="middle" className="mc-chart-label">
          {l.label}
        </text>
      ))}
    </svg>
  )
}

export default function MarketCapView() {
  const [data, setData] = useState<MarketCapData | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [pillar, setPillar] = useState('all')
  const [selectedId, setSelectedId] = useState<string | null>(null)
  const [rangeKey, setRangeKey] = useState<RangeKey>('5y')
  const [customStart, setCustomStart] = useState(monthsAgo(36).slice(0, 7))
  const [customEnd, setCustomEnd] = useState(() => {
    const d = new Date()
    d.setMonth(d.getMonth() - 1)
    return d.toISOString().slice(0, 7)
  })

  useEffect(() => {
    fetch(publicUrl('rotation_marketcap.json'))
      .then((r) => {
        if (!r.ok) {
          throw new Error(
            `加载规模数据失败: ${r.status}（请先运行 python scripts/build_rotation_catalog.py）`,
          )
        }
        return r.json()
      })
      .then((d: MarketCapData) => {
        setData(d)
        setSelectedId(d.latest[0]?.id ?? null)
        if (d.display_end) {
          setCustomEnd(d.display_end.slice(0, 7))
        }
      })
      .catch((e: Error) => setError(e.message))
  }, [])

  const pillars = useMemo(() => {
    if (!data) return []
    const ids = [...new Set(data.series.map((s) => s.pillar))]
    return ids.map((id) => ({
      id,
      label: data.series.find((s) => s.pillar === id)?.pillar_label ?? id,
      count: data.series.filter((s) => s.pillar === id).length,
    }))
  }, [data])

  const dateBounds = useMemo(() => {
    const displayEnd = data?.display_end ?? '9999-12-31'
    let start: string
    let end: string
    if (rangeKey === 'custom') {
      start = `${customStart}-01`
      end = clampEnd(`${customEnd}-01`, displayEnd)
    } else {
      const months = rangeKey === '1y' ? 12 : rangeKey === '3y' ? 36 : rangeKey === '5y' ? 60 : 120
      start = monthsAgo(months)
      end = displayEnd
    }
    // 起止颠倒时交换，避免切片为空
    if (start.slice(0, 7) > end.slice(0, 7)) {
      ;[start, end] = [end, start]
    }
    return { start, end }
  }, [rangeKey, customStart, customEnd, data?.display_end])

  const shareFrames = useMemo(() => {
    if (!data) return [] as ShareFrame[]
    const opts = { start: dateBounds.start, end: dateBounds.end, pillar }
    if (data.share_panel?.dates?.length) {
      const fromPanel = sliceSharePanel(data.share_panel, opts)
      if (fromPanel.length >= 2) return fromPanel
    }
    return buildShareFramesFromSeries(data.series, opts)
  }, [data, dateBounds, pillar])

  const filteredLatest = useMemo(() => {
    if (!shareFrames.length) return []
    const last = shareFrames[shareFrames.length - 1]
    return last.shares.map((s) => ({
      id: s.id,
      name: s.name,
      pillar: s.pillar,
      pillar_label: s.pillar_label,
      date: last.date,
      value_usd: s.value,
      share: s.share,
    }))
  }, [shareFrames])

  const filteredTotal = useMemo(
    () => filteredLatest.reduce((s, x) => s + x.value_usd, 0),
    [filteredLatest],
  )

  const filteredSeries = useMemo(() => {
    if (!data) return []
    const base = pillar === 'all' ? data.series : data.series.filter((s) => s.pillar === pillar)
    return base.map((s) => ({
      ...s,
      points: s.points.filter(([d]) => d >= dateBounds.start && d <= dateBounds.end),
    }))
  }, [data, pillar, dateBounds])

  const selectedSeries = filteredSeries.find((s) => s.id === selectedId) ?? filteredSeries[0] ?? null
  const selectedDoc = data?.series.find((s) => s.id === selectedSeries?.id)?.documentation

  if (error) {
    return <p className="empty">{error}</p>
  }

  if (!data) {
    return <p className="empty">正在加载规模占比数据…</p>
  }

  return (
    <div className="mc-page">
      <header className="hero">
        <div>
          <p className="meta-row" style={{ marginBottom: 8 }}>
            <span>全球大类资产 · 规模占比</span>
          </p>
          <h1 className="brand">规模占比</h1>
        </div>
        <p className="lede">
          以各资产美元规模占可统计池的比重刻画结构变迁。切换时间区间或类别时按当期样本重算占比；悬停堆积图可查看该月结构。未完成的当月已隐藏（展示至{' '}
          {data.display_end?.slice(0, 7) ?? '—'}）。
        </p>
        <div className="stats">
          <div className="stat">
            <strong>{data.counts.with_marketcap}</strong>
            <span>有规模数据</span>
          </div>
          <div className="stat">
            <strong>{formatUsd(filteredTotal)}</strong>
            <span>区间末合计</span>
          </div>
          <div className="stat">
            <strong>{data.display_end?.slice(0, 7) ?? data.generated_at.slice(0, 10)}</strong>
            <span>展示截止</span>
          </div>
        </div>
      </header>

      <div className="mc-toolbar">
        <div className="mc-pillar-tabs">
          <button
            type="button"
            className={`mc-tab ${pillar === 'all' ? 'active' : ''}`}
            onClick={() => setPillar('all')}
          >
            全部 ({data.latest.length})
          </button>
          {pillars.map((p) => (
            <button
              key={p.id}
              type="button"
              className={`mc-tab ${pillar === p.id ? 'active' : ''}`}
              onClick={() => setPillar(p.id)}
            >
              {p.label} ({p.count})
            </button>
          ))}
        </div>
        <div className="mc-range-tabs">
          {(
            [
              ['1y', '1年'],
              ['3y', '3年'],
              ['5y', '5年'],
              ['10y', '10年'],
              ['custom', '自定义'],
            ] as const
          ).map(([key, label]) => (
            <button
              key={key}
              type="button"
              className={`mc-tab ${rangeKey === key ? 'active' : ''}`}
              onClick={() => setRangeKey(key)}
            >
              {label}
            </button>
          ))}
          {rangeKey === 'custom' && (
            <div className="mc-custom-range">
              <label>
                起
                <input
                  type="month"
                  value={customStart}
                  max={data.display_end?.slice(0, 7)}
                  onChange={(e) => setCustomStart(e.target.value)}
                />
              </label>
              <label>
                止
                <input
                  type="month"
                  value={customEnd}
                  max={data.display_end?.slice(0, 7)}
                  onChange={(e) => setCustomEnd(e.target.value)}
                />
              </label>
            </div>
          )}
        </div>
      </div>

      <section className="mc-composition">
        <h2 className="mc-section-title">规模占比堆积（按月）</h2>
        <p className="mc-section-sub">
          {pillar === 'all' ? '全部可统计资产' : pillars.find((p) => p.id === pillar)?.label} ·{' '}
          {shareFrames[0]?.date.slice(0, 7) ?? '—'} → {shareFrames.at(-1)?.date.slice(0, 7) ?? '—'} ·
          共 {shareFrames.length} 个月 · 占比随所选样本重算
        </p>
        {shareFrames.length >= 2 ? (
          <StackedShareChart frames={shareFrames} />
        ) : (
          <p className="empty">当前区间内可对齐月份不足，请扩大时间范围。</p>
        )}
      </section>

      <section className="mc-composition">
        <h2 className="mc-section-title">区间末占比</h2>
        <p className="mc-section-sub">
          {shareFrames.at(-1)?.date.slice(0, 7) ?? '—'} · 合计 {formatUsd(filteredTotal)}
        </p>
        <div className="mc-composition-grid">
          <div className="mc-bars">
            {filteredLatest.map((item) => {
              const color = PILLAR_COLORS[item.pillar] ?? '#0f5c4c'
              return (
                <button
                  key={item.id}
                  type="button"
                  className={`mc-bar-row ${selectedId === item.id ? 'selected' : ''}`}
                  onClick={() => setSelectedId(item.id)}
                >
                  <div className="mc-bar-meta">
                    <span className="mc-bar-name">{item.name}</span>
                    <span className="mc-bar-val">
                      {formatUsd(item.value_usd)} · {formatPct(item.share)}
                    </span>
                  </div>
                  <div className="mc-bar-track">
                    <div
                      className="mc-bar-fill"
                      style={{ width: `${item.share * 100}%`, background: color }}
                    />
                  </div>
                </button>
              )
            })}
          </div>
        </div>
      </section>

      {selectedSeries && selectedSeries.points.length > 0 && (
        <section className="detail mc-detail">
          <h2>{selectedSeries.name}</h2>
          <div className="sub">
            {selectedSeries.pillar_label} · {selectedSeries.points.length} 个月 ·{' '}
            {selectedSeries.authority ?? '—'}
          </div>
          <LineChart series={selectedSeries} />
          <div className="detail-grid">
            <div>
              <label>区间末规模</label>
              <div>{formatUsd(selectedSeries.points.at(-1)?.[1] ?? 0, false)}</div>
            </div>
            <div>
              <label>区间末日期</label>
              <div>{selectedSeries.points.at(-1)?.[0] ?? '—'}</div>
            </div>
            <div>
              <label>区间末占比</label>
              <div>{formatPct(filteredLatest.find((x) => x.id === selectedSeries.id)?.share ?? 0)}</div>
            </div>
            <div>
              <label>口径</label>
              <div>{selectedSeries.method ?? '—'}</div>
            </div>
          </div>
          {selectedDoc && (
            <div className="mc-docs">
              <h3>指标说明</h3>
              {selectedDoc.summary && <p>{selectedDoc.summary}</p>}
              <div className="detail-grid mc-docs-grid">
                <div>
                  <label>数据来源</label>
                  <div>{selectedDoc.data_source ?? '—'}</div>
                </div>
                <div>
                  <label>计算方法</label>
                  <div>{selectedDoc.methodology ?? '—'}</div>
                </div>
                <div>
                  <label>更新频率</label>
                  <div>{selectedDoc.frequency ?? '—'}</div>
                </div>
                <div>
                  <label>更新节奏</label>
                  <div>{selectedDoc.update_schedule ?? '—'}</div>
                </div>
                <div>
                  <label>数据最后时点</label>
                  <div>{selectedDoc.last_data_date ?? '—'}</div>
                </div>
                <div>
                  <label>本次拉取时间</label>
                  <div>{selectedDoc.last_updated ?? '—'}</div>
                </div>
                <div>
                  <label>预计下次更新</label>
                  <div>{selectedDoc.expected_next_update ?? '—'}</div>
                </div>
                {selectedDoc.notes ? (
                  <div>
                    <label>备注</label>
                    <div>{selectedDoc.notes}</div>
                  </div>
                ) : null}
              </div>
            </div>
          )}
        </section>
      )}

      <section className="mc-table-section">
        <h2 className="mc-section-title">规模明细表</h2>
        <div className="table-wrap">
          <table>
            <thead>
              <tr>
                <th>资产</th>
                <th>类别</th>
                <th>区间末规模</th>
                <th>占比</th>
                <th>数据截止</th>
                <th>来源</th>
              </tr>
            </thead>
            <tbody>
              {filteredLatest.map((row) => (
                <tr
                  key={row.id}
                  className={`clickable ${selectedId === row.id ? 'selected' : ''}`}
                  onClick={() => setSelectedId(row.id)}
                >
                  <td className="name-cell">
                    <strong>{row.name}</strong>
                    <span>{row.id}</span>
                  </td>
                  <td>
                    <span className="badge">{row.pillar_label}</span>
                  </td>
                  <td>{formatUsd(row.value_usd, false)}</td>
                  <td>{formatPct(row.share)}</td>
                  <td>{row.date}</td>
                  <td>{data.series.find((s) => s.id === row.id)?.authority ?? '—'}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
        <p className="notes">
          注：占比 = 所选时间与类别下，各资产美元规模 / 当期可统计样本合计。切换区间或类别会重算。未完成当月不展示。
        </p>
      </section>

      <AllIndicatorsDocs />
    </div>
  )
}

type RotationCatalogAsset = {
  id: string
  name: string
  pillar: string
  documentation?: import('./marketcap-types').IndicatorDocumentation
  marketcap?: { method?: string | null }
}

function AllIndicatorsDocs() {
  const [assets, setAssets] = useState<RotationCatalogAsset[]>([])

  useEffect(() => {
    fetch('/rotation_catalog.json')
      .then((r) => (r.ok ? r.json() : null))
      .then((d) => {
        if (d?.assets) setAssets(d.assets)
      })
      .catch(() => undefined)
  }, [])

  if (!assets.length) return null

  const pillarLabels: Record<string, string> = {
    equity: '股票',
    bond: '债券',
    precious_metal: '贵金属',
    commodity: '商品',
    crypto: '加密',
    fx: '外汇',
    real_estate: '地产',
  }

  return (
    <section className="mc-table-section">
      <h2 className="mc-section-title">全部指标说明（{assets.length} 项）</h2>
      <div className="mc-docs-list">
        {assets.map((a) => {
          const doc = a.documentation
          if (!doc) return null
          return (
            <details key={a.id} className="mc-docs-item">
              <summary>
                <strong>{a.name}</strong>
                <span>
                  {pillarLabels[a.pillar] ?? a.pillar}
                  {a.marketcap?.method === 'na' ? ' · 仅回报' : ''}
                </span>
              </summary>
              <div className="mc-docs-body">
                <p>{doc.summary}</p>
                <p>
                  <strong>来源：</strong>
                  {doc.data_source}
                </p>
                <p>
                  <strong>方法：</strong>
                  {doc.methodology}
                </p>
                <p>
                  <strong>频率：</strong>
                  {doc.frequency} · <strong>数据时点：</strong>
                  {doc.last_data_date ?? '—'} · <strong>预计下次：</strong>
                  {doc.expected_next_update ?? '—'}
                </p>
                <p>
                  <strong>更新节奏：</strong>
                  {doc.update_schedule ?? '—'}
                </p>
                {doc.notes ? (
                  <p>
                    <strong>备注：</strong>
                    {doc.notes}
                  </p>
                ) : null}
              </div>
            </details>
          )
        })}
      </div>
    </section>
  )
}
