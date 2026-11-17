// Flujo completo en un navegador real: importar, leer dorsales, buscar, revisar dudosos,
// consentimiento facial, búsqueda por cara y borrado de datos biométricos.
// Fixtures funcionales (ver make_fixtures.py): NO miden precisión.
import { test, expect } from '@playwright/test'
import fs from 'node:fs'
import path from 'node:path'
import { fileURLToPath } from 'node:url'

const here = path.dirname(fileURLToPath(import.meta.url))
const PHOTOS = path.join(here, '.fixtures', 'photos')
const SHOTS = path.join(here, '..', 'e2e-results')
const files = () => fs.readdirSync(PHOTOS).filter((f) => f.endsWith('.jpg')).map((f) => path.join(PHOTOS, f))
const shot = (page, name) => page.screenshot({ path: path.join(SHOTS, `${name}.png`) })
const stats = async (page) => (await page.request.get('/api/stats')).json()
const idsByName = async (page) => Object.fromEntries((await (await page.request.get('/api/photos?limit=100')).json()).photos.map((p) => [p.name, p.id]))

async function waitIdle(page, { faces = false } = {}) {
  await expect.poll(async () => {
    const s = await stats(page)
    const ocr = (s.ocr.pending || 0) + (s.ocr.processing || 0)
    const f = faces ? (s.faces.status.pending || 0) + (s.faces.status.processing || 0) : 0
    return s.photos > 0 && ocr === 0 && f === 0
  }, { timeout: 150_000, intervals: [1000] }).toBe(true)
}

test.describe.configure({ mode: 'serial' })

test('importar: todas las fotos quedan en el catálogo, con o sin coincidencias', async ({ page }) => {
  await page.goto('/')
  await expect(page.getByRole('heading', { name: 'Encuentra tus fotos de la carrera' })).toBeVisible()
  const all = files()
  await page.locator('input[type=file][multiple]:not([webkitdirectory])').setInputFiles(all)
  await expect(page.getByText('Importación terminada')).toBeVisible({ timeout: 60_000 })
  await waitIdle(page)
  await page.reload()
  await expect(page.getByRole('tab', { name: new RegExp(`Todas ${all.length}`) })).toBeVisible()
  await expect(page.getByRole('list', { name: 'Galería' }).getByRole('listitem')).toHaveCount(all.length)
  // la foto sin nada sigue en "Sin dorsal leído"
  await page.getByRole('tab', { name: /Sin dorsal leído/ }).click()
  await expect(page.getByRole('button', { name: 'Abrir solo_fondo.jpg' })).toBeVisible()
  await shot(page, '1440-catalogo')
})

test('búsqueda por dorsal y revisión manual (añadir y descartar) sin perder fotos', async ({ page }) => {
  await page.goto('/?dorsal=184')
  const sure = page.getByRole('list', { name: 'Coincidencias seguras' })
  await expect(sure.getByRole('listitem')).toHaveCount(2)
  await expect(sure.getByRole('button', { name: 'Abrir a_dorsal.jpg' })).toBeVisible()
  await expect(sure.getByRole('button', { name: 'Abrir a_y_b_dorsales.jpg' })).toBeVisible()

  // revisar: añadir a mano el 184 a una foto donde no se lee y después descartarlo
  const ids = await idsByName(page)
  await page.goto('/')
  await page.getByRole('button', { name: 'Abrir a_sin_dorsal.jpg' }).click()
  const dlg = page.getByRole('dialog')
  await dlg.getByLabel('Añadir un dorsal que falta').fill('184')
  await dlg.getByRole('button', { name: 'Añadir dorsal' }).click()
  await expect(dlg.getByText('a mano')).toBeVisible()
  await page.keyboard.press('Escape')
  await page.goto('/?dorsal=184')
  await expect(sure.getByRole('listitem')).toHaveCount(3)
  await sure.getByRole('button', { name: 'Abrir a_sin_dorsal.jpg' }).click()
  await dlg.getByRole('button', { name: 'Descartar dorsal 184' }).click()
  await expect(dlg.getByText('ninguno leído')).toBeVisible()
  await page.keyboard.press('Escape')
  await expect(sure.getByRole('listitem')).toHaveCount(2)
  const photo = await (await page.request.get(`/api/photos/${ids['a_sin_dorsal.jpg']}`)).json()
  expect(photo.id).toBe(ids['a_sin_dorsal.jpg'])  // descartar no borra la foto
})

test('consentimiento: sin marcar la casilla no se activa; la API también lo exige', async ({ page }) => {
  const r = await page.request.put('/api/settings', { data: { mode: 'balanced', faces_enabled: true } })
  expect(r.status()).toBe(422)
  await page.goto('/?dorsal=184')
  await page.getByRole('button', { name: 'Buscar también por la cara' }).click()
  const dlg = page.getByRole('dialog', { name: 'Buscar también por la cara' })
  await expect(dlg.getByRole('button', { name: 'Activar' })).toBeDisabled()
  await shot(page, '1440-consentimiento')
  await dlg.getByRole('button', { name: 'Ahora no' }).click()
  expect((await stats(page)).faces.enabled).toBe(false)
  expect((await stats(page)).faces.count).toBe(0)                       // nada se ha procesado
})

