import { useCallback, useEffect, useRef, useState } from 'react'
import { Play, Tag, EyeOff, ArrowRight, Loader2, AlertTriangle } from 'lucide-react'
import { api } from './api.js'

const TAG_LABELS = {
  inclinado: 'Inclinado', ocluido: 'Parcialmente oculto', pequeno: 'Número pequeño', varios_corredores: 'Varios corredores',
  fondo_complejo: 'Fondo complejo', cartel_reloj: 'Cartel / reloj', poca_luz: 'Poca luz', desenfocado: 'Desenfocado',
  cara_pequena: 'Cara pequeña', perfil: 'Cara de perfil', gafas: 'Gafas', gorra: 'Gorra / visera',
}
const pct = (x) => (x === null || x === undefined ? '—' : `${(x * 100).toFixed(1)} %`)
const sec = (x) => (x === null || x === undefined ? '—' : `${x.toFixed(2)} s`)

export default function EvalView() {
  const [summary, setSummary] = useState(null)
  const [runs, setRuns] = useState([])
  const [error, setError] = useState('')

  const reload = useCallback(async () => {
    try { setSummary(await api.evalSummary()); setRuns((await api.evalRuns()).runs); setError('') }
    catch (e) { setError(e.message) }
  }, [])
  useEffect(() => { reload() }, [reload])

  return (
    <div className="mx-auto w-full max-w-[1200px] space-y-8 px-4 py-6 sm:px-5" data-testid="eval">
      <div>
        <h2 className="text-xl font-semibold">Evaluación del OCR</h2>
        <p className="mt-1 max-w-3xl text-sm text-ink-300">
          Etiqueta a mano los dorsales realmente legibles de una carpeta de fotos y mide cuánto acierta el motor.
          Cada foto se asigna automáticamente a <strong>ajuste</strong> (30 %, para tocar parámetros) o <strong>test</strong> (70 %, validación final).
          Los parámetros nunca deben ajustarse mirando los resultados de test.
        </p>
        <p className="mt-1 text-xs text-ink-500">Recomendación: usa una carpeta de evaluación distinta de tu biblioteca (arranca con la variable RACEFINDER_DATA apuntando a otra carpeta).</p>
      </div>
      {error && <div role="alert" className="rounded-lg border border-red-500/40 bg-red-500/10 px-4 py-3 text-sm">{error}</div>}
      {summary && <Summary s={summary} />}
      {summary && <Labeler summary={summary} onChange={reload} />}
      {summary && <Runner summary={summary} onDone={reload} />}
      {runs.length > 0 && <Runs runs={runs} />}
    </div>
  )
}

function Summary({ s }) {
  return (
    <div className="grid gap-3 sm:grid-cols-3" data-testid="eval-summary">
      {[['Sin etiquetar', s.unlabeled, null], ['Ajuste (tune)', s.splits.tune.photos, s.splits.tune], ['Test (validación final)', s.splits.test.photos, s.splits.test]].map(([t, n, d]) => (
        <div key={t} className="rounded-lg border border-ink-700 bg-ink-900 p-4">
          <div className="text-xs text-ink-500">{t}</div>
          <div className="text-2xl font-semibold">{n}</div>
          {d && <div className="text-xs text-ink-300">{d.with_bibs} con dorsal · {d.no_bib} sin dorsal legible · {d.runs} ejecuciones</div>}
        </div>
      ))}
    </div>
  )
}

