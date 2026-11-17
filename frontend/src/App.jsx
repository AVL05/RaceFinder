import { useCallback, useEffect, useRef, useState } from 'react'
import { Search, Upload, FolderOpen, X, Loader2, Pause, Play, ArrowLeft, Check, AlertTriangle, RefreshCw } from 'lucide-react'
import { api, uploadInBatches, filesFromDrop, ALLOWED } from './api.js'
import Library from './Library.jsx'
import SettingsPanel from './SettingsPanel.jsx'
import EvalView from './EvalView.jsx'
import { ToastProvider, useToast } from './Toast.jsx'

const readUrl = () => {
  const p = new URLSearchParams(location.search)
  return { q: (p.get('dorsal') || '').replace(/\D/g, '').slice(0, 5), similar: p.get('parecidos') === '1' }
}

export default function App() {
  return <ToastProvider><Shell /></ToastProvider>
}

function Shell() {
  const toast = useToast()
  const [view, setView] = useState('library')
  const [stats, setStats] = useState(null)
  const [offline, setOffline] = useState(false)
  const [version, setVersion] = useState(0) // sube cuando cambia el índice: la galería se recarga
  const [{ q, similar }, setSearch] = useState(readUrl)
  const [draft, setDraft] = useState(q)
  const [upload, setUpload] = useState(null)
  const [drag, setDrag] = useState(0)
  const fileRef = useRef(null)
  const dirRef = useRef(null)
  const searchRef = useRef(null)
  const lastKey = useRef('')
  const lastBump = useRef(0)
  const lastPhotos = useRef(-1)
  const rate = useRef([])

  // ---------- estado del servidor ----------
  const refresh = useCallback(async () => {
    try {
      const s = await api.stats()
      setStats(s); setOffline(false)
      // durante un análisis largo (miles de fotos) se recarga la galería como mucho cada 10 s;
      // los cambios de verdad (fotos añadidas o quitadas, fin del análisis) se reflejan al momento
      const key = `${s.photos}|${s.ocr.done || 0}|${s.ocr.error || 0}|${s.with_bib}|${s.faces?.status?.done || 0}`
      const busyNow = (s.ocr.pending || 0) + (s.ocr.processing || 0) + (s.faces?.enabled ? (s.faces.status?.pending || 0) + (s.faces.status?.processing || 0) : 0) > 0
      const urgent = s.photos !== lastPhotos.current || !busyNow
      if (key !== lastKey.current && (urgent || Date.now() - lastBump.current > 10_000)) {
        lastKey.current = key; lastPhotos.current = s.photos; lastBump.current = Date.now(); setVersion((v) => v + 1)
      }
      const now = Date.now()
      rate.current = [...rate.current.filter((r) => now - r.t < 60_000), { t: now, done: s.ocr.done || 0 }]
    } catch { setOffline(true) }
  }, [])
  useEffect(() => { refresh() }, [refresh])
  const ocrPending = (stats?.ocr?.pending || 0) + (stats?.ocr?.processing || 0)
  const facePending = stats?.faces?.enabled ? (stats.faces.status?.pending || 0) + (stats.faces.status?.processing || 0) : 0
  const pending = ocrPending + facePending
  const active = pending > 0 && !stats?.processing_paused
  useEffect(() => {
    const t = setInterval(refresh, offline ? 3000 : active || upload?.running ? 1500 : 8000)
    return () => clearInterval(t)
  }, [active, offline, upload?.running, refresh])

  // ---------- búsqueda sincronizada con la URL ----------
  useEffect(() => {
    const t = setTimeout(() => setSearch((s) => (s.q === draft ? s : { ...s, q: draft })), 220)
    return () => clearTimeout(t)
  }, [draft])
  useEffect(() => {
    const p = new URLSearchParams()
    if (q) p.set('dorsal', q)
    if (similar) p.set('parecidos', '1')
    const url = p.toString() ? `?${p}` : location.pathname
    if (url !== location.search) history.replaceState(null, '', url)
  }, [q, similar])
  useEffect(() => {
    const onPop = () => { const u = readUrl(); setSearch(u); setDraft(u.q) }
    window.addEventListener('popstate', onPop)
    return () => window.removeEventListener('popstate', onPop)
  }, [])
  const searchFor = useCallback((n) => { setDraft(n); setSearch((s) => ({ ...s, q: n })); setView('library'); window.scrollTo({ top: 0 }) }, [])

  // atajo "/" para buscar
  useEffect(() => {
    const k = (e) => {
      if (e.key === '/' && !['INPUT', 'TEXTAREA', 'SELECT'].includes(document.activeElement?.tagName)) { e.preventDefault(); searchRef.current?.focus() }
    }
    window.addEventListener('keydown', k)
    return () => window.removeEventListener('keydown', k)
  }, [])

  // ---------- importación ----------
  const doUpload = async (files) => {
    if (!files.length) return
    if (upload?.running) { toast('Espera a que termine la importación en curso', 'warn'); return }
    setUpload({ running: true, done: 0, total: files.filter((f) => ALLOWED.test(f.name)).length, added: 0, duplicate: 0, rejected: 0, skipped: 0, errors: [] })
    const t = await uploadInBatches(files, (p) => setUpload({ ...p, running: true }))
    setUpload({ ...t, running: false })
    if (t.total === 0) toast('Ninguno de esos archivos es JPG, PNG o WebP', 'warn')
    refresh()
  }
  // Importar una carpeta del disco: la lee el servidor (rápido, sin subir nada por el navegador).
  // Si el sistema no puede abrir el selector de carpetas, se usa el del navegador.
  const importFromDisk = async () => {
    if (upload?.running) { toast('Espera a que termine la importación en curso', 'warn'); return }
    let path
    try { ({ path } = await api.pickFolder('Elige la carpeta con las fotos')) } catch { dirRef.current.click(); return }
    if (!path) return
    try { setUpload(fromServer(await api.importFolder(path))) } catch (e) { toast(e.message, 'error') }
  }
  // al abrir la página: ¿hay una importación en curso? (sobrevive a recargar)
  useEffect(() => { api.importStatus().then((s) => { if (s.running) setUpload(fromServer(s)) }).catch(() => {}) }, [])
  // mientras dura, se sigue su progreso
  useEffect(() => {
    if (!(upload?.server && upload.running)) return
    const t = setInterval(async () => {
      try { const s = await api.importStatus(); setUpload(fromServer(s)); if (!s.running) refresh() }
      catch { /* la API se está reiniciando: se vuelve a intentar */ }
    }, 800)
    return () => clearInterval(t)
  }, [upload?.server, upload?.running, refresh])
  const onDrop = async (e) => {
    e.preventDefault(); setDrag(0)
    try { doUpload(await filesFromDrop(e.dataTransfer)) } catch { toast('No se pudieron leer los archivos soltados', 'error') }
  }
  const hasFiles = (e) => [...(e.dataTransfer?.types || [])].includes('Files')

  const pauseResume = async () => {
    try { setStats(stats.processing_paused ? await api.process() : await api.cancel()) } catch (e) { toast(e.message, 'error') }
  }

  // tiempo estimado a partir del ritmo real del último minuto
  const eta = (() => {
    const r = rate.current
    if (!active || r.length < 2) return null
    const d = r[r.length - 1].done - r[0].done, dt = (r[r.length - 1].t - r[0].t) / 1000
    if (d <= 0 || dt < 5) return null
    const s = (ocrPending / d) * dt
    return s < 90 ? `~${Math.max(1, Math.round(s))} s` : s < 5400 ? `~${Math.round(s / 60)} min` : `~${(s / 3600).toFixed(1)} h`
  })()

  const total = stats?.photos || 0
  const facesPhase = ocrPending === 0 && facePending > 0
  const done = facesPhase ? (stats?.faces?.status?.done || 0) + (stats?.faces?.status?.error || 0) : stats?.ocr?.done || 0

  return (
    <div className="flex min-h-full flex-col"
      onDragEnter={(e) => { if (hasFiles(e)) { e.preventDefault(); setDrag((d) => d + 1) } }}
      onDragOver={(e) => { if (hasFiles(e)) e.preventDefault() }}
      onDragLeave={(e) => { if (hasFiles(e)) setDrag((d) => Math.max(0, d - 1)) }}
      onDrop={onDrop}>
      <header className="sticky top-0 z-30 border-b border-white/5 bg-ink-950/85 backdrop-blur-xl">
        <div className="mx-auto flex max-w-[1680px] flex-wrap items-center gap-x-3 gap-y-2.5 px-4 py-3 sm:flex-nowrap sm:gap-5 sm:px-6">
          <button onClick={() => { setView('library'); searchFor('') }} className="shrink-0 text-lg font-semibold tracking-tight" aria-label="RaceFinder, inicio">
            Race<span className="text-accent">Finder</span>
          </button>

          {view === 'library' ? (
            <form role="search" onSubmit={(e) => { e.preventDefault(); setSearch((s) => ({ ...s, q: draft })) }} className="relative order-last w-full min-w-0 sm:order-none sm:w-auto sm:max-w-xl sm:flex-1">
              <Search className="pointer-events-none absolute left-3.5 top-1/2 -translate-y-1/2 text-ink-500" size={17} aria-hidden />
              <input ref={searchRef} aria-label="Buscar por número de dorsal" inputMode="numeric" autoComplete="off" value={draft}
                onChange={(e) => setDraft(e.target.value.replace(/\D/g, '').slice(0, 5))}
                onKeyDown={(e) => { if (e.key === 'Escape') setDraft('') }}
                placeholder="Busca tu dorsal…"
                className="h-11 w-full rounded-xl border border-white/10 bg-ink-900 pl-10 pr-24 text-[15px] placeholder:text-ink-500 focus:border-accent/60 focus:outline-none" />
              <div className="absolute right-2 top-1/2 flex -translate-y-1/2 items-center gap-1">
                {draft && <button type="button" onClick={() => { setDraft(''); searchRef.current?.focus() }} className="rounded-md p-1.5 text-ink-500 hover:text-white" aria-label="Borrar búsqueda"><X size={15} /></button>}
                <kbd className="hidden rounded border border-white/10 px-1.5 py-0.5 text-[11px] text-ink-500 sm:block">/</kbd>
              </div>
            </form>
          ) : (
            <button onClick={() => setView('library')} className="order-last flex items-center gap-2 rounded-lg px-2 py-1.5 text-sm text-ink-300 hover:text-white sm:order-none"><ArrowLeft size={16} aria-hidden /> Volver a las fotos</button>
          )}

          <div className="ml-auto flex shrink-0 items-center gap-2">
            {pending > 0 && (
              <div className="hidden items-center gap-2 rounded-full border border-white/10 bg-ink-900 py-1 pl-3 pr-1 text-xs md:flex" role="status" aria-live="polite">
                {stats.processing_paused ? <span className="text-ink-300">En pausa · {done}/{total}</span>
                  : <><Loader2 size={13} className="animate-spin text-accent" aria-hidden /><span>{facesPhase ? 'Analizando caras' : 'Leyendo dorsales'} {done}/{total}{eta && !facesPhase ? ` · ${eta}` : ''}</span></>}
                <button onClick={pauseResume} className="rounded-full p-1.5 hover:bg-white/10" aria-label={stats.processing_paused ? 'Reanudar análisis' : 'Pausar análisis'}>
                  {stats.processing_paused ? <Play size={13} /> : <Pause size={13} />}
                </button>
              </div>
            )}
            <button onClick={() => fileRef.current.click()} className="flex h-10 items-center gap-2 rounded-xl bg-accent px-3.5 text-sm font-medium text-ink-950 hover:brightness-110" title="Añadir fotos">
              <Upload size={16} aria-hidden /><span className="hidden sm:inline">Añadir fotos</span>
            </button>
            <button onClick={importFromDisk} className="hidden h-10 items-center gap-2 rounded-xl border border-white/10 px-3.5 text-sm hover:bg-white/5 sm:flex" title="Importar una carpeta del disco (rápido: no se sube nada, se enlaza)">
              <FolderOpen size={16} aria-hidden /> Carpeta
            </button>
            <SettingsPanel onWiped={() => searchFor('')} onChanged={refresh} onOpenEval={() => setView('eval')} onAddFolder={importFromDisk} />
            <input ref={fileRef} type="file" multiple accept=".jpg,.jpeg,.png,.webp,image/jpeg,image/png,image/webp" hidden onChange={(e) => { doUpload([...e.target.files]); e.target.value = '' }} />
            <input ref={dirRef} type="file" webkitdirectory="" directory="" multiple hidden onChange={(e) => { doUpload([...e.target.files]); e.target.value = '' }} />
          </div>
        </div>
        {pending > 0 && (
          <div className="h-0.5 bg-white/5" aria-hidden><div className="h-full bg-accent transition-all duration-700" style={{ width: `${total ? (done / total) * 100 : 0}%` }} /></div>
        )}
      </header>

      {offline && (
        <div role="alert" className="mx-auto mt-4 flex w-[calc(100%-2rem)] max-w-[1680px] items-center justify-between gap-3 rounded-xl border border-red-500/30 bg-red-500/10 px-4 py-3 text-sm">
          <span className="flex items-center gap-2"><AlertTriangle size={16} aria-hidden /> No se puede contactar con RaceFinder. Comprueba que la terminal con <code>pnpm run dev</code> sigue abierta.</span>
          <button onClick={refresh} className="flex shrink-0 items-center gap-1 underline"><RefreshCw size={14} aria-hidden /> Reintentar</button>
        </div>
      )}

      <main className="flex flex-1 flex-col">
        {view === 'library'
          ? <Library q={q} similar={similar} setSimilar={(v) => setSearch((s) => ({ ...s, similar: v }))} stats={stats} version={version}
              onSearch={searchFor} onRefresh={refresh} onPickFiles={() => fileRef.current.click()} onPickFolder={importFromDisk} />
          : <EvalView />}
      </main>

      {upload && <UploadPanel u={upload} onClose={() => setUpload(null)} />}

      {drag > 0 && (
        <div className="pointer-events-none fixed inset-0 z-50 grid place-items-center bg-ink-950/80 p-6 backdrop-blur-sm rf-fade">
          <div className="grid w-full max-w-xl place-items-center gap-3 rounded-3xl border-2 border-dashed border-accent/70 px-8 py-16 text-center">
            <Upload size={36} className="text-accent" aria-hidden />
            <p className="text-xl font-medium">Suelta para añadir las fotos</p>
            <p className="text-sm text-ink-300">También puedes soltar carpetas enteras. Las fotos no salen de tu equipo.</p>
          </div>
        </div>
      )}
    </div>
  )
}

