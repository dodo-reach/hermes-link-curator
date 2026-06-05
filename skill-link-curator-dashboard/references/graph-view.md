# Graph view — D3 force-directed over the vault

The archive dashboard exposes `/graph` (HTML) and `/graph-json` (data). The
front-end is D3 v7 loaded from CDN — no `npm install`, no build step. This
document captures the reusable pieces so a future agent can rebuild or extend
the view without rediscovering the tuning.

## Data shape

`get_graph_data()` in `archive.py` returns:

```json
{
  "nodes": [
    {"id": "tag:#ai",         "label": "#ai",        "kind": "tag",   "count": 61},
    {"id": "entry:<url-hash>","label": "Title",      "kind": "entry", "type": "github", "url": "https://..."}
  ],
  "links": [
    {"source": "tag:#ai", "target": "entry:<url-hash>"}
  ]
}
```

Two node kinds, bipartite. `id` is namespaced with `tag:` / `entry:` to avoid
collisions if a tag literally collides with a URL.

## Filtering

- **Tag nodes with `count < 2` are dropped** — one-off tags produce isolated
  edge-bridges that add noise without grouping power.
- **Entries with no surviving tag are dropped** — they'd be orphan nodes with
  no edges, just visual clutter.

With 103 entries / ~150 tags this typically yields ~78 tag nodes + ~101 entry
nodes + ~400 links. Readable, no hairball.

## Why tag-graph (not entry-similarity)

An entry↔entry Jaccard graph on shared tags with 100+ nodes becomes a dense
hairball even at high thresholds. Tag hubs give a bipartite layout where the
hub size encodes tag popularity — same idea as Obsidian's native graph view
when the user has more notes than topics.

If you ever need entry↔entry (e.g. for a "related entries" feature), keep that
as a *secondary* view, not the default. Build a separate `/graph-related`
route that uses a top-N threshold (e.g. Jaccard ≥ 0.3) and `<=` 5 edges per
node to keep the layout sparse.

## D3 force tuning

These are the values that worked for ~180 nodes / ~400 links. Anything denser
needs these re-tuned.

```js
d3.forceSimulation(nodes)
  .force('link',
    d3.forceLink(links)
      .id(d => d.id)
      .distance(d => d.source.kind === 'tag' ? 40 : 50)
      .strength(0.6))
  .force('charge',
    d3.forceManyBody()
      .strength(d => d.kind === 'tag' ? -180 : -30))
  .force('center', d3.forceCenter(w/2, h/2))
  .force('collision',
    d3.forceCollide()
      .radius(d => d.kind === 'tag' ? 32 : 8))
```

**Why hub-vs-leaf asymmetry**: tag nodes have larger charge and longer link
distance so the cluster spreads out, while entry nodes stay close to their
hubs. Without the asymmetry tag nodes pull each other into a tight ball.

## Color map (entry types)

Matches the dashboard aesthetic — minimalist, no rainbow.

| Type      | Color     |
|-----------|-----------|
| `github`  | `#2c2c2c` |
| `x-post`  | `#888`    |
| `article` | `#5a7a9a` |
| `tool`    | `#7a9a5a` |
| `video`   | `#9a7a5a` |
| `paper`   | `#9a5a7a` |
| `other`   | `#aaa`    |

Tag nodes are filled `#f4f3ef` (the secondary background) with a dark stroke,
so they read as "neutral hubs" and entries read as the colored payload.

## Interactions

| Action | Result |
|--------|--------|
| Drag node | Repositions (tag nodes unfix on release, entry nodes stay put — entries are "leaves", no reason to pin them) |
| Scroll | Zoom 0.3×–5× (`d3.zoom().scaleExtent`) |
| Click tag node | Highlight connected cluster, dim rest to opacity 0.15. Click again to clear. |
| Dblclick entry | `window.open(url, '_blank')` |
| Dblclick background | Reset zoom via `zoom.transform(d3.zoomIdentity)` |

**Pitfall**: `svg.on('dblclick.zoom', null)` — D3's zoom behavior captures
dblclick by default for double-click-to-zoom. You must null it out before
binding your own dblclick handler on the SVG, otherwise the zoom reset and
the entry-open handlers race.

## Reusable starter

The full template is at `templates/force-graph.html` (extends the dashboard
`base.html`). To use as a starting point for a different graph, copy it and
edit the data endpoint URL + any color/label logic. The D3 boilerplate
(zoom, drag, sim, tick) doesn't need to change.

## Embedding in the dashboard

The page extends `base.html` and overrides the `{% block calendar_script %}`
slot. CSS lives in `base.html` under a `/* ── Graph ── */` section so the
graph page doesn't need its own stylesheet.
