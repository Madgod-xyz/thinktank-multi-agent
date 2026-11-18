import { patchKeyedChildren, createSvgEl, setAttr, setText } from '../dom.mjs';
import { formatNum, stateLabel, t, toneForState } from '../i18n.mjs';
import { getRoleMeta, normalizeRoleId, roleMonogram, roleTitle } from '../roles.mjs';

const LIFECYCLE_STAGES = ['Open', 'Fixing', 'InReview', 'Testing', 'Verified'];
const SEVERITY_RANK = { CRITICAL: 0, HIGH: 1, MEDIUM: 2, LOW: 3 };
const FINDING_FILTERS = ['ALL', 'Open', 'Fixing', 'InReview', 'Testing', 'Verified'];
const WBS_FILTERS = ['ALL', 'ACTIVE', 'COMPLETED'];

function makeArrowIcon(doc) {
  const svg = createSvgEl(doc, 'svg', {
    class: 'dir-arrow-icon', width: '12', height: '12', viewBox: '0 0 12 12', 'aria-hidden': 'true',
  });
  svg.appendChild(createSvgEl(doc, 'path', {
    d: 'M2 6h7.5M6.8 3.2L9.6 6 6.8 8.8',
    fill: 'none', stroke: 'currentColor', 'stroke-width': '1.3', 'stroke-linecap': 'round', 'stroke-linejoin': 'round',
  }));
  return svg;
}

function findingNumericId(id) {
  const m = /^F-(\d+)$/i.exec(String(id || ''));
  return m ? Number(m[1]) : 9999;
}

function sortFindings(list = []) {
  return [...list].sort((a, b) => {
    const pinDiff = Number(Boolean(b?.markedImportant)) - Number(Boolean(a?.markedImportant));
    if (pinDiff !== 0) return pinDiff;
    const sevA = SEVERITY_RANK[String(a?.severity || 'MEDIUM').toUpperCase()] ?? 2;
    const sevB = SEVERITY_RANK[String(b?.severity || 'MEDIUM').toUpperCase()] ?? 2;
    if (sevA !== sevB) return sevA - sevB;
    return findingNumericId(a?.id) - findingNumericId(b?.id);
  });
}

