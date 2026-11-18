import test from 'node:test';
import assert from 'node:assert/strict';
import { buildGraphFromInteractions, createCaseStore } from '../src/store.mjs';
import { buildWsUrl, createSyncClient } from '../src/sync.mjs';
import { CANONICAL_ROLES, normalizeRoleId } from '../src/roles.mjs';
import {
  TOPOLOGY_VIEWBOX,
  computeNodeLayout,
  computeTopologyLayout,
  patchTopologyPulse,
  renderTopologyBoard,
} from '../src/boards/topology-board.mjs';
import { renderCommandBoard } from '../src/boards/command-board.mjs';
import { renderChronicleBoard } from '../src/boards/chronicle-board.mjs';
import { renderSquadBoard } from '../src/boards/squad-board.mjs';
import { renderDossierDrawer, renderSettingsSheet } from '../src/inspector.mjs';
import { initThinkTankStudio } from '../src/app.mjs';

function makeMockSvgDoc() {
  function makeNode(tag) {
    const attrs = new Map();
    const children = [];
    const listeners = new Map();
    const classSet = new Set();
    const node = {
      tagName: String(tag).toUpperCase(),
      parentNode: null,
      textContent: '',
      value: '',
      min: '',
      max: '',
      disabled: false,
      hidden: false,
      style: { setProperty() {} },
      children,
      get options() { return children; },
      get parentElement() { return node.parentNode; },
      classList: {
        toggle(cls, force) {
          if (force === undefined) {
            if (classSet.has(cls)) classSet.delete(cls);
            else classSet.add(cls);
          } else if (force) classSet.add(cls);
          else classSet.delete(cls);
        },
        contains(cls) { return classSet.has(cls); },
      },
      set className(v) {
        classSet.clear();
        for (const c of String(v || '').split(/\s+/).filter(Boolean)) classSet.add(c);
      },
      get className() { return Array.from(classSet).join(' '); },
      set innerHTML(_v) { children.length = 0; },
      get firstElementChild() { return children[0] || null; },
      get nextElementSibling() {
        if (!node.parentNode) return null;
        const sibs = node.parentNode.children;
        const idx = sibs.indexOf(node);
        return idx >= 0 && idx + 1 < sibs.length ? sibs[idx + 1] : null;
      },
      getAttribute(k) { return attrs.has(k) ? attrs.get(k) : null; },
      setAttribute(k, v) { attrs.set(k, String(v)); },
      removeAttribute(k) { attrs.delete(k); },
      hasAttribute(k) { return attrs.has(k); },
      appendChild(child) {
        if (child.parentNode) child.remove();
        child.parentNode = node;
        children.push(child);
        return child;
      },
      append(...items) {
        for (const it of items) node.appendChild(it);
      },
      insertBefore(child, ref) {
        if (child.parentNode) child.remove();
        child.parentNode = node;
        if (!ref) { children.push(child); return child; }
        const idx = children.indexOf(ref);
        if (idx < 0) children.push(child);
        else children.splice(idx, 0, child);
        return child;
      },
      remove() {
        if (!node.parentNode) return;
        const idx = node.parentNode.children.indexOf(node);
        if (idx >= 0) node.parentNode.children.splice(idx, 1);
        node.parentNode = null;
      },
      addEventListener(ev, fn) { listeners.set(ev, fn); },
      querySelector(sel) {
        const attrM = sel.match(/^\[data-act="([^"]+)"\]$/) || sel.match(/^\[data-ref="([^"]+)"\]$/);
        const clsM = sel.match(/^\.([a-z0-9_-]+)$/i);
        const walk = (n) => {
          for (const ch of n.children) {
            if (attrM && (ch.getAttribute('data-act') === attrM[1] || ch.getAttribute('data-ref') === attrM[1])) return ch;
            if (clsM && ch.classList.contains(clsM[1])) return ch;
            const found = walk(ch);
            if (found) return found;
          }
          return null;
        };
        return walk(node);
      },
    };
    return node;
  }

  return {
    createElement(tag) { return makeNode(tag); },
    createElementNS(_ns, tag) { return makeNode(tag); },
  };
}

