import React, { useEffect, useState, useRef } from 'react'
import {
  Mail, Instagram, Video, Users, Hash, Sparkles,
  ArrowUpRight, TrendingUp, Activity,
} from 'lucide-react'
import { api } from '../lib/api.js'
import { fmt, nicheColor } from '../lib/utils.js'

export default function Dashboard({ onNavigate }) {
  const [stats, setStats] = useState(null)
  const [prevStats, setPrevStats] = useState(null)
  const [niches, setNiches] = useState([])
  const [dist, setDist] = useState([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState(null)
  const [lastRefresh, setLastRefresh] = useState(null)
  const prevStatsRef = useRef(null)

  function loadAll(showLoading = false) {
    if (showLoading) setLoading(true)
    Promise.all([api.stats(), api.niches(), api.viewDistribution()])
      .then(([s, n, d]) => {
        if (prevStatsRef.current) setPrevStats(prevStatsRef.current)
        prevStatsRef.current = s
        setStats(s)
        setNiches(n.slice(0, 10))
        setDist(d)
        setLastRefresh(new Date())
        setError(null)
      })
      .catch(e => setError(e.message))
      .finally(() => setLoading(false))
  }

  useEffect(() => {
    loadAll(true)
    const interval = setInterval(() => loadAll(false), 30_000)
    return () => clearInterval(interval)
  }, [])

  if (loading && !stats) return <LoadingState />
  if (error && !stats)   return <ErrorState message={error} />
  if (stats?.error)      return <ErrorState message={stats.error} />

  const progressPct = stats.hashtags_total
    ? (stats.hashtags_done / stats.hashtags_total) * 100
    : 0

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 28 }}>
      {/* Page header */}
      <div style={{ display: 'flex', alignItems: 'flex-start', justifyContent: 'space-between', gap: 20 }}>
        <div>
          <h1 className="title">Overview</h1>
          <p className="subtitle">
            Watching your creator database grow in real time.
          </p>
        </div>
        <LiveIndicator lastRefresh={lastRefresh} />
      </div>

      {/* Progress bar */}
      <div className="card" style={{ padding: 18 }}>
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 10 }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
            <Activity size={14} style={{ color: 'var(--text-3)' }} />
            <span style={{ fontSize: 13, fontWeight: 500 }}>Hashtag progress</span>
            <span style={{ fontSize: 12, color: 'var(--text-3)' }}>
              {stats.hashtags_done} of {stats.hashtags_total} scraped
            </span>
          </div>
          <span className="mono" style={{ fontSize: 13, fontWeight: 600 }}>
            {progressPct.toFixed(1)}%
          </span>
        </div>
        <div style={{ height: 4, background: 'var(--bg-active)', borderRadius: 2, overflow: 'hidden' }}>
          <div
            style={{
              height: '100%',
              width: `${progressPct}%`,
              background: 'var(--text)',
              borderRadius: 2,
              transition: 'width 0.6s cubic-bezier(0.16, 1, 0.3, 1)',
            }}
          />
        </div>
      </div>

      {/* Stat cards grid */}
      <div
        style={{
          display: 'grid',
          gridTemplateColumns: 'repeat(auto-fill, minmax(220px, 1fr))',
          gap: 12,
        }}
      >
        <StatCard
          icon={<Users size={14} />}
          label="Creators"
          value={stats.total_creators}
          prev={prevStats?.total_creators}
          sub="unique profiles"
        />
        <StatCard
          icon={<Video size={14} />}
          label="Videos"
          value={stats.total_videos}
          prev={prevStats?.total_videos}
          sub="scraped"
        />
        <StatCard
          icon={<Mail size={14} />}
          label="With email"
          value={stats.with_email}
          prev={prevStats?.with_email}
          sub={stats.total_creators ? `${((stats.with_email / stats.total_creators) * 100).toFixed(1)}% coverage` : '—'}
        />
        <StatCard
          icon={<Instagram size={14} />}
          label="With Instagram"
          value={stats.with_instagram}
          prev={prevStats?.with_instagram}
          sub={stats.total_creators ? `${((stats.with_instagram / stats.total_creators) * 100).toFixed(1)}% coverage` : '—'}
        />
        {stats.enriched > 0 && (
          <StatCard
            icon={<Sparkles size={14} />}
            label="Enriched"
            value={stats.enriched}
            prev={prevStats?.enriched}
            sub="accurate medians"
          />
        )}
        <StatCard
          icon={<Hash size={14} />}
          label="Hashtags"
          value={`${stats.hashtags_done}/${stats.hashtags_total}`}
          sub={stats.hashtags_done === stats.hashtags_total ? 'all complete' : 'in progress'}
          noMono
        />
      </div>

      {/* Charts */}
      <div
        style={{
          display: 'grid',
          gridTemplateColumns: 'repeat(auto-fit, minmax(360px, 1fr))',
          gap: 16,
        }}
      >
        <ChartCard
          title="Creators by niche"
          subtitle="Derived from hashtag sources"
        >
          <BarList
            data={niches}
            labelKey="niche"
            valueKey="count"
            colorFn={nicheColor}
            labelWidth={110}
          />
        </ChartCard>

        <ChartCard
          title="View distribution"
          subtitle="Across all scraped videos"
        >
          <BarList
            data={dist}
            labelKey="range"
            valueKey="count"
            color="var(--text-2)"
            labelWidth={82}
          />
        </ChartCard>
      </div>

      {/* CTA */}
      {stats.total_creators > 0 && (
        <div
          className="card card-hover"
          style={{
            display: 'flex', alignItems: 'center', justifyContent: 'space-between',
            padding: 20, cursor: 'pointer',
          }}
          onClick={() => onNavigate('creators')}
        >
          <div style={{ display: 'flex', alignItems: 'center', gap: 14 }}>
            <div style={{
              width: 36, height: 36, borderRadius: 9,
              background: 'var(--accent-bg)', color: 'var(--accent)',
              display: 'flex', alignItems: 'center', justifyContent: 'center',
            }}>
              <TrendingUp size={17} />
            </div>
            <div>
              <div style={{ fontWeight: 600, fontSize: 14, color: 'var(--text)' }}>
                Explore creators
              </div>
              <div style={{ fontSize: 12.5, color: 'var(--text-2)', marginTop: 1 }}>
                Filter by views, followers, niche, contact info
              </div>
            </div>
          </div>
          <ArrowUpRight size={18} style={{ color: 'var(--text-3)' }} />
        </div>
      )}
    </div>
  )
}

