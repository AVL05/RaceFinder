import { useEffect, useMemo, useRef, useState } from 'react'
import { ScanFace, ShieldCheck, Loader2, X, Check } from 'lucide-react'
import { api } from './api.js'
import { useToast } from './Toast.jsx'
import RetryImg from './RetryImg.jsx'

/** Activa la búsqueda por cara tras un consentimiento explícito. */
export function ConsentDialog({ onClose, onEnabled }) {
  const toast = useToast()
  const [ok, setOk] = useState(false)
  const [busy, setBusy] = useState(false)
  const enable = async () => {
    setBusy(true)
    try {
      const s = await api.settings()
      await api.saveSettings({ ...s, faces_enabled: true, face_consent: true })
      toast('Búsqueda por cara activada. Analizando caras en segundo plano…', 'ok')
      onEnabled?.(); onClose()
    } catch (e) { toast(e.message, 'error') } finally { setBusy(false) }
  }
  useEffect(() => {
    const k = (e) => { if (e.key === 'Escape') onClose() }
    window.addEventListener('keydown', k)
    return () => window.removeEventListener('keydown', k)
  }, [onClose])
  return (
    <div className="fixed inset-0 z-[55] grid place-items-center bg-black/70 p-4 backdrop-blur-sm rf-fade" onMouseDown={(e) => { if (e.target === e.currentTarget) onClose() }}>
      <div role="dialog" aria-modal="true" aria-labelledby="consent-title" className="w-full max-w-lg rounded-2xl border border-white/10 bg-ink-900 p-6 shadow-2xl">
        <div className="flex items-start justify-between gap-4">
          <h2 id="consent-title" className="flex items-center gap-2 text-lg font-semibold"><ScanFace size={20} className="text-accent" aria-hidden /> Buscar también por la cara</h2>
          <button onClick={onClose} aria-label="Cerrar" className="text-ink-500 hover:text-white"><X size={18} /></button>
        </div>
        <p className="mt-3 text-sm text-ink-300">Encuentra las fotos en las que sales aunque el dorsal no se lea: RaceFinder toma tu cara de las fotos donde sí se lee tu dorsal y busca caras parecidas en el resto.</p>
        <ul className="mt-4 space-y-2 text-sm">
          {['Todo ocurre en tu equipo. Ninguna foto ni dato sale a internet (solo se descargan una vez los modelos de OpenCV, 38 MB).',
            'Se guarda un vector numérico anónimo por cara, sin nombres ni identidades. Nadie queda "reconocido".',
            'Solo se busca a partir de las caras que tú eliges.',
            'Puedes borrar todos los datos faciales cuando quieras desde Ajustes.'].map((t) => (
            <li key={t} className="flex gap-2"><ShieldCheck size={16} className="mt-0.5 shrink-0 text-green-400" aria-hidden /><span className="text-ink-300">{t}</span></li>
          ))}
        </ul>
        <label className="mt-5 flex cursor-pointer items-start gap-3 rounded-lg border border-white/10 bg-ink-950 p-3 text-sm">
          <input type="checkbox" checked={ok} onChange={(e) => setOk(e.target.checked)} className="mt-0.5 accent-[var(--color-accent)]" />
          <span>Las fotos son de un evento en el que tengo permiso para hacer esto, y solo buscaré mi cara o la de personas que me lo hayan autorizado.</span>
        </label>
        <div className="mt-5 flex justify-end gap-2">
          <button onClick={onClose} className="rounded-lg px-4 py-2 text-sm text-ink-300 hover:text-white">Ahora no</button>
          <button disabled={!ok || busy} onClick={enable} className="flex items-center gap-2 rounded-lg bg-accent px-4 py-2 text-sm font-medium text-ink-950 disabled:opacity-40">
            {busy && <Loader2 size={15} className="animate-spin" aria-hidden />} Activar
          </button>
        </div>
      </div>
    </div>
  )
}

/**
 * Bajo los resultados de un dorsal: propone las caras que aparecen encima de ese dorsal,
 * deja que la persona confirme cuáles son suyas y busca fotos con caras parecidas.
 */
