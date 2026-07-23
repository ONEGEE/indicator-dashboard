/** 根据 Vite base 解析 public 目录下的 JSON 等资源路径（兼容 GitHub Pages base）。 */
export function publicUrl(path: string): string {
  const base = import.meta.env.BASE_URL || '/'
  const normalized = path.replace(/^\//, '')
  return `${base}${normalized}`
}