test('store slice revisions isolate transient pulses from topology, WBS, findings, and ledger', () => {
  const store = createCaseStore({ convId: 'c1', lang: 'fa' });
  store.applySnapshot({
    convId: 'c1',
    sync: { generation: 'g1', seq: 2 },
    thinkTank: { project: 'Demo', status: 'ACTIVE' },
    agents: [{ id: 'backend-auditor', status: 'ACTIVE' }],
    interactions: [{ seq: 1, from: 'team-manager', to: 'backend-auditor', action: 'ASSIGN_TASK' }],
  });

  const before = { ...store.revs };
  store.applyTransientPulse({
    type: 'TRANSIENT_PULSE',
    pulseKind: 'TELEMETRY',
    agentId: 'backend-auditor',
    tool: 'edit_file',
    toolCall: { id: 'tc1', agent: 'backend-auditor', tool: 'edit_file' },
  });

  assert.equal(store.revs.telemetryRev, before.telemetryRev + 1);
  assert.equal(store.revs.pulseRev, before.pulseRev + 1);
  assert.equal(store.revs.topologyRev, before.topologyRev);
  assert.equal(store.revs.findingsRev, before.findingsRev);
  assert.equal(store.revs.wbsRev, before.wbsRev);
  assert.equal(store.revs.ledgerRev, before.ledgerRev);
  assert.equal(store.revs.pipelineRev, before.pipelineRev);
});

test('sync client handles SYNC_READY, CASE_EVENT seq gaps, SYNC_REPLAY, and TRANSIENT_PULSE', async () => {
  const store = createCaseStore({ convId: 'c1' });
  let statusFetchCalls = 0;
  const mockFetch = async (url) => {
    if (String(url).includes('/status')) {
      statusFetchCalls += 1;
      return {
        ok: true,
        json: async () => ({
          convId: 'c1',
          sync: { generation: 'g1', seq: 5 },
          thinkTank: { project: 'Recovered', status: 'ACTIVE' },
        }),
      };
    }
    return { ok: true, json: async () => ({}) };
  };

  const client = createSyncClient({ store, fetchImpl: mockFetch, WebSocketImpl: null, sidecarObj: null });
  store.applySnapshot({ convId: 'c1', sync: { generation: 'g1', seq: 1 }, thinkTank: { project: 'Demo' } });
  const revBeforeReady = { ...store.revs };

  client.handleFrame({ type: 'SYNC_READY' });
  assert.equal(statusFetchCalls, 0);
  assert.deepEqual(store.revs, revBeforeReady);

  client.handleFrame({
    type: 'CASE_EVENT',
    convId: 'c1',
    generation: 'g1',
    seq: 2,
    changedSlices: ['messages'],
    message: { id: 'm2', seq: 2, senderRole: 'team-manager', content: 'next' },
  });
  assert.equal(store.state.seq, 2);
  assert.equal(statusFetchCalls, 0);

  client.handleFrame({
    type: 'SYNC_REPLAY',
    convId: 'c1',
    generation: 'g1',
    seq: 3,
    events: [
      {
        type: 'CASE_EVENT',
        convId: 'c1',
        generation: 'g1',
        seq: 3,
        changedSlices: ['interactions', 'graph'],
        interaction: { seq: 3, from: 'team-manager', to: 'ui-frontend-designer', action: 'ASSIGN_TASK' },
      },
    ],
  });
  assert.equal(store.state.seq, 3);
  assert.equal(store.state.graph.edges.length, 1);

  const topoRevBeforePulse = store.revs.topologyRev;
  client.handleFrame({ type: 'TRANSIENT_PULSE', convId: 'c1', agentId: 'ui-frontend-designer', tool: 'write_file' });
  assert.equal(store.state.seq, 3);
  assert.equal(store.revs.topologyRev, topoRevBeforePulse);

  client.handleFrame({
    type: 'CASE_EVENT',
    convId: 'c1',
    generation: 'g1',
    seq: 7,
    changedSlices: ['thinkTank'],
  });
  await new Promise((r) => setTimeout(r, 10));
  assert.equal(statusFetchCalls, 1);
  assert.equal(store.state.seq, 5);
  assert.equal(buildWsUrl('ws://127.0.0.1:8780/ws', { convId: 'c1', generation: 'g1', afterSeq: 5 }), 'ws://127.0.0.1:8780/ws?convId=c1&generation=g1&afterSeq=5');
});

