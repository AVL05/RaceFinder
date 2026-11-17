// pnpm run dev  ->  prepara lo que falte (entorno Python, dependencias) y arranca API + interfaz.
// pnpm run dev --network -> permite abrir la interfaz desde otros dispositivos de la red.
// pnpm run start -> igual, pero sirve la interfaz compilada desde la API (sin recarga en caliente).
import { spawn, spawnSync } from 'node:child_process'
import { createHash } from 'node:crypto'
import fs from 'node:fs'
import net from 'node:net'
import { networkInterfaces } from 'node:os'
import path from 'node:path'
import { fileURLToPath } from 'node:url'

const ROOT = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..')
const BACKEND = path.join(ROOT, 'backend')
const FRONTEND = path.join(ROOT, 'frontend')
const VENV_PY = path.join(BACKEND, '.venv', process.platform === 'win32' ? 'Scripts/python.exe' : 'bin/python')
const PROD = process.argv.includes('--prod')
const NETWORK = process.argv.includes('--network')
const isWin = process.platform === 'win32'

const c = { dim: '\x1b[2m', red: '\x1b[31m', green: '\x1b[32m', yellow: '\x1b[33m', cyan: '\x1b[36m', mag: '\x1b[35m', bold: '\x1b[1m', reset: '\x1b[0m' }
const log = (msg) => console.log(`${c.bold}${c.mag}racefinder${c.reset} ${msg}`)
const fail = (msg) => { console.error(`${c.red}${c.bold}✖ ${msg}${c.reset}`); process.exit(1) }

function run(cmd, args, opts = {}) {
  // los .cmd de Windows (pnpm) necesitan shell: se pasa como una sola orden para evitar avisos de Node
  const r = path.isAbsolute(cmd)
    ? spawnSync(cmd, args, { stdio: 'inherit', ...opts })
    : spawnSync([cmd, ...args].join(' '), { stdio: 'inherit', shell: true, ...opts })
  if (r.status !== 0) fail(`Falló: ${cmd} ${args.join(' ')}`)
}
const VITE = path.join(FRONTEND, 'node_modules', 'vite', 'bin', 'vite.js')

function findSystemPython() {
  const local = process.env.LOCALAPPDATA || ''
  const candidates = [
    ...['313', '312', '311'].map((v) => [path.join(local, 'Programs', 'Python', `Python${v}`, 'python.exe'), []]),
    ['py', ['-3.12']], ['py', ['-3']], ['python3', []], ['python', []],
  ]
  for (const [cmd, pre] of candidates) {
    if (path.isAbsolute(cmd) && !fs.existsSync(cmd)) continue
    const r = spawnSync(cmd, [...pre, '-c', 'import sys;print(sys.version_info[:2]>=(3,10), sys.executable)'], { encoding: 'utf-8', shell: false })
    if (r.status === 0 && r.stdout.startsWith('True') && !r.stdout.includes('WindowsApps')) return [cmd, pre]
  }
  return null
}

function ensurePython() {
  if (!fs.existsSync(VENV_PY)) {
    const py = findSystemPython()
    if (!py) fail('No encuentro Python 3.10+. Instálalo con:  winget install Python.Python.3.12 --scope user')
    log('Creando entorno Python (solo la primera vez)…')
    run(py[0], [...py[1], '-m', 'venv', path.join(BACKEND, '.venv')])
  }
  const req = path.join(BACKEND, 'requirements.txt')
  const stamp = path.join(BACKEND, '.venv', '.racefinder-req')
  const hash = createHash('sha256').update(fs.readFileSync(req)).digest('hex')
  if (!fs.existsSync(stamp) || fs.readFileSync(stamp, 'utf-8') !== hash) {
    log('Instalando dependencias de Python (solo cuando cambian)…')
    run(VENV_PY, ['-m', 'pip', 'install', '--disable-pip-version-check', '-q', '-r', req])
    fs.writeFileSync(stamp, hash)
  }
}

function ensureNode() {
  if (!fs.existsSync(VITE)) {
    log('Instalando dependencias de la interfaz…')
    run('pnpm', ['install'], { cwd: ROOT })
  }
}

const canListen = (port, host) => new Promise((resolve) => {
  const s = net.createServer()
  s.once('error', () => resolve(false))
  s.once('listening', () => s.close(() => resolve(true)))
  s.listen(port, host)
})

async function freePort(port, hosts = ['127.0.0.1']) {
  for (const host of hosts) {
    if (!(await canListen(port, host))) return freePort(port + 1, hosts)
  }
  return port
}

async function waitHealthy(port, child, ms = 90_000) {
  const t = Date.now()
  while (Date.now() - t < ms) {
    if (child.exitCode !== null) return false
    try { if ((await fetch(`http://127.0.0.1:${port}/api/health`)).ok) return true } catch { /* aún arrancando */ }
    await new Promise((r) => setTimeout(r, 400))
  }
  return false
}

