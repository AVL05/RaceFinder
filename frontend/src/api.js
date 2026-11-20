// Cliente de la API local. Rutas relativas: en desarrollo las proxifica Vite; en producción las sirve FastAPI.
async function json(res) {
  if (!res.ok) {
    let msg = res.status >= 500 ? 'El servidor local ha tenido un problema. Inténtalo de nuevo.' : `Error ${res.status}`
    try { const b = await res.json(); if (typeof b.detail === 'string') msg = b.detail } catch { /* sin cuerpo */ }
    const err = new Error(msg)
    err.status = res.status
    throw err
  }
  return res.json()
}

const get = (url) => fetch(url).then(json, () => { throw new Error('No se puede contactar con RaceFinder. ¿Sigue abierta la ventana de la terminal?') })
const send = (method, url, body) =>
  fetch(url, { method, headers: { 'Content-Type': 'application/json' }, body: body === undefined ? undefined : JSON.stringify(body) })
    .then(json, () => { throw new Error('No se puede contactar con RaceFinder.') })

function query(path, params) {
  const values = Object.entries(params).filter(([, value]) => value != null && value !== '')
  return values.length ? `${path}?${new URLSearchParams(values)}` : path
}

export const api = {
  stats: (album) => get(query('/api/stats', { album })),
  albums: () => get('/api/albums'),
  createAlbum: (album) => send('POST', '/api/albums', album),
  updateAlbum: (id, album) => send('PATCH', `/api/albums/${id}`, album),
  deleteAlbum: (id) => send('DELETE', `/api/albums/${id}`),
  changeAlbumPhotos: (id, ids, action) => send('POST', `/api/albums/${id}/photos`, { ids, action }),
  setFavorites: (ids, favorite) => send('PUT', '/api/photos/favorites', { ids, favorite }),
  photos: (limit = 120, offset = 0, { filter = 'all', album, filename, sort } = {}) =>
    get(query('/api/photos', { limit, offset, filter, album, filename, sort })),
  selection: (options) => get(query('/api/photos/selection', options)),
  catalogCsv: (options) => query('/api/export/catalog.csv', options),
  search: (bib, similar = false, album) => get(query('/api/search', { bib, mode: similar ? 'similar' : 'exact', album })),
  photo: (id, album) => get(query(`/api/photos/${id}`, { album })),
  facesForBib: (bib, album) => get(query('/api/faces/for-bib', { bib, album })),
  faceSearch: (face_ids, album) => send('POST', query('/api/faces/search', { album }), { face_ids }),
  faceCropUrl: (id) => `/api/faces/${id}/crop`,
  deleteFaces: () => send('DELETE', '/api/faces'),
  bibIndex: (limit = 400, album) => get(query('/api/bibs/index', { limit, album })),
  known: (items, album) => send('POST', query('/api/photos/known', { album }), { items }),
  // RaceFinder corre en tu equipo: el servidor lee y guarda en carpetas del disco directamente (sin subir ni descargar)
  pickFolder: (title) => send('POST', '/api/system/pick-folder', { title }),
  importFolder: (path, album) => send('POST', '/api/import/folder', { path, album }),
  importStatus: () => get('/api/import/status'),
  importCancel: () => send('POST', '/api/import/cancel'),
  saveToFolder: (body) => send('POST', '/api/export/save', body),
  upload: (files, album) => {
    const fd = new FormData()
    files.forEach((f) => fd.append('files', f, f.name))
    return fetch(query('/api/photos', { album }), { method: 'POST', body: fd }).then(json)
  },
  process: () => send('POST', '/api/process'),
  reanalyze: () => send('POST', '/api/process?reanalyze=true'),
  reprocess: (id) => send('POST', `/api/photos/${id}/reprocess`),
  cancel: () => send('POST', '/api/process/cancel'),
  settings: () => get('/api/settings'),
  saveSettings: (body) => send('PUT', '/api/settings', body),
  review: (bibId, review) => send('PATCH', `/api/bibs/${bibId}`, { review }),
  addBib: (photoId, number) => send('POST', `/api/photos/${photoId}/bibs`, { number }),
  remove: (id) => send('DELETE', `/api/photos/${id}`),
  removeMany: (ids) => send('POST', '/api/photos/delete', { ids }),
  removeAll: () => send('POST', '/api/photos/delete-all', { confirm: 'ELIMINAR' }),
  // ?v=<hash>: si un id se reutiliza (biblioteca borrada, última foto quitada) el navegador no sirve una imagen vieja
  thumbUrl: (p) => `/api/photos/${p.id}/thumb?v=${p.v}`,
  previewUrl: (p) => `/api/photos/${p.id}/preview?v=${p.v}`,
  originalUrl: (p) => `/api/photos/${p.id}/original?v=${p.v}`,
  downloadUrl: (p) => `/api/photos/${p.id}/original?download=true&v=${p.v}`,
  cropUrl: (bibId) => `/api/bibs/${bibId}/crop`,
  exportZip: async (ids) => {
    const res = await fetch('/api/export', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ ids }) })
    if (!res.ok) throw new Error('No se pudo preparar la descarga')
    return res.blob()
  },
  // evaluación (herramienta avanzada)
  evalSummary: () => get('/api/eval/summary'),
  evalPhotos: (state, limit = 40, offset = 0) => get(`/api/eval/photos?state=${state}&limit=${limit}&offset=${offset}`),
  evalLabel: (id, body) => send('PUT', `/api/eval/labels/${id}`, body),
  evalRun: (split, confirm_test = false, params = {}) => send('POST', '/api/eval/run', { split, confirm_test, params }),
  evalSearchRun: (split, confirm_test = false) => send('POST', '/api/eval/search-run', { split, confirm_test }),
  evalStatus: () => get('/api/eval/status'),
  evalRuns: () => get('/api/eval/runs'),
}

