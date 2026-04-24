import React, { useEffect, useState, useRef } from 'react'
import {
  Mail, Instagram, Video, Users, Hash, Sparkles,
  ArrowUpRight, Target, Crown, BadgeCheck, Globe, Radio,
} from 'lucide-react'
import { api } from '../lib/api.js'
import { fmt, nicheColor } from '../lib/utils.js'

export default function Dashboard({ onNavigate }) {
  const [stats, setStats] = useState(null)
  const [summary, setSummary] = useState(null)
  const [prevSummary, setPrevSummary] = useState(null)
  const [niches, setNiches] = useState([])
  const [viewDist, setViewDist] = useState([])
  const [followerDist, setFollowerDist] = useState([])
  const [regions, setRegions] = useState([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState(null)
  const [lastRefresh, setLastRefresh] = useState(null)
  const prevSummaryRef = useRef(null)

  function loadAll(showLoading = false) {
    if (showLoading) setLoading(true)
    Promise.all([
      api.stats(),
      api.summary(),
      api.niches(),
      api.viewDistribution(),
      api.followerDistribution(),
      api.regions(),
    ])
      .then(([s, sum, n, vd, fd, rg]) => {
        if (prevSummaryRef.current) setPrevSummary(prevSummaryRef.current)
        prevSummaryRef.current = sum
        setStats(s)
        setSummary(sum)
        setNiches(n.slice(0, 10))
        setViewDist(vd)
        setFollowerDist(fd)
        setRegions(rg.slice(0, 8))
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
  if (error && !stats) return <ErrorState message={error} />
  if (stats?.error) return <ErrorState message={stats.error} />

  const progressPct = stats.hashtags_total
    ? (stats.hashtags_done / stats.hashtags_total) * 100
    : 0

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 44 }}>
      {/* ── FEATURE HEADER ── */}
      <FeatureHeader lastRefresh={lastRefresh} />

      {/* ── HERO NUMBER ── */}
      <HeroFeature summary={summary} prev={prevSummary} onNavigate={onNavigate} />

      {/* ── STAT STRIP — key KPIs ── */}
      <StatStrip summary={summary} prev={prevSummary} />

      {/* ── DIVIDER ── */}
      <Divider label="Distribution" />

      {/* ── FOLLOWER BAND BREAKDOWN ── */}
      <FollowerFeature bands={followerDist} />

      {/* ── PROGRESS BAR ── */}
      <ProgressBar stats={stats} pct={progressPct} />

      {/* ── DIVIDER ── */}
      <Divider label="Sections" />

      {/* ── CHARTS GRID (niches / regions / views) ── */}
      <div
        className="stagger"
        style={{
          display: 'grid',
          gridTemplateColumns: 'repeat(auto-fit, minmax(320px, 1fr))',
          gap: 0,
          borderTop: '1px solid var(--rule)',
          borderLeft: '1px solid var(--rule)',
        }}
      >
        <FeatureCell title="Niches" subtitle="By source hashtag category">
          <BarList data={niches} labelKey="niche" valueKey="count" colorFn={nicheColor} labelWidth={96} />
        </FeatureCell>

        <FeatureCell title="View Spread" subtitle="Per-video view count (not followers)">
          <BarList data={viewDist} labelKey="range" valueKey="count" color="var(--ink-3)" labelWidth={78} />
        </FeatureCell>

        {regions.length > 0 && (
          <FeatureCell title="Regions" subtitle="From enriched profiles">
            <BarList data={regions} labelKey="region" valueKey="count" color="var(--accent)" labelWidth={56} />
          </FeatureCell>
        )}
      </div>

      {/* ── RAW STATS STRIP ── */}
      <RawStatsRow stats={stats} summary={summary} />

      {/* ── CTA ── */}
      {stats.total_creators > 0 && (
        <CtaRow onNavigate={onNavigate} summary={summary} />
      )}
    </div>
  )
}

/* ================================================================ */

function FeatureHeader({ lastRefresh }) {
  return (
    <div style={{
      display: 'flex', alignItems: 'flex-end', justifyContent: 'space-between',
      gap: 24, flexWrap: 'wrap',
      paddingBottom: 32,
      position: 'relative',
    }}>
      <div style={{ flex: 1, minWidth: 280 }}>
        <div className="ornament-rule" style={{ marginBottom: 20, maxWidth: 360 }}>
          <span className="eyebrow eyebrow-accent" style={{ letterSpacing: '0.18em' }}>
            Section A
          </span>
          <span style={{ fontSize: 14, color: 'var(--accent)' }}>❖</span>
          <span className="eyebrow" style={{ letterSpacing: '0.18em' }}>
            Market Overview
          </span>
        </div>
        <h1 className="title" style={{ fontSize: 'clamp(48px, 7vw, 78px)', lineHeight: 0.94 }}>
          The&nbsp;<em style={{ fontStyle: 'italic', color: 'var(--accent)' }}>long&nbsp;tail</em>
          <br />
          of influence.
        </h1>
        <p className="dek drop-cap" style={{ maxWidth: '55ch', marginTop: 18 }}>
          A running ledger of scraped TikTok creators, ranked by outreach
          readiness. Every row has been touched by the scraper, deduped by
          handle, and stamped with a contact coverage score. Updates every
          thirty seconds.
        </p>
      </div>
      <LiveBadge lastRefresh={lastRefresh} />
    </div>
  )
}

function HeroFeature({ summary, prev, onNavigate }) {
  const inRange = summary.in_range_10k_1m || 0
  const contact = summary.in_range_with_contact || 0
  const coverage = inRange ? ((contact / inRange) * 100).toFixed(0) : 0
  const delta = prev ? contact - (prev.in_range_with_contact ?? contact) : 0

  return (
    <div
      style={{
        display: 'grid',
        gridTemplateColumns: 'minmax(0, 1fr) minmax(220px, 260px)',
        gap: 40,
        padding: '20px 0 8px',
        alignItems: 'flex-start',
        position: 'relative',
      }}
    >
      {/* Hero number + label */}
      <div
        onClick={() => onNavigate('creators')}
        style={{ minWidth: 0, position: 'relative', cursor: 'pointer' }}
      >
        <div className="eyebrow" style={{ marginBottom: 18, color: 'var(--ink-2)' }}>
          ⸺ Ready for outreach · 10k–1M followers · verified contact ⸺
        </div>
        <div style={{
          display: 'flex', alignItems: 'flex-end', gap: 18, flexWrap: 'wrap',
        }}>
          <span
            key={contact}
            className="press"
            style={{
              fontFamily: "'Instrument Serif', serif",
              fontWeight: 400,
              fontSize: 'clamp(112px, 17vw, 204px)',
              lineHeight: 0.82,
              letterSpacing: '-0.045em',
              color: 'var(--ink)',
              fontVariantNumeric: 'tabular-nums',
              display: 'inline-block',
            }}
          >
            {fmt(contact)}
          </span>
          {delta > 0 && (
            <span
              className="fade-in"
              style={{
                fontFamily: "'Geist Mono', monospace",
                fontSize: 12,
                color: 'var(--signal)',
                background: 'var(--signal-bg)',
                padding: '5px 10px',
                border: '1px solid color-mix(in srgb, var(--signal) 28%, transparent)',
                letterSpacing: '0.06em',
                marginBottom: 22,
                textTransform: 'uppercase',
              }}
            >
              ↑ {fmt(delta)} this tick
            </span>
          )}
        </div>
        <p className="dek" style={{ marginTop: 20, maxWidth: '54ch' }}>
          That is <span className="serif" style={{ fontStyle: 'italic', color: 'var(--accent)', fontSize: 22 }}>{coverage}%</span> of
          your {fmt(inRange).toLocaleString?.() || fmt(inRange)} in-range creators carrying reachable contact —
          email, Instagram, YouTube, or site. Click through to the roster.
        </p>
      </div>

      {/* Marginalia — quiet sidebar annotations */}
      <aside style={{
        display: 'flex', flexDirection: 'column', gap: 20,
        paddingTop: 26, paddingLeft: 22,
        borderLeft: '1px solid var(--rule-ink)',
        position: 'relative',
      }}>
        <div>
          <div className="eyebrow" style={{ color: 'var(--accent)', marginBottom: 6 }}>
            ※ Fig. 01
          </div>
          <div className="marginalia" style={{ border: 'none', padding: 0 }}>
            Contact coverage is computed on any creator with at least one of:
            email, Instagram, YouTube handle, or personal website linked in bio.
          </div>
        </div>

        <div>
          <div className="eyebrow" style={{ color: 'var(--ink-3)', marginBottom: 6 }}>
            ※ Target band
          </div>
          <div className="marginalia" style={{ border: 'none', padding: 0 }}>
            10k floor ·  rules out empty / spam accounts.<br />
            1M ceiling · excludes priced-out megastars.
          </div>
        </div>

        <div
          onClick={() => onNavigate('creators')}
          style={{
            display: 'inline-flex', alignItems: 'center', justifyContent: 'space-between',
            gap: 10, padding: '10px 14px',
            border: '1px solid var(--ink)',
            background: 'var(--ink)', color: 'var(--paper)',
            cursor: 'pointer',
            transition: 'background 0.18s ease, border-color 0.18s ease',
          }}
          onMouseEnter={e => { e.currentTarget.style.background = 'var(--accent)'; e.currentTarget.style.borderColor = 'var(--accent)' }}
          onMouseLeave={e => { e.currentTarget.style.background = 'var(--ink)'; e.currentTarget.style.borderColor = 'var(--ink)' }}
        >
          <span className="eyebrow" style={{ color: 'var(--paper)', opacity: 0.85 }}>
            Open roster
          </span>
          <ArrowUpRight size={15} />
        </div>
      </aside>
    </div>
  )
}

function StatStrip({ summary, prev }) {
  const items = [
    {
      icon: Target,
      label: 'In target band',
      value: summary.in_range_10k_1m,
      prev: prev?.in_range_10k_1m,
      sub: '10k – 1M followers',
    },
    {
      icon: Mail,
      label: 'Contactable',
      value: summary.in_range_with_contact,
      prev: prev?.in_range_with_contact,
      sub: 'any reachable channel',
      accent: true,
    },
    {
      icon: Crown,
      label: 'Mid-tier',
      value: summary.mid_tier_100k_1m,
      prev: prev?.mid_tier_100k_1m,
      sub: '100k – 1M premium',
    },
    {
      icon: Mail,
      label: 'Mid-tier reach',
      value: summary.mid_tier_with_contact,
      prev: prev?.mid_tier_with_contact,
      sub: 'premium · contactable',
      accent: true,
    },
  ]

  return (
    <div
      className="stagger"
      style={{
        display: 'grid',
        gridTemplateColumns: 'repeat(auto-fit, minmax(220px, 1fr))',
        gap: 0,
        borderTop: '1px solid var(--rule-ink)',
        borderBottom: '1px solid var(--rule-ink)',
      }}
    >
      {items.map((item, i) => (
        <StatCell key={i} {...item} isLast={i === items.length - 1} />
      ))}
    </div>
  )
}

function StatCell({ icon: Icon, label, value, prev, sub, accent, isLast }) {
  const delta = (typeof value === 'number' && typeof prev === 'number') ? value - prev : null
  return (
    <div
      style={{
        padding: '22px 24px',
        borderRight: isLast ? 'none' : '1px solid var(--rule)',
        position: 'relative',
        background: accent ? 'var(--panel)' : 'transparent',
      }}
    >
      <div style={{
        display: 'flex', alignItems: 'center', justifyContent: 'space-between',
        marginBottom: 14,
      }}>
        <div style={{ display: 'inline-flex', alignItems: 'center', gap: 8, color: accent ? 'var(--accent)' : 'var(--ink-3)' }}>
          <Icon size={13} />
          <span className="eyebrow" style={{ color: accent ? 'var(--accent)' : 'var(--ink-3)' }}>{label}</span>
        </div>
        {delta !== null && delta > 0 && (
          <span
            className="fade-in"
            style={{
              fontFamily: "'Geist Mono', monospace",
              fontSize: 10.5,
              color: 'var(--signal)',
              letterSpacing: '0.04em',
            }}
          >
            ↑ {fmt(delta)}
          </span>
        )}
      </div>
      <div
        className="serif"
        style={{
          fontSize: 44,
          lineHeight: 0.95,
          letterSpacing: '-0.025em',
          color: accent ? 'var(--accent)' : 'var(--ink)',
          fontVariantNumeric: 'tabular-nums',
        }}
      >
        {fmt(value)}
      </div>
      <div style={{ fontSize: 12, color: 'var(--ink-3)', marginTop: 8, fontStyle: 'italic', fontFamily: "'Instrument Serif', serif", letterSpacing: 0.1 }}>
        {sub}
      </div>
    </div>
  )
}

function ProgressBar({ stats, pct }) {
  return (
    <div style={{ padding: '0 0 6px' }}>
      <div style={{
        display: 'flex', alignItems: 'center', justifyContent: 'space-between',
        marginBottom: 10, gap: 12, flexWrap: 'wrap',
      }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: 12 }}>
          <Hash size={13} style={{ color: 'var(--ink-3)' }} />
          <span className="eyebrow">Hashtag sweep</span>
          <span style={{ fontSize: 12, color: 'var(--ink-3)', fontFamily: "'Geist Mono', monospace" }}>
            {stats.hashtags_done} / {stats.hashtags_total}
          </span>
        </div>
        <span className="mono" style={{ fontSize: 12, fontWeight: 500, color: 'var(--ink-2)' }}>
          {pct.toFixed(1)}%
        </span>
      </div>
      <div style={{
        height: 2,
        background: 'var(--rule)',
        overflow: 'hidden',
      }}>
        <div
          style={{
            height: '100%',
            width: `${pct}%`,
            background: 'var(--accent)',
            transition: 'width 0.8s cubic-bezier(0.16, 1, 0.3, 1)',
          }}
        />
      </div>
    </div>
  )
}

function FollowerFeature({ bands }) {
  if (!bands?.length) {
    return <div style={{ fontSize: 13, color: 'var(--ink-3)' }}>No data yet.</div>
  }
  const maxTotal = Math.max(...bands.map(b => b.total), 1)
  const TARGET = new Set(['10k–50k', '50k–100k', '100k–500k', '500k–1M'])

  return (
    <div>
      <SectionHeading
        kicker="Figure 01"
        title="Follower distribution"
        dek="Creator count per follower band. Highlighted rows fall inside the 10k–1M outreach window. Contact coverage trails each band."
      />

      <div style={{
        marginTop: 22,
        border: '1px solid var(--rule-ink)',
        borderRadius: 3,
      }}>
        {/* Header row */}
        <div style={{
          display: 'grid',
          gridTemplateColumns: '140px 1fr 100px 150px',
          alignItems: 'center',
          gap: 16,
          padding: '10px 18px',
          borderBottom: '1px solid var(--rule-ink)',
          background: 'var(--panel)',
        }}>
          <span className="eyebrow">Band</span>
          <span className="eyebrow" style={{ textAlign: 'left' }}>Share</span>
          <span className="eyebrow" style={{ textAlign: 'right' }}>Total</span>
          <span className="eyebrow" style={{ textAlign: 'right' }}>Contact · %</span>
        </div>

        {bands.map((b, i) => {
          const isTarget = TARGET.has(b.band)
          const pct = (b.total / maxTotal) * 100
          const contactPct = b.total ? (b.with_any_contact / b.total) * 100 : 0

          return (
            <div
              key={b.band}
              style={{
                display: 'grid',
                gridTemplateColumns: '140px 1fr 100px 150px',
                alignItems: 'center',
                gap: 16,
                padding: '16px 18px',
                borderBottom: i === bands.length - 1 ? 'none' : '1px solid var(--rule)',
                background: isTarget ? 'var(--bg-selected)' : 'transparent',
                position: 'relative',
              }}
            >
              {isTarget && (
                <span style={{
                  position: 'absolute', left: 0, top: 0, bottom: 0,
                  width: 3, background: 'var(--accent)',
                }} />
              )}
              <div style={{ display: 'flex', alignItems: 'baseline', gap: 8 }}>
                <span className="serif" style={{
                  fontSize: 22,
                  color: isTarget ? 'var(--ink)' : 'var(--ink-2)',
                  letterSpacing: '-0.015em',
                  lineHeight: 1,
                }}>
                  {b.band}
                </span>
              </div>

              <div style={{
                position: 'relative',
                height: 8,
                background: 'var(--bg-hover)',
                borderRadius: 0,
                overflow: 'hidden',
              }}>
                <div style={{
                  position: 'absolute', inset: 0,
                  width: `${pct}%`,
                  background: isTarget ? 'var(--accent)' : 'var(--ink-4)',
                  transition: 'width 0.8s cubic-bezier(0.16, 1, 0.3, 1)',
                }} />
              </div>

              <span className="mono" style={{
                fontSize: 16,
                fontWeight: 600,
                color: 'var(--ink)',
                textAlign: 'right',
                letterSpacing: '-0.005em',
              }}>
                {fmt(b.total)}
              </span>

              <span style={{
                fontSize: 12,
                color: 'var(--ink-3)',
                textAlign: 'right',
                display: 'flex', justifyContent: 'flex-end', alignItems: 'center', gap: 8,
                fontFamily: "'Geist Mono', monospace",
                fontVariantNumeric: 'tabular-nums',
              }}>
                <Mail size={11} />
                <span style={{ color: 'var(--ink-2)' }}>{fmt(b.with_any_contact)}</span>
                <span style={{
                  padding: '1px 6px',
                  background: isTarget ? 'var(--accent-bg)' : 'var(--bg-hover)',
                  color: isTarget ? 'var(--accent)' : 'var(--ink-3)',
                  fontSize: 10.5,
                  letterSpacing: '0.04em',
                }}>
                  {contactPct.toFixed(0)}%
                </span>
              </span>
            </div>
          )
        })}
      </div>
    </div>
  )
}

function RawStatsRow({ stats, summary }) {
  const items = [
    { icon: Users,        label: 'Creators',     value: stats.total_creators },
    { icon: Video,        label: 'Videos',       value: stats.total_videos },
    { icon: Mail,         label: 'Emails',       value: stats.with_email },
    { icon: Instagram,    label: 'Instagrams',   value: stats.with_instagram },
    summary.verified_in_range > 0 && { icon: BadgeCheck, label: 'Verified', value: summary.verified_in_range },
    summary.with_region   > 0 && { icon: Globe,       label: 'Regions',    value: summary.with_region },
    stats.enriched        > 0 && { icon: Sparkles,    label: 'Enriched',   value: stats.enriched },
  ].filter(Boolean)

  return (
    <div style={{
      display: 'flex', flexWrap: 'wrap',
      gap: 0,
      borderTop:    '1px solid var(--rule)',
      borderBottom: '1px solid var(--rule)',
    }}>
      {items.map((it, i) => (
        <div key={i} style={{
          padding: '16px 24px',
          display: 'flex', alignItems: 'center', gap: 12,
          borderRight: i === items.length - 1 ? 'none' : '1px solid var(--rule)',
          flex: 1, minWidth: 180,
        }}>
          <it.icon size={14} style={{ color: 'var(--ink-3)' }} />
          <div>
            <div className="eyebrow" style={{ marginBottom: 3 }}>{it.label}</div>
            <div className="mono" style={{ fontSize: 17, fontWeight: 600, letterSpacing: '-0.01em' }}>
              {fmt(it.value)}
            </div>
          </div>
        </div>
      ))}
    </div>
  )
}

function CtaRow({ onNavigate, summary }) {
  return (
    <div
      onClick={() => onNavigate('creators')}
      style={{
        border: '1px solid var(--rule-ink)',
        padding: '28px 32px',
        cursor: 'pointer',
        display: 'flex', alignItems: 'center', justifyContent: 'space-between',
        gap: 28, flexWrap: 'wrap',
        background: 'var(--panel-2)',
        position: 'relative',
        transition: 'background 0.15s ease, border-color 0.15s ease',
      }}
      onMouseEnter={e => { e.currentTarget.style.background = 'var(--panel)' }}
      onMouseLeave={e => { e.currentTarget.style.background = 'var(--panel-2)' }}
    >
      <div>
        <div className="eyebrow eyebrow-accent" style={{ marginBottom: 12 }}>— Continue to full roster —</div>
        <div className="serif" style={{
          fontSize: 40,
          lineHeight: 1,
          letterSpacing: '-0.02em',
        }}>
          Browse all <em style={{ color: 'var(--accent)' }}>{fmt(summary.total_creators)}</em> creators
        </div>
        <p className="dek" style={{ marginTop: 12 }}>
          Filter by followers, niche, region, contact. Export any slice to CSV.
        </p>
      </div>
      <div style={{
        display: 'inline-flex', alignItems: 'center', gap: 10,
        padding: '10px 16px',
        border: '1px solid var(--ink)',
        background: 'var(--ink)', color: 'var(--paper)',
        borderRadius: 2,
      }}>
        <span className="eyebrow" style={{ color: 'var(--paper)', opacity: 0.75 }}>Open roster</span>
        <ArrowUpRight size={15} />
      </div>
    </div>
  )
}

/* ────────── Layout primitives ────────── */

function Divider({ label, ornament = '❖' }) {
  return (
    <div className="ornament-rule" style={{ margin: '8px 0 0' }}>
      <span className="eyebrow" style={{ color: 'var(--ink-2)', letterSpacing: '0.18em' }}>
        {label}
      </span>
      <span style={{ fontSize: 14, color: 'var(--accent)' }}>{ornament}</span>
    </div>
  )
}

function SectionHeading({ kicker, title, dek }) {
  return (
    <div>
      <div className="eyebrow eyebrow-accent">{kicker}</div>
      <h2 className="serif" style={{
        fontSize: 34,
        lineHeight: 1.05,
        letterSpacing: '-0.02em',
        margin: '6px 0 0',
        color: 'var(--ink)',
      }}>
        {title}
      </h2>
      {dek && <p className="dek" style={{ fontSize: 15 }}>{dek}</p>}
    </div>
  )
}

function FeatureCell({ title, subtitle, children }) {
  return (
    <div style={{
      padding: 22,
      borderRight: '1px solid var(--rule)',
      borderBottom: '1px solid var(--rule)',
    }}>
      <div style={{ marginBottom: 16 }}>
        <div className="eyebrow" style={{ color: 'var(--accent)' }}>Figure</div>
        <div className="serif" style={{ fontSize: 22, letterSpacing: '-0.015em', marginTop: 2, color: 'var(--ink)' }}>
          {title}
        </div>
        <div style={{ fontSize: 12, color: 'var(--ink-3)', marginTop: 3, fontStyle: 'italic', fontFamily: "'Instrument Serif', serif" }}>
          {subtitle}
        </div>
      </div>
      {children}
    </div>
  )
}

function BarList({ data, labelKey, valueKey, colorFn, color, labelWidth }) {
  const max = Math.max(...data.map(d => d[valueKey]), 1)
  if (!data.length) {
    return <div style={{ fontSize: 13, color: 'var(--ink-3)', padding: '12px 0' }}>No data yet.</div>
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
            <span style={{
              width: labelWidth,
              fontSize: 12, color: 'var(--ink-2)',
              textAlign: 'right', flexShrink: 0,
              overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap',
              fontFamily: "'Geist Mono', monospace",
              letterSpacing: '0.02em',
            }}>
              {label}
            </span>
            <div style={{
              flex: 1, height: 6,
              background: 'var(--bg-hover)',
              overflow: 'hidden', position: 'relative',
            }}>
              <div
                style={{
                  height: '100%', width: `${pct}%`,
                  background: typeof barColor === 'string' && barColor.startsWith('bg-') ? undefined : barColor,
                  transition: 'width 0.7s cubic-bezier(0.16, 1, 0.3, 1)',
                }}
                className={typeof barColor === 'string' && barColor.startsWith('bg-') ? barColor : ''}
              />
            </div>
            <span className="mono" style={{
              fontSize: 12, color: 'var(--ink)',
              width: 56, textAlign: 'right', flexShrink: 0, fontWeight: 500,
            }}>
              {fmt(value)}
            </span>
          </div>
        )
      })}
    </div>
  )
}

