import React, { useState, useEffect, useCallback, useRef } from 'react'
import {
  Search, ChevronUp, ChevronDown, ChevronsUpDown,
  Mail, Instagram, Youtube, Twitter, Globe, BadgeCheck,
  ChevronLeft, ChevronRight, SlidersHorizontal, X, Filter, RotateCcw,
  Download, FileJson, FileSpreadsheet,
} from 'lucide-react'
import { api } from '../lib/api.js'
import { fmt, fmtPct, nicheColor, initials } from '../lib/utils.js'
import CreatorDetail from './CreatorDetail.jsx'

// Niches are loaded dynamically from /api/niches at mount time

const COLUMNS = [
  { key: 'handle',          label: 'Creator',       sortKey: 'handle',          width: 240 },
  { key: 'niche',           label: 'Niche',         sortKey: null,              width: 130 },
  { key: 'follower_count',  label: 'Followers',     sortKey: 'follower_count',  width: 100,  align: 'right' },
  { key: 'median_views',    label: 'Median views',  sortKey: 'median_views',    width: 110, align: 'right' },
  { key: 'mean_views',      label: 'Avg views',     sortKey: 'mean_views',      width: 100, align: 'right' },
  { key: 'engagement_rate', label: 'ER',            sortKey: 'engagement_rate', width: 70,  align: 'right' },
  { key: 'videos_sampled',  label: 'Vids',          sortKey: 'videos_sampled',  width: 60,  align: 'right' },
  { key: 'contacts',        label: 'Contact',       sortKey: null,              width: 130 },
  { key: 'region',          label: 'Region',        sortKey: null,              width: 80 },
]

const DEFAULT_FILTERS = {
  search: '',
  niche: 'all',
  median_min: '',
  median_max: '',
  follower_min: '',
  follower_max: '',
  min_er: '',
  min_videos: '',
  has_email: false,
  has_instagram: false,
  region: '',
}

