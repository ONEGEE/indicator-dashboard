export type SeriesStats = {
  exists: boolean
  rows: number
  start: string | null
  end: string | null
  last_value: number | null
  value_field: string | null
  schema: string[] | null
}

export type Pillar = {
  id: string
  name: string
  name_en: string
  role: string
  description: string
}

export type SeriesItem = {
  id: string
  name: string
  name_en?: string | null
  pillar: string
  origin: string
  tier?: string
  category?: string | null
  subcategory?: string | null
  region?: string | null
  source?: string | null
  symbol?: string | null
  frequency?: string | null
  unit?: string | null
  csv: string
  notes?: string | null
  stats: SeriesStats
}

export type ValidationPair = {
  id: string
  name: string
  method?: string
  overlap_start?: string
  overlap_end?: string
  rows?: number
  correlation?: number
  mean_abs_diff?: number
  csv?: string
  error?: string
}

export type Catalog = {
  generated_at: string
  framework: {
    title: string
    reference: string
    reference_url: string
    summary: string
    pillars: Pillar[]
    longrun_sources?: Record<string, { name: string; url: string; coverage: string }>
  }
  validation?: { generated_at: string; pairs: ValidationPair[] } | null
  counts: {
    total: number
    with_data: number
    by_pillar: Record<string, number>
    by_tier?: Record<string, number>
  }
  series: SeriesItem[]
}