test('roles.mjs alias normalization matches backend catalog parity', () => {
  assert.equal(CANONICAL_ROLES.length, 9);
  assert.equal(normalizeRoleId('orchestrator'), 'main_agent');
  assert.equal(normalizeRoleId('coordinator'), 'main_agent');
  assert.equal(normalizeRoleId('manager'), 'team-manager');
  assert.equal(normalizeRoleId('owner'), 'user');
  for (const r of CANONICAL_ROLES) {
    assert.ok(r.monogram && r.frameShape && r.glyph && r.title.fa && r.title.en);
  }
});

test('computeTopologyLayout places all nodes and badges inside bounds with zero node overlap', () => {
  const sampleEdges = [
    { from: 'main_agent', to: 'team-manager', action: 'ASSIGN_TASK', count: 2 },
    { from: 'team-manager', to: 'ui-frontend-designer', action: 'ASSIGN_TASK', count: 1 },
    { from: 'team-manager', to: 'backend-auditor', action: 'ASSIGN_TASK', count: 1 },
    { from: 'ui-frontend-designer', to: 'backend-auditor', action: 'PEER_SYNC', count: 3 },
    { from: 'backend-auditor', to: 'ui-frontend-designer', action: 'PEER_SYNC', count: 2 },
    { from: 'council-critic', to: 'ui-frontend-designer', action: 'RETURN_DEFECT', count: 1 },
    { from: 'code-reviewer', to: 'qa-reviewer', action: 'QA_DISPATCH', count: 1 },
    { from: 'qa-reviewer', to: 'code-reviewer', action: 'QA_REPORT', count: 1 },
  ];

  for (const lang of ['fa', 'en']) {
    const nodes = computeNodeLayout(lang);
    assert.equal(nodes.length, 9);
    for (const n of nodes) {
      assert.ok(n.x >= TOPOLOGY_VIEWBOX.minX, `${n.id} x=${n.x} < minX`);
      assert.ok(n.x + n.width <= TOPOLOGY_VIEWBOX.maxX, `${n.id} right=${n.x + n.width} > maxX`);
      assert.ok(n.y >= TOPOLOGY_VIEWBOX.minY, `${n.id} y=${n.y} < minY`);
      assert.ok(n.y + n.height <= TOPOLOGY_VIEWBOX.maxY, `${n.id} bottom=${n.y + n.height} > maxY`);
    }
    for (let i = 0; i < nodes.length; i += 1) {
      for (let j = i + 1; j < nodes.length; j += 1) {
        const a = nodes[i];
        const b = nodes[j];
        const overlapX = a.x < b.x + b.width && a.x + a.width > b.x;
        const overlapY = a.y < b.y + b.height && a.y + a.height > b.y;
        assert.equal(overlapX && overlapY, false, `Overlap between ${a.id} and ${b.id}`);
      }
    }

    const layout = computeTopologyLayout(sampleEdges, lang);
    assert.equal(layout.edges.length, sampleEdges.length);
    for (const e of layout.edges) {
      assert.ok(e.d && e.d.startsWith('M '), `Missing path for ${e.key}`);
      assert.ok(e.badgeX >= TOPOLOGY_VIEWBOX.minX && e.badgeX <= TOPOLOGY_VIEWBOX.maxX);
      assert.ok(e.badgeY >= TOPOLOGY_VIEWBOX.minY && e.badgeY <= TOPOLOGY_VIEWBOX.maxY);
    }
  }
});

