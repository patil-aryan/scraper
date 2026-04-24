import React, { useEffect, useState } from 'react'
import {
  X, Mail, Instagram, Youtube, Twitter, Globe,
  ExternalLink, BadgeCheck, Heart, MessageCircle, Share2, Play,
  Calendar, Copy, Check,
} from 'lucide-react'
import { api } from '../lib/api.js'
import { fmt, fmtPct, fmtDate, initials } from '../lib/utils.js'

export default function CreatorDetail({ creator, onClose }) {
  const [detail, setDetail] = useState(null)
  const [loading, setLoading] = useState(false)

  useEffect(() => {
    if (!creator) { setDetail(null); return }
    setLoading(true)
    api.creator(creator.sec_uid)
      .then(setDetail)
      .catch(() => setDetail(null))
      .finally(() => setLoading(false))
  }, [creator?.sec_uid])

  // ESC key closes
  useEffect(() => {
    if (!creator) return
    const h = e => { if (e.key === 'Escape') onClose() }
    window.addEventListener('keydown', h)
    return () => window.removeEventListener('keydown', h)
  }, [creator, onClose])

  const open = !!creator

  // Lock body scroll while modal is open
  useEffect(() => {
    if (open) {
      const prev = document.body.style.overflow
      document.body.style.overflow = 'hidden'
      return () => { document.body.style.overflow = prev }
    }
  }, [open])

  return (
    <>
      <div
        className={`modal-backdrop${open ? ' open' : ''}`}
        onClick={onClose}
        aria-hidden={!open}
      />
      <div
        className={`modal-container${open ? ' open' : ''}`}
        onClick={onClose}
        aria-hidden={!open}
      >
        <div
          className="modal-panel"
          role="dialog"
          aria-modal="true"
          onClick={e => e.stopPropagation()}
        >
          {creator && (
            <>
              <Header creator={creator} onClose={onClose} />
              <div className="modal-scroll">
                {loading ? (
                  <div style={{
                    padding: 80, textAlign: 'center', color: 'var(--text-3)', fontSize: 13,
                  }}>
                    <div className="pulse" style={{
                      width: 6, height: 6, borderRadius: '50%',
                      background: 'var(--text-3)', display: 'inline-block',
                      marginRight: 8,
                    }} />
                    Loading details…
                  </div>
                ) : detail ? (
                  <Body creator={detail.creator} videos={detail.videos} enriched={detail.enriched} />
                ) : (
                  <div style={{ padding: 40, color: 'var(--text-3)', fontSize: 13, textAlign: 'center' }}>
                    Could not load details.
                  </div>
                )}
              </div>
            </>
          )}
        </div>
      </div>
    </>
  )
}

/* ============================================================ */

function Header({ creator, onClose }) {
  return (
    <div style={{
      padding: '28px 32px 22px',
      borderBottom: '1px solid var(--rule-ink)',
      background: 'var(--panel-2)',
      position: 'sticky', top: 0, zIndex: 2,
    }}>
      {/* Top dateline row */}
      <div style={{
        display: 'flex', alignItems: 'center', justifyContent: 'space-between',
        marginBottom: 18,
      }}>
        <div className="eyebrow eyebrow-accent">
          ⸺ Creator Profile · Feature ⸺
        </div>
        <div style={{ display: 'flex', gap: 8, flexShrink: 0 }}>
          <a
            href={`https://tiktok.com/@${creator.unique_id}`}
            target="_blank"
            rel="noopener noreferrer"
            className="btn btn-sm"
          >
            <ExternalLink size={12} /> View on TikTok
          </a>
          <button className="btn btn-sm btn-icon btn-ghost" onClick={onClose} title="Close (Esc)">
            <X size={14} />
          </button>
        </div>
      </div>

      {/* Name + meta row */}
      <div style={{ display: 'flex', gap: 18, alignItems: 'center', flex: 1, minWidth: 0 }}>
        <Avatar size={64} name={creator.nickname || creator.unique_id} />
        <div style={{ minWidth: 0, flex: 1 }}>
          <div style={{ display: 'flex', alignItems: 'baseline', gap: 10, flexWrap: 'wrap' }}>
            <span className="serif" style={{
              fontSize: 38,
              lineHeight: 1,
              letterSpacing: '-0.025em',
              color: 'var(--ink)',
            }}>
              @{creator.unique_id}
            </span>
            {creator.verified ? (
              <BadgeCheck size={18} style={{ color: 'var(--accent)', flexShrink: 0 }} />
            ) : null}
          </div>
          <div style={{
            display: 'flex', alignItems: 'center', gap: 10, marginTop: 8,
            fontFamily: "'Geist Mono', monospace",
            fontSize: 11, letterSpacing: '0.08em',
            color: 'var(--ink-3)', textTransform: 'uppercase',
          }}>
            {creator.nickname && <span>{creator.nickname}</span>}
            {creator.nickname && creator.region && <span>·</span>}
            {creator.region && <span>{creator.region}</span>}
          </div>
        </div>
      </div>
    </div>
  )
}

