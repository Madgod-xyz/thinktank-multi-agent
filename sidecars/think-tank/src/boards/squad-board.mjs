import { createSvgEl, patchKeyedChildren, setAttr, setText } from '../dom.mjs';
import { formatNum, stateLabel, t, toneForState } from '../i18n.mjs';
import { CANONICAL_ROLES, getRoleMeta, normalizeRoleId, roleMonogram, roleTitle } from '../roles.mjs';

const TIER_FILTERS = ['ALL', 'SUPERVISORS', 'QA', 'WORKERS'];

function matchesTier(role, filter) {
  if (!filter || filter === 'ALL') return true;
  if (filter === 'SUPERVISORS') return role.tier === 'coordinator' || role.tier === 'supervisor';
  if (filter === 'QA') return role.tier === 'tester';
  if (filter === 'WORKERS') return role.tier === 'worker';
  return true;
}

function capForRole(roleId, caps = {}) {
  if (roleId === 'main_agent') return Number(caps.main || 50);
  if (roleId === 'team-manager') return Number(caps.manager || 50);
  return Number(caps.subagents || 50);
}

function ensureScaffold(container, doc, onAction) {
  if (container._squadRefs) return container._squadRefs;
  container.innerHTML = '';

  const rosterPlate = doc.createElement('section');
  rosterPlate.className = 'board-region surface-plate';
  const rosterHead = doc.createElement('div');
  rosterHead.className = 'region-head';
  const rosterTitle = doc.createElement('h2');
  rosterTitle.className = 'region-title';
  const filterBar = doc.createElement('div');
  filterBar.className = 'filter-bar';
  const filterBtns = new Map();
  for (const fk of TIER_FILTERS) {
    const b = doc.createElement('button');
    b.type = 'button';
    b.className = 'pill-filter';
    b.addEventListener('click', () => onAction?.({ type: 'SET_SQUAD_FILTER', filter: fk }));
    filterBar.appendChild(b);
    filterBtns.set(fk, b);
  }
  rosterHead.append(rosterTitle, filterBar);
  const squadList = doc.createElement('div');
  squadList.className = 'squad-list';
  rosterPlate.append(rosterHead, squadList);

  const locksPlate = doc.createElement('section');
  locksPlate.className = 'board-region surface-plate';
  const locksTitle = doc.createElement('h2');
  locksTitle.className = 'region-title';
  const locksScroll = doc.createElement('div');
  locksScroll.className = 'table-scroll';
  const locksTable = doc.createElement('table');
  locksTable.className = 'data-table';
  const locksThead = doc.createElement('thead');
  const locksHRow = doc.createElement('tr');
  const locksThs = [doc.createElement('th'), doc.createElement('th'), doc.createElement('th')];
  locksHRow.append(...locksThs);
  locksThead.appendChild(locksHRow);
  const locksTbody = doc.createElement('tbody');
  locksTable.append(locksThead, locksTbody);
  locksScroll.appendChild(locksTable);
  const locksEmpty = doc.createElement('p');
  locksEmpty.className = 'empty-note';
  locksPlate.append(locksTitle, locksScroll, locksEmpty);

  const telPlate = doc.createElement('section');
  telPlate.className = 'board-region surface-plate';
  const telTitle = doc.createElement('h2');
  telTitle.className = 'region-title';
  const telScroll = doc.createElement('div');
  telScroll.className = 'table-scroll';
  const telTable = doc.createElement('table');
  telTable.className = 'data-table';
  const telThead = doc.createElement('thead');
  const telHRow = doc.createElement('tr');
  const telThs = [
    doc.createElement('th'), doc.createElement('th'), doc.createElement('th'),
    doc.createElement('th'), doc.createElement('th'),
  ];
  telHRow.append(...telThs);
  telThead.appendChild(telHRow);
  const telTbody = doc.createElement('tbody');
  telTable.append(telThead, telTbody);
  telScroll.appendChild(telTable);
  const telEmpty = doc.createElement('p');
  telEmpty.className = 'empty-note';
  telPlate.append(telTitle, telScroll, telEmpty);

  container.append(rosterPlate, locksPlate, telPlate);

  container._squadRefs = {
    rosterTitle, filterBtns, squadList,
    locksTitle, locksThs, locksScroll, locksTbody, locksEmpty,
    telTitle, telThs, telScroll, telTbody, telEmpty,
  };
  return container._squadRefs;
}

