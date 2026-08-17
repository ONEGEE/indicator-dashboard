import { useEffect, useMemo, useState } from 'react'
import { publicUrl } from './assets'
import {
  RIGHT_LONG_MODES,
  STAGE_COLORS,
  STAGE_LABELS,
  buildJourneysFromRrg,
  defaultParams,
  filterJourneys,
  segmentAtMonth,
  timelineMonths,
  type Journey,
  type JourneyView,
  type RightLongParams,
  type RightLongPolicy,
  type RightLongStage,
} from './rrg-right-long'
import type { RrgData, RrgMode } from './rrg-lib'

function statusLabel(j: Journey): string {
  if (j.status === 'falsified') return '已证伪'
  if (j.status === 'review') return '待复审'
  return '进行中'
}

function GanttRow({
  journey: j,
  months,
  falsified,
  selected,
  onSelect,
}: {
  journey: Journey
  months: string[]
  falsified: boolean
  selected: boolean
  onSelect: () => void
}) {
  const failYm = j.falsifiedAt ? j.falsifiedAt.slice(0, 7) : null

  return (
    <button
      type="button"
      className={`rl-gantt-row ${falsified ? 'is-falsified' : ''} ${selected ? 'selected' : ''}`}
      onClick={onSelect}
    >
      <div className="rl-gantt-label">
        <strong>{j.assetName}</strong>
        <span className="rl-gantt-meta">
          {j.currentStage ? STAGE_LABELS[j.currentStage] : '—'} · {statusLabel(j)}
        </span>
      </div>
      <div className="rl-gantt-track" style={{ gridTemplateColumns: `repeat(${months.length}, 1fr)` }}>
        {months.map((ym) => {
          const stage = segmentAtMonth(j, ym)
          const isFail = falsified && failYm != null && ym >= failYm
          const bg = stage ? STAGE_COLORS[stage] : 'transparent'
          const opacity = isFail ? 0.28 : stage ? 1 : 0
          return (
            <div key={ym} className="rl-gantt-cell" title={stage ? `${ym} ${stage}` : ym}>
              {stage ? (
                <span className="rl-gantt-block" style={{ background: bg, opacity }} aria-hidden />
              ) : null}
            </div>
          )
        })}
      </div>
    </button>
  )
}