function Body({ creator, videos, enriched }) {
  const plays = videos.map(v => v.play_count || 0)
  const maxPlay = Math.max(...plays, 1)

  const medianViews = enriched?.median_views ?? null
  const meanViews   = enriched?.mean_views   ?? (plays.length ? plays.reduce((a, b) => a + b, 0) / plays.length : null)
  const minViews    = enriched?.min_views    ?? (plays.length ? Math.min(...plays) : null)
  const maxViews    = enriched?.max_views    ?? (plays.length ? Math.max(...plays) : null)
  const er          = enriched?.engagement_rate ?? null
  const postsPerWeek = enriched?.posts_per_week ?? null

  return (
    <div style={{ padding: '28px 32px 32px', display: 'flex', flexDirection: 'column', gap: 30 }}>
      {/* Pull-quote bio (editorial, hanging quotes) */}
      {creator.signature && (
        <blockquote className="pull-quote" style={{ margin: 0 }}>
          &ldquo;{creator.signature}&rdquo;
        </blockquote>
      )}

      {/* Profile summary */}
      <Section label="Profile">
        <StatGrid>
          <Stat label="Followers"    value={fmt(creator.follower_count)} size="lg" />
          <Stat label="Following"    value={fmt(creator.following_count)} />
          <Stat label="Total likes"  value={fmt(creator.heart_count)} />
          <Stat label="Videos"       value={fmt(creator.video_count)} />
        </StatGrid>
      </Section>

      {/* Performance */}
      <Section
        label="Performance"
        badge={enriched ? { text: 'enriched', color: 'var(--success)' } : { text: `${videos.length} sampled`, color: 'var(--text-3)' }}
      >
        <StatGrid>
          <Stat label="Median views" value={medianViews !== null ? fmt(medianViews) : '—'} size="lg" highlight />
          <Stat label="Avg views"    value={meanViews !== null ? fmt(Math.round(meanViews)) : '—'} />
          <Stat label="Min views"    value={minViews !== null ? fmt(minViews) : '—'} />
          <Stat label="Max views"    value={maxViews !== null ? fmt(maxViews) : '—'} />
          <Stat label="Engagement rate" value={er !== null ? fmtPct(er) : '—'} />
          <Stat label="Posts / week"    value={postsPerWeek ? postsPerWeek.toFixed(1) : '—'} />
        </StatGrid>
      </Section>

      {/* Videos */}
      {plays.length > 0 && (
        <Section label="Recent videos" badge={{ text: `${videos.length} scraped`, color: 'var(--text-3)' }}>
          <Sparkline videos={videos} maxPlay={maxPlay} />
          <VideoList videos={videos} handle={creator.unique_id} />
        </Section>
      )}

      {/* Contact */}
      {(creator.email || creator.instagram || creator.youtube || creator.twitter || creator.website) && (
        <Section label="Contact">
          <div style={{ display: 'flex', flexDirection: 'column', gap: 6 }}>
            {creator.email     && <ContactRow icon={<Mail size={13} />}      href={`mailto:${creator.email}`}                      label={creator.email}       copyable />}
            {creator.instagram && <ContactRow icon={<Instagram size={13} />} href={`https://instagram.com/${creator.instagram}`} label={`@${creator.instagram}`} copyable />}
            {creator.youtube   && <ContactRow icon={<Youtube size={13} />}   href={`https://youtube.com/@${creator.youtube}`}     label={creator.youtube} />}
            {creator.twitter   && <ContactRow icon={<Twitter size={13} />}   href={`https://x.com/${creator.twitter}`}           label={`@${creator.twitter}`} />}
            {creator.website   && <ContactRow icon={<Globe size={13} />}     href={creator.website}                               label={creator.website} />}
          </div>
        </Section>
      )}

      {/* Timestamps */}
      <div style={{
        paddingTop: 16,
        borderTop: '1px solid var(--border)',
        display: 'flex', justifyContent: 'space-between',
        fontSize: 11.5, color: 'var(--text-3)',
      }}>
        <span>First seen · {fmtDate(creator.first_seen)}</span>
        <span>Last seen · {fmtDate(creator.last_seen)}</span>
      </div>
    </div>
  )
}

