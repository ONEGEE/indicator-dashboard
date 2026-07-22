import { useEffect, useState } from 'react'

const STORAGE_KEY = 'databoard-theme'

export type ThemeMode = 'light' | 'dark'

export function getStoredTheme(): ThemeMode {
  try {
    const v = localStorage.getItem(STORAGE_KEY)
    if (v === 'dark' || v === 'light') return v
  } catch {
    /* ignore */
  }
  return 'light'
}

export function applyTheme(mode: ThemeMode) {
  document.documentElement.setAttribute('data-theme', mode)
  try {
    localStorage.setItem(STORAGE_KEY, mode)
  } catch {
    /* ignore */
  }
}

/** 顶栏主题开关，作用于全部页签 */
export default function ThemeToggle() {
  const [theme, setTheme] = useState<ThemeMode>(() => getStoredTheme())

  useEffect(() => {
    applyTheme(theme)
  }, [theme])

  const dark = theme === 'dark'

  return (
    <label className="theme-toggle" title={dark ? '切换为浅色' : '切换为暗黑'}>
      <span className="theme-toggle-label">{dark ? '暗黑' : '浅色'}</span>
      <button
        type="button"
        role="switch"
        aria-checked={dark}
        aria-label="暗黑风格开关"
        className={`theme-switch ${dark ? 'on' : ''}`}
        onClick={() => setTheme(dark ? 'light' : 'dark')}
      >
        <span className="theme-switch-knob" />
      </button>
    </label>
  )
}