/* ============================================================ */

function LiveIndicator({ lastRefresh }) {
  return (
    <div
      style={{
        display: 'flex', alignItems: 'center', gap: 8,
        padding: '6px 10px',
        background: 'var(--success-bg)',
        borderRadius: 999,
        fontSize: 12,
        color: 'var(--success)',
        border: '1px solid color-mix(in srgb, var(--success) 20%, transparent)',
      }}
    >
      <span className="pulse" style={{ width: 6, height: 6, borderRadius: '50%', background: 'var(--success)' }} />
      <span style={{ fontWeight: 500 }}>Live</span>
      {lastRefresh && (
        <span style={{ color: 'var(--text-3)' }}>
          · updated {lastRefresh.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })}
        </span>
      )}
    </div>
  )
}

function StatCard({ icon, label, value, prev, sub, noMono }) {
  const delta = (typeof value === 'number' && typeof prev === 'number') ? value - prev : null
  const displayVal = typeof value === 'number' ? fmt(value) : value

  return (
    <div className="card card-hover" style={{ padding: 16 }}>
      <div style={{
        display: 'flex', alignItems: 'center', justifyContent: 'space-between',
        marginBottom: 12,
      }}>
        <div style={{
          display: 'inline-flex', alignItems: 'center', gap: 7,
          color: 'var(--text-3)',
        }}>
          {icon}
          <span className="section-label">{label}</span>
        </div>
        {delta !== null && delta > 0 && (
          <span
            style={{
              display: 'inline-flex', alignItems: 'center', gap: 2,
              fontSize: 11, fontWeight: 600,
              color: 'var(--success)',
              padding: '1px 6px',
              background: 'var(--success-bg)',
              borderRadius: 10,
            }}
            className="fade-in"
          >
            +{fmt(delta)}
          </span>
        )}
      </div>
      <div
        className={noMono ? '' : 'mono'}
        style={{
          fontSize: 28, fontWeight: 600, color: 'var(--text)',
          lineHeight: 1, letterSpacing: '-0.02em',
        }}
      >
        {displayVal}
      </div>
      <div style={{ fontSize: 12, color: 'var(--text-3)', marginTop: 6 }}>
        {sub}
      </div>
    </div>
  )
}

