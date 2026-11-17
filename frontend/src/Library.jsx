import { memo, useCallback, useEffect, useMemo, useRef, useState } from 'react'
import { Check, Download, FolderDown, Trash2, X, Loader2, ImagePlus, FolderOpen, Hash, AlertCircle, SearchX, ChevronDown, ChevronUp } from 'lucide-react'
import { api, downloadPhotos, isOffline } from './api.js'
import Lightbox from './Lightbox.jsx'
import { FaceSection } from './Faces.jsx'
import { useToast } from './Toast.jsx'
import RetryImg from './RetryImg.jsx'
import VirtualGrid from './VirtualGrid.jsx'

const PAGE = 120
const plural = (n, one, many) => `${n} ${n === 1 ? one : many}`
const FILTERS = [['all', 'Todas'], ['with_bib', 'Con dorsal'], ['no_bib', 'Sin dorsal leído'], ['pending', 'Por analizar'], ['error', 'Con error']]

function similarTo(a, b) {
  if (a === b || Math.abs(a.length - b.length) > 1) return false
  if (a.length === b.length) return [...a].filter((x, i) => x !== b[i]).length === 1
  const [s, l] = a.length < b.length ? [a, b] : [b, a]
  return [...l].some((_, i) => l.slice(0, i) + l.slice(i + 1) === s)
}