export function renderSquadBoard(container, state, { onAction, doc = globalThis.document } = {}) {
  if (!container || !doc) return;
  const refs = ensureScaffold(container, doc, onAction);
  const lang = state.lang || 'fa';

  setText(refs.rosterTitle, t('squad.title', {}, lang));
  const activeFilter = state.squadFilter || 'ALL';
  const filterLabels = {
    ALL: 'filter.all',
    SUPERVISORS: 'filter.supervisors',
    QA: 'filter.qa',
    WORKERS: 'filter.workers',
  };
  for (const [fk, btn] of refs.filterBtns.entries()) {
    btn.classList.toggle('is-selected', activeFilter === fk);
    setText(btn, t(filterLabels[fk], {}, lang));
  }

  const byId = new Map((state.agents || []).map((a) => [normalizeRoleId(a.id), a]));
  const roster = CANONICAL_ROLES.map((r) => ({ ...r, ...(byId.get(r.id) || {}) }))
    .filter((r) => matchesTier(r, activeFilter));

  const roleCaps = state.thinkTank?.roleCaps || { main: 50, manager: 50, subagents: 50 };

  patchKeyedChildren(
    refs.squadList,
    roster,
    (ag) => ag.id,
    (ag) => {
      const row = doc.createElement('article');
      row.className = 'squad-row';

      const ident = doc.createElement('div');
      ident.className = 'squad-ident';

      const iconFrame = doc.createElement('span');
      iconFrame.className = 'role-icon-frame';
      setAttr(iconFrame, 'data-shape', ag.frameShape);
      const svg = createSvgEl(doc, 'svg', { width: '16', height: '16', viewBox: '0 0 16 16', 'aria-hidden': 'true' });
      svg.appendChild(createSvgEl(doc, 'path', {
        d: ag.glyph, fill: 'none', stroke: 'currentColor', 'stroke-width': '1.4', 'stroke-linecap': 'round', 'stroke-linejoin': 'round',
      }));
      iconFrame.appendChild(svg);

      const mono = doc.createElement('span');
      mono.className = 'role-mono';
      setAttr(mono, 'data-shape', ag.frameShape);
      setText(mono, ag.monogram);

      const details = doc.createElement('div');
      details.className = 'squad-details';
      const titleEl = doc.createElement('div');
      titleEl.className = 'squad-title';
      const specEl = doc.createElement('div');
      specEl.className = 'squad-spec';
      const taskEl = doc.createElement('div');
      taskEl.className = 'squad-task';
      details.append(titleEl, specEl, taskEl);
      ident.append(iconFrame, mono, details);

      const meta = doc.createElement('div');
      meta.className = 'squad-meta';
      const statusTag = doc.createElement('span');
      statusTag.className = 'status-tag';
      const verifiedTag = doc.createElement('span');
      verifiedTag.className = 'status-tag';
      verifiedTag.setAttribute('data-tone', 'verified');
      const toolCode = doc.createElement('code');
      toolCode.className = 'code-id';
      const meter = doc.createElement('span');
      meter.className = 'turn-meter';
      const meterFill = doc.createElement('span');
      meterFill.className = 'turn-meter-fill';
      meter.appendChild(meterFill);
      const turnsCode = doc.createElement('span');
      turnsCode.className = 'code-id';
      const msgBtn = doc.createElement('button');
      msgBtn.type = 'button';
      msgBtn.className = 'btn btn-quiet btn-compact';
      const inspBtn = doc.createElement('button');
      inspBtn.type = 'button';
      inspBtn.className = 'btn btn-quiet btn-compact';
      meta.append(statusTag, verifiedTag, toolCode, meter, turnsCode, msgBtn, inspBtn);

      msgBtn.addEventListener('click', () => onAction?.({ type: 'MESSAGE_ROLE', roleId: row.getAttribute('data-role-id') }));
      inspBtn.addEventListener('click', () => onAction?.({ type: 'INSPECT', target: { type: 'role', id: row.getAttribute('data-role-id') } }));

      row.append(ident, meta);
      row._refs = { titleEl, specEl, taskEl, statusTag, verifiedTag, toolCode, meterFill, turnsCode, msgBtn, inspBtn };
      return row;
    },
    (row, ag) => {
      const r = row._refs;
      setText(r.titleEl, roleTitle(ag.id, lang, false));
      setText(r.specEl, ag.specialty?.[lang] || ag.specialty?.en || '');
      const taskText = ag.currentTask || ag.task || '';
      r.taskEl.hidden = !taskText;
      setText(r.taskEl, taskText);

      const st = String(ag.status || 'IDLE').toUpperCase();
      setText(r.statusTag, stateLabel(st, lang));
      setAttr(r.statusTag, 'data-tone', toneForState(st));

      r.verifiedTag.hidden = !ag.verifiedSubagent;
      setText(r.verifiedTag, t('cmd.verifiedSubagent', {}, lang));

      const toolText = ag.activeTool || ag.tool || '';
      r.toolCode.hidden = !toolText;
      setText(r.toolCode, toolText);

      const cap = capForRole(ag.id, roleCaps);
      const used = Number(ag.turnsUsed || 0);
      const ratio = Math.max(0, Math.min(1, used / Math.max(1, cap)));
      r.meterFill.style.setProperty('--meter-scale', ratio.toFixed(3));
      setText(r.turnsCode, `${formatNum(used, lang)}/${formatNum(cap, lang)}`);

      setText(r.msgBtn, t('squad.messageRole', {}, lang));
      setText(r.inspBtn, t('squad.inspectRole', {}, lang));
    },
    'data-role-id',
  );

  setText(refs.locksTitle, t('squad.locksTitle', {}, lang));
  ['squad.colPath', 'cmd.colOwner', 'squad.colWorkItem'].forEach((k, i) => setText(refs.locksThs[i], t(k, {}, lang)));
  const locks = Array.isArray(state.fileLocks) ? state.fileLocks : [];
  refs.locksScroll.hidden = locks.length === 0;
  refs.locksEmpty.hidden = locks.length > 0;
  setText(refs.locksEmpty, t('squad.locksEmpty', {}, lang));
  patchKeyedChildren(
    refs.locksTbody,
    locks,
    (lk) => `${lk.path}::${lk.owner}`,
    () => {
      const tr = doc.createElement('tr');
      const tdPath = doc.createElement('td');
      const codePath = doc.createElement('code');
      codePath.className = 'file-path';
      tdPath.appendChild(codePath);
      const tdOwner = doc.createElement('td');
      const ownerMono = doc.createElement('span');
      ownerMono.className = 'role-mono';
      const ownerTitle = doc.createElement('span');
      const ownerWrap = doc.createElement('div');
      ownerWrap.className = 'role-pair';
      ownerWrap.append(ownerMono, ownerTitle);
      tdOwner.appendChild(ownerWrap);
      const tdWork = doc.createElement('td');
      const workCode = doc.createElement('code');
      workCode.className = 'code-id';
      tdWork.appendChild(workCode);
      tr.append(tdPath, tdOwner, tdWork);
      tr._refs = { codePath, ownerMono, ownerTitle, workCode };
      return tr;
    },
    (tr, lk) => {
      const ownerId = normalizeRoleId(lk.owner || '');
      setText(tr._refs.codePath, lk.path || '');
      setText(tr._refs.ownerMono, roleMonogram(ownerId));
      setAttr(tr._refs.ownerMono, 'data-shape', getRoleMeta(ownerId)?.frameShape || 'circle');
      setText(tr._refs.ownerTitle, roleTitle(ownerId, lang, true));
      setText(tr._refs.workCode, lk.workItemId || '-');
    },
    'data-lock-key',
  );

  setText(refs.telTitle, t('squad.telemetryTitle', {}, lang));
  ['squad.colStep', 'cmd.colOwner', 'squad.colTool', 'cmd.colStatus', 'squad.colTime'].forEach((k, i) => setText(refs.telThs[i], t(k, {}, lang)));
  const toolCalls = (state.telemetry?.toolCalls || []).slice(0, 30);
  refs.telScroll.hidden = toolCalls.length === 0;
  refs.telEmpty.hidden = toolCalls.length > 0;
  setText(refs.telEmpty, t('squad.telemetryEmpty', {}, lang));
  patchKeyedChildren(
    refs.telTbody,
    toolCalls,
    (tc, i) => tc.id || `${tc.timestamp || ''}-${tc.tool || ''}-${i}`,
    () => {
      const tr = doc.createElement('tr');
      const tdStep = doc.createElement('td');
      tdStep.className = 'seq-num';
      const tdAgent = doc.createElement('td');
      const tdTool = doc.createElement('td');
      const toolCode = doc.createElement('code');
      toolCode.className = 'code-id';
      tdTool.appendChild(toolCode);
      const tdStatus = doc.createElement('td');
      const stTag = doc.createElement('span');
      stTag.className = 'status-tag';
      tdStatus.appendChild(stTag);
      const tdTime = doc.createElement('td');
      tdTime.className = 'code-id';
      tr.append(tdStep, tdAgent, tdTool, tdStatus, tdTime);
      tr._refs = { tdStep, tdAgent, toolCode, stTag, tdTime };
      return tr;
    },
    (tr, tc, idx) => {
      const agentId = normalizeRoleId(tc.agentId || tc.agent || '');
      setText(tr._refs.tdStep, formatNum(idx + 1, lang));
      setText(tr._refs.tdAgent, agentId ? `${roleMonogram(agentId)} ${roleTitle(agentId, lang, true)}` : (tc.agentName || '-'));
      setText(tr._refs.toolCode, tc.tool || '-');
      const st = String(tc.status || (tc.success === false ? 'FAILED' : 'DONE')).toUpperCase();
      setText(tr._refs.stTag, stateLabel(st, lang));
      setAttr(tr._refs.stTag, 'data-tone', toneForState(st));
      setText(tr._refs.tdTime, tc.timestamp || '-');
    },
    'data-tel-key',
  );
}
