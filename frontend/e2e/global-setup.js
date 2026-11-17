import { execFileSync } from 'node:child_process'
import fs from 'node:fs'
import path from 'node:path'
import { fileURLToPath } from 'node:url'

const here = path.dirname(fileURLToPath(import.meta.url))

export default async function globalSetup() {
  const out = path.join(here, '.fixtures', 'photos')
  fs.rmSync(out, { recursive: true, force: true })
  const py = path.join(here, '..', '..', 'backend', '.venv', 'Scripts', 'python.exe')
  execFileSync(py, ['-W', 'ignore', path.join(here, 'make_fixtures.py'), path.join(here, '.fixtures', 'cache'), out], { stdio: 'inherit' })
  fs.mkdirSync(path.join(here, '..', 'e2e-results'), { recursive: true })
}