export default function Creators() {
  const [filters, setFilters] = useState(DEFAULT_FILTERS)
  const [showFilters, setShowFilters] = useState(false)
  const [page, setPage] = useState(1)
  const [sort, setSort] = useState({ key: 'follower_count', order: 'desc' })
  const [data, setData] = useState({ items: [], total: 0, pages: 0 })
  const [loading, setLoading] = useState(true)
  const [selectedCreator, setSelectedCreator] = useState(null)
  const [regions, setRegions] = useState([])
  const [niches, setNiches] = useState([])   // [{niche, count}, ...]

  useEffect(() => { api.regions().then(setRegions).catch(() => {}) }, [])
  useEffect(() => {
    // Reload niches every 60s so newly-discovered ones appear during scraping
    const fetch = () => api.niches().then(setNiches).catch(() => {})
    fetch()
    const t = setInterval(fetch, 60_000)
    return () => clearInterval(t)
  }, [])

  const load = useCallback((f, p, s) => {
    setLoading(true)
    const params = {
      page: p,
      per_page: 50,
      sort: s.key,
      order: s.order,
      ...(f.search && { search: f.search }),
      ...(f.niche && f.niche !== 'all' && { niche: f.niche }),
      ...(f.median_min && { median_min: f.median_min }),
      ...(f.median_max && { median_max: f.median_max }),
      ...(f.follower_min && { follower_min: f.follower_min }),
      ...(f.follower_max && { follower_max: f.follower_max }),
      ...(f.min_er && { min_er: f.min_er }),
      ...(f.min_videos && { min_videos: f.min_videos }),
      ...(f.has_email && { has_email: true }),
      ...(f.has_instagram && { has_instagram: true }),
      ...(f.region && { region: f.region }),
    }
    return api.creators(params)
      .then(d => setData(d))
      .catch(() => setData({ items: [], total: 0, pages: 0 }))
      .finally(() => setLoading(false))
  }, [])

  // Reload whenever filters or sort changes (debounced)
  const debounceRef = useRef(null)
  useEffect(() => {
    clearTimeout(debounceRef.current)
    debounceRef.current = setTimeout(() => {
      setPage(1)
      load(filters, 1, sort)
    }, 250)
    return () => clearTimeout(debounceRef.current)
  }, [filters, sort, load])

  function updateFilter(key, value) {
    setFilters(f => ({ ...f, [key]: value }))
  }
  function resetFilters() {
    setFilters(DEFAULT_FILTERS)
  }
  function handleSort(key) {
    setSort(s => ({ key, order: s.key === key && s.order === 'desc' ? 'asc' : 'desc' }))
  }
  function handlePageChange(newPage) {
    setPage(newPage)
    load(filters, newPage, sort)
  }

  const activeFilterCount = Object.entries(filters).filter(([k, v]) => {
    if (k === 'niche') return v !== 'all'
    if (k === 'search') return false   // search shown in its own input
    return v !== '' && v !== false
  }).length

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 16 }}>
      {/* Header */}
      <div>
        <h1 className="title">Creators</h1>
        <p className="subtitle">
          {loading ? 'Loading…' : (
            <>
              <span className="mono" style={{ fontWeight: 600, color: 'var(--text)' }}>{fmt(data.total)}</span>
              {' '}matching creators in the database
            </>
          )}
        </p>
      </div>

      {/* Toolbar */}
      <div style={{ display: 'flex', alignItems: 'center', gap: 8, flexWrap: 'wrap' }}>
        <SearchBar
          value={filters.search}
          onChange={v => updateFilter('search', v)}
        />

        <button
          className="btn"
          onClick={() => setShowFilters(v => !v)}
          style={{
            background: showFilters ? 'var(--bg-active)' : undefined,
            borderColor: showFilters ? 'var(--border-strong)' : undefined,
          }}
        >
          <Filter size={13} />
          Filters
          {activeFilterCount > 0 && (
            <span style={{
              marginLeft: 2,
              background: 'var(--text)', color: 'var(--bg)',
              borderRadius: 999, minWidth: 18, height: 16,
              padding: '0 5px',
              display: 'inline-flex', alignItems: 'center', justifyContent: 'center',
              fontSize: 10.5, fontWeight: 700,
            }}>
              {activeFilterCount}
            </span>
          )}
        </button>

        {activeFilterCount > 0 && (
          <button className="btn btn-ghost" onClick={resetFilters} title="Clear all filters">
            <RotateCcw size={13} /> Clear
          </button>
        )}

        <ExportButton filters={filters} sort={sort} totalCount={data.total} />

        <div style={{ marginLeft: 'auto', display: 'flex', alignItems: 'center', gap: 6 }}>
          <SortInfo sort={sort} />
        </div>
      </div>

      {/* Filter panel */}
      {showFilters && (
        <div className="card fade-in" style={{ padding: 16 }}>
          <div style={{
            display: 'grid',
            gridTemplateColumns: 'repeat(auto-fill, minmax(200px, 1fr))',
            gap: 14,
          }}>
            <Field label="Niche">
              <select className="input" value={filters.niche} onChange={e => updateFilter('niche', e.target.value)}>
                <option value="all">All niches{niches.length ? ` (${niches.length})` : ''}</option>
                {niches.map(({ niche, count }) => (
                  <option key={niche} value={niche}>
                    {niche} ({fmt(count)})
                  </option>
                ))}
              </select>
            </Field>

            <Field label="Median views">
              <RangeInputs
                min={filters.median_min}
                max={filters.median_max}
                onMin={v => updateFilter('median_min', v)}
                onMax={v => updateFilter('median_max', v)}
              />
            </Field>

            <Field label="Followers">
              <RangeInputs
                min={filters.follower_min}
                max={filters.follower_max}
                onMin={v => updateFilter('follower_min', v)}
                onMax={v => updateFilter('follower_max', v)}
              />
            </Field>

            <Field label="Min engagement rate">
              <input
                className="input"
                type="number"
                step="0.01"
                placeholder="e.g. 0.02"
                value={filters.min_er}
                onChange={e => updateFilter('min_er', e.target.value)}
              />
            </Field>

            <Field label="Min videos sampled">
              <input
                className="input"
                type="number"
                placeholder="e.g. 5"
                value={filters.min_videos}
                onChange={e => updateFilter('min_videos', e.target.value)}
              />
            </Field>

            <Field label="Region">
              <select className="input" value={filters.region} onChange={e => updateFilter('region', e.target.value)}>
                <option value="">All regions</option>
                {regions.map(r => (
                  <option key={r.region} value={r.region}>{r.region} ({fmt(r.count)})</option>
                ))}
              </select>
            </Field>

            <Field label="Requirements">
              <div style={{ display: 'flex', flexDirection: 'column', gap: 8, paddingTop: 3 }}>
                <ToggleRow
                  checked={filters.has_email}
                  onChange={v => updateFilter('has_email', v)}
                  icon={<Mail size={12} />}
                  label="Has email"
                />
                <ToggleRow
                  checked={filters.has_instagram}
                  onChange={v => updateFilter('has_instagram', v)}
                  icon={<Instagram size={12} />}
                  label="Has Instagram"
                />
              </div>
            </Field>
          </div>
        </div>
      )}

      {/* Table */}
      <div
        className="card"
        style={{
          padding: 0,
          overflow: 'hidden',
          display: 'flex',
          flexDirection: 'column',
        }}
      >
        <div style={{ overflow: 'auto', flex: 1, maxHeight: 'calc(100vh - 320px)' }}>
          <table className="data-table">
            <thead>
              <tr>
                {COLUMNS.map(col => (
                  <th
                    key={col.key}
                    className={`${col.sortKey ? 'sortable' : ''} ${sort.key === col.sortKey ? 'sorted' : ''}`}
                    onClick={() => col.sortKey && handleSort(col.sortKey)}
                    style={{
                      width: col.width,
                      minWidth: col.width,
                      textAlign: col.align || 'left',
                    }}
                  >
                    <span style={{
                      display: 'inline-flex', alignItems: 'center', gap: 4,
                      justifyContent: col.align === 'right' ? 'flex-end' : 'flex-start',
                      width: '100%',
                    }}>
                      {col.label}
                      {col.sortKey && (
                        sort.key === col.sortKey
                          ? (sort.order === 'desc' ? <ChevronDown size={11} /> : <ChevronUp size={11} />)
                          : <ChevronsUpDown size={10} style={{ opacity: 0.3 }} />
                      )}
                    </span>
                  </th>
                ))}
              </tr>
            </thead>
            <tbody>
              {data.items.length === 0 && !loading && (
                <tr>
                  <td colSpan={COLUMNS.length} style={{ padding: 48, textAlign: 'center' }}>
                    <EmptyState onReset={resetFilters} hasFilters={activeFilterCount > 0} />
                  </td>
                </tr>
              )}
              {data.items.map(creator => (
                <CreatorRow
                  key={creator.sec_uid}
                  creator={creator}
                  selected={selectedCreator?.sec_uid === creator.sec_uid}
                  onClick={() => setSelectedCreator(creator)}
                />
              ))}
            </tbody>
          </table>
        </div>

        {/* Pagination footer */}
        {data.pages > 1 && (
          <Pagination
            current={page}
            total={data.pages}
            totalItems={data.total}
            onChange={handlePageChange}
          />
        )}
      </div>

      <CreatorDetail
        creator={selectedCreator}
        onClose={() => setSelectedCreator(null)}
      />
    </div>
  )
}

