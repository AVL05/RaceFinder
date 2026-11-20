import { memo, useCallback, useEffect, useMemo, useRef, useState } from 'react'
import { Check, Download, FolderDown, Trash2, X, Loader2, ImagePlus, FolderOpen, FolderPlus, Hash, AlertCircle, SearchX, ChevronDown, ChevronUp, ShieldCheck, Images, FileCheck2, ArrowLeft, Star, Search, ListChecks } from 'lucide-react'
import { api, downloadPhotos, isOffline } from './api.js'
import Lightbox from './Lightbox.jsx'
import { FaceSection } from './Faces.jsx'
import { useToast } from './Toast.jsx'
import RetryImg from './RetryImg.jsx'
import VirtualGrid from './VirtualGrid.jsx'
import { AlbumAssignment } from './AlbumControls.jsx'

const PAGE = 120
const PLACEHOLDERS = Array.from({ length: 12 }, (_, i) => i)
const plural = (n, one, many) => `${n} ${n === 1 ? one : many}`
const FILTERS = [['all', 'Todas'], ['with_bib', 'Con dorsal'], ['no_bib', 'Sin dorsal leído'], ['favorites', 'Favoritas'], ['review', 'Por revisar'], ['pending', 'Por analizar'], ['error', 'Con error']]

function similarTo(a, b) {
  if (a === b || Math.abs(a.length - b.length) > 1) return false
  if (a.length === b.length) return [...a].filter((x, i) => x !== b[i]).length === 1
  const [s, l] = a.length < b.length ? [a, b] : [b, a]
  return [...l].some((_, i) => l.slice(0, i) + l.slice(i + 1) === s)
}

