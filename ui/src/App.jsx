import React, { useState, useEffect } from 'react'
import { Moon, Sun, LayoutDashboard, Users } from 'lucide-react'
import Dashboard from './components/Dashboard.jsx'
import Creators from './components/Creators.jsx'

export default function App() {
  const [dark, setDark] = useState(() => {
    const stored = localStorage.getItem('theme')
    if (stored) return stored === 'dark'
    return window.matchMedia('(prefers-color-scheme: dark)').matches
  })
  const [page, setPage] = useState(() => localStorage.getItem('page') || 'dashboard')

  useEffect(() => {
    document.documentElement.classList.toggle('dark', dark)
    localStorage.setItem('theme', dark ? 'dark' : 'light')
  }, [dark])

  useEffect(() => { localStorage.setItem('page', page) }, [page])

  return (
    <div style={{ minHeight: '100vh', display: 'flex', flexDirection: 'column', position: 'relative' }}>
      <div className="vignette" />
      <Masthead dark={dark} setDark={setDark} page={page} setPage={setPage} />
      <main
        style={{
          flex: 1,
          maxWidth: 1320,
          width: '100%',
          margin: '0 auto',
          padding: '40px 32px 64px',
          position: 'relative',
          zIndex: 2,
        }}
      >
        <div className="fade-in" key={page}>
          {page === 'dashboard' && <Dashboard onNavigate={setPage} />}
          {page === 'creators' && <Creators />}
        </div>
      </main>
      <Footer />
    </div>
  )
}

function Masthead({ dark, setDark, page, setPage }) {
  const today = new Date().toLocaleDateString('en-US', {
    weekday: 'short', year: 'numeric', month: 'short', day: 'numeric'
  }).toUpperCase()

  return (
    <header
      style={{
        borderBottom: '1px solid var(--rule-ink)',
        background: 'var(--paper)',
        position: 'sticky',
        top: 0,
        zIndex: 40,
        backdropFilter: 'saturate(140%) blur(10px)',
        backgroundColor: 'color-mix(in srgb, var(--paper) 88%, transparent)',
      }}
    >
      {/* Top dateline strip */}
      <div style={{
        borderBottom: '1px solid var(--rule)',
        fontFamily: "'Geist Mono', monospace",
      }}>
        <div style={{
          maxWidth: 1320, margin: '0 auto',
          padding: '6px 32px',
          display: 'flex', justifyContent: 'space-between',
          fontSize: 10.5, letterSpacing: '0.14em', textTransform: 'uppercase',
          color: 'var(--ink-3)',
        }}>
          <span>VOL. 01 · No. {Math.floor(Date.now() / 86400000) % 1000}</span>
          <span style={{ display: 'inline-flex', alignItems: 'center', gap: 10 }}>
            <span className="dot blink" style={{ color: 'var(--signal)' }} />
            LIVE INDEX
          </span>
          <span>{today}</span>
        </div>
      </div>

      {/* Main masthead */}
      <div
        style={{
          maxWidth: 1320,
          margin: '0 auto',
          padding: '14px 32px',
          display: 'grid',
          gridTemplateColumns: 'auto 1fr auto',
          alignItems: 'center',
          gap: 28,
        }}
      >
        {/* Nameplate */}
        <div style={{ display: 'flex', alignItems: 'baseline', gap: 10, position: 'relative' }}>
          <span className="nameplate" style={{ fontSize: 34, color: 'var(--ink)' }}>
            The&nbsp;Creator
          </span>
          <span style={{
            fontFamily: "'Instrument Serif', serif",
            fontSize: 20,
            color: 'var(--accent)',
            margin: '0 2px',
            transform: 'translateY(-4px)',
            display: 'inline-block',
          }}>
            ❖
          </span>
          <span className="nameplate" style={{
            fontSize: 34, fontStyle: 'normal', color: 'var(--ink)',
            textDecoration: 'underline',
            textDecorationColor: 'var(--accent)',
            textDecorationThickness: '1.5px',
            textUnderlineOffset: '4px',
          }}>
            Index
          </span>
          <span className="dateline" style={{
            position: 'absolute', bottom: -3, right: -98,
            fontSize: 9, color: 'var(--ink-3)',
          }}>
            EST. MMXXVI
          </span>
        </div>

        {/* Nav tabs */}
        <nav style={{
          display: 'flex', alignItems: 'center', gap: 0,
          justifyContent: 'center',
          borderLeft: '1px solid var(--rule)',
          borderRight: '1px solid var(--rule)',
          padding: '0 16px',
          marginLeft: 'auto',
        }}>
          <NavTab active={page === 'dashboard'} onClick={() => setPage('dashboard')}
                  icon={<LayoutDashboard size={13} />}>
            Overview
          </NavTab>
          <NavTab active={page === 'creators'} onClick={() => setPage('creators')}
                  icon={<Users size={13} />}>
            Roster
          </NavTab>
        </nav>

        {/* Right actions */}
        <div style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
          <button
            className="btn btn-icon btn-ghost"
            onClick={() => setDark(d => !d)}
            title={dark ? 'Switch to light' : 'Switch to dark'}
            aria-label="Toggle theme"
            style={{ border: '1px solid var(--rule)' }}
          >
            {dark ? <Sun size={14} /> : <Moon size={14} />}
          </button>
        </div>
      </div>
    </header>
  )
}

function NavTab({ active, onClick, icon, children }) {
  return (
    <button
      onClick={onClick}
      style={{
        display: 'inline-flex',
        alignItems: 'center',
        gap: 7,
        padding: '8px 16px',
        height: 34,
        borderRadius: 0,
        border: 'none',
        borderBottom: active ? '2px solid var(--accent)' : '2px solid transparent',
        background: 'transparent',
        color: active ? 'var(--ink)' : 'var(--ink-2)',
        fontSize: 12.5,
        fontWeight: active ? 600 : 500,
        letterSpacing: '0.02em',
        cursor: 'pointer',
        transition: 'color 0.12s ease, border-color 0.12s ease',
        textTransform: 'uppercase',
      }}
      onMouseEnter={e => { if (!active) e.currentTarget.style.color = 'var(--ink)' }}
      onMouseLeave={e => { if (!active) e.currentTarget.style.color = 'var(--ink-2)' }}
    >
      {icon}
      {children}
    </button>
  )
}

function Footer() {
  return (
    <footer style={{
      borderTop: '1px solid var(--rule)',
      marginTop: 40,
      padding: '18px 32px',
      fontFamily: "'Geist Mono', monospace",
      fontSize: 10.5,
      letterSpacing: '0.12em',
      textTransform: 'uppercase',
      color: 'var(--ink-3)',
      display: 'flex', justifyContent: 'space-between',
      maxWidth: 1320, margin: '40px auto 0', width: '100%',
    }}>
      <span>— end of section —</span>
      <span>Creator Index · Internal research</span>
    </footer>
  )
}