const fromServer = (s) => ({ server: true, running: s.running, phase: s.phase, total: s.total, done: s.done, added: s.added, duplicate: s.duplicate,
  rejected: s.rejected, skipped: 0, linked: s.linked, cancelled: s.cancelled, errors: [...(s.fatal ? [s.fatal] : []), ...s.errors] })

function UploadPanel({ u, onClose }) {
  const [open, setOpen] = useState(false)
  const pct = u.total ? Math.round((u.done / u.total) * 100) : 100
  useEffect(() => {
    if (u.running || u.errors.length || u.rejected) return
    const t = setTimeout(onClose, 6000)
    return () => clearTimeout(t)
  }, [u.running, u.errors.length, u.rejected, onClose])
  return (
    <div className="fixed bottom-4 right-4 z-40 w-[min(calc(100vw-2rem),380px)] rounded-2xl border border-white/10 bg-ink-900/95 p-4 text-sm shadow-2xl backdrop-blur rf-fade" role="status" aria-live="polite">
      <div className="flex items-start justify-between gap-3">
        <div className="flex items-center gap-2 font-medium">
          {u.running ? <Loader2 size={16} className="animate-spin text-accent" aria-hidden /> : <Check size={16} className="text-green-400" aria-hidden />}
          {u.running ? (u.phase === 'scanning' ? 'Buscando fotos en la carpeta…' : u.phase === 'checking' ? `Comprobando qué fotos ya tienes… ${u.checked} de ${u.total}` : u.retrying ? 'Esperando a que RaceFinder responda…' : `Importando ${u.done} de ${u.total}`) : u.cancelled ? 'Importación cancelada' : 'Importación terminada'}
        </div>
        {u.server && u.running && <button onClick={() => api.importCancel().catch(() => {})} className="text-xs underline text-ink-300 hover:text-white">Cancelar</button>}
        {!u.running && <button onClick={onClose} aria-label="Cerrar" className="text-ink-500 hover:text-white"><X size={16} /></button>}
      </div>
      {u.running && <div className="mt-3 h-1 overflow-hidden rounded bg-white/10"><div className="h-full bg-accent transition-all" style={{ width: `${pct}%` }} /></div>}
      <p className="mt-2 text-ink-300">
        <strong className="text-white">{u.added}</strong> nuevas · {u.duplicate} ya estaban{u.rejected ? <> · <span className="text-red-300">{u.rejected} con error</span></> : null}
        {u.skipped ? ` · ${u.skipped} ignoradas (no son fotos)` : ''}
      </p>
      {!u.running && u.added > 0 && <p className="mt-1 text-xs text-ink-500">Los dorsales se leen en segundo plano; puedes buscar mientras tanto.{u.linked ? ' Las fotos no se han duplicado en el disco.' : ''}</p>}
      {u.errors.length > 0 && (
        <div className="mt-2">
          <button onClick={() => setOpen(!open)} className="text-xs underline">{open ? 'Ocultar' : 'Ver'} detalles</button>
          {open && <ul className="mt-1 max-h-32 overflow-auto text-xs text-ink-300">{u.errors.slice(0, 50).map((e, i) => <li key={i}>{e}</li>)}</ul>}
        </div>
      )}
    </div>
  )
}