/* ============================================================ */

function SearchBar({ value, onChange }) {
  return (
    <div style={{ position: 'relative', flex: 1, maxWidth: 360, minWidth: 200 }}>
      <Search
        size={13}
        style={{
          position: 'absolute', left: 10, top: '50%', transform: 'translateY(-50%)',
          color: 'var(--text-3)', pointerEvents: 'none',
        }}
      />
      <input
        className="input"
        placeholder="Search handle, name, bio, email…"
        value={value}
        onChange={e => onChange(e.target.value)}
        style={{ paddingLeft: 30, paddingRight: value ? 28 : 10 }}
      />
      {value && (
        <button
          onClick={() => onChange('')}
          style={{
            position: 'absolute', right: 6, top: '50%', transform: 'translateY(-50%)',
            width: 20, height: 20, borderRadius: 4,
            border: 'none', background: 'transparent',
            display: 'flex', alignItems: 'center', justifyContent: 'center',
            color: 'var(--text-3)', cursor: 'pointer',
          }}
          onMouseEnter={e => { e.currentTarget.style.background = 'var(--bg-hover)' }}
          onMouseLeave={e => { e.currentTarget.style.background = 'transparent' }}
        >
          <X size={12} />
        </button>
      )}
    </div>
  )
}

function ExportButton({ filters, sort, totalCount }) {
  const [open, setOpen] = useState(false)
  const ref = useRef(null)

  useEffect(() => {
    if (!open) return
    const handler = (e) => { if (ref.current && !ref.current.contains(e.target)) setOpen(false) }
    document.addEventListener('mousedown', handler)
    return () => document.removeEventListener('mousedown', handler)
  }, [open])

  function buildUrl(format) {
    const params = new URLSearchParams()
    params.set('format', format)
    params.set('sort', sort.key)
    params.set('order', sort.order)
    if (filters.search) params.set('search', filters.search)
    if (filters.niche && filters.niche !== 'all') params.set('niche', filters.niche)
    if (filters.median_min) params.set('median_min', filters.median_min)
    if (filters.median_max) params.set('median_max', filters.median_max)
    if (filters.follower_min) params.set('follower_min', filters.follower_min)
    if (filters.follower_max) params.set('follower_max', filters.follower_max)
    if (filters.min_er) params.set('min_er', filters.min_er)
    if (filters.min_videos) params.set('min_videos', filters.min_videos)
    if (filters.has_email) params.set('has_email', 'true')
    if (filters.has_instagram) params.set('has_instagram', 'true')
    if (filters.region) params.set('region', filters.region)
    return `/api/creators/export?${params.toString()}`
  }

  function download(format) {
    const url = buildUrl(format)
    const a = document.createElement('a')
    a.href = url
    a.download = ''  // hint to browser to download, server sets filename
    document.body.appendChild(a)
    a.click()
    document.body.removeChild(a)
    setOpen(false)
  }

  return (
    <div ref={ref} style={{ position: 'relative' }}>
      <button
        className="btn"
        onClick={() => setOpen(o => !o)}
        title={totalCount > 0 ? `Export ${fmt(totalCount)} creators` : 'No data to export'}
        disabled={totalCount === 0}
      >
        <Download size={13} />
        Export
        <ChevronDown size={11} style={{ marginLeft: 2, opacity: 0.6 }} />
      </button>

      {open && (
        <div
          className="card fade-in"
          style={{
            position: 'absolute',
            top: 'calc(100% + 4px)',
            left: 0,
            minWidth: 200,
            padding: 4,
            zIndex: 30,
            boxShadow: 'var(--shadow-md)',
          }}
        >
          <MenuItem icon={<FileSpreadsheet size={13} />} label="Export as CSV"     hint=".csv"  onClick={() => download('csv')} />
          <MenuItem icon={<FileJson size={13} />}        label="Export as JSON"   hint=".json" onClick={() => download('json')} />
          <div style={{ padding: '6px 10px 4px', fontSize: 11, color: 'var(--text-3)', borderTop: '1px solid var(--border)', marginTop: 4 }}>
            Exports {fmt(totalCount)} matching creators with current filters.
          </div>
        </div>
      )}
    </div>
  )
}

