import { CANONICAL_ROLES, roleMonogram, roleTitle } from '../roles.mjs';
import { actionLabel, formatNum, stateLabel, t } from '../i18n.mjs';
import { createSvgEl, patchKeyedChildren, setAttr, setText } from '../dom.mjs';

export const TOPOLOGY_VIEWBOX = { width: 920, height: 520, minX: 20, maxX: 900, minY: 12, maxY: 510 };
export const NODE_CARD = { width: 172, height: 56, halfW: 86, halfH: 28 };

const COL_X = [130, 350, 570, 790];
const TIER_Y = { 1: 82, 2: 256, 3: 430 };

export function computeNodeLayout(lang = 'fa') {
  return CANONICAL_ROLES.map((role) => {
    const cx = COL_X[role.colIndex] ?? 460;
    const cy = TIER_Y[role.tierRow] ?? 256;
    const rawTitle = roleTitle(role.id, lang, true);
    const label = rawTitle.length > 18 ? `${rawTitle.slice(0, 17)}…` : rawTitle;
    return {
      id: role.id,
      monogram: role.monogram,
      frameShape: role.frameShape,
      glyph: role.glyph,
      tierRow: role.tierRow,
      cx,
      cy,
      x: cx - NODE_CARD.halfW,
      y: cy - NODE_CARD.halfH,
      width: NODE_CARD.width,
      height: NODE_CARD.height,
      label,
    };
  });
}

export function edgeStrokeVar(edge = {}) {
  const act = String(edge.action || edge.requestType || '').toUpperCase();
  if (act.includes('DEFECT') || act === 'INTERROGATE') return 'var(--status-open)';
  if (act === 'WORKER_FIX' || act === 'QA_DISPATCH') return 'var(--status-working)';
  if (act === 'QA_REPORT' || act === 'COMPLETE') return edge.resolved === false ? 'var(--status-open)' : 'var(--status-verified)';
  if (act === 'PEER_SYNC' || act === 'REVIEW_QUERY') return 'var(--status-review)';
  return 'var(--color-accent)';
}

function markerIdForStroke(strokeVar) {
  if (strokeVar.includes('status-open')) return 'tt-arrow-open';
  if (strokeVar.includes('status-working')) return 'tt-arrow-working';
  if (strokeVar.includes('status-verified')) return 'tt-arrow-verified';
  if (strokeVar.includes('status-review')) return 'tt-arrow-review';
  return 'tt-arrow-accent';
}

function clamp(v, lo, hi) {
  return Math.max(lo, Math.min(hi, v));
}