function Labeler({ summary, onChange }) {
  const [photo, setPhoto] = useState(undefined) // undefined = cargando, null = no quedan
  const [bibs, setBibs] = useState([])
  const [draft, setDraft] = useState('')
  const [present, setPresent] = useState([])
  const [pdraft, setPdraft] = useState('')
  const [tags, setTags] = useState(new Set())
  const [err, setErr] = useState('')
  const inputRef = useRef(null)

  const next = useCallback(async () => {
    const r = await api.evalPhotos('unlabeled', 1, 0)
    setPhoto(r.photos[0] ?? null); setBibs([]); setDraft(''); setPresent([]); setPdraft(''); setTags(new Set()); setErr('')
  }, [])
  useEffect(() => { next() }, [next])

  const addDraft = () => { if (/^\d{1,5}$/.test(draft) && !bibs.includes(draft)) { setBibs([...bibs, draft]); setDraft('') } }
  const save = async (state) => {
    try {
      const list = state === 'labeled' ? (draft && /^\d{1,5}$/.test(draft) && !bibs.includes(draft) ? [...bibs, draft] : bibs) : []
      const pres = pdraft && /^\d{1,5}$/.test(pdraft) && !present.includes(pdraft) ? [...present, pdraft] : present
      await api.evalLabel(photo.id, { state, bibs: list, present: pres, tags: [...tags] })
      await onChange(); await next(); inputRef.current?.focus()
    } catch (e) { setErr(e.message) }
  }

  if (photo === undefined) return <div className="rf-skeleton h-64 rounded-lg" />
  if (photo === null) return (
    <div className="rounded-lg border border-ink-700 bg-ink-900 p-6 text-sm text-ink-300" data-testid="labeler-empty">
      {summary.splits.tune.photos + summary.splits.test.photos === 0
        ? 'No hay fotos que etiquetar. Importa la carpeta de evaluación en la pestaña Fotos.'
        : 'Todas las fotos importadas están etiquetadas.'}
    </div>
  )
  return (
    <section aria-label="Etiquetado" className="grid gap-4 rounded-lg border border-ink-700 bg-ink-900 p-4 md:grid-cols-[minmax(0,2fr)_minmax(280px,1fr)]" data-testid="labeler">
      <div className="grid place-items-center rounded bg-black">
        <img src={api.previewUrl(photo)} alt={`Foto a etiquetar: ${photo.name}`} className="max-h-[60vh] w-full object-contain" />
      </div>
      <div className="space-y-4">
        <div>
          <div className="text-xs text-ink-500">{photo.name} · quedan {summary.unlabeled}</div>
          <label htmlFor="bibdraft" className="mt-2 block text-sm font-medium">Dorsales legibles en la foto</label>
          <div className="mt-1 flex gap-2">
            <input id="bibdraft" ref={inputRef} inputMode="numeric" value={draft} onChange={(e) => setDraft(e.target.value.replace(/\D/g, '').slice(0, 5))}
              onKeyDown={(e) => { if (e.key === 'Enter') { e.preventDefault(); addDraft() } }}
              className="w-full rounded border border-ink-700 bg-ink-950 px-3 py-2 text-sm" placeholder="Número y Enter" />
            <button onClick={addDraft} className="rounded border border-ink-700 px-3 text-sm hover:bg-ink-800">Añadir</button>
          </div>
          <ul className="mt-2 flex flex-wrap gap-2" aria-label="Dorsales etiquetados">
            {bibs.map((b) => (
              <li key={b}><button onClick={() => setBibs(bibs.filter((x) => x !== b))} className="rounded-full border border-ink-700 bg-ink-950 px-3 py-1 text-sm" aria-label={`Quitar ${b}`}>#{b} ✕</button></li>
            ))}
          </ul>
          <label htmlFor="presentdraft" className="mt-3 block text-sm font-medium">Corredores que salen sin dorsal legible</label>
          <p className="text-xs text-ink-500">Su número (si lo sabes), aunque en esta foto no se lea: sirve para medir la búsqueda por cara.</p>
          <div className="mt-1 flex gap-2">
            <input id="presentdraft" inputMode="numeric" value={pdraft} onChange={(e) => setPdraft(e.target.value.replace(/\D/g, '').slice(0, 5))}
              onKeyDown={(e) => { if (e.key === 'Enter') { e.preventDefault(); if (/^\d{1,5}$/.test(pdraft) && !present.includes(pdraft)) { setPresent([...present, pdraft]); setPdraft('') } } }}
              className="w-full rounded border border-ink-700 bg-ink-950 px-3 py-2 text-sm" placeholder="Número y Enter" />
          </div>
          <ul className="mt-2 flex flex-wrap gap-2" aria-label="Corredores sin dorsal legible">
            {present.map((b) => (
              <li key={b}><button onClick={() => setPresent(present.filter((x) => x !== b))} className="rounded-full border border-dashed border-ink-500 px-3 py-1 text-sm" aria-label={`Quitar ${b}`}>#{b} sin dorsal ✕</button></li>
            ))}
          </ul>
        </div>
        <fieldset>
          <legend className="flex items-center gap-1 text-sm font-medium"><Tag size={14} aria-hidden /> Condiciones (opcional)</legend>
          <div className="mt-1 grid grid-cols-2 gap-1 text-xs text-ink-300">
            {Object.entries(TAG_LABELS).map(([k, v]) => (
              <label key={k} className="flex items-center gap-2"><input type="checkbox" checked={tags.has(k)}
                onChange={(e) => setTags((t) => { const n = new Set(t); e.target.checked ? n.add(k) : n.delete(k); return n })} /> {v}</label>
            ))}
          </div>
        </fieldset>
        {err && <p role="alert" className="text-sm text-red-400">{err}</p>}
        <div className="flex flex-wrap gap-2">
          <button onClick={() => save('labeled')} className="flex items-center gap-2 rounded-lg bg-accent px-4 py-2 text-sm font-medium text-ink-950"><ArrowRight size={15} aria-hidden /> Guardar y siguiente</button>
          <button onClick={() => save('no_bib')} className="flex items-center gap-2 rounded-lg border border-ink-700 px-4 py-2 text-sm hover:bg-ink-800"><EyeOff size={15} aria-hidden /> Sin dorsal legible</button>
        </div>
        <p className="text-xs text-ink-500">Etiqueta solo lo que una persona puede leer en la foto. Un dorsal ilegible no debe contarse como fallo del OCR.</p>
      </div>
    </section>
  )
}