function LiveBadge({ lastRefresh }) {
  return (
    <div style={{
      display: 'inline-flex', alignItems: 'center', gap: 10,
      padding: '7px 12px',
      border: '1px solid var(--rule-ink)',
      borderRadius: 999,
      background: 'var(--panel-2)',
    }}>
      <Radio size={12} style={{ color: 'var(--signal)' }} className="pulse" />
      <span style={{ fontFamily: "'Geist Mono', monospace", fontSize: 10.5, letterSpacing: '0.14em', color: 'var(--ink-2)', textTransform: 'uppercase' }}>
        Live
      </span>
      {lastRefresh && (
        <>
          <span style={{ color: 'var(--ink-4)' }}>·</span>
          <span style={{ fontFamily: "'Geist Mono', monospace", fontSize: 10.5, color: 'var(--ink-3)' }}>
            {lastRefresh.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })}
          </span>
        </>
      )}
    </div>
  )
}

function LoadingState() {
  return (
    <div style={{
      display: 'flex', alignItems: 'center', justifyContent: 'center',
      minHeight: 320, color: 'var(--ink-3)',
    }}>
      <div style={{ display: 'flex', alignItems: 'center', gap: 10, fontSize: 13 }}>
        <span className="pulse" style={{ width: 6, height: 6, borderRadius: '50%', background: 'var(--ink-3)' }} />
        <span className="eyebrow">Setting the page ·</span>
        <span style={{ fontFamily: "'Instrument Serif', serif", fontStyle: 'italic' }}>loading edition</span>
      </div>
    </div>
  )
}

function ErrorState({ message }) {
  return (
    <div style={{
      border: '1px solid var(--rule-ink)', padding: 40, textAlign: 'center',
      background: 'var(--panel-2)',
    }}>
      <div className="eyebrow eyebrow-accent" style={{ marginBottom: 14 }}>⸺ Stop the presses ⸺</div>
      <div className="serif" style={{ fontSize: 28, lineHeight: 1.1, marginBottom: 10, color: 'var(--ink)' }}>
        Could not load the edition
      </div>
      <div className="mono" style={{ fontSize: 12, color: 'var(--ink-2)', marginBottom: 18 }}>
        {message}
      </div>
      <div style={{ fontSize: 13, color: 'var(--ink-2)', maxWidth: 420, margin: '0 auto', fontStyle: 'italic', fontFamily: "'Instrument Serif', serif" }}>
        Make sure <kbd>uvicorn api:app --port 8000</kbd> is running and <kbd>creators.db</kbd> exists.
      </div>
    </div>
  )
}
