import { test, expect } from '@playwright/test'
import { readFile } from 'node:fs/promises'

const fixture = new URL('./.fixtures/photos/a_dorsal.jpg', import.meta.url)
const gallery = (page) => page.getByRole('list', { name: 'Galería' })

test('organizar carreras, buscar y exportar una selección desde móvil', async ({ page, request }, testInfo) => {
  await page.setViewportSize({ width: 375, height: 812 })
  const suffix = Date.now()
  const firstName = `Carrera urbana ${suffix}`
  const secondName = `Trail ${suffix}`
  const firstPhoto = `Águila-${suffix}.jpg`
  const secondPhoto = `Bosque-${suffix}.jpg`
  const source = await readFile(fixture)
  const file = (name, variant) => ({
    name, mimeType: 'image/jpeg',
    buffer: Buffer.concat([source, Buffer.from(`${suffix}${variant}`)]),
  })
  const albums = []

  try {
    await page.goto('/')
    await page.getByRole('button', { name: 'Nuevo álbum' }).click()
    const dialog = page.getByRole('dialog', { name: 'Nuevo álbum' })
    await dialog.getByLabel('Nombre del álbum').fill(firstName)
    await dialog.getByLabel('Máximo').fill('800')
    await dialog.getByRole('button', { name: 'Crear álbum' }).click()
    await expect(page.getByRole('heading', { name: firstName })).toBeVisible()
    const first = Number(new URL(page.url()).searchParams.get('album'))
    albums.push(first)
    expect(first).toBeGreaterThan(0)
    await expect(page.getByRole('heading', { name: 'Álbum vacío' })).toBeVisible()

    await page.locator('input[type=file][multiple]:not([webkitdirectory])').setInputFiles(file(firstPhoto, 'a'))
    await expect(gallery(page).getByRole('button', { name: `Abrir ${firstPhoto}` })).toBeVisible({ timeout: 30_000 })
    const { photos: [firstRecord] } = await (await request.get('/api/photos', { params: { album: first } })).json()
    expect((await request.post(`/api/photos/${firstRecord.id}/bibs`, { data: { number: '184' } })).ok()).toBeTruthy()

    const secondResponse = await request.post('/api/albums', { data: { name: secondName } })
    expect(secondResponse.status()).toBe(201)
    const second = (await secondResponse.json()).id
    albums.push(second)
    const uploaded = await request.post(`/api/photos?album=${second}`, { multipart: { files: file(secondPhoto, 'bb') } })
    expect(uploaded.ok()).toBeTruthy()
    const secondId = (await uploaded.json()).results[0].id
    expect((await request.post(`/api/photos/${secondId}/bibs`, { data: { number: '184' } })).ok()).toBeTruthy()

    await page.goto(`/?dorsal=184&album=${first}`)
    const matches = page.getByRole('list', { name: 'Coincidencias seguras' })
    await expect(matches.getByRole('button', { name: `Abrir ${firstPhoto}` })).toBeVisible()
    await expect(matches.getByRole('button', { name: `Abrir ${secondPhoto}` })).toHaveCount(0)
    await page.getByRole('button', { name: 'Volver al álbum' }).click()

    await gallery(page).getByRole('button', { name: `Marcar ${firstPhoto} como favorita` }).click()
    await expect(gallery(page).getByRole('button', { name: `Quitar ${firstPhoto} de favoritas` })).toBeVisible()
    await page.reload()
    await page.getByRole('tab', { name: 'Favoritas 1' }).click()
    const filename = page.getByRole('searchbox', { name: 'Buscar por nombre de archivo' })
    await filename.fill('fichero inexistente')
    await expect(page.getByText(/No hay archivos que coincidan/)).toBeVisible()
    await filename.fill('águila')
    await expect(gallery(page).getByRole('listitem')).toHaveCount(1)
    await page.getByLabel('Orden').selectOption('name')
    const csvUrl = await page.getByRole('link', { name: 'Catálogo CSV' }).getAttribute('href')
    expect(await (await request.get(csvUrl)).text()).toContain(firstPhoto)
    expect(await page.evaluate(() => document.documentElement.scrollWidth - document.documentElement.clientWidth)).toBe(0)
    await expect.poll(() => gallery(page).locator('img').first().evaluate((img) => img.naturalWidth)).toBeGreaterThan(0)
    await page.screenshot({ path: testInfo.outputPath('catalogo-movil.png'), fullPage: true })

    await page.getByRole('button', { name: 'Seleccionar todas' }).click()
    await page.getByRole('button', { name: 'Organizar selección en álbumes' }).click()
    const assignment = page.getByRole('dialog', { name: 'Organizar selección' })
    await assignment.getByLabel('Álbum de destino').selectOption(String(second))
    await assignment.getByRole('button', { name: 'Añadir al álbum' }).click()
    await expect(assignment).toHaveCount(0)
    expect((await (await request.get('/api/stats', { params: { album: second } })).json()).photos).toBe(2)

    await page.getByRole('button', { name: 'Organizar selección en álbumes' }).click()
    await assignment.getByRole('button', { name: 'Quitar del álbum actual' }).click()
    await expect(page.getByRole('heading', { name: 'Álbum vacío' })).toBeVisible()
    expect((await request.get(`/api/photos/${firstRecord.id}`)).ok()).toBeTruthy()
  } finally {
    const { photos } = await (await request.get('/api/photos', { params: { filename: String(suffix) } })).json()
    if (photos.length) await request.post('/api/photos/delete', { data: { ids: photos.map((photo) => photo.id) } })
    for (const album of albums) await request.delete(`/api/albums/${album}`)
  }
})
