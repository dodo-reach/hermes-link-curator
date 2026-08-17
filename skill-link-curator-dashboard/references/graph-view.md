# Graph view — D3 force-directed over the vault

The archive dashboard exposes `/graph` (HTML) and `/graph-json` (data). The
front-end uses the vendored D3 v7 bundle — no `npm install`, no build step. This
document captures the reusable pieces so a future agent can rebuild or extend
the view without rediscovering the tuning.

## Data shape

`get_graph_data()` in `archive.py` returns:

```json
{
  "nodes": [
    {"id": "tag:#ai",         "label": "#ai",        "kind": "tag",   "count": 61},
    {"id": "entry:<digest>:1","label": "Title",      "kind": "entry", "type": "github", "url": "https://..."}
  ],
  "links": [
    {"source": "tag:#ai", "target": "entry:<digest>:1"}
  ]
}
```

Two node kinds, bipartite. `id` is namespaced with `tag:` / `entry:` to avoid
collisions. Every parsed archive occurrence receives one entry node. Entry IDs
are deterministic SHA-256-based opaque values with occurrence suffixes, unique
within each response even when URLs or entire entries are duplicated. Consumers
must not interpret these IDs or rely on the former `entry:<raw-url>` format.

## Filtering

- **A tag must occur in at least two distinct entries** to receive a tag node.
  Repeated tokens within one entry count once.
- **Tags used by only one entry are intentionally hidden** because they add
  noise without grouping power.
- **Every entry remains visible.** Entries with no repeated tags, including
  untagged entries, appear as standalone nodes without links.

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
  .force('standalone-x', d3.forceX(w/2)
    .strength(d => isDisconnectedEntry(d) ? 0.04 : 0))
  .force('standalone-y', d3.forceY(h/2)
    .strength(d => isDisconnectedEntry(d) ? 0.04 : 0))
  .force('collision',
    d3.forceCollide()
      .radius(d => d.kind === 'tag' ? 32 : 8))
```

**Why hub-vs-leaf asymmetry**: tag nodes have larger charge and longer link
distance so the cluster spreads out, while entry nodes stay close to their
hubs. Without the asymmetry tag nodes pull each other into a tight ball.

Capture linked entry IDs before passing links to `forceLink`, because D3 mutates
the `source` and `target` values into node objects. The weak X/Y forces apply
only to disconnected entries; connected clusters keep zero strength. Resize
handling must update all three center coordinates. Entries pinned by a user
retain their fixed coordinates after a resize and are not automatically
recentered.

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
| Drag node | All nodes move; entry nodes stay pinned where dropped, while tag nodes rejoin the simulation on release. |
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