function ensureScaffold(container, doc, onAction) {
  if (container._cmdRefs) return container._cmdRefs;
  container.innerHTML = '';

  const pulsePlate = doc.createElement('section');
  pulsePlate.className = 'pulse-strip surface-plate';
  const pulseHead = doc.createElement('div');
  pulseHead.className = 'region-head';
  const pulseTitle = doc.createElement('h2');
  pulseTitle.className = 'region-title';
  pulseHead.appendChild(pulseTitle);
  const pulseList = doc.createElement('div');
  pulseList.className = 'pulse-list';
  const pulseEmpty = doc.createElement('p');
  pulseEmpty.className = 'empty-note';
  pulsePlate.append(pulseHead, pulseList, pulseEmpty);

  const gatePlate = doc.createElement('section');
  gatePlate.className = 'decision-gate surface-plate';
  gatePlate.hidden = true;
  const gateHead = doc.createElement('div');
  gateHead.className = 'region-head';
  const gateTitle = doc.createElement('h2');
  gateTitle.className = 'region-title';
  const gateBadge = doc.createElement('span');
  gateBadge.className = 'status-tag';
  gateBadge.setAttribute('data-tone', 'review');
  gateHead.append(gateTitle, gateBadge);
  const gateSubject = doc.createElement('h3');
  gateSubject.className = 'sub-heading';
  const gateSummary = doc.createElement('p');
  gateSummary.className = 'dossier-text';
  const gateOptions = doc.createElement('div');
  gateOptions.className = 'decision-options';
  const gateActions = doc.createElement('div');
  gateActions.className = 'decision-actions';
  const gateApproveBtn = doc.createElement('button');
  gateApproveBtn.type = 'button';
  gateApproveBtn.className = 'btn btn-primary';
  const gateContinueBtn = doc.createElement('button');
  gateContinueBtn.type = 'button';
  gateContinueBtn.className = 'btn btn-primary';
  const gateStopBtn = doc.createElement('button');
  gateStopBtn.type = 'button';
  gateStopBtn.className = 'btn btn-danger-outline';
  gateActions.append(gateApproveBtn, gateContinueBtn, gateStopBtn);
  const gateReviseRow = doc.createElement('form');
  gateReviseRow.className = 'decision-revise-row';
  const gateReviseInput = doc.createElement('textarea');
  gateReviseInput.className = 'field-textarea decision-revise-input';
  gateReviseInput.rows = 1;
  const gateReviseBtn = doc.createElement('button');
  gateReviseBtn.type = 'submit';
  gateReviseBtn.className = 'btn btn-quiet';
  gateReviseRow.append(gateReviseInput, gateReviseBtn);
  gatePlate.append(gateHead, gateSubject, gateSummary, gateOptions, gateActions, gateReviseRow);

  gateApproveBtn.addEventListener('click', () => onAction?.({ type: 'PROPOSAL_ACTION', action: 'approve' }));
  gateContinueBtn.addEventListener('click', () => onAction?.({ type: 'REVIEW_DECISION', decision: 'continue' }));
  gateStopBtn.addEventListener('click', () => onAction?.({ type: 'REVIEW_DECISION', decision: 'stop' }));
  gateReviseRow.addEventListener('submit', (ev) => {
    ev.preventDefault();
    const comment = gateReviseInput.value.trim();
    Promise.resolve(onAction?.({ type: 'PROPOSAL_ACTION', action: 'request_revision', comment })).then((ok) => {
      if (ok !== false) gateReviseInput.value = '';
    });
  });

  const receiptPlate = doc.createElement('section');
  receiptPlate.className = 'receipt-plate surface-plate';
  receiptPlate.hidden = true;
  const receiptHead = doc.createElement('div');
  receiptHead.className = 'region-head';
  const receiptTitle = doc.createElement('h2');
  receiptTitle.className = 'region-title';
  const receiptQaTag = doc.createElement('span');
  receiptQaTag.className = 'status-tag';
  receiptQaTag.setAttribute('data-tone', 'verified');
  receiptHead.append(receiptTitle, receiptQaTag);
  const receiptStats = doc.createElement('div');
  receiptStats.className = 'receipt-stats';
  const statCells = [];
  for (let i = 0; i < 4; i += 1) {
    const cell = doc.createElement('div');
    cell.className = 'receipt-cell';
    const fig = doc.createElement('span');
    fig.className = 'receipt-figure';
    const lbl = doc.createElement('span');
    lbl.className = 'field-label';
    cell.append(fig, lbl);
    receiptStats.appendChild(cell);
    statCells.push({ fig, lbl });
  }
  const receiptReason = doc.createElement('p');
  receiptReason.className = 'dossier-text';
  receiptReason.hidden = true;
  const receiptActions = doc.createElement('div');
  receiptActions.className = 'receipt-actions';
  const replayBtn = doc.createElement('button');
  replayBtn.type = 'button';
  replayBtn.className = 'btn btn-quiet';
  const reopenBtn = doc.createElement('button');
  reopenBtn.type = 'button';
  reopenBtn.className = 'btn btn-quiet';
  const newRunBtn = doc.createElement('button');
  newRunBtn.type = 'button';
  newRunBtn.className = 'btn btn-primary';
  receiptActions.append(replayBtn, reopenBtn, newRunBtn);
  receiptPlate.append(receiptHead, receiptStats, receiptReason, receiptActions);

  replayBtn.addEventListener('click', () => onAction?.({ type: 'REPLAY_CASE' }));
  reopenBtn.addEventListener('click', () => onAction?.({ type: 'REOPEN_CASE' }));
  newRunBtn.addEventListener('click', () => onAction?.({ type: 'NEW_RUN' }));

  const findingsPlate = doc.createElement('section');
  findingsPlate.className = 'board-region surface-plate';
  const findingsHead = doc.createElement('div');
  findingsHead.className = 'region-head';
  const findingsTitle = doc.createElement('h2');
  findingsTitle.className = 'region-title';
  const findingsFilters = doc.createElement('div');
  findingsFilters.className = 'filter-bar';
  const findingFilterBtns = new Map();
  for (const fk of FINDING_FILTERS) {
    const b = doc.createElement('button');
    b.type = 'button';
    b.className = 'pill-filter';
    b.setAttribute('data-filter', fk);
    b.addEventListener('click', () => onAction?.({ type: 'SET_FINDING_FILTER', filter: fk }));
    findingsFilters.appendChild(b);
    findingFilterBtns.set(fk, b);
  }
  findingsHead.append(findingsTitle, findingsFilters);
  const findingsList = doc.createElement('div');
  findingsList.className = 'findings-list';
  const findingsEmpty = doc.createElement('p');
  findingsEmpty.className = 'empty-note';
  const archiveDetails = doc.createElement('details');
  archiveDetails.className = 'archive-details';
  const archiveSummary = doc.createElement('summary');
  archiveSummary.className = 'archive-summary';
  const archiveList = doc.createElement('div');
  archiveList.className = 'findings-list';
  archiveDetails.append(archiveSummary, archiveList);
  findingsPlate.append(findingsHead, findingsList, findingsEmpty, archiveDetails);

  const wbsPlate = doc.createElement('section');
  wbsPlate.className = 'board-region surface-plate';
  const wbsHead = doc.createElement('div');
  wbsHead.className = 'region-head';
  const wbsTitle = doc.createElement('h2');
  wbsTitle.className = 'region-title';
  const wbsFilters = doc.createElement('div');
  wbsFilters.className = 'filter-bar';
  const wbsFilterBtns = new Map();
  for (const wk of WBS_FILTERS) {
    const b = doc.createElement('button');
    b.type = 'button';
    b.className = 'pill-filter';
    b.setAttribute('data-filter', wk);
    b.addEventListener('click', () => onAction?.({ type: 'SET_WBS_FILTER', filter: wk }));
    wbsFilters.appendChild(b);
    wbsFilterBtns.set(wk, b);
  }
  wbsHead.append(wbsTitle, wbsFilters);
  const wbsScroll = doc.createElement('div');
  wbsScroll.className = 'table-scroll';
  const wbsTable = doc.createElement('table');
  wbsTable.className = 'data-table';
  const wbsThead = doc.createElement('thead');
  const wbsHeadRow = doc.createElement('tr');
  const wbsThs = [];
  for (let i = 0; i < 5; i += 1) {
    const th = doc.createElement('th');
    wbsHeadRow.appendChild(th);
    wbsThs.push(th);
  }
  wbsThead.appendChild(wbsHeadRow);
  const wbsTbody = doc.createElement('tbody');
  wbsTable.append(wbsThead, wbsTbody);
  wbsScroll.appendChild(wbsTable);
  const wbsEmpty = doc.createElement('p');
  wbsEmpty.className = 'empty-note';
  wbsPlate.append(wbsHead, wbsScroll, wbsEmpty);

  container.append(pulsePlate, gatePlate, receiptPlate, findingsPlate, wbsPlate);

  container._cmdRefs = {
    pulseTitle, pulseList, pulseEmpty,
    gatePlate, gateTitle, gateBadge, gateSubject, gateSummary, gateOptions,
    gateApproveBtn, gateContinueBtn, gateStopBtn, gateReviseRow, gateReviseInput, gateReviseBtn,
    receiptPlate, receiptTitle, receiptQaTag, statCells, receiptReason, replayBtn, reopenBtn, newRunBtn,
    findingsTitle, findingFilterBtns, findingsList, findingsEmpty, archiveDetails, archiveSummary, archiveList,
    wbsTitle, wbsFilterBtns, wbsThs, wbsScroll, wbsTbody, wbsEmpty,
  };
  return container._cmdRefs;
}

