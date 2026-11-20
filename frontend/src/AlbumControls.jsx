import { useEffect, useRef, useState } from 'react'
import { FolderPlus, Pencil, Plus, Trash2, X } from 'lucide-react'
import { api } from './api.js'
import { useToast } from './Toast.jsx'

function AlbumDialog({ title, onClose, children }) {
  const ref = useRef(null)
  useEffect(() => {
    const dialog = ref.current
    dialog.showModal()
    return () => dialog.close()
  }, [])
  return (
    <dialog ref={ref} aria-labelledby="album-dialog-title" className="rf-album-dialog"
      onCancel={(e) => { e.preventDefault(); onClose() }}>
      <div className="flex items-start justify-between gap-3">
        <h2 id="album-dialog-title" className="text-xl font-semibold">{title}</h2>
        <button onClick={onClose} className="rf-button rf-button-quiet min-w-11" aria-label="Cerrar"><X size={18} aria-hidden /></button>
      </div>
      {children}
    </dialog>
  )
}

export default function AlbumControls({ albums, current, importing, onSelect, onChange }) {
  const toast = useToast()
  const [editing, setEditing] = useState(null)
  const [name, setName] = useState('')
  const [range, setRange] = useState({ min: '', max: '' })
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')

  const edit = (album) => {
    setEditing(album ?? {})
    setName(album?.name ?? '')
    setRange({ min: album?.min_number == null ? '' : String(album.min_number), max: album?.max_number == null ? '' : String(album.max_number) })
    setError('')
  }
  const close = () => { if (!busy) setEditing(null) }
  const save = async (e) => {
    e.preventDefault()
    if (!name.trim() || busy) return
    setBusy(true)
    setError('')
    try {
      const data = { name: name.trim(), min_number: range.min === '' ? null : Number(range.min), max_number: range.max === '' ? null : Number(range.max) }
      if (editing.id) {
        await api.updateAlbum(editing.id, data)
        await onChange()
        toast('Álbum actualizado', 'ok')
      } else {
        const created = await api.createAlbum(data)
        await onChange()
        onSelect(created.id, true)
        toast('Álbum creado. Ya puedes añadir fotos.', 'ok')
      }
      setEditing(null)
    } catch (e) { setError(e.message) } finally { setBusy(false) }
  }
  const remove = async () => {
    if (!window.confirm(`¿Eliminar el álbum «${current.name}»? Sus fotos seguirán en la biblioteca.`)) return
    setBusy(true)
    try {
      await api.deleteAlbum(current.id)
      onSelect(null, true)
      await onChange()
      toast('Álbum eliminado. Las fotos siguen en la biblioteca.', 'ok')
    } catch (e) { toast(e.message, 'error') } finally { setBusy(false) }
  }
  return (
    <div className="rf-container rf-album-bar">
      <label className="rf-album-select">
        <span>Álbum</span>
        <select aria-label="Álbum activo" value={current?.id ?? ''} onChange={(e) => onSelect(Number(e.target.value) || null)}>
          <option value="">Toda la biblioteca</option>
          {albums.map((album) => <option key={album.id} value={album.id}>{album.name} ({album.photos})</option>)}
        </select>
      </label>
      <div className="flex flex-wrap items-center gap-2">
        <button onClick={() => edit()} className="rf-button rf-button-quiet min-w-11" aria-label="Nuevo álbum" title="Nuevo álbum" disabled={busy}>
          <Plus size={16} aria-hidden /><span className={current ? 'hidden sm:inline' : ''}>Nuevo álbum</span>
        </button>
        {current && <>
          <button onClick={() => edit(current)} className="rf-button rf-button-quiet min-w-11" aria-label="Editar álbum" title="Editar álbum" disabled={busy}><Pencil size={16} aria-hidden /></button>
          <button onClick={remove} className="rf-button rf-button-quiet min-w-11 hover:text-red-300" aria-label="Eliminar álbum" title="Eliminar álbum" disabled={busy || importing}><Trash2 size={16} aria-hidden /></button>
        </>}
      </div>
      {editing && (
        <AlbumDialog title={editing.id ? 'Editar álbum' : 'Nuevo álbum'} onClose={close}>
          <form onSubmit={save} className="mt-4 space-y-4">
            <label className="grid gap-1.5 text-sm">
              Nombre del álbum
              <input value={name} onChange={(e) => setName(e.target.value)} maxLength={80} required autoComplete="off" className="rf-catalog-input" />
            </label>
            <fieldset className="space-y-2">
              <legend className="text-sm font-semibold">Rango de dorsales</legend>
              <p className="text-sm text-ink-300">Deja ambos campos vacíos para usar el rango general.</p>
              <div className="grid grid-cols-2 gap-2">
                <label className="grid gap-1.5 text-sm">
                  Mínimo
                  <input type="number" min="0" max="99999" value={range.min} onChange={(e) => setRange({ ...range, min: e.target.value })} className="rf-catalog-input" />
                </label>
                <label className="grid gap-1.5 text-sm">
                  Máximo
                  <input type="number" min="0" max="99999" value={range.max} onChange={(e) => setRange({ ...range, max: e.target.value })} className="rf-catalog-input" />
                </label>
              </div>
            </fieldset>
            {error && <p role="alert" className="text-sm text-red-300">{error}</p>}
            <div className="flex flex-wrap justify-end gap-2">
              <button type="button" onClick={close} disabled={busy} className="rf-button rf-button-quiet">Cancelar</button>
              <button disabled={busy || !name.trim()} className="rf-button rf-button-primary">{editing.id ? 'Guardar cambios' : 'Crear álbum'}</button>
            </div>
          </form>
        </AlbumDialog>
      )}
    </div>
  )
}