export default function Library({ q, similar, setSimilar, stats, version, onSearch, onRefresh, onPickFiles, onPickFolder }) {
  const toast = useToast()
  const [filter, setFilter] = useState('all')
  const [photos, setPhotos] = useState(null)
  const [total, setTotal] = useState(0)
  const [results, setResults] = useState(null)
  const [faceResults, setFaceResults] = useState(null)
  const [searching, setSearching] = useState(false)
  const [index, setIndex] = useState([])
  const [selected, setSelected] = useState(() => new Set())
  const [open, setOpen] = useState(null)
  // lista congelada del visor: si una revisión saca la foto de los resultados, el visor sigue mostrándola
  const [viewList, setViewList] = useState([])
  const [busy, setBusy] = useState('')
  const anchor = useRef(null)
  const loadingMore = useRef(false)
  const photosRef = useRef(photos)
  photosRef.current = photos

  // ---------- datos ----------
  // tramo de la galería que se está viendo (lo informa la rejilla virtualizada)
  const visible = useRef([0, PAGE])
  const totalRef = useRef(0)
  totalRef.current = total
  const loadBrowse = useCallback(async (reset) => {
    try {
      const cur = photosRef.current
      if (reset || !cur || filter !== 'all') {
        // filtros: las fotos entran y salen del filtro, se recarga desde arriba lo ya cargado (máx. 1000)
        const keep = reset || !cur ? PAGE : Math.min(1000, Math.max(PAGE, cur.length))
        const r = await api.photos(keep, 0, filter)
        setPhotos(r.photos); setTotal(r.total)
        return
      }
      // "Todas" con miles de fotos: solo se refresca el tramo visible y se conserva el resto de la lista
      const [a, b] = visible.current
      const offset = Math.max(0, a - 40), limit = Math.min(1000, Math.max(PAGE, b - a + 80))
      const r = await api.photos(limit, offset, filter)
      let next = cur
      if (r.total !== totalRef.current) {  // fotos añadidas o quitadas: las nuevas van arriba
        const top = offset === 0 ? r : await api.photos(PAGE, 0, filter)
        const ids = new Set(top.photos.map((p) => p.id))
        next = [...top.photos, ...cur.filter((p) => !ids.has(p.id))]
        if (r.total < totalRef.current) {   // borradas: se quitan las que ya no existen en el tramo consultado
          const seen = new Set(r.photos.map((p) => p.id))
          next = next.filter((p, i) => i < offset || i >= offset + limit || seen.has(p.id))
        }
      }
      const byId = new Map(r.photos.map((p) => [p.id, p]))
      setPhotos(next.map((p) => byId.get(p.id) ?? p)); setTotal(r.total)
    } catch (e) { if (!isOffline(e)) { setPhotos((p) => p ?? []); toast(e.message, 'error') } }  // sin conexión: se espera y se recarga al volver
  }, [filter, toast])

  const loadMore = useCallback(async () => {
    const cur = photosRef.current
    if (!cur || loadingMore.current || cur.length >= total) return
    loadingMore.current = true
    try {
      const r = await api.photos(PAGE, cur.length, filter)
      setPhotos((old) => { const ids = new Set(old.map((x) => x.id)); return [...old, ...r.photos.filter((x) => !ids.has(x.id))] })
      setTotal(r.total)
    } catch { /* se reintenta al volver a hacer scroll */ } finally { loadingMore.current = false }
  }, [total, filter])

  const loadSearch = useCallback(async () => {
    if (!q) { setResults(null); return }
    setSearching(true)
    try { setResults((await api.search(q, similar)).results) } catch (e) { if (!isOffline(e)) { toast(e.message, 'error'); setResults([]) } } finally { setSearching(false) }
  }, [q, similar, toast])

  const loadIndex = useCallback(async () => { try { setIndex((await api.bibIndex()).bibs) } catch { /* no crítico */ } }, [])

  useEffect(() => { setPhotos(null); loadBrowse(true) }, [filter]) // eslint-disable-line react-hooks/exhaustive-deps
  useEffect(() => { loadBrowse(false); loadIndex() }, [version]) // eslint-disable-line react-hooks/exhaustive-deps
  useEffect(() => { loadSearch() }, [q, similar, version]) // eslint-disable-line react-hooks/exhaustive-deps
  useEffect(() => { setSelected(new Set()); anchor.current = null; setFaceResults(null) }, [q, filter])


  const reloadAll = useCallback(async () => { await Promise.all([loadBrowse(false), loadSearch(), loadIndex()]); onRefresh() }, [loadBrowse, loadSearch, loadIndex, onRefresh])

  // ---------- lista visible y selección ----------
  const sure = useMemo(() => results?.filter((p) => p.match === 'exact') ?? [], [results])
  const unsure = useMemo(() => results?.filter((p) => p.match !== 'exact') ?? [], [results])
  const bibIds = useMemo(() => new Set((results ?? []).map((p) => p.id)), [results])
  const faceById = useMemo(() => new Map((faceResults ?? []).map((p) => [p.id, p.face])), [faceResults])
  // solo por la cara: fotos que el dorsal no encontró (dorsal tapado, de lado, ilegible…)
  const faceOnly = useMemo(() => (faceResults ?? []).filter((p) => !bibIds.has(p.id)).map((p) => ({ ...p, match: 'face' })), [faceResults, bibIds])
  const shown = useMemo(() => (q ? [...sure, ...unsure, ...faceOnly] : photos ?? []), [q, sure, unsure, faceOnly, photos])
  const selecting = selected.size > 0

  const toggle = (p, e) => {
    const idx = shown.findIndex((x) => x.id === p.id)
    setSelected((s) => {
      const n = new Set(s)
      if (e?.shiftKey && anchor.current !== null) {
        const a = shown.findIndex((x) => x.id === anchor.current)
        const [from, to] = a < idx ? [a, idx] : [idx, a]
        shown.slice(from, to + 1).forEach((x) => n.add(x.id))
      } else n.has(p.id) ? n.delete(p.id) : n.add(p.id)
      return n
    })
    anchor.current = p.id
  }
  const openViewer = (id) => { setViewList(shown); setOpen(id) }
  const onCard = (p, e) => { if (selecting || e.ctrlKey || e.metaKey || e.shiftKey) toggle(p, e); else openViewer(p.id) }
  // con el visor abierto, refresca los datos de las fotos que siguen visibles y conserva las demás
  useEffect(() => {
    if (open === null) return
    const byId = new Map(shown.map((p) => [p.id, p]))
    setViewList((l) => l.map((p) => byId.get(p.id) ?? p))
  }, [shown]) // eslint-disable-line react-hooks/exhaustive-deps

  useEffect(() => {
    const k = (e) => { if (e.key === 'Escape' && !open && selecting) setSelected(new Set()) }
    window.addEventListener('keydown', k)
    return () => window.removeEventListener('keydown', k)
  }, [open, selecting])

  const selPhotos = shown.filter((p) => selected.has(p.id))
  const download = async (list) => {
    if (!list.length) return
    setBusy('download')
    try { await downloadPhotos(list); toast(list.length > 1 ? `Descargando ${list.length} originales en un ZIP` : 'Descargando el original', 'ok') }
    catch (e) { toast(e.message, 'error') } finally { setBusy('') }
  }
  // Guardar en una carpeta del disco: el servidor copia los originales (sin ZIP ni descarga del navegador)
  const saveTo = async (list, subfolder = '') => {
    if (!list.length) return
    setBusy('save')
    try {
      const { path } = await api.pickFolder('¿En qué carpeta guardo las fotos?')
      if (!path) return
      const r = await api.saveToFolder({ ids: list.map((p) => p.id), dest: path, subfolder, open_after: true })
      toast(`${plural(r.saved, 'foto guardada', 'fotos guardadas')} en ${r.dest}${r.skipped ? ` · ${r.skipped} ya estaban` : ''}${r.failed.length ? ` · ${r.failed.length} con error` : ''}`, r.failed.length ? 'warn' : 'ok')
    } catch (e) { toast(e.message, 'error') } finally { setBusy('') }
  }
  const removeSel = async () => {
    if (!window.confirm(`¿Quitar ${selected.size} foto(s) de RaceFinder? Tus archivos originales en el disco no se tocan.`)) return
    setBusy('delete')
    try { await api.removeMany([...selected]); setSelected(new Set()); toast('Fotos quitadas', 'ok'); await reloadAll() }
    catch (e) { toast(e.message, 'error') } finally { setBusy('') }
  }

  // ---------- render ----------
  // todos los hooks van antes de este return anticipado (React exige el mismo orden en cada render)
  const onRange = useCallback((a, b) => { visible.current = [a, b] }, [])
  const handlers = useRef({})
  handlers.current = { onCard, toggle }
  const cardClick = useCallback((p, e) => handlers.current.onCard(p, e), [])
  const cardToggle = useCallback((p, e) => handlers.current.toggle(p, e), [])
  if (stats && stats.photos === 0) return <Empty onPickFiles={onPickFiles} onPickFolder={onPickFolder} />

  const grid = 'grid grid-cols-2 gap-1.5 sm:grid-cols-[repeat(auto-fill,minmax(220px,1fr))] sm:gap-2.5'
  // los manejadores leen el estado más reciente desde una ref: así las tarjetas memorizadas no se repintan sin motivo
  const card = (p, style) => <Card key={p.id} p={p} q={q} face={faceById.get(p.id)} selected={selected.has(p.id)} selecting={selecting} style={style} onClick={cardClick} onToggle={cardToggle} />
  const pending = (stats?.ocr?.pending || 0) + (stats?.ocr?.processing || 0)
  const suggestions = q && results?.length === 0 ? index.filter((b) => similarTo(q, b.number)).slice(0, 8) : []

  return (
    <div className="mx-auto w-full max-w-[1680px] flex-1 px-3 pb-28 pt-5 sm:px-6">
      {q ? (
        <>
          <div className="mb-5 flex flex-wrap items-end justify-between gap-3">
            <div>
              <p className="text-xs uppercase tracking-[0.14em] text-ink-500">Resultados</p>
              <h2 className="mt-1 flex items-center gap-3 text-2xl font-semibold sm:text-3xl">
                Dorsal <span className="text-accent">{q}</span>
                {searching && <Loader2 size={20} className="animate-spin text-ink-500" aria-label="Buscando" />}
              </h2>
              {results && <p className="mt-1 text-sm text-ink-300">{results.length === 0 ? 'Ninguna foto' : `${plural(sure.length, 'foto', 'fotos')}${unsure.length ? ` · ${unsure.length} por revisar` : ''}`}{faceOnly.length ? ` · ${faceOnly.length} más por la cara` : ''}{pending ? ` · ${pending === 1 ? 'queda 1 foto' : `quedan ${pending} fotos`} por analizar` : ''}</p>}
            </div>
            <div className="flex flex-wrap items-center gap-2">
              <label className="flex cursor-pointer items-center gap-2 rounded-lg border border-white/10 px-3 py-2 text-sm text-ink-300 hover:bg-white/5">
                <input type="checkbox" className="accent-[var(--color-accent)]" checked={similar} onChange={(e) => setSimilar(e.target.checked)} />
                Incluir números parecidos
              </label>
              {shown.length > 0 && <>
                <button onClick={() => setSelected(new Set(shown.map((p) => p.id)))} className="rounded-lg border border-white/10 px-3 py-2 text-sm hover:bg-white/5">Seleccionar todas</button>
                <button onClick={() => saveTo(sure.length ? sure : shown, `dorsal-${q}`)} disabled={busy === 'save'} className="flex items-center gap-2 rounded-lg bg-accent px-3 py-2 text-sm font-medium text-ink-950 hover:brightness-110 disabled:opacity-60"
                  title="Copia los originales a una carpeta de tu disco, en una subcarpeta con el dorsal">
                  {busy === 'save' ? <Loader2 size={15} className="animate-spin" aria-hidden /> : <FolderDown size={15} aria-hidden />}
                  {(sure.length || shown.length) === 1 ? 'Guardar la foto en una carpeta' : `Guardar ${sure.length ? `las ${sure.length} fotos` : `las ${shown.length}`} en una carpeta`}
                </button>
                <button onClick={() => download(sure.length ? sure : shown)} disabled={busy === 'download'} className="flex items-center gap-2 rounded-lg border border-white/10 px-3 py-2 text-sm hover:bg-white/5 disabled:opacity-60" title="Descarga un ZIP con el navegador">
                  {busy === 'download' ? <Loader2 size={15} className="animate-spin" aria-hidden /> : <Download size={15} aria-hidden />}
                  ZIP
                </button>
              </>}
            </div>
          </div>

          {results === null && <SkeletonGrid grid={grid} />}

          {results?.length === 0 && (
            <div className="mx-auto mt-14 max-w-lg text-center rf-fade">
              <SearchX size={40} className="mx-auto text-ink-500" aria-hidden />
              <p className="mt-4 text-lg">No hay fotos con el dorsal {q}</p>
              <p className="mt-1 text-sm text-ink-300">
                {pending ? 'Todavía se están analizando fotos: los resultados aparecerán solos.' : similar ? 'Tampoco hay números parecidos. Puede que el dorsal no se vea bien en las fotos.' : 'Prueba a incluir números parecidos: el lector puede haber confundido un dígito.'}
              </p>
              {!similar && <button onClick={() => setSimilar(true)} className="mt-4 rounded-lg bg-accent px-4 py-2 text-sm font-medium text-ink-950">Buscar números parecidos</button>}
              {suggestions.length > 0 && (
                <div className="mt-6">
                  <p className="text-xs text-ink-500">¿Quizás alguno de estos?</p>
                  <div className="mt-2 flex flex-wrap justify-center gap-2">{suggestions.map((b) => <BibChip key={b.number} b={b} onClick={() => onSearch(b.number)} />)}</div>
                </div>
              )}
            </div>
          )}

          {sure.length > 0 && <VirtualGrid items={sure} renderItem={card} label="Coincidencias seguras" />}
          {unsure.length > 0 && (
            <section className="mt-10">
              <h3 className="text-sm font-medium">Por revisar <span className="text-ink-500">({unsure.length})</span></h3>
              <p className="mb-3 mt-0.5 text-xs text-ink-500">Lectura poco clara o número que difiere en un dígito. Ábrelas para confirmar o descartar.</p>
              <VirtualGrid items={unsure} renderItem={card} label="Coincidencias por revisar" />
            </section>
          )}
          {results?.length > 0 && <FaceSection q={q} stats={stats} onResults={setFaceResults} onEnabled={onRefresh} />}
          {faceOnly.length > 0 && (
            <section className="mt-4">
              <h3 className="text-sm font-medium">Por parecido facial <span className="text-ink-500">({faceOnly.length})</span></h3>
              <p className="mb-3 mt-0.5 text-xs text-ink-500">Fotos donde no se leyó el dorsal {q} pero aparece una cara parecida a las que has marcado.</p>
              <VirtualGrid items={faceOnly} renderItem={card} label="Coincidencias por cara" />
            </section>
          )}
        </>
      ) : (
        <>
          {index.length > 0 && <BibIndex index={index} onSearch={onSearch} />}
          <div className="mb-4 mt-2 flex flex-wrap items-center justify-between gap-3">
            <div className="flex gap-1.5 overflow-x-auto pb-1" role="tablist" aria-label="Filtrar fotos">
              {FILTERS.map(([id, label]) => {
                const n = { all: stats?.photos, with_bib: stats?.with_bib, no_bib: stats ? Math.max(0, (stats.ocr.done || 0) - (stats.with_bib || 0)) : undefined, pending, error: stats?.ocr?.error || 0 }[id]
                if ((id === 'pending' && !pending && filter !== 'pending') || (id === 'error' && !n && filter !== 'error')) return null
                return (
                  <button key={id} role="tab" aria-selected={filter === id} onClick={() => setFilter(id)}
                    className={`shrink-0 rounded-full px-3.5 py-1.5 text-sm transition ${filter === id ? 'bg-ink-100 text-ink-950' : 'text-ink-300 hover:bg-white/5'}`}>
                    {label}{n !== undefined && n !== null ? <span className={filter === id ? 'text-ink-500' : 'text-ink-500'}> {n}</span> : null}
                  </button>
                )
              })}
            </div>
            {filter === 'error' && (stats?.ocr?.error || 0) > 0 && (
              <button onClick={async () => { await api.process(); toast('Reintentando las fotos con error', 'ok'); onRefresh() }} className="text-sm underline">Reintentar todas</button>
            )}
          </div>
          {photos === null ? <SkeletonGrid grid={grid} /> : photos.length === 0 ? (
            <p className="mt-16 text-center text-sm text-ink-300">No hay fotos en este filtro.</p>
          ) : (
            <>
              <VirtualGrid items={photos} renderItem={card} label="Galería" onEndReached={photos.length < total ? loadMore : undefined}
                onRangeChange={onRange} />
              {photos.length < total && <div className="flex justify-center py-10 text-ink-500"><Loader2 className="animate-spin" size={20} aria-label="Cargando más fotos" /></div>}
            </>
          )}
        </>
      )}

      {selecting && (
        <div className="fixed inset-x-0 bottom-4 z-40 flex justify-center px-3 rf-fade">
          <div className="flex items-center gap-1 rounded-2xl border border-white/10 bg-ink-900/95 p-1.5 pl-4 text-sm shadow-2xl backdrop-blur" role="toolbar" aria-label="Acciones de la selección">
            <span className="mr-2 whitespace-nowrap font-medium">{selected.size} seleccionada{selected.size === 1 ? '' : 's'}</span>
            <button onClick={() => saveTo(selPhotos, q ? `dorsal-${q}` : '')} disabled={busy === 'save'} className="flex items-center gap-2 rounded-xl bg-accent px-3 py-2 font-medium text-ink-950 hover:brightness-110 disabled:opacity-60">
              {busy === 'save' ? <Loader2 size={15} className="animate-spin" aria-hidden /> : <FolderDown size={15} aria-hidden />}<span className="hidden sm:inline">Guardar en carpeta</span>
            </button>
            <button onClick={() => download(selPhotos)} disabled={busy === 'download'} className="flex items-center gap-2 rounded-xl px-3 py-2 text-ink-300 hover:bg-white/5 hover:text-white disabled:opacity-60" title="Descargar un ZIP">
              {busy === 'download' ? <Loader2 size={15} className="animate-spin" aria-hidden /> : <Download size={15} aria-hidden />}<span className="hidden sm:inline">ZIP</span>
            </button>
            <button onClick={removeSel} disabled={busy === 'delete'} className="rounded-xl p-2.5 text-ink-300 hover:bg-white/5 hover:text-red-300" aria-label="Quitar de RaceFinder" title="Quitar de RaceFinder"><Trash2 size={16} /></button>
            <button onClick={() => setSelected(new Set())} className="rounded-xl p-2.5 text-ink-300 hover:bg-white/5 hover:text-white" aria-label="Cancelar selección" title="Cancelar (Esc)"><X size={16} /></button>
          </div>
        </div>
      )}

      {open !== null && viewList.some((p) => p.id === open) && (
        <Lightbox photos={viewList} id={open} onClose={() => setOpen(null)} onNavigate={setOpen}
          selected={selected} onToggleSelect={(p) => toggle(p)}
          onChanged={reloadAll}
          onDelete={async (id) => {
            const idx = viewList.findIndex((p) => p.id === id)
            const next = viewList[idx + 1] ?? viewList[idx - 1]
            try { await api.remove(id); setViewList((l) => l.filter((p) => p.id !== id)); setOpen(next ? next.id : null); toast('Foto quitada', 'ok'); await reloadAll() } catch (e) { toast(e.message, 'error') }
          }} />
      )}
    </div>
  )
}

