import { buildGraphFromInteractions, createCaseStore } from './store.mjs';
import { createSyncClient } from './sync.mjs';
import { dirForLang, formatNum, normalizeLang, t } from './i18n.mjs';
import { setAttr, setText } from './dom.mjs';
import { patchCommandPulse, renderCommandBoard } from './boards/command-board.mjs';
import { patchTopologyPulse, renderTopologyBoard } from './boards/topology-board.mjs';
import { renderChronicleBoard } from './boards/chronicle-board.mjs';
import { renderSquadBoard } from './boards/squad-board.mjs';
import { renderDossierDrawer, renderSettingsSheet } from './inspector.mjs';

const BOARDS = ['command', 'topology', 'chronicle', 'squad'];

function safeStorageGet(key, fallback) {
  try {
    return globalThis.localStorage?.getItem(key) || fallback;
  } catch (_) {
    return fallback;
  }
}

function safeStorageSet(key, val) {
  try {
    globalThis.localStorage?.setItem(key, val);
  } catch (_) {}
}

function resolveInitialContext() {
  const win = globalThis.window || {};
  const hostCtx = win.__ANTIGRAVITY_HOST_CONTEXT__ || {};
  const sidecarObj = win.sidecar || {};
  let qp = null;
  try {
    qp = win.location?.search ? new URLSearchParams(win.location.search) : null;
  } catch (_) {}
  const convId = String(
    qp?.get('convId') || qp?.get('conversationId')
    || sidecarObj.convId || sidecarObj.conversationId
    || hostCtx.convId || hostCtx.conversationId || '',
  ).trim();
  const projectId = String(
    qp?.get('projectId') || sidecarObj.projectId || hostCtx.projectId || '',
  ).trim();
  const workspaceUri = String(
    qp?.get('workspaceUri') || sidecarObj.workspaceUri || hostCtx.workspaceUri || '',
  ).trim();
  return { convId, projectId, workspaceUri };
}

function getDistinctSeqs(state) {
  const set = new Set([0]);
  for (const it of state.interactions || []) {
    const s = Number(it?.seq || 0);
    if (s > 0) set.add(s);
  }
  const maxSeq = Number(state.seq || 0);
  if (maxSeq > 0) set.add(maxSeq);
  return Array.from(set).sort((a, b) => a - b);
}