/* ============================================================ */

function Section({ label, badge, children }) {
  return (
    <div>
      <div style={{
        display: 'flex', alignItems: 'center', gap: 8,
        marginBottom: 10,
      }}>
        <span className="section-label">{label}</span>
        {badge && (
          <span style={{
            fontSize: 10.5, fontWeight: 500,
            color: badge.color,
            padding: '1px 7px',
            border: `1px solid color-mix(in srgb, ${badge.color} 30%, transparent)`,
            borderRadius: 999,
            textTransform: 'lowercase',
            letterSpacing: 0,
          }}>
            {badge.text}
          </span>
        )}
      </div>
      {children}
    </div>
  )
}

function StatGrid({ children }) {
  return (
    <div style={{
      display: 'grid',
      gridTemplateColumns: '1fr 1fr',
      gap: 0,
      border: '1px solid var(--rule-ink)',
      overflow: 'hidden',
    }}>
      {children}
    </div>
  )
}

function Stat({ label, value, size, highlight }) {
  const isLg = size === 'lg'
  return (
    <div style={{
      padding: isLg ? '18px 18px 16px' : '14px 16px',
      background: highlight ? 'var(--bg-selected)' : 'var(--panel-2)',
      borderRight: '1px solid var(--rule)',
      borderBottom: '1px solid var(--rule)',
      position: 'relative',
    }}>
      {highlight && (
        <span style={{
          position: 'absolute', top: 0, left: 0, bottom: 0,
          width: 2, background: 'var(--accent)',
        }} />
      )}
      <div className="eyebrow" style={{ marginBottom: isLg ? 8 : 4 }}>
        {label}
      </div>
      <div
        className={isLg ? 'serif' : 'mono'}
        style={{
          fontSize: isLg ? 30 : 15,
          fontWeight: isLg ? 400 : 500,
          color: highlight ? 'var(--accent)' : 'var(--ink)',
          letterSpacing: isLg ? '-0.02em' : '-0.005em',
          lineHeight: 1,
        }}
      >
        {value}
      </div>
    </div>
  )
}

function Sparkline({ videos, maxPlay }) {
  return (
    <div style={{ marginBottom: 14 }}>
      <div style={{
        display: 'flex', alignItems: 'flex-end', gap: 2, height: 54,
        padding: '0 2px',
      }}>
        {videos.slice(0, 50).map((v, i) => {
          const h = Math.max(3, ((v.play_count || 0) / maxPlay) * 50)
          return (
            <div
              key={v.video_id || i}
              title={`${fmt(v.play_count)} views${v.create_time ? ' · ' + fmtDate(v.create_time) : ''}`}
              style={{
                flex: 1, height: h, minWidth: 3,
                background: 'var(--border-strong)',
                borderRadius: '2px 2px 0 0',
                transition: 'background-color 0.12s ease, transform 0.12s ease',
                cursor: 'default',
              }}
              onMouseEnter={e => {
                e.currentTarget.style.background = 'var(--accent)'
                e.currentTarget.style.transform = 'scaleY(1.05)'
              }}
              onMouseLeave={e => {
                e.currentTarget.style.background = 'var(--border-strong)'
                e.currentTarget.style.transform = 'scaleY(1)'
              }}
            />
          )
        })}
      </div>
      <div style={{
        display: 'flex', justifyContent: 'space-between',
        marginTop: 4,
        fontSize: 10, color: 'var(--text-3)',
        letterSpacing: '0.05em', textTransform: 'uppercase',
      }}>
        <span>Newest</span>
        <span>Oldest</span>
      </div>
    </div>
  )
}

function VideoList({ videos, handle }) {
  return (
    <div style={{
      display: 'flex', flexDirection: 'column',
      border: '1px solid var(--border)',
      borderRadius: 8,
      overflow: 'hidden',
    }}>
      {videos.map((v, i) => (
        <VideoRow key={v.video_id || i} video={v} handle={handle} rank={i + 1} last={i === videos.length - 1} />
      ))}
    </div>
  )
}