function ChartCard({ title, subtitle, children }) {
  return (
    <div className="card" style={{ padding: 20 }}>
      <div style={{ marginBottom: 16 }}>
        <div style={{ fontWeight: 600, fontSize: 13.5, color: 'var(--text)' }}>{title}</div>
        <div style={{ fontSize: 12, color: 'var(--text-3)', marginTop: 2 }}>{subtitle}</div>
      </div>
      {children}
    </div>
  )
}

function BarList({ data, labelKey, valueKey, colorFn, color, labelWidth }) {
  const max = Math.max(...data.map(d => d[valueKey]), 1)
  if (!data.length) {
    return <div style={{ fontSize: 13, color: 'var(--text-3)', padding: '12px 0' }}>No data yet.</div>
  }
  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 7 }}>
      {data.map(d => {
        const label = d[labelKey]
        const value = d[valueKey]
        const pct = (value / max) * 100
        const barColor = colorFn ? colorFn(label) : color
        return (
          <div key={label} style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
            <span
              style={{
                width: labelWidth,
                fontSize: 12,
                color: 'var(--text-2)',
                textAlign: 'right',
                flexShrink: 0,
                overflow: 'hidden',
                textOverflow: 'ellipsis',
                whiteSpace: 'nowrap',
              }}
            >
              {label}
            </span>
            <div
              style={{
                flex: 1,
                height: 8,
                background: 'var(--bg-hover)',
                borderRadius: 4,
                overflow: 'hidden',
                position: 'relative',
              }}
            >
              <div
                style={{
                  height: '100%',
                  width: `${pct}%`,
                  background: barColor,
                  borderRadius: 4,
                  transition: 'width 0.6s cubic-bezier(0.16, 1, 0.3, 1)',
                }}
              />
            </div>
            <span
              className="mono"
              style={{
                fontSize: 12,
                color: 'var(--text-2)',
                width: 54,
                textAlign: 'right',
                flexShrink: 0,
              }}
            >
              {fmt(value)}
            </span>
          </div>
        )
      })}
    </div>
  )
}

function LoadingState() {
  return (
    <div style={{
      display: 'flex', alignItems: 'center', justifyContent: 'center',
      minHeight: 320, color: 'var(--text-3)',
    }}>
      <div style={{ display: 'flex', alignItems: 'center', gap: 8, fontSize: 13 }}>
        <span className="pulse" style={{
          width: 6, height: 6, borderRadius: '50%', background: 'var(--text-3)',
        }} />
        Loading dashboard…
      </div>
    </div>
  )
}

function ErrorState({ message }) {
  return (
    <div className="card" style={{ padding: 28, textAlign: 'center' }}>
      <div style={{
        width: 44, height: 44, borderRadius: 11,
        background: 'var(--danger-bg)', color: 'var(--danger)',
        display: 'flex', alignItems: 'center', justifyContent: 'center',
        margin: '0 auto 14px',
        fontSize: 20, fontWeight: 600,
      }}>
        !
      </div>
      <div style={{ fontWeight: 600, fontSize: 15, marginBottom: 6 }}>
        Could not load data
      </div>
      <div className="mono" style={{ fontSize: 12, color: 'var(--text-2)', marginBottom: 16 }}>
        {message}
      </div>
      <div style={{ fontSize: 13, color: 'var(--text-2)', maxWidth: 420, margin: '0 auto' }}>
        Make sure <kbd>uvicorn api:app --port 8080</kbd> is running and{' '}
        <kbd>creators.db</kbd> exists.
      </div>
    </div>
  )
}
