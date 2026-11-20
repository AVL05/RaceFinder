import { useEffect, useRef, useState } from 'react'
import { Settings2, FlaskConical, RotateCw, ScanFace, Trash2, Images, X, Loader2, AlertTriangle } from 'lucide-react'
import { ConsentDialog } from './Faces.jsx'
import { api } from './api.js'
import { useToast } from './Toast.jsx'

const MODES = [
  ['fast', 'Rápido', 'Una pasada por foto. Puede saltarse dorsales muy pequeños.'],
  ['balanced', 'Equilibrado', 'Recomendado. Si no ve ningún dorsal, revisa la foto por zonas.'],
  ['thorough', 'A fondo', 'Revisa siempre la foto por zonas. Más lento, para fotos con mucha gente lejos.'],
]

export default function SettingsPanel({ onChanged, onOpenEval, onWiped }) {
  const toast = useToast()
  const [open, setOpen] = useState(false)
  const [s, setS] = useState(null)
  const [range, setRange] = useState({ min: '', max: '' })
  const [consent, setConsent] = useState(false)
  const [wipe, setWipe] = useState(false)
  const [count, setCount] = useState(null)
  const ref = useRef(null)
  const trigger = useRef(null)
  const panel = useRef(null)

  const close = () => {
    setOpen(false)
    trigger.current?.focus()
  }

  useEffect(() => {
    if (!open) return
    panel.current?.focus({ preventScroll: true })
    api.stats().then((st) => setCount(st.photos)).catch(() => {})
    api.settings().then((v) => { setS(v); setRange({ min: v.min_number || '', max: v.max_number === 99999 ? '' : v.max_number }) }).catch((e) => toast(e.message, 'error'))
    const k = (e) => {
      if (e.key === 'Escape' && !e.target.closest?.('[aria-modal="true"]')) close()
    }
    const c = (e) => { if (ref.current && !ref.current.contains(e.target)) setOpen(false) }
    window.addEventListener('keydown', k); document.addEventListener('mousedown', c)
    return () => { window.removeEventListener('keydown', k); document.removeEventListener('mousedown', c) }
  }, [open, toast])

  const save = async (next, msg) => {
    try { setS(await api.saveSettings(next)); toast(msg, 'ok'); onChanged?.() } catch (e) { toast(e.message, 'error') }
  }
  const applyRange = () => {
    const min = range.min === '' ? 0 : +range.min, max = range.max === '' ? 99999 : +range.max
    save({ ...s, min_number: min, max_number: max }, min === 0 && max === 99999 ? 'Se muestran todos los números' : `Solo dorsales del ${min} al ${max}`)
  }

  return (
    <div className="relative" ref={ref}>
      <button ref={trigger} onClick={() => setOpen(!open)} aria-expanded={open} aria-haspopup="dialog" aria-label="Ajustes" title="Ajustes"
        className={`rf-button rf-button-quiet ${open ? 'bg-white/5' : ''}`}>
        <Settings2 size={18} aria-hidden />
      </button>
      {open && (
        <div ref={panel} tabIndex={-1} role="dialog" aria-labelledby="ajustes-title" className="rf-settings text-sm rf-fade">
          <div className="rf-settings-title">
            <h2 id="ajustes-title" className="text-lg font-semibold">Ajustes</h2>
            <button onClick={close} className="rf-button rf-button-quiet" aria-label="Cerrar ajustes"><X size={16} aria-hidden /></button>
          </div>
          {!s ? <div className="rf-skeleton m-4 h-40 rounded-lg" /> : (
            <div className="space-y-5 p-4">
              <fieldset>
                <legend className="font-medium">Lectura de dorsales</legend>
                <div className="mt-2 space-y-1">
                  {MODES.map(([id, label, hint]) => (
                    <label key={id} className={`flex cursor-pointer items-start gap-3 rounded-lg p-2 ${s.mode === id ? 'bg-white/5' : 'hover:bg-white/[0.03]'}`}>
                      <input type="radio" name="mode" checked={s.mode === id} onChange={() => save({ ...s, mode: id }, `Modo ${label.toLowerCase()}`)} className="mt-1 accent-[var(--color-accent)]" />
                      <span><span className="font-medium">{label}</span><br /><span className="text-xs text-ink-300">{hint}</span></span>
                    </label>
                  ))}
                </div>
              </fieldset>

              <fieldset>
                <legend className="font-medium">Rango global de dorsales</legend>
                <p className="mt-1 text-xs text-ink-300">Se usa en la biblioteca y en los álbumes sin un rango propio. Las correcciones manuales se conservan.</p>
                <form className="mt-2 flex items-center gap-2" onSubmit={(e) => { e.preventDefault(); applyRange() }}>
                  <input aria-label="Dorsal mínimo" inputMode="numeric" placeholder="desde" value={range.min} onChange={(e) => setRange({ ...range, min: e.target.value.replace(/\D/g, '').slice(0, 5) })} className="min-w-0 flex-1 rounded-lg border border-white/10 bg-ink-950 px-2.5 py-1.5" />
                  <span className="text-ink-500">–</span>
                  <input aria-label="Dorsal máximo" inputMode="numeric" placeholder="hasta" value={range.max} onChange={(e) => setRange({ ...range, max: e.target.value.replace(/\D/g, '').slice(0, 5) })} className="min-w-0 flex-1 rounded-lg border border-white/10 bg-ink-950 px-2.5 py-1.5" />
                  <button className="shrink-0 rounded-lg bg-ink-100 px-3 py-1.5 font-medium text-ink-950 hover:bg-white">Aplicar</button>
                </form>
              </fieldset>

              <fieldset>
                <legend className="flex items-center gap-2 font-medium"><ScanFace size={15} aria-hidden /> Búsqueda por cara</legend>
                {s.faces_enabled ? (
                  <div className="mt-1 space-y-2">
                    <p className="text-xs text-ink-300">Activada. Al buscar un dorsal verás también las fotos donde aparece la misma cara. Los datos faciales son anónimos y solo están en este equipo.</p>
                    <div className="flex flex-wrap gap-3">
                      <button onClick={() => save({ ...s, faces_enabled: false }, 'Búsqueda por cara desactivada (los datos se conservan)')} className="text-xs text-ink-300 underline hover:text-white">Desactivar</button>
                      <button onClick={async () => {
                        if (!window.confirm('Se borrarán todos los datos faciales (vectores y recortes de caras) y se desactivará la búsqueda por cara. Tus fotos no se tocan.')) return
                        try { const r = await api.deleteFaces(); setS({ ...s, faces_enabled: false }); toast(`Datos faciales borrados (${r.deleted} caras)`, 'ok'); onChanged?.() } catch (e) { toast(e.message, 'error') }
                      }} className="flex items-center gap-1 text-xs text-red-300 underline hover:text-red-200"><Trash2 size={12} aria-hidden /> Borrar todos los datos faciales</button>
                    </div>
                  </div>
                ) : (
                  <div className="mt-1">
                    <p className="text-xs text-ink-300">Encuentra fotos en las que sales aunque no se lea el dorsal. Desactivada por defecto.</p>
                    <button onClick={() => setConsent(true)} className="mt-2 rounded-lg border border-white/10 px-3 py-1.5 text-xs hover:bg-white/5">Activar…</button>
                  </div>
                )}
              </fieldset>

              <div className="flex flex-col items-start gap-2 border-t border-white/10 pt-4">
                <button onClick={async () => {
                  if (!window.confirm('Se volverán a leer todas las fotos con el modo actual. Tus correcciones manuales se conservan.')) return
                  try { await api.reanalyze(); toast('Releyendo todas las fotos', 'ok'); onChanged?.(); setOpen(false) } catch (e) { toast(e.message, 'error') }
                }} className="flex items-center gap-2 text-ink-300 hover:text-white"><RotateCw size={14} aria-hidden /> Volver a leer todas las fotos</button>
                <button onClick={() => { setOpen(false); onOpenEval() }} className="flex items-center gap-2 text-ink-300 hover:text-white"><FlaskConical size={14} aria-hidden /> Medir la precisión (avanzado)</button>
              </div>

              <fieldset className="rounded-xl border border-red-500/25 bg-red-500/[0.04] p-3">
                <legend className="flex items-center gap-2 px-1 font-medium"><Images size={15} aria-hidden /> Biblioteca</legend>
                <p className="text-xs text-ink-300">{count === null ? '…' : count === 1 ? '1 foto en RaceFinder.' : `${count} fotos en RaceFinder.`} Tus archivos originales en el disco no se tocan.</p>
                <button disabled={!count} onClick={() => { setOpen(false); setWipe(true) }}
                  className="mt-2 flex items-center gap-2 rounded-lg border border-red-500/40 px-3 py-1.5 text-xs text-red-300 hover:bg-red-500/10 disabled:opacity-40">
                  <Trash2 size={13} aria-hidden /> Eliminar todas las fotos…
                </button>
              </fieldset>
            </div>
          )}
        </div>
      )}
      {wipe && <DeleteAllDialog count={count} onClose={() => setWipe(false)} onDone={() => { setWipe(false); setCount(0); onWiped?.(); onChanged?.() }} />}
      {consent && <ConsentDialog onClose={() => setConsent(false)} onEnabled={() => { setS({ ...s, faces_enabled: true }); onChanged?.() }} />}
    </div>
  )
}