export function FaceSection({ q, stats, onResults, onEnabled }) {
  const [consent, setConsent] = useState(false)
  const [cand, setCand] = useState(null)
  const [chosen, setChosen] = useState(() => new Set())
  const [searching, setSearching] = useState(false)
  const [count, setCount] = useState(null)
  const touched = useRef(false)
  const enabled = stats?.faces?.enabled
  const fs = stats?.faces?.status || {}
  const facePending = (fs.pending || 0) + (fs.processing || 0)
  const doneKey = enabled ? `${fs.done || 0}` : 'off'

  // candidatas: se recargan mientras avanza el análisis de caras
  useEffect(() => { touched.current = false; setCand(null); setChosen(new Set()); setCount(null); onResults(null) }, [q]) // eslint-disable-line react-hooks/exhaustive-deps
  useEffect(() => {
    if (!enabled || !q) return
    let live = true
    api.facesForBib(q).then((r) => {
      if (!live) return
      setCand(r)
      if (!touched.current) setChosen(new Set(r.faces.filter((f) => f.preselect).map((f) => f.id)))
    }).catch(() => {})
    return () => { live = false }
  }, [q, enabled, doneKey])

  // búsqueda automática con las caras elegidas
  const key = useMemo(() => [...chosen].sort().join(','), [chosen])
  useEffect(() => {
    if (!enabled) return
    if (!key) { onResults(null); setCount(null); return }
    let live = true
    setSearching(true)
    const t = setTimeout(() => {
      api.faceSearch(key.split(',').map(Number))
        .then((r) => { if (live) { onResults(r.results); setCount(r.count) } })
        .catch(() => { if (live) onResults(null) })
        .finally(() => { if (live) setSearching(false) })
    }, 250)
    return () => { live = false; clearTimeout(t) }
  }, [key, enabled, doneKey]) // eslint-disable-line react-hooks/exhaustive-deps

  if (!enabled) {
    return (
      <>
        <div className="mt-10 flex flex-wrap items-center justify-between gap-4 rounded-2xl border border-white/10 bg-gradient-to-r from-ink-900 to-ink-950 p-5">
          <div className="flex items-start gap-3">
            <ScanFace size={26} className="mt-0.5 shrink-0 text-accent" aria-hidden />
            <div>
              <p className="font-medium">¿Sales en fotos donde no se lee el dorsal?</p>
              <p className="text-sm text-ink-300">Busca también por tu cara, a partir de las fotos donde sí se lee el {q}.</p>
            </div>
          </div>
          <button onClick={() => setConsent(true)} className="rounded-xl bg-ink-100 px-4 py-2 text-sm font-medium text-ink-950 hover:bg-white">Buscar también por la cara</button>
        </div>
        {consent && <ConsentDialog onClose={() => setConsent(false)} onEnabled={onEnabled} />}
      </>
    )
  }

  const toggle = (id) => { touched.current = true; setChosen((s) => { const n = new Set(s); n.has(id) ? n.delete(id) : n.add(id); return n }) }
  const faces = cand?.faces ?? []
  return (
    <section className="mt-10 rounded-2xl border border-white/10 bg-ink-900/60 p-4 sm:p-5" aria-label="Búsqueda por cara">
      <div className="flex flex-wrap items-baseline justify-between gap-2">
        <h3 className="flex items-center gap-2 font-medium"><ScanFace size={18} className="text-accent" aria-hidden /> Tu cara en otras fotos</h3>
        <span className="text-xs text-ink-500" role="status">
          {facePending > 0 ? <span className="flex items-center gap-1"><Loader2 size={12} className="animate-spin" aria-hidden /> Analizando caras {fs.done || 0}/{stats.photos}</span>
            : searching ? 'Buscando…' : count !== null ? `${count} foto${count === 1 ? '' : 's'} con una cara parecida` : ''}
        </span>
      </div>
      {stats?.faces?.error && <p className="mt-2 text-sm text-amber-300">{stats.faces.error}</p>}
      {cand === null ? <div className="rf-skeleton mt-3 h-24 rounded-lg" /> : faces.length === 0 ? (
        <p className="mt-2 text-sm text-ink-300">{cand.indexed < cand.photos ? 'Todavía no se han analizado las caras de las fotos con este dorsal. Aparecerán aquí en cuanto estén listas.' : 'No se ve ninguna cara en las fotos con este dorsal (de espaldas, muy lejos o tapada).'}</p>
      ) : (
        <>
          <p className="mt-1 text-sm text-ink-300">Marcadas: las caras que aparecen justo encima del dorsal {q}. <strong className="text-ink-100">Desmarca las que no sean tuyas</strong> y añade otras si hace falta.</p>
          <ul className="mt-3 flex gap-2 overflow-x-auto pb-2">
            {faces.map((f) => {
              const on = chosen.has(f.id)
              return (
                <li key={f.id} className="shrink-0">
                  <button onClick={() => toggle(f.id)} aria-pressed={on} aria-label={on ? 'Quitar esta cara de la búsqueda' : 'Usar esta cara en la búsqueda'}
                    className={`relative block h-20 w-20 overflow-hidden rounded-xl border-2 transition sm:h-24 sm:w-24 ${on ? 'border-accent' : 'border-transparent opacity-50 hover:opacity-90'}`}>
                    <RetryImg src={api.faceCropUrl(f.id)} alt="" loading="lazy" className="h-full w-full object-cover" />
                    {on && <span className="absolute right-1 top-1 grid h-5 w-5 place-items-center rounded-full bg-accent text-ink-950"><Check size={12} strokeWidth={3} /></span>}
                    {f.associated && f.consistent === false && <span className="absolute inset-x-0 bottom-0 bg-amber-400/90 text-[10px] font-semibold text-black">¿otra persona?</span>}
                    {f.associated && !f.trusted_bib && f.consistent !== false && <span className="absolute inset-x-0 bottom-0 bg-amber-400/90 text-[10px] font-semibold text-black">dorsal dudoso</span>}
                  </button>
                </li>
              )
            })}
          </ul>
          <p className="text-[11px] text-ink-500">El parecido facial no es una certeza: revisa las fotos antes de descargarlas.</p>
        </>
      )}
    </section>
  )
}