export function patchCommandPulse(container, state, doc = globalThis.document) {
  const refs = container?._cmdRefs;
  if (!refs || !doc) return;
  const lang = state.lang || 'fa';
  setText(refs.pulseTitle, t('cmd.pulseTitle', {}, lang));
  const activeAgents = (state.agents || []).filter(
    (ag) => ag.status === 'WORKING' || ag.status === 'ACTIVE' || Boolean(ag.activeTool || ag.tool),
  );
  refs.pulseEmpty.hidden = activeAgents.length > 0;
  setText(refs.pulseEmpty, t('cmd.pulseIdle', {}, lang));

  patchKeyedChildren(
    refs.pulseList,
    activeAgents,
    (ag) => ag.id,
    (ag) => {
      const item = doc.createElement('div');
      item.className = 'pulse-item';
      const mono = doc.createElement('span');
      mono.className = 'role-mono';
      const meta = getRoleMeta(ag.id);
      if (meta?.frameShape) mono.setAttribute('data-shape', meta.frameShape);
      const nameEl = doc.createElement('span');
      const toolEl = doc.createElement('code');
      toolEl.className = 'code-id';
      const taskEl = doc.createElement('span');
      taskEl.className = 'pulse-task';
      const verifiedEl = doc.createElement('span');
      verifiedEl.className = 'status-tag';
      verifiedEl.setAttribute('data-tone', 'verified');
      item.append(mono, nameEl, toolEl, taskEl, verifiedEl);
      item._refs = { mono, nameEl, toolEl, taskEl, verifiedEl };
      return item;
    },
    (item, ag) => {
      item.classList.toggle('is-working', ag.status === 'WORKING');
      setText(item._refs.mono, roleMonogram(ag.id));
      setText(item._refs.nameEl, roleTitle(ag.id, lang, true));
      const toolName = ag.activeTool || ag.tool || '';
      item._refs.toolEl.hidden = !toolName;
      setText(item._refs.toolEl, toolName);
      const taskText = ag.currentTask || ag.task || '';
      item._refs.taskEl.hidden = !taskText;
      setText(item._refs.taskEl, taskText);
      item._refs.verifiedEl.hidden = !ag.verifiedSubagent;
      setText(item._refs.verifiedEl, t('cmd.verifiedSubagent', {}, lang));
    },
    'data-agent-id',
  );
}

