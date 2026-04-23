import React, { useState, useEffect } from 'react'
import { Moon, Sun, LayoutDashboard, Users, Sparkles } from 'lucide-react'
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
    <div className="bg-page" style={{ minHeight: '100vh', display: 'flex', flexDirection: 'column' }}>
      <TopBar dark={dark} setDark={setDark} page={page} setPage={setPage} />
      <main
        style={{
          flex: 1,
          maxWidth: 1280,
          width: '100%',
          margin: '0 auto',
          padding: '28px 28px 40px',
        }}
      >
        <div className="fade-in" key={page}>
          {page === 'dashboard' && <Dashboard onNavigate={setPage} />}
          {page === 'creators' && <Creators />}
        </div>
      </main>
    </div>
  )
}

function TopBar({ dark, setDark, page, setPage }) {
  return (
    <header
      style={{
        background: 'var(--bg)',
        borderBottom: '1px solid var(--border)',
        position: 'sticky',
        top: 0,
        zIndex: 40,
        backdropFilter: 'saturate(180%) blur(8px)',
        backgroundColor: 'color-mix(in srgb, var(--bg) 92%, transparent)',
      }}
    >
      <div
        style={{
          maxWidth: 1280,
          margin: '0 auto',
          padding: '0 28px',
          height: 52,
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'space-between',
          gap: 24,
        }}
      >
        {/* Brand */}
        <div style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
          <div
            style={{
              width: 26,
              height: 26,
              borderRadius: 7,
              background: 'var(--text)',
              color: 'var(--bg)',
              display: 'flex',
              alignItems: 'center',
              justifyContent: 'center',
            }}
          >
            <Sparkles size={14} strokeWidth={2.5} />
          </div>
          <div style={{ display: 'flex', flexDirection: 'column', lineHeight: 1.1 }}>
            <span style={{ fontWeight: 600, fontSize: 13.5, color: 'var(--text)', letterSpacing: '-0.01em' }}>
              Creator DB
            </span>
            <span style={{ fontSize: 10.5, color: 'var(--text-3)', letterSpacing: '0.02em' }}>
              TikTok research
            </span>
          </div>
        </div>

        {/* Nav tabs */}
        <nav style={{ display: 'flex', alignItems: 'center', gap: 2 }}>
          <NavTab active={page === 'dashboard'} onClick={() => setPage('dashboard')} icon={<LayoutDashboard size={14} />}>
            Dashboard
          </NavTab>
          <NavTab active={page === 'creators'} onClick={() => setPage('creators')} icon={<Users size={14} />}>
            Creators
          </NavTab>
        </nav>

        {/* Right */}
        <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
          <button
            className="btn btn-icon btn-ghost"
            onClick={() => setDark(d => !d)}
            title={dark ? 'Switch to light mode' : 'Switch to dark mode'}
            aria-label="Toggle theme"
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
        padding: '6px 12px',
        height: 32,
        borderRadius: 6,
        border: 'none',
        background: active ? 'var(--bg-active)' : 'transparent',
        color: active ? 'var(--text)' : 'var(--text-2)',
        fontSize: 13,
        fontWeight: active ? 600 : 500,
        cursor: 'pointer',
        transition: 'background-color 0.1s ease, color 0.1s ease',
      }}
      onMouseEnter={e => { if (!active) e.currentTarget.style.background = 'var(--bg-hover)' }}
      onMouseLeave={e => { if (!active) e.currentTarget.style.background = 'transparent' }}
    >
      {icon}
      {children}
    </button>
  )
}
