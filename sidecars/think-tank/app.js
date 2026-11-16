(() => {
  'use strict';

  const $ = (sel, root = document) => root.querySelector(sel);
  const $$ = (sel, root = document) => [...root.querySelectorAll(sel)];

  const I18N = window.ThinkTankI18n || {
    getLanguage: () => 'fa',
    setLanguage: () => {},
    applyLanguage: () => {},
    tKey: (k) => k,
    translate: (k) => k,
    formatNumber: (n) => String(n),
    roleText: (r, f) => r[f] || '',
    skillNames: {},
  };

  const tKey = (key, vars = null) => (
    I18N.tKey ? I18N.tKey(key, state.language, vars) : key
  );
  const t = (text) => (I18N.translate ? I18N.translate(text, state.language) : text);
  const num = (n) => (I18N.formatNumber ? I18N.formatNumber(n, state.language) : String(n));

  const ROLE_DEFAULTS = {
    main_agent: { monogram: 'MA', frameShape: 'hexagon', tier: 'coordinator' },
    'team-manager': { monogram: 'TM', frameShape: 'square', tier: 'supervisor' },
    'council-critic': { monogram: 'CC', frameShape: 'square', tier: 'supervisor' },
    'code-reviewer': { monogram: 'CR', frameShape: 'square', tier: 'supervisor' },
    'qa-reviewer': { monogram: 'QA', frameShape: 'diamond', tier: 'tester' },
    'ui-frontend-designer': { monogram: 'UI', frameShape: 'circle', tier: 'worker' },
    'backend-auditor': { monogram: 'BE', frameShape: 'circle', tier: 'worker' },
    ecommerce_seo_operator: { monogram: 'SE', frameShape: 'circle', tier: 'worker' },
    wp_technical_operator: { monogram: 'WP', frameShape: 'circle', tier: 'worker' },
  };

  const ROLE_GLYPHS = {
    main_agent: '<polygon points="10,2 17,6 17,14 10,18 3,14 3,6"/><circle cx="10" cy="10" r="2.2"/>',
    'team-manager': '<rect x="7.5" y="2.5" width="5" height="3.5" rx="1"/><rect x="2.5" y="13.5" width="5" height="3.5" rx="1"/><rect x="12.5" y="13.5" width="5" height="3.5" rx="1"/><path d="M10 6v3.5M5 13.5v-4h10v4"/>',
    'council-critic': '<circle cx="9" cy="9" r="5"/><path d="M13 13l4 4M9 6.8v2.6M9 11.4v.4"/>',
    'code-reviewer': '<path d="M6.5 6.5L3 10l3.5 3.5M13.5 6.5L17 10l-3.5 3.5M11.5 5l-3 10"/>',
    'qa-reviewer': '<path d="M8 3h4M8.5 3v4.5l-4 7.5A1.5 1.5 0 0 0 5.8 17h8.4a1.5 1.5 0 0 0 1.3-2l-4-7.5V3"/><path d="M7.5 13l1.6 1.6 3.4-3.6"/>',
    'ui-frontend-designer': '<rect x="3" y="3" width="14" height="14" rx="2"/><path d="M3 8h14M8.5 8v9"/>',
    'backend-auditor': '<ellipse cx="10" cy="5.5" rx="6" ry="2.2"/><path d="M4 5.5v4.5c0 1.2 2.7 2.2 6 2.2s6-1 6-2.2V5.5M4 10v4.5c0 1.2 2.7 2.2 6 2.2s6-1 6-2.2V10"/>',
    ecommerce_seo_operator: '<path d="M3 14.5l4.5-4.5 3 2.5L17 6"/><path d="M13 6h4v4"/>',
    wp_technical_operator: '<path d="M3 5.5h14M3 10h14M3 14.5h14"/><circle cx="7" cy="5.5" r="1.5" fill="currentColor"/><circle cx="13" cy="10" r="1.5" fill="currentColor"/><circle cx="8.5" cy="14.5" r="1.5" fill="currentColor"/>',
  };

  const ACTION_TO_REQUEST_TYPE = {
    DELEGATE: 'REFERRAL',
    ASSIGN_SUBTASK: 'REFERRAL',
    SUBTASK_UPDATE: 'REFERRAL',
    REFERRAL: 'REFERRAL',
    WORKER_FIX: 'REWRITE',
    REVISION_REQUESTED: 'REWRITE',
    REWRITE: 'REWRITE',
    REVIEW_QUERY: 'QUESTION',
    QUESTION: 'QUESTION',
    INTERROGATE: 'INTERROGATION',
    INTERROGATE_REPLY: 'INTERROGATION',
    INTERROGATION: 'INTERROGATION',
    RETURN_DEFECT: 'DEFECT_RETURN',
    QA_REOPEN: 'DEFECT_RETURN',
    DEFECT_RETURN: 'DEFECT_RETURN',
    CRITIQUE: 'CRITIQUE',
    QA_REPORT: 'QA_REPORT',
    QA_DISPATCH: 'QA_REPORT',
    PEER_SYNC: 'PEER_SYNC',
    APPROVE: 'DECISION',
    DECIDE: 'DECISION',
    DECISION: 'DECISION',
    PROPOSAL: 'DECISION',
    COMPLETE: 'DECISION',
    GOVERNANCE: 'DECISION',
    MESSAGE: 'MESSAGE',
  };

  const SVG_ICONS = {
    sun: '<svg viewBox="0 0 20 20" width="16" height="16" fill="none" stroke="currentColor" stroke-width="1.6" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><circle cx="10" cy="10" r="3.5"></circle><path d="M10 2.5v1.5M10 16v1.5M2.5 10H4M16 10h1.5M4.7 4.7l1.1 1.1M14.2 14.2l1.1 1.1M15.3 4.7l-1.1 1.1M5.8 14.2l-1.1 1.1"></path></svg>',
    moon: '<svg viewBox="0 0 20 20" width="16" height="16" fill="none" stroke="currentColor" stroke-width="1.6" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M16 12.5A6.5 6.5 0 0 1 7.5 4a6.8 6.8 0 1 0 8.5 8.5z"></path></svg>',
    check: '<svg class="lifecycle-check-draw" viewBox="0 0 20 20" width="14" height="14" fill="none" stroke="currentColor" stroke-width="2.2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M4.5 10.5l3.5 3.5 7.5-8"></path></svg>',
    flag: '<svg viewBox="0 0 20 20" width="15" height="15" fill="none" stroke="currentColor" stroke-width="1.6" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M5 3v14M5 4h10l-2 3.5L15 11H5"></path></svg>',
    pin: '<svg viewBox="0 0 20 20" width="15" height="15" fill="none" stroke="currentColor" stroke-width="1.6" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M10 3l2.2 4.5 4.8.7-3.5 3.4.8 4.9L10 14.2 5.7 16.5l.8-4.9L3 8.2l4.8-.7L10 3z"></path></svg>',
    play: '<svg viewBox="0 0 20 20" width="14" height="14" fill="currentColor" aria-hidden="true"><path d="M6 4.5l10 5.5-10 5.5V4.5z"></path></svg>',
    pause: '<svg viewBox="0 0 20 20" width="14" height="14" fill="currentColor" aria-hidden="true"><rect x="5" y="4" width="3.5" height="12" rx="1"></rect><rect x="11.5" y="4" width="3.5" height="12" rx="1"></rect></svg>',
    arrow: '<svg class="dir-arrow" viewBox="0 0 20 20" width="14" height="14" fill="none" stroke="currentColor" stroke-width="1.6" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M4 10h12M11.5 5.5L16 10l-4.5 4.5"></path></svg>',
    // Unified 20x20 action icons (shape only)
    RETURN_DEFECT: '<svg viewBox="0 0 20 20" width="15" height="15" fill="none" stroke="currentColor" stroke-width="1.6" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M5 3v14M5 4h10l-2 3.5L15 11H5"></path></svg>',
    WORKER_FIX: '<svg viewBox="0 0 20 20" width="15" height="15" fill="none" stroke="currentColor" stroke-width="1.6" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M13.5 3.5a3.5 3.5 0 0 0-4.4 4.4L4.2 12.8a1.5 1.5 0 0 0 2.1 2.1l4.9-4.9a3.5 3.5 0 0 0 4.4-4.4l-2 2-1.8-.4-.4-1.8 2-1.9z"></path></svg>',
    REVIEW_QUERY: '<svg viewBox="0 0 20 20" width="15" height="15" fill="none" stroke="currentColor" stroke-width="1.6" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M4 5a2 2 0 0 1 2-2h8a2 2 0 0 1 2 2v6a2 2 0 0 1-2 2H8l-4 3.5V5z"></path><path d="M8.5 7.2a1.6 1.6 0 1 1 2.6 1.2c-.6.4-1.1.8-1.1 1.6"></path></svg>',
    QA_DISPATCH: '<svg viewBox="0 0 20 20" width="15" height="15" fill="none" stroke="currentColor" stroke-width="1.6" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M7.5 3.5h5M8.5 3.5v4.8L5 14.5A1.5 1.5 0 0 0 6.3 16.5h7.4A1.5 1.5 0 0 0 15 14.5l-3.5-6.2V3.5"></path></svg>',
    QA_REPORT: '<svg viewBox="0 0 20 20" width="15" height="15" fill="none" stroke="currentColor" stroke-width="1.6" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M7.5 3.5h5M8.5 3.5v4.8L5 14.5A1.5 1.5 0 0 0 6.3 16.5h7.4A1.5 1.5 0 0 0 15 14.5l-3.5-6.2V3.5"></path><path d="M8 13l1.5 1.5L12.5 11"></path></svg>',
    PEER_SYNC: '<svg viewBox="0 0 20 20" width="15" height="15" fill="none" stroke="currentColor" stroke-width="1.6" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M4 7h11l-2.5-2.5M16 13H5l2.5 2.5"></path></svg>',
    INTERROGATE: '<svg viewBox="0 0 20 20" width="15" height="15" fill="none" stroke="currentColor" stroke-width="1.6" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><circle cx="9" cy="9" r="5"></circle><path d="M13 13l3.5 3.5"></path></svg>',
    DELEGATE: '<svg viewBox="0 0 20 20" width="15" height="15" fill="none" stroke="currentColor" stroke-width="1.6" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><rect x="4" y="3.5" width="12" height="13" rx="1.5"></rect><path d="M7 8h6M7 11.5h4"></path></svg>',
    MESSAGE: '<svg viewBox="0 0 20 20" width="15" height="15" fill="none" stroke="currentColor" stroke-width="1.6" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M4 5.5A2 2 0 0 1 6 3.5h8a2 2 0 0 1 2 2v5a2 2 0 0 1-2 2H8l-4 3.5V5.5z"></path></svg>',
    // Origin icons
    originSubagent: '<svg viewBox="0 0 20 20" width="14" height="14" fill="none" stroke="currentColor" stroke-width="1.6" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><rect x="4" y="4" width="12" height="12" rx="2"></rect><circle cx="10" cy="10" r="2"></circle></svg>',
    originMainProxy: '<svg viewBox="0 0 20 20" width="14" height="14" fill="none" stroke="currentColor" stroke-width="1.6" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><polygon points="10,2.5 16.5,6.2 16.5,13.8 10,17.5 3.5,13.8 3.5,6.2"></polygon><path d="M8 10h4M10.5 8l2 2-2 2"></path></svg>',
    originUser: '<svg viewBox="0 0 20 20" width="14" height="14" fill="none" stroke="currentColor" stroke-width="1.6" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><circle cx="10" cy="7" r="2.8"></circle><path d="M4.5 16.5a5.5 5.5 0 0 1 11 0"></path></svg>',
  };

  const state = {
    activeConvId: null,
    hostConvId: null,
    workspaceUri: '',
    pinnedConvId: null,
    userPinnedConv: false,
    convSearchQuery: '',
    hasSession: false,
    project: '',
    directive: '',
    phase: '',
    status: 'DISCONNECTED',
    progress: 0,
    round: 0,
    maxRounds: 50,
    runIndex: 1,
    isClosed: false,
    roleCaps: {},
    roleUsage: {},
    triageDecision: null,
    closureReceipt: null,
    originCounts: { subagent: 0, 'main-proxy': 0, user: 0 },
    conversations: [],
    roles: [],
    agents: [],
    messages: [],
    interactions: [],
    findings: [],
    fileLocks: [],
    subtasks: [],
    proposal: null,
    review: null,
    activeTab: 'flow',
    mapSubview: 'sequence',
    findingFilter: null,
    wbsFilter: null,
    boardChannel: 'ALL',
    boardSearchQuery: '',
    teamTier: 'all',
    rawKind: 'findings',
    inspectorItem: null,
    settingsOpen: false,
    devMode: localStorage.getItem('thinktank-dev-mode') === 'true',
    replayLive: true,
    replaySeq: 0,
    replaySpeed: 700,
    replayTimer: null,
    selectedProposalOption: null,
    revisionDraftOpen: false,
    pendingResetCase: false,
    telemetry: { toolCalls: [], terminalLogs: [], backgroundTasks: [] },
    connected: false,
    lastSeenSeq: 0,
    wsGeneration: null,
    theme: localStorage.getItem('thinktank-theme') || 'dark',
    language: I18N.getLanguage ? I18N.getLanguage() : 'fa',
    ws: null,
    reconnectTimer: null,
    pollTimer: null,
    hostContextTimer: null,
    toastTimer: null,
  };

  let dataRevision = 0;
  let lastSnapshotHash = '';
  let recordedEventsCache = { rev: -1, events: [] };
  let replayTicksStructKey = '';
  let seqDiagramStructKey = '';
  let srTableCacheKey = '';

  const signatures = {
    header: '',
    flow: '',
    map: '',
    team: '',
    inspector: '',
  };

  function inspectorKey() {
    const it = state.inspectorItem;
    if (!it) return '';
    return `${it.type}:${it.id || it.seq || `${normalizeRoleId(it.from)}->${normalizeRoleId(it.to)}`}`;
  }

  function preserveDetailsOpen(container, updateFn) {
    if (!container) return updateFn();
    const openKeys = new Set(
      [...container.querySelectorAll('details[open][data-details-key]')].map((d) => d.dataset.detailsKey)
    );
    updateFn();
    if (!openKeys.size) return;
    for (const d of container.querySelectorAll('details[data-details-key]')) {
      if (openKeys.has(d.dataset.detailsKey)) d.open = true;
    }
  }

  const TAB_LIST = ['flow', 'map', 'team'];
  const SEVERITY_RANK = { CRITICAL: 0, HIGH: 1, MEDIUM: 2, LOW: 3 };
  const ACTIVE_FINDING_STATES = new Set(['Open', 'Fixing', 'InReview', 'Testing']);
  const LIFECYCLE_STAGES = [
    { key: 'Open', labelKey: 'flow.findings.rail.open', tone: 'open', states: ['Open'] },
    { key: 'Fixing', labelKey: 'flow.findings.rail.fixing', tone: 'working', states: ['Fixing'] },
    { key: 'InReview', labelKey: 'flow.findings.rail.inReview', tone: 'review', states: ['InReview'] },
    { key: 'Testing', labelKey: 'flow.findings.rail.testing', tone: 'working', states: ['Testing'] },
    { key: 'Verified', labelKey: 'flow.findings.rail.verified', tone: 'verified', states: ['Verified', 'Closed'] },
  ];

  function esc(str) {
    return String(str ?? '')
      .replace(/&/g, '&amp;')
      .replace(/</g, '&lt;')
      .replace(/>/g, '&gt;')
      .replace(/"/g, '&quot;')
      .replace(/'/g, '&#39;');
  }

  function toast(msg) {
    const el = $('#toast');
    if (!el) return;
    el.textContent = msg;
    el.classList.remove('hidden');
    clearTimeout(state.toastTimer);
    state.toastTimer = setTimeout(() => el.classList.add('hidden'), 3200);
  }

  function normalizeRoleId(raw) {
    const v = String(raw || '').trim().toLowerCase().replace(/^(?:agent|tt)[_-]/, '');
    const map = {
      team_manager: 'team-manager',
      manager: 'team-manager',
      coordinator: 'team-manager',
      council_critic: 'council-critic',
      critic: 'council-critic',
      code_reviewer: 'code-reviewer',
      reviewer: 'code-reviewer',
      qa_reviewer: 'qa-reviewer',
      ui_frontend_designer: 'ui-frontend-designer',
      designer_solver: 'ui-frontend-designer',
      backend_auditor: 'backend-auditor',
      backend_engineer: 'backend-auditor',
      security_reviewer: 'backend-auditor',
      seo_specialist: 'ecommerce_seo_operator',
      'ecommerce-seo-operator': 'ecommerce_seo_operator',
      'wp-technical-operator': 'wp_technical_operator',
      main: 'main_agent',
      main_agent: 'main_agent',
    };
    return map[v] || v;
  }

  function getRoleMeta(roleId) {
    const canon = normalizeRoleId(roleId);
    const catalogRole = state.roles.find((r) => r.id === canon);
    const fallback = ROLE_DEFAULTS[canon] || { monogram: canon.slice(0, 2).toUpperCase() || 'AG', frameShape: 'circle', tier: 'worker' };
    return {
      id: canon,
      monogram: catalogRole?.monogram || fallback.monogram,
      frameShape: catalogRole?.frameShape || fallback.frameShape,
      tier: catalogRole?.tier || fallback.tier,
      role: catalogRole,
    };
  }

  function roleLabel(roleId) {
    const raw = String(roleId || '').trim();
    if (!raw || raw.toLowerCase() === 'user') return tKey('flow.composer.senderYou');
    const meta = getRoleMeta(raw);
    if (meta.role) return I18N.roleText ? I18N.roleText(meta.role, 'title', state.language) : meta.role.title;
    const live = state.agents.find((a) => normalizeRoleId(a.id) === meta.id);
    return (live && live.name) || raw;
  }

  function roleBilingualLabel(roleId) {
    const raw = String(roleId || '').trim();
    if (!raw || raw.toLowerCase() === 'user') {
      const faYou = I18N.tKey ? I18N.tKey('flow.composer.senderYou', 'fa') : 'شما';
      const enYou = I18N.tKey ? I18N.tKey('flow.composer.senderYou', 'en') : 'You';
      return state.language === 'en' ? `${enYou} · ${faYou}` : `${faYou} · ${enYou}`;
    }
    const meta = getRoleMeta(raw);
    const roleObj = meta.role || { id: meta.id, title: raw };
    const faTitle = (I18N.roleText ? I18N.roleText(roleObj, 'title', 'fa') : roleObj.title) || raw;
    const enTitle = (I18N.roleText ? I18N.roleText(roleObj, 'title', 'en') : '') || meta.id;
    const primary = state.language === 'en' ? enTitle : faTitle;
    const secondary = state.language === 'en' ? faTitle : enTitle;
    const pair = secondary && secondary !== primary ? `${primary} · ${secondary}` : primary;
    return meta.monogram ? `${pair} (${meta.monogram})` : pair;
  }

  function renderRoleMonogram(roleId, size = 26) {
    const raw = String(roleId || '').trim().toLowerCase();
    const tip = roleBilingualLabel(roleId);
    if (raw === 'user') {
      return `<span class="role-monogram" data-role-tooltip="${esc(tip)}" title="${esc(tip)}">${SVG_ICONS.originUser}</span>`;
    }
    const { monogram, frameShape, id } = getRoleMeta(roleId);
    const label = roleLabel(id);
    const glyph = ROLE_GLYPHS[id] || ROLE_GLYPHS.main_agent;
    let shapeSvg = '';
    if (frameShape === 'hexagon') {
      shapeSvg = '<polygon points="16,2 28,9 28,23 16,30 4,23 4,9" fill="var(--paper)" stroke="currentColor" stroke-width="1.5"/>';
    } else if (frameShape === 'square') {
      shapeSvg = '<rect x="3" y="3" width="26" height="26" rx="4" fill="var(--paper)" stroke="currentColor" stroke-width="1.5"/>';
    } else if (frameShape === 'diamond') {
      shapeSvg = '<polygon points="16,2 30,16 16,30 2,16" fill="var(--paper)" stroke="currentColor" stroke-width="1.5"/>';
    } else {
      shapeSvg = '<circle cx="16" cy="16" r="13" fill="var(--paper)" stroke="currentColor" stroke-width="1.5"/>';
    }
    return `<span class="role-monogram" data-role="${esc(id)}" data-monogram="${esc(monogram)}" data-role-tooltip="${esc(tip)}" title="${esc(tip)}" aria-label="${esc(label)}">
      <svg viewBox="0 0 32 32" width="${size}" height="${size}" aria-hidden="true">
        ${shapeSvg}
        <g transform="translate(7.5,7.5) scale(0.85)" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round">${glyph}</g>
      </svg>
      <span class="role-monogram-code" aria-hidden="true">${esc(monogram)}</span>
    </span>`;
  }

  function stateTone(st) {
    const s = String(st || '').toUpperCase();
    if (s === 'OPEN' || s === 'BLOCKED' || s === 'FAIL') return 'open';
    if (s === 'FIXING' || s === 'TESTING' || s === 'IN_PROGRESS' || s === 'WORKING' || s === 'ACTIVE') return 'working';
    if (s === 'INREVIEW' || s === 'IN_REVIEW' || s === 'ASSIGNED' || s === 'REVIEW') return 'review';
    if (s === 'VERIFIED' || s === 'CLOSED' || s === 'COMPLETED' || s === 'DONE' || s === 'PASS') return 'verified';
    return 'muted';
  }

  function findingStateLabel(st) {
    return tKey(`flow.findings.state.${st}`) || st;
  }

  function translateStatus(rawStatus) {
    const up = String(rawStatus || 'IDLE').toUpperCase().trim();
    const map = {
      ACTIVE: ['فعال', 'Active'],
      WORKING: ['در حال کار', 'Working'],
      COMPLETED: ['تکمیل‌شده', 'Completed'],
      DONE: ['تکمیل‌شده', 'Completed'],
      CLOSED: ['بسته', 'Closed'],
      IDLE: ['آماده', 'Idle'],
      ASSIGNED: ['واگذارشده', 'Assigned'],
      IN_PROGRESS: ['در حال انجام', 'In Progress'],
      IN_REVIEW: ['در حال بازبینی', 'In Review'],
      BLOCKED: ['مسدود', 'Blocked'],
      PAUSED: ['متوقف', 'Paused'],
      AWAITING_APPROVAL: ['منتظر تأیید کاربر', 'Awaiting Approval'],
      WAITING_FOR_HUMAN: ['منتظر تصمیم کاربر', 'Waiting for Human'],
      DISCONNECTED: ['قطع اتصال', 'Disconnected'],
      APPROVED: ['تأییدشده', 'Approved'],
      REJECTED: ['ردشده', 'Rejected'],
      APPROVE: ['موافق', 'Approve'],
      CONDITIONAL: ['موافقت مشروط', 'Conditional'],
      CRITIQUE: ['نقد و چالش', 'Critique'],
      REVIEW: ['در بازبینی', 'In Review'],
    };
    const pair = map[up];
    if (pair) return state.language === 'en' ? pair[1] : pair[0];
    return t(String(rawStatus || ''));
  }

  function actionLabel(actionUpper) {
    const key = `action.${actionUpper}`;
    const translated = tKey(key);
    return translated !== key ? translated : (actionUpper || 'MESSAGE');
  }

  function actionIcon(actionUpper) {
    return SVG_ICONS[actionUpper] || SVG_ICONS.MESSAGE;
  }

  function resolveRequestType(item) {
    const raw = String(item?.requestType || '').trim();
    if (raw) return raw.toUpperCase();
    const act = String(item?.actionType || item?.action || 'MESSAGE').toUpperCase();
    return ACTION_TO_REQUEST_TYPE[act] || 'MESSAGE';
  }

  function requestTypeLabel(item) {
    const code = resolveRequestType(item);
    const key = `reqType.${code}`;
    const translated = tKey(key);
    if (translated !== key) return translated;
    return item?.requestType ? String(item.requestType) : actionLabel(item?.actionType || item?.action || 'MESSAGE');
  }

  function originIconAndLabel(origin) {
    const o = String(origin || 'main-proxy').toLowerCase();
    if (o === 'subagent') return { icon: SVG_ICONS.originSubagent, label: tKey('flow.ledger.origin.subagent') };
    if (o === 'user') return { icon: SVG_ICONS.originUser, label: tKey('flow.ledger.origin.user') };
    return { icon: SVG_ICONS.originMainProxy, label: tKey('flow.ledger.origin.main-proxy') };
  }

  async function apiGet(path) {
    let res = null;
    try {
      res = await fetch(path, { headers: { Accept: 'application/json' } });
    } catch (_) {
      res = null;
    }
    if (!res || !res.ok) {
      const backendUrl = `http://127.0.0.1:8780${path.startsWith('/api') ? path : `/api${path}`}`;
      res = await fetch(backendUrl, { headers: { Accept: 'application/json' } });
    }
    const body = await res.json().catch(() => ({}));
    if (!res.ok || (body && body.status === 'error' && Number(body.httpStatus) >= 400)) {
      const err = new Error(body.detail || body.error || `HTTP ${body?.httpStatus || res.status}`);
      err.status = Number(body?.httpStatus) || res.status;
      throw err;
    }
    return body;
  }

  async function apiPost(path, data) {
    const runFetch = async (url) => fetch(url, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json', Accept: 'application/json' },
      body: JSON.stringify(data),
    });
    let res = null;
    try {
      res = await runFetch(path);
    } catch (_) {
      res = null;
    }
    if (!res || (res.status === 404 && !path.startsWith('http'))) {
      const backendUrl = `http://127.0.0.1:8780${path.startsWith('/api') ? path : `/api${path}`}`;
      res = await runFetch(backendUrl);
    }
    const body = await res.json().catch(() => ({}));
    if (!res.ok || (body && body.status === 'error' && Number(body.httpStatus) >= 400)) {
      const err = new Error(body.detail || body.error || `HTTP ${body?.httpStatus || res.status}`);
      err.status = Number(body?.httpStatus) || res.status;
      throw err;
    }
    return body;
  }

  function resolveHostConvId(ctx) {
    const params = new URLSearchParams(window.location.search);
    const explicitDeepLink = params.get('convId');
    if (explicitDeepLink && explicitDeepLink.trim()) return explicitDeepLink.trim();

    if (ctx && typeof ctx === 'object' && ('conversationId' in ctx || 'convId' in ctx)) {
      const liveCid = String(ctx.conversationId || ctx.convId || '').trim();
      if (liveCid && liveCid !== 'default') return liveCid;
      if (ctx.workspaceMatched === false) return '';
    }

    const urlConvId = params.get('conversationId');
    if (urlConvId && urlConvId.trim() && urlConvId.trim() !== 'default') return urlConvId.trim();

    const candidates = [
      window.__ANTIGRAVITY_HOST_CONTEXT__?.conversationId,
      window.__ANTIGRAVITY_HOST_CONTEXT__?.convId,
      window.sidecar?.conversationId,
      window.sidecar?.convId,
    ];
    for (const c of candidates) {
      if (typeof c === 'string' && c.trim() && c.trim() !== 'default') return c.trim();
    }
    return '';
  }

  async function fetchStatusForConv(cid) {
    const rawTarget = (cid || state.activeConvId || '').trim();
    const target = rawTarget || (state.workspaceUri ? 'default' : '');
    const params = new URLSearchParams();
    if (target) params.set('convId', target);
    if (state.workspaceUri) params.set('workspaceUri', state.workspaceUri);
    const qs = params.toString() ? `?${params.toString()}` : '';
    return apiGet(`/api/status${qs}`);
  }

  function invalidateSignatures() {
    for (const k of Object.keys(signatures)) signatures[k] = '';
    replayTicksStructKey = '';
    seqDiagramStructKey = '';
    srTableCacheKey = '';
  }

  function resetConversationViewState() {
    clearInterval(state.replayTimer);
    state.replayTimer = null;
    state.replayLive = true;
    state.replaySeq = 0;
    state.lastSeenSeq = 0;
    state.wsGeneration = null;
    state.inspectorItem = null;
    state.findingFilter = null;
    state.wbsFilter = null;
    state.selectedProposalOption = null;
    state.hasSession = false;
    state.project = '';
    state.directive = '';
    state.phase = '';
    state.status = 'DISCONNECTED';
    state.progress = 0;
    state.round = 0;
    state.runIndex = 1;
    state.isClosed = false;
    state.triageDecision = null;
    state.closureReceipt = null;
    state.originCounts = { subagent: 0, 'main-proxy': 0, user: 0 };
    state.agents = [];
    state.messages = [];
    state.interactions = [];
    state.findings = [];
    state.fileLocks = [];
    state.subtasks = [];
    state.proposal = null;
    state.review = null;
    dataRevision += 1;
    lastSnapshotHash = '';
    invalidateSignatures();
  }

  let switchRequestSeq = 0;
  async function switchConversation(newCid, pinnedByUser = false) {
    const clean = (newCid || '').trim();
    if (!clean || clean === state.activeConvId) return;
    const reqSeq = ++switchRequestSeq;
    state.activeConvId = clean;
    state.userPinnedConv = pinnedByUser;
    state.pinnedConvId = pinnedByUser ? clean : null;
    if (state.ws) {
      const prevWs = state.ws;
      state.ws = null;
      try { prevWs.close(); } catch (_) {}
    }
    try {
      const data = await fetchStatusForConv(clean);
      if (reqSeq !== switchRequestSeq || state.activeConvId !== clean) return;
      resetConversationViewState();
      applySnapshot(data, clean);
    } catch (err) {
      if (reqSeq !== switchRequestSeq) return;
      if (err && Number(err.status) === 403) {
        state.userPinnedConv = false;
        state.pinnedConvId = null;
        state.activeConvId = state.hostConvId && state.hostConvId !== clean ? state.hostConvId : '';
        resetConversationViewState();
        renderAll();
        if (err.message) toast(err.message);
      } else {
        resetConversationViewState();
        await refreshStatus();
      }
    }
    if (reqSeq === switchRequestSeq && state.activeConvId) connectWebSocket();
  }

  function applyTheme(theme) {
    const chosen = theme === 'light' ? 'light' : 'dark';
    state.theme = chosen;
    localStorage.setItem('thinktank-theme', chosen);
    document.documentElement.setAttribute('data-theme', chosen);
    if (chosen === 'dark') {
      document.documentElement.classList.add('dark');
    } else {
      document.documentElement.classList.remove('dark');
    }
    const btn = $('#theme-toggle');
    if (btn) {
      btn.setAttribute('aria-pressed', chosen === 'dark' ? 'true' : 'false');
      const slot = $('#theme-icon-slot');
      if (slot) slot.innerHTML = chosen === 'dark' ? SVG_ICONS.sun : SVG_ICONS.moon;
    }
  }

  function applyLang(locale) {
    const chosen = locale === 'en' ? 'en' : 'fa';
    state.language = chosen;
    document.documentElement.lang = chosen;
    document.documentElement.dir = chosen === 'en' ? 'ltr' : 'rtl';
    if (I18N.setLanguage) I18N.setLanguage(chosen);
    if (I18N.applyLanguage) I18N.applyLanguage(chosen, false);
    const lbl = $('#language-toggle-label');
    if (lbl) lbl.textContent = chosen === 'en' ? 'FA' : 'EN';
    invalidateSignatures();
    populateTargetSelect(true);
    renderAll();
  }

  function activateTab(tabId) {
    const chosen = TAB_LIST.includes(tabId) ? tabId : 'flow';
    state.activeTab = chosen;
    for (const btn of $$('.primary-nav .nav-tab')) {
      const active = btn.dataset.tab === chosen;
      btn.classList.toggle('is-active', active);
      btn.setAttribute('aria-selected', active ? 'true' : 'false');
      btn.tabIndex = active ? 0 : -1;
    }
    for (const id of TAB_LIST) {
      const panel = $(`#tab-${id}`);
      if (panel) panel.classList.toggle('hidden', id !== chosen);
    }
    if (chosen === 'map') renderMap();
    if (chosen === 'team') renderTeam();
  }

  function computeHasSession(data, tt) {
    if (typeof data.hasSession === 'boolean') return data.hasSession;
    if (typeof tt.hasSession === 'boolean') return tt.hasSession;
    const statusUp = String(tt.status || '').toUpperCase().trim();
    if (statusUp && !['DISCONNECTED', 'IDLE'].includes(statusUp)) return true;
    if (String(tt.project || '').trim() || String(tt.directive || '').trim()) return true;
    if ((data.messages && data.messages.length) || (data.subtasks && data.subtasks.length) || (data.findings && data.findings.length)) return true;
    if (data.proposal || data.review) return true;
    return false;
  }

  function applySnapshot(data, requestedCid = null) {
    if (!data || typeof data !== 'object') return;
    const isWildcardActive = !state.activeConvId || state.activeConvId === 'default';
    const isParentResolved = Boolean(requestedCid && requestedCid === state.activeConvId && data.convId && data.convId === data.parentConvId);
    if (data.convId && !isWildcardActive && data.convId !== state.activeConvId && !state.userPinnedConv && !isParentResolved) return;
    if (data.convId && (isWildcardActive || (!state.userPinnedConv && isParentResolved))) state.activeConvId = data.convId;

    const tt = data.thinkTank || {};
    const incomingSyncSeq = Number(data.sync?.seq || 0);
    const incomingRunIdx = Number(tt.runIndex ?? data.runIndex ?? 1);
    if (
      data.convId
      && data.convId === state.activeConvId
      && incomingSyncSeq > 0
      && state.lastSeenSeq > 0
      && incomingSyncSeq < state.lastSeenSeq
      && incomingRunIdx <= Number(state.runIndex || 1)
    ) {
      return;
    }
    const snapKey = JSON.stringify({
      c: data.convId || state.activeConvId || '',
      hs: data.hasSession,
      ic: data.isClosed,
      tt,
      a: data.agents,
      m: data.messages,
      i: data.interactions,
      f: data.findings,
      l: data.fileLocks,
      s: data.subtasks,
      p: data.proposal,
      r: data.review,
      o: data.originCounts,
      u: data.roleUsage,
      cr: data.closureReceipt,
    });
    const snapChanged = snapKey !== lastSnapshotHash;
    if (snapChanged) {
      lastSnapshotHash = snapKey;
      dataRevision += 1;
    }

    const prevRunIndex = state.runIndex;
    const prevHasSession = state.hasSession;
    state.hasSession = computeHasSession(data, tt);
    state.project = tt.project ?? '';
    state.directive = tt.directive ?? '';
    state.phase = tt.phase ?? '';
    state.status = tt.status ?? 'DISCONNECTED';
    state.progress = Number(tt.progress ?? 0);
    state.round = Number(tt.round ?? 0);
    state.maxRounds = Number(tt.maxRounds ?? 50);
    state.runIndex = Number(tt.runIndex ?? data.runIndex ?? 1);
    if (state.runIndex !== prevRunIndex && (!data.convId || data.convId === state.activeConvId)) {
      state.inspectorItem = null;
      state.selectedProposalOption = null;
    }
    state.roleCaps = tt.roleCaps || {};
    state.triageDecision = tt.triageDecision || data.triageDecision || null;
    state.closureReceipt = data.closureReceipt || tt.closureReceipt || null;

    if (Array.isArray(data.agents)) state.agents = data.agents;
    if (Array.isArray(data.messages)) state.messages = data.messages;
    if (Array.isArray(data.interactions)) state.interactions = data.interactions;
    if (Array.isArray(data.findings)) state.findings = data.findings;
    if (Array.isArray(data.fileLocks)) state.fileLocks = data.fileLocks;
    if (Array.isArray(data.subtasks)) state.subtasks = data.subtasks;
    if (data.originCounts && typeof data.originCounts === 'object') state.originCounts = data.originCounts;
    if (data.roleUsage && typeof data.roleUsage === 'object') state.roleUsage = data.roleUsage;
    if (data.telemetry && typeof data.telemetry === 'object') state.telemetry = data.telemetry;
    if ('proposal' in data) state.proposal = data.proposal;
    if ('review' in data) state.review = data.review;
    if (Array.isArray(data.conversationsList)) state.conversations = data.conversationsList;

    const statusUpper = String(tt.status || state.status || '').toUpperCase();
    state.isClosed = Boolean(data.isClosed || tt.isClosed || statusUpper === 'COMPLETED' || statusUpper === 'DONE' || statusUpper === 'CLOSED');

    const syncSeq = Number(data.sync?.seq || 0);
    if (syncSeq > state.lastSeenSeq) state.lastSeenSeq = syncSeq;
    if (data.sync?.generation) state.wsGeneration = data.sync.generation;

    if (state.replayLive) {
      state.replaySeq = getMaxRecordedSeq();
    }

    if (!snapChanged && dataRevision > 0 && state.hasSession === prevHasSession && typeof renderHeaderAndVisibility === 'function') {
      renderHeaderAndVisibility();
      return;
    }
    renderAll();
  }

  function getMaxRecordedSeq() {
    let m = 0;
    for (const msg of state.messages) {
      const s = Number(msg.seq || 0);
      if (s > m) m = s;
    }
    for (const ev of state.interactions) {
      const s = Number(ev.seq || 0);
      if (s > m) m = s;
    }
    return m;
  }

  function getSortedFindings() {
    return [...state.findings].sort((a, b) => {
      const ra = SEVERITY_RANK[String(a.severity || 'MEDIUM').toUpperCase()] ?? 2;
      const rb = SEVERITY_RANK[String(b.severity || 'MEDIUM').toUpperCase()] ?? 2;
      if (ra !== rb) return ra - rb;
      const ta = Number(a.createdAt || a.events?.[0] || 0);
      const tb = Number(b.createdAt || b.events?.[0] || 0);
      if (ta !== tb) return ta - tb;
      return String(a.id || '').localeCompare(String(b.id || ''));
    });
  }

  function openInspector(item) {
    state.inspectorItem = item;
    const panel = $('#case-inspector');
    if (panel) panel.classList.toggle('is-open', Boolean(item));
    signatures.inspector = '';
    renderInspector();
    renderFlow();
    if (state.activeTab === 'map') renderMap();
  }

  function closeInspector() {
    state.inspectorItem = null;
    const panel = $('#case-inspector');
    if (panel) panel.classList.remove('is-open');
    signatures.inspector = '';
    renderInspector();
    renderFlow();
    if (state.activeTab === 'map') renderMap();
  }

  let lastFocusedBeforeSettings = null;
  function toggleSettingsSheet(open) {
    const nextOpen = Boolean(open);
    if (nextOpen && !state.settingsOpen) {
      lastFocusedBeforeSettings = document.activeElement instanceof HTMLElement ? document.activeElement : null;
    }
    state.settingsOpen = nextOpen;
    if (!nextOpen) state.pendingResetCase = false;
    const sheet = $('#settings-sheet');
    if (sheet) sheet.classList.toggle('hidden', !state.settingsOpen);
    if (state.settingsOpen) {
      syncSettingsInputs();
      renderRawInspector();
      const firstFocusable = sheet?.querySelector('button:not([disabled]), input:not([disabled]), select:not([disabled]), textarea:not([disabled]), [href], [tabindex]:not([tabindex="-1"])');
      if (firstFocusable instanceof HTMLElement) firstFocusable.focus();
    } else if (lastFocusedBeforeSettings && lastFocusedBeforeSettings.isConnected) {
      lastFocusedBeforeSettings.focus();
      lastFocusedBeforeSettings = null;
    }
  }

  function renderHeaderAndVisibility() {
    const titleEl = $('#header-case-title');
    const subEl = $('#header-project-subtitle');
    const pickerWrap = $('#header-session-picker');
    const emptyEl = $('#empty-session-screen');
    const shellEl = $('#active-workspace-shell');

    const openFindingsCount = state.findings.filter((f) => ACTIVE_FINDING_STATES.has(f.state)).length;
    if (titleEl) {
      titleEl.textContent = state.hasSession ? (state.project || tKey('app.untitled')) : tKey('app.brand');
    }
    if (subEl) {
      subEl.classList.toggle('hidden', !state.hasSession);
      if (state.hasSession) {
        const caseLabel = state.isClosed ? tKey('header.caseClosed') : tKey('header.caseOpen');
        const runTag = state.runIndex > 1 ? ` · ${tKey('header.runBadge')} #${num(state.runIndex)}` : '';
        subEl.textContent = `${caseLabel}${runTag} · ${num(openFindingsCount)} ${tKey('header.openFindings')} · ${tKey('header.round')} ${num(state.round)}/${num(state.maxRounds)}`;
      }
    }
    if (pickerWrap) pickerWrap.classList.toggle('hidden', !state.hasSession && state.conversations.length === 0);

    if (emptyEl) emptyEl.classList.toggle('hidden', state.hasSession);
    if (shellEl) shellEl.classList.toggle('hidden', !state.hasSession);

    const devMeta = $('#empty-dev-meta');
    if (devMeta) devMeta.classList.toggle('hidden', !state.devMode);
    const convBadge = $('#empty-conv-badge');
    if (convBadge) convBadge.textContent = state.activeConvId || '—';

    const emptySessionsEl = $('#empty-active-sessions');
    if (emptySessionsEl) {
      const choices = state.conversations.filter((c) => c && c.id && c.id !== 'default').slice(0, 6);
      const showChoices = !state.hasSession && choices.length > 0;
      emptySessionsEl.classList.toggle('hidden', !showChoices);
      if (showChoices) {
        const eSig = choices.map((c) => `${c.id}:${c.project || ''}:${c.isClosed ? 1 : 0}:${c.runIndex || 1}`).join('|') + `::${state.language}`;
        if (emptySessionsEl.dataset.sig !== eSig) {
          emptySessionsEl.dataset.sig = eSig;
          emptySessionsEl.innerHTML = `<div class="empty-sessions-title">${esc(tKey('empty.activeSessionsTitle'))}</div>`
            + choices.map((c) => {
              const title = c.project && c.project !== 'مکالمه جاری' ? c.project : tKey('header.currentSession');
              const runTag = Number(c.runIndex || 1) > 1 ? ` #${num(c.runIndex)}` : '';
              const statusText = c.isClosed ? tKey('header.caseClosed') : tKey('header.caseOpen');
              return `<button type="button" class="empty-session-item" data-switch-conv="${esc(c.id)}">
                <span class="empty-session-item-name">${esc(title)}${esc(runTag)}</span>
                <span class="empty-session-item-meta">${esc(statusText)}</span>
              </button>`;
            }).join('');
        }
      }
    }

    const dot = $('#ws-status-dot');
    const lbl = $('#ws-status-label');
    if (dot && lbl) {
      dot.classList.toggle('is-online', state.connected && !state.isClosed);
      dot.classList.toggle('is-closed', state.isClosed);
      lbl.textContent = state.isClosed ? tKey('app.closed') : state.connected ? tKey('app.live') : tKey('app.offline');
    }

    const sel = $('#conv-switcher');
    if (sel) {
      const currentCid = state.activeConvId || 'default';
      const hasCurrent = state.conversations.some((c) => c.id === currentCid);
      const baseList = hasCurrent
        ? state.conversations
        : [{ id: currentCid, project: state.project || tKey('header.currentSession'), isClosed: state.isClosed, runIndex: state.runIndex || 1 }, ...state.conversations];
      const q = state.convSearchQuery.trim().toLowerCase();
      const filtered = q
        ? baseList.filter((c) => `${c.project || ''} ${c.id}`.toLowerCase().includes(q) || c.id === currentCid)
        : baseList;
      const sig = filtered.map((c) => `${c.id}:${c.project || ''}:${c.isClosed ? 1 : 0}:${c.runIndex || 1}:${c.isArchivedRun ? 1 : 0}`).join('|') + '::' + currentCid + '::' + state.language;
      if (signatures.header !== sig) {
        signatures.header = sig;
        sel.innerHTML = filtered.map((c) => {
          const base = c.project && c.project !== 'مکالمه جاری' ? c.project : tKey('header.currentSession');
          const statusSymbol = c.isClosed ? '○' : '●';
          const runIdx = Number(c.runIndex || 1);
          const runSuffix = (runIdx > 1 || c.isArchivedRun) ? ` #${num(runIdx)}` : '';
          const label = `${statusSymbol} ${base}${runSuffix}`;
          return `<option value="${esc(c.id)}"${c.id === currentCid ? ' selected' : ''}>${esc(label)}</option>`;
        }).join('');
      }
    }

    const runBar = $('#run-history-bar');
    const runPills = $('#run-history-pills');
    if (runBar && runPills) {
      const currentCid = state.activeConvId || state.hostConvId || 'default';
      const baseCid = currentCid.split('--run-')[0];
      const relatedRuns = state.conversations.filter((c) => (
        c.parentConvId === baseCid || c.id === baseCid || String(c.id || '').startsWith(`${baseCid}--run-`)
      ));
      if (!relatedRuns.some((c) => c.id === currentCid) && state.hasSession) {
        relatedRuns.push({
          id: currentCid,
          runIndex: state.runIndex || 1,
          isClosed: state.isClosed,
          isArchivedRun: currentCid.includes('--run-'),
          project: state.project,
        });
      }
      relatedRuns.sort((a, b) => Number(a.runIndex || 1) - Number(b.runIndex || 1));
      const showBar = state.hasSession && relatedRuns.length > 0;
      runBar.classList.toggle('hidden', !showBar);
      if (showBar) {
        const rSig = relatedRuns.map((c) => `${c.id}:${c.runIndex || 1}:${c.isClosed ? 1 : 0}`).join('|') + `::${currentCid}::${state.language}`;
        if (runPills.dataset.sig !== rSig) {
          runPills.dataset.sig = rSig;
          runPills.innerHTML = relatedRuns.map((c) => {
            const idx = Number(c.runIndex || 1);
            const active = c.id === currentCid;
            const symbol = c.isClosed ? '○' : '●';
            return `<button type="button" class="chip-btn run-pill${active ? ' is-active' : ''}" data-run-conv="${esc(c.id)}" aria-pressed="${active ? 'true' : 'false'}" title="${esc(c.project || baseCid)}">${symbol} #${num(idx)}</button>`;
          }).join('');
        }
      }
    }
  }

  function isWorkingAgentStatus(st) {
    return ['ACTIVE', 'WORKING', 'IN_PROGRESS'].includes(String(st || '').toUpperCase());
  }

  function renderNowStrip() {
    const triageEl = $('#triage-badge');
    if (triageEl) {
      if (state.triageDecision?.chosen) {
        triageEl.classList.remove('hidden');
        const label = state.triageDecision.chosen === 'solo' ? tKey('flow.now.triageSolo') : tKey('flow.now.triageThinkTank');
        const ttReasons = Array.isArray(state.triageDecision.thinktankReasons) ? state.triageDecision.thinktankReasons : [];
        const soloReasons = Array.isArray(state.triageDecision.soloReasons) ? state.triageDecision.soloReasons : [];
        const reasons = (state.triageDecision.chosen === 'solo' ? soloReasons : ttReasons).filter(Boolean);
        const allReasons = [...ttReasons, ...soloReasons].filter(Boolean);
        triageEl.textContent = `${tKey('flow.now.triageLabel')}: ${label}${reasons.length ? ` (${num(reasons.length)})` : ''}`;
        if (allReasons.length) {
          triageEl.setAttribute('title', `${tKey('flow.now.triageReasons')}: ${allReasons.join(' · ')}`);
        } else {
          triageEl.removeAttribute('title');
        }
      } else {
        triageEl.classList.add('hidden');
        triageEl.removeAttribute('title');
      }
    }

    const nowList = $('#now-activities');
    if (nowList) {
      const items = [];
      for (const f of getSortedFindings()) {
        if (!ACTIVE_FINDING_STATES.has(f.state)) continue;
        const actor = f.state === 'InReview' ? 'code-reviewer' : f.state === 'Testing' ? 'qa-reviewer' : (f.owner || 'team-manager');
        items.push({ role: actor, text: `${roleLabel(actor)} · ${findingStateLabel(f.state)} `, ref: f.id });
      }
      for (const ag of state.agents) {
        if (isWorkingAgentStatus(ag.status) && (ag.currentTask || ag.task)) {
          items.push({ role: ag.id, text: `${roleLabel(ag.id)} · ${ag.currentTask || ag.task}`, ref: '' });
        }
      }
      if (!items.length) {
        const lastMsg = state.messages[state.messages.length - 1];
        const tail = lastMsg?.timestamp ? ` · ${tKey('flow.now.lastEvent')} ${lastMsg.timestamp}` : '';
        nowList.innerHTML = `<p class="empty-note">${esc(tKey('flow.now.idle') + tail)}</p>`;
      } else {
        const shown = items.slice(0, 3);
        const extra = items.length - shown.length;
        nowList.innerHTML = shown.map((it) => {
          const canonRole = normalizeRoleId(it.role);
          const ag = state.agents.find((a) => normalizeRoleId(a.id) === canonRole);
          const isRealSub = Boolean(ag?.verifiedSubagent || ag?.subagentConvId);
          const subSlice = state.devMode && ag?.subagentConvId ? ` <code class="mono-id">${esc(String(ag.subagentConvId).slice(0, 8))}</code>` : '';
          const realBadge = isRealSub ? ` <span class="verified-subagent-badge" title="${esc(tKey('team.verifiedSubagent'))}">${SVG_ICONS.originSubagent}<span>${esc(tKey('team.verifiedSubagent'))}</span>${subSlice}</span>` : '';
          return `
          <div class="now-item">
            ${renderRoleMonogram(it.role, 22)}
            <span>${esc(it.text)}${it.ref ? ` <span class="mono-id">${esc(it.ref)}</span>` : ''}</span>
            ${realBadge}
          </div>`;
        }).join('') + (extra > 0 ? `<p class="meta-note">+${num(extra)} ${esc(tKey('flow.now.moreActivity'))}</p>` : '');
      }
    }

    const awaitingBox = $('#awaiting-user-box');
    const decisionBox = $('#decision-box');
    const pendingProposal = state.proposal && state.proposal.status !== 'COMPLETED';
    const awaitingHumanReview = Boolean(state.review && state.review.status === 'WAITING_FOR_HUMAN' && state.review.humanRequired && !state.isClosed);
    const awaitingSomething = Boolean(pendingProposal || awaitingHumanReview);
    if (awaitingBox) {
      awaitingBox.classList.toggle('hidden', !awaitingSomething);
      if (awaitingSomething) {
        const awaitingTitle = awaitingHumanReview
          ? `${tKey('flow.decision.reviewTitle')}`
          : (state.proposal?.title || '');
        awaitingBox.innerHTML = `
          <span class="role-pair">${SVG_ICONS.flag} <span>${esc(tKey('flow.now.awaitingUser'))}: ${esc(awaitingTitle)}</span></span>
          <button type="button" id="btn-jump-decision" class="tt-btn tt-compact-btn">${esc(tKey('flow.now.reviewBtn'))}</button>`;
      }
    }

    if (decisionBox) {
      const html = createDecisionHtml(state.proposal, state.review);
      decisionBox.classList.toggle('hidden', !html);
      decisionBox.innerHTML = html;
    }
  }

  function createDecisionHtml(proposal, review) {
    if (!proposal && !review) return '';
    const awaitingHumanReview = Boolean(review && review.status === 'WAITING_FOR_HUMAN' && review.humanRequired && !state.isClosed);
    const isCompleted = proposal && proposal.status === 'COMPLETED';
    const title = awaitingHumanReview
      ? tKey('flow.decision.reviewTitle')
      : (proposal ? proposal.title : (review?.title || ''));
    const summary = awaitingHumanReview
      ? [review?.managerSummary, review?.mainSummary].filter(Boolean).join(' · ')
      : (proposal ? proposal.summary : (review?.managerSummary || ''));
    const options = Array.isArray(proposal?.decisionOptions) ? proposal.decisionOptions : [];
    const votes = Array.isArray(proposal?.votes) ? proposal.votes : [];
    const chosenOptId = state.selectedProposalOption || proposal?.userDecision?.optionId || proposal?.selectedOptionId || null;

    const optionsHtml = options.length
      ? `<div class="proposal-options">${options.map((opt) => {
          const optId = String(opt.id || opt.label || '');
          const selected = chosenOptId === optId;
          return `<button type="button" class="tt-btn tt-compact-btn ${selected ? 'tt-btn-primary' : 'tt-btn-ghost'} proposal-opt-btn" data-opt-id="${esc(optId)}">${esc(opt.label || optId)}</button>`;
        }).join('')}</div>`
      : '';

    const revisionDraftHtml = state.revisionDraftOpen
      ? `<div id="proposal-revision-wrap" class="composer-row">
          <input id="proposal-revision-note" type="text" class="tt-input" placeholder="${esc(tKey('flow.decision.revisionPlaceholder'))}" />
          <button type="button" class="tt-btn tt-compact-btn tt-btn-primary proposal-act-btn" data-act="request_revision">${esc(tKey('flow.decision.sendRevision'))}</button>
          <button type="button" class="tt-btn tt-compact-btn tt-btn-ghost proposal-act-btn" data-act="cancel_revision">${esc(tKey('flow.decision.cancel'))}</button>
        </div>`
      : '';

    const actionsHtml = proposal && !isCompleted && !state.isClosed
      ? `<div class="proposal-actions">
          <button type="button" class="tt-btn tt-compact-btn tt-btn-verified proposal-act-btn" data-act="approve">${esc(tKey('flow.decision.approve'))}</button>
          <button type="button" class="tt-btn tt-compact-btn tt-btn-ghost proposal-act-btn" data-act="open_revision">${esc(tKey('flow.decision.revise'))}</button>
        </div>${revisionDraftHtml}`
      : '';

    const humanReviewHtml = awaitingHumanReview
      ? `<div id="human-review-decision-wrap" class="proposal-actions">
          <input id="review-decision-note" type="text" class="tt-input" placeholder="${esc(tKey('flow.decision.notePlaceholder'))}" />
          <button type="button" class="tt-btn tt-compact-btn tt-btn-verified review-dec-btn" data-decision="continue">${esc(tKey('flow.decision.continueBtn'))}</button>
          <button type="button" class="tt-btn tt-compact-btn tt-btn-open review-dec-btn" data-decision="stop">${esc(tKey('flow.decision.stopBtn'))}</button>
        </div>`
      : '';

    const votesHtml = votes.length
      ? `<div id="council-consensus-box" class="council-grid">${votes.map((v) => `
          <div class="council-vote-row">
            <strong>${esc(roleLabel(v.voterId || v.voterName || v.voter))}</strong>
            <span class="meta-note"> · ${esc(translateStatus(v.stance || 'REVIEW'))} · ${num(v.confidence || 0)}${state.language === 'en' ? '%' : '٪'}</span>
            ${v.comment ? `<p class="empty-note">${esc(v.comment)}</p>` : ''}
          </div>`).join('')}</div>`
      : '';

    return `
      <div class="section-head">
        <strong>${esc(title)}</strong>
        <span class="status-pill ${isCompleted ? 'state-verified' : 'state-working'}">${esc(isCompleted ? tKey('flow.decision.verifiedClosed') : translateStatus(awaitingHumanReview ? review.status : (proposal?.status || 'ACTIVE')))}</span>
      </div>
      ${summary ? `<p class="empty-note">${esc(summary)}</p>` : ''}
      ${optionsHtml}${actionsHtml}${humanReviewHtml}${votesHtml}`;
  }

  function renderProgressBars() {
    const fBar = $('#findings-progress-bar');
    if (fBar) {
      const fStates = [
        { state: 'Open', key: 'flow.bars.open', swatch: 'swatch-open' },
        { state: 'Fixing', key: 'flow.bars.fixing', swatch: 'swatch-working' },
        { state: 'InReview', key: 'flow.bars.inReview', swatch: 'swatch-review' },
        { state: 'Testing', key: 'flow.bars.testing', swatch: 'swatch-working' },
        { state: 'Verified', key: 'flow.bars.verified', swatch: 'swatch-verified' },
        { state: 'WontFix', key: 'flow.bars.wontfix', swatch: 'swatch-muted' },
      ];
      const counts = {};
      for (const f of state.findings) {
        const key = f.state === 'Closed' ? 'Verified' : (f.state || 'Open');
        counts[key] = (counts[key] || 0) + 1;
      }
      fBar.innerHTML = fStates.filter((s) => s.state !== 'WontFix' || counts[s.state] > 0).map((s) => {
        const cnt = counts[s.state] || 0;
        const active = state.findingFilter === s.state;
        return `<button type="button" class="segment-btn${active ? ' is-active' : ''}" data-finding-state="${esc(s.state)}" aria-pressed="${active ? 'true' : 'false'}">
          <span class="segment-swatch ${s.swatch}" aria-hidden="true"></span>
          <span>${num(cnt)} ${esc(tKey(s.key))}</span>
        </button>`;
      }).join('');
    }

    const wBar = $('#wbs-progress-bar');
    if (wBar) {
      const wStates = [
        { state: 'ASSIGNED', key: 'flow.bars.assigned', swatch: 'swatch-muted' },
        { state: 'IN_PROGRESS', key: 'flow.bars.inProgress', swatch: 'swatch-working' },
        { state: 'IN_REVIEW', key: 'flow.bars.inReview', swatch: 'swatch-review' },
        { state: 'COMPLETED', key: 'flow.bars.completed', swatch: 'swatch-verified' },
      ];
      const counts = {};
      for (const st of state.subtasks) {
        const key = String(st.status || 'ASSIGNED').toUpperCase();
        counts[key] = (counts[key] || 0) + 1;
      }
      wBar.innerHTML = wStates.map((s) => {
        const cnt = counts[s.state] || 0;
        const active = state.wbsFilter === s.state;
        return `<button type="button" class="segment-btn${active ? ' is-active' : ''}" data-wbs-state="${esc(s.state)}" aria-pressed="${active ? 'true' : 'false'}">
          <span class="segment-swatch ${s.swatch}" aria-hidden="true"></span>
          <span>${num(cnt)} ${esc(tKey(s.key))}</span>
        </button>`;
      }).join('');
    }
  }

  function renderLifecycleRail(finding) {
    const fState = finding.state || 'Open';
    const currentIdx = Math.max(0, LIFECYCLE_STAGES.findIndex((st) => st.states.includes(fState)));
    const stageName = findingStateLabel(fState);
    const returnsText = finding.returnCount > 0 ? `، ${num(finding.returnCount)} ${tKey('flow.findings.returns')}` : '';
    const aria = `${finding.id}: ${num(currentIdx + 1)}/5 ${stageName}${returnsText}`;

    return `<div class="lifecycle-rail" role="img" aria-label="${esc(aria)}">
      ${LIFECYCLE_STAGES.map((st, idx) => {
        const isDone = idx < currentIdx || (idx === 4 && (fState === 'Verified' || fState === 'Closed'));
        const isCurrent = idx === currentIdx && !isDone;
        return `<div class="rail-node ${isDone ? 'is-done' : ''} ${isCurrent ? `is-current tone-${st.tone}` : ''}">
          <span class="rail-dot" aria-hidden="true">${isDone ? SVG_ICONS.check : ''}</span>
          <span>${esc(tKey(st.labelKey))}</span>
        </div>`;
      }).join('')}
    </div>`;
  }

  function renderFindingCardHtml(f) {
    const tone = stateTone(f.state);
    const selected = state.inspectorItem?.type === 'finding' && state.inspectorItem.id === f.id;
    const sev = String(f.severity || 'MEDIUM').toUpperCase();
    const sevLabel = tKey(`flow.findings.sev.${sev}`) || sev;
    const evCount = Array.isArray(f.events) ? f.events.length : 0;
    return `<article class="finding-card${selected ? ' is-selected' : ''}" data-finding-id="${esc(f.id)}" tabindex="0">
      <div class="finding-card-head">
        <div class="finding-head-left">
          <span class="mono-id">${esc(f.id)}</span>
          <span class="finding-severity sev-${esc(sev)}">${esc(sevLabel)}</span>
          ${f.returnCount > 0 ? `<span class="meta-note mono-id">↺${num(f.returnCount)}</span>` : ''}
        </div>
        <div class="finding-head-right">
          <button type="button" class="finding-pin-btn" data-finding-id="${esc(f.id)}" aria-pressed="${f.markedImportant ? 'true' : 'false'}" title="${esc(tKey('flow.findings.pinImportant'))}" aria-label="${esc(tKey('flow.findings.pinImportant'))}">
            ${SVG_ICONS.pin}
          </button>
          <span class="status-pill state-${tone}">${f.state === 'Verified' || f.state === 'Closed' ? SVG_ICONS.check : ''}<span>${esc(findingStateLabel(f.state))}</span></span>
        </div>
      </div>
      <p class="finding-title">${esc(f.title || f.id)}</p>
      <div class="finding-meta">
        <span class="role-pair">${renderRoleMonogram(f.raisedBy || 'council-critic', 22)} ${SVG_ICONS.arrow} ${renderRoleMonogram(f.owner || 'ui-frontend-designer', 22)}</span>
        <span>${num(evCount)} ${esc(tKey('flow.findings.eventsCount'))}</span>
        ${f.workItemId ? `<span class="mono-id">${esc(f.workItemId)}</span>` : ''}
      </div>
      ${renderLifecycleRail(f)}
    </article>`;
  }

  function renderFindingsSection() {
    const allSorted = getSortedFindings();
    const active = allSorted.filter((f) => ACTIVE_FINDING_STATES.has(f.state));
    const verified = allSorted.filter((f) => !ACTIVE_FINDING_STATES.has(f.state));

    const filterBtn = $('#btn-clear-finding-filter');
    if (filterBtn) filterBtn.classList.toggle('hidden', !state.findingFilter);

    const totalEl = $('#findings-total-count');
    if (totalEl) totalEl.textContent = num(allSorted.length);

    let shownActive = active;
    let shownVerified = verified;
    if (state.findingFilter) {
      if (state.findingFilter === 'Verified' || state.findingFilter === 'WontFix') {
        shownActive = [];
        shownVerified = verified.filter((f) => (state.findingFilter === 'Verified' ? (f.state === 'Verified' || f.state === 'Closed') : f.state === 'WontFix'));
      } else {
        shownActive = active.filter((f) => f.state === state.findingFilter);
      }
    }

    const listEl = $('#findings-list');
    if (listEl) {
      if (!allSorted.length) {
        listEl.innerHTML = `<p class="empty-note">${esc(tKey('flow.findings.empty'))}</p>`;
      } else if (!shownActive.length && state.findingFilter !== 'Verified' && state.findingFilter !== 'WontFix') {
        listEl.innerHTML = `<p class="empty-note">${esc(tKey('flow.findings.emptyFiltered'))}</p>`;
      } else {
        listEl.innerHTML = shownActive.map(renderFindingCardHtml).join('');
      }
    }

    const drawer = $('#verified-findings-drawer');
    const vCount = $('#verified-findings-count');
    const vList = $('#verified-findings-list');
    if (drawer && vCount && vList) {
      drawer.classList.toggle('hidden', shownVerified.length === 0);
      vCount.textContent = num(shownVerified.length);
      if (state.findingFilter === 'Verified' || state.findingFilter === 'WontFix') drawer.open = true;
      vList.innerHTML = shownVerified.map(renderFindingCardHtml).join('');
    }
  }

  function renderWbsSection() {
    const clearBtn = $('#btn-clear-wbs-filter');
    if (clearBtn) clearBtn.classList.toggle('hidden', !state.wbsFilter);

    const totalEl = $('#wbs-total-count');
    if (totalEl) totalEl.textContent = num(state.subtasks.length);

    const listEl = $('#wbs-list');
    if (!listEl) return;

    const rows = state.wbsFilter
      ? state.subtasks.filter((s) => String(s.status || 'ASSIGNED').toUpperCase() === state.wbsFilter)
      : state.subtasks;

    if (!rows.length) {
      listEl.innerHTML = `<p class="empty-note">${esc(tKey('flow.wbs.empty'))}</p>`;
      return;
    }

    preserveDetailsOpen(listEl, () => {
      listEl.innerHTML = rows.map((st) => {
        const openCount = state.findings.filter((f) => f.workItemId === st.id && ACTIVE_FINDING_STATES.has(f.state)).length;
        const locked = Array.isArray(st.lockedFiles) ? st.lockedFiles : [];
        const tone = stateTone(st.status);
        return `<div class="wbs-row" data-work-item-id="${esc(st.id)}">
          <div class="wbs-row-top">
            <div class="role-pair">
              ${renderRoleMonogram(st.assignee, 22)}
              <span class="wbs-row-title">${esc(st.title)}</span>
            </div>
            <span class="status-pill state-${tone}">${esc(translateStatus(st.status))}</span>
          </div>
          <div class="wbs-row-meta">
            <span>${esc(roleLabel(st.assignee))}</span>
            ${openCount > 0 ? `<span>· ${num(openCount)} ${esc(tKey('flow.wbs.openFindings'))}</span>` : ''}
          </div>
          ${st.acceptanceCriteria ? `<p class="wbs-acceptance">${esc(tKey('flow.wbs.acceptance'))} ${esc(st.acceptanceCriteria)}</p>` : ''}
          ${locked.length ? `<details class="locked-files-details" data-details-key="wbs-locks-${esc(st.id)}">
            <summary>${esc(tKey('flow.wbs.lockedFiles'))} (<span class="mono-id">${num(locked.length)}</span>)</summary>
            <ul class="locked-files-list">${locked.map((p) => `<li class="mono-id">${esc(p)}</li>`).join('')}</ul>
          </details>` : ''}
        </div>`;
      }).join('');
    });
  }

  function matchesLedgerChannel(m, channel) {
    if (channel === 'ALL') return true;
    const act = String(m.actionType || m.action || 'MESSAGE').toUpperCase();
    const origin = String(m.origin || '').toLowerCase();
    if (channel === 'FINDINGS') return Boolean(m.findingId) || ['RETURN_DEFECT', 'WORKER_FIX', 'CRITIQUE', 'INTERROGATE'].includes(act);
    if (channel === 'QA') return ['QA_DISPATCH', 'QA_REPORT', 'REVIEW_QUERY'].includes(act) || String(m.channel || '').toUpperCase() === 'QA';
    if (channel === 'SYNC') return act === 'PEER_SYNC' || String(m.channel || '').toUpperCase() === 'SYNC';
    if (channel === 'TASKS') return act === 'DELEGATE' || Boolean(m.workItemId) || String(m.channel || '').toUpperCase() === 'SUBAGENTS';
    if (channel === 'USER') return origin === 'user' || String(m.senderRole || '').toLowerCase() === 'user';
    return true;
  }

  function renderEventLedger() {
    for (const btn of $$('#event-ledger-section .channel-bar .chip-btn')) {
      btn.classList.toggle('is-active', btn.dataset.channel === state.boardChannel);
    }
    const feed = $('#messages-feed');
    if (!feed) return;
    const q = state.boardSearchQuery.trim().toLowerCase();
    const filtered = [...state.messages].reverse().filter((m) => {
      if (!matchesLedgerChannel(m, state.boardChannel)) return false;
      if (!q) return true;
      return (`#${m.seq} ${m.findingId || ''} ${m.content || ''} ${m.senderRole || ''} ${m.recipientRole || ''}`).toLowerCase().includes(q);
    });
    if (!filtered.length) {
      feed.innerHTML = `<p class="empty-note">${esc(tKey('flow.ledger.empty'))}</p>`;
      return;
    }
    feed.innerHTML = filtered.map((m) => {
      const act = String(m.actionType || m.action || 'MESSAGE').toUpperCase();
      const catMeta = requestCategoryMeta(m);
      const orig = originIconAndLabel(m.origin || (m.senderRole === 'user' ? 'user' : 'main-proxy'));
      const selected = state.inspectorItem?.type === 'event' && Number(state.inspectorItem.seq) === Number(m.seq);
      const summary = String(m.content || '').replace(/\s+/g, ' ').trim();
      const fromRole = m.senderRole || m.senderCode || 'main_agent';
      const toRole = m.recipientRole || m.recipientCode || '';
      return `<div class="ledger-row${selected ? ' is-selected' : ''}" data-seq="${esc(m.seq)}" data-req-category="${esc(catMeta.category)}" tabindex="0">
        <div class="ledger-row-main">
          <span class="mono-id">#${esc(m.seq)}</span>
          <span class="role-pair">${renderRoleMonogram(fromRole, 20)}${toRole && toRole.toUpperCase() !== 'ALL' ? `${SVG_ICONS.arrow}${renderRoleMonogram(toRole, 20)}` : ''}</span>
          <span class="req-type-chip" data-req-category="${esc(catMeta.category)}" title="${esc(actionLabel(act))}">${actionIcon(act)} <span>${esc(requestTypeLabel(m))}</span></span>
          ${m.findingId ? `<span class="mono-id finding-ref-tag">${esc(m.findingId)}</span>` : ''}
          <span class="ledger-row-summary">${esc(summary)}</span>
        </div>
        <div class="ledger-row-meta">
          <span class="origin-badge" title="${esc(orig.label)}" aria-label="${esc(orig.label)}">${orig.icon}</span>
          <span class="mono-id">${esc(m.timestamp || '')}</span>
        </div>
      </div>`;
    }).join('');
  }

  function renderClosureReceipt() {
    const el = $('#closure-receipt');
    if (!el) return;
    if (!state.isClosed) {
      el.classList.add('hidden');
      return;
    }
    el.classList.remove('hidden');

    const r = state.closureReceipt || {};
    const doneTasks = r.subtasksCompleted ?? state.subtasks.filter((s) => s.status === 'COMPLETED').length;
    const totalTasks = r.subtasksTotal ?? state.subtasks.length;
    const fVerified = r.findingsVerified ?? state.findings.filter((f) => ['Verified', 'Closed'].includes(f.state)).length;
    const fOpen = r.findingsOpen ?? state.findings.filter((f) => ACTIVE_FINDING_STATES.has(f.state)).length;
    const fWontFix = r.findingsWontFix ?? state.findings.filter((f) => f.state === 'WontFix').length;
    const qaRuns = r.qaRunsCount ?? state.findings.reduce((acc, f) => acc + (f.evidence?.length || 0), 0);
    const qaStatus = qaRuns === 0 ? tKey('receipt.qaNone') : (r.qaAllExitZero !== false ? tKey('receipt.qaAllZero') : tKey('receipt.qaHasFail'));
    const origins = r.originCounts || state.originCounts || {};
    const totalEvents = r.totalEvents ?? state.messages.length;
    const wontFixItems = state.findings.filter((f) => f.state === 'WontFix');

    el.innerHTML = `
      <div class="receipt-head">
        <span class="status-pill state-verified">${SVG_ICONS.check}<span>${esc(tKey('receipt.title'))}</span></span>
        <strong>${esc(r.project || state.project || tKey('app.untitled'))}</strong>
        <span class="meta-note mono-id">${esc(r.closedAt || '')} · ${num(totalEvents)} ${esc(tKey('receipt.events'))}</span>
      </div>
      <div class="receipt-rows">
        <div class="receipt-row">
          <span class="receipt-row-label">${esc(tKey('receipt.tasksLabel'))}</span>
          <span>${esc(tKey('receipt.tasksFormat', { done: num(doneTasks), total: num(totalTasks) }))}</span>
        </div>
        <div class="receipt-row">
          <span class="receipt-row-label">${esc(tKey('receipt.findingsLabel'))}</span>
          <span>${esc(tKey('receipt.findingsFormat', { verified: num(fVerified), open: num(fOpen), wontfix: num(fWontFix) }))}</span>
        </div>
        <div class="receipt-row">
          <span class="receipt-row-label">${esc(tKey('receipt.qaLabel'))}</span>
          <span>${esc(tKey('receipt.qaFormat', { runs: num(qaRuns), status: qaStatus }))}</span>
        </div>
        <div class="receipt-row">
          <span class="receipt-row-label">${esc(tKey('receipt.originsLabel'))}</span>
          <span>${esc(tKey('receipt.originsFormat', { subagent: num(origins.subagent || 0), proxy: num(origins['main-proxy'] || 0), user: num(origins.user || 0) }))}</span>
        </div>
        ${r.forceCloseReason ? `<div class="receipt-row"><span class="receipt-row-label">${esc(tKey('receipt.forceReason'))}</span><span>${esc(r.forceCloseReason)}</span></div>` : ''}
      </div>
      ${wontFixItems.length ? `<div><strong class="meta-note">${esc(tKey('receipt.wontFixTitle'))}</strong><ul>${wontFixItems.map((f) => `<li><span class="mono-id">${esc(f.id)}</span> — ${esc(f.wontFixReason || f.title)}</li>`).join('')}</ul></div>` : ''}
      <div class="receipt-actions">
        <button type="button" id="btn-receipt-replay" class="tt-btn tt-btn-primary">${esc(tKey('receipt.replayBtn'))}</button>
        <button type="button" id="btn-receipt-reopen-case" class="tt-btn">${esc(tKey('receipt.reopenCase'))}</button>
        <button type="button" id="btn-receipt-new-case" class="tt-btn">${esc(tKey('receipt.newCaseBtn'))}</button>
      </div>`;
  }

  function computeFlowSignature() {
    return [
      dataRevision,
      state.activeConvId || '',
      state.language,
      state.isClosed ? 1 : 0,
      state.devMode ? 1 : 0,
      state.runIndex || 1,
      state.findingFilter || '',
      state.wbsFilter || '',
      state.boardChannel,
      state.boardSearchQuery,
      state.selectedProposalOption || '',
      state.revisionDraftOpen ? 1 : 0,
      inspectorKey(),
    ].join('|');
  }

  function renderFlow() {
    if (!state.hasSession) return;
    const sig = computeFlowSignature();
    if (signatures.flow === sig) return;
    signatures.flow = sig;

    populateTargetSelect();

    const activeIds = ['#now-strip', '#process-bars-card', '#findings-section', '#wbs-section', '#event-ledger-section', '#user-composer-form'];
    for (const sel of activeIds) {
      const node = $(sel);
      if (node) node.classList.toggle('hidden', state.isClosed);
    }
    if (state.isClosed) {
      renderClosureReceipt();
      return;
    }
    renderClosureReceipt();
    renderNowStrip();
    renderProgressBars();
    renderFindingsSection();
    renderWbsSection();
    renderEventLedger();
  }

  function computeInspectorSignature() {
    const it = state.inspectorItem;
    const replaySuffix = it?.type === 'edge' ? `:${state.replayLive ? 'L' : state.replaySeq}` : '';
    return `${dataRevision}|${state.activeConvId || ''}|${state.language}|${inspectorKey()}${replaySuffix}`;
  }

  function renderInspector() {
    const body = $('#case-inspector-body');
    const title = $('#inspector-title');
    if (!body || !title) return;

    const sig = computeInspectorSignature();
    if (signatures.inspector === sig) return;
    signatures.inspector = sig;

    const item = state.inspectorItem;
    if (!item) {
      title.textContent = tKey('inspector.title');
      body.innerHTML = `<p class="empty-note">${esc(tKey('inspector.emptyHint'))}</p>`;
      return;
    }

    if (item.type === 'finding') {
      const f = state.findings.find((x) => x.id === item.id);
      if (!f) {
        title.textContent = tKey('inspector.title');
        body.innerHTML = `<p class="empty-note">${esc(tKey('inspector.emptyHint'))}</p>`;
        return;
      }
      title.innerHTML = `<span class="mono-id">${esc(f.id)}</span> · ${esc(findingStateLabel(f.state))}`;
      const threadMsgs = state.messages.filter((m) => (f.events || []).includes(m.seq) || m.findingId === f.id);
      const evidenceList = Array.isArray(f.evidence) ? f.evidence : [];

      body.innerHTML = `
        <div class="inspector-block">
          <strong>${esc(f.title || f.id)}</strong>
          ${f.reproSteps ? `<p class="meta-note"><strong>${esc(tKey('flow.findings.reproSteps'))}:</strong> ${esc(f.reproSteps)}</p>` : ''}
          ${f.wontFixReason ? `<p class="meta-note"><strong>${esc(tKey('flow.findings.wontFixReason'))}:</strong> ${esc(f.wontFixReason)}</p>` : ''}
        </div>
        <div class="inspector-block">
          <strong>${esc(tKey('inspector.threadHeading'))}</strong>
          ${threadMsgs.length ? threadMsgs.map((m) => {
            const orig = originIconAndLabel(m.origin || 'main-proxy');
            return `<div class="inspector-block">
              <div class="finding-meta">
                <span class="mono-id">#${esc(m.seq)}</span>
                ${renderRoleMonogram(m.senderRole || m.senderCode, 20)}
                <span>${esc(actionLabel(String(m.actionType || 'MESSAGE').toUpperCase()))}</span>
                <span class="origin-badge" title="${esc(orig.label)}">${orig.icon}</span>
              </div>
              <p>${esc(m.content || '')}</p>
            </div>`;
          }).join('') : `<p class="empty-note">${esc(tKey('flow.ledger.empty'))}</p>`}
        </div>
        <div class="inspector-block">
          <strong>${esc(tKey('inspector.evidenceHeading'))}</strong>
          ${evidenceList.length ? evidenceList.map((ev) => `
            <div class="inspector-block">
              <div class="finding-meta">
                <span class="mono-id">${esc(tKey('inspector.exitCode'))}: ${esc(ev.exitCode)}</span>
                <span class="mono-id">${esc(ev.runner || '')}</span>
              </div>
              ${ev.command ? `<code class="mono-code">${esc(ev.command)}</code>` : ''}
              ${ev.runnerReason ? `<p class="meta-note">${esc(tKey('inspector.runnerReason'))}: ${esc(ev.runnerReason)}</p>` : ''}
              ${ev.stdoutHash ? `<p class="meta-note mono-id">${esc(tKey('inspector.hash'))}: ${esc(String(ev.stdoutHash).slice(0, 16))}</p>` : ''}
              ${ev.excerpt ? `<pre class="evidence-pre mono-code">${esc(ev.excerpt)}</pre>` : ''}
            </div>`).join('') : `<p class="empty-note">${esc(tKey('flow.findings.noEvidence'))}</p>`}
        </div>`;
      return;
    }

    if (item.type === 'event') {
      const m = state.messages.find((x) => Number(x.seq) === Number(item.seq));
      const evRec = buildRecordedEvents().find((x) => Number(x.seq) === Number(item.seq));
      if (!m && !evRec) {
        title.textContent = tKey('inspector.title');
        body.innerHTML = `<p class="empty-note">${esc(tKey('inspector.emptyHint'))}</p>`;
        return;
      }
      const act = String(m?.actionType || m?.action || evRec?.action || 'MESSAGE').toUpperCase();
      const catMeta = requestCategoryMeta(m || evRec);
      const fromRole = m?.senderRole || m?.senderCode || evRec?.from || 'main_agent';
      const toRole = m?.recipientRole || m?.recipientCode || evRec?.to || '';
      const reqLabel = requestTypeLabel(m || evRec);
      const orig = originIconAndLabel(m?.origin || (fromRole === 'user' ? 'user' : 'main-proxy'));
      const fId = m?.findingId || evRec?.findingId || '';
      title.innerHTML = `<span class="mono-id">#${esc(item.seq)}</span> · ${esc(reqLabel)}`;
      const extras = [
        m?.thoughts ? { label: tKey('inspector.reasoning'), val: m.thoughts } : null,
        m?.critique ? { label: tKey('inspector.critique'), val: m.critique } : null,
        m?.question ? { label: tKey('inspector.question'), val: m.question } : null,
        m?.report ? { label: tKey('inspector.report'), val: m.report } : null,
      ].filter(Boolean);

      body.innerHTML = `
        <div class="inspector-block">
          <strong>${esc(tKey('inspector.participants'))}</strong>
          <div class="finding-meta">
            ${renderRoleMonogram(fromRole, 22)} <span>${esc(roleLabel(fromRole))}</span>
            ${toRole && String(toRole).toUpperCase() !== 'ALL' ? `${SVG_ICONS.arrow} ${renderRoleMonogram(toRole, 22)} <span>${esc(roleLabel(toRole))}</span>` : ''}
          </div>
          <div class="finding-meta" style="margin-top:8px;">
            <span class="req-type-chip" data-req-category="${esc(catMeta.category)}">${actionIcon(act)} <span>${esc(tKey('inspector.requestType'))}: ${esc(reqLabel)}</span></span>
            <span class="origin-badge">${orig.icon} <span>${esc(orig.label)}</span></span>
            ${fId ? `<span class="mono-id finding-ref-tag">${esc(fId)}</span>` : ''}
          </div>
        </div>
        <div class="inspector-block">
          <strong>${esc(tKey('inspector.whatDone'))}</strong>
          <p>${esc(m?.content || evRec?.fullSummary || evRec?.summary || actionLabel(act))}</p>
        </div>
        ${extras.map((ex) => `<div class="inspector-block"><strong>${esc(ex.label)}</strong><p>${esc(ex.val)}</p></div>`).join('')}`;
      return;
    }

    if (item.type === 'edge') {
      const fromId = normalizeRoleId(item.from);
      const toId = normalizeRoleId(item.to);
      const cutoff = state.replayLive ? Infinity : state.replaySeq;
      const edgeEvents = buildRecordedEvents().filter((ev) => ev.seq <= cutoff && ev.from === fromId && ev.to === toId);
      title.innerHTML = `${esc(roleLabel(fromId))} <span class="dir-arrow">${SVG_ICONS.arrow}</span> ${esc(roleLabel(toId))}`;
      if (!edgeEvents.length) {
        body.innerHTML = `<p class="empty-note">${esc(tKey('inspector.noEdgeEvents'))}</p>`;
        return;
      }
      body.innerHTML = `
        <div class="inspector-block">
          <strong>${esc(tKey('inspector.participants'))}</strong>
          <div class="finding-meta">
            ${renderRoleMonogram(fromId, 24)} <span>${esc(roleLabel(fromId))}</span>
            ${SVG_ICONS.arrow}
            ${renderRoleMonogram(toId, 24)} <span>${esc(roleLabel(toId))}</span>
          </div>
        </div>
        <div class="inspector-block">
          <strong>${esc(tKey('inspector.edgeHeading'))} (${num(edgeEvents.length)})</strong>
        </div>
        ${edgeEvents.map((ev) => {
          const msg = state.messages.find((x) => Number(x.seq) === Number(ev.seq));
          const catMeta = requestCategoryMeta(msg || ev);
          const reqLabel = requestTypeLabel(msg || ev);
          const what = msg?.content || ev.fullSummary || ev.summary || actionLabel(ev.action);
          return `<div class="inspector-block">
            <div class="finding-meta">
              <span class="mono-id">#${esc(ev.seq)}</span>
              <span class="req-type-chip" data-req-category="${esc(catMeta.category)}">${actionIcon(ev.action)} <span>${esc(reqLabel)}</span></span>
              ${ev.findingId ? `<span class="mono-id finding-ref-tag">${esc(ev.findingId)}</span>` : ''}
            </div>
            <p>${esc(what)}</p>
            <button type="button" class="edge-event-link" data-seq="${esc(ev.seq)}">${esc(tKey('inspector.openEvent'))} #${esc(ev.seq)}</button>
          </div>`;
        }).join('')}`;
    }
  }

  function buildRecordedEvents() {
    if (recordedEventsCache.rev === dataRevision) return recordedEventsCache.events;
    const bySeq = new Map();
    for (const m of state.messages) {
      const s = Number(m.seq || 0);
      if (s <= 0) continue;
      bySeq.set(s, {
        seq: s,
        from: normalizeRoleId(m.senderRole || m.senderCode || 'main_agent'),
        to: normalizeRoleId(m.recipientRole || m.recipientCode || m.senderRole || 'main_agent'),
        action: String(m.actionType || 'MESSAGE').toUpperCase(),
        requestType: m.requestType || '',
        findingId: m.findingId || '',
        result: String(m.result || '').toUpperCase(),
        decision: String(m.decision || '').toUpperCase(),
        severity: String(m.severity || '').toUpperCase(),
        resolved: Boolean(m.resolved),
        summary: String(m.content || '').slice(0, 60),
        fullSummary: String(m.content || ''),
      });
    }
    for (const ev of state.interactions) {
      const s = Number(ev.seq || 0);
      if (s <= 0) continue;
      const existing = bySeq.get(s) || {};
      bySeq.set(s, {
        seq: s,
        from: normalizeRoleId(ev.from || existing.from || 'main_agent'),
        to: normalizeRoleId(ev.to || existing.to || 'team-manager'),
        action: String(ev.action || existing.action || 'PEER_SYNC').toUpperCase(),
        requestType: ev.requestType || existing.requestType || '',
        findingId: ev.findingId || existing.findingId || '',
        result: String(ev.result || existing.result || '').toUpperCase(),
        decision: String(ev.decision || existing.decision || '').toUpperCase(),
        severity: String(ev.severity || existing.severity || '').toUpperCase(),
        resolved: Boolean(ev.resolved || existing.resolved),
        summary: ev.summary || existing.summary || '',
        fullSummary: existing.fullSummary || ev.summary || '',
      });
    }
    const sorted = [...bySeq.values()].sort((a, b) => a.seq - b.seq);
    recordedEventsCache = { rev: dataRevision, events: sorted };
    return sorted;
  }

  function resolveFindingStateAt(findingId, cutoff, events) {
    if (!findingId) return null;
    if (state.replayLive && (cutoff === undefined || cutoff === Infinity)) {
      const f = state.findings.find((item) => item.id === findingId);
      return f ? f.state : null;
    }
    const list = events || buildRecordedEvents();
    const limit = cutoff === undefined ? Infinity : cutoff;
    let st = null;
    for (const e of list) {
      if (e.seq > limit) break;
      if (e.findingId !== findingId) continue;
      const res = String(e.result || '').toUpperCase();
      const dec = String(e.decision || '').toUpperCase();
      const sev = String(e.severity || '').toUpperCase();
      if (e.action === 'RETURN_DEFECT' || e.action === 'QA_REOPEN') {
        st = 'Open';
      } else if (e.action === 'WORKER_FIX') {
        st = 'InReview';
      } else if (e.action === 'QA_DISPATCH') {
        st = 'Testing';
      } else if (e.action === 'QA_REPORT') {
        st = res === 'PASS' ? 'Verified' : 'Fixing';
      } else if (e.action === 'REVIEW_QUERY') {
        if (res === 'REJECT' || dec === 'REJECT' || sev === 'HIGH' || sev === 'CRITICAL') {
          st = 'Fixing';
        }
      }
    }
    return st;
  }

  function findingStateToTone(st) {
    if (!st) return null;
    if (st === 'Verified' || st === 'Closed') return 'verified';
    if (st === 'Open') return 'open';
    if (st === 'Fixing' || st === 'Testing') return 'working';
    if (st === 'InReview') return 'review';
    if (st === 'WontFix') return 'muted';
    return null;
  }

  function eventTone(ev, cutoff = state.replayLive ? Infinity : state.replaySeq, events = buildRecordedEvents()) {
    const fState = ev.findingId ? resolveFindingStateAt(ev.findingId, cutoff, events) : null;
    const fTone = findingStateToTone(fState);
    const res = String(ev.result || '').toUpperCase();
    let tone = 'muted';
    if (fTone) {
      tone = fTone;
    } else if (res === 'PASS') {
      tone = 'verified';
    } else if (res === 'FAIL') {
      tone = 'open';
    } else if (state.replayLive && ev.resolved && ev.findingId) {
      tone = 'verified';
    }
    const colorMap = {
      verified: 'var(--verified)',
      open: 'var(--open)',
      review: 'var(--review)',
      working: 'var(--working)',
      muted: 'var(--ink-muted)',
    };
    return { tone, color: colorMap[tone], marker: `seq-arrow-${tone}` };
  }

  function eventToneColor(ev, cutoff, events) {
    return eventTone(ev, cutoff, events).color;
  }

  function requestCategoryMeta(item) {
    const code = resolveRequestType(item);
    if (code === 'REFERRAL') {
      return { category: 'referral', color: 'var(--cat-referral)', seqMarker: 'seq-arrow-cat-referral', netMarker: 'net-cat-referral' };
    }
    if (code === 'QUESTION' || code === 'INTERROGATION') {
      return { category: 'inquiry', color: 'var(--cat-inquiry)', seqMarker: 'seq-arrow-cat-inquiry', netMarker: 'net-cat-inquiry' };
    }
    if (code === 'DEFECT_RETURN' || code === 'CRITIQUE') {
      return { category: 'defect', color: 'var(--cat-defect)', seqMarker: 'seq-arrow-cat-defect', netMarker: 'net-cat-defect' };
    }
    if (code === 'REWRITE') {
      return { category: 'rewrite', color: 'var(--cat-rewrite)', seqMarker: 'seq-arrow-cat-rewrite', netMarker: 'net-cat-rewrite' };
    }
    if (code === 'PEER_SYNC' || code === 'MESSAGE') {
      return { category: 'sync', color: 'var(--cat-sync)', seqMarker: 'seq-arrow-cat-sync', netMarker: 'net-cat-sync' };
    }
    if (code === 'QA_REPORT' || code === 'DECISION') {
      return { category: 'verify', color: 'var(--cat-verify)', seqMarker: 'seq-arrow-cat-verify', netMarker: 'net-cat-verify' };
    }
    return { category: 'sync', color: 'var(--cat-sync)', seqMarker: 'seq-arrow-cat-sync', netMarker: 'net-cat-sync' };
  }

  function renderReplayControls(events) {
    const minSeq = events.length ? events[0].seq : 0;
    const maxSeq = events.length ? events[events.length - 1].seq : 0;
    const slider = $('#graph-replay-slider');
    if (slider) {
      slider.min = String(minSeq);
      slider.max = String(maxSeq);
      if (state.replayLive) state.replaySeq = maxSeq;
      slider.value = String(Math.max(minSeq, Math.min(maxSeq, state.replaySeq)));
    }

    const ticksEl = $('#replay-ticks');
    if (ticksEl) {
      if (!maxSeq || !events.length) {
        replayTicksStructKey = '';
        ticksEl.innerHTML = '';
      } else {
        const isRtl = document.documentElement.dir === 'rtl';
        const cutoff = state.replayLive ? Infinity : state.replaySeq;
        const structKey = `${dataRevision}|${state.activeConvId || ''}|${isRtl ? 'rtl' : 'ltr'}|${minSeq}|${maxSeq}|${events.length}`;
        if (replayTicksStructKey !== structKey) {
          replayTicksStructKey = structKey;
          ticksEl.innerHTML = events.map((ev) => {
            const ratio = maxSeq > minSeq ? (ev.seq - minSeq) / (maxSeq - minSeq) : 0.5;
            const pos = isRtl ? (1 - ratio) : ratio;
            const leftCss = `calc(8px + (100% - 16px) * ${pos.toFixed(4)})`;
            const future = ev.seq > cutoff;
            return `<span class="replay-tick" data-seq="${esc(ev.seq)}" style="left:${leftCss};background-color:${eventToneColor(ev, cutoff, events)};opacity:${future ? '0.26' : '1'};"></span>`;
          }).join('');
        } else {
          const bySeq = new Map(events.map((ev) => [String(ev.seq), ev]));
          for (const tick of ticksEl.children) {
            const ev = bySeq.get(tick.dataset.seq);
            if (!ev) continue;
            const future = ev.seq > cutoff;
            const wantOpacity = future ? '0.26' : '1';
            if (tick.style.opacity !== wantOpacity) tick.style.opacity = wantOpacity;
            const wantColor = eventToneColor(ev, cutoff, events);
            if (tick.style.backgroundColor !== wantColor) tick.style.backgroundColor = wantColor;
          }
        }
      }
    }

    const playBtn = $('#graph-replay-play');
    if (playBtn) {
      const playing = Boolean(state.replayTimer);
      playBtn.innerHTML = `${playing ? SVG_ICONS.pause : SVG_ICONS.play}<span>${esc(playing ? tKey('map.replay.pause') : tKey('map.replay.play'))}</span>`;
    }

    const seqEl = $('#graph-replay-seq');
    if (seqEl) {
      seqEl.textContent = `#${num(state.replaySeq)} / #${num(maxSeq)}`;
    }

    const liveBtn = $('#graph-replay-live');
    if (liveBtn) {
      liveBtn.classList.toggle('tt-btn-primary', state.replayLive);
      if (state.replayLive) {
        liveBtn.textContent = tKey('map.replay.live');
      } else {
        const newer = events.filter((ev) => ev.seq > state.replaySeq).length;
        liveBtn.textContent = tKey('map.replay.behind', { n: num(newer) });
      }
    }
  }

  function computeMapSignature() {
    const widthEl = state.mapSubview === 'network' ? $('#network-graph-wrap') : $('#sequence-diagram-canvas');
    const w = widthEl?.clientWidth || 0;
    return [
      dataRevision,
      state.activeConvId || '',
      state.language,
      state.mapSubview,
      state.replayLive ? 'L' : state.replaySeq,
      state.replayTimer ? 1 : 0,
      inspectorKey(),
      w,
    ].join('|');
  }

  function renderMap() {
    if (!state.hasSession) return;
    for (const btn of $$('#map-subview-toggle .seg-btn')) {
      const active = btn.dataset.subview === state.mapSubview;
      btn.classList.toggle('is-active', active);
      btn.setAttribute('aria-pressed', active ? 'true' : 'false');
    }
    const seqWrap = $('#sequence-diagram-wrap');
    const netWrap = $('#network-graph-wrap');
    if (seqWrap) seqWrap.classList.toggle('hidden', state.mapSubview !== 'sequence');
    if (netWrap) netWrap.classList.toggle('hidden', state.mapSubview !== 'network');

    const sig = computeMapSignature();
    if (signatures.map === sig) return;
    signatures.map = sig;

    const events = buildRecordedEvents();
    renderReplayControls(events);
    const cutoff = state.replayLive ? Infinity : state.replaySeq;

    if (state.mapSubview === 'sequence') {
      renderSequenceDiagram(events, cutoff);
    } else {
      renderNetworkView(events, cutoff);
    }
    if (state.inspectorItem?.type === 'edge') {
      renderInspector();
    }
  }

  function renderSequenceDiagram(events, cutoff) {
    const canvas = $('#sequence-diagram-canvas');
    const tbody = $('#sequence-sr-tbody');
    if (tbody) {
      const srKey = `${dataRevision}|${state.activeConvId || ''}|${state.language}|${state.replayLive ? 'L' : cutoff}`;
      if (srTableCacheKey !== srKey) {
        srTableCacheKey = srKey;
        const toneLabel = (ev) => {
          const fState = ev.findingId ? resolveFindingStateAt(ev.findingId, cutoff, events) : null;
          if (fState) return findingStateLabel(fState);
          const { tone } = eventTone(ev, cutoff, events);
          if (tone === 'verified') return tKey('flow.findings.state.Verified');
          if (tone === 'open') return tKey('flow.findings.state.Open');
          if (tone === 'review') return tKey('flow.findings.state.InReview');
          if (tone === 'working') return tKey('flow.findings.state.Fixing');
          return '—';
        };
        tbody.innerHTML = events.map((ev) => `<tr>
          <td>#${esc(ev.seq)}</td>
          <td>${esc(roleLabel(ev.from))}</td>
          <td>${esc(roleLabel(ev.to))}</td>
          <td>${esc(actionLabel(ev.action))}</td>
          <td>${esc(ev.findingId || '—')}</td>
          <td>${esc(toneLabel(ev))}</td>
        </tr>`).join('');
      }
    }
    if (!canvas) return;
    if (!events.length) {
      seqDiagramStructKey = '';
      canvas.innerHTML = `<p class="empty-note">${esc(tKey('map.empty'))}</p>`;
      return;
    }

    const activeSet = new Set();
    for (const ev of events) {
      if (ROLE_DEFAULTS[ev.from]) activeSet.add(ev.from);
      if (ROLE_DEFAULTS[ev.to]) activeSet.add(ev.to);
    }
    const orderedIds = Object.keys(ROLE_DEFAULTS).filter((id) => activeSet.has(id));
    if (!orderedIds.length) orderedIds.push('main_agent', 'team-manager');

    const isRtl = document.documentElement.dir === 'rtl';
    const cols = isRtl ? [...orderedIds].reverse() : orderedIds;
    const width = Math.max(340, canvas.clientWidth || 640);
    const colW = Math.max(54, Math.floor((width - 24) / cols.length));
    const svgW = Math.max(width, cols.length * colW + 24);
    const headerH = 44;
    const rowH = 42;
    const svgH = headerH + events.length * rowH + 16;

    const resolveSeqVisual = (ev) => {
      const evTone = eventTone(ev, cutoff, events);
      if (evTone.tone === 'muted') {
        const cat = requestCategoryMeta(ev);
        return { color: cat.color, marker: cat.seqMarker };
      }
      return { color: evTone.color, marker: evTone.marker };
    };

    const structKey = `${dataRevision}|${state.activeConvId || ''}|${state.language}|${svgW}|${events.length}`;
    if (seqDiagramStructKey === structKey && canvas.querySelector('svg .seq-event-row')) {
      const bySeq = new Map(events.map((ev) => [Number(ev.seq), ev]));
      for (const rowEl of canvas.querySelectorAll('svg .seq-event-row')) {
        const seqNum = Number(rowEl.dataset.seq);
        const ev = bySeq.get(seqNum);
        if (!ev) continue;
        const isFuture = seqNum > cutoff;
        const isSelected = state.inspectorItem?.type === 'event' && Number(state.inspectorItem.seq) === seqNum;
        const { color, marker } = resolveSeqVisual(ev);
        rowEl.setAttribute('opacity', isFuture ? '0.25' : '1');
        rowEl.classList.toggle('is-selected', isSelected);
        const vis = rowEl.querySelector('.seq-edge-main');
        if (vis) {
          vis.setAttribute('stroke', color);
          vis.setAttribute('stroke-width', isSelected ? (vis.tagName === 'path' ? '2.6' : '2.8') : (vis.tagName === 'path' ? '1.6' : '1.8'));
          vis.setAttribute('marker-end', `url(#${marker})`);
        }
        const flow = rowEl.querySelector('.seq-edge-flow');
        if (flow) flow.setAttribute('stroke', color);
        const port = rowEl.querySelector('.seq-origin-port');
        if (port) port.setAttribute('fill', color);
        const txt = rowEl.querySelector('text');
        if (txt) txt.setAttribute('font-weight', isSelected ? '700' : '600');
      }
      return;
    }
    seqDiagramStructKey = structKey;

    const colX = new Map();
    cols.forEach((id, idx) => colX.set(id, 12 + colW * idx + colW / 2));

    const defs = `<defs>
      <marker id="seq-arrow-open" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="6" markerHeight="6" orient="auto-start-reverse"><path d="M 0 1 L 10 5 L 0 9 z" fill="var(--open)"/></marker>
      <marker id="seq-arrow-working" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="6" markerHeight="6" orient="auto-start-reverse"><path d="M 0 1 L 10 5 L 0 9 z" fill="var(--working)"/></marker>
      <marker id="seq-arrow-review" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="6" markerHeight="6" orient="auto-start-reverse"><path d="M 0 1 L 10 5 L 0 9 z" fill="var(--review)"/></marker>
      <marker id="seq-arrow-verified" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="6" markerHeight="6" orient="auto-start-reverse"><path d="M 0 1 L 10 5 L 0 9 z" fill="var(--verified)"/></marker>
      <marker id="seq-arrow-muted" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="6" markerHeight="6" orient="auto-start-reverse"><path d="M 0 1 L 10 5 L 0 9 z" fill="var(--ink-muted)"/></marker>
      <marker id="seq-arrow-cat-referral" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="6" markerHeight="6" orient="auto-start-reverse"><path d="M 0 1 L 10 5 L 0 9 z" fill="var(--cat-referral)"/></marker>
      <marker id="seq-arrow-cat-inquiry" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="6" markerHeight="6" orient="auto-start-reverse"><path d="M 0 1 L 10 5 L 0 9 z" fill="var(--cat-inquiry)"/></marker>
      <marker id="seq-arrow-cat-defect" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="6" markerHeight="6" orient="auto-start-reverse"><path d="M 0 1 L 10 5 L 0 9 z" fill="var(--cat-defect)"/></marker>
      <marker id="seq-arrow-cat-rewrite" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="6" markerHeight="6" orient="auto-start-reverse"><path d="M 0 1 L 10 5 L 0 9 z" fill="var(--cat-rewrite)"/></marker>
      <marker id="seq-arrow-cat-sync" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="6" markerHeight="6" orient="auto-start-reverse"><path d="M 0 1 L 10 5 L 0 9 z" fill="var(--cat-sync)"/></marker>
      <marker id="seq-arrow-cat-verify" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="6" markerHeight="6" orient="auto-start-reverse"><path d="M 0 1 L 10 5 L 0 9 z" fill="var(--cat-verify)"/></marker>
    </defs>`;

    const lifelines = cols.map((id) => {
      const x = colX.get(id);
      const { monogram, frameShape } = getRoleMeta(id);
      const glyph = ROLE_GLYPHS[id] || ROLE_GLYPHS.main_agent;
      const tip = roleBilingualLabel(id);
      let frameSvg = '';
      if (frameShape === 'hexagon') {
        frameSvg = `<polygon points="${x},3 ${x + 11},8 ${x + 11},18 ${x},23 ${x - 11},18 ${x - 11},8" fill="var(--sheet-2)" stroke="var(--rule-strong)" stroke-width="1.4"/>`;
      } else if (frameShape === 'square') {
        frameSvg = `<rect x="${x - 11}" y="3" width="22" height="20" rx="4" fill="var(--sheet-2)" stroke="var(--rule-strong)" stroke-width="1.4"/>`;
      } else if (frameShape === 'diamond') {
        frameSvg = `<polygon points="${x},2 ${x + 12},13 ${x},24 ${x - 12},13" fill="var(--sheet-2)" stroke="var(--rule-strong)" stroke-width="1.4"/>`;
      } else {
        frameSvg = `<circle cx="${x}" cy="13" r="10.5" fill="var(--sheet-2)" stroke="var(--rule-strong)" stroke-width="1.4"/>`;
      }
      return `<g class="seq-lifeline-head" data-role="${esc(id)}" data-role-tooltip="${esc(tip)}" tabindex="0" aria-label="${esc(tip)}">
        <title>${esc(tip)}</title>
        ${frameSvg}
        <g transform="translate(${x - 7}, 6) scale(0.7)" fill="none" stroke="var(--ink)" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round">${glyph}</g>
        <text x="${x}" y="38" text-anchor="middle" fill="var(--ink)" font-size="12" font-weight="700" font-family="Outfit, Vazirmatn, sans-serif">${esc(monogram)}</text>
        <line x1="${x}" y1="42" x2="${x}" y2="${svgH - 8}" stroke="var(--rule-strong)" stroke-dasharray="3 3" stroke-width="1"/>
      </g>`;
    }).join('');

    const rowsSvg = events.map((ev, idx) => {
      const y = headerH + idx * rowH + 26;
      const x1 = colX.get(ev.from) ?? colX.get(cols[0]);
      const x2 = colX.get(ev.to) ?? x1;
      const isFuture = ev.seq > cutoff;
      const isSelected = state.inspectorItem?.type === 'event' && Number(state.inspectorItem.seq) === Number(ev.seq);
      const { color, marker } = resolveSeqVisual(ev);
      const reqLabel = requestTypeLabel(ev);
      const label = `#${ev.seq} ${ev.findingId ? `${ev.findingId} · ` : ''}${reqLabel}`;
      const midX = x1 === x2 ? x1 + 24 : (x1 + x2) / 2;
      const labelW = Math.min(svgW - 16, Math.max(64, Math.round(label.length * 6.8 + 16)));
      const pillX = Math.max(4, Math.min(svgW - labelW - 4, Math.round(midX - labelW / 2)));
      const pillTextX = pillX + labelW / 2;
      const startY = x1 === x2 ? y - 6 : y;
      const hitLine = x1 === x2
        ? `<path d="M ${x1} ${y - 6} h 26 v 12 h -26" fill="none" stroke="transparent" stroke-width="14"/>`
        : `<line x1="${x1}" y1="${y}" x2="${x2}" y2="${y}" stroke="transparent" stroke-width="14"/>`;
      const lineSvg = x1 === x2
        ? `<path class="seq-edge-main" d="M ${x1} ${y - 6} h 26 v 12 h -26" fill="none" stroke="${color}" stroke-width="${isSelected ? '2.6' : '1.6'}" marker-end="url(#${marker})"/><path class="seq-edge-flow" d="M ${x1} ${y - 6} h 26 v 12 h -26" fill="none" stroke="${color}" stroke-width="${isSelected ? '2.4' : '1.6'}"/>`
        : `<line class="seq-edge-main" x1="${x1}" y1="${y}" x2="${x2}" y2="${y}" stroke="${color}" stroke-width="${isSelected ? '2.8' : '1.8'}" marker-end="url(#${marker})"/><line class="seq-edge-flow" x1="${x1}" y1="${y}" x2="${x2}" y2="${y}" stroke="${color}" stroke-width="${isSelected ? '2.4' : '1.8'}"/>`;
      return `<g class="seq-event-row${isSelected ? ' is-selected' : ''}" data-seq="${esc(ev.seq)}" tabindex="0" role="button" aria-label="${esc(label)}" opacity="${isFuture ? '0.25' : '1'}">
        <title>${esc(label)}${ev.summary ? ` — ${esc(ev.summary)}` : ''}</title>
        ${hitLine}
        <circle class="seq-origin-port" cx="${x1}" cy="${startY}" r="3" fill="${color}"/>
        ${lineSvg}
        <rect class="seq-label-pill" x="${pillX}" y="${y - 23}" width="${labelW}" height="20" rx="10" fill="var(--sheet)" stroke="var(--rule)" stroke-width="1"/>
        <text x="${pillTextX}" y="${y - 9}" text-anchor="middle" fill="var(--ink)" font-size="12" font-weight="${isSelected ? '700' : '600'}">${esc(label)}</text>
      </g>`;
    }).join('');

    canvas.innerHTML = `<svg viewBox="0 0 ${svgW} ${svgH}" width="${svgW}" height="${svgH}" role="img" aria-label="${esc(tKey('map.sr.caption'))}">${defs}${lifelines}${rowsSvg}</svg>`;
  }

  function renderNetworkView(events, cutoff) {
    const visibleEvents = events.filter((ev) => ev.seq <= cutoff);
    const aggMap = new Map();
    for (const ev of visibleEvents) {
      if (!ROLE_DEFAULTS[ev.from] || !ROLE_DEFAULTS[ev.to] || ev.from === ev.to) continue;
      const key = `${ev.from}->${ev.to}`;
      const cur = aggMap.get(key) || { from: ev.from, to: ev.to, count: 0, openCount: 0, events: [] };
      cur.count += 1;
      if (eventTone(ev, cutoff, events).tone === 'open') cur.openCount += 1;
      cur.events.push(ev);
      aggMap.set(key, cur);
    }
    const edges = [...aggMap.values()];

    // Communication table for < 480px
    const tableWrap = $('#comm-table-wrap');
    if (tableWrap) {
      if (!edges.length) {
        tableWrap.innerHTML = `<p class="empty-note">${esc(tKey('map.empty'))}</p>`;
      } else {
        tableWrap.innerHTML = `<table class="comm-table">
          <thead><tr>
            <th>${esc(tKey('map.table.from'))}</th>
            <th>${esc(tKey('map.table.to'))}</th>
            <th>${esc(tKey('map.table.count'))}</th>
            <th>${esc(tKey('map.table.open'))}</th>
          </tr></thead>
          <tbody>${edges.map((e) => `<tr class="net-edge-row" data-from="${esc(e.from)}" data-to="${esc(e.to)}" tabindex="0" role="button">
            <td>${esc(getRoleMeta(e.from).monogram)} · ${esc(roleLabel(e.from))}</td>
            <td>${esc(getRoleMeta(e.to).monogram)} · ${esc(roleLabel(e.to))}</td>
            <td class="mono-id">${num(e.count)}</td>
            <td class="mono-id">${num(e.openCount)}</td>
          </tr>`).join('')}</tbody>
        </table>`;
      }
    }

    const svg = $('#swarm-interaction-svg');
    if (!svg) return;
    const rawNetW = $('#network-graph-wrap')?.clientWidth || 0;
    if (rawNetW > 0) state.lastNetWidth = rawNetW;
    const containerW = Math.max(540, Math.min(860, rawNetW || state.lastNetWidth || 640));
    const h = 440;
    svg.setAttribute('viewBox', `0 0 ${containerW} ${h}`);

    const row1 = ['main_agent', 'team-manager', 'council-critic', 'code-reviewer'];
    const row2 = ['qa-reviewer'];
    const row3 = ['ui-frontend-designer', 'backend-auditor', 'ecommerce_seo_operator', 'wp_technical_operator'];
    const pos = {};
    const sidePad = 68;
    const spanW = Math.max(240, containerW - sidePad * 2);
    row1.forEach((id, i) => { pos[id] = { x: sidePad + (spanW / (row1.length - 1)) * i, y: 76 }; });
    row2.forEach((id) => { pos[id] = { x: Math.min(containerW - sidePad, Math.round(containerW * 0.72)), y: 222 }; });
    row3.forEach((id, i) => { pos[id] = { x: sidePad + (spanW / (row3.length - 1)) * i, y: 368 }; });

    const selEdge = state.inspectorItem?.type === 'edge'
      ? `${normalizeRoleId(state.inspectorItem.from)}>${normalizeRoleId(state.inspectorItem.to)}`
      : '';
    const netNodesSig = Object.keys(pos).map((id) => {
      const active = isRoleActiveInCase(id) ? 1 : 0;
      const ag = state.agents.find((a) => normalizeRoleId(a.id) === id);
      const working = !state.isClosed && ag && isWorkingAgentStatus(ag.status) ? 1 : 0;
      return `${id}:${active}${working}`;
    }).join(',');
    const netEdgesSig = edges.map((e) => {
      const latest = e.events[e.events.length - 1];
      const eTone = eventTone(latest, cutoff, events).tone;
      return `${e.from}>${e.to}:${e.count}:${e.openCount}:${eTone}:${requestTypeLabel(latest)}`;
    }).join('|');
    const netStructKey = `${state.activeConvId || ''}|${state.language}|${containerW}|${state.isClosed ? 1 : 0}|${selEdge}|${netNodesSig}|${netEdgesSig}`;
    if (svg.dataset && svg.dataset.netKey === netStructKey && svg.innerHTML) return;
    if (svg.dataset) svg.dataset.netKey = netStructKey;

    const markerPath = '<path d="M 1 1.5 L 10.5 6 L 1 10.5 L 3.4 6 z"';
    const markerDefs = [
      ['net-open', 'var(--open)'],
      ['net-working', 'var(--working)'],
      ['net-review', 'var(--review)'],
      ['net-verified', 'var(--verified)'],
      ['net-muted', 'var(--ink-muted)'],
      ['net-cat-referral', 'var(--cat-referral)'],
      ['net-cat-inquiry', 'var(--cat-inquiry)'],
      ['net-cat-defect', 'var(--cat-defect)'],
      ['net-cat-rewrite', 'var(--cat-rewrite)'],
      ['net-cat-sync', 'var(--cat-sync)'],
      ['net-cat-verify', 'var(--cat-verify)'],
    ].map(([id, fill]) => (
      `<marker id="${id}" viewBox="0 0 12 12" refX="9.2" refY="6" markerWidth="10" markerHeight="10" markerUnits="userSpaceOnUse" orient="auto-start-reverse">${markerPath} fill="${fill}"/></marker>`
    )).join('');
    const defs = `<defs>${markerDefs}</defs>`;

    const isRtl = document.documentElement.dir === 'rtl';
    const tierLabelX = isRtl ? containerW - 14 : 14;
    const tierAnchor = isRtl ? 'end' : 'start';
    const rtlTextStyle = 'direction:ltr;unicode-bidi:plaintext';
    const tierBands = `<g class="net-tier-guides" aria-hidden="true">
      <line x1="14" y1="148" x2="${containerW - 14}" y2="148" stroke="var(--rule)" stroke-dasharray="4 4" stroke-width="1"/>
      <line x1="14" y1="294" x2="${containerW - 14}" y2="294" stroke="var(--rule)" stroke-dasharray="4 4" stroke-width="1"/>
      <text x="${tierLabelX}" y="22" text-anchor="${tierAnchor}" style="${rtlTextStyle}" fill="var(--ink-muted)" font-size="12" font-weight="600" opacity="0.88">${esc(tKey('map.tier.supervisors'))}</text>
      <text x="${tierLabelX}" y="166" text-anchor="${tierAnchor}" style="${rtlTextStyle}" fill="var(--ink-muted)" font-size="12" font-weight="600" opacity="0.88">${esc(tKey('map.tier.tester'))}</text>
      <text x="${tierLabelX}" y="312" text-anchor="${tierAnchor}" style="${rtlTextStyle}" fill="var(--ink-muted)" font-size="12" font-weight="600" opacity="0.88">${esc(tKey('map.tier.workers'))}</text>
    </g>`;

    const edgeTone = (edgeEvents) => {
      let hasWorking = false;
      let hasReview = false;
      let hasVerified = false;
      for (const ev of edgeEvents) {
        const { tone } = eventTone(ev, cutoff, events);
        if (tone === 'open') return 'open';
        if (tone === 'working') hasWorking = true;
        else if (tone === 'review') hasReview = true;
        else if (tone === 'verified') hasVerified = true;
      }
      if (hasWorking) return 'working';
      if (hasReview) return 'review';
      if (hasVerified) return 'verified';
      return 'muted';
    };

    const toneColor = {
      open: 'var(--open)',
      working: 'var(--working)',
      review: 'var(--review)',
      verified: 'var(--verified)',
      muted: 'var(--ink-muted)',
    };

    const ellipseAnchor = (p, ux, uy) => {
      const rx = 34;
      // Extra bottom clearance so arrows leaving/entering from below clear node monogram text cleanly
      const ry = uy > 0.52 ? 40 : 27;
      const scale = 1 / (Math.hypot(ux / rx, uy / ry) || 1);
      return { x: p.x + ux * scale, y: p.y + uy * scale };
    };

    const edgePlans = edges.map((e, idx) => {
      const p1 = pos[e.from];
      const p2 = pos[e.to];
      const dx = p2.x - p1.x;
      const dy = p2.y - p1.y;
      const len = Math.hypot(dx, dy) || 1;
      const nx = -dy / len;
      const ny = dx / len;
      const hasReverse = aggMap.has(`${e.to}->${e.from}`);
      const isSameRow = Math.abs(dy) < 16;

      let signedBend;
      if (hasReverse) {
        const mag = Math.max(36, Math.min(62, len * 0.22));
        signedBend = (e.from < e.to ? 1 : -1) * mag;
      } else if (isSameRow) {
        // Quadratic apex reaches 0.5 * bend; scale >= 72 when spanning intermediate same-row nodes
        const skipsNodes = Math.abs(dx) > spanW * 0.45;
        const mag = skipsNodes ? Math.max(72, Math.min(86, len * 0.22)) : Math.max(46, Math.min(64, len * 0.25));
        // Bend row-3 arcs cleanly upward away from monograms, row-1 arcs downward away from tier title
        const wantUp = p1.y > 280;
        const targetDy = wantUp ? -1 : 1;
        signedBend = (ny >= 0 ? targetDy : -targetDy) * mag;
      } else {
        const mag = Math.max(24, Math.min(44, len * 0.13)) + (idx % 2) * 6;
        signedBend = (idx % 2 === 0 ? 1 : -1) * mag;
      }

      const cx = (p1.x + p2.x) / 2 + nx * signedBend;
      const cy = (p1.y + p2.y) / 2 + ny * signedBend;

      const t1x = cx - p1.x;
      const t1y = cy - p1.y;
      const t1Len = Math.hypot(t1x, t1y) || 1;
      const sPt = ellipseAnchor(p1, t1x / t1Len, t1y / t1Len);

      const t2x = p2.x - cx;
      const t2y = p2.y - cy;
      const t2Len = Math.hypot(t2x, t2y) || 1;
      const ePt = ellipseAnchor(p2, -t2x / t2Len, -t2y / t2Len);

      const sx = sPt.x;
      const sy = sPt.y;
      const ex = ePt.x;
      const ey = ePt.y;

      const tPos = hasReverse ? (e.from < e.to ? 0.44 : 0.56) : 0.5;
      const mt = 1 - tPos;
      const bx = mt * mt * sx + 2 * mt * tPos * cx + tPos * tPos * ex;
      const by = mt * mt * sy + 2 * mt * tPos * cy + tPos * tPos * ey;
      const outSign = signedBend >= 0 ? 1 : -1;
      const lx = bx + nx * outSign * 14;
      const ly = by + ny * outSign * 14 + 4;

      const latest = e.events[e.events.length - 1];
      const reqLabel = requestTypeLabel(latest);
      const edgeText = e.count > 1 ? `×${e.count} ${reqLabel}` : reqLabel;
      const labelW = Math.min(176, Math.max(56, edgeText.length * 7.0 + 18));
      return { e, sx, sy, cx, cy, ex, ey, lx, ly, labelW, labelH: 20, latest, edgeText };
    });

    const nodePts = Object.values(pos);
    for (let pass = 0; pass < 24; pass++) {
      let moved = false;
      for (let i = 0; i < edgePlans.length; i++) {
        const a = edgePlans[i];
        // Repel from node boxes so labels never obscure SVG icons or monograms
        for (const np of nodePts) {
          if (Math.abs(a.lx - np.x) < (a.labelW / 2 + 36) && Math.abs(a.ly - np.y) < 38) {
            a.ly += (a.ly <= np.y ? -15 : 15);
            moved = true;
          }
        }
        for (let j = i + 1; j < edgePlans.length; j++) {
          const b = edgePlans[j];
          const overlapX = (a.labelW / 2 + b.labelW / 2 + 6) - Math.abs(a.lx - b.lx);
          const overlapY = ((a.labelH + b.labelH) / 2 + 3) - Math.abs(a.ly - b.ly);
          if (overlapX > 0 && overlapY > 0) {
            const pushY = (overlapY / 2 + 3) * (a.ly <= b.ly ? -1 : 1);
            a.ly += pushY;
            b.ly -= pushY;
            if (overlapX < 64) {
              const pushX = Math.min(18, overlapX / 4) * (a.lx <= b.lx ? -1 : 1);
              a.lx += pushX;
              b.lx -= pushX;
            }
            moved = true;
          }
        }
        a.lx = Math.max(a.labelW / 2 + 12, Math.min(containerW - a.labelW / 2 - 12, a.lx));
        a.ly = Math.max(20, Math.min(h - 14, a.ly));
      }
      if (!moved) break;
    }

    const edgesSvg = edgePlans.map(({ e, sx, sy, cx, cy, ex, ey, lx, ly, labelW, latest, edgeText }) => {
      const eTone = edgeTone(e.events);
      const catMeta = eTone === 'muted' ? requestCategoryMeta(latest) : null;
      const stroke = catMeta ? catMeta.color : (toneColor[eTone] || 'var(--ink-muted)');
      const marker = catMeta ? catMeta.netMarker : `net-${eTone}`;
      const isSelected = state.inspectorItem?.type === 'edge' && normalizeRoleId(state.inspectorItem.from) === e.from && normalizeRoleId(state.inspectorItem.to) === e.to;
      const baseSw = Math.min(3.0, 1.5 + Math.log2(e.count + 1) * 0.55);
      const sw = (isSelected ? Math.min(3.6, baseSw + 0.9) : baseSw).toFixed(1);
      const flowSw = Math.max(1.2, Number(sw) * 0.65).toFixed(1);
      const tip = `${roleLabel(e.from)} -> ${roleLabel(e.to)}: ${edgeText}${latest?.summary ? ` — ${latest.summary}` : ''}`;
      const d = `M ${sx.toFixed(1)} ${sy.toFixed(1)} Q ${cx.toFixed(1)} ${cy.toFixed(1)} ${ex.toFixed(1)} ${ey.toFixed(1)}`;
      return `<g class="net-edge-arrow${isSelected ? ' is-selected' : ''}" data-from="${esc(e.from)}" data-to="${esc(e.to)}" tabindex="0" role="button" aria-label="${esc(tip)}">
        <title>${esc(tip)}</title>
        <path d="${d}" fill="none" stroke="transparent" stroke-width="16"/>
        <path class="net-edge-stroke" d="${d}" fill="none" stroke="${stroke}" stroke-width="${sw}" stroke-linecap="round" marker-end="url(#${marker})"/>
        <path class="net-edge-flow" d="${d}" fill="none" stroke="${stroke}" stroke-width="${flowSw}" stroke-linecap="round"/>
        <circle cx="${sx.toFixed(1)}" cy="${sy.toFixed(1)}" r="2.8" fill="${stroke}" stroke="var(--paper)" stroke-width="1"/>
        <rect class="net-label-pill" x="${(lx - labelW / 2).toFixed(1)}" y="${(ly - 14).toFixed(1)}" width="${labelW.toFixed(1)}" height="20" rx="10" fill="var(--sheet)" stroke="${stroke}" stroke-opacity="0.45" stroke-width="1"/>
        <text x="${lx.toFixed(1)}" y="${ly.toFixed(1)}" text-anchor="middle" style="${rtlTextStyle}" fill="var(--ink)" font-size="12" font-weight="600" paint-order="stroke" stroke="var(--paper)" stroke-width="3.5" stroke-linejoin="round">${esc(edgeText)}</text>
      </g>`;
    }).join('');

    const nodesSvg = Object.entries(pos).map(([id, p]) => {
      const meta = getRoleMeta(id);
      const isActive = isRoleActiveInCase(id);
      const ag = state.agents.find((a) => normalizeRoleId(a.id) === id);
      const isWorkingNow = !state.isClosed && Boolean(ag && isWorkingAgentStatus(ag.status));
      const tip = roleBilingualLabel(id);
      const glyph = ROLE_GLYPHS[id] || ROLE_GLYPHS.main_agent;
      let frameSvg = '';
      if (meta.frameShape === 'hexagon') {
        frameSvg = '<polygon class="net-node-frame" points="0,-21 26,-10 26,10 0,21 -26,10 -26,-10" fill="var(--sheet)" stroke="var(--rule-strong)" stroke-width="1.6"/>';
      } else if (meta.frameShape === 'square') {
        frameSvg = '<rect class="net-node-frame" x="-25" y="-18" width="50" height="36" rx="4" fill="var(--sheet)" stroke="var(--rule-strong)" stroke-width="1.6"/>';
      } else if (meta.frameShape === 'diamond') {
        frameSvg = '<polygon class="net-node-frame" points="0,-22 30,0 0,22 -30,0" fill="var(--sheet)" stroke="var(--rule-strong)" stroke-width="1.6"/>';
      } else {
        frameSvg = '<ellipse class="net-node-frame" cx="0" cy="0" rx="26" ry="19" fill="var(--sheet)" stroke="var(--rule-strong)" stroke-width="1.6"/>';
      }
      const haloSvg = isWorkingNow
        ? '<ellipse class="net-node-halo" cx="0" cy="0" rx="32" ry="25" fill="none" stroke="var(--working)" stroke-width="1.6"/>'
        : '';
      return `<g class="net-node-group" data-role="${esc(id)}" data-role-tooltip="${esc(tip)}" tabindex="0" transform="translate(${p.x}, ${p.y})" opacity="${isActive ? '1' : '0.42'}">
        <title>${esc(tip)}</title>
        ${haloSvg}
        ${frameSvg}
        <g transform="translate(-10, -10)" fill="none" stroke="var(--ink)" stroke-width="1.6" stroke-linecap="round" stroke-linejoin="round">${glyph}</g>
        <text x="0" y="33" text-anchor="middle" style="${rtlTextStyle}" fill="var(--ink-muted)" font-size="12" font-weight="700" font-family="ui-monospace, SFMono-Regular, monospace">${esc(meta.monogram)}</text>
      </g>`;
    }).join('');

    svg.innerHTML = `${defs}${tierBands}${edgesSvg}${nodesSvg}`;
  }

  function isRoleActiveInCase(roleId) {
    const ag = state.agents.find((a) => normalizeRoleId(a.id) === roleId);
    if (ag && isWorkingAgentStatus(ag.status)) return true;
    if (state.subtasks.some((s) => normalizeRoleId(s.assignee) === roleId)) return true;
    if (state.findings.some((f) => normalizeRoleId(f.owner) === roleId || normalizeRoleId(f.raisedBy) === roleId)) return true;
    if (state.messages.some((m) => normalizeRoleId(m.senderRole) === roleId || normalizeRoleId(m.recipientRole) === roleId)) return true;
    return false;
  }

  function renderTeamRowHtml(r) {
    const ag = state.agents.find((a) => normalizeRoleId(a.id) === r.id);
    const rawStatus = state.isClosed ? 'COMPLETED' : String(ag?.status || 'IDLE').toUpperCase();
    const title = I18N.roleText ? I18N.roleText(r, 'title', state.language) : (r.title || r.id);
    const desc = I18N.roleText ? I18N.roleText(r, 'description', state.language) : (r.description || '');
    const taskTxt = ag?.currentTask || ag?.task || (I18N.roleText ? I18N.roleText(r, 'specialty', state.language) : r.specialty) || '';
    const skills = Array.isArray(r.skills) ? r.skills : [];
    const shownSkills = skills.slice(0, 6);
    const extraSkills = skills.length - shownSkills.length;

    const turns = Number(ag?.turnsUsed ?? 0);
    const activeTool = String(ag?.activeTool || '').trim();
    const lockedFiles = (state.fileLocks || []).filter((l) => normalizeRoleId(l.owner) === r.id).map((l) => l.path);
    const roleMsgs = state.messages.filter((m) => normalizeRoleId(m.senderRole) === r.id || normalizeRoleId(m.recipientRole) === r.id).slice(-5).reverse();
    const tip = roleBilingualLabel(r.id);
    const isRealSub = Boolean(ag?.verifiedSubagent || ag?.subagentConvId);
    const subSlice = state.devMode && ag?.subagentConvId ? ` <code class="mono-id">${esc(String(ag.subagentConvId).slice(0, 8))}</code>` : '';
    const realSubBadge = isRealSub ? `<span class="verified-subagent-badge" title="${esc(tKey('team.verifiedSubagent'))}">${SVG_ICONS.originSubagent}<span>${esc(tKey('team.verifiedSubagent'))}</span>${subSlice}</span>` : '';

    return `<details class="team-row" data-details-key="team-${esc(r.id)}">
      <summary class="team-row-summary" data-role-tooltip="${esc(tip)}" title="${esc(tip)}">
        <div class="team-row-identity">
          ${renderRoleMonogram(r.id, 28)}
          <div class="team-row-titles">
            <span class="team-row-name">${esc(title)}</span>
            <span class="team-row-task">${esc(taskTxt)}</span>
          </div>
        </div>
        <div class="finding-head-right">
          ${realSubBadge}
          <span class="status-pill state-${stateTone(rawStatus)}">${esc(translateStatus(rawStatus))}</span>
        </div>
      </summary>
      <div class="team-row-body">
        ${desc ? `<p class="empty-note">${esc(desc)}</p>` : ''}
        ${(turns > 0 || activeTool) ? `<div class="finding-meta">
          ${turns > 0 ? `<span>${esc(tKey('team.turnsUsed'))}: <strong class="mono-id">${num(turns)}</strong></span>` : ''}
          ${activeTool ? `<span>${esc(tKey('team.activeTool'))}: <code class="mono-id">${esc(activeTool)}</code></span>` : ''}
        </div>` : ''}
        ${shownSkills.length ? `<div class="agent-skills-row">
          ${shownSkills.map((sk) => `<span class="skill-chip">${esc((state.language === 'en' && I18N.skillNames?.[sk]) || sk)}</span>`).join('')}
          ${extraSkills > 0 ? `<span class="skill-chip mono-id">+${num(extraSkills)}</span>` : ''}
        </div>` : ''}
        ${lockedFiles.length ? `<div><strong class="meta-note">${esc(tKey('team.lockedFiles'))}:</strong> ${lockedFiles.map((p) => `<code class="mono-id">${esc(p)}</code>`).join(' · ')}</div>` : ''}
        ${roleMsgs.length ? `<div><strong class="meta-note">${esc(tKey('team.recentEvents'))}:</strong> ${roleMsgs.map((m) => `<span class="mono-id">#${esc(m.seq)}</span>`).join(' ')}</div>` : ''}
        <div>
          <button type="button" class="tt-btn tt-compact-btn agent-chat-btn" data-id="${esc(r.id)}" ${state.isClosed ? 'disabled aria-disabled="true"' : ''}>${esc(tKey('team.msgAgent'))}</button>
        </div>
      </div>
    </details>`;
  }

  function renderTeam() {
    if (!state.hasSession) return;
    for (const btn of $$('#tab-team .tier-filters .chip-btn')) {
      btn.classList.toggle('is-active', btn.dataset.tier === state.teamTier);
    }

    const sig = `${dataRevision}|${state.activeConvId || ''}|${state.language}|${state.isClosed ? 1 : 0}|${state.devMode ? 1 : 0}|${state.teamTier}`;
    if (signatures.team === sig) return;
    signatures.team = sig;

    const baseRoles = state.roles.length ? state.roles : Object.keys(ROLE_DEFAULTS).map((id) => ({ id, title: id, tier: ROLE_DEFAULTS[id].tier }));
    const filtered = baseRoles.filter((r) => state.teamTier === 'all' || (r.tier || ROLE_DEFAULTS[r.id]?.tier) === state.teamTier);
    const active = filtered.filter((r) => isRoleActiveInCase(r.id));
    const inactive = filtered.filter((r) => !isRoleActiveInCase(r.id));

    const listEl = $('#team-list');
    if (listEl) {
      preserveDetailsOpen(listEl, () => {
        listEl.innerHTML = (active.length ? active : filtered).map(renderTeamRowHtml).join('');
      });
    }
    const inactiveDrawer = $('#inactive-team-drawer');
    const inactiveCount = $('#inactive-team-count');
    const inactiveList = $('#inactive-team-list');
    if (inactiveDrawer && inactiveCount && inactiveList) {
      const showInactive = active.length > 0 && inactive.length > 0;
      inactiveDrawer.classList.toggle('hidden', !showInactive);
      inactiveCount.textContent = num(inactive.length);
      preserveDetailsOpen(inactiveList, () => {
        inactiveList.innerHTML = showInactive ? inactive.map(renderTeamRowHtml).join('') : '';
      });
    }
  }

  function populateTargetSelect(force = false) {
    const sel = $('#composer-target');
    if (!sel) return;
    const rolesList = state.roles.length ? state.roles : Object.keys(ROLE_DEFAULTS).map((id) => ({ id, title: id }));
    if (!force && sel.options.length === rolesList.length + 1 && sel.dataset.lang === state.language) return;
    const prev = sel.value || 'ALL';
    sel.innerHTML = `<option value="ALL">${esc(tKey('flow.composer.targetTeam'))}</option>` +
      rolesList.map((r) => `<option value="${esc(r.id)}">${esc(roleLabel(r.id))}</option>`).join('');
    sel.dataset.lang = state.language;
    sel.value = prev;
  }

  function syncSettingsInputs() {
    const pIn = $('#input-project');
    const dIn = $('#input-directive');
    if (pIn && document.activeElement !== pIn) pIn.value = state.project || '';
    if (dIn && document.activeElement !== dIn) dIn.value = state.directive || '';

    const capMain = Number(state.roleCaps?.main ?? 50);
    const capManager = Number(state.roleCaps?.manager ?? 50);
    const capSub = Number(state.roleCaps?.subagents ?? 50);
    if ($('#cap-main') && document.activeElement !== $('#cap-main')) $('#cap-main').value = String(capMain);
    if ($('#cap-manager') && document.activeElement !== $('#cap-manager')) $('#cap-manager').value = String(capManager);
    if ($('#cap-subagents') && document.activeElement !== $('#cap-subagents')) $('#cap-subagents').value = String(capSub);

    const usage = state.roleUsage || {};
    const mainUsed = Number(usage.main ?? usage.main_agent ?? 0);
    const mgrUsed = Number(usage.manager ?? usage['team-manager'] ?? 0);
    const subUsed = usage.subagents !== undefined
      ? Number(usage.subagents ?? 0)
      : Object.entries(usage).reduce((acc, [k, v]) => (
        k === 'main' || k === 'main_agent' || k === 'manager' || k === 'team-manager' || k === 'user' ? acc : acc + Number(v || 0)
      ), 0);

    const setMeter = (txtSel, barSel, used, cap) => {
      const txt = $(txtSel);
      const bar = $(barSel);
      if (txt) txt.textContent = `${num(used)} / ${num(cap)}`;
      if (bar) bar.style.setProperty('--cap-ratio', String(Math.min(1, Math.max(0, cap > 0 ? used / cap : 0))));
    };
    setMeter('#cap-main-usage', '#cap-main-bar', mainUsed, capMain);
    setMeter('#cap-manager-usage', '#cap-manager-bar', mgrUsed, capManager);
    setMeter('#cap-subagents-usage', '#cap-subagents-bar', subUsed, capSub);

    const devToggle = $('#dev-mode-toggle');
    if (devToggle) devToggle.checked = state.devMode;
    const rawDrawer = $('#raw-inspector-drawer');
    if (rawDrawer) rawDrawer.classList.toggle('hidden', !state.devMode);
    const completeBtn = $('#btn-Complete-Case');
    if (completeBtn) completeBtn.disabled = state.isClosed || !state.hasSession;
  }

  function renderRawInspector() {
    const el = $('#raw-json-viewer');
    if (!el || !state.devMode) return;
    const map = {
      findings: state.findings,
      messages: state.messages,
      interactions: state.interactions,
      subtasks: state.subtasks,
      fileLocks: state.fileLocks,
      agents: state.agents,
      roles: state.roles,
      full: {
        convId: state.activeConvId,
        hasSession: state.hasSession,
        status: state.status,
        isClosed: state.isClosed,
        originCounts: state.originCounts,
        closureReceipt: state.closureReceipt,
        findings: state.findings,
        subtasks: state.subtasks,
        messages: state.messages,
      },
    };
    el.textContent = JSON.stringify(map[state.rawKind] ?? map.findings, null, 2);
  }

  function renderAll() {
    renderHeaderAndVisibility();
    if (!state.hasSession) return;
    renderFlow();
    if (state.activeTab === 'map') renderMap();
    if (state.activeTab === 'team') renderTeam();
    renderInspector();
    if (state.settingsOpen) {
      syncSettingsInputs();
      renderRawInspector();
    }
  }

  function getHostContextPath() {
    return state.workspaceUri
      ? `/api/host/context?workspaceUri=${encodeURIComponent(state.workspaceUri)}`
      : '/api/host/context';
  }

  function startHostContextWatch() {
    if (state.hostContextTimer) return;
    state.hostContextTimer = setInterval(() => {
      if (!state.userPinnedConv) syncHostContextOnly();
    }, 3000);
  }

  function startFallbackPoll() {
    if (state.pollTimer) return;
    state.pollTimer = setInterval(syncWithHostAndStatus, 5000);
  }

  function stopFallbackPoll() {
    if (state.pollTimer) {
      clearInterval(state.pollTimer);
      state.pollTimer = null;
    }
  }

  let hostSyncInFlight = null;
  async function syncHostContextOnly(forceNotify = false) {
    if (hostSyncInFlight) return hostSyncInFlight;
    hostSyncInFlight = (async () => {
      try {
        const ctx = await apiGet(getHostContextPath()).catch(() => null);
        const liveHostCid = resolveHostConvId(ctx);
        if (liveHostCid) {
          const changed = liveHostCid !== state.hostConvId;
          state.hostConvId = liveHostCid;
          const holdOpenActiveCase = Boolean(state.hasSession && !state.isClosed && state.activeConvId && state.activeConvId !== 'default');
          if (!state.userPinnedConv && liveHostCid !== state.activeConvId) {
            if (!holdOpenActiveCase || ctx?.hasSession === true) {
              await switchConversation(liveHostCid, false);
              return true;
            }
          }
          if ((changed || ctx?.hasSession) && !state.hasSession && liveHostCid === state.activeConvId) {
            await refreshStatus();
            return true;
          }
        } else if (ctx && ctx.workspaceMatched === false && !state.userPinnedConv && state.activeConvId) {
          if (!(state.hasSession && !state.isClosed)) {
            state.hostConvId = '';
            state.activeConvId = '';
            resetConversationViewState();
            renderAll();
          }
        }
        if (forceNotify) toast(tKey('empty.syncNoMatch'));
      } catch (_) {
        if (forceNotify) toast(tKey('empty.syncNoMatch'));
      }
      return false;
    })();
    try {
      return await hostSyncInFlight;
    } finally {
      hostSyncInFlight = null;
    }
  }

  async function syncWithHostAndStatus() {
    const switched = await syncHostContextOnly(false);
    if (!switched) await refreshStatus();
  }

  async function refreshStatus() {
    const requestedCid = state.activeConvId || '';
    try {
      const data = await fetchStatusForConv(requestedCid);
      applySnapshot(data, requestedCid);
    } catch (err) {
      if (err && Number(err.status) === 403) {
        if (state.ws) {
          const prevWs = state.ws;
          state.ws = null;
          try { prevWs.close(); } catch (_) {}
        }
        state.userPinnedConv = false;
        state.pinnedConvId = null;
        state.activeConvId = state.hostConvId && state.hostConvId !== requestedCid ? state.hostConvId : '';
        resetConversationViewState();
        renderHeaderAndVisibility();
      }
      try {
        const listData = await apiGet('/api/conversations');
        if (Array.isArray(listData?.conversations)) {
          state.conversations = listData.conversations;
          renderHeaderAndVisibility();
        }
      } catch (_) {}
      if (err && Number(err.status) === 403 && err.message) {
        toast(err.message);
      }
    }
  }

  function applyIncrementalWsMsg(msg) {
    if (!msg || typeof msg !== 'object') return false;
    let touched = false;
    const prevRunIndex = state.runIndex;
    const tt = msg.thinkTank && typeof msg.thinkTank === 'object' ? msg.thinkTank : null;
    if (tt) {
      touched = true;
      state.project = 'project' in tt ? (tt.project ?? '') : state.project;
      state.directive = 'directive' in tt ? (tt.directive ?? '') : state.directive;
      state.phase = 'phase' in tt ? (tt.phase ?? '') : state.phase;
      state.status = 'status' in tt ? (tt.status ?? 'DISCONNECTED') : state.status;
      if (tt.progress !== undefined) state.progress = Number(tt.progress || 0);
      if (tt.round !== undefined) state.round = Number(tt.round || 1);
      if (tt.maxRounds !== undefined) state.maxRounds = Number(tt.maxRounds || 7);
      if (tt.runIndex !== undefined) state.runIndex = Number(tt.runIndex || 1);
      if (tt.roleCaps) state.roleCaps = tt.roleCaps;
      if ('triageDecision' in tt) state.triageDecision = tt.triageDecision;
      if ('closureReceipt' in tt) state.closureReceipt = tt.closureReceipt;
      state.hasSession = computeHasSession({ ...msg, thinkTank: tt, messages: msg.messages ?? state.messages, subtasks: msg.subtasks ?? state.subtasks, findings: msg.findings ?? state.findings }, tt);
      if (tt.runIndex !== undefined && Number(tt.runIndex) !== prevRunIndex) {
        state.inspectorItem = null;
        state.selectedProposalOption = null;
      }
    }
    if (Array.isArray(msg.conversationsList)) {
      touched = true;
      state.conversations = msg.conversationsList;
    }
    if (msg.message && typeof msg.message === 'object') {
      touched = true;
      const incoming = msg.message;
      const idx = state.messages.findIndex((m) => (incoming.id && m.id === incoming.id) || (incoming.seq && m.seq === incoming.seq));
      if (idx >= 0) state.messages[idx] = incoming;
      else state.messages.push(incoming);
    }
    if (Array.isArray(msg.agents)) { touched = true; state.agents = msg.agents; }
    if (Array.isArray(msg.messages)) { touched = true; state.messages = msg.messages; }
    if (Array.isArray(msg.interactions)) { touched = true; state.interactions = msg.interactions; }
    if (Array.isArray(msg.findings)) { touched = true; state.findings = msg.findings; }
    if (Array.isArray(msg.fileLocks)) { touched = true; state.fileLocks = msg.fileLocks; }
    if (Array.isArray(msg.subtasks)) { touched = true; state.subtasks = msg.subtasks; }
    if (msg.originCounts && typeof msg.originCounts === 'object') { touched = true; state.originCounts = msg.originCounts; }
    if (msg.roleUsage && typeof msg.roleUsage === 'object') { touched = true; state.roleUsage = msg.roleUsage; }
    if (msg.telemetryEntry && typeof msg.telemetryEntry === 'object') {
      const calls = Array.isArray(state.telemetry?.toolCalls) ? state.telemetry.toolCalls : [];
      state.telemetry = { ...(state.telemetry || {}), toolCalls: [msg.telemetryEntry, ...calls.filter((c) => c?.id !== msg.telemetryEntry.id)].slice(0, 25) };
    }
    if (msg.terminalLog && typeof msg.terminalLog === 'object') {
      const logs = Array.isArray(state.telemetry?.terminalLogs) ? state.telemetry.terminalLogs : [];
      state.telemetry = { ...(state.telemetry || {}), terminalLogs: [msg.terminalLog, ...logs.filter((l) => l?.id !== msg.terminalLog.id)].slice(0, 25) };
    }
    if (msg.backgroundTask && typeof msg.backgroundTask === 'object') {
      const tasks = Array.isArray(state.telemetry?.backgroundTasks) ? state.telemetry.backgroundTasks : [];
      const idxT = tasks.findIndex((t) => t?.id === msg.backgroundTask.id);
      const nextTasks = idxT >= 0 ? tasks.map((t, i) => (i === idxT ? msg.backgroundTask : t)) : [msg.backgroundTask, ...tasks];
      state.telemetry = { ...(state.telemetry || {}), backgroundTasks: nextTasks };
    }
    if (msg.telemetry && typeof msg.telemetry === 'object') state.telemetry = msg.telemetry;
    if ('proposal' in msg) { touched = true; state.proposal = msg.proposal; }
    if ('review' in msg) { touched = true; state.review = msg.review; }
    if ('closureReceipt' in msg) { touched = true; state.closureReceipt = msg.closureReceipt; }
    if (!touched) return false;

    dataRevision += 1;
    lastSnapshotHash = '';

    const statusUpper = String(tt?.status || state.status || '').toUpperCase();
    state.isClosed = Boolean(msg.isClosed || tt?.isClosed || statusUpper === 'COMPLETED' || statusUpper === 'DONE' || statusUpper === 'CLOSED');
    if (state.replayLive) state.replaySeq = getMaxRecordedSeq();
    return true;
  }

  function connectWebSocket() {
    if (state.ws && (state.ws.readyState === WebSocket.OPEN || state.ws.readyState === WebSocket.CONNECTING)) return;
    const convId = state.activeConvId || 'default';
    const requestedWsCid = convId;
    try {
      const params = new URLSearchParams({ convId });
      if (state.wsGeneration && state.lastSeenSeq > 0) {
        params.set('generation', state.wsGeneration);
        params.set('afterSeq', String(state.lastSeenSeq));
      }
      const ws = new WebSocket(`ws://127.0.0.1:8780/ws?${params.toString()}`);
      state.ws = ws;
      ws.onopen = () => {
        if (state.ws !== ws) return;
        state.connected = true;
        stopFallbackPoll();
        renderHeaderAndVisibility();
      };
      ws.onmessage = (ev) => {
        if (state.ws !== ws) return;
        try {
          const msg = JSON.parse(ev.data);
          const isWildcardActive = !state.activeConvId || state.activeConvId === 'default';
          const isWsParentResolved = Boolean(
            !state.userPinnedConv
            && requestedWsCid
            && requestedWsCid === state.activeConvId
            && msg.convId
            && msg.parentConvId
            && msg.convId === msg.parentConvId
          );
          if (msg.convId && !isWildcardActive && msg.convId !== state.activeConvId && msg.parentConvId !== state.activeConvId && !isWsParentResolved) return;
          if (isWsParentResolved && msg.convId !== state.activeConvId) {
            state.activeConvId = msg.convId;
          }
          if (msg.generation) state.wsGeneration = msg.generation;

          if (msg.type === 'SYNC_READY') {
            if (Number(msg.seq || 0) > state.lastSeenSeq) refreshStatus();
            return;
          }
          if (msg.type === 'SYNC_SNAPSHOT') {
            if (msg.seq) state.lastSeenSeq = Number(msg.seq);
            if (Array.isArray(msg.conversationsList)) state.conversations = msg.conversationsList;
            if (msg.snapshot) {
              applySnapshot({
                ...msg.snapshot,
                convId: msg.convId || msg.snapshot.id || msg.snapshot.convId,
                parentConvId: msg.parentConvId || msg.snapshot.parentConvId || msg.convId,
                hasSession: typeof msg.hasSession === 'boolean' ? msg.hasSession : msg.snapshot.hasSession,
                isClosed: typeof msg.isClosed === 'boolean' ? msg.isClosed : msg.snapshot.isClosed,
                conversationsList: Array.isArray(msg.conversationsList) ? msg.conversationsList : msg.snapshot.conversationsList,
                sync: { seq: msg.seq, generation: msg.generation },
              }, requestedWsCid);
            } else {
              refreshStatus();
            }
            return;
          }
          if (msg.type === 'SYNC_REPLAY') {
            if (msg.seq) state.lastSeenSeq = Number(msg.seq);
            const events = Array.isArray(msg.events) ? msg.events : [];
            if (events.length) {
              let appliedAny = false;
              for (const replayed of events) {
                if (applyIncrementalWsMsg(replayed)) appliedAny = true;
              }
              if (appliedAny) renderAll();
              else refreshStatus();
            }
            return;
          }

          const incomingSeq = Number(msg.seq || 0);
          if (incomingSeq > 0 && state.lastSeenSeq > 0 && incomingSeq > state.lastSeenSeq + 1) {
            state.lastSeenSeq = incomingSeq;
            refreshStatus();
            return;
          }
          if (incomingSeq > state.lastSeenSeq) state.lastSeenSeq = incomingSeq;

          if (msg.type === 'TELEMETRY_UPDATE') {
            applyIncrementalWsMsg(msg);
            return;
          }

          if (msg.type === 'SNAPSHOT') {
            applySnapshot(msg, requestedWsCid);
          } else if (applyIncrementalWsMsg(msg)) {
            renderAll();
          } else {
            refreshStatus();
          }
        } catch (_) {}
      };
      ws.onclose = () => {
        if (state.ws !== ws) return;
        state.connected = false;
        renderHeaderAndVisibility();
        startFallbackPoll();
        clearTimeout(state.reconnectTimer);
        state.reconnectTimer = setTimeout(connectWebSocket, 3000);
      };
      ws.onerror = () => {
        if (state.ws === ws) ws.close();
      };
    } catch (_) {
      state.connected = false;
      startFallbackPoll();
    }
  }

  function stepReplay(delta) {
    const events = buildRecordedEvents();
    if (!events.length) return;
    clearInterval(state.replayTimer);
    state.replayTimer = null;
    state.replayLive = false;
    let idx = events.findIndex((ev) => ev.seq >= state.replaySeq);
    if (idx < 0) idx = events.length - 1;
    const nextIdx = Math.max(0, Math.min(events.length - 1, idx + delta));
    state.replaySeq = events[nextIdx].seq;
    renderMap();
  }

  function toggleReplayPlay() {
    if (state.replayTimer) {
      clearInterval(state.replayTimer);
      state.replayTimer = null;
      renderMap();
      return;
    }
    const events = buildRecordedEvents();
    const maxSeq = events.length ? events[events.length - 1].seq : 0;
    if (!maxSeq) return;
    state.replayLive = false;
    if (state.replaySeq >= maxSeq) state.replaySeq = 0;
    state.replayTimer = setInterval(() => {
      const next = events.find((ev) => ev.seq > state.replaySeq);
      if (!next) {
        clearInterval(state.replayTimer);
        state.replayTimer = null;
        state.replayLive = true;
      } else {
        state.replaySeq = next.seq;
      }
      renderMap();
    }, state.replaySpeed || 700);
    renderMap();
  }

  function setInlineFeedback(sel, msg, isError = false) {
    const el = $(sel);
    if (!el) return;
    el.textContent = msg;
    el.classList.toggle('is-error', isError);
    el.classList.remove('hidden');
  }

  async function submitUserMessage(e) {
    if (e) e.preventDefault();
    const input = $('#composer-input');
    const text = (input?.value || '').trim();
    if (!text) return;
    const target = $('#composer-target')?.value || 'ALL';
    try {
      await apiPost('/api/chat/send', {
        convId: state.activeConvId,
        channel: 'MAIN',
        origin: 'user',
        isOperator: true,
        senderCode: 'USER',
        senderRole: 'user',
        senderName: tKey('flow.composer.senderYou'),
        recipientCode: target.toUpperCase(),
        recipientRole: target,
        recipientName: target === 'ALL' ? tKey('flow.composer.targetTeam') : roleLabel(target),
        content: text,
      });
      input.value = '';
      await refreshStatus();
    } catch (err) {
      toast(err.message || tKey('app.sendError'));
    }
  }

  function wireEvents() {
    $('#theme-toggle')?.addEventListener('click', () => {
      applyTheme(state.theme === 'dark' ? 'light' : 'dark');
    });

    $('#language-toggle')?.addEventListener('click', () => {
      applyLang(state.language === 'fa' ? 'en' : 'fa');
    });

    $('#btn-settings-sheet')?.addEventListener('click', () => toggleSettingsSheet(true));
    $('#btn-close-settings')?.addEventListener('click', () => toggleSettingsSheet(false));
    $('#settings-backdrop')?.addEventListener('click', () => toggleSettingsSheet(false));
    $('#btn-close-inspector')?.addEventListener('click', closeInspector);

    $('#conv-search-input')?.addEventListener('input', (e) => {
      state.convSearchQuery = e.target.value || '';
      renderHeaderAndVisibility();
    });

    $('#conv-switcher')?.addEventListener('change', async (e) => {
      const nextCid = e.target.value;
      const pinned = Boolean(nextCid && state.hostConvId && nextCid !== state.hostConvId);
      await switchConversation(nextCid, pinned);
    });

    $('#run-history-pills')?.addEventListener('click', async (e) => {
      const pill = e.target instanceof Element ? e.target.closest('.run-pill[data-run-conv]') : null;
      if (!pill) return;
      const nextCid = pill.dataset.runConv;
      const pinned = Boolean(nextCid && state.hostConvId && nextCid !== state.hostConvId);
      await switchConversation(nextCid, pinned);
    });

    $('#btn-new-run')?.addEventListener('click', async () => {
      const baseCid = (state.activeConvId || state.hostConvId || '').split('--run-')[0];
      if (!baseCid) return;
      try {
        state.activeConvId = baseCid;
        state.userPinnedConv = false;
        state.pinnedConvId = null;
        resetConversationViewState();
        if (state.ws) {
          const prevWs = state.ws;
          state.ws = null;
          try { prevWs.close(); } catch (_) {}
        }
        await apiPost('/api/task/update', {
          convId: baseCid,
          newRun: true,
          status: 'ACTIVE',
          progress: 5,
        });
        await refreshStatus();
        connectWebSocket();
      } catch (err) {
        toast(err.message || tKey('app.sendError'));
      }
    });

    const roleTooltipEl = $('#role-hover-tooltip');
    let activeTooltipTarget = null;
    const positionRoleTooltip = (target, clientX, clientY) => {
      if (!roleTooltipEl || !target) return;
      const rect = target.getBoundingClientRect();
      const tipW = roleTooltipEl.offsetWidth || 180;
      const tipH = roleTooltipEl.offsetHeight || 28;
      const anchorX = Number.isFinite(clientX) && clientX > 0 ? clientX + 12 : rect.left + rect.width / 2 - tipW / 2;
      const anchorY = Number.isFinite(clientY) && clientY > 0 ? clientY - tipH - 12 : rect.top - tipH - 8;
      const clampedX = Math.max(8, Math.min(window.innerWidth - tipW - 8, anchorX));
      const clampedY = anchorY < 8 ? Math.min(window.innerHeight - tipH - 8, rect.bottom + 8) : Math.min(window.innerHeight - tipH - 8, anchorY);
      roleTooltipEl.style.left = `${Math.round(clampedX)}px`;
      roleTooltipEl.style.top = `${Math.round(clampedY)}px`;
    };
    const showRoleTooltip = (target, clientX, clientY) => {
      if (!roleTooltipEl || !target) return;
      const text = target.getAttribute('data-role-tooltip');
      if (!text) return;
      activeTooltipTarget = target;
      roleTooltipEl.textContent = text;
      roleTooltipEl.classList.remove('hidden');
      roleTooltipEl.setAttribute('aria-hidden', 'false');
      positionRoleTooltip(target, clientX, clientY);
    };
    const hideRoleTooltip = () => {
      if (!roleTooltipEl) return;
      activeTooltipTarget = null;
      roleTooltipEl.classList.add('hidden');
      roleTooltipEl.setAttribute('aria-hidden', 'true');
    };
    document.addEventListener('pointerover', (e) => {
      const target = e.target instanceof Element ? e.target.closest('[data-role-tooltip]') : null;
      if (!target) return;
      showRoleTooltip(target, e.clientX, e.clientY);
    });
    document.addEventListener('pointermove', (e) => {
      if (!activeTooltipTarget) return;
      const target = e.target instanceof Element ? e.target.closest('[data-role-tooltip]') : null;
      if (target === activeTooltipTarget) positionRoleTooltip(target, e.clientX, e.clientY);
    });
    document.addEventListener('pointerout', (e) => {
      if (!activeTooltipTarget) return;
      const next = e.relatedTarget instanceof Element ? e.relatedTarget.closest('[data-role-tooltip]') : null;
      if (!next || next !== activeTooltipTarget) hideRoleTooltip();
    });
    document.addEventListener('focusin', (e) => {
      const target = e.target instanceof Element ? e.target.closest('[data-role-tooltip]') : null;
      if (target) showRoleTooltip(target);
    });
    document.addEventListener('focusout', (e) => {
      if (!activeTooltipTarget) return;
      const next = e.relatedTarget instanceof Element ? e.relatedTarget.closest('[data-role-tooltip]') : null;
      if (!next) hideRoleTooltip();
    });
    window.addEventListener('scroll', hideRoleTooltip, true);
    document.addEventListener('keydown', (e) => {
      if (e.key === 'Escape') hideRoleTooltip();
    });

    $('#btn-init-session')?.addEventListener('click', async () => {
      const targetCid = state.activeConvId || state.hostConvId;
      if (!targetCid) return;
      try {
        await apiPost('/api/task/update', {
          convId: targetCid,
          project: 'ThinkTank Case',
          directive: tKey('flow.empty.initDirective'),
          status: 'ACTIVE',
          progress: 5,
        });
        state.hasSession = true;
        await refreshStatus();
      } catch (err) {
        toast(err.message || tKey('app.sendError'));
      }
    });

    $('#btn-sync-host-session')?.addEventListener('click', async () => {
      state.userPinnedConv = false;
      state.pinnedConvId = null;
      const switched = await syncHostContextOnly(true);
      if (!switched) await refreshStatus();
    });

    $('#empty-active-sessions')?.addEventListener('click', async (e) => {
      const btn = e.target instanceof Element ? e.target.closest('.empty-session-item[data-switch-conv]') : null;
      if (!btn) return;
      await switchConversation(btn.dataset.switchConv, true);
    });

    window.addEventListener('focus', () => {
      if (!state.userPinnedConv) syncHostContextOnly(false);
    });
    document.addEventListener('visibilitychange', () => {
      if (!document.hidden && !state.userPinnedConv) syncHostContextOnly(false);
    });

    const tabs = $$('.primary-nav .nav-tab');
    for (const btn of tabs) {
      btn.addEventListener('click', () => activateTab(btn.dataset.tab));
      btn.addEventListener('keydown', (e) => {
        const idx = tabs.indexOf(btn);
        let next = -1;
        if (e.key === 'ArrowRight') next = (idx + 1) % tabs.length;
        else if (e.key === 'ArrowLeft') next = (idx - 1 + tabs.length) % tabs.length;
        else if (e.key === 'Home') next = 0;
        else if (e.key === 'End') next = tabs.length - 1;
        if (next >= 0) {
          e.preventDefault();
          tabs[next].focus();
          activateTab(tabs[next].dataset.tab);
        }
      });
    }

    $('#tab-flow')?.addEventListener('click', async (e) => {
      if (e.target.closest('#btn-jump-decision')) {
        $('#decision-box')?.scrollIntoView({ behavior: 'smooth', block: 'center' });
        return;
      }

      if (e.target.closest('#btn-receipt-replay')) {
        activateTab('map');
        state.replayLive = false;
        const evs = buildRecordedEvents();
        state.replaySeq = evs.length ? evs[0].seq : 0;
        renderMap();
        return;
      }

      if (e.target.closest('#btn-receipt-reopen-case')) {
        try {
          await apiPost('/api/task/update', {
            convId: state.activeConvId,
            reopen: true,
            status: 'ACTIVE',
          });
          await refreshStatus();
        } catch (err) {
          toast(err.message || tKey('app.sendError'));
        }
        return;
      }

      if (e.target.closest('#btn-receipt-new-case')) {
        state.pendingResetCase = true;
        toggleSettingsSheet(true);
        $('#input-project')?.focus();
        return;
      }

      const fSeg = e.target.closest('[data-finding-state]');
      if (fSeg) {
        const st = fSeg.dataset.findingState;
        state.findingFilter = state.findingFilter === st ? null : st;
        renderProgressBars();
        renderFindingsSection();
        signatures.flow = computeFlowSignature();
        return;
      }

      if (e.target.closest('#btn-clear-finding-filter')) {
        state.findingFilter = null;
        renderProgressBars();
        renderFindingsSection();
        signatures.flow = computeFlowSignature();
        return;
      }

      const wSeg = e.target.closest('[data-wbs-state]');
      if (wSeg) {
        const st = wSeg.dataset.wbsState;
        state.wbsFilter = state.wbsFilter === st ? null : st;
        renderProgressBars();
        renderWbsSection();
        signatures.flow = computeFlowSignature();
        return;
      }

      if (e.target.closest('#btn-clear-wbs-filter')) {
        state.wbsFilter = null;
        renderProgressBars();
        renderWbsSection();
        signatures.flow = computeFlowSignature();
        return;
      }

      const pinBtn = e.target.closest('.finding-pin-btn');
      if (pinBtn) {
        e.stopPropagation();
        const findingId = pinBtn.dataset.findingId;
        try {
          await apiPost('/api/findings/action', {
            convId: state.activeConvId,
            findingId,
            action: 'mark_important',
          });
          await refreshStatus();
        } catch (err) {
          toast(err.message || tKey('app.sendError'));
        }
        return;
      }

      const fCard = e.target.closest('.finding-card[data-finding-id]');
      if (fCard) {
        openInspector({ type: 'finding', id: fCard.dataset.findingId });
        return;
      }

      const ledgerRow = e.target.closest('.ledger-row[data-seq]');
      if (ledgerRow) {
        openInspector({ type: 'event', seq: Number(ledgerRow.dataset.seq) });
        return;
      }

      const optBtn = e.target.closest('.proposal-opt-btn');
      if (optBtn && state.proposal) {
        state.selectedProposalOption = optBtn.dataset.optId;
        try {
          await apiPost('/api/proposal/action', {
            convId: state.activeConvId,
            proposalId: state.proposal.id,
            action: 'select_option',
            optionId: state.selectedProposalOption,
          });
          await refreshStatus();
        } catch (err) {
          toast(err.message);
        }
        return;
      }

      const revDecBtn = e.target.closest('.review-dec-btn[data-decision]');
      if (revDecBtn && state.review) {
        const decision = revDecBtn.dataset.decision;
        const note = ($('#review-decision-note')?.value || '').trim();
        try {
          await apiPost('/api/governance/review_decision', {
            convId: state.activeConvId,
            decision,
            note,
          });
          await refreshStatus();
        } catch (err) {
          toast(err.message || tKey('app.sendError'));
        }
        return;
      }

      const actBtn = e.target.closest('.proposal-act-btn');
      if (actBtn && state.proposal) {
        const act = actBtn.dataset.act;
        if (act === 'open_revision') {
          state.revisionDraftOpen = true;
          signatures.flow = '';
          renderFlow();
          $('#proposal-revision-note')?.focus();
          return;
        }
        if (act === 'cancel_revision') {
          state.revisionDraftOpen = false;
          signatures.flow = '';
          renderFlow();
          return;
        }
        let comment = '';
        if (act === 'request_revision') {
          comment = ($('#proposal-revision-note')?.value || '').trim();
        }
        try {
          await apiPost('/api/proposal/action', {
            convId: state.activeConvId,
            proposalId: state.proposal.id,
            action: act,
            optionId: state.selectedProposalOption || state.proposal?.userDecision?.optionId || state.proposal?.selectedOptionId || null,
            comment,
          });
          state.revisionDraftOpen = false;
          await refreshStatus();
        } catch (err) {
          toast(err.message);
        }
      }
    });

    $('#tab-flow')?.addEventListener('keydown', (e) => {
      if (e.key !== 'Enter' && e.key !== ' ') return;
      if (e.target.closest('.finding-pin-btn, button, a, input, select, textarea, summary')) return;
      const fCard = e.target.closest('.finding-card[data-finding-id]');
      if (fCard) {
        e.preventDefault();
        openInspector({ type: 'finding', id: fCard.dataset.findingId });
        return;
      }
      const ledgerRow = e.target.closest('.ledger-row[data-seq]');
      if (ledgerRow) {
        e.preventDefault();
        openInspector({ type: 'event', seq: Number(ledgerRow.dataset.seq) });
      }
    });

    for (const chBtn of $$('#event-ledger-section .channel-bar .chip-btn')) {
      chBtn.addEventListener('click', () => {
        state.boardChannel = chBtn.dataset.channel || 'ALL';
        renderEventLedger();
        signatures.flow = computeFlowSignature();
      });
    }

    $('#board-search')?.addEventListener('input', (e) => {
      state.boardSearchQuery = e.target.value || '';
      renderEventLedger();
      signatures.flow = computeFlowSignature();
    });

    $('#user-composer-form')?.addEventListener('submit', submitUserMessage);
    $('#composer-input')?.addEventListener('keydown', (e) => {
      if (e.key === 'Enter' && (e.ctrlKey || e.metaKey)) {
        e.preventDefault();
        submitUserMessage();
      }
    });

    for (const sBtn of $$('#map-subview-toggle .seg-btn')) {
      sBtn.addEventListener('click', () => {
        state.mapSubview = sBtn.dataset.subview === 'network' ? 'network' : 'sequence';
        renderMap();
      });
    }

    $('#sequence-diagram-canvas')?.addEventListener('click', (e) => {
      const row = e.target.closest('.seq-event-row[data-seq]');
      if (!row) return;
      openInspector({ type: 'event', seq: Number(row.dataset.seq) });
    });

    $('#sequence-diagram-canvas')?.addEventListener('keydown', (e) => {
      if (e.key !== 'Enter' && e.key !== ' ') return;
      const row = e.target.closest('.seq-event-row[data-seq]');
      if (!row) return;
      e.preventDefault();
      openInspector({ type: 'event', seq: Number(row.dataset.seq) });
    });

    const openEdgeFromTarget = (el) => {
      const edgeEl = el?.closest('[data-from][data-to]');
      if (!edgeEl) return false;
      openInspector({ type: 'edge', from: edgeEl.dataset.from, to: edgeEl.dataset.to });
      return true;
    };

    $('#swarm-interaction-svg')?.addEventListener('click', (e) => openEdgeFromTarget(e.target));
    $('#swarm-interaction-svg')?.addEventListener('keydown', (e) => {
      if ((e.key === 'Enter' || e.key === ' ') && openEdgeFromTarget(e.target)) {
        e.preventDefault();
      }
    });
    $('#comm-table-wrap')?.addEventListener('click', (e) => openEdgeFromTarget(e.target));
    $('#comm-table-wrap')?.addEventListener('keydown', (e) => {
      if ((e.key === 'Enter' || e.key === ' ') && openEdgeFromTarget(e.target)) {
        e.preventDefault();
      }
    });
    $('#case-inspector-body')?.addEventListener('click', (e) => {
      const linkBtn = e.target.closest('.edge-event-link[data-seq]');
      if (!linkBtn) return;
      openInspector({ type: 'event', seq: Number(linkBtn.dataset.seq) });
    });

    $('#graph-step-prev')?.addEventListener('click', () => stepReplay(-1));
    $('#graph-step-next')?.addEventListener('click', () => stepReplay(1));
    $('#graph-replay-play')?.addEventListener('click', toggleReplayPlay);
    $('#graph-replay-speed')?.addEventListener('change', (e) => {
      state.replaySpeed = Number(e.target.value || 700);
    });
    $('#graph-replay-slider')?.addEventListener('input', (e) => {
      state.replayLive = false;
      state.replaySeq = Number(e.target.value || 0);
      clearInterval(state.replayTimer);
      state.replayTimer = null;
      renderMap();
    });
    $('#graph-replay-live')?.addEventListener('click', () => {
      state.replayLive = true;
      clearInterval(state.replayTimer);
      state.replayTimer = null;
      renderMap();
    });

    document.addEventListener('keydown', (e) => {
      if (e.key === 'Tab' && state.settingsOpen) {
        const sheet = $('#settings-sheet');
        const focusables = [...(sheet?.querySelectorAll('button:not([disabled]), input:not([disabled]), select:not([disabled]), textarea:not([disabled]), [href], [tabindex]:not([tabindex="-1"])') || [])]
          .filter((el) => el.offsetParent !== null);
        if (focusables.length) {
          const first = focusables[0];
          const last = focusables[focusables.length - 1];
          if (e.shiftKey && document.activeElement === first) {
            e.preventDefault();
            last.focus();
          } else if (!e.shiftKey && (document.activeElement === last || !sheet.contains(document.activeElement))) {
            e.preventDefault();
            first.focus();
          }
        }
        return;
      }
      if (e.key === 'Escape' && state.settingsOpen) {
        toggleSettingsSheet(false);
        return;
      }
      if (e.key === 'Escape' && state.inspectorItem) {
        closeInspector();
        return;
      }
      if (state.activeTab !== 'map' || state.settingsOpen) return;
      const tag = document.activeElement?.tagName;
      if (tag === 'INPUT' || tag === 'TEXTAREA' || tag === 'SELECT' || document.activeElement?.isContentEditable) return;

      const isRtl = document.documentElement.dir === 'rtl';
      if (e.code === 'Space') {
        e.preventDefault();
        toggleReplayPlay();
      } else if (e.key === 'ArrowLeft') {
        e.preventDefault();
        stepReplay(isRtl ? 1 : -1);
      } else if (e.key === 'ArrowRight') {
        e.preventDefault();
        stepReplay(isRtl ? -1 : 1);
      } else if (e.key === 'l' || e.key === 'L') {
        e.preventDefault();
        state.replayLive = true;
        clearInterval(state.replayTimer);
        state.replayTimer = null;
        renderMap();
      }
    });

    for (const tBtn of $$('#tab-team .tier-filters .chip-btn')) {
      tBtn.addEventListener('click', () => {
        state.teamTier = tBtn.dataset.tier || 'all';
        renderTeam();
      });
    }

    $('#tab-team')?.addEventListener('click', (e) => {
      const btn = e.target.closest('.agent-chat-btn[data-id]');
      if (!btn || btn.disabled || state.isClosed) return;
      activateTab('flow');
      if ($('#composer-target')) $('#composer-target').value = btn.dataset.id;
      $('#composer-input')?.focus();
    });

    $('#session-form')?.addEventListener('submit', async (e) => {
      e.preventDefault();
      try {
        const resetting = Boolean(state.pendingResetCase);
        const payload = {
          convId: state.activeConvId,
          project: $('#input-project')?.value?.trim() || state.project,
          directive: $('#input-directive')?.value?.trim() || state.directive,
          status: (resetting || !state.isClosed) ? 'ACTIVE' : 'COMPLETED',
        };
        if (resetting) {
          payload.resetCase = true;
          payload.round = 1;
          payload.progress = 5;
        }
        await apiPost('/api/task/update', payload);
        state.pendingResetCase = false;
        setInlineFeedback('#session-save-feedback', tKey('app.saved'));
        await refreshStatus();
      } catch (err) {
        setInlineFeedback('#session-save-feedback', err.message || tKey('app.sendError'), true);
      }
    });

    $('#btn-Complete-Case')?.addEventListener('click', async () => {
      const forceWrap = $('#force-close-wrap');
      const forceReason = ($('#input-force-reason')?.value || '').trim();
      const payload = {
        convId: state.activeConvId,
        status: 'COMPLETED',
        progress: 100,
      };
      if (forceWrap && !forceWrap.classList.contains('hidden') && forceReason) {
        payload.forceClose = true;
        payload.forceReason = forceReason;
      }
      try {
        await apiPost('/api/task/update', payload);
        if (forceWrap) forceWrap.classList.add('hidden');
        setInlineFeedback('#session-save-feedback', tKey('receipt.title'));
        await refreshStatus();
        toggleSettingsSheet(false);
      } catch (err) {
        if (err.status === 409 && forceWrap) forceWrap.classList.remove('hidden');
        setInlineFeedback('#session-save-feedback', err.message || tKey('app.sendError'), true);
      }
    });

    $('#caps-form')?.addEventListener('submit', async (e) => {
      e.preventDefault();
      const clampCap = (sel) => Math.max(1, Math.min(500, Number($(sel)?.value || 50) || 50));
      try {
        await apiPost('/api/task/update', {
          convId: state.activeConvId,
          roleCaps: {
            main: clampCap('#cap-main'),
            manager: clampCap('#cap-manager'),
            subagents: clampCap('#cap-subagents'),
          },
        });
        setInlineFeedback('#caps-save-feedback', tKey('app.saved'));
        await refreshStatus();
      } catch (err) {
        setInlineFeedback('#caps-save-feedback', err.message || tKey('app.sendError'), true);
      }
    });

    $('#btn-extend-rounds')?.addEventListener('click', async () => {
      try {
        await apiPost('/api/governance/extend_rounds', { additionalRounds: 3, convId: state.activeConvId });
        setInlineFeedback('#session-save-feedback', tKey('app.saved'));
        await refreshStatus();
      } catch (err) {
        setInlineFeedback('#session-save-feedback', err.message || tKey('app.sendError'), true);
      }
    });

    $('#btn-reconnect')?.addEventListener('click', () => {
      if (state.ws) state.ws.close();
      connectWebSocket();
      refreshStatus();
    });

    $('#dev-mode-toggle')?.addEventListener('change', (e) => {
      state.devMode = Boolean(e.target.checked);
      localStorage.setItem('thinktank-dev-mode', state.devMode ? 'true' : 'false');
      renderAll();
    });

    $('#raw-kind-select')?.addEventListener('change', (e) => {
      state.rawKind = e.target.value;
      renderRawInspector();
    });

    $('#raw-copy-btn')?.addEventListener('click', async () => {
      try {
        await navigator.clipboard.writeText($('#raw-json-viewer')?.textContent || '');
        const btn = $('#raw-copy-btn');
        if (btn) btn.textContent = tKey('settings.rawCopied');
      } catch (_) {}
    });

    let resizeTimer = null;
    window.addEventListener('resize', () => {
      clearTimeout(resizeTimer);
      resizeTimer = setTimeout(() => {
        if (state.hasSession && state.activeTab === 'map') renderMap();
      }, 120);
    });
  }

  async function init() {
    applyTheme(state.theme);
    applyLang(state.language);
    wireEvents();

    const rolesPromise = apiGet('/api/roles')
      .then((rolesData) => {
        if (Array.isArray(rolesData?.roles)) state.roles = rolesData.roles;
        else if (Array.isArray(rolesData)) state.roles = rolesData;
      })
      .catch(() => {});

    const wsPromise = (async () => {
      try {
        if (window.sidecar?.getWorkspaceUris) {
          const uris = await Promise.race([
            window.sidecar.getWorkspaceUris(),
            new Promise((resolve) => setTimeout(() => resolve([]), 200)),
          ]);
          if (Array.isArray(uris) && typeof uris[0] === 'string') {
            state.workspaceUri = uris[0].trim();
          }
        }
        if (window.sidecar?.onWorkspaceChange) {
          window.sidecar.onWorkspaceChange((uris) => {
            const nextUri = Array.isArray(uris) && typeof uris[0] === 'string' ? uris[0].trim() : '';
            if (nextUri !== state.workspaceUri) {
              state.workspaceUri = nextUri;
              if (!state.userPinnedConv) syncHostContextOnly(false);
            }
          });
        }
      } catch (_) {}
    })();

    await Promise.allSettled([rolesPromise, wsPromise]);

    let ctx = null;
    try {
      ctx = await apiGet(getHostContextPath());
    } catch (_) {}
    const initialHostCid = resolveHostConvId(ctx);
    if (initialHostCid) {
      state.hostConvId = initialHostCid;
      state.activeConvId = initialHostCid;
    }

    connectWebSocket();
    startHostContextWatch();
    await refreshStatus();
  }

  init();
})();