function createFindingRow(doc, onAction) {
  const row = doc.createElement('div');
  row.className = 'finding-row';
  row.tabIndex = 0;
  row.setAttribute('role', 'button');

  const main = doc.createElement('div');
  main.className = 'finding-main';
  const idEl = doc.createElement('span');
  idEl.className = 'finding-id';
  const sevTag = doc.createElement('span');
  sevTag.className = 'status-tag';
  const titleEl = doc.createElement('span');
  titleEl.className = 'finding-title';
  main.append(idEl, sevTag, titleEl);

  const meta = doc.createElement('div');
  meta.className = 'finding-meta';
  const track = doc.createElement('span');
  track.className = 'lifecycle-track';
  track.setAttribute('aria-hidden', 'true');
  const trackSteps = [];
  for (let i = 0; i < LIFECYCLE_STAGES.length; i += 1) {
    const step = doc.createElement('span');
    step.className = 'lifecycle-step';
    track.appendChild(step);
    trackSteps.push(step);
  }
  const stateTag = doc.createElement('span');
  stateTag.className = 'status-tag';
  const pair = doc.createElement('span');
  pair.className = 'role-pair';
  const fromMono = doc.createElement('span');
  fromMono.className = 'role-mono';
  const arrowSvg = makeArrowIcon(doc);
  const toMono = doc.createElement('span');
  toMono.className = 'role-mono';
  pair.append(fromMono, arrowSvg, toMono);
  const retEl = doc.createElement('span');
  retEl.className = 'code-id';
  const evTag = doc.createElement('span');
  evTag.className = 'status-tag';
  const pinBtn = doc.createElement('button');
  pinBtn.type = 'button';
  pinBtn.className = 'btn btn-quiet btn-compact btn-pin';
  meta.append(track, stateTag, pair, retEl, evTag, pinBtn);

  row.append(main, meta);
  row._refs = { idEl, sevTag, titleEl, trackSteps, stateTag, fromMono, toMono, retEl, evTag, pinBtn };

  const inspect = () => {
    const fid = row.getAttribute('data-finding-id');
    if (fid) onAction?.({ type: 'INSPECT', target: { type: 'finding', id: fid } });
  };
  row.addEventListener('click', (ev) => {
    if (ev.target.closest?.('.btn-pin')) return;
    inspect();
  });
  row.addEventListener('keydown', (ev) => {
    if (ev.target.closest?.('.btn-pin')) return;
    if (ev.key === 'Enter' || ev.key === ' ') { ev.preventDefault(); inspect(); }
  });
  pinBtn.addEventListener('click', (ev) => {
    ev.stopPropagation();
    const fid = row.getAttribute('data-finding-id');
    if (fid) onAction?.({ type: 'FINDING_ACTION', findingId: fid, action: 'mark_important' });
  });
  return row;
}

