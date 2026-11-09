// Builds the shared UI into the two host bundles:
//   dashboard/dist/index.js + style.css  (web dashboard, IIFE, React from the dashboard SDK)
//   desktop/plugin.js                    (desktop app, ESM, imports react + @hermes/plugin-sdk only)
//   ui/dev/out/                          (standalone preview harness with demo data; `--dev`)
// Usage: node ui/build.mjs [--dev] [--watch]
import { createRequire } from 'node:module'
import path from 'node:path'
import { fileURLToPath } from 'node:url'

const here = path.dirname(fileURLToPath(import.meta.url))
const root = path.resolve(here, '..')
const require = createRequire(import.meta.url)

function loadEsbuild() {
  const candidates = [process.env.ESBUILD_PATH, 'esbuild',
    path.join(process.env.HOME || '', '.hermes/hermes-agent/node_modules/esbuild')].filter(Boolean)
  for (const c of candidates) {
    try { return require(c) } catch { /* try the next one */ }
  }
  throw new Error('esbuild not found: npm i -D esbuild, or set ESBUILD_PATH')
}

const esbuild = loadEsbuild()
const args = new Set(process.argv.slice(2))

// The stylesheet embeds its fonts as data URLs, so every host gets one self-contained file with no
// network fetches. JS hosts import it as text; this plugin bundles it first so the fonts are inlined.
const cssLoaders = { '.css': 'css', '.woff2': 'dataurl' }
const inlineCss = {
  name: 'inline-css',
  setup(build) {
    build.onLoad({ filter: /styles\.css$/ }, async (a) => {
      const out = await esbuild.build({ entryPoints: [a.path], bundle: true, write: false, minify: true, loader: cssLoaders, logLevel: 'silent' })
      return { contents: out.outputFiles[0].text, loader: 'text' }
    })
  },
}
const common = {
  bundle: true,
  jsx: 'transform',
  jsxFactory: 'React.createElement',
  jsxFragment: 'React.Fragment',
  target: ['es2020'],
  legalComments: 'none',
  logLevel: 'info',
  loader: { '.css': 'text' },
  minify: true,
  sourcemap: false,
  plugins: [inlineCss],
}

const builds = [
  {
    ...common,
    entryPoints: [path.join(here, 'hosts/dashboard.jsx')],
    outfile: path.join(root, 'dashboard/dist/index.js'),
    format: 'iife',
    alias: { react: path.join(here, 'hosts/react-dashboard.js') },
  },
  {
    ...common,
    entryPoints: [path.join(here, 'src/styles.css')],
    outfile: path.join(root, 'dashboard/dist/style.css'),
    loader: cssLoaders,
    plugins: [],
  },
  {
    ...common,
    entryPoints: [path.join(here, 'hosts/desktop.jsx')],
    outfile: path.join(root, 'desktop/plugin.js'),
    format: 'esm',
    external: ['react', 'react/jsx-runtime', '@hermes/plugin-sdk'],
  },
]

if (args.has('--dev')) {
  const nm = path.join(process.env.HOME || '', '.hermes/hermes-agent/node_modules')
  builds.push({
    ...common,
    entryPoints: [path.join(here, 'dev/harness.jsx')],
    outfile: path.join(here, 'dev/out/harness.js'),
    format: 'iife',
    nodePaths: [nm],
    minify: false,
    define: { 'process.env.NODE_ENV': '"development"' },
  })
}

if (args.has('--watch')) {
  for (const b of builds) (await esbuild.context(b)).watch()
  console.log('watching…')
} else {
  await Promise.all(builds.map((b) => esbuild.build(b)))
}
