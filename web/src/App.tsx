import { useEffect, useMemo, useState } from 'react'
import { publicUrl } from './assets'
import MarketCapView from './MarketCapView'
import RrgView from './RrgView'
import ThemeToggle from './ThemeToggle'
import type { Catalog, SeriesItem } from './types'

type Page = 'catalog' | 'marketcap' | 'rrg'

function formatValue(item: SeriesItem): string {
  const v = item.stats.last_value
  if (v == null) return '—'
  const abs = Math.abs(v)
  const digits = abs >= 1000 ? 2 : abs >= 10 ? 2 : 4
  const text = v.toLocaleString('zh-CN', {
    maximumFractionDigits: digits,
    minimumFractionDigits: 0,
  })
  return item.unit === 'percent' ? `${text}%` : text
}

export default function App() {
  const [page, setPage] = useState<Page>('marketcap')
  const [catalog, setCatalog] = useState<Catalog | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [pillar, setPillar] = useState<string>('all')
  const [tier, setTier] = useState<string>('all')
  const [region, setRegion] = useState<string>('all')
  const [query, setQuery] = useState('')
  const [selectedId, setSelectedId] = useState<string | null>(null)

  useEffect(() => {
    fetch(publicUrl('catalog.json'))
      .then((r) => {
        if (!r.ok) throw new Error(`加载 catalog 失败: ${r.status}`)
        return r.json()
      })
      .then((data: Catalog) => {
        setCatalog(data)
        setSelectedId(data.series[0]?.id ?? null)
      })
      .catch((e: Error) => setError(e.message))
  }, [])

  const regions = useMemo(() => {
    if (!catalog) return []
    return [...new Set(catalog.series.map((s) => s.region).filter(Boolean) as string[])].sort()
  }, [catalog])

  const filtered = useMemo(() => {
    if (!catalog) return []
    const q = query.trim().toLowerCase()
    return catalog.series.filter((s) => {
      if (pillar !== 'all' && s.pillar !== pillar) return false
      if (tier !== 'all' && (s.tier ?? 'market') !== tier) return false
      if (region !== 'all' && s.region !== region) return false
      if (!q) return true
      const hay = [s.name, s.name_en, s.id, s.symbol, s.source].filter(Boolean).join(' ').toLowerCase()
      return hay.includes(q)
    })
  }, [catalog, pillar, tier, region, query])

  const selected = catalog?.series.find((s) => s.id === selectedId) ?? filtered[0] ?? null

  const nav = (
    <nav className="app-nav">
      <button
        type="button"
        className={`app-nav-btn ${page === 'catalog' ? 'active' : ''}`}
        onClick={() => setPage('catalog')}
      >
        数据目录
      </button>
      <button
        type="button"
        className={`app-nav-btn ${page === 'marketcap' ? 'active' : ''}`}
        onClick={() => setPage('marketcap')}
      >
        规模占比
      </button>
      <button
        type="button"
        className={`app-nav-btn ${page === 'rrg' ? 'active' : ''}`}
        onClick={() => setPage('rrg')}
      >
        资本轮动
      </button>
      <ThemeToggle />
    </nav>
  )

  if (page === 'marketcap') {
    return (
      <div className="app">
        {nav}
        <MarketCapView />
      </div>
    )
  }

  if (page === 'rrg') {
    return (
      <div className="app app-rrg">
        {nav}
        <RrgView />
      </div>
    )
  }

  if (error) {
    return (
      <div className="app">
        {nav}
        <p className="empty">{error}</p>
      </div>
    )
  }

  if (!catalog) {
    return (
      <div className="app">
        {nav}
        <p className="empty">正在加载数据目录…</p>
      </div>
    )
  }

  const { framework, counts } = catalog

  return (
    <div className="app">
      {nav}
      <header className="hero">
        <div>
          <p className="meta-row" style={{ marginBottom: 8 }}>
            <span>投资决策数据台 · Phase 1</span>
          </p>
          <h1 className="brand">{framework.title}</h1>
        </div>
        <p className="lede">{framework.summary}</p>
        <div className="meta-row">
          <span>
            参考框架：
            <a href={framework.reference_url} target="_blank" rel="noreferrer">
              {framework.reference}
            </a>
          </span>
          <span>目录生成：{catalog.generated_at}</span>
        </div>
        <div className="stats">
          <div className="stat">
            <strong>{counts.total}</strong>
            <span>数据序列</span>
          </div>
          <div className="stat">
            <strong>{counts.with_data}</strong>
            <span>已入库</span>
          </div>
          <div className="stat">
            <strong>{counts.by_tier?.longrun ?? 0}</strong>
            <span>百年长周期</span>
          </div>
        </div>
      </header>

      <section className="pillars">
        <button
          type="button"
          className={`pillar ${pillar === 'all' ? 'active' : ''}`}
          onClick={() => setPillar('all')}
        >
          <h3>全部</h3>
          <div className="role">浏览全部序列</div>
          <p>按中金大类资产框架组织：股、债、地产、商品、贵金属，并附宏观情境数据。</p>
          <div className="count">{counts.total} 项</div>
        </button>
        {framework.pillars.map((p) => (
          <button
            key={p.id}
            type="button"
            className={`pillar ${pillar === p.id ? 'active' : ''}`}
            onClick={() => setPillar(p.id)}
          >
            <h3>{p.name}</h3>
            <div className="role">{p.role}</div>
            <p>{p.description}</p>
            <div className="count">{counts.by_pillar[p.id] ?? 0} 项</div>
          </button>
        ))}
      </section>

      <div className="toolbar">
        <input
          value={query}
          onChange={(e) => setQuery(e.target.value)}
          placeholder="搜索名称 / 代码 / 数据源"
        />
        <select value={region} onChange={(e) => setRegion(e.target.value)}>
          <option value="all">全部地区</option>
          {regions.map((r) => (
            <option key={r} value={r}>
              {r}
            </option>
          ))}
        </select>
        <select value={tier} onChange={(e) => setTier(e.target.value)}>
          <option value="all">全部层级</option>
          <option value="longrun">百年长周期 (JST/Jacks/Shiller)</option>
          <option value="market">市场高频 (日/月)</option>
        </select>
      </div>

      {catalog.validation?.pairs?.length ? (
        <section className="detail" style={{ marginBottom: 16 }}>
          <h2 style={{ fontSize: '1.2rem', marginBottom: 10 }}>交叉验证</h2>
          <div className="table-wrap">
            <table>
              <thead>
                <tr>
                  <th>对比项</th>
                  <th>重叠区间</th>
                  <th>相关系数</th>
                  <th>样本</th>
                </tr>
              </thead>
              <tbody>
                {catalog.validation.pairs.map((p) => (
                  <tr key={p.id}>
                    <td>{p.name}</td>
                    <td>
                      {p.overlap_start && p.overlap_end
                        ? `${p.overlap_start} → ${p.overlap_end}`
                        : p.error ?? '—'}
                    </td>
                    <td>{p.correlation != null ? p.correlation.toFixed(4) : '—'}</td>
                    <td>{p.rows ?? '—'}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </section>
      ) : null}

      <div className="table-wrap">
        {filtered.length === 0 ? (
          <div className="empty">没有匹配的数据项</div>
        ) : (
          <table>
            <thead>
              <tr>
                <th>名称</th>
                <th>支柱</th>
                <th>层级</th>
                <th>地区</th>
                <th>频率</th>
                <th>最新值</th>
                <th>区间</th>
                <th>行数</th>
                <th>来源</th>
              </tr>
            </thead>
            <tbody>
              {filtered.map((item) => {
                const pillarMeta = framework.pillars.find((p) => p.id === item.pillar)
                return (
                  <tr
                    key={item.id}
                    className={`clickable ${selected?.id === item.id ? 'selected' : ''}`}
                    onClick={() => setSelectedId(item.id)}
                  >
                    <td className="name-cell">
                      <strong>{item.name}</strong>
                      <span>{item.symbol ?? item.id}</span>
                    </td>
                    <td>
                      <span className="badge">{pillarMeta?.name ?? item.pillar}</span>
                    </td>
                    <td>
                      <span className="badge">{(item.tier ?? 'market') === 'longrun' ? '长周期' : '市场'}</span>
                    </td>
                    <td>{item.region ?? '—'}</td>
                    <td>{item.frequency ?? '—'}</td>
                    <td>{formatValue(item)}</td>
                    <td>
                      {item.stats.start && item.stats.end
                        ? `${item.stats.start} → ${item.stats.end}`
                        : '—'}
                    </td>
                    <td>{item.stats.rows.toLocaleString('zh-CN')}</td>
                    <td>{item.source ?? '—'}</td>
                  </tr>
                )
              })}
            </tbody>
          </table>
        )}
      </div>

      {selected && (
        <section className="detail">
          <h2>{selected.name}</h2>
          <div className="sub">
            {selected.name_en ? `${selected.name_en} · ` : ''}
            {selected.id}
          </div>
          <div className="detail-grid">
            <div>
              <label>支柱</label>
              <div>{framework.pillars.find((p) => p.id === selected.pillar)?.name ?? selected.pillar}</div>
            </div>
            <div>
              <label>标的 / 代码</label>
              <div>{selected.symbol ?? '—'}</div>
            </div>
            <div>
              <label>CSV 路径</label>
              <div>data/{selected.csv}</div>
            </div>
            <div>
              <label>字段</label>
              <div>{selected.stats.schema?.join(', ') ?? '—'}</div>
            </div>
            <div>
              <label>最新值字段</label>
              <div>{selected.stats.value_field ?? '—'}</div>
            </div>
            <div>
              <label>最新值</label>
              <div>{formatValue(selected)}</div>
            </div>
            <div>
              <label>起止</label>
              <div>
                {selected.stats.start && selected.stats.end
                  ? `${selected.stats.start} → ${selected.stats.end}`
                  : '—'}
              </div>
            </div>
            <div>
              <label>单位</label>
              <div>{selected.unit ?? '—'}</div>
            </div>
          </div>
          {selected.notes && <p className="notes">{selected.notes}</p>}
        </section>
      )}
    </div>
  )
}