export function computeTopologyLayout(rawEdges = [], lang = 'fa') {
  const nodes = computeNodeLayout(lang);
  const nodeMap = new Map(nodes.map((n) => [n.id, n]));
  const pairSet = new Set((rawEdges || []).map((e) => `${e.from}->${e.to}`));
  const portBuckets = new Map();
  const addPort = (nodeId, side, slotKey, peerCx) => {
    const k = `${nodeId}:${side}`;
    if (!portBuckets.has(k)) portBuckets.set(k, []);
    portBuckets.get(k).push({ slotKey, peerCx });
  };

  const valid = [];
  for (const e of Array.isArray(rawEdges) ? rawEdges : []) {
    const src = nodeMap.get(e.from);
    const dst = nodeMap.get(e.to);
    if (!src || !dst || src.id === dst.id) continue;
    const key = e.key || `${src.id}->${dst.id}`;
    const sameTier = src.tierRow === dst.tierRow;
    const srcSide = sameTier ? (src.tierRow === 1 ? 'top' : 'bottom') : (src.cy < dst.cy ? 'bottom' : 'top');
    const dstSide = sameTier ? (dst.tierRow === 1 ? 'top' : 'bottom') : (src.cy < dst.cy ? 'top' : 'bottom');
    addPort(src.id, srcSide, `${key}:out`, dst.cx);
    addPort(dst.id, dstSide, `${key}:in`, src.cx);
    valid.push({ ...e, key, src, dst, sameTier, srcSide, dstSide });
  }

  const portX = new Map();
  for (const [k, list] of portBuckets.entries()) {
    const nodeId = k.split(':')[0];
    const node = nodeMap.get(nodeId);
    list.sort((a, b) => (a.peerCx - b.peerCx) || a.slotKey.localeCompare(b.slotKey));
    const span = Math.min(108, Math.max(0, (list.length - 1) * 20));
    for (let i = 0; i < list.length; i += 1) {
      const offset = list.length === 1 ? 0 : -span / 2 + (span * i) / (list.length - 1);
      portX.set(list[i].slotKey, Math.round(node.cx + offset));
    }
  }

  const routed = valid.map((e) => {
    let sx = portX.get(`${e.key}:out`) ?? e.src.cx;
    let ex = portX.get(`${e.key}:in`) ?? e.dst.cx;
    const hasReverse = pairSet.has(`${e.dst.id}->${e.src.id}`);
    if (hasReverse && Math.abs(sx - ex) < 6) {
      const shift = e.src.id < e.dst.id ? -10 : 10;
      sx = clamp(sx + shift, e.src.x + 18, e.src.x + NODE_CARD.width - 18);
      ex = clamp(ex + shift, e.dst.x + 18, e.dst.x + NODE_CARD.width - 18);
    }
    const sy = e.srcSide === 'top' ? e.src.y : e.src.y + NODE_CARD.height;
    const ey = e.dstSide === 'top' ? e.dst.y - 2 : e.dst.y + NODE_CARD.height + 2;
    let d = '';
    let mx = Math.round((sx + ex) / 2);
    let my = Math.round((sy + ey) / 2);

    if (e.sameTier) {
      const r = 8;
      const dirX = ex >= sx ? 1 : -1;
      const busY = e.src.tierRow === 1 ? (dirX > 0 ? 34 : 43) : (dirX > 0 ? 474 : 485);
      const preY = e.src.tierRow === 1 ? busY + r : busY - r;
      if (Math.abs(ex - sx) < 20) {
        d = `M ${sx} ${sy} C ${sx} ${busY}, ${ex} ${busY}, ${ex} ${ey}`;
      } else {
        d = `M ${sx} ${sy} L ${sx} ${preY} Q ${sx} ${busY} ${sx + dirX * r} ${busY} L ${ex - dirX * r} ${busY} Q ${ex} ${busY} ${ex} ${preY} L ${ex} ${ey}`;
      }
      my = busY;
    } else {
      const spansQaTier = (e.src.tierRow === 1 && e.dst.tierRow === 3) || (e.src.tierRow === 3 && e.dst.tierRow === 1);
      const midX = (sx + ex) / 2;
      if (spansQaTier && midX > 660) {
        const corridorX = e.src.tierRow === 1 ? 616 : 602;
        const dirY = ey > sy ? 1 : -1;
        d = `M ${sx} ${sy} C ${sx} ${sy + dirY * 46}, ${corridorX} ${256 - dirY * 54}, ${corridorX} 256 C ${corridorX} ${256 + dirY * 54}, ${ex} ${ey - dirY * 46}, ${ex} ${ey}`;
        mx = corridorX;
        my = e.src.tierRow === 1 ? 196 : 316;
      } else {
        const dy = ey - sy;
        const tLen = Math.max(36, Math.round(Math.abs(dy) * 0.42));
        const cy1 = dy >= 0 ? sy + tLen : sy - tLen;
        const cy2 = dy >= 0 ? ey - tLen : ey + tLen;
        d = `M ${sx} ${sy} C ${sx} ${cy1}, ${ex} ${cy2}, ${ex} ${ey}`;
        my = Math.round(sy + dy * (hasReverse ? (e.src.id < e.dst.id ? 0.42 : 0.58) : 0.5));
      }
    }
    const strokeVar = edgeStrokeVar(e);
    const shortAct = actionLabel(e.action || e.requestType, lang);
    const badgeText = `${formatNum(e.count || 1, lang)}x ${shortAct}`.slice(0, 22);
    const pillW = Math.min(148, Math.max(52, Math.round(badgeText.length * 6.4 + 14)));
    return {
      ...e, sx, sy, ex, ey, d, strokeVar, markerId: markerIdForStroke(strokeVar),
      badgeText, pillW,
      badgeX: clamp(mx, 14 + Math.ceil(pillW / 2), TOPOLOGY_VIEWBOX.width - 14 - Math.ceil(pillW / 2)),
      badgeY: clamp(my, 34, 484),
    };
  });

  const tierLabels = [
    { tier: 1, x: 460, y: 15, text: t('topo.tier1', {}, lang) },
    { tier: 2, x: 130, y: 256, text: t('topo.tier2', {}, lang) },
    { tier: 3, x: 460, y: 509, text: t('topo.tier3', {}, lang) },
  ];

  const staticObstacles = [
    ...nodes.map((n) => ({ left: n.x - 4, right: n.x + n.width + 4, top: n.y - 4, bottom: n.y + n.height + 4 })),
    { left: 380, right: 540, top: 4, bottom: 24 },
    { left: 40, right: 220, top: 242, bottom: 270 },
    { left: 380, right: 540, top: 496, bottom: 516 },
  ];

  for (let pass = 0; pass < 6; pass += 1) {
    for (const edge of routed) {
      const halfW = edge.pillW / 2;
      const box = () => ({
        left: edge.badgeX - halfW,
        right: edge.badgeX + halfW,
        top: edge.badgeY - 9,
        bottom: edge.badgeY + 9,
      });
      for (const obs of staticObstacles) {
        const b = box();
        if (b.left < obs.right && b.right > obs.left && b.top < obs.bottom && b.bottom > obs.top) {
          const pushUp = obs.top - 10;
          const pushDown = obs.bottom + 10;
          if (pushUp >= 34 && (pushDown > 484 || Math.abs(edge.badgeY - pushUp) <= Math.abs(pushDown - edge.badgeY))) {
            edge.badgeY = pushUp;
          } else {
            edge.badgeY = clamp(pushDown, 34, 484);
          }
        }
      }
    }
    for (let i = 0; i < routed.length; i += 1) {
      for (let j = i + 1; j < routed.length; j += 1) {
        const a = routed[i];
        const b = routed[j];
        const minDx = (a.pillW + b.pillW) / 2 + 4;
        if (Math.abs(a.badgeX - b.badgeX) < minDx && Math.abs(a.badgeY - b.badgeY) < 20) {
          a.badgeY = clamp(a.badgeY - 11, 34, 484);
          b.badgeY = clamp(b.badgeY + 11, 34, 484);
        }
      }
    }
  }

  return { viewBox: TOPOLOGY_VIEWBOX, nodes, edges: routed, tierLabels };
}

