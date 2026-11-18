import { CANONICAL_ROLES, normalizeRoleId } from './roles.mjs';
import { normalizeLang } from './i18n.mjs';

export function mergeAgentsWithCatalog(rawAgents = []) {
  const byId = new Map();
  for (const item of Array.isArray(rawAgents) ? rawAgents : []) {
    const id = normalizeRoleId(item?.id || item?.role || item?.agent_name);
    if (id) byId.set(id, item);
  }
  return CANONICAL_ROLES.map((cat) => {
    const live = byId.get(cat.id) || {};
    return {
      ...cat,
      status: String(live.status || 'IDLE').toUpperCase(),
      task: live.currentTask || live.task || '',
      currentTask: live.currentTask || live.task || '',
      tool: live.activeTool || live.tool || '',
      activeTool: live.activeTool || live.tool || '',
      thought: live.thought || '',
      turnsUsed: Number(live.turnsUsed || 0),
      verifiedSubagent: Boolean(live.verifiedSubagent),
      subagentConvId: live.subagentConvId || '',
      collaboratingWith: Array.isArray(live.collaboratingWith) ? live.collaboratingWith : [],
      updatedAtMs: Number(live.updatedAtMs || 0),
    };
  });
}

export function buildGraphFromInteractions(interactions = [], cutoffSeq = null) {
  const edgeMap = new Map();
  let maxSeq = 0;
  let totalEvents = 0;
  for (const it of Array.isArray(interactions) ? interactions : []) {
    const seq = Number(it?.seq || 0);
    if (seq > maxSeq) maxSeq = seq;
    if (cutoffSeq !== null && cutoffSeq !== undefined && seq > cutoffSeq) continue;
    const from = normalizeRoleId(it?.from || it?.senderRole);
    const to = normalizeRoleId(it?.to || it?.recipientRole);
    if (!from || !to || from === 'all' || to === 'all' || from === 'user' || to === 'user') continue;
    if (from === to) continue;
    totalEvents += 1;
    const key = `${from}->${to}`;
    let entry = edgeMap.get(key);
    if (!entry) {
      entry = {
        key, from, to,
        action: it.action || it.requestType || 'CHAT',
        requestType: it.requestType || it.action || 'CHAT',
        channel: it.channel || 'MAIN',
        count: 0, openCount: 0, resolved: true, lastSeq: 0, seqs: [], label: it.label || '',
      };
      edgeMap.set(key, entry);
    }
    entry.count += 1;
    if (it.resolved === false) {
      entry.openCount += 1;
      entry.resolved = false;
    }
    if (seq >= entry.lastSeq) {
      entry.lastSeq = seq;
      entry.action = it.action || entry.action;
      entry.requestType = it.requestType || entry.requestType;
      entry.channel = it.channel || entry.channel;
      entry.label = it.label || entry.label;
    }
    if (seq && !entry.seqs.includes(seq)) entry.seqs.push(seq);
  }
  return { edges: Array.from(edgeMap.values()), totalEvents, maxSeq };
}

function inferChangedSlices(frame = {}) {
  if (Array.isArray(frame.changedSlices) && frame.changedSlices.length) {
    return frame.changedSlices;
  }
  const t = String(frame.type || '').toUpperCase();
  if (t === 'AGENTS_UPDATE') return ['agents'];
  if (t === 'SUBTASKS_UPDATE') return ['subtasks', 'fileLocks'];
  if (t === 'FINDINGS_UPDATE') return ['findings'];
  if (t === 'PROPOSAL_UPDATE') return ['proposal'];
  if (t === 'GOVERNANCE_UPDATE') return ['review', 'thinkTank'];
  if (t === 'STATE_UPDATE') return ['thinkTank'];
  if (t === 'NEW_MESSAGE') return ['messages'];
  if (t === 'COLLABORATION_UPDATE') return ['interactions', 'graph'];
  const inferred = [];
  for (const k of ['thinkTank', 'agents', 'subtasks', 'fileLocks', 'findings', 'messages', 'interactions', 'graph', 'proposal', 'review', 'telemetry', 'conversationsList']) {
    if (k in frame) inferred.push(k);
  }
  if ('message' in frame && !inferred.includes('messages')) inferred.push('messages');
  return inferred;
}

function dedupeMessages(list = []) {
  const byKey = new Map();
  for (const m of list) {
    if (!m) continue;
    const key = m.id || (m.seq ? `seq-${m.seq}` : `${m.senderRole}-${m.timestamp}-${m.content}`);
    byKey.set(key, m);
  }
  return Array.from(byKey.values()).sort((a, b) => Number(a.seq || 0) - Number(b.seq || 0));
}

function dedupeInteractions(list = []) {
  const byKey = new Map();
  for (const it of list) {
    if (!it) continue;
    const from = normalizeRoleId(it.from || it.senderRole);
    const to = normalizeRoleId(it.to || it.recipientRole);
    const key = `${it.seq || 0}:${from}->${to}:${it.action || it.requestType || ''}`;
    byKey.set(key, { ...it, from, to });
  }
  return Array.from(byKey.values()).sort((a, b) => Number(a.seq || 0) - Number(b.seq || 0));
}