const Card = memo(function Card({ p, q, face, selected, selecting, style, onClick: click, onToggle: tog }) {
  const settled = useSettled()
  const onClick = (e) => click(p, e)
  const onToggle = (e) => tog(p, e)
  const ev = p.evidence ?? p.bibs ?? []
  const shownBibs = ev.slice(0, 3)
  const cropBib = q && p.match !== 'face' ? ev.find((b) => (b.kind ? true : b.number === q) && b.bbox?.[2] > 0) : null
  const faceInfo = p.face ?? face
  const analysing = p.ocr_status === 'pending' || p.ocr_status === 'processing'
  return (
    <li style={style} className="group overflow-hidden rounded-lg bg-ink-800">
      <button onClick={onClick} className="absolute inset-0 block w-full" aria-label={`${selecting ? (selected ? 'Quitar de la selección' : 'Añadir a la selección') : 'Abrir'} ${p.name}`}>
        <Thumb src={api.thumbUrl(p)} className={selected ? 'scale-[0.92] rounded-md' : 'group-hover:scale-[1.03]'} />
      </button>
      {selected && <div className="pointer-events-none absolute inset-0 rounded-lg ring-2 ring-inset ring-accent" />}
      <button onClick={onToggle} aria-pressed={selected} aria-label={selected ? `Quitar ${p.name} de la selección` : `Seleccionar ${p.name}`}
        className={`absolute left-2 top-2 grid h-6 w-6 place-items-center rounded-full border-2 transition ${selected ? 'border-accent bg-accent text-ink-950' : 'border-white/80 bg-black/30 text-transparent opacity-0 group-hover:opacity-100 focus-visible:opacity-100 [@media(hover:none)]:opacity-100'} ${selecting ? 'opacity-100' : ''}`}>
        <Check size={14} strokeWidth={3} />
      </button>
      {p.match === 'doubtful' && <span className="pointer-events-none absolute right-2 top-2 rounded-full bg-amber-400 px-2 py-0.5 text-[11px] font-semibold text-black">Revisar</span>}
      {p.match === 'similar' && <span className="pointer-events-none absolute right-2 top-2 rounded-full bg-sky-300 px-2 py-0.5 text-[11px] font-semibold text-black">Parecido</span>}
      {faceInfo && (p.match === 'face'
        ? <span className="pointer-events-none absolute right-2 top-2 rounded-full bg-violet-300 px-2 py-0.5 text-[11px] font-semibold text-black" title={`Similitud ${faceInfo.similarity} (no es una probabilidad)`}>Cara · parecido {faceInfo.strength}</span>
        : p.match === 'exact' && <span className="pointer-events-none absolute right-2 top-2 rounded-full bg-violet-300 px-2 py-0.5 text-[11px] font-semibold text-black" title="El dorsal y la cara coinciden">Dorsal + cara</span>)}
      {settled && p.match === 'face' && faceInfo && (
        <RetryImg src={api.faceCropUrl(faceInfo.face_id)} alt="Cara parecida" loading="lazy"
          className="pointer-events-none absolute bottom-2 right-2 h-14 w-14 rounded-md border border-white/70 object-cover shadow-lg" />
      )}
      {settled && cropBib && (
        <RetryImg src={api.cropUrl(cropBib.bib_id ?? cropBib.id)} alt={`Dorsal leído: ${cropBib.number}`} loading="lazy"
          className="pointer-events-none absolute bottom-2 right-2 h-12 max-w-[45%] rounded-md border border-white/70 object-cover shadow-lg sm:h-14" />
      )}
      <div className="pointer-events-none absolute inset-x-0 bottom-0 flex items-end gap-1 bg-gradient-to-t from-black/75 via-black/20 to-transparent p-2 pt-8">
        {analysing && <span className="flex items-center gap-1 text-[11px] text-white/80"><Loader2 size={11} className="animate-spin" aria-hidden /> Leyendo…</span>}
        {p.ocr_status === 'error' && <span className="flex items-center gap-1 text-[11px] text-red-300"><AlertCircle size={11} aria-hidden /> No se pudo leer</span>}
        {!cropBib && shownBibs.map((b, i) => (
          <span key={i} className="rounded bg-white/90 px-1.5 py-0.5 text-[11px] font-semibold tabular-nums text-black">{b.number}</span>
        ))}
      </div>
    </li>
  )
}, (a, b) => {
  // la foto es "la misma" si coinciden los datos que se pintan; el resto de props se compara siempre
  const sameP = a.p === b.p || (a.p.id === b.p.id && a.p.v === b.p.v && a.p.ocr_status === b.p.ocr_status && a.p.match === b.p.match &&
    JSON.stringify(a.p.bibs ?? a.p.evidence) === JSON.stringify(b.p.bibs ?? b.p.evidence) && JSON.stringify(a.p.face) === JSON.stringify(b.p.face))
  return sameP && JSON.stringify(a.face) === JSON.stringify(b.face) && a.selected === b.selected && a.selecting === b.selecting &&
    a.q === b.q && a.onClick === b.onClick && a.style?.top === b.style?.top && a.style?.left === b.style?.left && a.style?.width === b.style?.width
})