function statusDotVar(status) {
  const s = String(status || 'IDLE').toUpperCase();
  if (s === 'WORKING') return 'var(--status-working)';
  if (s === 'ACTIVE') return 'var(--status-review)';
  if (s === 'DONE' || s === 'COMPLETED') return 'var(--status-verified)';
  return 'var(--color-rule-strong)';
}

function ensureScaffold(container, doc, onAction) {
  if (container._topoRefs) return container._topoRefs;
  container.innerHTML = '';
  const stage = doc.createElement('div');
  stage.className = 'topology-stage surface-plate';

  const head = doc.createElement('div');
  head.className = 'region-head';
  const titleEl = doc.createElement('h2');
  titleEl.className = 'region-title';
  const clearBtn = doc.createElement('button');
  clearBtn.type = 'button';
  clearBtn.className = 'btn btn-quiet btn-compact';
  clearBtn.hidden = true;
  clearBtn.addEventListener('click', () => onAction?.({ type: 'CLEAR_TOPO_FOCUS' }));
  head.appendChild(titleEl);
  head.appendChild(clearBtn);
  stage.appendChild(head);

  const wrap = doc.createElement('div');
  wrap.className = 'topology-canvas-wrap';
  const svg = createSvgEl(doc, 'svg', {
    class: 'topology-svg', viewBox: '0 0 920 520', dir: 'ltr', role: 'group', 'aria-label': 'Architecture Topology',
  });

  const defs = createSvgEl(doc, 'defs');
  for (const [id, fillVar] of [
    ['tt-arrow-accent', 'var(--color-accent)'],
    ['tt-arrow-open', 'var(--status-open)'],
    ['tt-arrow-working', 'var(--status-working)'],
    ['tt-arrow-review', 'var(--status-review)'],
    ['tt-arrow-verified', 'var(--status-verified)'],
  ]) {
    const marker = createSvgEl(doc, 'marker', {
      id, viewBox: '0 0 10 10', refX: '8', refY: '5', markerWidth: '6', markerHeight: '6', orient: 'auto-start-reverse',
    });
    marker.appendChild(createSvgEl(doc, 'path', { d: 'M 0 1.5 L 8.5 5 L 0 8.5 z', fill: fillVar }));
    defs.appendChild(marker);
  }
  svg.appendChild(defs);

  const bgLayer = createSvgEl(doc, 'g', { class: 'topo-bg-layer' });
  bgLayer.appendChild(createSvgEl(doc, 'line', {
    x1: '790', y1: '110', x2: '790', y2: '228', stroke: 'var(--color-rule-strong)', 'stroke-dasharray': '4 4', 'stroke-width': '1.2',
  }));
  const emptyText = createSvgEl(doc, 'text', {
    x: '460', y: '172', 'text-anchor': 'middle', fill: 'var(--color-muted)',
    'font-family': 'var(--font-sans)', 'font-size': '12', 'unicode-bidi': 'plaintext', direction: 'ltr',
  });
  bgLayer.appendChild(emptyText);
  const labelsLayer = createSvgEl(doc, 'g', { class: 'topo-labels-layer' });
  const edgesLayer = createSvgEl(doc, 'g', { class: 'topo-edges-layer' });
  const nodesLayer = createSvgEl(doc, 'g', { class: 'topo-nodes-layer' });
  svg.appendChild(bgLayer);
  svg.appendChild(labelsLayer);
  svg.appendChild(edgesLayer);
  svg.appendChild(nodesLayer);
  wrap.appendChild(svg);
  stage.appendChild(wrap);

  const replayBar = doc.createElement('div');
  replayBar.className = 'replay-bar';
  replayBar.innerHTML = `
    <div class="replay-controls">
      <button type="button" class="btn btn-quiet btn-compact" data-act="prev"></button>
      <button type="button" class="btn btn-quiet btn-compact" data-act="play"></button>
      <button type="button" class="btn btn-quiet btn-compact" data-act="next"></button>
      <select class="field-select btn-compact" data-act="speed" aria-label="Replay speed">
        <option value="0.5">0.5x</option>
        <option value="1" selected>1x</option>
        <option value="2">2x</option>
      </select>
      <button type="button" class="btn btn-quiet btn-compact" data-act="live"></button>
    </div>
    <div class="replay-track-wrap">
      <input type="range" class="replay-range" min="0" max="0" value="0" aria-label="Sequence timeline">
      <span class="seq-num" data-ref="seqReadout">#0</span>
    </div>`;
  replayBar.addEventListener('click', (ev) => {
    const btn = ev.target.closest?.('button[data-act]');
    if (btn) onAction?.({ type: 'REPLAY_CONTROL', control: btn.getAttribute('data-act') });
  });
  replayBar.querySelector('[data-act="speed"]')?.addEventListener('change', (ev) => {
    onAction?.({ type: 'REPLAY_SPEED', speed: Number(ev.target.value || 1) });
  });
  replayBar.querySelector('.replay-range')?.addEventListener('input', (ev) => {
    onAction?.({ type: 'REPLAY_SEEK', seq: Number(ev.target.value || 0) });
  });
  stage.appendChild(replayBar);

  const fbWrap = doc.createElement('div');
  fbWrap.className = 'topo-fallback-wrap table-scroll';
  const fbTable = doc.createElement('table');
  fbTable.className = 'data-table';
  const fbTbody = doc.createElement('tbody');
  fbTable.appendChild(fbTbody);
  fbWrap.appendChild(fbTable);
  stage.appendChild(fbWrap);
  container.appendChild(stage);

  container._topoRefs = { titleEl, clearBtn, svg, emptyText, labelsLayer, edgesLayer, nodesLayer, replayBar, fbTbody };
  return container._topoRefs;
}