export function createCaseStore(prefs = {}) {
  const listeners = new Set();
  const revs = {
    headerRev: 0, pipelineRev: 0, pulseRev: 0, wbsRev: 0,
    findingsRev: 0, topologyRev: 0, ledgerRev: 0, squadRev: 0,
    telemetryRev: 0, uiRev: 0,
  };

  const state = {
    lang: normalizeLang(prefs.lang || 'fa'),
    theme: prefs.theme === 'light' ? 'light' : 'dark',
    activeBoard: ['command', 'topology', 'chronicle', 'squad'].includes(prefs.activeBoard) ? prefs.activeBoard : 'command',
    chronicleView: 'swimlane',
    findingFilter: 'ALL',
    wbsFilter: 'ALL',
    chronicleChannel: 'ALL',
    chronicleQuery: '',
    squadFilter: 'ALL',
    topologyFocusNode: null,
    topologySelectedEdge: null,
    replay: { active: false, playing: false, cursorSeq: null, speed: 1 },
    inspector: null,
    settingsOpen: false,
    devMode: false,
    composerTarget: 'all',
    loadState: 'loading',
    connState: 'syncing',
    offlineError: '',
    actionError: '',
    convId: prefs.convId || '',
    parentConvId: '',
    workspaceUri: prefs.workspaceUri || '',
    projectId: prefs.projectId || '',
    generation: '',
    seq: 0,
    hasSession: false,
    thinkTank: {
      status: 'IDLE', project: '', directive: '', phase: '', round: 1, maxRounds: 50,
      pipelineStage: 1, isClosed: false, hasSession: false, runIndex: 1,
      roleCaps: { main: 50, manager: 50, subagents: 50 }, closureReceipt: null,
    },
    agents: mergeAgentsWithCatalog([]),
    subtasks: [],
    fileLocks: [],
    findings: [],
    messages: [],
    interactions: [],
    graph: { edges: [], totalEvents: 0, maxSeq: 0 },
    proposal: null,
    review: null,
    telemetry: { toolCalls: [], terminalLogs: [], backgroundTasks: [] },
    originCounts: { subagent: 0, 'main-proxy': 0, user: 0 },
    roleUsage: { main: 0, manager: 0, subagents: 0 },
    conversationsList: [],
  };

  const notify = () => { for (const fn of listeners) fn(state, revs); };

  function applySnapshot(raw = {}) {
    const snap = raw.snapshot || raw;
    state.loadState = 'ready';
    state.convId = snap.convId || snap.sync?.conversation_id || state.convId;
    state.parentConvId = snap.parentConvId || state.convId;
    if (snap.workspaceUri) state.workspaceUri = snap.workspaceUri;
    if (snap.projectId) state.projectId = snap.projectId;
    state.generation = snap.sync?.generation || snap.generation || state.generation;
    state.seq = Number(snap.sync?.seq ?? snap.seq ?? state.seq ?? 0);
    const tt = snap.thinkTank || {};
    const isClosed = Boolean(snap.isClosed ?? tt.isClosed);
    const hasSession = Boolean(snap.hasSession ?? tt.hasSession ?? (tt.project || (snap.subtasks || []).length || (snap.messages || []).length));
    state.hasSession = hasSession;
    state.thinkTank = { ...state.thinkTank, ...tt, isClosed, hasSession, pipelineStage: Number(snap.pipelineStage || tt.pipelineStage || 1) };
    state.connState = isClosed ? 'closed' : 'live';
    state.agents = mergeAgentsWithCatalog(snap.agents || []);
    state.subtasks = Array.isArray(snap.subtasks) ? snap.subtasks : [];
    state.fileLocks = Array.isArray(snap.fileLocks) ? snap.fileLocks : [];
    state.findings = Array.isArray(snap.findings) ? snap.findings : [];
    state.messages = dedupeMessages(snap.messages || []);
    state.interactions = dedupeInteractions(snap.interactions || []);
    state.graph = snap.graph?.edges ? snap.graph : buildGraphFromInteractions(state.interactions);
    state.proposal = snap.proposal ?? null;
    state.review = snap.review ?? null;
    if (snap.telemetry) state.telemetry = { ...state.telemetry, ...snap.telemetry };
    if (snap.originCounts) state.originCounts = { ...state.originCounts, ...snap.originCounts };
    if (snap.roleUsage) state.roleUsage = { ...state.roleUsage, ...snap.roleUsage };
    if (Array.isArray(snap.conversationsList)) state.conversationsList = snap.conversationsList;
    for (const k of Object.keys(revs)) revs[k] += 1;
    notify();
  }

  function applyCaseEvent(frame = {}) {
    const slices = new Set(inferChangedSlices(frame));
    if (frame.seq !== undefined && Number(frame.seq) > state.seq) state.seq = Number(frame.seq);
    if (frame.generation) state.generation = frame.generation;
    if (slices.has('thinkTank') || 'closureReceipt' in frame) {
      if (frame.thinkTank) state.thinkTank = { ...state.thinkTank, ...frame.thinkTank };
      if ('closureReceipt' in frame) state.thinkTank.closureReceipt = frame.closureReceipt;
      state.hasSession = Boolean(state.thinkTank.hasSession || state.thinkTank.project || state.subtasks.length);
      state.connState = state.thinkTank.isClosed ? 'closed' : (state.connState === 'offline' ? 'offline' : 'live');
      revs.headerRev += 1;
      revs.pipelineRev += 1;
    }
    if (slices.has('agents')) {
      if (Array.isArray(frame.agents)) state.agents = mergeAgentsWithCatalog(frame.agents);
      revs.pulseRev += 1;
      revs.squadRev += 1;
    }
    if (slices.has('subtasks') || slices.has('fileLocks')) {
      if (Array.isArray(frame.subtasks)) state.subtasks = frame.subtasks;
      if (Array.isArray(frame.fileLocks)) state.fileLocks = frame.fileLocks;
      state.hasSession = state.hasSession || state.subtasks.length > 0;
      revs.wbsRev += 1;
      revs.squadRev += 1;
    }
    if (slices.has('findings')) {
      if (Array.isArray(frame.findings)) state.findings = frame.findings;
      revs.findingsRev += 1;
      revs.pipelineRev += 1;
    }
    if (slices.has('messages') || 'message' in frame) {
      if (Array.isArray(frame.messages)) state.messages = dedupeMessages(frame.messages);
      else if (frame.message) state.messages = dedupeMessages([...state.messages, frame.message]);
      state.hasSession = state.hasSession || state.messages.length > 0;
      revs.ledgerRev += 1;
      revs.pipelineRev += 1;
    }
    if (slices.has('interactions') || slices.has('graph')) {
      if (Array.isArray(frame.interactions)) state.interactions = dedupeInteractions(frame.interactions);
      else if (frame.interaction) state.interactions = dedupeInteractions([...state.interactions, frame.interaction]);
      state.graph = frame.graph?.edges ? frame.graph : buildGraphFromInteractions(state.interactions);
      revs.topologyRev += 1;
      revs.ledgerRev += 1;
    }
    if (slices.has('proposal')) { state.proposal = frame.proposal ?? null; revs.pipelineRev += 1; }
    if (slices.has('review')) { state.review = frame.review ?? null; revs.pipelineRev += 1; }
    if (slices.has('telemetry') || frame.telemetry || frame.telemetryEntry) {
      if (frame.telemetry) {
        state.telemetry = { ...state.telemetry, ...frame.telemetry };
      } else if (frame.telemetryEntry) {
        const nextCalls = [frame.telemetryEntry, ...(state.telemetry.toolCalls || [])].slice(0, 25);
        state.telemetry = { ...state.telemetry, toolCalls: nextCalls };
      }
      revs.telemetryRev += 1;
    }
    if (frame.originCounts) { state.originCounts = { ...state.originCounts, ...frame.originCounts }; revs.pipelineRev += 1; }
    if (frame.roleUsage) { state.roleUsage = { ...state.roleUsage, ...frame.roleUsage }; revs.squadRev += 1; }
    if (slices.has('conversationsList') && Array.isArray(frame.conversationsList)) {
      state.conversationsList = frame.conversationsList;
      revs.headerRev += 1;
    }
    notify();
  }

  function applyTransientPulse(frame = {}) {
    if (frame.telemetry) {
      state.telemetry = { ...state.telemetry, ...frame.telemetry };
      revs.telemetryRev += 1;
    } else if (frame.toolCall) {
      const next = [frame.toolCall, ...(state.telemetry.toolCalls || [])].slice(0, 60);
      state.telemetry = { ...state.telemetry, toolCalls: next };
      revs.telemetryRev += 1;
    }
    const roleId = normalizeRoleId(frame.agentId || frame.roleId || frame.toolCall?.agent || '');
    if (roleId) {
      const toolName = frame.tool || frame.activeTool || frame.toolCall?.tool || '';
      state.agents = state.agents.map((a) => (a.id === roleId
        ? { ...a, status: frame.status || 'WORKING', tool: toolName || a.tool, activeTool: toolName || a.activeTool }
        : a));
      revs.pulseRev += 1;
    }
    notify();
  }

  function setUi(patch = {}) {
    Object.assign(state, patch);
    revs.uiRev += 1;
    notify();
  }

  function setConnection(connState, offlineError = '') {
    state.connState = connState;
    state.offlineError = offlineError;
    if (connState === 'offline') state.loadState = 'offline';
    revs.headerRev += 1;
    notify();
  }

  return {
    state, revs, applySnapshot, applyCaseEvent, applyTransientPulse, setUi, setConnection,
    subscribe(fn) { listeners.add(fn); return () => listeners.delete(fn); },
  };
}
