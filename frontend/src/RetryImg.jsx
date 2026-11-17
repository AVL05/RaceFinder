import { forwardRef, useEffect, useState } from 'react'

const DELAYS = [1000, 2000, 4000, 8000, 15000]

/**
 * <img> que se recupera sola: si la API no responde un momento (reinicio, equipo saturado…),
 * reintenta con espera creciente en vez de quedarse rota para siempre.
 */
const RetryImg = forwardRef(function RetryImg({ src, onError, ...props }, ref) {
  const [attempt, setAttempt] = useState(0)
  useEffect(() => { setAttempt(0) }, [src])
  const url = attempt === 0 ? src : `${src}${src.includes('?') ? '&' : '?'}retry=${attempt}`
  return (
    <img ref={ref} {...props} src={url}
      onError={(e) => {
        if (attempt < DELAYS.length) {
          const next = attempt + 1
          setTimeout(() => setAttempt((a) => (a === next - 1 ? next : a)), DELAYS[attempt])
        } else onError?.(e)
      }} />
  )
})

export default RetryImg