function Runner({ summary, onDone }) {
  const [split, setSplit] = useState('tune')
  const [confirm, setConfirm] = useState(false)
  const [status, setStatus] = useState(summary.status)
  const [err, setErr] = useState('')

  useEffect(() => {
    if (!status?.running) return
    const t = setInterval(async () => {
      const s = await api.evalStatus(); setStatus(s)
      if (!s.running) onDone()
    }, 1000)
    return () => clearInterval(t)
  }, [status?.running, onDone])

  const n = summary.splits[split].photos
  const start = async () => {
    try { setErr(''); setStatus(await api.evalRun(split, confirm)); setConfirm(false) } catch (e) { setErr(e.message) }
  }
  const startSearch = async () => {
    try { setErr(''); await api.evalSearchRun(split, confirm); setConfirm(false); onDone() } catch (e) { setErr(e.message) }
  }
  return (
    <section aria-label="Ejecutar evaluación" className="rounded-lg border border-ink-700 bg-ink-900 p-4">
      <h3 className="font-medium">Ejecutar OCR y medir</h3>
      <div className="mt-3 flex flex-wrap items-center gap-3 text-sm">
        <label className="flex items-center gap-2">Partición
          <select value={split} onChange={(e) => setSplit(e.target.value)} className="rounded border border-ink-700 bg-ink-950 px-2 py-1.5">
            <option value="tune">Ajuste ({summary.splits.tune.photos})</option>
            <option value="test">Test ({summary.splits.test.photos})</option>
          </select>
        </label>
        {split === 'test' && (
          <label className="flex items-center gap-2 text-amber-300"><AlertTriangle size={14} aria-hidden />
            <input type="checkbox" checked={confirm} onChange={(e) => setConfirm(e.target.checked)} />
            No he ajustado parámetros con estas fotos ({summary.splits.test.runs} ejecuciones previas)
          </label>
        )}
        <button disabled={status?.running || n === 0 || (split === 'test' && !confirm)} onClick={start}
          className="flex items-center gap-2 rounded-lg bg-accent px-4 py-2 font-medium text-ink-950 disabled:opacity-40">
          {status?.running ? <Loader2 size={15} className="animate-spin" aria-hidden /> : <Play size={15} aria-hidden />} Evaluar OCR
        </button>
        <button disabled={status?.running || n === 0 || (split === 'test' && !confirm)} onClick={startSearch}
          className="rounded-lg border border-ink-700 px-4 py-2 hover:bg-ink-800 disabled:opacity-40" title="Usa las lecturas y caras ya guardadas">
          Evaluar búsqueda (dorsal + cara)
        </button>
        {status?.running && <span role="status">{status.done} / {status.total} fotos</span>}
      </div>
      {n === 0 && <p className="mt-2 text-xs text-ink-500">No hay fotos etiquetadas en esta partición.</p>}
      {(err || status?.error) && <p role="alert" className="mt-2 text-sm text-red-400">{err || status.error}</p>}
    </section>
  )
}

