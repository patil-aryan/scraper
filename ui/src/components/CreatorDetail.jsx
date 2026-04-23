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

  return (
    <>
      <div className={`slideover-backdrop${open ? ' open' : ''}`} onClick={onClose} />

      <aside className={`slideover${open ? ' open' : ''}`} aria-hidden={!open}>
        {creator && (
          <>
            <Header creator={creator} onClose={onClose} />

            {loading ? (
              <div style={{
                padding: 60, textAlign: 'center', color: 'var(--text-3)', fontSize: 13,
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
              <div style={{ padding: 28, color: 'var(--text-3)', fontSize: 13 }}>
                Could not load details.
              </div>
            )}
          </>
        )}
      </aside>
    </>
  )
}

/* ============================================================ */

function Header({ creator, onClose }) {
  return (
    <div style={{
      padding: '18px 22px',
      borderBottom: '1px solid var(--border)',
      display: 'flex', alignItems: 'flex-start', justifyContent: 'space-between',
      gap: 14,
      background: 'var(--bg)',
      position: 'sticky', top: 0, zIndex: 2,
    }}>
      <div style={{ display: 'flex', gap: 12, alignItems: 'flex-start', flex: 1, minWidth: 0 }}>
        <Avatar size={44} name={creator.nickname || creator.unique_id} />
        <div style={{ minWidth: 0, flex: 1 }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: 5 }}>
            <span style={{ fontWeight: 600, fontSize: 16, color: 'var(--text)', letterSpacing: '-0.01em' }}>
              @{creator.unique_id}
            </span>
            {creator.verified ? (
              <BadgeCheck size={15} style={{ color: 'var(--accent)', flexShrink: 0 }} />
            ) : null}
          </div>
          {creator.nickname && (
            <div style={{ fontSize: 13, color: 'var(--text-2)', marginTop: 1 }}>
              {creator.nickname}
            </div>
          )}
          {creator.region && (
            <div style={{ fontSize: 12, color: 'var(--text-3)', marginTop: 3 }}>
              {creator.region}
            </div>
          )}
        </div>
      </div>
      <div style={{ display: 'flex', gap: 6, flexShrink: 0 }}>
        <a
          href={`https://tiktok.com/@${creator.unique_id}`}
          target="_blank"
          rel="noopener noreferrer"
          className="btn btn-sm"
        >
          <ExternalLink size={12} /> Open
        </a>
        <button className="btn btn-sm btn-icon" onClick={onClose} title="Close (Esc)">
          <X size={13} />
        </button>
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
    <div style={{ padding: '22px', display: 'flex', flexDirection: 'column', gap: 24 }}>
      {/* Bio */}
      {creator.signature && (
        <div
          style={{
            fontSize: 13,
            color: 'var(--text)',
            lineHeight: 1.65,
            padding: '14px 16px',
            background: 'var(--bg-subtle)',
            borderRadius: 8,
            border: '1px solid var(--border)',
            whiteSpace: 'pre-wrap',
            wordBreak: 'break-word',
          }}
        >
          {creator.signature}
        </div>
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
      gap: 1,
      background: 'var(--border)',
      borderRadius: 8,
      overflow: 'hidden',
      border: '1px solid var(--border)',
    }}>
      {children}
    </div>
  )
}

function Stat({ label, value, size, highlight }) {
  const fontSize = size === 'lg' ? 20 : 15
  return (
    <div style={{
      padding: '12px 14px',
      background: highlight ? 'var(--bg-subtle)' : 'var(--bg-card)',
    }}>
      <div style={{ fontSize: 11, color: 'var(--text-3)', marginBottom: 3, letterSpacing: '0.01em' }}>
        {label}
      </div>
      <div
        className="mono"
        style={{
          fontSize,
          fontWeight: highlight ? 600 : 500,
          color: 'var(--text)',
          letterSpacing: '-0.01em',
          lineHeight: 1.1,
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