function VideoRow({ video, handle, rank, last }) {
  const url = `https://www.tiktok.com/@${handle}/video/${video.video_id}`
  return (
    <a
      href={url}
      target="_blank"
      rel="noopener noreferrer"
      style={{
        display: 'grid',
        gridTemplateColumns: '22px 1fr auto',
        alignItems: 'center',
        gap: 12,
        padding: '9px 12px',
        textDecoration: 'none',
        color: 'var(--text)',
        borderBottom: last ? 'none' : '1px solid var(--border)',
        transition: 'background-color 0.08s ease',
      }}
      onMouseEnter={e => { e.currentTarget.style.background = 'var(--bg-hover)' }}
      onMouseLeave={e => { e.currentTarget.style.background = 'transparent' }}
    >
      <span className="mono" style={{ fontSize: 10.5, color: 'var(--text-3)', textAlign: 'right', fontWeight: 500 }}>
        {rank}
      </span>

      <div style={{ display: 'flex', alignItems: 'center', gap: 14, minWidth: 0, overflow: 'hidden' }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: 4, minWidth: 70 }}>
          <Play size={10} style={{ color: 'var(--text-3)' }} />
          <span className="mono" style={{ fontSize: 13, fontWeight: 600 }}>
            {fmt(video.play_count)}
          </span>
        </div>

        <div style={{ display: 'flex', gap: 10, fontSize: 11.5, color: 'var(--text-3)' }}>
          <StatIcon icon={<Heart size={10} />}         value={fmt(video.digg_count)} />
          <StatIcon icon={<MessageCircle size={10} />} value={fmt(video.comment_count)} />
          <StatIcon icon={<Share2 size={10} />}        value={fmt(video.share_count)} />
        </div>

        {video.create_time && (
          <span
            className="mono"
            style={{
              marginLeft: 'auto',
              fontSize: 10.5,
              color: 'var(--text-3)',
              whiteSpace: 'nowrap',
              display: 'flex', alignItems: 'center', gap: 3,
            }}
          >
            <Calendar size={9} />
            {fmtDate(video.create_time)}
          </span>
        )}
      </div>

      <ExternalLink size={11} style={{ color: 'var(--text-3)', flexShrink: 0 }} />
    </a>
  )
}

function StatIcon({ icon, value }) {
  return (
    <span style={{ display: 'inline-flex', alignItems: 'center', gap: 3 }}>
      {icon}
      <span className="mono">{value}</span>
    </span>
  )
}

function ContactRow({ icon, href, label, copyable }) {
  const [copied, setCopied] = useState(false)

  function handleCopy(e) {
    e.preventDefault()
    e.stopPropagation()
    navigator.clipboard.writeText(label)
    setCopied(true)
    setTimeout(() => setCopied(false), 1200)
  }

  return (
    <a
      href={href}
      target="_blank"
      rel="noopener noreferrer"
      style={{
        display: 'flex', alignItems: 'center', gap: 10,
        padding: '10px 12px', borderRadius: 7,
        background: 'var(--bg-subtle)',
        border: '1px solid var(--border)',
        color: 'var(--text)',
        textDecoration: 'none', fontSize: 13,
        transition: 'background-color 0.1s ease, border-color 0.1s ease',
        overflow: 'hidden',
      }}
      onMouseEnter={e => {
        e.currentTarget.style.background = 'var(--bg-hover)'
        e.currentTarget.style.borderColor = 'var(--border-strong)'
      }}
      onMouseLeave={e => {
        e.currentTarget.style.background = 'var(--bg-subtle)'
        e.currentTarget.style.borderColor = 'var(--border)'
      }}
    >
      <span style={{ color: 'var(--text-3)', flexShrink: 0 }}>{icon}</span>
      <span style={{
        flex: 1, minWidth: 0,
        overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap',
      }}>
        {label}
      </span>
      {copyable && (
        <button
          onClick={handleCopy}
          title="Copy"
          style={{
            width: 24, height: 24, borderRadius: 5,
            border: 'none', background: 'transparent',
            color: copied ? 'var(--success)' : 'var(--text-3)',
            display: 'flex', alignItems: 'center', justifyContent: 'center',
            cursor: 'pointer',
            flexShrink: 0,
          }}
          onMouseEnter={e => { e.currentTarget.style.background = 'var(--bg-active)' }}
          onMouseLeave={e => { e.currentTarget.style.background = 'transparent' }}
        >
          {copied ? <Check size={12} /> : <Copy size={12} />}
        </button>
      )}
      <ExternalLink size={11} style={{ color: 'var(--text-3)', flexShrink: 0 }} />
    </a>
  )
}

function Avatar({ size = 36, name }) {
  return (
    <div style={{
      width: size, height: size, borderRadius: '50%',
      background: 'var(--bg-active)',
      color: 'var(--text-2)',
      display: 'flex', alignItems: 'center', justifyContent: 'center',
      fontSize: size * 0.36, fontWeight: 600,
      flexShrink: 0,
      letterSpacing: '-0.02em',
    }}>
      {initials(name)}
    </div>
  )
}