export default function RrgRightLongView() {
  const [mode, setMode] = useState<RrgMode>('cn_sw')
  const [data, setData] = useState<RrgData | null>(null)
  const [policy, setPolicy] = useState<RightLongPolicy | null>(null)
  const [params, setParams] = useState<RightLongParams | null>(null)
  const [view, setView] = useState<JourneyView>('active')
  const [deOnly, setDeOnly] = useState(false)
  const [advanced, setAdvanced] = useState(false)
  const [selectedId, setSelectedId] = useState<number | null>(null)
  const [error, setError] = useState<string | null>(null)

  const modeMeta = RIGHT_LONG_MODES.find((m) => m.id === mode)!

  useEffect(() => {
    Promise.all([
      fetch(publicUrl(modeMeta.url)).then((r) => {
        if (!r.ok) throw new Error(`RRG ${r.status}`)
        return r.json() as Promise<RrgData>
      }),
      fetch(publicUrl('rrg_right_long_policy.json')).then((r) => {
        if (!r.ok) throw new Error(`policy ${r.status}`)
        return r.json() as Promise<RightLongPolicy>
      }),
    ])
      .then(([d, p]) => {
        setData(d)
        setPolicy(p)
        setParams(defaultParams(mode, p))
        setError(null)
      })
      .catch((e: Error) => setError(e.message))
  }, [mode, modeMeta.url])

  useEffect(() => {
    if (policy) setParams(defaultParams(mode, policy))
  }, [mode, policy])

  const journeys = useMemo(() => {
    if (!data || !policy || !params) return []
    return buildJourneysFromRrg(data, mode, params, policy)
  }, [data, mode, params, policy])

  const filtered = useMemo(() => filterJourneys(journeys, view, deOnly), [journeys, view, deOnly])

  const months = useMemo(() => timelineMonths(journeys, 18), [journeys])

  const selected = filtered.find((j) => j.journeyId === selectedId) ?? filtered[0] ?? null

  const stats = useMemo(() => {
    const active = journeys.filter((j) => j.status === 'active' || j.status === 'review')
    const deActive = active.filter((j) => j.reachedDe)
    return {
      total: journeys.length,
      active: active.length,
      deActive: deActive.length,
      falsified: journeys.filter((j) => j.status === 'falsified').length,
    }
  }, [journeys])

  const updateParam = <K extends keyof RightLongParams>(key: K, value: RightLongParams[K]) => {
    setParams((prev) => (prev ? { ...prev, [key]: value } : prev))
  }

  if (error) return <p className="empty">加载失败：{error}</p>
  if (!data || !policy || !params) return <p className="empty">正在加载 RRG 右多策略…</p>

  return (
    <div className="rl-page">
      <header className="hero rl-hero">
        <div>
          <p className="meta-row" style={{ marginBottom: 8 }}>
            <span>RRG 右多策略 · 庙旺得利</span>
          </p>
          <h1 className="brand">行业相对强弱 · 右侧做多</h1>
        </div>
        <p className="lede">
          月度 JdK 12/3 · 甘特时间线记录每次旅程。利仅观察；得为首次跟进；旺/庙持有。证伪置灰不删除。
        </p>
        <div className="stats">
          <div className="stat">
            <strong>{stats.active}</strong>
            <span>进行中</span>
          </div>
          <div className="stat">
            <strong>{stats.deActive}</strong>
            <span>得及以上</span>
          </div>
          <div className="stat">
            <strong>{stats.falsified}</strong>
            <span>已证伪</span>
          </div>
          <div className="stat">
            <strong>{stats.total}</strong>
            <span>历史旅程</span>
          </div>
        </div>
      </header>

      <div className="rl-toolbar">
        <div className="rl-mode-tabs">
          {RIGHT_LONG_MODES.map((m) => (
            <button
              key={m.id}
              type="button"
              className={`mc-tab ${mode === m.id ? 'active' : ''}`}
              onClick={() => setMode(m.id)}
            >
              {m.label}
            </button>
          ))}
        </div>
        <div className="rl-view-tabs">
          {(
            [
              ['active', '进行中'],
              ['falsified', '已证伪'],
              ['all', '全部'],
            ] as const
          ).map(([id, label]) => (
            <button
              key={id}
              type="button"
              className={`mc-tab ${view === id ? 'active' : ''}`}
              onClick={() => setView(id)}
            >
              {label}
            </button>
          ))}
        </div>
        <label className="rl-check">
          <input type="checkbox" checked={deOnly} onChange={(e) => setDeOnly(e.target.checked)} />
          只看得及以上
        </label>
        <button type="button" className="mc-tab" onClick={() => setAdvanced((v) => !v)}>
          {advanced ? '收起高级' : '高级参数'}
        </button>
      </div>

      {advanced && (
        <section className="rl-advanced panel">
          <div className="rl-advanced-grid">
            <label>
              利 Mom 连续（月）
              <select
                value={params.liMomMinInWindow}
                onChange={(e) => updateParam('liMomMinInWindow', Number(e.target.value))}
              >
                <option value={2}>2/3</option>
                <option value={3}>3/3</option>
              </select>
            </label>
            <label>
              得 站住月数
              <select value={params.deHoldMonths} onChange={(e) => updateParam('deHoldMonths', Number(e.target.value))}>
                <option value={1}>1</option>
                <option value={2}>2</option>
              </select>
            </label>
            <label>
              庙 领先月数
              <select
                value={params.miaoLeadingMonths}
                onChange={(e) => updateParam('miaoLeadingMonths', Number(e.target.value))}
              >
                {[4, 6, 8].map((n) => (
                  <option key={n} value={n}>
                    {n}
                  </option>
                ))}
              </select>
            </label>
            <label>
              旺 距离分位
              <select
                value={params.wangDistPct}
                onChange={(e) => updateParam('wangDistPct', Number(e.target.value))}
              >
                {[0.65, 0.7, 0.75].map((n) => (
                  <option key={n} value={n}>
                    {Math.round(n * 100)}%
                  </option>
                ))}
              </select>
            </label>
            <label>
              旺 Ratio 下限
              <select
                value={params.wangRatioMin}
                onChange={(e) => updateParam('wangRatioMin', Number(e.target.value))}
              >
                {[101, 102, 103].map((n) => (
                  <option key={n} value={n}>
                    {n}
                  </option>
                ))}
              </select>
            </label>
            <button
              type="button"
              className="mc-tab"
              onClick={() => policy && setParams(defaultParams(mode, policy))}
            >
              恢复默认
            </button>
          </div>
          <p className="rl-advanced-hint">
            默认已按回测分市场硬编码（美股：利3/3·得1·庙4；申万：利2/3·得2·庙6）。敏感度高的项在此调整。
          </p>
        </section>
      )}

      <div className="rl-legend">
        {(['利', '得', '旺', '庙'] as RightLongStage[]).map((s) => (
          <span key={s} className="rl-legend-item">
            <i style={{ background: STAGE_COLORS[s] }} />
            {STAGE_LABELS[s]}
          </span>
        ))}
      </div>

      <section className="rl-gantt panel">
        <div className="rl-gantt-head" style={{ gridTemplateColumns: `200px repeat(${months.length}, 1fr)` }}>
          <div className="rl-gantt-head-label">行业 / 状态</div>
          {months.map((ym) => (
            <div key={ym} className="rl-gantt-head-month">
              {ym.slice(2)}
            </div>
          ))}
        </div>
        {filtered.length === 0 ? (
          <p className="empty">当前视图无记录{view === 'active' ? '（无进行中的旅程）' : ''}</p>
        ) : (
          filtered.map((j) => (
            <GanttRow
              key={`${j.assetId}-${j.journeyId}`}
              journey={j}
              months={months}
              falsified={j.status === 'falsified'}
              selected={selected?.journeyId === j.journeyId}
              onSelect={() => setSelectedId(j.journeyId)}
            />
          ))
        )}
      </section>

      {selected && (
        <aside className="rl-detail panel">
          <h3>
            {selected.assetName}
            <span className="rl-detail-sub">旅程 #{selected.journeyId}</span>
          </h3>
          <p className="rl-detail-line">
            <strong>状态</strong> {statusLabel(selected)}
            {selected.currentStage ? ` · ${STAGE_LABELS[selected.currentStage]}` : ''}
          </p>
          <p className="rl-detail-line">
            <strong>区间</strong> {selected.openedAt.slice(0, 7)}
            {selected.closedAt ? ` → ${selected.closedAt.slice(0, 7)}` : ' → 今'}
          </p>
          {selected.falsifiedReason && (
            <p className="rl-detail-line warn">
              <strong>证伪</strong> {selected.falsifiedReason}
            </p>
          )}
          <p className="rl-detail-line">
            <strong>决策</strong> {selected.decisionNote}
          </p>
          <p className="rl-detail-line">
            <strong>周度</strong> {selected.weeklyNote}
          </p>
          <h4>事件</h4>
          <ul className="rl-events">
            {selected.events.map((e, i) => (
              <li key={`${e.date}-${i}`}>
                <time>{e.date.slice(0, 7)}</time> {e.note}
              </li>
            ))}
          </ul>
        </aside>
      )}

      {policy.key_findings && (
        <section className="rl-findings panel">
          <h3>回测要点</h3>
          <ul>
            {policy.key_findings.slice(0, 4).map((line) => (
              <li key={line}>{line}</li>
            ))}
          </ul>
        </section>
      )}
    </div>
  )
}