function updateFindingRow(row, f, state, lang) {
  const r = row._refs;
  const isSel = state.inspector?.type === 'finding' && state.inspector?.id === f.id;
  row.classList.toggle('is-selected', Boolean(isSel));
  setText(r.idEl, f.id || 'F-00');
  const sev = String(f.severity || 'MEDIUM').toUpperCase();
  setText(r.sevTag, sev);
  setAttr(r.sevTag, 'data-tone', toneForState(sev));
  setText(r.titleEl, f.title || '');

  const fState = String(f.state || 'Open');
  const stageIdx = fState === 'Closed' ? LIFECYCLE_STAGES.length : LIFECYCLE_STAGES.indexOf(fState);
  for (let i = 0; i < r.trackSteps.length; i += 1) {
    const step = r.trackSteps[i];
    step.classList.toggle('is-done', stageIdx >= 0 && (i < stageIdx || fState === 'Verified' || fState === 'Closed'));
    step.classList.toggle('is-active', stageIdx >= 0 && i === stageIdx && fState !== 'Verified' && fState !== 'Closed');
  }

  setText(r.stateTag, stateLabel(fState, lang));
  setAttr(r.stateTag, 'data-tone', toneForState(fState));

  const raisedId = normalizeRoleId(f.raisedBy || 'council-critic');
  const ownerId = normalizeRoleId(f.owner || 'main_agent');
  setText(r.fromMono, roleMonogram(raisedId));
  setAttr(r.fromMono, 'data-shape', getRoleMeta(raisedId)?.frameShape || 'square');
  setText(r.toMono, roleMonogram(ownerId));
  setAttr(r.toMono, 'data-shape', getRoleMeta(ownerId)?.frameShape || 'circle');

  const retCount = Number(f.returnCount || 0);
  r.retEl.hidden = retCount <= 0;
  setText(r.retEl, `x${formatNum(retCount, lang)}`);

  const evList = Array.isArray(f.evidence) ? f.evidence : [];
  if (evList.length > 0) {
    const lastEv = evList[evList.length - 1];
    const rawCode = lastEv?.exitCode;
    const hasCode = rawCode !== null && rawCode !== undefined && rawCode !== '';
    const pass = hasCode && Number(rawCode) === 0;
    r.evTag.hidden = false;
    setAttr(r.evTag, 'data-tone', pass ? 'verified' : 'open');
    setText(r.evTag, pass ? `exit ${formatNum(0, lang)}` : `FAIL (${hasCode ? formatNum(rawCode, lang) : '?'})`);
  } else {
    r.evTag.hidden = true;
  }

  const pinned = Boolean(f.markedImportant);
  r.pinBtn.classList.toggle('is-pinned', pinned);
  setAttr(r.pinBtn, 'aria-pressed', pinned ? 'true' : 'false');
  setText(r.pinBtn, t('cmd.pinImportant', {}, lang));
}