test('renderTopologyBoard preserves SVG node/edge identity and patchTopologyPulse updates status in place', () => {
  const doc = makeMockSvgDoc();
  const container = doc.createElement('div');
  const interactions = [
    { seq: 1, from: 'team-manager', to: 'ui-frontend-designer', action: 'ASSIGN_TASK' },
  ];
  const state = {
    lang: 'fa',
    seq: 1,
    agents: [{ id: 'ui-frontend-designer', status: 'ACTIVE' }],
    interactions,
    graph: buildGraphFromInteractions(interactions),
    replay: { active: false, playing: false, cursorSeq: null, speed: 1 },
  };

  renderTopologyBoard(container, state, { buildGraph: buildGraphFromInteractions, doc });
  const firstNodeG = container._topoRefs.nodesLayer.children[0];
  const firstEdgeG = container._topoRefs.edgesLayer.children[0];
  assert.ok(firstNodeG && firstEdgeG);

  patchTopologyPulse(container, [{ id: 'ui-frontend-designer', status: 'WORKING' }]);
  const uiNode = container._topoRefs.nodesLayer.children.find((g) => g.getAttribute('data-node-id') === 'ui-frontend-designer');
  assert.equal(uiNode._refs.halo.getAttribute('opacity'), '1');
  assert.equal(container._topoRefs.edgesLayer.children[0], firstEdgeG);

  renderTopologyBoard(container, { ...state, lang: 'en' }, { buildGraph: buildGraphFromInteractions, doc });
  assert.equal(container._topoRefs.nodesLayer.children[0], firstNodeG);
  assert.equal(container._topoRefs.edgesLayer.children[0], firstEdgeG);
});

test('command, chronicle, squad boards and inspector render rich snapshots without throwing', () => {
  const doc = makeMockSvgDoc();
  const sampleState = {
    lang: 'fa',
    theme: 'dark',
    convId: 'conv-1',
    seq: 4,
    chronicleView: 'swimlane',
    chronicleChannel: 'ALL',
    chronicleQuery: '',
    findingFilter: 'ALL',
    wbsFilter: 'ALL',
    squadFilter: 'ALL',
    composerTarget: 'all',
    settingsOpen: true,
    devMode: true,
    thinkTank: {
      project: 'ThinkTank v4', directive: 'Ship v4', status: 'ACTIVE',
      round: 2, maxRounds: 50, pipelineStage: 3, isClosed: true,
      roleCaps: { main: 50, manager: 50, subagents: 50 },
      closureReceipt: { subtasksCompleted: 1, findingsVerified: 1, qaRunsCount: 1, qaAllExitZero: true, originCounts: { subagent: 2 } },
    },
    proposal: {
      status: 'AWAITING_APPROVAL', title: 'Prop', summary: 'Approve plan',
      decisionOptions: [{ id: 'opt-1', label: 'Proceed' }],
    },
    agents: [{ id: 'ui-frontend-designer', status: 'WORKING', activeTool: 'write_file', currentTask: 'Build UI', turnsUsed: 3, verifiedSubagent: true }],
    subtasks: [{ id: 'WBS-UI-02', title: 'Build UI', assignee: 'ui-frontend-designer', status: 'IN_PROGRESS', acceptanceCriteria: '0 FAIL', lockedFiles: ['app.css'] }],
    fileLocks: [{ path: 'app.css', owner: 'ui-frontend-designer', workItemId: 'WBS-UI-02' }],
    findings: [
      { id: 'F-01', title: 'Fix F7', severity: 'HIGH', state: 'InReview', raisedBy: 'council-critic', owner: 'ui-frontend-designer', reproSteps: 'Run lint', returnCount: 1, events: [2], evidence: [{ exitCode: 0, command: 'node --test', excerpt: 'pass', runner: 'substrate' }] },
      { id: 'F-02', title: 'Archived', severity: 'MEDIUM', state: 'Closed', raisedBy: 'council-critic', owner: 'backend-auditor' },
    ],
    messages: [
      { id: 'm1', seq: 1, senderRole: 'team-manager', recipientRole: 'ui-frontend-designer', actionType: 'ASSIGN_TASK', content: 'Build UI', timestamp: '10:00:00' },
      { id: 'm2', seq: 2, senderRole: 'council-critic', recipientRole: 'ui-frontend-designer', actionType: 'RETURN_DEFECT', findingId: 'F-01', content: 'Fix F7', thoughts: 'details', timestamp: '10:01:00' },
    ],
    interactions: [
      { seq: 1, from: 'team-manager', to: 'ui-frontend-designer', action: 'ASSIGN_TASK', timestamp: '10:00:00' },
      { seq: 2, from: 'council-critic', to: 'ui-frontend-designer', action: 'RETURN_DEFECT', findingId: 'F-01', timestamp: '10:01:00' },
    ],
    telemetry: { toolCalls: [{ id: 't1', agent: 'ui-frontend-designer', tool: 'write_file', status: 'DONE', timestamp: '10:02:00' }] },
    conversationsList: [{ convId: 'conv-1', project: 'ThinkTank v4', runIndex: 1, isClosed: true }],
  };

  const cmdEl = doc.createElement('div');
  renderCommandBoard(cmdEl, sampleState, { doc });
  assert.equal(cmdEl._cmdRefs.findingsList.children.length, 1);
  assert.equal(cmdEl._cmdRefs.archiveList.children.length, 1);
  assert.equal(cmdEl._cmdRefs.wbsTbody.children.length, 1);

  const chronEl = doc.createElement('div');
  renderChronicleBoard(chronEl, sampleState, { doc });
  assert.equal(chronEl._chronRefs.swimList.children.length, 2);
  renderChronicleBoard(chronEl, { ...sampleState, chronicleView: 'feed' }, { doc });
  assert.equal(chronEl._chronRefs.feedList.children.length, 2);

  const squadEl = doc.createElement('div');
  renderSquadBoard(squadEl, sampleState, { doc });
  assert.equal(squadEl._squadRefs.squadList.children.length, 9);
  assert.equal(squadEl._squadRefs.locksTbody.children.length, 1);
  assert.equal(squadEl._squadRefs.telTbody.children.length, 1);

  const drawerEl = doc.createElement('aside');
  for (const target of [
    { type: 'finding', id: 'F-01' },
    { type: 'edge', from: 'council-critic', to: 'ui-frontend-designer' },
    { type: 'event', seq: 2 },
    { type: 'role', id: 'ui-frontend-designer' },
  ]) {
    renderDossierDrawer(drawerEl, { ...sampleState, inspector: target }, { doc });
    assert.equal(drawerEl.hidden, false);
  }

  const backdrop = doc.createElement('div');
  const dialog = doc.createElement('div');
  backdrop.appendChild(dialog);
  renderSettingsSheet(dialog, sampleState, { doc });
  assert.equal(backdrop.hidden, false);
  assert.equal(typeof initThinkTankStudio, 'function');
});

