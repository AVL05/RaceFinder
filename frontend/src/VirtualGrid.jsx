import { useEffect, useLayoutEffect, useRef, useState } from 'react'

/**
 * Rejilla virtualizada: con 10.000 fotos solo existen en la página las tarjetas visibles (± unas filas),
 * así el scroll y las actualizaciones siguen fluidos. Las fotos y sus esqueletos
 * comparten la misma geometría. Tarjetas 3:2 y dos columnas en móvil.
 */
export default function VirtualGrid({ items, renderItem, label, onEndReached, onRangeChange, overscan = 3 }) {
  const ref = useRef(null)
  const [width, setWidth] = useState(0)
  const [range, setRange] = useState([0, 8])

  useLayoutEffect(() => {
    const el = ref.current
    if (!el) return
    setWidth(el.clientWidth)
    const ro = new ResizeObserver(() => setWidth(el.clientWidth))
    ro.observe(el)
    return () => ro.disconnect()
  }, [])

  const narrow = width < 640
  const gap = narrow ? 8 : 12
  const cols = Math.max(1, narrow ? 2 : Math.floor((width + gap) / (220 + gap)))
  const itemW = width ? (width - gap * (cols - 1)) / cols : 0
  const itemH = Math.round(itemW * 2 / 3)
  const rowH = itemH + gap
  const rows = Math.ceil(items.length / cols)

  useEffect(() => {
    if (!rowH) return
    // cálculo O(1) directamente en cada evento (sin requestAnimationFrame, que algunos navegadores pausan);
    // setRange no repinta si el rango no cambia
    const update = () => {
      const el = ref.current
      if (!el) return
      const top = el.getBoundingClientRect().top
      const first = Math.max(0, Math.floor(-top / rowH) - overscan)
      const last = Math.min(rows - 1, Math.ceil((window.innerHeight - top) / rowH) + overscan)
      setRange((r) => (r[0] === first && r[1] === last ? r : [first, last]))
      onRangeChange?.(first * cols, Math.min(items.length, (last + 1) * cols))
      if (onEndReached && last >= rows - 1 - overscan) onEndReached()
    }
    update()
    window.addEventListener('scroll', update, { passive: true })
    window.addEventListener('resize', update)
    return () => { window.removeEventListener('scroll', update); window.removeEventListener('resize', update) }
  }, [rowH, rows, cols, items.length, overscan, onEndReached, onRangeChange])

  const [first, last] = range
  const from = first * cols, to = Math.min(items.length, (last + 1) * cols)
  return (
    <ul ref={ref} aria-label={label} className="relative" style={{ height: rows ? rows * rowH - gap : 0 }}>
      {width > 0 && items.slice(from, to).map((it, k) => {
        const i = from + k
        return renderItem(it, {
          position: 'absolute', top: Math.floor(i / cols) * rowH, left: (i % cols) * (itemW + gap), width: itemW, height: itemH,
        })
      })}
    </ul>
  )
}