export function renderCommandBoard(container, state, { onAction, doc = globalThis.document } = {}) {
  if (!container || !doc) return;
  const refs = ensureScaffold(container, doc, onAction);
  const lang = state.lang || 'fa';

  patchCommandPulse(container, state, doc);

  const hasProposalGate = state.proposal?.status === 'AWAITING_APPROVAL';
  const hasReviewGate = state.review?.status === 'WAITING_FOR_HUMAN';
  refs.gatePlate.hidden = !hasProposalGate && !hasReviewGate;
  if (hasProposalGate || hasReviewGate) {
    setText(refs.gateTitle, t('cmd.decisionTitle', {}, lang));
    if (hasProposalGate) {
      const p = state.proposal;
      setText(refs.gateBadge, stateLabel(p.status, lang));
      setText(refs.gateSubject, p.title || '');
      setText(refs.gateSummary, p.summary || '');
      refs.gateOptions.hidden = !(p.decisionOptions || []).length;
      patchKeyedChildren(
        refs.gateOptions,
        p.decisionOptions || [],
        (opt, i) => opt.id || `opt-${i}`,
        (opt) => {
          const btn = doc.createElement('button');
          btn.type = 'button';
          btn.className = 'decision-opt-btn';
          btn._optId = opt.id;
          btn.addEventListener('click', () => onAction?.({ type: 'PROPOSAL_ACTION', action: 'select_option', optionId: btn._optId }));
          return btn;
        },
        (btn, opt) => {
          btn._optId = opt.id;
          btn.classList.toggle('is-active', p.userDecision?.optionId === opt.id);
          setText(btn, opt.label || opt.title || opt.id);
        },
        'data-opt-id',
      );
      refs.gateApproveBtn.hidden = false;
      setText(refs.gateApproveBtn, t('cmd.approve', {}, lang));
      refs.gateContinueBtn.hidden = true;
      refs.gateStopBtn.hidden = true;
      refs.gateReviseRow.hidden = false;
      refs.gateReviseInput.placeholder = t('cmd.revisePlaceholder', {}, lang);
      setText(refs.gateReviseBtn, t('cmd.revise', {}, lang));
    } else {
      const rv = state.review;
      setText(refs.gateBadge, `${formatNum(rv.confidence ?? 0, lang)}%`);
      setText(refs.gateSubject, rv.managerSummary || '');
      setText(refs.gateSummary, rv.mainSummary || '');
      refs.gateOptions.hidden = true;
      refs.gateApproveBtn.hidden = true;
      refs.gateContinueBtn.hidden = false;
      refs.gateStopBtn.hidden = false;
      setText(refs.gateContinueBtn, t('cmd.continueWork', {}, lang));
      setText(refs.gateStopBtn, t('cmd.stopWork', {}, lang));
      refs.gateReviseRow.hidden = true;
    }
  }

  const receipt = state.thinkTank?.closureReceipt;
  const showReceipt = Boolean(state.thinkTank?.isClosed || receipt);
  refs.receiptPlate.hidden = !showReceipt;
  if (showReceipt) {
    const r = receipt || {};
    const subtasksDone = r.subtasksCompleted ?? (state.subtasks || []).filter((s) => ['COMPLETED', 'DONE'].includes(String(s.status || '').toUpperCase())).length;
    const findingsClosed = r.findingsVerified ?? (state.findings || []).filter((f) => ['Verified', 'Closed'].includes(String(f.state || ''))).length;
    const qaRuns = r.qaRunsCount ?? 0;
    const subagentEvs = r.originCounts?.subagent ?? state.originCounts?.subagent ?? 0;
    setText(refs.receiptTitle, t('cmd.receiptTitle', {}, lang));
    refs.receiptQaTag.hidden = !r.qaAllExitZero;
    setText(refs.receiptQaTag, t('cmd.qaAllZero', {}, lang));
    const pairs = [
      [subtasksDone, t('cmd.receiptTasks', {}, lang)],
      [findingsClosed, t('cmd.receiptFindings', {}, lang)],
      [qaRuns, t('cmd.receiptQa', {}, lang)],
      [subagentEvs, t('cmd.receiptOrigins', {}, lang)],
    ];
    pairs.forEach(([val, lbl], idx) => {
      setText(refs.statCells[idx].fig, formatNum(val, lang));
      setText(refs.statCells[idx].lbl, lbl);
    });
    refs.receiptReason.hidden = !r.forceCloseReason;
    setText(refs.receiptReason, r.forceCloseReason || '');
    setText(refs.replayBtn, t('cmd.replayBtn', {}, lang));
    setText(refs.reopenBtn, t('cmd.reopenBtn', {}, lang));
    setText(refs.newRunBtn, t('header.newRun', {}, lang));
  }

  setText(refs.findingsTitle, t('cmd.findingsTitle', {}, lang));
  const fFilter = state.findingFilter || 'ALL';
  for (const [fk, btn] of refs.findingFilterBtns.entries()) {
    btn.classList.toggle('is-selected', fFilter === fk);
    setText(btn, fk === 'ALL' ? t('filter.all', {}, lang) : stateLabel(fk, lang));
  }

  const allFindings = sortFindings(state.findings || []);
  const closedFindings = allFindings.filter((f) => ['Closed', 'WontFix'].includes(f.state));
  const visibleFindings = fFilter === 'ALL'
    ? allFindings.filter((f) => !['Closed', 'WontFix'].includes(f.state))
    : allFindings.filter((f) => f.state === fFilter);

  refs.findingsEmpty.hidden = visibleFindings.length > 0;
  setText(refs.findingsEmpty, t('cmd.findingsEmpty', {}, lang));
  patchKeyedChildren(
    refs.findingsList,
    visibleFindings,
    (f) => f.id,
    () => createFindingRow(doc, onAction),
    (row, f) => updateFindingRow(row, f, state, lang),
    'data-finding-id',
  );

  refs.archiveDetails.hidden = closedFindings.length === 0;
  setText(refs.archiveSummary, t('cmd.closedArchive', { count: closedFindings.length }, lang));
  patchKeyedChildren(
    refs.archiveList,
    closedFindings,
    (f) => f.id,
    () => createFindingRow(doc, onAction),
    (row, f) => updateFindingRow(row, f, state, lang),
    'data-finding-id',
  );

  setText(refs.wbsTitle, t('cmd.wbsTitle', {}, lang));
  const wFilter = state.wbsFilter || 'ALL';
  for (const [wk, btn] of refs.wbsFilterBtns.entries()) {
    btn.classList.toggle('is-selected', wFilter === wk);
    const labelKey = wk === 'ALL' ? 'filter.all' : (wk === 'ACTIVE' ? 'filter.active' : 'filter.completed');
    setText(btn, t(labelKey, {}, lang));
  }
  const colKeys = ['cmd.colId', 'cmd.colTask', 'cmd.colOwner', 'cmd.colFiles', 'cmd.colStatus'];
  colKeys.forEach((ck, i) => setText(refs.wbsThs[i], t(ck, {}, lang)));

  const subtasks = (state.subtasks || []).filter((st) => {
    const done = ['COMPLETED', 'DONE'].includes(String(st.status || '').toUpperCase());
    if (wFilter === 'ACTIVE') return !done;
    if (wFilter === 'COMPLETED') return done;
    return true;
  });

  refs.wbsScroll.hidden = subtasks.length === 0;
  refs.wbsEmpty.hidden = subtasks.length > 0;
  setText(refs.wbsEmpty, t('cmd.wbsEmpty', {}, lang));

  patchKeyedChildren(
    refs.wbsTbody,
    subtasks,
    (st) => st.id,
    () => {
      const tr = doc.createElement('tr');
      const tdId = doc.createElement('td');
      const idCode = doc.createElement('code');
      idCode.className = 'code-id';
      tdId.appendChild(idCode);

      const tdTask = doc.createElement('td');
      const titleEl = doc.createElement('div');
      const accEl = doc.createElement('div');
      accEl.className = 'squad-spec';
      tdTask.append(titleEl, accEl);

      const tdOwner = doc.createElement('td');
      const ownerWrap = doc.createElement('div');
      ownerWrap.className = 'role-pair';
      const ownerMono = doc.createElement('span');
      ownerMono.className = 'role-mono';
      const ownerName = doc.createElement('span');
      ownerWrap.append(ownerMono, ownerName);
      tdOwner.appendChild(ownerWrap);

      const tdFiles = doc.createElement('td');
      const filesWrap = doc.createElement('div');
      filesWrap.className = 'file-chips';
      tdFiles.appendChild(filesWrap);

      const tdStatus = doc.createElement('td');
      const statusTag = doc.createElement('span');
      statusTag.className = 'status-tag';
      tdStatus.appendChild(statusTag);

      tr.append(tdId, tdTask, tdOwner, tdFiles, tdStatus);
      tr._refs = { idCode, titleEl, accEl, ownerMono, ownerName, filesWrap, statusTag };
      return tr;
    },
    (tr, st) => {
      const r = tr._refs;
      setText(r.idCode, st.id || '');
      setText(r.titleEl, st.title || '');
      r.accEl.hidden = !st.acceptanceCriteria;
      setText(r.accEl, st.acceptanceCriteria || '');

      const ownerId = normalizeRoleId(st.assignee || '');
      setText(r.ownerMono, roleMonogram(ownerId));
      setAttr(r.ownerMono, 'data-shape', getRoleMeta(ownerId)?.frameShape || 'circle');
      setText(r.ownerName, roleTitle(ownerId, lang, true));

      patchKeyedChildren(
        r.filesWrap,
        st.lockedFiles || [],
        (fp) => fp,
        () => {
          const code = doc.createElement('code');
          code.className = 'file-chip file-path';
          return code;
        },
        (el, fp) => setText(el, fp),
        'data-file',
      );

      setText(r.statusTag, stateLabel(st.status || 'PENDING', lang));
      setAttr(r.statusTag, 'data-tone', toneForState(st.status));
    },
    'data-subtask-id',
  );
}