export function initThinkTankStudio(doc = globalThis.document) {
  if (!doc) return null;

  const stripPreloadBodyStyles = () => {
    if (doc.body?.style) {
      doc.body.style.removeProperty('background');
      doc.body.style.removeProperty('color');
      doc.body.style.removeProperty('font-family');
    }
  };
  stripPreloadBodyStyles();
  doc.addEventListener?.('DOMContentLoaded', stripPreloadBodyStyles);

  const ctx = resolveInitialContext();
  const lang = normalizeLang(safeStorageGet('tt_v4_lang', 'fa'));
  const theme = safeStorageGet('tt_v4_theme', 'dark') === 'light' ? 'light' : 'dark';
  const savedBoard = safeStorageGet('tt_v4_board', 'command');
  const activeBoard = BOARDS.includes(savedBoard) ? savedBoard : 'command';

  const store = createCaseStore({ ...ctx, lang, theme, activeBoard });
  const sync = createSyncClient({ store });

  const dom = {
    root: doc.documentElement,
    caseTitle: doc.getElementById('header-case-title'),
    connBadge: doc.getElementById('header-conn-badge'),
    runPills: doc.getElementById('header-run-pills'),
    btnNewRun: doc.getElementById('btn-new-run'),
    btnCaseSwitcher: doc.getElementById('btn-case-switcher'),
    btnLangToggle: doc.getElementById('btn-lang-toggle'),
    btnThemeToggle: doc.getElementById('btn-theme-toggle'),
    btnOpenSettings: doc.getElementById('btn-open-settings'),
    offlineBanner: doc.getElementById('offline-banner'),
    offlineText: doc.getElementById('offline-banner-text'),
    btnRetrySync: doc.getElementById('btn-retry-sync'),
    pipeSteps: Array.from(doc.querySelectorAll('#pipeline-steps .pipe-step')),
    metricRound: doc.getElementById('metric-round'),
    metricOpenFindings: doc.getElementById('metric-open-findings'),
    metricSeq: doc.getElementById('metric-seq'),
    tablist: doc.getElementById('board-tablist'),
    tabs: Array.from(doc.querySelectorAll('#board-tablist .tab-btn')),
    stateLoading: doc.getElementById('state-loading'),
    stateEmpty: doc.getElementById('state-empty'),
    emptyTitle: doc.getElementById('empty-title'),
    emptyDesc: doc.getElementById('empty-desc'),
    btnEmptyCreate: doc.getElementById('btn-empty-create'),
    btnEmptySync: doc.getElementById('btn-empty-sync'),
    emptyCreateForm: doc.getElementById('empty-create-form'),
    emptyProjectLabel: doc.getElementById('empty-project-label'),
    emptyProjectInput: doc.getElementById('empty-project-input'),
    emptyDirectiveLabel: doc.getElementById('empty-directive-label'),
    emptyDirectiveInput: doc.getElementById('empty-directive-input'),
    btnEmptySubmit: doc.getElementById('btn-empty-submit'),
    btnEmptyCancel: doc.getElementById('btn-empty-cancel'),
    emptyRecentWrap: doc.getElementById('empty-recent-wrap'),
    emptyRecentHeading: doc.getElementById('empty-recent-heading'),
    emptyRecentList: doc.getElementById('empty-recent-list'),
    workspace: doc.getElementById('studio-workspace'),
    panels: {
      command: doc.getElementById('panel-command'),
      topology: doc.getElementById('panel-topology'),
      chronicle: doc.getElementById('panel-chronicle'),
      squad: doc.getElementById('panel-squad'),
    },
    dossierDrawer: doc.getElementById('dossier-drawer'),
    settingsSheet: doc.getElementById('settings-sheet'),
    settingsDialog: doc.getElementById('settings-dialog'),
  };

  let replayTimer = null;
  function stopReplayTimer() {
    if (replayTimer) {
      clearInterval(replayTimer);
      replayTimer = null;
    }
  }

  function stepReplay(delta) {
    const seqs = getDistinctSeqs(store.state);
    if (seqs.length <= 1) return;
    const maxSeq = seqs[seqs.length - 1];
    const current = store.state.replay.active ? Number(store.state.replay.cursorSeq ?? maxSeq) : maxSeq;
    let idx = seqs.findIndex((s) => s >= current);
    if (idx < 0) idx = seqs.length - 1;
    const nextIdx = Math.max(0, Math.min(seqs.length - 1, idx + delta));
    const nextSeq = seqs[nextIdx];
    store.setUi({
      replay: { ...store.state.replay, active: true, cursorSeq: nextSeq },
    });
    if (nextIdx >= seqs.length - 1 && store.state.replay.playing) {
      stopReplayTimer();
      store.setUi({ replay: { ...store.state.replay, active: true, playing: false, cursorSeq: nextSeq } });
    }
  }

  function startReplayTimer() {
    stopReplayTimer();
    const speed = Number(store.state.replay.speed || 1);
    const intervalMs = Math.max(250, Math.round(900 / speed));
    replayTimer = setInterval(() => {
      if (!store.state.replay.playing) {
        stopReplayTimer();
        return;
      }
      stepReplay(1);
    }, intervalMs);
  }

  function applyReplayControl(control) {
    const seqs = getDistinctSeqs(store.state);
    const maxSeq = seqs[seqs.length - 1] || 0;
    if (control === 'live') {
      stopReplayTimer();
      store.setUi({ replay: { ...store.state.replay, active: false, playing: false, cursorSeq: null } });
      return;
    }
    if (control === 'prev') {
      stopReplayTimer();
      store.state.replay.playing = false;
      stepReplay(-1);
      return;
    }
    if (control === 'next') {
      stopReplayTimer();
      store.state.replay.playing = false;
      stepReplay(1);
      return;
    }
    if (control === 'play') {
      const nextPlaying = !store.state.replay.playing;
      if (!nextPlaying) {
        stopReplayTimer();
        store.setUi({ replay: { ...store.state.replay, playing: false } });
      } else {
        const cur = store.state.replay.active ? Number(store.state.replay.cursorSeq ?? 0) : 0;
        const startSeq = cur >= maxSeq ? 0 : cur;
        store.setUi({ replay: { ...store.state.replay, active: true, playing: true, cursorSeq: startSeq } });
        startReplayTimer();
      }
    }
  }

  async function refreshConversations() {
    const convs = await sync.getApi('/conversations');
    if (Array.isArray(convs?.conversations)) {
      store.state.conversationsList = convs.conversations;
      store.revs.headerRev += 1;
      scheduleRender();
    }
  }

  async function onAction(action) {
    if (!action || !action.type) return true;
    const cid = store.state.convId || 'default';

    switch (action.type) {
      case 'SET_FINDING_FILTER':
        store.setUi({ findingFilter: action.filter || 'ALL' });
        return true;
      case 'SET_WBS_FILTER':
        store.setUi({ wbsFilter: action.filter || 'ALL' });
        return true;
      case 'SET_CHRONICLE_VIEW':
        store.setUi({ chronicleView: action.view === 'feed' ? 'feed' : 'swimlane' });
        return true;
      case 'SET_CHRONICLE_CHANNEL':
        store.setUi({ chronicleChannel: action.channel || 'ALL' });
        return true;
      case 'SET_CHRONICLE_QUERY':
        store.setUi({ chronicleQuery: action.query || '' });
        return true;
      case 'SET_COMPOSER_TARGET':
        store.setUi({ composerTarget: action.target || 'all' });
        return true;
      case 'SET_SQUAD_FILTER':
        store.setUi({ squadFilter: action.filter || 'ALL' });
        return true;
      case 'INSPECT':
        store.setUi({ inspector: action.target || null });
        return true;
      case 'CLOSE_INSPECTOR':
        store.setUi({ inspector: null });
        return true;
      case 'CLOSE_SETTINGS':
        store.setUi({ settingsOpen: false, settingsError: '' });
        return true;
      case 'TOGGLE_DEV_MODE':
        store.setUi({ devMode: action.enabled ?? !store.state.devMode });
        return true;
      case 'TOPO_CLICK_NODE': {
        const nextFocus = store.state.topologyFocusNode === action.nodeId ? null : action.nodeId;
        store.setUi({ topologyFocusNode: nextFocus, topologySelectedEdge: null });
        return true;
      }
      case 'TOPO_CLICK_EDGE': {
        const edge = action.edge;
        if (!edge) return true;
        store.setUi({
          topologySelectedEdge: edge.key,
          inspector: { type: 'edge', from: edge.from, to: edge.to, key: edge.key },
        });
        return true;
      }
      case 'CLEAR_TOPO_FOCUS':
        store.setUi({ topologyFocusNode: null, topologySelectedEdge: null });
        return true;
      case 'REPLAY_CONTROL':
        applyReplayControl(action.control);
        return true;
      case 'REPLAY_SPEED':
        store.setUi({ replay: { ...store.state.replay, speed: Number(action.speed || 1) } });
        if (store.state.replay.playing) startReplayTimer();
        return true;
      case 'REPLAY_SEEK':
        stopReplayTimer();
        store.setUi({ replay: { ...store.state.replay, active: true, playing: false, cursorSeq: Number(action.seq || 0) } });
        return true;
      case 'REPLAY_CASE':
        safeStorageSet('tt_v4_board', 'topology');
        store.setUi({
          activeBoard: 'topology',
          replay: { ...store.state.replay, active: true, playing: true, cursorSeq: 0 },
        });
        startReplayTimer();
        return true;
      case 'MESSAGE_ROLE':
        safeStorageSet('tt_v4_board', 'chronicle');
        store.setUi({ activeBoard: 'chronicle', composerTarget: action.roleId || 'all', inspector: null });
        doc.querySelector('#panel-chronicle .composer-input')?.focus?.();
        return true;
      case 'SWITCH_CASE':
        await sync.switchConversation(action.convId, true);
        store.setUi({ settingsOpen: false, settingsError: '', inspector: null });
        return true;
      case 'SYNC_ACTIVE_TAB':
        await sync.syncActiveTab();
        return true;
      case 'NEW_RUN': {
        const baseCid = cid.split('--run-')[0] || '';
        if (!baseCid || baseCid === 'default') {
          store.setUi({ settingsError: 'No active conversation selected', actionError: 'No active conversation selected' });
          return false;
        }
        const res = await sync.postApi('/task/update', { convId: baseCid, newRun: true });
        if (res?.status === 'error' || res?.status === 'offline') {
          const msg = res.detail || res.error || 'Error';
          store.setUi({ settingsError: msg, actionError: msg });
          return false;
        }
        store.setUi({ settingsError: '', actionError: '' });
        await sync.switchConversation(baseCid, true);
        return true;
      }
      case 'REOPEN_CASE': {
        const res = await sync.postApi('/governance/reopen', { convId: cid });
        if (res?.status === 'error' || res?.status === 'offline') {
          const msg = res.detail || res.error || 'Error';
          store.setUi({ settingsError: msg, actionError: msg });
          return false;
        }
        store.setUi({ settingsError: '', actionError: '' });
        await sync.fetchStatus(cid);
        return true;
      }
      case 'CREATE_CASE': {
        let targetCid = (store.state.convId && store.state.convId !== 'default') ? store.state.convId : '';
        if (!targetCid) {
          const wsQ = store.state.workspaceUri ? `?workspaceUri=${encodeURIComponent(store.state.workspaceUri)}` : '';
          const hostCtx = await sync.getApi(`/host/context${wsQ}`);
          const candidate = hostCtx?.conversationId || hostCtx?.convId || '';
          targetCid = (candidate && candidate !== 'default')
            ? candidate
            : (globalThis.crypto?.randomUUID ? globalThis.crypto.randomUUID() : `case-${Date.now()}`);
          store.state.convId = targetCid;
        }
        const res = await sync.postApi('/task/update', {
          convId: targetCid,
          project: action.project,
          directive: action.directive || '',
          status: 'ACTIVE',
          round: 1,
          progress: 5,
        });
        if (res?.status === 'error' || res?.status === 'offline') {
          store.setUi({ actionError: res.detail || res.error || 'Error' });
          return false;
        }
        store.setUi({ actionError: '' });
        await sync.fetchStatus(targetCid);
        sync.connectWs();
        return true;
      }
      case 'UPDATE_META':
      case 'EXTEND_ROUNDS':
      case 'COMPLETE_CASE':
      case 'FORCE_CLOSE':
      case 'SAVE_CAPS': {
        const endpoint = action.type === 'EXTEND_ROUNDS' ? '/governance/extend_rounds' : '/task/update';
        const body = action.type === 'EXTEND_ROUNDS'
          ? { convId: cid, additionalRounds: 3 }
          : action.type === 'COMPLETE_CASE'
            ? { convId: cid, status: 'COMPLETED', progress: 100 }
            : action.type === 'FORCE_CLOSE'
              ? { convId: cid, status: 'COMPLETED', progress: 100, forceClose: true, forceReason: action.reason }
              : action.type === 'SAVE_CAPS'
                ? { convId: cid, roleCaps: action.roleCaps }
                : { convId: cid, project: action.project, directive: action.directive };
        const res = await sync.postApi(endpoint, body);
        if (res?.status === 'error' || res?.status === 'offline') {
          const msg = res.detail || res.error || 'Error';
          store.setUi({ settingsError: msg, actionError: msg });
          return false;
        }
        store.setUi({ settingsError: '', actionError: '' });
        await sync.fetchStatus(cid);
        return true;
      }
      case 'FINDING_ACTION': {
        const res = await sync.postApi('/findings/action', {
          convId: cid,
          findingId: action.findingId,
          action: action.action,
          reason: action.reason,
        });
        if (res?.status === 'error' || res?.status === 'offline') {
          store.setUi({ actionError: res.detail || res.error || 'Error' });
          return false;
        }
        store.setUi({ actionError: '' });
        await sync.fetchStatus(cid);
        return true;
      }
      case 'PROPOSAL_ACTION': {
        const res = await sync.postApi('/proposal/action', {
          convId: cid,
          action: action.action,
          optionId: action.optionId,
          comment: action.comment,
        });
        if (res?.status === 'error' || res?.status === 'offline') {
          store.setUi({ actionError: res.detail || res.error || 'Error' });
          return false;
        }
        store.setUi({ actionError: '' });
        await sync.fetchStatus(cid);
        return true;
      }
      case 'REVIEW_DECISION': {
        const res = await sync.postApi('/governance/review_decision', {
          convId: cid,
          decision: action.decision,
          note: action.note || '',
        });
        if (res?.status === 'error' || res?.status === 'offline') {
          store.setUi({ actionError: res.detail || res.error || 'Error' });
          return false;
        }
        store.setUi({ actionError: '' });
        await sync.fetchStatus(cid);
        return true;
      }
      case 'POST_USER_CHAT': {
        const langNow = store.state.lang || 'fa';
        const target = action.targetRole && action.targetRole !== 'all' ? action.targetRole : '';
        const res = await sync.postApi('/chat/send', {
          convId: cid,
          channel: 'MAIN',
          senderCode: 'OWNER',
          senderName: langNow === 'fa' ? 'شما' : 'You',
          senderRole: 'owner',
          recipient: target || undefined,
          recipientRole: target || undefined,
          recipientCode: target ? target.toUpperCase() : undefined,
          isOperator: true,
          content: action.content,
        });
        if (res?.status === 'error' || res?.status === 'offline') {
          store.setUi({ actionError: res.detail || res.error || 'Error' });
          return false;
        }
        store.setUi({ actionError: '' });
        if (action.forwardToHost && cid && cid !== 'default') {
          const prompt = target ? `@${target} ${action.content}` : action.content;
          await sync.postApi('/host/send-message', { convId: cid, prompt });
        }
        await sync.fetchStatus(cid);
        return true;
      }
      default:
        return true;
    }
  }

  function renderHeaderAndChrome(state) {
    stripPreloadBodyStyles();
    const lang = state.lang || 'fa';
    dom.root.lang = lang;
    dom.root.dir = dirForLang(lang);
    dom.root.dataset.mode = state.theme;
    dom.root.dataset.theme = state.theme;

    setText(dom.caseTitle, state.thinkTank?.project || t('app.title', {}, lang));
    if (dom.connBadge) {
      const conn = state.connState || 'syncing';
      setAttr(dom.connBadge, 'data-conn', conn);
      setText(dom.connBadge, t(`conn.${conn}`, {}, lang));
    }

    setText(dom.btnNewRun, t('header.newRun', {}, lang));
    setText(dom.btnCaseSwitcher, t('header.switchCase', {}, lang));
    setText(dom.btnLangToggle, t('header.langToggle', {}, lang));
    setAttr(dom.btnThemeToggle, 'aria-label', t('header.themeToggle', {}, lang));
    setAttr(dom.btnOpenSettings, 'aria-label', t('header.settings', {}, lang));

    if (dom.runPills) {
      const baseCid = (state.parentConvId || state.convId || '').split('--run-')[0];
      const related = (state.conversationsList || [])
        .filter((c) => {
          const id = c.convId || c.id || '';
          return baseCid && (id === baseCid || id.startsWith(`${baseCid}--run-`));
        })
        .sort((a, b) => Number(a.runIndex || 1) - Number(b.runIndex || 1));

      dom.runPills.innerHTML = '';
      for (const rc of related.slice(-5)) {
        const rcid = rc.convId || rc.id;
        const btn = doc.createElement('button');
        btn.type = 'button';
        btn.className = 'run-pill';
        if (rcid === state.convId) btn.classList.add('is-current');
        setText(btn, `#${formatNum(rc.runIndex || 1, lang)}`);
        btn.addEventListener('click', () => onAction({ type: 'SWITCH_CASE', convId: rcid }));
        dom.runPills.appendChild(btn);
      }
    }

    if (dom.offlineBanner) {
      dom.offlineBanner.hidden = state.connState !== 'offline' && !state.actionError;
      setText(dom.offlineText, state.actionError || state.offlineError || t('state.offlineBanner', {}, lang));
      setText(dom.btnRetrySync, t('state.retry', {}, lang));
    }

    for (const tab of dom.tabs) {
      const b = tab.getAttribute('data-board');
      setText(tab, t(`tab.${b}`, {}, lang));
    }

    setText(dom.emptyTitle, t('state.emptyTitle', {}, lang));
    setText(dom.emptyDesc, t('state.emptyDesc', {}, lang));
    setText(dom.btnEmptyCreate, t('state.createCase', {}, lang));
    setText(dom.btnEmptySync, t('state.syncTab', {}, lang));
    setText(dom.emptyProjectLabel, t('state.projectLabel', {}, lang));
    setText(dom.emptyDirectiveLabel, t('state.directiveLabel', {}, lang));
    setText(dom.btnEmptySubmit, t('state.submitCreate', {}, lang));
    setText(dom.btnEmptyCancel, t('state.cancel', {}, lang));
    setText(dom.emptyRecentHeading, t('state.recentCases', {}, lang));

    if (dom.emptyRecentList && dom.emptyRecentWrap) {
      const recents = (state.conversationsList || []).slice(0, 6);
      dom.emptyRecentWrap.hidden = recents.length === 0;
      dom.emptyRecentList.innerHTML = '';
      for (const c of recents) {
        const cid = c.convId || c.id;
        const btn = doc.createElement('button');
        btn.type = 'button';
        btn.className = 'recent-case-row';
        const nameSpan = doc.createElement('span');
        setText(nameSpan, c.project || cid);
        const tagSpan = doc.createElement('span');
        tagSpan.className = 'status-tag';
        setText(tagSpan, c.isClosed ? t('conn.closed', {}, lang) : t('conn.live', {}, lang));
        btn.append(nameSpan, tagSpan);
        btn.addEventListener('click', () => onAction({ type: 'SWITCH_CASE', convId: cid }));
        dom.emptyRecentList.appendChild(btn);
      }
    }
  }

  function renderPipeline(state) {
    const lang = state.lang || 'fa';
    const tt = state.thinkTank || {};
    const stage = Number(tt.pipelineStage || 1);
    const closed = Boolean(tt.isClosed);

    for (const step of dom.pipeSteps) {
      const sNum = Number(step.getAttribute('data-stage') || 1);
      step.classList.toggle('is-done', closed || sNum < stage);
      step.classList.toggle('is-current', !closed && sNum === stage);
      const lblEl = step.querySelector('[data-stage-label]');
      if (lblEl) setText(lblEl, t(`pipe.s${sNum}`, {}, lang));
      const numEl = step.querySelector('.pipe-num');
      if (numEl) setText(numEl, formatNum(sNum, lang));
    }

    const openCount = (state.findings || []).filter((f) => ['Open', 'Fixing', 'InReview', 'Testing'].includes(f.state)).length;
    setText(dom.metricRound, t('pipe.round', { round: tt.round || 1, max: tt.maxRounds || 50 }, lang));
    setText(dom.metricOpenFindings, t('pipe.openFindings', { count: openCount }, lang));
    setText(dom.metricSeq, `#${formatNum(state.seq || 0, lang)}`);
  }

  const lastRevs = {
    headerRev: -1, pipelineRev: -1, pulseRev: -1, wbsRev: -1,
    findingsRev: -1, topologyRev: -1, ledgerRev: -1, squadRev: -1,
    telemetryRev: -1, uiRev: -1,
  };
  const boardRendered = {
    command: '', topology: '', chronicle: '', squad: '',
  };
  let lastBoard = '';
  let lastLang = '';
  let lastInspectorSig = '';
  let lastSettingsSig = '';
  let scheduled = false;

  function renderNow() {
    scheduled = false;
    const { state, revs } = store;
    const lang = state.lang || 'fa';
    const langChanged = lang !== lastLang;
    const boardSwitched = state.activeBoard !== lastBoard;

    const isLoading = state.loadState === 'loading';
    const showEmpty = !isLoading && !state.hasSession;
    const showWorkspace = !isLoading && state.hasSession;
    if (dom.stateLoading) dom.stateLoading.hidden = !isLoading;
    if (dom.stateEmpty) dom.stateEmpty.hidden = !showEmpty;
    if (dom.workspace) dom.workspace.hidden = !showWorkspace;

    if (revs.headerRev !== lastRevs.headerRev || revs.uiRev !== lastRevs.uiRev || langChanged) {
      renderHeaderAndChrome(state);
    }

    if (revs.pipelineRev !== lastRevs.pipelineRev || revs.findingsRev !== lastRevs.findingsRev || langChanged) {
      renderPipeline(state);
    }

    if (boardSwitched || revs.uiRev !== lastRevs.uiRev) {
      for (const tab of dom.tabs) {
        const b = tab.getAttribute('data-board');
        const active = b === state.activeBoard;
        setAttr(tab, 'aria-selected', active ? 'true' : 'false');
        setAttr(tab, 'tabindex', active ? '0' : '-1');
      }
      for (const b of BOARDS) {
        if (dom.panels[b]) dom.panels[b].hidden = b !== state.activeBoard;
      }
    }

    if (showWorkspace) {
      const cmdSig = `${revs.wbsRev}:${revs.findingsRev}:${revs.pipelineRev}:${revs.uiRev}:${lang}`;
      const topoSig = `${revs.topologyRev}:${revs.uiRev}:${lang}`;
      const chronSig = `${revs.ledgerRev}:${revs.uiRev}:${lang}`;
      const squadSig = `${revs.squadRev}:${revs.pulseRev}:${revs.telemetryRev}:${revs.wbsRev}:${revs.uiRev}:${lang}`;

      if (state.activeBoard === 'command') {
        if (boardRendered.command !== cmdSig) {
          renderCommandBoard(dom.panels.command, state, { onAction, doc });
          boardRendered.command = cmdSig;
        } else if (revs.pulseRev !== lastRevs.pulseRev) {
          patchCommandPulse(dom.panels.command, state, doc);
        }
      } else if (state.activeBoard === 'topology') {
        if (boardRendered.topology !== topoSig) {
          renderTopologyBoard(dom.panels.topology, state, { buildGraph: buildGraphFromInteractions, onAction, doc });
          boardRendered.topology = topoSig;
        } else if (revs.pulseRev !== lastRevs.pulseRev) {
          patchTopologyPulse(dom.panels.topology, state.agents);
        }
      } else if (state.activeBoard === 'chronicle') {
        if (boardRendered.chronicle !== chronSig) {
          renderChronicleBoard(dom.panels.chronicle, state, { onAction, doc });
          boardRendered.chronicle = chronSig;
        }
      } else if (state.activeBoard === 'squad') {
        if (boardRendered.squad !== squadSig) {
          renderSquadBoard(dom.panels.squad, state, { onAction, doc });
          boardRendered.squad = squadSig;
        }
      }
    }

    const inspSig = state.inspector
      ? `${JSON.stringify(state.inspector)}:${revs.findingsRev}:${revs.ledgerRev}:${revs.wbsRev}:${revs.squadRev}:${revs.uiRev}:${lang}`
      : 'closed';
    if (inspSig !== lastInspectorSig) {
      renderDossierDrawer(dom.dossierDrawer, state, { onAction, doc });
      lastInspectorSig = inspSig;
    }

    const settingsSig = state.settingsOpen
      ? `open:${state.convId}:${state.devMode}:${state.settingsError || ''}:${revs.headerRev}:${revs.pipelineRev}:${lang}`
      : 'closed';
    if (settingsSig !== lastSettingsSig) {
      renderSettingsSheet(dom.settingsDialog, state, { onAction, doc });
      lastSettingsSig = settingsSig;
    }

    Object.assign(lastRevs, revs);
    lastBoard = state.activeBoard;
    lastLang = lang;
  }

  function scheduleRender() {
    if (scheduled) return;
    scheduled = true;
    const raf = globalThis.requestAnimationFrame;
    if (!doc.hidden && typeof raf === 'function') {
      raf(() => {
        if (scheduled) renderNow();
      });
      setTimeout(() => {
        if (scheduled) renderNow();
      }, 24);
    } else {
      Promise.resolve().then(() => {
        if (scheduled) renderNow();
      });
    }
  }

  store.subscribe(scheduleRender);
  doc.addEventListener?.('visibilitychange', () => {
    if (!doc.hidden) renderNow();
  });

  function selectBoard(board) {
    if (!BOARDS.includes(board) || store.state.activeBoard === board) return;
    safeStorageSet('tt_v4_board', board);
    store.setUi({ activeBoard: board });
  }

  dom.btnLangToggle?.addEventListener('click', () => {
    const next = store.state.lang === 'fa' ? 'en' : 'fa';
    safeStorageSet('tt_v4_lang', next);
    store.setUi({ lang: next });
  });

  dom.btnThemeToggle?.addEventListener('click', () => {
    const next = store.state.theme === 'dark' ? 'light' : 'dark';
    safeStorageSet('tt_v4_theme', next);
    store.setUi({ theme: next });
  });

  dom.btnNewRun?.addEventListener('click', () => onAction({ type: 'NEW_RUN' }));
  dom.btnRetrySync?.addEventListener('click', () => {
    store.setUi({ actionError: '' });
    sync.fetchStatus(store.state.convId).then(() => sync.connectWs());
  });
  dom.btnCaseSwitcher?.addEventListener('click', () => {
    store.setUi({ settingsOpen: true, settingsError: '' });
    refreshConversations();
  });
  dom.btnOpenSettings?.addEventListener('click', () => {
    store.setUi({ settingsOpen: true, settingsError: '' });
    refreshConversations();
  });
  dom.settingsSheet?.addEventListener('click', (ev) => {
    if (ev.target === dom.settingsSheet) onAction({ type: 'CLOSE_SETTINGS' });
  });

  dom.btnEmptyCreate?.addEventListener('click', () => {
    if (dom.emptyCreateForm) dom.emptyCreateForm.hidden = false;
    dom.emptyProjectInput?.focus?.();
  });
  dom.btnEmptyCancel?.addEventListener('click', () => {
    if (dom.emptyCreateForm) dom.emptyCreateForm.hidden = true;
  });
  dom.btnEmptySync?.addEventListener('click', () => onAction({ type: 'SYNC_ACTIVE_TAB' }));
  dom.emptyCreateForm?.addEventListener('submit', async (ev) => {
    ev.preventDefault();
    const project = dom.emptyProjectInput?.value.trim() || '';
    if (!project) return;
    const directive = dom.emptyDirectiveInput?.value.trim() || '';
    const ok = await onAction({ type: 'CREATE_CASE', project, directive });
    if (ok !== false && dom.emptyCreateForm) dom.emptyCreateForm.hidden = true;
  });

  for (const tab of dom.tabs) {
    tab.addEventListener('click', () => selectBoard(tab.getAttribute('data-board')));
  }

  dom.tablist?.addEventListener('keydown', (ev) => {
    const idx = dom.tabs.indexOf(doc.activeElement);
    if (idx < 0) return;
    const isRtl = dom.root.dir === 'rtl';
    let nextIdx = idx;
    if (ev.key === 'ArrowRight') nextIdx = (idx + (isRtl ? -1 : 1) + dom.tabs.length) % dom.tabs.length;
    else if (ev.key === 'ArrowLeft') nextIdx = (idx + (isRtl ? 1 : -1) + dom.tabs.length) % dom.tabs.length;
    else if (ev.key === 'Home') nextIdx = 0;
    else if (ev.key === 'End') nextIdx = dom.tabs.length - 1;
    else return;
    ev.preventDefault();
    const targetTab = dom.tabs[nextIdx];
    targetTab.focus({ preventScroll: true });
    selectBoard(targetTab.getAttribute('data-board'));
  });

  doc.addEventListener('keydown', (ev) => {
    const tag = ev.target?.tagName;
    if (tag === 'INPUT' || tag === 'TEXTAREA' || tag === 'SELECT' || ev.target?.isContentEditable) return;
    if (ev.ctrlKey || ev.metaKey || ev.altKey) return;

    if (ev.key === 'Escape') {
      if (store.state.settingsOpen) {
        store.setUi({ settingsOpen: false, settingsError: '' });
      } else if (store.state.inspector) {
        store.setUi({ inspector: null });
      }
      return;
    }

    if (ev.key >= '1' && ev.key <= '4') {
      selectBoard(BOARDS[Number(ev.key) - 1]);
      return;
    }

    if (store.state.activeBoard === 'topology' && !store.state.settingsOpen) {
      if (ev.key === ' ') {
        ev.preventDefault();
        applyReplayControl('play');
      } else if (ev.key === 'ArrowLeft') {
        ev.preventDefault();
        applyReplayControl('prev');
      } else if (ev.key === 'ArrowRight') {
        ev.preventDefault();
        applyReplayControl('next');
      } else if (ev.key === 'l' || ev.key === 'L') {
        applyReplayControl('live');
      }
    }
  });

  renderNow();
  sync.start();

  return { store, sync, onAction, renderNow, destroy: () => { stopReplayTimer(); sync.destroy(); } };
}

if (typeof globalThis.document !== 'undefined' && globalThis.document.getElementById('studio-shell')) {
  initThinkTankStudio(globalThis.document);
}