function DeleteAllDialog({ count, onClose, onDone }) {
  const toast = useToast()
  const [text, setText] = useState('')
  const [busy, setBusy] = useState(false)
  const ok = text.trim().toUpperCase() === 'ELIMINAR'
  useEffect(() => {
    const k = (e) => { if (e.key === 'Escape' && !busy) onClose() }
    window.addEventListener('keydown', k)
    return () => window.removeEventListener('keydown', k)
  }, [busy, onClose])
  const run = async () => {
    setBusy(true)
    try {
      const r = await api.removeAll()
      toast(r.deleted === 1 ? 'Se ha eliminado 1 foto' : `Se han eliminado ${r.deleted} fotos`, 'ok')
      onDone()
    } catch (e) { toast(e.message, 'error'); setBusy(false) }
  }
  return (
    <div className="fixed inset-0 z-[55] grid place-items-center bg-black/70 p-4 backdrop-blur-sm rf-fade" onMouseDown={(e) => { if (e.target === e.currentTarget && !busy) onClose() }}>
      <div role="dialog" aria-modal="true" aria-labelledby="wipe-title" className="w-full max-w-md rounded-2xl border border-white/10 bg-ink-900 p-6 shadow-2xl">
        <div className="flex items-start justify-between gap-4">
          <h2 id="wipe-title" className="flex items-center gap-2 text-lg font-semibold"><AlertTriangle size={20} className="text-red-400" aria-hidden /> Eliminar todas las fotos</h2>
          <button onClick={onClose} disabled={busy} aria-label="Cerrar" className="text-ink-500 hover:text-white"><X size={18} /></button>
        </div>
        <p className="mt-3 text-sm text-ink-300">
          Se quitarán de RaceFinder <strong className="text-ink-100">{count === 1 ? '1 foto' : `las ${count} fotos`}</strong> con todo lo que se ha generado a partir de ellas:
          dorsales leídos, revisiones, datos faciales y etiquetas de evaluación. No se puede deshacer.
        </p>
        <p className="mt-2 text-sm text-ink-300">Tus archivos originales en el disco <strong className="text-ink-100">no se tocan</strong>: podrás volver a importarlos cuando quieras. Los ajustes se conservan.</p>
        <label htmlFor="wipe-confirm" className="mt-5 block text-sm">Escribe <strong className="font-mono text-red-300">ELIMINAR</strong> para confirmar</label>
        <input id="wipe-confirm" autoFocus autoComplete="off" value={text} onChange={(e) => setText(e.target.value)} onKeyDown={(e) => { if (e.key === 'Enter' && ok && !busy) run() }}
          className="mt-1.5 w-full rounded-lg border border-white/10 bg-ink-950 px-3 py-2 font-mono text-sm focus:border-red-400/60" />
        <div className="mt-5 flex justify-end gap-2">
          <button onClick={onClose} disabled={busy} className="rounded-lg px-4 py-2 text-sm text-ink-300 hover:text-white">Cancelar</button>
          <button onClick={run} disabled={!ok || busy} className="flex items-center gap-2 rounded-lg bg-red-500 px-4 py-2 text-sm font-medium text-white hover:bg-red-400 disabled:opacity-40">
            {busy ? <Loader2 size={15} className="animate-spin" aria-hidden /> : <Trash2 size={15} aria-hidden />} Eliminar todo
          </button>
        </div>
      </div>
    </div>
  )
}
