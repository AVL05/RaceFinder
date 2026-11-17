import { createContext, useCallback, useContext, useState } from 'react'
import { X } from 'lucide-react'

const Ctx = createContext(() => {})
export const useToast = () => useContext(Ctx)

export function ToastProvider({ children }) {
  const [items, setItems] = useState([])
  const push = useCallback((text, kind = 'info') => {
    const id = Math.random().toString(36).slice(2)
    setItems((l) => (l.some((t) => t.text === text) ? l : [...l.slice(-3), { id, text, kind }]))
    setTimeout(() => setItems((l) => l.filter((t) => t.id !== id)), kind === 'error' ? 7000 : 3500)
  }, [])
  const tone = { info: 'border-white/10', ok: 'border-green-500/40', warn: 'border-amber-400/40', error: 'border-red-500/50' }
  return (
    <Ctx.Provider value={push}>
      {children}
      <div className="pointer-events-none fixed inset-x-0 top-20 z-[60] flex flex-col items-center gap-2 px-4" aria-live="assertive">
        {items.map((t) => (
          <div key={t.id} role={t.kind === 'error' ? 'alert' : 'status'}
            className={`pointer-events-auto flex max-w-md items-center gap-3 rounded-xl border bg-ink-900/95 px-4 py-2.5 text-sm shadow-xl backdrop-blur rf-fade ${tone[t.kind]}`}>
            <span>{t.text}</span>
            <button onClick={() => setItems((l) => l.filter((x) => x.id !== t.id))} aria-label="Cerrar aviso" className="text-ink-500 hover:text-white"><X size={14} /></button>
          </div>
        ))}
      </div>
    </Ctx.Provider>
  )
}
