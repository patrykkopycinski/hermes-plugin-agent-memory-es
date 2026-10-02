/**
 * agent-memory-es inspector — read-only desktop page for the ames memory bank.
 * Shows what the current owner's key can see: per-tier counts by visibility,
 * recent semantic facts, active mental models (staleness flagged), worker
 * drafts, knowledge pages. Manual Refresh button only — no polling, no writes.
 *
 * Ships inside the agent_memory_es plugin package (desktop/ half); the backend
 * proxy lives in dashboard/plugin_api.py (ctx.rest → /api/plugins/<id>/stats).
 */
import { ROUTES_AREA, SIDEBAR_NAV_AREA } from '@hermes/plugin-sdk'
import { jsx, jsxs } from 'react/jsx-runtime'
import { useCallback, useEffect, useState } from 'react'

const ID = 'ames-inspector'

function Card({ title, children }) {
  return jsxs('div', {
    className: 'rounded-lg border border-(--ui-border) bg-(--ui-card) p-3',
    children: [
      jsx('div', {
        className: 'mb-2 text-xs font-semibold uppercase tracking-wide text-(--ui-text-tertiary)',
        children: title,
      }),
      children,
    ],
  })
}

function VisChips({ byVisibility }) {
  return jsxs('div', { className: 'flex gap-1.5', children: [
    ['private', 'team', 'common'].map((v) =>
      byVisibility[v] != null && jsxs('span', {
        className: 'rounded px-1.5 py-0.5 text-[0.6875rem] tabular-nums',
        style: { background: 'var(--ui-bg-tertiary)' },
        children: [jsx('span', { className: 'text-(--ui-text-tertiary)', children: v + ' ' }), byVisibility[v]],
      }, v)),
  ] })
}

function MemoryPage({ rest }) {
  const [data, setData] = useState(null)
  const [error, setError] = useState(null)
  const [loading, setLoading] = useState(false)

  const load = useCallback(async () => {
    setLoading(true); setError(null)
    try {
      const r = await rest('/stats')
      if (!r.ok) throw new Error(`${r.status} ${await r.text()}`)
      setData(await r.json())
    } catch (e) {
      setError(String(e.message || e))
    } finally {
      setLoading(false)
    }
  }, [rest])

  useEffect(() => { load() }, [load])

  return jsxs('div', {
    className: 'flex h-full flex-col gap-3 overflow-auto p-4 text-sm',
    children: [
      jsxs('div', { className: 'flex items-center justify-between', children: [
        jsxs('div', { className: 'font-medium', children: [
          'Memory bank',
          data && jsx('span', {
            className: 'ml-2 text-(--ui-text-tertiary)',
            children: data.owner_id,
          }),
        ] }),
        jsx('button', {
          type: 'button',
          onClick: load,
          disabled: loading,
          className: 'rounded-md border border-(--ui-border) px-3 py-1 text-xs transition-colors hover:bg-(--ui-bg-tertiary) disabled:opacity-50',
          children: loading ? 'Loading…' : 'Refresh',
        }),
      ] }),
      error && jsx('div', {
        className: 'rounded-md border border-(--ui-danger,red) p-3 text-xs',
        children: error,
      }),
      data && jsxs('div', { className: 'grid gap-3 lg:grid-cols-2', children: [
        jsxs('div', { className: 'flex flex-col gap-3', children: [
          jsxs(Card, { title: 'Facts by tier', children: [
            ['episodic', 'semantic', 'procedural'].map((k) => {
              const c = data.counts[k] || { total: 0, by_visibility: {} }
              return jsxs('div', { className: 'flex items-center justify-between py-0.5', children: [
                jsxs('span', { children: [k, jsx('span', {
                  className: 'ml-1.5 font-semibold tabular-nums', children: c.total })] }),
                jsx(VisChips, { byVisibility: c.by_visibility || {} }),
              ] }, k)
            }),
          ] }),
          jsxs(Card, { title: `Recent semantic (${(data.recent_semantic || []).length})`, children: [
            (data.recent_semantic || []).map((f) => jsxs('div', {
              className: 'border-b border-(--ui-border) py-1 last:border-0',
              children: [
                jsx('div', { className: 'text-xs leading-snug', children: f.text }),
                jsxs('div', { className: 'mt-0.5 text-[0.6875rem] text-(--ui-text-tertiary)', children: [
                  f.occurred_at || '', ' · ', f.visibility,
                ] }),
              ],
            }, f.id)),
          ] }),
        ] }),
        jsxs('div', { className: 'flex flex-col gap-3', children: [
          jsxs(Card, { title: `Mental models — active (${(data.models || []).length})`, children: [
            (data.models || []).length === 0 && jsx('div', {
              className: 'text-xs text-(--ui-text-tertiary)', children: 'none',
            }),
            (data.models || []).map((m) => jsxs('div', {
              className: 'border-b border-(--ui-border) py-1 last:border-0',
              children: [
                jsxs('div', { className: 'text-xs font-medium', children: [
                  m.question_pattern,
                  m.stale && jsx('span', {
                    className: 'ml-1.5 rounded bg-amber-500/15 px-1.5 py-0.5 text-[0.625rem] text-amber-500',
                    children: 'stale',
                  }),
                  m.visibility !== 'private' && jsx('span', {
                    className: 'ml-1.5 text-[0.625rem] text-(--ui-text-tertiary)',
                    children: m.visibility,
                  }),
                ] }),
                jsx('div', { className: 'text-xs text-(--ui-text-secondary)', children: m.summary }),
              ],
            }, m.id)),
          ] }),
          jsxs(Card, { title: `Worker drafts (${(data.drafts || []).length}) — promotion stays manual`, children: [
            (data.drafts || []).length === 0 && jsx('div', {
              className: 'text-xs text-(--ui-text-tertiary)', children: 'none',
            }),
            (data.drafts || []).map((d) => jsxs('div', {
              className: 'border-b border-(--ui-border) py-1 last:border-0',
              children: [
                jsxs('div', { className: 'text-xs font-medium', children: [
                  d.question_pattern,
                  jsxs('span', { className: 'ml-1.5 text-[0.625rem] text-(--ui-text-tertiary)', children: [String((d.source_ids || []).length), ' sources'] }),
                ] }),
                jsx('div', { className: 'text-xs text-(--ui-text-secondary)', children: d.summary }),
              ],
            }, d.id)),
          ] }),
          jsxs(Card, { title: `Knowledge pages (${(data.pages || []).length})`, children: [
            (data.pages || []).length === 0 && jsx('div', {
              className: 'text-xs text-(--ui-text-tertiary)', children: 'none',
            }),
            (data.pages || []).map((p) => jsxs('div', {
              className: 'flex items-center justify-between py-0.5 text-xs',
              children: [
                jsx('span', { children: p.title || p.scope }),
                jsxs('span', { className: 'text-(--ui-text-tertiary) tabular-nums', children: [p.fact_count != null ? `${p.fact_count} facts` : ''] }),
              ],
            }, p.id)),
          ] }),
        ] }),
      ] }),
    ],
  })
}

export default {
  id: ID,
  register(ctx) {
    ctx.registerMany([
      {
        id: 'page',
        area: ROUTES_AREA,
        data: { path: '/ames-memory' },
        render: () => jsx(MemoryPage, { rest: ctx.rest }),
      },
      {
        id: 'nav',
        area: SIDEBAR_NAV_AREA,
        data: { path: '/ames-memory', label: 'Memory', codicon: 'database' },
      },
    ])
  },
}