const children = []
function start(name, color, cmd, args, opts) {
  const p = spawn(cmd, args, { ...opts, env: { ...process.env, FORCE_COLOR: '1', ...opts.env } })
  const tag = `${color}${name.padEnd(3)}${c.reset} │ `
  const pipe = (stream, out) => {
    let buf = ''
    stream.on('data', (d) => {
      buf += d.toString()
      const lines = buf.split(/\r?\n/); buf = lines.pop()
      for (const l of lines) if (l.trim()) out.write(tag + l + '\n')
    })
  }
  pipe(p.stdout, process.stdout); pipe(p.stderr, process.stderr)
  p.on('exit', (code) => {
    if (stopping || p.restarting) return
    if (name === 'api' && !PROD && apiReady) { log(`${c.red}La API se ha detenido por un error. Corrígelo y guarda: se reiniciará sola.${c.reset}`); return }
    log(`${c.red}${name} se ha detenido (código ${code}). Cerrando…${c.reset}`); stop(1)
  })
  children.push(p)
  return p
}

function killTree(p) {
  if (p.exitCode !== null) return Promise.resolve()
  return new Promise((resolve) => {
    p.once('exit', resolve)
    if (isWin) spawnSync('taskkill', ['/pid', String(p.pid), '/T', '/F'], { stdio: 'ignore' })
    else p.kill('SIGTERM')
  })
}

let stopping = false
let apiReady = false
function stop(code = 0) {
  if (stopping) return
  stopping = true
  for (const p of children) {
    if (p.exitCode !== null) continue
    if (isWin) spawnSync('taskkill', ['/pid', String(p.pid), '/T', '/F'], { stdio: 'ignore' })
    else p.kill('SIGTERM')
  }
  process.exit(code)
}
process.on('SIGINT', () => stop(0))
process.on('SIGTERM', () => stop(0))

// ---------------------------------------------------------------------------
ensurePython()
ensureNode()

const apiPort = await freePort(Number(process.env.RACEFINDER_API_PORT_START) || 8000)
const apiEnv = { RACEFINDER_DEV: PROD ? '0' : '1', PYTHONUNBUFFERED: '1' }
if (PROD) {
  log('Compilando la interfaz…')
  run(process.execPath, [VITE, 'build'], { cwd: FRONTEND })
}
const uvicornArgs = ['-m', 'uvicorn', 'app.main:get_app', '--factory', '--host', '127.0.0.1', '--port', String(apiPort), '--log-level', 'warning']
const startApi = () => start('api', c.cyan, VENV_PY, uvicornArgs, { cwd: BACKEND, env: apiEnv })
log(`Arrancando API en http://127.0.0.1:${apiPort} …`)
let api = startApi()
if (!(await waitHealthy(apiPort, api))) fail('La API no ha arrancado. Revisa los mensajes de arriba.')
apiReady = true

// Recarga propia del backend al guardar un .py (el --reload de uvicorn se cuelga en Windows sin consola).
// La cola de análisis es persistente: tras reiniciar continúa donde iba.
if (!PROD) {
  let timer = null, busy = false
  fs.watch(path.join(BACKEND, 'app'), { recursive: true }, (_e, file) => {
    if (!file || !file.endsWith('.py')) return
    clearTimeout(timer)
    timer = setTimeout(async () => {
      if (busy || stopping) return
      busy = true
      log(`${c.dim}Cambios en ${file}: reiniciando la API…${c.reset}`)
      api.restarting = true
      await killTree(api)
      api = startApi()
      if (await waitHealthy(apiPort, api, 60_000)) log(`${c.dim}API lista${c.reset}`)
      busy = false
    }, 300)
  })
}

if (PROD) {
  log(`${c.green}${c.bold}Listo → http://127.0.0.1:${apiPort}${c.reset}  (Ctrl+C para salir)`)
  if (!process.env.RACEFINDER_NO_OPEN) {
  const opener = isWin ? ['cmd', ['/c', 'start', '', `http://127.0.0.1:${apiPort}`]] : ['xdg-open', [`http://127.0.0.1:${apiPort}`]]
  spawn(opener[0], opener[1], { stdio: 'ignore', detached: true }).unref()
  }
} else {
  const webHost = NETWORK ? '0.0.0.0' : '127.0.0.1'
  // On Windows, a wildcard bind can succeed even if the port is taken on a specific IP.
  const webHosts = NETWORK && isWin
    ? [...Object.values(networkInterfaces()).flat().filter(({ family }) => family === 'IPv4').map(({ address }) => address), webHost]
    : [webHost]
  const webPort = await freePort(5173, webHosts)
  start('web', c.green, process.execPath, [VITE, '--host', webHost, '--port', String(webPort), '--strictPort', ...(process.env.RACEFINDER_NO_OPEN ? [] : ['--open'])], {
    cwd: FRONTEND, env: { RACEFINDER_API_PORT: String(apiPort) },
  })
  log(`${c.green}${c.bold}Abre → http://127.0.0.1:${webPort}${c.reset}  (Ctrl+C para salir)`)
}