// Una tarjeta solo pide su imagen si sigue en pantalla un instante: al bajar deprisa por miles de fotos,
// las que pasan de largo no generan peticiones y las visibles no quedan en cola detrás de ellas.
function useSettled(ms = 120) {
  const [go, setGo] = useState(false)
  useEffect(() => { const t = setTimeout(() => setGo(true), ms); return () => clearTimeout(t) }, [ms])
  return go
}

function Thumb({ src, className }) {
  const go = useSettled()
  const [ok, setOk] = useState(false)
  // si la imagen ya estaba en caché, 'load' puede dispararse antes de que React escuche: se comprueba 'complete'
  const ref = useCallback((el) => { if (el?.complete && el.naturalWidth) setOk(true) }, [])
  if (!go) return null
  return (
    <RetryImg ref={ref} src={src} alt="" loading="lazy" decoding="async" draggable={false} onLoad={() => setOk(true)}
      className={`h-full w-full object-cover transition duration-300 ${ok ? 'opacity-100' : 'opacity-0'} ${className}`} />
  )
}

function BibIndex({ index, onSearch }) {
  const [all, setAll] = useState(false)
  const top = all ? index : index.slice(0, 24)
  return (
    <section className="mb-6" aria-label="Dorsales encontrados">
      <div className="mb-2 flex items-baseline justify-between">
        <h2 className="flex items-center gap-1.5 text-sm font-medium text-ink-300"><Hash size={14} aria-hidden /> Dorsales encontrados <span className="text-ink-500">({index.length})</span></h2>
        {index.length > 24 && <button onClick={() => setAll(!all)} className="flex items-center gap-1 text-xs text-ink-300 hover:text-white">{all ? <>Ver menos <ChevronUp size={13} /></> : <>Ver todos <ChevronDown size={13} /></>}</button>}
      </div>
      <div className={`flex gap-1.5 ${all ? 'flex-wrap' : 'overflow-x-auto pb-1 [scrollbar-width:thin]'}`}>
        {top.map((b) => <BibChip key={b.number} b={b} onClick={() => onSearch(b.number)} />)}
      </div>
    </section>
  )
}

