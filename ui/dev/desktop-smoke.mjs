// Smoke test for desktop/plugin.js outside the desktop app: loads the built ESM file with a stub
// @hermes/plugin-sdk and the real React, checks that it imports only allowed specifiers, registers its
// contributions, and that its page and settings page render without throwing.
// Usage: node ui/dev/desktop-smoke.mjs  (needs react + react-dom resolvable, e.g. NODE_PATH)
import fs from 'node:fs'
import os from 'node:os'
import path from 'node:path'
import { fileURLToPath, pathToFileURL } from 'node:url'
import { createRequire } from 'node:module'

const here = path.dirname(fileURLToPath(import.meta.url))
const root = path.resolve(here, '../..')
const src = fs.readFileSync(path.join(root, 'desktop/plugin.js'), 'utf8')

const specifiers = [...src.matchAll(/(?:^|[;\s])(?:import|export)\s[^'"]*?from\s*['"]([^'"]+)['"]/g)].map((m) => m[1])
const bad = specifiers.filter((s) => !['react', 'react/jsx-runtime', '@hermes/plugin-sdk'].includes(s))
if (bad.length) throw new Error('disallowed imports: ' + bad.join(', '))
if (/\bimport\s*\(/.test(src)) throw new Error('dynamic import found')

const nm = process.env.REACT_NODE_MODULES || path.join(os.homedir(), '.hermes/hermes-agent/node_modules')
const tmp = fs.mkdtempSync(path.join(process.env.TMPDIR || os.tmpdir(), 'at-desktop-smoke-'))
fs.mkdirSync(path.join(tmp, 'node_modules/@hermes/plugin-sdk'), { recursive: true })
fs.writeFileSync(path.join(tmp, 'node_modules/@hermes/plugin-sdk/package.json'), '{"name":"@hermes/plugin-sdk","type":"module","main":"index.js"}')
fs.writeFileSync(path.join(tmp, 'node_modules/@hermes/plugin-sdk/index.js'), `
export const ROUTES_AREA = 'routes', SIDEBAR_NAV_AREA = 'sidebar.nav', PALETTE_AREA = 'palette'
export const host = { navigate: (p) => globalThis.__nav.push(p), notify() {} }
`)
for (const m of ['react', 'react-dom', 'scheduler']) fs.symlinkSync(path.join(nm, m), path.join(tmp, 'node_modules', m))
fs.writeFileSync(path.join(tmp, 'plugin.mjs'), src)

globalThis.__nav = []
const listeners = {}
globalThis.window = { addEventListener: (t, f) => { (listeners[t] ||= []).push(f) }, removeEventListener() {}, dispatchEvent() {}, innerWidth: 1280, innerHeight: 800, localStorage: { getItem: () => null, setItem() {} } }
globalThis.document = { getElementById: () => null, createElement: () => ({ remove() {} }), head: { appendChild() {} }, documentElement: {} }
globalThis.CustomEvent = class { constructor(t, o) { this.type = t; this.detail = o && o.detail } }

const plugin = (await import(pathToFileURL(path.join(tmp, 'plugin.mjs')).href)).default
const contributions = []
let settingsPage = null
const disposers = []
const ctx = {
  registerMany: (cs) => { contributions.push(...cs); return () => {} },
  register: (c) => { contributions.push(c); return () => {} },
  registerSettingsPage: (p) => { settingsPage = p; return () => {} },
  rest: async () => ({ ok: true }),
  onDispose: (f) => disposers.push(f),
}
plugin.register(ctx)
const req = createRequire(path.join(tmp, 'plugin.mjs'))
const { renderToString } = req('react-dom/server')
const byArea = Object.fromEntries(contributions.map((c) => [c.area + ':' + c.id, c]))
const route = contributions.find((c) => c.area === 'routes')
const html = renderToString(route.render())
const settingsHtml = renderToString(settingsPage.render())
const palette = contributions.filter((c) => c.area === 'palette')
palette[1].data.run()
const report = {
  id: plugin.id,
  contributions: Object.keys(byArea),
  routePath: route.data.path,
  nav: contributions.find((c) => c.area === 'sidebar.nav').data,
  palette: palette.map((p) => p.data.label),
  paletteNavigates: globalThis.__nav,
  pageRendered: html.includes('at-root'),
  settingsRendered: settingsHtml.includes('at-root'),
  disposers: disposers.length,
}
console.log(JSON.stringify(report, null, 1))
if (!report.pageRendered || !report.settingsRendered || plugin.id !== 'alchemy-task') process.exit(1)
fs.rmSync(tmp, { recursive: true, force: true })