test('F-01 & F-02: sidecar.fetch 401 fallback, fetchStatus error guard, workspace discovery, and CREATE_CASE default handling', async () => {
  const store = createCaseStore({ lang: 'fa' });
  const calls = [];
  const sidecarObj = {
    async getWorkspaceUris() { return ['file:///c:/Projects/TestRepo']; },
    onWorkspaceChange() {},
    async fetch(url) {
      calls.push(['sidecar.fetch', url]);
      return { ok: false, status: 401, json: async () => ({ error: 'unauthorized' }) };
    },
  };
  const fetchImpl = async (url, init = {}) => {
    calls.push(['fetchImpl', url, init.method || 'GET', init.body || '']);
    if (String(url).includes('/host/context')) {
      return { ok: true, json: async () => ({ conversationId: 'default', workspaceMatched: false }) };
    }
    if (String(url).includes('/status')) {
      return { ok: false, status: 409, json: async () => ({ detail: 'Different project' }) };
    }
    if (String(url).includes('/conversations')) {
      return { ok: true, json: async () => ({ conversations: [] }) };
    }
    if (String(url).includes('/task/update')) {
      return { ok: false, status: 400, json: async () => ({ detail: 'Explicit convId required' }) };
    }
    return { ok: true, json: async () => ({}) };
  };
  const client = createSyncClient({ store, fetchImpl, WebSocketImpl: null, sidecarObj });
  await client.start();
  assert.equal(store.state.workspaceUri, 'file:///c:/Projects/TestRepo');
  assert.ok(calls.some(([fn, u]) => fn === 'sidecar.fetch' && String(u).startsWith('/api/host/context')));
  assert.ok(calls.some(([fn, u]) => fn === 'fetchImpl' && String(u).includes('http://127.0.0.1:8780/api/host/context')));
  // fetchStatus 409 error must NOT wipe loadState to ready or apply snapshot
  assert.equal(store.state.loadState, 'loading');

  // Direct API 400/500 on fallback preserves error status and CREATE_CASE ignores 'default'
  const errRes = await client.postApi('/task/update', { convId: 'default', project: 'X' });
  assert.equal(errRes.status, 'error');
  assert.equal(errRes.httpStatus, 400);
});

