import { createSvgEl, setAttr, setText } from './dom.mjs';
import { actionLabel, formatNum, stateLabel, t, toneForState } from './i18n.mjs';
import { getRoleMeta, normalizeRoleId, roleMonogram, roleTitle } from './roles.mjs';

function el(doc, tag, className, text) {
  const node = doc.createElement(tag);
  if (className) node.className = className;
  if (text !== undefined && text !== null) setText(node, text);
  return node;
}

function kvRow(doc, label, value) {
  const row = el(doc, 'div', 'dossier-kv');
  row.append(el(doc, 'span', 'field-label', label), el(doc, 'span', '', value));
  return row;
}

export function renderDossierDrawer(container, state, { onAction, doc = globalThis.document } = {}) {
  if (!container || !doc) return;
  const target = state.inspector;
  if (!target) {
    container.hidden = true;
    return;
  }
  container.hidden = false;
  container.innerHTML = '';
  const lang = state.lang || 'fa';

  const head = el(doc, 'div', 'dossier-head');
  const titleEl = el(doc, 'h2', 'region-title');
  const closeBtn = el(doc, 'button', 'btn btn-quiet btn-compact', t('insp.close', {}, lang));
  closeBtn.type = 'button';
  closeBtn.addEventListener('click', () => onAction?.({ type: 'CLOSE_INSPECTOR' }));
  head.append(titleEl, closeBtn);
  container.appendChild(head);

  const body = el(doc, 'div', 'dossier-body');

  if (target.type === 'finding') {
    const f = (state.findings || []).find((it) => String(it.id).toUpperCase() === String(target.id).toUpperCase());
    if (!f) {
      setText(titleEl, String(target.id || 'Finding'));
      body.appendChild(el(doc, 'p', 'empty-note', t('cmd.findingsEmpty', {}, lang)));
      container.appendChild(body);
      return;
    }
    setText(titleEl, `${f.id} — ${f.title || ''}`);

    const summarySec = el(doc, 'div', 'dossier-section');
    const tags = el(doc, 'div', 'dossier-actions');
    const sevTag = el(doc, 'span', 'status-tag', String(f.severity || 'MEDIUM').toUpperCase());
    setAttr(sevTag, 'data-tone', toneForState(f.severity));
    const stTag = el(doc, 'span', 'status-tag', stateLabel(f.state, lang));
    setAttr(stTag, 'data-tone', toneForState(f.state));
    tags.append(sevTag, stTag);
    summarySec.appendChild(tags);
    summarySec.appendChild(kvRow(doc, t('cmd.colOwner', {}, lang), `${roleMonogram(f.raisedBy)} -> ${roleMonogram(f.owner)} (${roleTitle(f.owner, lang, true)})`));
    summarySec.appendChild(kvRow(doc, t('pipe.round', { round: f.round || 1, max: state.thinkTank?.maxRounds || 50 }, lang), `x${formatNum(f.returnCount || 0, lang)}`));
    if (f.wontFixReason) {
      summarySec.appendChild(el(doc, 'p', 'dossier-text', f.wontFixReason));
    }
    body.appendChild(summarySec);

    if (f.reproSteps) {
      const reproSec = el(doc, 'div', 'dossier-section');
      reproSec.appendChild(el(doc, 'h3', 'sub-heading', t('insp.repro', {}, lang)));
      reproSec.appendChild(el(doc, 'p', 'dossier-text', f.reproSteps));
      body.appendChild(reproSec);
    }

    const evSec = el(doc, 'div', 'dossier-section');
    evSec.appendChild(el(doc, 'h3', 'sub-heading', t('insp.evidence', {}, lang)));
    const evidence = Array.isArray(f.evidence) ? f.evidence : [];
    if (!evidence.length) {
      evSec.appendChild(el(doc, 'p', 'empty-note', '-'));
    } else {
      for (const ev of evidence) {
        const box = el(doc, 'div', 'evidence-item');
        const evTop = el(doc, 'div', 'dossier-kv');
        const rawCode = ev?.exitCode;
        const hasCode = rawCode !== null && rawCode !== undefined && rawCode !== '';
        const pass = hasCode && Number(rawCode) === 0;
        const codeTag = el(doc, 'span', 'status-tag', hasCode ? `exit ${formatNum(rawCode, lang)}` : 'FAIL');
        setAttr(codeTag, 'data-tone', pass ? 'verified' : 'open');
        const runnerText = ev.runnerReason ? `${ev.runner || 'substrate'} (${ev.runnerReason})` : (ev.runner || 'substrate');
        evTop.append(codeTag, el(doc, 'code', 'code-id', runnerText));
        box.appendChild(evTop);
        if (ev.command) box.appendChild(el(doc, 'pre', 'cmd-snippet', ev.command));
        if (ev.excerpt) box.appendChild(el(doc, 'pre', 'cmd-snippet', ev.excerpt));
        if (ev.stdoutHash) box.appendChild(el(doc, 'code', 'code-id', String(ev.stdoutHash).slice(0, 20)));
        evSec.appendChild(box);
      }
    }
    body.appendChild(evSec);

    if (Array.isArray(f.events) && f.events.length) {
      const chSec = el(doc, 'div', 'dossier-section');
      chSec.appendChild(el(doc, 'h3', 'sub-heading', t('insp.eventsChain', {}, lang)));
      const chain = el(doc, 'div', 'dossier-chain');
      for (const seqVal of f.events) {
        const btn = el(doc, 'button', 'btn btn-quiet btn-compact seq-num', `#${formatNum(seqVal, lang)}`);
        btn.type = 'button';
        btn.addEventListener('click', () => onAction?.({ type: 'INSPECT', target: { type: 'event', seq: Number(seqVal) } }));
        chain.appendChild(btn);
      }
      chSec.appendChild(chain);
      body.appendChild(chSec);
    }

    if (!state.thinkTank?.isClosed && !['Closed', 'WontFix'].includes(f.state)) {
      const wfForm = el(doc, 'form', 'dossier-section');
      const lbl = el(doc, 'label', 'field-group');
      lbl.appendChild(el(doc, 'span', 'field-label', t('insp.wontFixLabel', {}, lang)));
      const reasonInput = doc.createElement('input');
      reasonInput.type = 'text';
      reasonInput.className = 'field-input';
      reasonInput.required = true;
      lbl.appendChild(reasonInput);
      const actRow = el(doc, 'div', 'dossier-actions');
      const submitBtn = el(doc, 'button', 'btn btn-danger-outline btn-compact', t('insp.wontFixBtn', {}, lang));
      submitBtn.type = 'submit';
      const pinBtn = el(doc, 'button', 'btn btn-quiet btn-compact', t('cmd.pinImportant', {}, lang));
      pinBtn.type = 'button';
      pinBtn.addEventListener('click', () => onAction?.({ type: 'FINDING_ACTION', findingId: f.id, action: 'mark_important' }));
      actRow.append(submitBtn, pinBtn);
      wfForm.append(lbl, actRow);
      wfForm.addEventListener('submit', (ev) => {
        ev.preventDefault();
        const reason = reasonInput.value.trim();
        if (!reason) return;
        onAction?.({ type: 'FINDING_ACTION', findingId: f.id, action: 'wontfix', reason });
      });
      body.appendChild(wfForm);
    }
  } else if (target.type === 'edge') {
    const fromId = normalizeRoleId(target.from);
    const toId = normalizeRoleId(target.to);
    setText(titleEl, `${t('insp.edgeTitle', {}, lang)}: ${roleMonogram(fromId)} -> ${roleMonogram(toId)}`);
    const headSec = el(doc, 'div', 'dossier-section');
    headSec.appendChild(kvRow(doc, roleTitle(fromId, lang, true), roleTitle(toId, lang, true)));
    body.appendChild(headSec);

    const matching = (state.interactions || []).filter((it) => {
      if (state.replay?.active && state.replay.cursorSeq !== null && Number(it.seq || 0) > state.replay.cursorSeq) return false;
      return normalizeRoleId(it.from || it.senderRole) === fromId && normalizeRoleId(it.to || it.recipientRole) === toId;
    });
    if (!matching.length) {
      body.appendChild(el(doc, 'p', 'empty-note', t('chron.empty', {}, lang)));
    } else {
      for (const it of matching) {
        const sec = el(doc, 'div', 'dossier-section');
        const top = el(doc, 'div', 'dossier-kv');
        const seqBtn = el(doc, 'button', 'btn btn-quiet btn-compact seq-num', `#${formatNum(it.seq || 0, lang)}`);
        seqBtn.type = 'button';
        seqBtn.addEventListener('click', () => onAction?.({ type: 'INSPECT', target: { type: 'event', seq: Number(it.seq || 0) } }));
        const actTag = el(doc, 'span', 'status-tag', actionLabel(it.action || it.requestType, lang));
        setAttr(actTag, 'data-tone', toneForState(it.action));
        top.append(seqBtn, actTag, el(doc, 'span', 'code-id', it.timestamp || ''));
        sec.appendChild(top);
        if (it.findingId) {
          const fBtn = el(doc, 'button', 'btn btn-quiet btn-compact finding-id', it.findingId);
          fBtn.type = 'button';
          fBtn.addEventListener('click', () => onAction?.({ type: 'INSPECT', target: { type: 'finding', id: it.findingId } }));
          sec.appendChild(fBtn);
        }
        if (it.summary) sec.appendChild(el(doc, 'p', 'dossier-text', it.summary));
        body.appendChild(sec);
      }
    }
  } else if (target.type === 'event') {
    const msgs = state.messages || [];
    const msg = msgs.find((m) => (target.id && m.id === target.id) || (target.seq && Number(m.seq) === Number(target.seq)));
    const inter = (state.interactions || []).find((it) => target.seq && Number(it.seq) === Number(target.seq));
    const item = msg || inter;
    setText(titleEl, `#${formatNum(target.seq || item?.seq || 0, lang)}`);
    if (!item) {
      body.appendChild(el(doc, 'p', 'empty-note', t('chron.empty', {}, lang)));
    } else {
      const fromId = normalizeRoleId(item.senderRole || item.senderCode || item.from || (item.isOperator ? 'user' : ''));
      const toId = normalizeRoleId(item.recipientRole || item.recipientCode || item.to || '');
      const metaSec = el(doc, 'div', 'dossier-section');
      metaSec.appendChild(kvRow(doc, t('cmd.colStatus', {}, lang), actionLabel(item.actionType || item.action, lang)));
      metaSec.appendChild(kvRow(doc, t('cmd.colOwner', {}, lang), `${roleTitle(fromId, lang, true)}${toId ? ` -> ${roleTitle(toId, lang, true)}` : ''}`));
      if (item.timestamp) metaSec.appendChild(kvRow(doc, t('squad.colTime', {}, lang), item.timestamp));
      if (item.origin) metaSec.appendChild(kvRow(doc, 'origin', item.origin));
      if (item.findingId) {
        const fBtn = el(doc, 'button', 'btn btn-quiet btn-compact finding-id', item.findingId);
        fBtn.type = 'button';
        fBtn.addEventListener('click', () => onAction?.({ type: 'INSPECT', target: { type: 'finding', id: item.findingId } }));
        metaSec.appendChild(fBtn);
      }
      body.appendChild(metaSec);

      const contentText = item.content || item.summary || '';
      if (contentText) {
        const sec = el(doc, 'div', 'dossier-section');
        sec.appendChild(el(doc, 'p', 'dossier-text', contentText));
        body.appendChild(sec);
      }
      for (const extraText of [item.thoughts, item.critique, item.question, item.report]) {
        if (!extraText) continue;
        const sec = el(doc, 'div', 'dossier-section');
        sec.appendChild(el(doc, 'p', 'dossier-text', extraText));
        body.appendChild(sec);
      }
    }
  } else if (target.type === 'role') {
    const rid = normalizeRoleId(target.id);
    const meta = getRoleMeta(rid);
    const live = (state.agents || []).find((a) => normalizeRoleId(a.id) === rid) || {};
    setText(titleEl, roleTitle(rid, lang, false));

    const profSec = el(doc, 'div', 'dossier-section');
    const ident = el(doc, 'div', 'role-pair');
    const frame = el(doc, 'span', 'role-icon-frame');
    setAttr(frame, 'data-shape', meta?.frameShape || 'circle');
    if (meta?.glyph) {
      const svg = createSvgEl(doc, 'svg', { width: '16', height: '16', viewBox: '0 0 16 16', 'aria-hidden': 'true' });
      svg.appendChild(createSvgEl(doc, 'path', {
        d: meta.glyph, fill: 'none', stroke: 'currentColor', 'stroke-width': '1.4', 'stroke-linecap': 'round', 'stroke-linejoin': 'round',
      }));
      frame.appendChild(svg);
    }
    const mono = el(doc, 'span', 'role-mono', roleMonogram(rid));
    setAttr(mono, 'data-shape', meta?.frameShape || 'circle');
    const stTag = el(doc, 'span', 'status-tag', stateLabel(live.status || 'IDLE', lang));
    setAttr(stTag, 'data-tone', toneForState(live.status || 'IDLE'));
    ident.append(frame, mono, stTag);
    profSec.appendChild(ident);
    if (meta?.specialty) profSec.appendChild(el(doc, 'p', 'dossier-text', meta.specialty[lang] || meta.specialty.en));
    if (live.verifiedSubagent) profSec.appendChild(kvRow(doc, t('cmd.verifiedSubagent', {}, lang), live.subagentConvId || 'subagent'));
    if (live.activeTool || live.tool) profSec.appendChild(kvRow(doc, t('squad.colTool', {}, lang), live.activeTool || live.tool));
    if (live.currentTask || live.task) profSec.appendChild(el(doc, 'p', 'dossier-text', live.currentTask || live.task));
    const msgBtn = el(doc, 'button', 'btn btn-primary btn-compact', t('squad.messageRole', {}, lang));
    msgBtn.type = 'button';
    msgBtn.addEventListener('click', () => onAction?.({ type: 'MESSAGE_ROLE', roleId: rid }));
    profSec.appendChild(msgBtn);
    body.appendChild(profSec);

    if (Array.isArray(meta?.skills) && meta.skills.length) {
      const skSec = el(doc, 'div', 'dossier-section');
      skSec.appendChild(el(doc, 'h3', 'sub-heading', t('insp.roleSkills', {}, lang)));
      const wrap = el(doc, 'div', 'skills-wrap');
      for (const sk of meta.skills) wrap.appendChild(el(doc, 'span', 'status-tag', sk));
      skSec.appendChild(wrap);
      body.appendChild(skSec);
    }

    const roleTasks = (state.subtasks || []).filter((s) => normalizeRoleId(s.assignee) === rid);
    if (roleTasks.length) {
      const tSec = el(doc, 'div', 'dossier-section');
      tSec.appendChild(el(doc, 'h3', 'sub-heading', t('cmd.wbsTitle', {}, lang)));
      for (const st of roleTasks) {
        tSec.appendChild(kvRow(doc, st.id || '-', `${st.title || ''} (${stateLabel(st.status, lang)})`));
      }
      body.appendChild(tSec);
    }

    const roleLocks = (state.fileLocks || []).filter((l) => normalizeRoleId(l.owner) === rid);
    if (roleLocks.length) {
      const lSec = el(doc, 'div', 'dossier-section');
      lSec.appendChild(el(doc, 'h3', 'sub-heading', t('squad.locksTitle', {}, lang)));
      const chips = el(doc, 'div', 'file-chips');
      for (const lk of roleLocks) chips.appendChild(el(doc, 'code', 'file-chip file-path', lk.path));
      lSec.appendChild(chips);
      body.appendChild(lSec);
    }
  }

  container.appendChild(body);
}