export function patchTopologyPulse(container, agents = []) {
  const refs = container?._topoRefs;
  if (!refs) return;
  const byId = new Map((agents || []).map((a) => [a.id, a]));
  for (const g of Array.from(refs.nodesLayer.children || [])) {
    const id = g.getAttribute?.('data-node-id');
    const ag = byId.get(id);
    if (!ag) continue;
    const dot = g._refs?.dot;
    const halo = g._refs?.halo;
    setAttr(dot, 'fill', statusDotVar(ag.status));
    setAttr(halo, 'opacity', ag.status === 'WORKING' ? '1' : '0');
  }
}

export function renderTopologyBoard(container, state, { buildGraph, onAction, doc = globalThis.document } = {}) {
  if (!container || !doc) return null;
  const refs = ensureScaffold(container, doc, onAction);
  const lang = state.lang || 'fa';
  const cutoff = state.replay?.active ? state.replay.cursorSeq : null;
  const graph = cutoff !== null && buildGraph
    ? buildGraph(state.interactions, cutoff)
    : (state.graph?.edges ? state.graph : (buildGraph ? buildGraph(state.interactions, null) : { edges: [], maxSeq: 0 }));

  const layout = computeTopologyLayout(graph.edges || [], lang);
  setText(refs.titleEl, t('topo.title', {}, lang));
  refs.clearBtn.hidden = !state.topologyFocusNode && !state.topologySelectedEdge;
  setText(refs.clearBtn, t('topo.clearFocus', {}, lang));

  patchKeyedChildren(refs.labelsLayer, layout.tierLabels, (it) => `tier-${it.tier}`, () => createSvgEl(doc, 'text', {
    'text-anchor': 'middle', fill: 'var(--color-muted)', 'font-family': 'var(--font-sans)', 'font-size': '11', 'unicode-bidi': 'plaintext',
  }), (el, it) => {
    setAttr(el, 'x', it.x); setAttr(el, 'y', it.y); setText(el, it.text);
  });

  const focusNode = state.topologyFocusNode;
  const selEdge = state.topologySelectedEdge;
  const connectedNodes = new Set(focusNode ? [focusNode] : []);
  if (focusNode) {
    for (const e of layout.edges) {
      if (e.from === focusNode || e.to === focusNode) { connectedNodes.add(e.from); connectedNodes.add(e.to); }
    }
  }

  setAttr(refs.emptyText, 'visibility', layout.edges.length === 0 ? 'visible' : 'hidden');
  setText(refs.emptyText, t('topo.emptyEdges', {}, lang));

  patchKeyedChildren(
    refs.edgesLayer,
    layout.edges,
    (e) => e.key,
    (e) => {
      const g = createSvgEl(doc, 'g', { class: 'topo-edge-group', tabindex: '0', role: 'button' });
      const hit = createSvgEl(doc, 'path', { fill: 'none', stroke: 'transparent', 'stroke-width': '14' });
      const path = createSvgEl(doc, 'path', { fill: 'none', 'stroke-linecap': 'round' });
      const pill = createSvgEl(doc, 'rect', {
        height: '18', rx: '4', fill: 'var(--color-surface-1)', 'stroke-width': '1',
      });
      const label = createSvgEl(doc, 'text', {
        'text-anchor': 'middle', 'font-family': 'var(--font-sans)', 'font-size': '10',
        fill: 'var(--color-ink)', 'unicode-bidi': 'plaintext', direction: 'ltr',
      });
      g.appendChild(hit);
      g.appendChild(path);
      g.appendChild(pill);
      g.appendChild(label);
      const triggerEdge = () => {
        if (g._edge) onAction?.({ type: 'TOPO_CLICK_EDGE', edge: g._edge });
      };
      g.addEventListener('click', triggerEdge);
      g.addEventListener('keydown', (ev) => {
        if (ev.key === 'Enter' || ev.key === ' ') { ev.preventDefault(); triggerEdge(); }
      });
      g._refs = { hit, path, pill, label };
      g._edge = e;
      return g;
    },
    (g, e) => {
      g._edge = e;
      const { hit, path, pill, label } = g._refs;
      const isSelected = selEdge === e.key;
      const isDimmed = (focusNode && e.from !== focusNode && e.to !== focusNode)
        || (!focusNode && selEdge && !isSelected);
      g.classList.toggle('topo-dimmed', Boolean(isDimmed));
      setAttr(g, 'aria-label', `${roleMonogram(e.from)} -> ${roleMonogram(e.to)}: ${e.badgeText}`);

      setAttr(hit, 'd', e.d);
      setAttr(path, 'd', e.d);
      setAttr(path, 'stroke', e.strokeVar);
      setAttr(path, 'stroke-width', isSelected ? '2.6' : '1.75');
      setAttr(path, 'marker-end', `url(#${e.markerId})`);

      const pillW = e.pillW || Math.min(148, Math.max(52, Math.round(e.badgeText.length * 6.4 + 14)));
      const pillX = clamp(Math.round(e.badgeX - pillW / 2), 14, TOPOLOGY_VIEWBOX.width - 14 - pillW);
      const pillY = clamp(Math.round(e.badgeY - 9), 24, TOPOLOGY_VIEWBOX.height - 26);
      setAttr(pill, 'x', pillX);
      setAttr(pill, 'y', pillY);
      setAttr(pill, 'width', pillW);
      setAttr(pill, 'stroke', e.strokeVar);

      setAttr(label, 'x', Math.round(pillX + pillW / 2));
      setAttr(label, 'y', pillY + 12.5);
      setText(label, e.badgeText);
    },
    'data-edge-key',
  );

  const agentsById = new Map((state.agents || []).map((a) => [a.id, a]));

  patchKeyedChildren(
    refs.nodesLayer,
    layout.nodes,
    (n) => n.id,
    (n) => {
      const g = createSvgEl(doc, 'g', { class: 'topo-node-group', tabindex: '0', role: 'button' });
      const card = createSvgEl(doc, 'rect', {
        x: n.x, y: n.y, width: n.width, height: n.height, rx: '8',
        fill: 'var(--color-surface-1)', stroke: 'var(--color-rule-strong)', 'stroke-width': '1.2',
      });
      const fx = n.x + 22;
      const fy = n.y + 28;
      let frame;
      if (n.frameShape === 'hexagon') {
        const pts = [0, 1, 2, 3, 4, 5].map((k) => {
          const a = ((k * 60 - 30) * Math.PI) / 180;
          return `${(fx + 13 * Math.cos(a)).toFixed(1)},${(fy + 13 * Math.sin(a)).toFixed(1)}`;
        }).join(' ');
        frame = createSvgEl(doc, 'polygon', { points: pts });
      } else if (n.frameShape === 'diamond') {
        frame = createSvgEl(doc, 'polygon', {
          points: `${fx},${fy - 14} ${fx + 14},${fy} ${fx},${fy + 14} ${fx - 14},${fy}`,
        });
      } else if (n.frameShape === 'square') {
        frame = createSvgEl(doc, 'rect', { x: fx - 12, y: fy - 12, width: '24', height: '24', rx: '4' });
      } else {
        frame = createSvgEl(doc, 'circle', { cx: fx, cy: fy, r: '12.5' });
      }
      setAttr(frame, 'fill', 'var(--color-surface-2)');
      setAttr(frame, 'stroke', 'var(--color-rule-strong)');
      setAttr(frame, 'stroke-width', '1.1');

      const glyph = createSvgEl(doc, 'path', {
        d: n.glyph,
        fill: 'none',
        stroke: 'var(--color-ink)',
        'stroke-width': '1.35',
        'stroke-linecap': 'round',
        'stroke-linejoin': 'round',
        transform: `translate(${fx - 8}, ${fy - 8})`,
      });

      const monogram = createSvgEl(doc, 'text', {
        x: n.x + 42, y: n.y + 22, 'text-anchor': 'start',
        'font-family': 'var(--font-mono)', 'font-size': '11', 'font-weight': '600',
        fill: 'var(--color-accent-text)', direction: 'ltr',
      });
      setText(monogram, n.monogram);

      const label = createSvgEl(doc, 'text', {
        x: n.x + 42, y: n.y + 41, 'text-anchor': 'start',
        'font-family': 'var(--font-sans)', 'font-size': '11',
        fill: 'var(--color-ink)', 'unicode-bidi': 'plaintext', direction: 'ltr',
      });

      const dotCx = n.x + n.width - 14;
      const dotCy = n.y + 16;
      const halo = createSvgEl(doc, 'circle', {
        cx: dotCx, cy: dotCy, r: '7', fill: 'none', stroke: 'var(--status-working)', 'stroke-width': '1.4', opacity: '0',
      });
      const dot = createSvgEl(doc, 'circle', {
        cx: dotCx, cy: dotCy, r: '4', fill: 'var(--color-rule-strong)',
      });

      g.appendChild(card);
      g.appendChild(frame);
      g.appendChild(glyph);
      g.appendChild(monogram);
      g.appendChild(label);
      g.appendChild(halo);
      g.appendChild(dot);

      const triggerNode = () => onAction?.({ type: 'TOPO_CLICK_NODE', nodeId: g.getAttribute('data-node-id') });
      g.addEventListener('click', triggerNode);
      g.addEventListener('keydown', (ev) => {
        if (ev.key === 'Enter' || ev.key === ' ') { ev.preventDefault(); triggerNode(); }
      });
      g._refs = { card, frame, monogram, label, dot, halo };
      return g;
    },
    (g, n) => {
      const ag = agentsById.get(n.id);
      const { card, label, dot, halo } = g._refs;
      const isFocused = focusNode === n.id;
      const isDimmed = focusNode && !connectedNodes.has(n.id);
      g.classList.toggle('topo-dimmed', Boolean(isDimmed));
      setAttr(card, 'fill', isFocused ? 'var(--color-accent-soft)' : 'var(--color-surface-1)');
      setAttr(card, 'stroke', isFocused ? 'var(--color-accent)' : 'var(--color-rule-strong)');
      setAttr(card, 'stroke-width', isFocused ? '1.8' : '1.2');
      setText(label, n.label);
      setAttr(dot, 'fill', statusDotVar(ag?.status));
      setAttr(halo, 'opacity', ag?.status === 'WORKING' ? '1' : '0');
      setAttr(g, 'aria-label', `${n.monogram} ${n.label} (${stateLabel(ag?.status || 'IDLE', lang)})`);
    },
    'data-node-id',
  );

  const fullMaxSeq = Math.max(
    Number(state.seq || 0),
    ...(state.interactions || []).map((it) => Number(it?.seq || 0)),
    0,
  );
  const activeSeq = state.replay?.active
    ? clamp(Number(state.replay.cursorSeq ?? fullMaxSeq), 0, fullMaxSeq)
    : fullMaxSeq;

  const prevBtn = refs.replayBar.querySelector('[data-act="prev"]');
  const playBtn = refs.replayBar.querySelector('[data-act="play"]');
  const nextBtn = refs.replayBar.querySelector('[data-act="next"]');
  const liveBtn = refs.replayBar.querySelector('[data-act="live"]');
  const speedSel = refs.replayBar.querySelector('[data-act="speed"]');
  const rangeEl = refs.replayBar.querySelector('.replay-range');
  const seqReadout = refs.replayBar.querySelector('[data-ref="seqReadout"]');

  if (prevBtn) {
    setText(prevBtn, t('topo.prev', {}, lang));
    prevBtn.disabled = fullMaxSeq <= 0 || activeSeq <= 0;
  }
  if (playBtn) {
    setText(playBtn, t(state.replay?.playing ? 'topo.pause' : 'topo.play', {}, lang));
    playBtn.disabled = fullMaxSeq <= 0;
  }
  if (nextBtn) {
    setText(nextBtn, t('topo.next', {}, lang));
    nextBtn.disabled = fullMaxSeq <= 0 || activeSeq >= fullMaxSeq;
  }
  if (liveBtn) {
    setText(liveBtn, t('topo.live', {}, lang));
    liveBtn.classList.toggle('is-active', !state.replay?.active);
  }
  if (speedSel) speedSel.value = String(state.replay?.speed || 1);
  if (rangeEl) {
    rangeEl.min = '0';
    rangeEl.max = String(fullMaxSeq);
    rangeEl.value = String(activeSeq);
    rangeEl.disabled = fullMaxSeq <= 0;
  }
  if (seqReadout) {
    setText(seqReadout, fullMaxSeq > 0 ? `#${formatNum(activeSeq, lang)} / #${formatNum(fullMaxSeq, lang)}` : '#0');
  }

  patchKeyedChildren(
    refs.fbTbody,
    layout.edges,
    (e) => e.key,
    (e) => {
      const tr = doc.createElement('tr');
      tr.className = 'is-clickable';
      const tdPair = doc.createElement('td');
      const tdAct = doc.createElement('td');
      const tdSeq = doc.createElement('td');
      tdSeq.className = 'seq-num';
      tr.appendChild(tdPair);
      tr.appendChild(tdAct);
      tr.appendChild(tdSeq);
      tr._refs = { tdPair, tdAct, tdSeq };
      tr._edge = e;
      tr.addEventListener('click', () => {
        if (tr._edge) onAction?.({ type: 'TOPO_CLICK_EDGE', edge: tr._edge });
      });
      return tr;
    },
    (tr, e) => {
      tr._edge = e;
      setText(tr._refs.tdPair, `${roleMonogram(e.from)} -> ${roleMonogram(e.to)}`);
      setText(tr._refs.tdAct, e.badgeText);
      setText(tr._refs.tdSeq, `#${formatNum(e.lastSeq || 0, lang)}`);
    },
    'data-edge-key',
  );

  return layout;
}