function Runs({ runs }) {
  return (
    <section aria-label="Resultados" className="space-y-4">
      <h3 className="font-medium">Resultados</h3>
      {runs.slice(0, 6).map((r) => {
        if (r.params?.kind === 'search') return <SearchRun key={r.id} r={r} />
        const m = r.metrics, b = m.per_bib, p = m.per_photo
        return (
          <article key={r.id} className="rounded-lg border border-ink-700 bg-ink-900 p-4 text-sm" data-testid="eval-run">
            <header className="flex flex-wrap items-center justify-between gap-2">
              <strong>{r.split === 'test' ? 'Test (validación final)' : 'Ajuste'} · {m.photos} fotos</strong>
              <span className="text-xs text-ink-500">{r.created_at} UTC</span>
            </header>
            {m.photos < 30 && <p className="mt-2 flex items-center gap-1 text-xs text-amber-300"><AlertTriangle size={13} aria-hidden /> Muestra pequeña ({m.photos} fotos): las métricas son orientativas.</p>}
            <div className="mt-3 grid gap-4 md:grid-cols-2">
              <div>
                <h4 className="text-xs uppercase tracking-wide text-ink-500">Por dorsal detectado (foto, número)</h4>
                <dl className="mt-1 grid grid-cols-3 gap-2">
                  <Metric k="Precision" v={pct(b.precision)} /><Metric k="Recall" v={pct(b.recall)} /><Metric k="F1" v={pct(b.f1)} />
                  <Metric k="Falsos positivos" v={b.fp} /><Metric k="Falsos negativos" v={b.fn} /><Metric k="Aciertos" v={b.tp} />
                </dl>
              </div>
              <div>
                <h4 className="text-xs uppercase tracking-wide text-ink-500">Por fotografía</h4>
                <dl className="mt-1 grid grid-cols-3 gap-2">
                  <Metric k="Todos los dorsales" v={pct(p.all_bibs_found_rate)} /><Metric k="Al menos uno" v={pct(p.any_bib_found_rate)} /><Metric k="Conjunto exacto" v={pct(p.exact_set_rate)} />
                  <Metric k="Falsas alarmas" v={`${p.false_alarm_photos}/${m.photos_without_readable_bib}`} /><Metric k="Tiempo medio" v={sec(m.timing.mean_s)} /><Metric k="Tiempo total" v={sec(m.timing.total_s)} />
                </dl>
              </div>
            </div>
            {Object.keys(m.by_tag).length > 0 && (
              <table className="mt-4 w-full text-left text-xs">
                <caption className="mb-1 text-left uppercase tracking-wide text-ink-500">Por condición</caption>
                <thead className="text-ink-500"><tr><th>Condición</th><th>Fotos</th><th>Precision</th><th>Recall</th><th>FP</th><th>FN</th></tr></thead>
                <tbody>{Object.entries(m.by_tag).map(([k, v]) => (
                  <tr key={k} className="border-t border-ink-700"><td className="py-1">{TAG_LABELS[k] ?? k}</td><td>{v.photos}</td><td>{pct(v.precision)}</td><td>{pct(v.recall)}</td><td>{v.fp}</td><td>{v.fn}</td></tr>
                ))}</tbody>
              </table>
            )}
            {m.timing.face_mean_s != null && <p className="mt-2 text-xs text-ink-300">Caras: {sec(m.timing.face_mean_s)} de media por foto</p>}
            <p className="mt-3 text-xs text-ink-500">Configuración: {Object.entries(r.params).map(([k, v]) => `${k}=${v}`).join(' · ')}</p>
          </article>
        )
      })}
    </section>
  )
}

const Metric = ({ k, v }) => (<div><dt className="text-[11px] text-ink-500">{k}</dt><dd className="text-base font-semibold">{v}</dd></div>)

const MODE_LABELS = { bib: 'Solo dorsal', face: 'Solo cara', combined: 'Dorsal o cara' }

function SearchRun({ r }) {
  const m = r.metrics
  return (
    <article className="rounded-lg border border-ink-700 bg-ink-900 p-4 text-sm" data-testid="eval-search-run">
      <header className="flex flex-wrap items-center justify-between gap-2">
        <strong>Búsqueda · {r.split === 'test' ? 'Test (validación final)' : 'Ajuste'} · {m.photos} fotos · {m.queries} dorsales</strong>
        <span className="text-xs text-ink-500">{r.created_at} UTC</span>
      </header>
      {m.photos < 30 && <p className="mt-2 flex items-center gap-1 text-xs text-amber-300"><AlertTriangle size={13} aria-hidden /> Muestra pequeña ({m.photos} fotos): las métricas son orientativas.</p>}
      {!r.params.faces && <p className="mt-2 text-xs text-ink-300">Búsqueda por cara desactivada o sin terminar: solo se mide el dorsal.</p>}
      <table className="mt-3 w-full text-left text-xs">
        <thead className="text-ink-500"><tr><th>Modo</th><th>Precision</th><th>Recall</th><th>F1</th><th>TP</th><th>FP</th><th>FN</th></tr></thead>
        <tbody>{m.modes.map((k) => { const x = m.per_mode[k]; return (
          <tr key={k} className="border-t border-ink-700"><td className="py-1">{MODE_LABELS[k]}</td><td>{pct(x.precision)}</td><td>{pct(x.recall)}</td><td>{pct(x.f1)}</td><td>{x.tp}</td><td>{x.fp}</td><td>{x.fn}</td></tr>) })}</tbody>
      </table>
      {m.face_only_recall != null && <p className="mt-2 text-xs text-ink-300">Fotos sin dorsal legible recuperadas por la cara: <strong className="text-ink-100">{pct(m.face_only_recall)}</strong> de {m.face_only_pairs}</p>}
      <p className="mt-3 text-xs text-ink-500">Umbral facial {r.params.face_threshold} (coseno, no probabilidad) · lectura dudosa por debajo de {r.params.doubtful_below}</p>
    </article>
  )
}