export function AlbumAssignment({ albums, current, ids, onClose, onChanged }) {
  const toast = useToast()
  const [target, setTarget] = useState(albums[0]?.id ?? '')
  const [name, setName] = useState('')
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')
  const close = () => { if (!busy) onClose() }
  const apply = async (action) => {
    if (busy) return
    setBusy(true)
    setError('')
    try {
      const id = action === 'remove' ? current.id : target
      const changed = id
        ? (await api.changeAlbumPhotos(id, ids, action)).changed
        : (await api.createAlbum({ name: name.trim(), ids })).photos
      await onChanged(action)
      toast(changed ? (action === 'remove' ? `Fotos quitadas del álbum: ${changed}` : `Fotos añadidas al álbum: ${changed}`) : 'El álbum ya estaba actualizado', 'ok')
      onClose()
    } catch (e) { setError(e.message) } finally { setBusy(false) }
  }
  return (
    <AlbumDialog title="Organizar selección" onClose={close}>
      <form onSubmit={(e) => { e.preventDefault(); apply('add') }} className="mt-4 space-y-4">
        <p className="text-sm text-ink-300">Puedes incluir las mismas fotos en varios álbumes.</p>
        <label className="grid gap-1.5 text-sm">
          Álbum de destino
          <select value={target} onChange={(e) => setTarget(Number(e.target.value) || '')} className="rf-catalog-input">
            <option value="">Crear un álbum nuevo</option>
            {albums.map((album) => <option key={album.id} value={album.id}>{album.name}</option>)}
          </select>
        </label>
        {!target && <label className="grid gap-1.5 text-sm">
          Nombre del álbum
          <input value={name} onChange={(e) => setName(e.target.value)} maxLength={80} required autoComplete="off" className="rf-catalog-input" />
        </label>}
        {error && <p role="alert" className="text-sm text-red-300">{error}</p>}
        <div className="flex flex-wrap justify-end gap-2">
          {current && <button type="button" onClick={() => apply('remove')} disabled={busy} className="rf-button rf-button-quiet">Quitar del álbum actual</button>}
          <button disabled={busy || (!target && !name.trim())} className="rf-button rf-button-primary"><FolderPlus size={17} aria-hidden /> Añadir al álbum</button>
        </div>
      </form>
    </AlbumDialog>
  )
}