function MenuItem({ icon, label, hint, onClick }) {
  return (
    <button
      onClick={onClick}
      style={{
        display: 'flex', alignItems: 'center', gap: 8, width: '100%',
        padding: '7px 10px', borderRadius: 5, border: 'none',
        background: 'transparent', color: 'var(--text)', cursor: 'pointer',
        fontSize: 13, textAlign: 'left',
      }}
      onMouseEnter={e => { e.currentTarget.style.background = 'var(--bg-hover)' }}
      onMouseLeave={e => { e.currentTarget.style.background = 'transparent' }}
    >
      <span style={{ color: 'var(--text-2)' }}>{icon}</span>
      <span style={{ flex: 1 }}>{label}</span>
      {hint && <span className="mono" style={{ fontSize: 11, color: 'var(--text-3)' }}>{hint}</span>}
    </button>
  )
}

function SortInfo({ sort }) {
  const label = {
    follower_count: 'followers',
    median_views: 'median views',
    mean_views: 'avg views',
    engagement_rate: 'engagement rate',
    videos_sampled: 'videos sampled',
    handle: 'handle',
  }[sort.key] || sort.key
  return (
    <span style={{ fontSize: 12, color: 'var(--text-3)' }}>
      Sorted by <span style={{ color: 'var(--text-2)', fontWeight: 500 }}>{label}</span>
      {sort.order === 'desc' ? ' ↓' : ' ↑'}
    </span>
  )
}