export default function Library({ album, albums, q, similar, setSimilar, stats: globalStats, version, onSearch, onRefresh, onPickFiles, onPickFolder }) {
  const toast = useToast()
  const albumId = album?.id
  const [albumStats, setAlbumStats] = useState(null)
  const [filter, setFilter] = useState('all')
  const [filenameDraft, setFilenameDraft] = useState('')
  const [filename, setFilename] = useState('')
  const [sort, setSort] = useState('recent')
  const [photos, setPhotos] = useState(null)
  const [total, setTotal] = useState(0)
  const [searchResult, setSearchResult] = useState(null)
  const [faceResults, setFaceResults] = useState(null)
  const [searching, setSearching] = useState(false)
  const [index, setIndex] = useState([])
  const [selected, setSelected] = useState(() => new Map())
  const [albumDialog, setAlbumDialog] = useState(false)
  const [open, setOpen] = useState(null)
  // lista congelada del visor: si una revisión saca la foto de los resultados, el visor sigue mostrándola
  const [viewList, setViewList] = useState([])
  const [busy, setBusy] = useState('')
  const anchor = useRef(null)
  const heading = useRef(null)
  const focusHeading = useRef(false)
  const searchRequest = useRef(0)
  const browseRequest = useRef(0)
  const loadingMore = useRef(null)
  const favoritePending = useRef(new Set())
  const photosRef = useRef(photos)
  photosRef.current = photos
  const query = useMemo(() => ({ album: albumId, filter, filename, sort }), [albumId, filter, filename, sort])
  const currentQuery = useRef(query)
  currentQuery.current = query
  const currentBib = useRef(q)
  currentBib.current = q
  const lastBrowseQuery = useRef(null)
  const stats = albumId ? albumStats : globalStats

  useEffect(() => {
    const timer = setTimeout(() => setFilename(filenameDraft.trim()), 220)
    return () => clearTimeout(timer)
  }, [filenameDraft])

  // ---------- datos ----------
  // tramo de la galería que se está viendo (lo informa la rejilla virtualizada)
  const visible = useRef([0, PAGE])
  const totalRef = useRef(0)
  totalRef.current = total
  const loadBrowse = useCallback(async (reset) => {
    const request = ++browseRequest.current
    const isCurrent = () => query === currentQuery.current && request === browseRequest.current
    try {
      const cur = photosRef.current
      if (reset || !cur || query.filter !== 'all' || query.filename || query.sort !== 'recent') {
        // filtros: las fotos entran y salen del filtro, se recarga desde arriba lo ya cargado (máx. 1000)
        const keep = reset || !cur ? PAGE : Math.min(1000, Math.max(PAGE, cur.length))
        const r = await api.photos(keep, 0, query)
        if (isCurrent()) { setPhotos(r.photos); setTotal(r.total) }
        return
      }
      // "Todas" con miles de fotos: solo se refresca el tramo visible y se conserva el resto de la lista
      const [a, b] = visible.current
      const offset = Math.max(0, a - 40), limit = Math.min(1000, Math.max(PAGE, b - a + 80))
      const r = await api.photos(limit, offset, query)
      let next = cur
      if (r.total !== totalRef.current) {  // fotos añadidas o quitadas: las nuevas van arriba
        const top = offset === 0 ? r : await api.photos(PAGE, 0, query)
        const ids = new Set(top.photos.map((p) => p.id))
        next = [...top.photos, ...cur.filter((p) => !ids.has(p.id))]
        if (r.total < totalRef.current) {   // borradas: se quitan las que ya no existen en el tramo consultado
          const seen = new Set(r.photos.map((p) => p.id))
          next = next.filter((p, i) => i < offset || i >= offset + limit || seen.has(p.id))
        }
      }
      const byId = new Map(r.photos.map((p) => [p.id, p]))
      if (isCurrent()) { setPhotos(next.map((p) => byId.get(p.id) ?? p)); setTotal(r.total) }
    } catch (e) { if (isCurrent() && !isOffline(e)) { setPhotos((p) => p ?? []); toast(e.message, 'error') } }
  }, [query, toast])

  const loadMore = useCallback(async () => {
    const cur = photosRef.current
    if (!cur || loadingMore.current === query || cur.length >= total) return
    loadingMore.current = query
    try {
      const r = await api.photos(PAGE, cur.length, query)
      if (query !== currentQuery.current) return
      setPhotos((old) => { const ids = new Set(old.map((x) => x.id)); return [...old, ...r.photos.filter((x) => !ids.has(x.id))] })
      setTotal(r.total)
    } catch { /* se reintenta al volver a hacer scroll */ }
    finally { if (loadingMore.current === query) loadingMore.current = null }
  }, [total, query])

  const loadSearch = useCallback(async () => {
    const request = ++searchRequest.current
    if (!q) { setSearchResult(null); setSearching(false); return }
    setSearching(true)
    try {
      const { results: matches } = await api.search(q, similar, albumId)
      if (request === searchRequest.current) setSearchResult({ q, matches })
    } catch (e) {
      if (request === searchRequest.current && !isOffline(e)) {
        toast(e.message, 'error')
        setSearchResult({ q, matches: [] })
      }
    } finally {
      if (request === searchRequest.current) setSearching(false)
    }
  }, [q, similar, albumId, toast])

  const loadIndex = useCallback(async () => { try { setIndex((await api.bibIndex(400, albumId)).bibs) } catch { /* no crítico */ } }, [albumId])
  const loadAlbumStats = useCallback(async () => {
    if (albumId) {
      try { setAlbumStats(await api.stats(albumId)) } catch { /* el estado general muestra la conexión */ }
    }
  }, [albumId])

  useEffect(() => {
    const reset = lastBrowseQuery.current !== query
    lastBrowseQuery.current = query
    if (reset) { setPhotos(null); setTotal(0); visible.current = [0, PAGE] }
    loadBrowse(reset)
  }, [query, loadBrowse, version])
  useEffect(() => { loadIndex(); loadAlbumStats() }, [loadIndex, loadAlbumStats, version])
  useEffect(() => { loadSearch() }, [loadSearch, version])
  useEffect(() => { setSelected(new Map()); setAlbumDialog(false); anchor.current = null }, [q, query])
  useEffect(() => { setFaceResults(null) }, [q])
  useEffect(() => {
    if (!focusHeading.current) return
    focusHeading.current = false
    heading.current?.focus({ preventScroll: true })
  }, [q])

  const goToBib = (number) => {
    focusHeading.current = true
    onSearch(number)
  }


  const reloadAll = useCallback(async () => {
    await Promise.all([loadBrowse(false), loadSearch(), loadIndex(), loadAlbumStats(), onRefresh()])
  }, [loadBrowse, loadSearch, loadIndex, loadAlbumStats, onRefresh])

  // ---------- lista visible y selección ----------
  const results = searchResult?.q === q ? searchResult.matches : null
  const sure = useMemo(() => results?.filter((p) => p.match === 'exact') ?? [], [results])
  const unsure = useMemo(() => results?.filter((p) => p.match !== 'exact') ?? [], [results])
  const bibIds = useMemo(() => new Set((results ?? []).map((p) => p.id)), [results])
  const faceById = useMemo(() => new Map((faceResults ?? []).map((p) => [p.id, p.face])), [faceResults])
  // solo por la cara: fotos que el dorsal no encontró (dorsal tapado, de lado, ilegible…)
  const faceOnly = useMemo(() => results?.length
    ? (faceResults ?? []).filter((p) => !bibIds.has(p.id)).map((p) => ({ ...p, match: 'face' }))
    : [], [results, faceResults, bibIds])
  const shown = useMemo(() => (q ? [...sure, ...unsure, ...faceOnly] : photos ?? []), [q, sure, unsure, faceOnly, photos])
  const selecting = selected.size > 0

  const toggle = (p, e) => {
    const idx = shown.findIndex((x) => x.id === p.id)
    setSelected((s) => {
      const n = new Map(s)
      if (e?.shiftKey && anchor.current !== null) {
        const a = shown.findIndex((x) => x.id === anchor.current)
        if (a >= 0 && idx >= 0) {
          shown.slice(Math.min(a, idx), Math.max(a, idx) + 1).forEach((x) => n.set(x.id, x))
          return n
        }
      }
      if (n.has(p.id)) n.delete(p.id)
      else n.set(p.id, p)
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
    const k = (e) => { if (e.key === 'Escape' && !open && selecting && !document.querySelector('dialog[open]')) setSelected(new Map()) }
    window.addEventListener('keydown', k)
    return () => window.removeEventListener('keydown', k)
  }, [open, selecting])

  const selPhotos = [...selected.values()]
  const selectCatalog = async () => {
    setBusy('select')
    try {
      const { photos: catalog } = await api.selection(query)
      if (query === currentQuery.current && !currentBib.current) setSelected(new Map(catalog.map((p) => [p.id, p])))
    } catch (e) { toast(e.message, 'error') } finally { setBusy('') }
  }
  const favoritePhotos = async (ids, favorite) => {
    if (ids.some((id) => favoritePending.current.has(id))) return
    ids.forEach((id) => favoritePending.current.add(id))
    try {
      await api.setFavorites(ids, favorite)
      const changed = new Set(ids)
      const update = (p) => changed.has(p.id) ? { ...p, favorite } : p
      setSelected((prev) => new Map([...prev.values()].map((p) => [p.id, update(p)])))
      setViewList((prev) => prev.map(update))
      setFaceResults((prev) => prev?.map(update) ?? null)
      await reloadAll()
    } catch (e) { toast(e.message, 'error') }
    finally { ids.forEach((id) => favoritePending.current.delete(id)) }
  }
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
    try { await api.removeMany([...selected.keys()]); setSelected(new Map()); toast('Fotos quitadas', 'ok'); await reloadAll() }
    catch (e) { toast(e.message, 'error') } finally { setBusy('') }
  }

  // ---------- render ----------
  // todos los hooks van antes de este return anticipado (React exige el mismo orden en cada render)
  const onRange = useCallback((a, b) => { visible.current = [a, b] }, [])
  const handlers = useRef({})
  handlers.current = { onCard, toggle, favoritePhotos }
  const cardClick = useCallback((p, e) => handlers.current.onCard(p, e), [])
  const cardToggle = useCallback((p, e) => handlers.current.toggle(p, e), [])
  const cardFavorite = useCallback((p) => handlers.current.favoritePhotos([p.id], !p.favorite), [])
  if (stats && stats.photos === 0 && !albumId) return <Empty onPickFiles={onPickFiles} onPickFolder={onPickFolder} />

  // los manejadores leen el estado más reciente desde una ref: así las tarjetas memorizadas no se repintan sin motivo
  const card = (p, style) => <Card key={p.id} p={p} q={q} face={faceById.get(p.id)} selected={selected.has(p.id)} selecting={selecting} style={style} onClick={cardClick} onToggle={cardToggle} onFavorite={cardFavorite} />
  const pending = (stats?.ocr?.pending || 0) + (stats?.ocr?.processing || 0)
  const suggestions = q && results?.length === 0 ? index.filter((b) => similarTo(q, b.number)).slice(0, 8) : []
  const counts = { all: stats?.photos, with_bib: stats?.with_bib, no_bib: stats ? Math.max(0, (stats.ocr.done || 0) - stats.with_bib) : undefined,
    favorites: stats?.favorites, review: stats?.needs_review, pending, error: stats?.ocr?.error || 0 }
  const filters = FILTERS.filter(([id]) => (id !== 'pending' && id !== 'error') || counts[id] > 0 || id === filter)
  const moveFilter = (e) => {
    const current = filters.findIndex(([id]) => id === filter)
    const targets = { ArrowLeft: (current - 1 + filters.length) % filters.length, ArrowRight: (current + 1) % filters.length, Home: 0, End: filters.length - 1 }
    if (!Object.hasOwn(targets, e.key)) return
    e.preventDefault()
    const [next] = filters[targets[e.key]]
    setFilter(next)
    document.getElementById(`filter-${next}`)?.focus()
  }

  return (
    <div className="rf-container rf-workspace">
      {q ? (
        <>
          <button onClick={() => goToBib('')} className="rf-button rf-button-quiet mb-3"><ArrowLeft size={16} aria-hidden /> {albumId ? 'Volver al álbum' : 'Biblioteca'}</button>
          <div className="rf-result-header">
            <div key={q} className="rf-result-identity rf-fade">
              <h1 ref={heading} tabIndex={-1} className="rf-result-bib">
                <span className="rf-kicker">Dorsal</span>
                <span className="rf-bib-number">{q}</span>
              </h1>
              <div className="min-w-0" role="status">
                <p className="rf-result-title">Resultados</p>
                {results && <p className="mt-1 text-sm text-ink-300">{results.length === 0 ? 'Ninguna foto' : `${plural(sure.length, 'foto', 'fotos')}${unsure.length ? ` · ${unsure.length} por revisar` : ''}`}{faceOnly.length ? ` · ${faceOnly.length} más por la cara` : ''}{pending ? ` · ${pending === 1 ? 'queda 1 foto' : `quedan ${pending} fotos`} por analizar` : ''}</p>}
                {searching && <span className="mt-1 flex items-center gap-2 text-sm text-ink-300"><Loader2 size={14} className="animate-spin" aria-hidden /> Buscando…</span>}
              </div>
            </div>
            <div className="rf-result-actions">
              <div className="rf-result-action-group">
                <label className="rf-button rf-button-quiet cursor-pointer">
                  <input type="checkbox" className="accent-[var(--color-accent)]" checked={similar} onChange={(e) => setSimilar(e.target.checked)} />
                  Números parecidos
                </label>
                {shown.length > 0 && <button onClick={() => setSelected(new Map(shown.map((p) => [p.id, p])))} className="rf-button rf-button-quiet">Seleccionar todas</button>}
              </div>
              {shown.length > 0 && (
                <div className="rf-result-action-group">
                  <button onClick={() => saveTo(sure.length ? sure : shown, `dorsal-${q}`)} disabled={busy === 'save'} className="rf-button rf-button-primary"
                    title="Copia los originales a una carpeta de tu disco, en una subcarpeta con el dorsal">
                    {busy === 'save' ? <Loader2 size={15} className="animate-spin" aria-hidden /> : <FolderDown size={15} aria-hidden />}
                    Guardar {plural(sure.length || shown.length, 'foto', 'fotos')}
                  </button>
                  <button onClick={() => download(sure.length ? sure : shown)} disabled={busy === 'download'} className="rf-button rf-button-quiet" title="Descargar con el navegador">
                    {busy === 'download' ? <Loader2 size={15} className="animate-spin" aria-hidden /> : <Download size={15} aria-hidden />}
                    {(sure.length || shown.length) === 1 ? 'Descargar original' : 'ZIP'}
                  </button>
                </div>
              )}
            </div>
          </div>

          {results === null && <SkeletonGrid />}

          {results?.length === 0 && (
            <section className="rf-empty-results rf-fade">
              <SearchX size={32} className="mx-auto text-accent" aria-hidden />
              <h2 className="mt-3 text-lg font-semibold">No hay fotos con el dorsal {q}</h2>
              <p className="mt-1 text-sm text-ink-300">
                {pending ? 'Todavía se están analizando fotos: los resultados aparecerán solos.' : similar ? 'Tampoco hay números parecidos. Puede que el dorsal no se vea bien en las fotos.' : 'Prueba a incluir números parecidos: el lector puede haber confundido un dígito.'}
              </p>
              {!similar && <button onClick={() => setSimilar(true)} className="rf-button rf-button-primary mt-4">Buscar números parecidos</button>}
              {suggestions.length > 0 && (
                <div className="mt-6">
                  <p className="text-xs text-ink-500">¿Quizás alguno de estos?</p>
                  <div className="mt-2 flex flex-wrap justify-center gap-2">{suggestions.map((b) => <BibChip key={b.number} b={b} onClick={() => goToBib(b.number)} />)}</div>
                </div>
              )}
            </section>
          )}

          {sure.length > 0 && (
            <section>
              <h2 className="rf-section-heading mb-3">Coincidencias seguras</h2>
              <VirtualGrid items={sure} renderItem={card} label="Coincidencias seguras" />
            </section>
          )}
          {unsure.length > 0 && (
            <section className="mt-10">
              <h2 className="rf-section-heading">Por revisar <span className="text-ink-500">({unsure.length})</span></h2>
              <p className="mb-3 mt-0.5 text-xs text-ink-500">Lectura poco clara o número que difiere en un dígito. Ábrelas para confirmar o descartar.</p>
              <VirtualGrid items={unsure} renderItem={card} label="Coincidencias por revisar" />
            </section>
          )}
          {results?.length > 0 && <FaceSection q={q} album={albumId} stats={stats ?? globalStats} onResults={setFaceResults} onEnabled={reloadAll} />}
          {faceOnly.length > 0 && (
            <section className="mt-4">
              <h2 className="rf-section-heading">Por parecido facial <span className="text-ink-500">({faceOnly.length})</span></h2>
              <p className="mb-3 mt-0.5 text-xs text-ink-500">Fotos donde no se leyó el dorsal {q} pero aparece una cara parecida a las que has marcado.</p>
              <VirtualGrid items={faceOnly} renderItem={card} label="Coincidencias por cara" />
            </section>
          )}
        </>
      ) : (
        <>
          <h1 ref={heading} tabIndex={-1} className="rf-workspace-title">{album?.name ?? 'Biblioteca'}</h1>
          {index.length > 0 && <BibIndex index={index} onSearch={goToBib} />}
          <div className="rf-catalog-tools">
            <div className="rf-filename-search">
              <Search size={17} className="text-accent" aria-hidden />
              <input aria-label="Buscar por nombre de archivo" type="search" maxLength={200} value={filenameDraft}
                onChange={(e) => setFilenameDraft(e.target.value)} placeholder="Nombre de archivo" className="rf-catalog-input" />
            </div>
            <label className="flex items-center gap-2 text-sm text-ink-300">
              <span className="sr-only sm:not-sr-only">Orden</span>
              <select value={sort} onChange={(e) => setSort(e.target.value)} className="rf-catalog-input">
                <option value="recent">Más recientes</option>
                <option value="oldest">Más antiguas</option>
                <option value="name">Archivo A–Z</option>
                <option value="name_desc">Archivo Z–A</option>
              </select>
            </label>
          </div>
          <div className="rf-gallery-toolbar">
            <div className="rf-filter-list" role="tablist" aria-label="Filtrar fotos" onKeyDown={moveFilter}>
              {filters.map(([id, label]) => (
                <button key={id} id={`filter-${id}`} role="tab" aria-selected={filter === id} aria-controls="photo-panel"
                  tabIndex={filter === id ? 0 : -1} onClick={() => setFilter(id)} className="rf-filter">
                  {label}{counts[id] != null && <> <span>{counts[id]}</span></>}
                </button>
              ))}
            </div>
            {filter === 'error' && (stats?.ocr?.error || 0) > 0 && (
              <button onClick={async () => { await api.process(); toast('Reintentando las fotos con error', 'ok'); onRefresh() }} className="text-sm underline">Reintentar todas</button>
            )}
          </div>
          {filter === 'review' && <p className="mb-3 text-sm text-ink-300">Abre una foto para confirmar o descartar los dorsales con lectura dudosa.</p>}
          {total > 0 && (
            <div className="mb-3 flex flex-wrap items-center gap-2">
              <span className="mr-auto text-sm tabular-nums text-ink-300" role="status">{plural(total, 'foto', 'fotos')}</span>
              <button onClick={selectCatalog} disabled={busy === 'select' || !!selected.size} className="rf-button rf-button-quiet">
                {busy === 'select' ? <Loader2 size={16} className="animate-spin" aria-hidden /> : <ListChecks size={16} aria-hidden />}
                Seleccionar todas
              </button>
              <a href={api.catalogCsv(query)} download className="rf-button rf-button-quiet" aria-label="Catálogo CSV">
                <Download size={16} aria-hidden /><span className="hidden sm:inline">Catálogo</span> CSV
              </a>
            </div>
          )}
          <div id="photo-panel" role="tabpanel" aria-labelledby={`filter-${filter}`} aria-busy={photos === null}>
            {photos === null ? <SkeletonGrid /> : photos.length === 0 ? (
              albumId && album.photos === 0 ? (
                <div className="rf-empty-results">
                  <FolderOpen size={30} className="mx-auto text-accent" aria-hidden />
                  <h2 className="mt-3 text-lg font-semibold">Álbum vacío</h2>
                  <p className="mt-1 text-sm text-ink-300">Importa fotos aquí o selecciona fotos de la biblioteca y añádelas a este álbum.</p>
                  <div className="mt-4 flex flex-wrap justify-center gap-2">
                    <button onClick={onPickFolder} className="rf-button rf-button-primary"><FolderOpen size={17} aria-hidden /> Elegir carpeta</button>
                    <button onClick={onPickFiles} className="rf-button rf-button-quiet"><ImagePlus size={17} aria-hidden /> Elegir fotos</button>
                  </div>
                </div>
              ) : (
                <div className="rf-empty-results text-ink-300">
                  <p>{filename ? `No hay archivos que coincidan con «${filename}».` : filter === 'review' ? 'No hay dorsales dudosos pendientes de revisar.' : filter === 'favorites' ? 'Marca una foto con la estrella para tenerla aquí.' : 'No hay fotos en este filtro.'}</p>
                  {filename && <button className="rf-button rf-button-quiet mt-3" onClick={() => setFilenameDraft('')}>Borrar búsqueda de archivos</button>}
                </div>
              )
            ) : (
              <>
                <VirtualGrid items={photos} renderItem={card} label="Galería" onEndReached={photos.length < total ? loadMore : undefined}
                  onRangeChange={onRange} />
                {photos.length < total && <div className="flex justify-center py-10 text-ink-500"><Loader2 className="animate-spin" size={20} aria-label="Cargando más fotos" /></div>}
              </>
            )}
          </div>
        </>
      )}

      {selecting && (
        <div className="pointer-events-none fixed inset-x-0 bottom-4 z-40 flex justify-center px-3 rf-fade">
          <div className="rf-selection" role="group" aria-label="Acciones de la selección">
            <span role="status" className="rf-selection-count">{selected.size} seleccionada{selected.size === 1 ? '' : 's'}</span>
            <button onClick={() => saveTo(selPhotos, q ? `dorsal-${q}` : '')} disabled={busy === 'save'} className="rf-button rf-button-primary" aria-label="Guardar selección en carpeta">
              {busy === 'save' ? <Loader2 size={15} className="animate-spin" aria-hidden /> : <FolderDown size={15} aria-hidden />}<span className="hidden sm:inline">Guardar en carpeta</span>
            </button>
            <button onClick={() => download(selPhotos)} disabled={busy === 'download'} className="rf-button rf-button-quiet" aria-label="Descargar selección" title="Descargar selección">
              {busy === 'download' ? <Loader2 size={15} className="animate-spin" aria-hidden /> : <Download size={15} aria-hidden />}<span className="hidden sm:inline">ZIP</span>
            </button>
            <button onClick={() => setAlbumDialog(true)} className="rf-button rf-button-quiet" aria-label="Organizar selección en álbumes" title="Organizar en álbumes"><FolderPlus size={17} aria-hidden /></button>
            <button onClick={() => favoritePhotos([...selected.keys()], !selPhotos.every((p) => p.favorite))} className="rf-button rf-button-quiet"
              aria-label={selPhotos.every((p) => p.favorite) ? 'Quitar selección de favoritas' : 'Marcar selección como favorita'}
              title={selPhotos.every((p) => p.favorite) ? 'Quitar selección de favoritas' : 'Marcar selección como favorita'}>
              <Star size={17} className={selPhotos.every((p) => p.favorite) ? 'fill-current text-accent' : ''} aria-hidden />
            </button>
            <button onClick={removeSel} disabled={busy === 'delete'} className="rf-button rf-button-quiet hover:text-red-300" aria-label="Quitar de RaceFinder" title="Quitar de RaceFinder"><Trash2 size={16} aria-hidden /></button>
            <button onClick={() => setSelected(new Map())} className="rf-button rf-button-quiet" aria-label="Cancelar selección" title="Cancelar (Esc)"><X size={16} aria-hidden /></button>
          </div>
        </div>
      )}
      {albumDialog && selecting && <AlbumAssignment
        albums={albums} current={album} ids={[...selected.keys()]} onClose={() => setAlbumDialog(false)}
        onChanged={async (action) => { if (action === 'remove') setSelected(new Map()); await reloadAll() }}
      />}

      {open !== null && viewList.some((p) => p.id === open) && (
        <Lightbox photos={viewList} id={open} album={albumId} onClose={() => setOpen(null)} onNavigate={setOpen}
          selected={selected} onToggleSelect={(p) => toggle(p)}
          onToggleFavorite={(p) => favoritePhotos([p.id], !p.favorite)}
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

const Card = memo(function Card({ p, q, face, selected, selecting, style, onClick: click, onToggle: tog, onFavorite }) {
  const settled = useSettled()
  const onClick = (e) => click(p, e)
  const onToggle = (e) => tog(p, e)
  const ev = p.evidence ?? p.bibs ?? []
  const shownBibs = ev.slice(0, 3)
  const cropBib = q && p.match !== 'face' ? ev.find((b) => (b.kind ? true : b.number === q) && b.bbox?.[2] > 0) : null
  const faceInfo = p.face ?? face
  const analysing = p.ocr_status === 'pending' || p.ocr_status === 'processing'
  return (
    <li style={style} className="rf-photo group">
      <button onClick={onClick} className="rf-photo-open" aria-label={`${selecting ? (selected ? 'Quitar de la selección' : 'Añadir a la selección') : 'Abrir'} ${p.name}`}>
        <Thumb src={api.thumbUrl(p)} className={selected ? 'scale-[0.92] rounded-md' : 'group-hover:scale-[1.03]'} />
      </button>
      {selected && <div className="pointer-events-none absolute inset-0 rounded-lg ring-2 ring-inset ring-accent" />}
      <button onClick={onToggle} aria-pressed={selected} aria-label={selected ? `Quitar ${p.name} de la selección` : `Seleccionar ${p.name}`}
        className="rf-photo-select">
        {selected && <Check size={16} strokeWidth={3} aria-hidden />}
      </button>
      <button onClick={() => onFavorite(p)} aria-label={p.favorite ? `Quitar ${p.name} de favoritas` : `Marcar ${p.name} como favorita`}
        aria-pressed={Boolean(p.favorite)} className="rf-photo-favorite" title={p.favorite ? 'Quitar de favoritas' : 'Marcar como favorita'}>
        <Star size={16} className={p.favorite ? 'fill-current' : ''} aria-hidden />
      </button>
      {settled && p.match === 'face' && faceInfo && (
        <RetryImg src={api.faceCropUrl(faceInfo.face_id)} alt="Cara parecida" loading="lazy"
          className="pointer-events-none absolute bottom-2 right-2 z-1 h-14 w-14 rounded-md border border-white/70 object-cover shadow-lg" />
      )}
      {settled && cropBib && (
        <RetryImg src={api.cropUrl(cropBib.bib_id ?? cropBib.id)} alt={`Dorsal leído: ${cropBib.number}`} loading="lazy"
          className="pointer-events-none absolute bottom-2 right-2 z-1 h-12 max-w-[45%] rounded-md border border-white/70 object-cover shadow-lg sm:h-14" />
      )}
      <div className="pointer-events-none absolute inset-x-0 bottom-0 flex flex-wrap items-end gap-1 bg-gradient-to-t from-black/75 via-black/20 to-transparent p-2 pt-8">
        {p.match === 'doubtful' && <span className="rf-photo-status bg-amber-400">Revisar</span>}
        {p.match === 'similar' && <span className="rf-photo-status bg-sky-300">Parecido</span>}
        {faceInfo && (p.match === 'face'
          ? <span className="rf-photo-status bg-violet-300" title={`Similitud ${faceInfo.similarity}`}>Cara<span className="hidden sm:inline"> · parecido {faceInfo.strength}</span></span>
          : p.match === 'exact' && <span className="rf-photo-status bg-violet-300" title="El dorsal y la cara coinciden">Dorsal + cara</span>)}
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
    a.p.favorite === b.p.favorite &&
    JSON.stringify(a.p.bibs ?? a.p.evidence) === JSON.stringify(b.p.bibs ?? b.p.evidence) && JSON.stringify(a.p.face) === JSON.stringify(b.p.face))
  return sameP && JSON.stringify(a.face) === JSON.stringify(b.face) && a.selected === b.selected && a.selecting === b.selecting &&
    a.q === b.q && a.onClick === b.onClick && a.onFavorite === b.onFavorite &&
    a.style?.top === b.style?.top && a.style?.left === b.style?.left && a.style?.width === b.style?.width
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
    <section className="rf-bib-index" aria-label="Dorsales encontrados">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <h2 className="rf-section-heading flex items-center gap-2"><Hash size={17} className="text-accent" aria-hidden /> Dorsales encontrados <span className="text-ink-500">({index.length})</span></h2>
        {index.length > 24 && <button onClick={() => setAll(!all)} aria-expanded={all} aria-controls="bib-list" className="rf-button rf-button-quiet">{all ? <>Ver menos <ChevronUp size={14} aria-hidden /></> : <>Ver todos <ChevronDown size={14} aria-hidden /></>}</button>}
      </div>
      <div id="bib-list" className={`rf-bib-list ${all ? 'flex-wrap' : 'overflow-x-auto'}`}>
        {top.map((b) => <BibChip key={b.number} b={b} onClick={() => onSearch(b.number)} />)}
      </div>
    </section>
  )
}

const BibChip = ({ b, onClick }) => (
  <button onClick={onClick} className="rf-bib-chip" aria-label={`Dorsal ${b.number}, ${plural(b.photos, 'foto', 'fotos')}`}>
    {b.number}<span>{b.photos}</span>
  </button>
)

const SkeletonGrid = () => (
  <div aria-hidden="true">
    <VirtualGrid items={PLACEHOLDERS} renderItem={(i, style) => <li key={i} style={style} className="rf-skeleton rounded-lg" />} />
  </div>
)

function Empty({ onPickFiles, onPickFolder }) {
  return (
    <div className="rf-container rf-welcome">
      <section className="rf-welcome-panel" aria-labelledby="welcome-title">
        <div className="rf-welcome-content">
          <p className="rf-kicker"><span className="rf-state-dot" aria-hidden /> Biblioteca vacía</p>
          <h1 id="welcome-title">Encuentra tus fotos de la carrera</h1>
          <p className="rf-welcome-description">Importa las fotos del evento y escribe tu número de dorsal. RaceFinder lee los dorsales de las fotos y reúne las coincidencias.</p>
          <div className="rf-welcome-actions">
            <button onClick={onPickFolder} className="rf-button rf-button-primary"><FolderOpen size={19} aria-hidden /> Elegir carpeta</button>
            <button onClick={onPickFiles} className="rf-button rf-button-quiet"><ImagePlus size={19} aria-hidden /> Elegir fotos</button>
          </div>
          <p className="rf-drop-hint">También puedes arrastrar aquí las fotos o la carpeta.</p>
        </div>
        <figure className="rf-example">
          <img src="/dorsal-ejemplo-720.webp" srcSet="/dorsal-ejemplo-720.webp 720w, /dorsal-ejemplo-1280.webp 1280w"
            sizes="(min-width: 1600px) 800px, (min-width: 880px) 51vw, 96vw" width="1280" height="960"
            fetchPriority="high" alt="Corredora con el dorsal 184 sujeto a la camiseta" />
          <span className="rf-example-scan" aria-hidden><span>Dorsal</span></span>
          <figcaption>Foto de ejemplo</figcaption>
        </figure>
      </section>
      <ul className="rf-welcome-facts">
        <li><ShieldCheck size={22} aria-hidden /><span><strong>Procesamiento local</strong>Las fotos se quedan en tu equipo</span></li>
        <li><FileCheck2 size={22} aria-hidden /><span><strong>Originales intactos</strong>Guarda las fotos a tamaño original</span></li>
        <li><Images size={22} aria-hidden /><span><strong>Formatos compatibles</strong>JPG, PNG y WebP</span></li>
      </ul>
    </div>
  )
}