test('búsqueda por cara a partir del dorsal: encuentra las fotos sin dorsal y no las de otra persona', async ({ page }) => {
  await page.goto('/?dorsal=184')
  await page.getByRole('button', { name: 'Buscar también por la cara' }).click()
  const dlg = page.getByRole('dialog', { name: 'Buscar también por la cara' })
  await dlg.getByRole('checkbox').check()
  await dlg.getByRole('button', { name: 'Activar' }).click()
  await waitIdle(page, { faces: true })
  await page.reload()
  const section = page.getByRole('region', { name: 'Búsqueda por cara' })
  await expect(section).toBeVisible()
  await expect(section.getByRole('button', { name: 'Quitar esta cara de la búsqueda' })).toHaveCount(2)   // las 2 caras sobre el 184
  const byFace = page.getByRole('list', { name: 'Coincidencias por cara' })
  await expect(byFace.getByRole('listitem')).toHaveCount(2)
  await expect(byFace.getByRole('button', { name: 'Abrir a_sin_dorsal.jpg' })).toBeVisible()
  await expect(byFace.getByRole('button', { name: 'Abrir b_y_a_sin_dorsal.jpg' })).toBeVisible()
  await expect(page.getByRole('button', { name: 'Abrir b_sin_dorsal.jpg' })).toHaveCount(0)
  await expect(page.getByRole('button', { name: 'Abrir b_dorsal.jpg' })).toHaveCount(0)
  await shot(page, '1440-busqueda-por-cara')

  // desmarcar todas las caras vacía los resultados por cara, pero no toca los del dorsal
  const selectedFaces = section.getByRole('button', { name: 'Quitar esta cara de la búsqueda' })
  while (await selectedFaces.count()) await selectedFaces.first().click()
  await expect(byFace).toHaveCount(0)
  await expect(page.getByRole('list', { name: 'Coincidencias seguras' }).getByRole('listitem')).toHaveCount(2)

  await page.setViewportSize({ width: 390, height: 844 })
  await page.reload()
  await expect(page.getByRole('list', { name: 'Coincidencias por cara' }).getByRole('listitem')).toHaveCount(2)
  const overflow = await page.evaluate(() => document.documentElement.scrollWidth - document.documentElement.clientWidth)
  expect(overflow).toBeLessThanOrEqual(0)
  await shot(page, '390-busqueda-por-cara')
})

test('borrado de datos faciales: vectores, recortes y acceso', async ({ page }) => {
  const before = await stats(page)
  expect(before.faces.count).toBeGreaterThan(0)
  const cand = await (await page.request.get('/api/faces/for-bib?bib=184')).json()
  const fid = cand.faces[0].id
  expect((await page.request.get(`/api/faces/${fid}/crop`)).status()).toBe(200)

  await page.goto('/')
  page.once('dialog', (d) => d.accept())
  await page.getByRole('button', { name: 'Ajustes' }).click()
  await page.getByRole('button', { name: /Borrar todos los datos faciales/ }).click()
  await expect(page.getByText(/Datos faciales borrados/)).toBeVisible()

  const after = await stats(page)
  expect(after.faces.count).toBe(0)
  expect(after.faces.enabled).toBe(false)
  expect((await page.request.get(`/api/faces/${fid}/crop`)).status()).toBe(409)
  expect((await page.request.get('/api/faces/for-bib?bib=184')).status()).toBe(409)
  expect(after.photos).toBe(before.photos)                                // las fotos siguen ahí
  await page.goto('/?dorsal=184')
  await expect(page.getByRole('button', { name: 'Buscar también por la cara' })).toBeVisible()
})

test('etiquetado para evaluación: dorsales legibles y corredores sin dorsal legible', async ({ page }) => {
  await page.goto('/')
  await page.getByRole('button', { name: 'Ajustes' }).click()
  await page.getByRole('button', { name: /Medir la precisión/ }).click()
  const lab = page.getByTestId('labeler')
  await expect(lab).toBeVisible()
  await lab.getByLabel('Corredores que salen sin dorsal legible').fill('184')
  await page.keyboard.press('Enter')
  await lab.getByLabel('Gorra / visera').check()
  await lab.getByRole('button', { name: 'Sin dorsal legible' }).click()
  const labeledPhotos = async () => (await (await page.request.get('/api/eval/photos?state=labeled')).json()).photos
  await expect.poll(async () => (await labeledPhotos()).length).toBe(1)
  const labeled = await labeledPhotos()
  expect(labeled[0].label).toMatchObject({ state: 'no_bib', bibs: [], present: ['184'], tags: ['gorra'] })
})

test('eliminar todas las fotos de una vez, con confirmación escrita', async ({ page }) => {
  const before = await stats(page)
  expect(before.photos).toBeGreaterThan(0)
  await page.goto('/?dorsal=184')
  await page.getByRole('button', { name: 'Ajustes' }).click()
  await expect(page.getByText(`${before.photos} fotos en RaceFinder.`)).toBeVisible()
  await page.getByRole('button', { name: /Eliminar todas las fotos/ }).click()
  const dlg = page.getByRole('dialog', { name: 'Eliminar todas las fotos' })
  const go = dlg.getByRole('button', { name: 'Eliminar todo' })
  await expect(go).toBeDisabled()
  await dlg.getByLabel(/para confirmar/).fill('eliminar fotos')
  await expect(go).toBeDisabled()                                   // la palabra debe ser exacta
  await dlg.getByLabel(/para confirmar/).fill('ELIMINAR')
  await shot(page, '1440-eliminar-todo')
  await go.click()
  await expect(page.getByText(`Se han eliminado ${before.photos} fotos`)).toBeVisible()
  await expect(page.getByRole('heading', { name: 'Encuentra tus fotos de la carrera' })).toBeVisible()
  await expect(page).toHaveURL(/\/$/)                                // la búsqueda anterior se limpia
  const after = await stats(page)
  expect(after.photos).toBe(0)
  expect(after.faces.count).toBe(0)
  // se puede volver a importar con normalidad
  await page.locator('input[type=file][multiple]:not([webkitdirectory])').setInputFiles(files().slice(0, 1))
  await expect(page.getByText('Importación terminada')).toBeVisible()
  await expect(page.getByText(/1<\/strong> nuevas|1 nuevas/)).toBeVisible()
})