test('F-04: WS stale onclose isolation, seq=0 gap detection, and CASE_EVENT telemetry update', async () => {
  const store = createCaseStore({ convId: 'c-zero' });
  store.applySnapshot({ convId: 'c-zero', sync: { generation: 'g1', seq: 0 }, thinkTank: { project: 'Zero', status: 'ACTIVE' } });
  let statusCalls = 0;
  const sockets = [];
  class MockWs {
    constructor(url) {
      this.url = url;
      this.closed = false;
      sockets.push(this);
    }
    close() { this.closed = true; }
  }
  const fetchImpl = async (url) => {
    if (String(url).includes('/status')) {
      statusCalls += 1;
      return { ok: true, json: async () => ({ convId: 'c-zero', sync: { generation: 'g1', seq: 3 }, thinkTank: { project: 'Zero', status: 'ACTIVE' } }) };
    }
    return { ok: true, json: async () => ({}) };
  };
  const client = createSyncClient({ store, fetchImpl, WebSocketImpl: MockWs, sidecarObj: null });
  client.connectWs();
  const sock1 = sockets[0];
  client.connectWs();
  const sock2 = sockets[1];
  // Closing stale sock1 must NOT flip connState away from live or schedule reconnect over sock2
  sock1.onclose?.();
  assert.equal(store.state.connState, 'live');
  assert.ok(sock2);

  // seq=0 receiving seq=2 triggers gap recovery
  client.handleFrame({ type: 'CASE_EVENT', convId: 'c-zero', generation: 'g1', seq: 2, changedSlices: ['thinkTank'] });
  await new Promise((r) => setTimeout(r, 15));
  assert.equal(statusCalls, 1);

  // telemetry slice inside CASE_EVENT increments telemetryRev
  const telBefore = store.revs.telemetryRev;
  client.handleFrame({
    type: 'CASE_EVENT',
    convId: 'c-zero',
    generation: 'g1',
    seq: 4,
    changedSlices: ['agents', 'telemetry'],
    agents: [{ id: 'seo', status: 'WORKING' }],
    telemetry: { toolCalls: [{ id: 't-case', tool: 'read_file', agentId: 'ecommerce_seo_operator' }], terminalLogs: [], backgroundTasks: [] },
  });
  assert.equal(store.revs.telemetryRev, telBefore + 1);
  assert.equal(store.state.telemetry.toolCalls[0].id, 't-case');
  client.destroy();
});