const BibChip = ({ b, onClick }) => (
  <button onClick={onClick} className="shrink-0 rounded-lg border border-white/10 bg-ink-900 px-2.5 py-1 text-sm tabular-nums hover:border-accent/60 hover:text-white" title={`${b.photos} foto(s)`}>
    {b.number}<span className="ml-1.5 text-xs text-ink-500">{b.photos}</span>
  </button>
)

const SkeletonGrid = ({ grid }) => (
  <div className={grid} aria-hidden>{Array.from({ length: 12 }, (_, i) => <div key={i} className="rf-skeleton aspect-[3/2] rounded-lg" />)}</div>
)

function Empty({ onPickFiles, onPickFolder }) {
  return (
    <div className="grid flex-1 place-items-center px-4 py-16">
      <div className="w-full max-w-2xl rounded-3xl border-2 border-dashed border-white/10 px-6 py-16 text-center rf-fade">
        <ImagePlus size={44} className="mx-auto text-accent" aria-hidden />
        <h2 className="mt-5 text-2xl font-semibold sm:text-3xl">Encuentra tus fotos de la carrera</h2>
        <p className="mx-auto mt-3 max-w-md text-ink-300">Arrastra aquí la carpeta con las fotos del evento. RaceFinder lee los dorsales automáticamente y podrás buscar el tuyo en segundos.</p>
        <div className="mt-8 flex flex-wrap justify-center gap-3">
          <button onClick={onPickFolder} className="flex items-center gap-2 rounded-xl bg-accent px-5 py-3 font-medium text-ink-950 hover:brightness-110"><FolderOpen size={18} aria-hidden /> Elegir carpeta</button>
          <button onClick={onPickFiles} className="flex items-center gap-2 rounded-xl border border-white/10 px-5 py-3 hover:bg-white/5"><ImagePlus size={18} aria-hidden /> Elegir fotos</button>
        </div>
        <p className="mt-8 text-xs text-ink-500">JPG, PNG o WebP · Todo se procesa en tu equipo: ninguna foto sale a internet · Los originales no se modifican</p>
      </div>
    </div>
  )
}