// sin conexión o API reiniciándose: lo indica el banner de la cabecera, no hace falta otro aviso
export const isOffline = (e) => !e?.status || e.status === 503

export const ALLOWED = /\.(jpe?g|png|webp)$/i

export function saveBlob(blob, name) {
  const a = document.createElement('a')
  a.href = URL.createObjectURL(blob); a.download = name
  document.body.appendChild(a); a.click(); a.remove()
  setTimeout(() => URL.revokeObjectURL(a.href), 10_000)
}

export async function downloadPhotos(photos) {
  if (photos.length === 1) {
    const a = document.createElement('a')
    a.href = api.downloadUrl(photos[0]); a.download = photos[0].name
    document.body.appendChild(a); a.click(); a.remove()
    return
  }
  // formulario oculto: el navegador guarda el ZIP en disco a medida que llega (sin cargarlo en memoria)
  const form = document.createElement('form')
  form.method = 'POST'; form.action = '/api/export/download'; form.style.display = 'none'
  const input = document.createElement('input')
  input.type = 'hidden'; input.name = 'ids'; input.value = photos.map((p) => p.id).join(',')
  form.appendChild(input); document.body.appendChild(form); form.submit(); form.remove()
}

// Sube en lotes (≤25 archivos / 40 MB) con 3 peticiones en paralelo.
export async function uploadInBatches(files, onProgress, { batchBytes = 40 * 1024 * 1024, parallel = 3, album } = {}) {
  const valid = files.filter((f) => ALLOWED.test(f.name))
  const tally = { added: 0, duplicate: 0, rejected: 0, skipped: files.length - valid.length, errors: [], total: valid.length }
  // 1) huella rápida (tamaño + SHA-256 de los primeros 64 KB) y pregunta al servidor cuáles ya tiene
  let pending = valid
  if (valid.length && crypto?.subtle) {
    try {
      const fps = new Array(valid.length)
      let checked = 0, next = 0
      const hashOne = async () => {
        while (next < valid.length) {
          const i = next++
          const buf = await valid[i].slice(0, 64 * 1024).arrayBuffer()
          const h = new Uint8Array(await crypto.subtle.digest('SHA-256', buf))
          fps[i] = { size: valid[i].size, head: [...h].map((b) => b.toString(16).padStart(2, '0')).join('') }
          if (++checked % 200 === 0) onProgress?.({ ...tally, done: 0, phase: 'checking', checked })
        }
      }
      await Promise.all(Array.from({ length: 8 }, hashOne))
      const known = []
      for (let k = 0; k < fps.length; k += 2000) known.push(...(await api.known(fps.slice(k, k + 2000), album)).known)
      pending = valid.filter((_, i) => !known[i])
      tally.duplicate += valid.length - pending.length
    } catch { pending = valid }  // si falla la comprobación, se sube todo: el servidor sigue detectando duplicados
  }
  const batches = []
  for (let i = 0; i < pending.length;) {
    const b = []; let bytes = 0
    while (i < pending.length && (b.length === 0 || (bytes + pending[i].size <= batchBytes && b.length < 25))) { bytes += pending[i].size; b.push(pending[i++]) }
    batches.push(b)
  }
  let done = valid.length - pending.length
  onProgress?.({ ...tally, done })
  let next = 0
  let queue = batches
  const failed = []        // lotes que fallaron: se reintentan una vez al final, cuando el servidor se haya recuperado
  let diskFull = false
  const worker = async () => {
    while (next < queue.length && !diskFull) {
      const batch = queue[next++]
      // si la API se corta (reinicio, equipo saturado) se reintenta el lote: subir dos veces la misma foto
      // es seguro porque el servidor la detecta como duplicada
      let lastErr = null
      for (let attempt = 0; attempt < 5; attempt++) {
        try {
          const { results } = await api.upload(batch, album)
          results.forEach((r) => { tally[r.status]++; if (r.error) tally.errors.push(`${r.name}: ${r.error}`) })
          lastErr = null
          break
        } catch (e) {
          lastErr = e
          if (e.status === 507) { diskFull = true; break }  // disco lleno: reintentar no sirve
          if (e.status && e.status < 500) break          // error del archivo/petición: no se reintenta
          onProgress?.({ ...tally, done, retrying: true })
          await new Promise((r) => setTimeout(r, 1500 * 2 ** attempt))
        }
      }
      if (lastErr && !diskFull && !queue.second) { failed.push(batch); continue }   // segunda oportunidad al final
      if (lastErr) {
        tally.rejected += batch.length
        tally.errors.push(`${batch.length} fotos no se pudieron subir (${lastErr.message}). Vuelve a añadir la carpeta: las que ya estén se omitirán.`)
      }
      done += batch.length
      onProgress?.({ ...tally, done })
    }
  }
  await Promise.all(Array.from({ length: Math.min(parallel, batches.length) }, worker))
  if (failed.length && !diskFull) {
    // pausa para que un servidor reiniciado o saturado se recupere, y una pasada más solo con lo que falló
    onProgress?.({ ...tally, done, retrying: true })
    await new Promise((r) => setTimeout(r, 15_000))
    queue = failed.slice(); queue.second = true; next = 0
    await Promise.all(Array.from({ length: Math.min(parallel, queue.length) }, worker))
  }
  if (diskFull) {
    const left = queue.slice(next).reduce((n, b) => n + b.length, 0)
    tally.rejected += left; done += left
  }
  return { ...tally, done }
}

// Recorre carpetas soltadas (drag & drop) recursivamente.
export async function filesFromDrop(dataTransfer) {
  const files = []
  const walk = async (entry) => {
    if (entry.isFile) files.push(await new Promise((r, j) => entry.file(r, j)))
    else if (entry.isDirectory) {
      const rd = entry.createReader()
      for (;;) {
        const batch = await new Promise((r, j) => rd.readEntries(r, j))
        if (!batch.length) break
        for (const c of batch) await walk(c)
      }
    }
  }
  const entries = [...(dataTransfer.items || [])].map((i) => i.webkitGetAsEntry?.()).filter(Boolean)
  if (entries.length) for (const e of entries) await walk(e)
  else files.push(...dataTransfer.files)
  return files
}