test('F-05: swimlane percentage coordinates, zero topology node/label/pill overlap, and null exitCode FAIL tag', () => {
  const doc = makeMockSvgDoc();
  const denseEdges = [
    { from: 'main_agent', to: 'team-manager', action: 'ASSIGN_TASK', count: 2 },
    { from: 'team-manager', to: 'ui-frontend-designer', action: 'ASSIGN_TASK', count: 1 },
    { from: 'team-manager', to: 'backend-auditor', action: 'ASSIGN_TASK', count: 1 },
    { from: 'council-critic', to: 'ui-frontend-designer', action: 'RETURN_DEFECT', count: 2 },
    { from: 'council-critic', to: 'wp_technical_operator', action: 'RETURN_DEFECT', count: 1 },
    { from: 'wp_technical_operator', to: 'council-critic', action: 'WORKER_FIX', count: 1 },
    { from: 'code-reviewer', to: 'wp_technical_operator', action: 'REVIEW_QUERY', count: 1 },
    { from: 'code-reviewer', to: 'qa-reviewer', action: 'QA_DISPATCH', count: 1 },
    { from: 'qa-reviewer', to: 'code-reviewer', action: 'QA_REPORT', count: 1 },
    { from: 'ui-frontend-designer', to: 'backend-auditor', action: 'PEER_SYNC', count: 2 },
  ];
  for (const lang of ['fa', 'en']) {
    const layout = computeTopologyLayout(denseEdges, lang);
    const labelBoxes = [
      { left: 380, right: 540, top: 4, bottom: 24, name: 'tier1-label' },
      { left: 40, right: 220, top: 242, bottom: 270, name: 'tier2-label' },
      { left: 380, right: 540, top: 496, bottom: 516, name: 'tier3-label' },
    ];
    for (const e of layout.edges) {
      const halfW = (e.pillW || 80) / 2;
      const box = { left: e.badgeX - halfW, right: e.badgeX + halfW, top: e.badgeY - 9, bottom: e.badgeY + 9 };
      for (const n of layout.nodes) {
        const hitNode = box.left < n.x + n.width && box.right > n.x && box.top < n.y + n.height && box.bottom > n.y;
        assert.equal(hitNode, false, `Pill ${e.key} overlaps node ${n.id}`);
      }
      for (const lb of labelBoxes) {
        const hitLabel = box.left < lb.right && box.right > lb.left && box.top < lb.bottom && box.bottom > lb.top;
        assert.equal(hitLabel, false, `Pill ${e.key} overlaps ${lb.name}`);
      }
    }
  }

  // Chronicle swimlane uses percentage x coordinates instead of fixed viewBox
  const chronEl = doc.createElement('div');
  renderChronicleBoard(chronEl, {
    lang: 'en',
    chronicleView: 'swimlane',
    chronicleChannel: 'ALL',
    chronicleQuery: '',
    interactions: [{ seq: 1, from: 'team-manager', to: 'backend-auditor', action: 'ASSIGN_TASK', timestamp: '10:00:00' }],
    messages: [{ id: 'm1', seq: 1, senderRole: 'team-manager', recipientRole: 'backend-auditor', actionType: 'ASSIGN_TASK', content: 'Go', timestamp: '10:00:00' }],
  }, { doc });
  const swimRow = chronEl._chronRefs.swimList.children[0];
  assert.equal(swimRow._refs.svg.getAttribute('viewBox'), null);
  assert.match(swimRow._refs.line.getAttribute('x1'), /%$/);

  // Command board & inspector treat null/undefined exitCode as FAIL rather than exit 0
  const cmdEl = doc.createElement('div');
  renderCommandBoard(cmdEl, {
    lang: 'en',
    findings: [{ id: 'F-99', title: 'Missing exitCode', severity: 'HIGH', state: 'Testing', evidence: [{ command: 'test', runner: 'substrate' }] }],
    subtasks: [],
    agents: [],
  }, { doc });
  const evTagText = cmdEl._cmdRefs.findingsList.children[0]._refs.evTag.textContent;
  assert.match(evTagText, /^FAIL/);
});

test('never-resolving sidecar.getWorkspaceUris() does not block start() and falls back on HTTP 200 offline proxy wrapper', async () => {
  const store = createCaseStore({ lang: 'fa' });
  const sidecarObj = {
    conversationId: 'conv-hanging-ws',
    getWorkspaceUris() {
      return new Promise(() => {});
    },
    async fetch(url) {
      if (String(url).startsWith('/api/status')) {
        return { ok: true, status: 200, json: async () => ({ status: 'offline', error: 'proxy down' }) };
      }
      return { ok: true, status: 200, json: async () => ({ conversations: [] }) };
    },
  };
  let directStatusCalls = 0;
  const fetchImpl = async (url) => {
    if (String(url).startsWith('http://127.0.0.1:8780/api/status')) {
      directStatusCalls += 1;
      return {
        ok: true,
        status: 200,
        json: async () => ({
          convId: 'conv-hanging-ws',
          hasSession: true,
          sync: { generation: 'g1', seq: 1 },
          thinkTank: { project: 'Unblocked Studio', status: 'ACTIVE' },
        }),
      };
    }
    return { ok: true, status: 200, json: async () => ({ conversations: [] }) };
  };
  const client = createSyncClient({ store, fetchImpl, WebSocketImpl: null, sidecarObj });
  const t0 = Date.now();
  await client.start();
  const elapsedMs = Date.now() - t0;
  assert.ok(elapsedMs < 200, `start() hung for ${elapsedMs}ms`);
  assert.equal(directStatusCalls, 1);
  assert.equal(store.state.loadState, 'ready');
  assert.equal(store.state.hasSession, true);
  assert.equal(store.state.thinkTank.project, 'Unblocked Studio');
});

