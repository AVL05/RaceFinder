import { useCallback, useEffect, useRef, useState } from 'react'
import { X, ChevronLeft, ChevronRight, Download, Trash2, Check, Ban, Plus, ZoomIn, ZoomOut, ScanLine, Circle, CheckCircle2, RotateCw, Loader2 } from 'lucide-react'
import { api } from './api.js'
import { useToast } from './Toast.jsx'
import RetryImg from './RetryImg.jsx'

const fmtSize = (b) => (b > 1e6 ? `${(b / 1e6).toFixed(1)} MB` : `${Math.round(b / 1e3)} KB`)

export default function Lightbox({ photos, id, onClose, onNavigate, selected, onToggleSelect, onChanged, onDelete }) {
  const toast = useToast()
  const idx = photos.findIndex((p) => p.id === id)
  const base = photos[idx]
  const prev = photos[idx - 1], next = photos[idx + 1]
  const [detail, setDetail] = useState(null)
  const [zoom, setZoom] = useState(false)
  const [boxes, setBoxes] = useState(true)
  const [loaded, setLoaded] = useState(false)
  const [zoomLoaded, setZoomLoaded] = useState(false)
  const [manual, setManual] = useState('')
  const root = useRef(null)
  const scroller = useRef(null)
  const zoomAt = useRef(null)
  const drag = useRef(null)
  const touch = useRef(null)

  const photo = detail?.id === id ? { ...base, ...detail } : base
  const bibs = (detail?.id === id ? detail.bibs : null) ?? base?.bibs ?? (base?.evidence ?? []).map((e) => ({ ...e, id: e.bib_id }))
  const isSel = selected.has(id)

  const loadDetail = useCallback(async () => { try { setDetail(await api.photo(id)) } catch { /* se muestra lo que ya hay */ } }, [id])
  useEffect(() => { setZoom(false); setLoaded(false); setManual(''); loadDetail() }, [id, loadDetail])
  useEffect(() => { if (!zoom) setZoomLoaded(false) }, [zoom])

  // precarga de las vecinas: navegación instantánea
  useEffect(() => { [prev, next].forEach((p) => { if (p) new Image().src = api.previewUrl(p) }) }, [prev, next])

  // foco atrapado dentro del visor y devuelto al cerrar; sin scroll de fondo
  useEffect(() => {
    const prevFocus = document.activeElement
    const overflow = document.body.style.overflow
    document.body.style.overflow = 'hidden'
    root.current?.focus()
    return () => { document.body.style.overflow = overflow; prevFocus?.focus?.() }
  }, [])

  const act = async (fn, ok) => { try { await fn(); await loadDetail(); onChanged(); if (ok) toast(ok, 'ok') } catch (e) { toast(e.message, 'error') } }
  const addManual = () => { if (/^\d{1,5}$/.test(manual)) act(async () => { await api.addBib(id, manual); setManual('') }, `Dorsal ${manual} añadido`) }

  useEffect(() => {
    const k = (e) => {
      if (e.key === 'Tab' && root.current) {
        const f = [...root.current.querySelectorAll('button:not([disabled]), a[href], input')]
        if (!f.length) return
        if (e.shiftKey && document.activeElement === f[0]) { e.preventDefault(); f[f.length - 1].focus() }
        else if (!e.shiftKey && document.activeElement === f[f.length - 1]) { e.preventDefault(); f[0].focus() }
        return
      }
      if (e.target.tagName === 'INPUT') { if (e.key === 'Escape') e.target.blur(); return }
      if (e.key === 'Escape') { if (zoom) setZoom(false); else onClose() }
      else if (e.key === 'ArrowLeft' && prev) onNavigate(prev.id)
      else if (e.key === 'ArrowRight' && next) onNavigate(next.id)
      else if (e.key.toLowerCase() === 's') onToggleSelect(base)
      else if (e.key.toLowerCase() === 'z' || e.key === ' ') { e.preventDefault(); setZoom((z) => !z) }
      else if (e.key.toLowerCase() === 'b') setBoxes((b) => !b)
      else if (e.key.toLowerCase() === 'd') window.location.assign(api.downloadUrl(base))
    }
    window.addEventListener('keydown', k)
    return () => window.removeEventListener('keydown', k)
  }, [prev, next, zoom, id, base, onClose, onNavigate, onToggleSelect])

  // al ampliar, centra el punto en el que se hizo clic
  const onZoomLoad = (e) => {
    const el = scroller.current, img = e.currentTarget
    if (!el) return
    const [fx, fy] = zoomAt.current ?? [0.5, 0.5]
    el.scrollLeft = fx * img.naturalWidth - el.clientWidth / 2
    el.scrollTop = fy * img.naturalHeight - el.clientHeight / 2
    setZoomLoaded(true)
  }

  if (!base) return null
  const W = photo.width || 1, H = photo.height || 1

  return (
    <div ref={root} tabIndex={-1} className="fixed inset-0 z-50 flex flex-col bg-black outline-none rf-fade" role="dialog" aria-modal="true" aria-label={`Foto ${photo.name}`}>
      {/* barra superior */}
      <div className="flex items-center gap-2 px-3 py-2.5 text-sm sm:px-4">
        <div className="min-w-0 flex-1">
          <div className="truncate font-medium">{photo.name}</div>
          <div className="text-xs text-ink-500">{idx + 1} de {photos.length} · {photo.width}×{photo.height} · {fmtSize(photo.size || 0)}</div>
        </div>
        <IconBtn onClick={() => onToggleSelect(base)} label={isSel ? 'Quitar de la selección (S)' : 'Seleccionar (S)'} active={isSel}>
          {isSel ? <CheckCircle2 size={18} /> : <Circle size={18} />}
        </IconBtn>
        <IconBtn onClick={() => setBoxes(!boxes)} label={boxes ? 'Ocultar marcas de dorsal (B)' : 'Mostrar marcas de dorsal (B)'} active={boxes} className="hidden sm:grid"><ScanLine size={18} /></IconBtn>
        <IconBtn onClick={() => setZoom(!zoom)} label={zoom ? 'Ajustar a la pantalla (Z)' : 'Ver a tamaño real (Z)'} className="hidden sm:grid">{zoom ? <ZoomOut size={18} /> : <ZoomIn size={18} />}</IconBtn>
        <a href={api.downloadUrl(base)} download={photo.name} className="flex h-9 items-center gap-2 rounded-lg bg-white/10 px-3 hover:bg-white/15" title="Descargar original (D)">
          <Download size={16} aria-hidden /><span className="hidden sm:inline">Original</span>
        </a>
        <IconBtn onClick={() => window.confirm('¿Quitar esta foto de RaceFinder? Tu archivo original en el disco no se toca.') && onDelete(id)} label="Quitar de RaceFinder" className="hover:text-red-300"><Trash2 size={17} /></IconBtn>
        <IconBtn onClick={onClose} label="Cerrar (Esc)"><X size={20} /></IconBtn>
      </div>

      {/* imagen */}
      <div className="relative flex min-h-0 flex-1 items-center justify-center"
        onTouchStart={(e) => { touch.current = e.touches[0].clientX }}
        onTouchEnd={(e) => {
          if (zoom || touch.current === null) return
          const dx = e.changedTouches[0].clientX - touch.current
          if (dx > 60 && prev) onNavigate(prev.id); else if (dx < -60 && next) onNavigate(next.id)
          touch.current = null
        }}>
        {zoom ? (
          <div ref={scroller} className="h-full w-full cursor-grab overflow-auto active:cursor-grabbing"
            onMouseDown={(e) => { drag.current = { x: e.clientX, y: e.clientY, l: scroller.current.scrollLeft, t: scroller.current.scrollTop, moved: false } }}
            onMouseMove={(e) => {
              const d = drag.current; if (!d) return
              if (Math.abs(e.clientX - d.x) + Math.abs(e.clientY - d.y) > 4) d.moved = true
              scroller.current.scrollLeft = d.l - (e.clientX - d.x); scroller.current.scrollTop = d.t - (e.clientY - d.y)
            }}
            onMouseUp={() => { const d = drag.current; drag.current = null; if (d && !d.moved) setZoom(false) }}
            onMouseLeave={() => { drag.current = null }}>
            <RetryImg src={api.originalUrl(base)} alt={photo.name} onLoad={onZoomLoad} draggable={false} className={`max-w-none select-none ${zoomLoaded ? '' : 'invisible'}`} />
            {!zoomLoaded && <div className="pointer-events-none absolute inset-0 grid place-items-center"><span className="flex items-center gap-2 rounded-full bg-white/10 px-4 py-2 text-sm"><Loader2 size={16} className="animate-spin" aria-hidden /> Cargando a tamaño real…</span></div>}
          </div>
        ) : (
          <>
            {!loaded && <Loader2 className="absolute animate-spin text-ink-500" size={28} aria-hidden />}
            <div className="relative max-h-full max-w-full">
              <RetryImg key={id} src={api.previewUrl(base)} alt={photo.name} onLoad={() => setLoaded(true)} draggable={false}
                onClick={(e) => { const r = e.currentTarget.getBoundingClientRect(); zoomAt.current = [(e.clientX - r.left) / r.width, (e.clientY - r.top) / r.height]; setZoom(true) }}
                className={`block max-h-[calc(100dvh-14rem)] max-w-[100vw] cursor-zoom-in select-none object-contain transition-opacity duration-200 sm:max-w-[calc(100vw-8rem)] ${loaded ? 'opacity-100' : 'opacity-0'}`} />
              {loaded && boxes && base.face?.bbox && (() => {
                const f = base.face.bbox
                return (
                  <div className="pointer-events-none absolute rounded-md border-2 border-violet-300"
                    style={{ left: `${(f[0] / W) * 100}%`, top: `${(f[1] / H) * 100}%`, width: `${((f[2] - f[0]) / W) * 100}%`, height: `${((f[3] - f[1]) / H) * 100}%` }}>
                    <span className="absolute -top-6 left-0 whitespace-nowrap rounded bg-violet-300 px-1.5 py-0.5 text-[11px] font-bold text-ink-950">cara · {base.face.strength}</span>
                  </div>
                )
              })()}
              {loaded && boxes && bibs.filter((b) => b.bbox?.[2] > 0).map((b) => (
                <div key={b.id} className="pointer-events-none absolute rounded-sm border-2 border-accent"
                  style={{ left: `${(b.bbox[0] / W) * 100}%`, top: `${(b.bbox[1] / H) * 100}%`, width: `${((b.bbox[2] - b.bbox[0]) / W) * 100}%`, height: `${((b.bbox[3] - b.bbox[1]) / H) * 100}%` }}>
                  <span className="absolute -top-6 left-0 rounded bg-accent px-1.5 py-0.5 text-[11px] font-bold tabular-nums text-ink-950">{b.number}</span>
                </div>
              ))}
            </div>
          </>
        )}
        {prev && <NavBtn side="left" onClick={() => onNavigate(prev.id)} />}
        {next && <NavBtn side="right" onClick={() => onNavigate(next.id)} />}
      </div>

      {/* dorsales */}
      <div className="border-t border-white/10 bg-ink-950/80 px-3 py-3 sm:px-4">
        <div className="mx-auto flex max-w-5xl flex-wrap items-center gap-2 text-sm">
          <span className="mr-1 text-ink-500">Dorsales:</span>
          {photo.ocr_status === 'pending' || photo.ocr_status === 'processing' ? <span className="flex items-center gap-1 text-ink-300"><Loader2 size={13} className="animate-spin" aria-hidden /> leyendo…</span> : null}
          {photo.ocr_status === 'error' && (
            <button onClick={() => act(() => api.reprocess(id), 'Foto en cola para reintentar')} className="flex items-center gap-1 text-red-300 underline"><RotateCw size={13} aria-hidden /> No se pudo leer · reintentar</button>
          )}
          {photo.ocr_status === 'done' && bibs.length === 0 && <span className="text-ink-300">ninguno leído</span>}
          {bibs.map((b) => {
            const ok = b.review === 'confirmed' || b.review === 'manual'
            return (
              <span key={b.id} className={`flex items-center gap-1 rounded-full border py-0.5 pl-3 pr-1 ${ok ? 'border-green-500/40 bg-green-500/10' : 'border-white/10 bg-ink-900'}`}>
                <strong className="tabular-nums">{b.number}</strong>
                <span className="ml-1 text-xs text-ink-500" title="Puntuación del lector de texto, no una probabilidad">{b.review === 'manual' ? 'a mano' : ok ? 'confirmado' : `${Math.round(b.confidence * 100)}%`}</span>
                {!ok && <button onClick={() => act(() => api.review(b.id, 'confirmed'), `Dorsal ${b.number} confirmado`)} className="rounded-full p-1.5 hover:bg-white/10 hover:text-green-300" aria-label={`Confirmar dorsal ${b.number}`} title="Es correcto"><Check size={14} /></button>}
                <button onClick={() => act(() => api.review(b.id, 'rejected'), `Dorsal ${b.number} descartado`)} className="rounded-full p-1.5 hover:bg-white/10 hover:text-red-300" aria-label={`Descartar dorsal ${b.number}`} title="No es un dorsal / es incorrecto"><Ban size={14} /></button>
              </span>
            )
          })}
          <form className="ml-auto flex items-center gap-1.5" onSubmit={(e) => { e.preventDefault(); addManual() }}>
            <input value={manual} onChange={(e) => setManual(e.target.value.replace(/\D/g, '').slice(0, 5))} inputMode="numeric"
              aria-label="Añadir un dorsal que falta" placeholder="¿Falta alguno?" className="w-32 rounded-lg border border-white/10 bg-ink-900 px-2.5 py-1.5 text-sm placeholder:text-ink-500 focus:border-accent/60 focus:outline-none" />
            <button disabled={!manual} className="rounded-lg border border-white/10 p-2 hover:bg-white/5 disabled:opacity-40" aria-label="Añadir dorsal"><Plus size={14} /></button>
          </form>
        </div>
        <p className="mx-auto mt-2 hidden max-w-5xl text-[11px] text-ink-500 lg:block">← → navegar · S seleccionar · Z o clic ampliar · B marcas · D descargar · Esc cerrar</p>
      </div>
    </div>
  )
}

const IconBtn = ({ onClick, label, children, active, className = '' }) => (
  <button onClick={onClick} aria-label={label} title={label} aria-pressed={active}
    className={`grid h-9 w-9 place-items-center rounded-lg hover:bg-white/10 ${active ? 'text-accent' : 'text-ink-100'} ${className}`}>{children}</button>
)

const NavBtn = ({ side, onClick }) => (
  <button onClick={onClick} aria-label={side === 'left' ? 'Foto anterior' : 'Foto siguiente'}
    className={`absolute top-1/2 hidden -translate-y-1/2 rounded-full bg-black/50 p-3 backdrop-blur hover:bg-black/80 sm:block ${side === 'left' ? 'left-3' : 'right-3'}`}>
    {side === 'left' ? <ChevronLeft size={22} /> : <ChevronRight size={22} />}
  </button>
)
