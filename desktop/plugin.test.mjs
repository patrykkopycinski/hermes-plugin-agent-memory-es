// node:test suite for MemoryPage.load (desktop/plugin.js).
// plugin.js imports '@hermes/plugin-sdk', 'react/jsx-runtime' and 'react',
// none of which resolve outside the Hermes desktop app — the loader below
// strips those imports and stubs them, then re-exports MemoryPage.
import test from 'node:test'
import assert from 'node:assert/strict'
import { readFileSync, writeFileSync, mkdtempSync } from 'node:fs'
import { tmpdir } from 'node:os'
import { join, dirname } from 'node:path'
import { pathToFileURL } from 'node:url'

const pluginSrc = readFileSync(join(dirname(new URL(import.meta.url).pathname), 'plugin.js'), 'utf8')

// Hook fakes injected into the module under test. toString()-based injection
// loses closures, so the counter must live inside the stub text itself.
const hooksPrelude = `
const __slots = []
let __i = 0
const useState = (initial) => {
  if (__i >= __slots.length) __slots.push({ value: initial })
  const slot = __slots[__i++]
  return [slot.value, (v) => { slot.value = v }]
}
const useCallback = (fn) => fn
const useEffect = (fn) => { fn() }
`

const stubs = `
const ROUTES_AREA = 'routes'
const SIDEBAR_NAV_AREA = 'sidebar'
const jsx = (t, p) => ({ t, p })
const jsxs = (t, p) => ({ t, p })
`

function loadPlugin() {
  const stripped = pluginSrc.replace(/^import .*$/gm, '')
  const src = stubs + hooksPrelude + stripped + '\nexport { MemoryPage, __slots }\n'
  const dir = mkdtempSync(join(tmpdir(), 'ames-plugin-test-'))
  const file = join(dir, 'plugin-under-test.mjs')
  writeFileSync(file, src)
  return import(pathToFileURL(file).href)
}

async function runLoad(restImpl) {
  const { MemoryPage, __slots } = await loadPlugin()
  MemoryPage({ rest: restImpl }) // first render; useEffect fires load()
  await new Promise((r) => setTimeout(r, 0)) // let the async load settle
  const read = () => __slots.map((s) => s.value)
  return { data: read()[0], error: read()[1], loading: read()[2] }
}

test('load: rest resolves payload -> data set, error null, loading false', async () => {
  const payload = { owner_id: 'o1', counts: {}, recent_semantic: [], models: [], drafts: [], pages: [] }
  const { data, error, loading } = await runLoad(async () => payload)
  assert.deepEqual(data, payload)
  assert.equal(error, null)
  assert.equal(loading, false)
})

test('load: rest rejects -> error message surfaced, data null, loading false', async () => {
  const { data, error, loading } = await runLoad(async () => { throw new Error('502 x') })
  assert.equal(error, '502 x')
  assert.equal(data, null)
  assert.equal(loading, false)
})

test('regression: rest returning a plain object (no .text/.json) must not throw "is not a function"', async () => {
  // ctx.rest resolves to parsed JSON, never a fetch Response. If load ever
  // goes back to treating it as one (r.ok / r.text / r.json), this fails.
  const { data, error } = await runLoad(async () => ({ owner_id: 'o1' }))
  assert.equal(error, null)
  assert.equal(data.owner_id, 'o1')
  assert.ok(!String(error).includes('is not a function'))
})