export function renderSettingsSheet(dialogEl, state, { onAction, doc = globalThis.document } = {}) {
  if (!dialogEl || !doc) return;
  const backdrop = dialogEl.parentElement;
  if (!state.settingsOpen) {
    if (backdrop) backdrop.hidden = true;
    return;
  }
  if (backdrop) backdrop.hidden = false;

  const lang = state.lang || 'fa';
  dialogEl.innerHTML = '';

  const head = el(doc, 'div', 'dossier-head');
  const title = el(doc, 'h2', 'region-title', t('set.title', {}, lang));
  title.id = 'settings-title';
  const closeBtn = el(doc, 'button', 'btn btn-quiet btn-compact', t('insp.close', {}, lang));
  closeBtn.type = 'button';
  closeBtn.addEventListener('click', () => onAction?.({ type: 'CLOSE_SETTINGS' }));
  head.append(title, closeBtn);
  dialogEl.appendChild(head);

  if (state.settingsError) {
    dialogEl.appendChild(el(doc, 'div', 'error-notice', state.settingsError));
  }

  const casesSec = el(doc, 'section', 'settings-section');
  casesSec.appendChild(el(doc, 'h3', 'sub-heading', t('set.casesHeading', {}, lang)));
  const searchInput = doc.createElement('input');
  searchInput.type = 'search';
  searchInput.className = 'field-input';
  searchInput.placeholder = t('set.searchCase', {}, lang);
  const casesActions = el(doc, 'div', 'dossier-actions');
  const syncBtn = el(doc, 'button', 'btn btn-quiet btn-compact', t('state.syncTab', {}, lang));
  syncBtn.type = 'button';
  syncBtn.addEventListener('click', () => onAction?.({ type: 'SYNC_ACTIVE_TAB' }));
  const newRunBtn = el(doc, 'button', 'btn btn-quiet btn-compact', t('header.newRun', {}, lang));
  newRunBtn.type = 'button';
  newRunBtn.addEventListener('click', () => onAction?.({ type: 'NEW_RUN' }));
  casesActions.append(syncBtn, newRunBtn);

  const casesList = el(doc, 'div', 'settings-cases-list');
  const renderCases = () => {
    const q = searchInput.value.trim().toLowerCase();
    casesList.innerHTML = '';
    const list = (state.conversationsList || []).filter((c) => {
      if (!q) return true;
      return `${c.project || ''} ${c.convId || c.id || ''}`.toLowerCase().includes(q);
    });
    for (const c of list) {
      const cid = c.convId || c.id;
      const row = el(doc, 'button', 'recent-case-row');
      row.type = 'button';
      const label = `${c.project || cid} (#${formatNum(c.runIndex || 1, lang)})`;
      row.append(el(doc, 'span', '', label), el(doc, 'span', 'status-tag', c.isClosed ? t('conn.closed', {}, lang) : t('conn.live', {}, lang)));
      row.addEventListener('click', () => onAction?.({ type: 'SWITCH_CASE', convId: cid }));
      casesList.appendChild(row);
    }
  };
  searchInput.addEventListener('input', renderCases);
  renderCases();
  casesSec.append(searchInput, casesActions, casesList);
  dialogEl.appendChild(casesSec);

  const metaForm = el(doc, 'form', 'settings-section');
  metaForm.appendChild(el(doc, 'h3', 'sub-heading', t('set.metaHeading', {}, lang)));
  const projGroup = el(doc, 'label', 'field-group');
  projGroup.appendChild(el(doc, 'span', 'field-label', t('state.projectLabel', {}, lang)));
  const projInput = doc.createElement('input');
  projInput.type = 'text';
  projInput.className = 'field-input';
  projInput.value = state.thinkTank?.project || '';
  projGroup.appendChild(projInput);

  const dirGroup = el(doc, 'label', 'field-group');
  dirGroup.appendChild(el(doc, 'span', 'field-label', t('state.directiveLabel', {}, lang)));
  const dirInput = doc.createElement('input');
  dirInput.type = 'text';
  dirInput.className = 'field-input';
  dirInput.value = state.thinkTank?.directive || '';
  dirGroup.appendChild(dirInput);

  const saveMetaBtn = el(doc, 'button', 'btn btn-quiet btn-compact', t('set.saveMeta', {}, lang));
  saveMetaBtn.type = 'submit';
  metaForm.append(projGroup, dirGroup, saveMetaBtn);
  metaForm.addEventListener('submit', (ev) => {
    ev.preventDefault();
    onAction?.({ type: 'UPDATE_META', project: projInput.value.trim(), directive: dirInput.value.trim() });
  });
  dialogEl.appendChild(metaForm);

  const govSec = el(doc, 'section', 'settings-section');
  govSec.appendChild(el(doc, 'h3', 'sub-heading', t('set.govHeading', {}, lang)));
  const govBtns = el(doc, 'div', 'dossier-actions');
  const extendBtn = el(doc, 'button', 'btn btn-quiet btn-compact', t('set.extendRounds', {}, lang));
  extendBtn.type = 'button';
  extendBtn.disabled = Boolean(state.thinkTank?.isClosed);
  extendBtn.addEventListener('click', () => onAction?.({ type: 'EXTEND_ROUNDS' }));

  const compOrReopen = el(
    doc,
    'button',
    'btn btn-primary btn-compact',
    state.thinkTank?.isClosed ? t('cmd.reopenBtn', {}, lang) : t('set.completeCase', {}, lang),
  );
  compOrReopen.type = 'button';
  compOrReopen.addEventListener('click', () => {
    onAction?.({ type: state.thinkTank?.isClosed ? 'REOPEN_CASE' : 'COMPLETE_CASE' });
  });
  govBtns.append(extendBtn, compOrReopen);
  govSec.appendChild(govBtns);

  if (!state.thinkTank?.isClosed) {
    const forceForm = el(doc, 'form', 'dossier-actions');
    const forceInput = doc.createElement('input');
    forceInput.type = 'text';
    forceInput.className = 'field-input';
    forceInput.placeholder = t('set.forceReason', {}, lang);
    forceInput.required = true;
    const forceBtn = el(doc, 'button', 'btn btn-danger-outline btn-compact', t('set.forceConfirm', {}, lang));
    forceBtn.type = 'submit';
    forceForm.append(forceInput, forceBtn);
    forceForm.addEventListener('submit', (ev) => {
      ev.preventDefault();
      const reason = forceInput.value.trim();
      if (!reason) return;
      onAction?.({ type: 'FORCE_CLOSE', reason });
    });
    govSec.appendChild(forceForm);
  }
  dialogEl.appendChild(govSec);

  const capsForm = el(doc, 'form', 'settings-section');
  capsForm.appendChild(el(doc, 'h3', 'sub-heading', t('set.capsHeading', {}, lang)));
  const capsGrid = el(doc, 'div', 'caps-grid');
  const caps = state.thinkTank?.roleCaps || { main: 50, manager: 50, subagents: 50 };
  const capInputs = {};
  for (const [key, labelText] of [
    ['main', roleTitle('main_agent', lang, true)],
    ['manager', roleTitle('team-manager', lang, true)],
    ['subagents', t('filter.workers', {}, lang)],
  ]) {
    const wrap = el(doc, 'label', 'field-group');
    wrap.appendChild(el(doc, 'span', 'field-label', labelText));
    const inp = doc.createElement('input');
    inp.type = 'number';
    inp.className = 'field-input';
    inp.min = '1';
    inp.max = '500';
    inp.value = String(caps[key] ?? 50);
    wrap.appendChild(inp);
    capsGrid.appendChild(wrap);
    capInputs[key] = inp;
  }
  const saveCapsBtn = el(doc, 'button', 'btn btn-quiet btn-compact', t('set.saveCaps', {}, lang));
  saveCapsBtn.type = 'submit';
  capsForm.append(capsGrid, saveCapsBtn);
  capsForm.addEventListener('submit', (ev) => {
    ev.preventDefault();
    onAction?.({
      type: 'SAVE_CAPS',
      roleCaps: {
        main: Number(capInputs.main.value || 50),
        manager: Number(capInputs.manager.value || 50),
        subagents: Number(capInputs.subagents.value || 50),
      },
    });
  });
  dialogEl.appendChild(capsForm);

  const devSec = el(doc, 'section', 'settings-section');
  const devLabel = el(doc, 'label', 'composer-check');
  const devCheck = doc.createElement('input');
  devCheck.type = 'checkbox';
  devCheck.checked = Boolean(state.devMode);
  devCheck.addEventListener('change', () => onAction?.({ type: 'TOGGLE_DEV_MODE', enabled: devCheck.checked }));
  devLabel.append(devCheck, el(doc, 'span', '', t('set.devMode', {}, lang)));
  devSec.appendChild(devLabel);
  if (state.devMode) {
    const snapPreview = {
      convId: state.convId,
      generation: state.generation,
      seq: state.seq,
      thinkTank: state.thinkTank,
      findingsCount: (state.findings || []).length,
      subtasksCount: (state.subtasks || []).length,
      graph: state.graph,
    };
    devSec.appendChild(el(doc, 'pre', 'cmd-snippet raw-json-pre', JSON.stringify(snapPreview, null, 2)));
  }
  dialogEl.appendChild(devSec);
}