function Field({ label, children }) {
  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 6 }}>
      <label className="section-label">{label}</label>
      {children}
    </div>
  )
}

function RangeInputs({ min, max, onMin, onMax }) {
  return (
    <div style={{ display: 'flex', gap: 6 }}>
      <input className="input" type="number" placeholder="Min" value={min} onChange={e => onMin(e.target.value)} />
      <input className="input" type="number" placeholder="Max" value={max} onChange={e => onMax(e.target.value)} />
    </div>
  )
}

function ToggleRow({ checked, onChange, icon, label }) {
  return (
    <div
      className="toggle"
      onClick={() => onChange(!checked)}
      style={{ cursor: 'pointer' }}
    >
      <span className={`toggle-track${checked ? ' on' : ''}`}>
        <span className="toggle-thumb" />
      </span>
      <span style={{ display: 'inline-flex', alignItems: 'center', gap: 5, color: checked ? 'var(--text)' : 'var(--text-2)' }}>
        {icon}
        {label}
      </span>
    </div>
  )
}

function CreatorRow({ creator, selected, onClick }) {
  const niche = inferNiche(creator.hashtags_seen)
  return (
    <tr className={selected ? 'selected' : ''} onClick={onClick}>
      <td style={{ maxWidth: 240 }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
          <Avatar name={creator.nickname || creator.unique_id} />
          <div style={{ minWidth: 0 }}>
            <div style={{
              display: 'flex', alignItems: 'center', gap: 4,
              fontWeight: 500, color: 'var(--text)',
              overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap',
            }}>
              @{creator.unique_id}
              {creator.verified ? <BadgeCheck size={12} style={{ color: 'var(--accent)', flexShrink: 0 }} /> : null}
            </div>
            {creator.nickname && (
              <div style={{
                fontSize: 12, color: 'var(--text-3)',
                overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap',
              }}>
                {creator.nickname}
              </div>
            )}
          </div>
        </div>
      </td>

      <td>
        {niche && (
          <span
            className="badge"
            style={{
              background: nicheColor(niche) + '20',
              color: nicheColor(niche),
              borderColor: 'transparent',
            }}
          >
            {niche}
          </span>
        )}
      </td>

      <td className="mono" style={{ textAlign: 'right' }}>{fmt(creator.follower_count)}</td>

      <td className="mono" style={{ textAlign: 'right' }}>
        <span style={{ fontWeight: 500 }}>{fmt(creator.median_views)}</span>
        {creator.is_enriched ? (
          <span title="Enriched from profile" style={{
            fontSize: 9, marginLeft: 4, color: 'var(--success)', fontWeight: 700,
          }}>
            ✓
          </span>
        ) : null}
      </td>

      <td className="mono" style={{ textAlign: 'right', color: 'var(--text-2)' }}>
        {fmt(creator.mean_views)}
      </td>

      <td className="mono" style={{ textAlign: 'right' }}>
        <EngagementBadge rate={creator.engagement_rate} />
      </td>

      <td className="mono" style={{ textAlign: 'right', color: 'var(--text-3)', fontSize: 12 }}>
        {creator.videos_sampled || '—'}
      </td>

      <td>
        <div style={{ display: 'flex', gap: 3 }}>
          {creator.email     && <ContactDot icon={<Mail size={10} />}      title={creator.email} />}
          {creator.instagram && <ContactDot icon={<Instagram size={10} />} title={creator.instagram} />}
          {creator.youtube   && <ContactDot icon={<Youtube size={10} />}   title={creator.youtube} />}
          {creator.twitter   && <ContactDot icon={<Twitter size={10} />}   title={creator.twitter} />}
          {creator.website   && <ContactDot icon={<Globe size={10} />}     title={creator.website} />}
          {!creator.email && !creator.instagram && !creator.youtube && !creator.twitter && !creator.website && (
            <span style={{ color: 'var(--text-3)', fontSize: 12 }}>—</span>
          )}
        </div>
      </td>

      <td style={{ color: 'var(--text-3)', fontSize: 12 }}>
        {creator.region || '—'}
      </td>
    </tr>
  )
}

function Avatar({ name }) {
  return (
    <div style={{
      width: 28, height: 28,
      borderRadius: '50%',
      background: 'var(--bg-active)',
      color: 'var(--text-2)',
      display: 'flex', alignItems: 'center', justifyContent: 'center',
      fontSize: 11, fontWeight: 600,
      flexShrink: 0,
    }}>
      {initials(name)}
    </div>
  )
}

function EngagementBadge({ rate }) {
  if (rate === null || rate === undefined) return <span style={{ color: 'var(--text-3)' }}>—</span>
  const color = rate >= 0.08 ? 'var(--success)'
              : rate >= 0.03 ? 'var(--text)'
              : 'var(--text-3)'
  return <span style={{ color, fontWeight: rate >= 0.03 ? 500 : 400 }}>{fmtPct(rate)}</span>
}

function ContactDot({ icon, title }) {
  return (
    <span
      title={title}
      style={{
        display: 'inline-flex', alignItems: 'center', justifyContent: 'center',
        width: 22, height: 22, borderRadius: 5,
        background: 'var(--bg-subtle)', color: 'var(--text-2)',
        border: '1px solid var(--border)',
      }}
    >
      {icon}
    </span>
  )
}

function EmptyState({ onReset, hasFilters }) {
  return (
    <div>
      <div style={{
        width: 40, height: 40,
        borderRadius: 10,
        background: 'var(--bg-active)',
        color: 'var(--text-3)',
        display: 'flex', alignItems: 'center', justifyContent: 'center',
        margin: '0 auto 12px',
      }}>
        <Search size={18} />
      </div>
      <div style={{ fontWeight: 600, color: 'var(--text)', marginBottom: 4 }}>
        No creators found
      </div>
      <div style={{ fontSize: 13, color: 'var(--text-2)', marginBottom: 14 }}>
        {hasFilters ? 'Try widening your filters or clearing them.' : 'Run scraper.py to populate the database.'}
      </div>
      {hasFilters && (
        <button className="btn" onClick={onReset}>
          <RotateCcw size={13} /> Clear filters
        </button>
      )}
    </div>
  )
}

function Pagination({ current, total, totalItems, onChange }) {
  return (
    <div style={{
      display: 'flex', alignItems: 'center', justifyContent: 'space-between',
      padding: '10px 14px',
      borderTop: '1px solid var(--border)',
      background: 'var(--bg-subtle)',
    }}>
      <span style={{ fontSize: 12, color: 'var(--text-3)' }}>
        Page {current} of {total} · {fmt(totalItems)} total
      </span>
      <div style={{ display: 'flex', gap: 4 }}>
        <button className="btn btn-sm btn-icon" disabled={current <= 1} onClick={() => onChange(current - 1)}>
          <ChevronLeft size={13} />
        </button>
        {pageRange(current, total).map((p, i) => (
          <button
            key={`${p}-${i}`}
            className={p === current ? 'btn btn-sm btn-primary' : 'btn btn-sm'}
            onClick={() => typeof p === 'number' && onChange(p)}
            disabled={typeof p !== 'number'}
            style={{ minWidth: 28 }}
          >
            {p}
          </button>
        ))}
        <button className="btn btn-sm btn-icon" disabled={current >= total} onClick={() => onChange(current + 1)}>
          <ChevronRight size={13} />
        </button>
      </div>
    </div>
  )
}

/* ============================================================ */

const NICHE_MAP = {
  // Entertainment
  fyp: 'entertainment', foryou: 'entertainment', foryoupage: 'entertainment',
  viral: 'entertainment', trending: 'entertainment', tiktok: 'entertainment',
  // Comedy
  comedy: 'comedy', funny: 'comedy', memes: 'comedy', humor: 'comedy',
  pranks: 'comedy', skit: 'comedy', relatable: 'comedy', fails: 'comedy',
  jokes: 'comedy', standup: 'comedy', roast: 'comedy', storytime: 'comedy',
  confessions: 'comedy', pov: 'comedy',
  // Dance/Music
  dance: 'dance/music', music: 'dance/music', singing: 'dance/music',
  singer: 'dance/music', musician: 'dance/music', rap: 'dance/music',
  hiphop: 'dance/music', rnb: 'dance/music', cover: 'dance/music',
  producer: 'dance/music', beatmaker: 'dance/music', indieartist: 'dance/music',
  newmusic: 'dance/music', songwriter: 'dance/music', choreography: 'dance/music',
  // Beauty
  makeup: 'beauty', skincare: 'beauty', beauty: 'beauty', haircare: 'beauty',
  nails: 'beauty', mensgrooming: 'beauty', perfume: 'beauty', fragrance: 'beauty',
  glowup: 'beauty', grwm: 'beauty', hairtok: 'beauty', skintok: 'beauty',
  acne: 'beauty', antiaging: 'beauty', naturalhair: 'beauty',
  // Fashion
  fashion: 'fashion', ootd: 'fashion', outfit: 'fashion', streetwear: 'fashion',
  aesthetic: 'fashion', thrift: 'fashion', menstyle: 'fashion',
  vintage: 'fashion', cottagecore: 'fashion', darkacademia: 'fashion', y2k: 'fashion',
  // Fitness
  fitness: 'fitness', gym: 'fitness', workout: 'fitness', yoga: 'fitness',
  running: 'fitness', bodybuilding: 'fitness', pilates: 'fitness',
  weightloss: 'fitness', crossfit: 'fitness', calisthenics: 'fitness',
  homeworkout: 'fitness', cycling: 'fitness', swimming: 'fitness',
  // Food
  food: 'food', recipe: 'food', cooking: 'food', baking: 'food', foodie: 'food',
  mealprep: 'food', chef: 'food', coffee: 'food', dessert: 'food',
  vegantok: 'food', sourdough: 'food',
  // Travel
  travel: 'travel', wanderlust: 'travel', hiking: 'travel', vanlife: 'travel',
  roadtrip: 'travel', backpacking: 'travel', solotravel: 'travel',
  digitalnomad: 'travel', solofemaletravel: 'travel',
  // Tech
  tech: 'tech', gadgets: 'tech', coding: 'tech', programming: 'tech',
  ai: 'tech', iphone: 'tech', android: 'tech', smarthome: 'tech',
  cybersecurity: 'tech', linux: 'tech', chatgpt: 'tech', machinelearning: 'tech',
  // Gaming
  gaming: 'gaming', gamer: 'gaming', fortnite: 'gaming', minecraft: 'gaming',
  valorant: 'gaming', roblox: 'gaming', streamer: 'gaming', twitch: 'gaming',
  esports: 'gaming', gamedev: 'gaming', pcgaming: 'gaming',
  // Finance
  finance: 'finance', investing: 'finance', stocks: 'finance', crypto: 'finance',
  personalfinance: 'finance', realestate: 'finance', nft: 'finance',
  // Business
  entrepreneur: 'business', sidehustle: 'business', marketing: 'business',
  smallbusiness: 'business', dropshipping: 'business', ecommerce: 'business',
  // Productivity / Education
  productivity: 'productivity', career: 'productivity', jobsearch: 'productivity',
  studytok: 'education', student: 'education', college: 'education',
  learnontiktok: 'education', teacher: 'education', science: 'education',
  history: 'education', psychology: 'education', languagelearning: 'education',
  // Art
  art: 'art', drawing: 'art', painting: 'art', photography: 'art',
  digitalart: 'art', illustration: 'art', tattoo: 'art',
  interiordesign: 'art', architecture: 'art', graphicdesign: 'art',
  // DIY
  diy: 'diy', crafts: 'diy', woodworking: 'diy', lifehack: 'diy',
  // Books
  booktok: 'books', reading: 'books', writing: 'books',
  poetry: 'books', author: 'books', bookclub: 'books',
  fantasy: 'books', selfhelp: 'books',
  // Pets
  pets: 'pets', dog: 'pets', cat: 'pets', reptile: 'pets',
  dogtraining: 'pets', cattok: 'pets', horse: 'pets', aquarium: 'pets',
  // Lifestyle
  motivation: 'lifestyle', mentalhealth: 'lifestyle', selfcare: 'lifestyle',
  asmr: 'lifestyle', satisfying: 'lifestyle', meditation: 'lifestyle',
  journaling: 'lifestyle', minimalism: 'lifestyle', zerowaste: 'lifestyle',
  sustainability: 'lifestyle', plantmom: 'lifestyle', gardening: 'lifestyle',
  homestead: 'lifestyle',
  // Family
  mom: 'family', dad: 'family', parenting: 'family', pregnancy: 'family',
  newborn: 'family', adulting: 'family',
  // Community
  lgbt: 'community', womenempowerment: 'community',
  blacktiktok: 'community', latinotiktok: 'community', asiantiktok: 'community',
  // Regional
  uktiktok: 'regional', australiantiktok: 'regional', canadatiktok: 'regional',
  indiatiktok: 'regional', nigeriatiktok: 'regional', philippinestiktok: 'regional',
  braziltiktok: 'regional', mexicotiktok: 'regional',
  southafricatiktok: 'regional', singaporetiktok: 'regional',
}

function inferNiche(hashtagsStr) {
  if (!hashtagsStr) return null
  const tags = hashtagsStr.split(',').map(t => t.trim().toLowerCase())
  const votes = {}
  for (const t of tags) {
    const n = NICHE_MAP[t]
    if (n) votes[n] = (votes[n] || 0) + 1
  }
  const sorted = Object.entries(votes).sort((a, b) => b[1] - a[1])
  return sorted.length > 0 ? sorted[0][0] : null
}

function pageRange(current, total) {
  if (total <= 7) return Array.from({ length: total }, (_, i) => i + 1)
  const pages = []
  if (current <= 4) pages.push(1, 2, 3, 4, 5, '…', total)
  else if (current >= total - 3) pages.push(1, '…', total - 4, total - 3, total - 2, total - 1, total)
  else pages.push(1, '…', current - 1, current, current + 1, '…', total)
  return pages
}
