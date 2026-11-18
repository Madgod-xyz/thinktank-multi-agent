import { createSvgEl, patchKeyedChildren, setAttr, setText } from '../dom.mjs';
import { actionLabel, formatNum, t, toneForState } from '../i18n.mjs';
import { CANONICAL_ROLES, getRoleMeta, normalizeRoleId, roleMonogram, roleTitle } from '../roles.mjs';
import { edgeStrokeVar } from './topology-board.mjs';

const CHANNELS = ['ALL', 'FINDINGS', 'QA', 'SYNC', 'TASKS', 'COUNCIL', 'USER'];
const TARGET_ROLES = [
  'all', 'team-manager', 'council-critic', 'code-reviewer', 'qa-reviewer',
  'ui-frontend-designer', 'backend-auditor', 'ecommerce_seo_operator', 'wp_technical_operator', 'main_agent',
];

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

function buildUnifiedEvents(state) {
  const msgBySeq = new Map();
  const events = [];
  const messages = Array.isArray(state.messages) ? state.messages : [];
  for (let i = 0; i < messages.length; i += 1) {
    const m = messages[i];
    if (!m) continue;
    const seq = Number(m.seq || 0);
    const sender = normalizeRoleId(m.senderRole || m.senderCode) || (m.isOperator ? 'user' : 'main_agent');
    const recipient = normalizeRoleId(m.recipientRole || m.recipientCode || m.recipient || (m.mentions && m.mentions[0]) || '');
    const ev = {
      key: m.id || (seq ? `msg-seq-${seq}` : `msg-idx-${i}`),
      id: m.id || '',
      seq,
      from: m.isOperator ? 'user' : sender,
      to: recipient,
      action: String(m.actionType || m.requestType || 'MESSAGE').toUpperCase(),
      channel: String(m.channel || 'MAIN').toUpperCase(),
      findingId: m.findingId || '',
      workItemId: m.workItemId || '',
      content: m.content || '',
      summary: String(m.content || '').split('\n')[0].slice(0, 120),
      thoughts: m.thoughts || m.thought || '',
      critique: m.critique || m.counterArgument || '',
      question: m.question || '',
      report: m.report || m.fullReport || '',
      timestamp: m.timestamp || '',
      isOperator: Boolean(m.isOperator || sender === 'user'),
      origin: m.origin || '',
    };
    if (seq) msgBySeq.set(seq, ev);
    events.push(ev);
  }

  for (const it of state.interactions || []) {
    if (!it) continue;
    const seq = Number(it.seq || 0);
    if (seq && msgBySeq.has(seq)) {
      const existing = msgBySeq.get(seq);
      if (!existing.to && it.to) existing.to = normalizeRoleId(it.to);
      continue;
    }
    const from = normalizeRoleId(it.from || it.senderRole) || 'main_agent';
    const to = normalizeRoleId(it.to || it.recipientRole);
    events.push({
      key: `int-${seq}-${from}-${to}`,
      id: '',
      seq,
      from,
      to,
      action: String(it.action || it.requestType || 'CHAT').toUpperCase(),
      channel: String(it.channel || 'SYNC').toUpperCase(),
      findingId: it.findingId || '',
      workItemId: it.workItemId || '',
      content: it.summary || it.label || '',
      summary: (it.summary || it.label || '').slice(0, 120),
      thoughts: '',
      critique: '',
      question: '',
      report: '',
      timestamp: it.timestamp || '',
      isOperator: from === 'user',
      origin: it.origin || '',
    });
  }

  return events.sort((a, b) => (a.seq - b.seq) || a.key.localeCompare(b.key));
}

function matchesChannel(ev, ch) {
  if (!ch || ch === 'ALL') return true;
  const act = ev.action;
  const evCh = ev.channel;
  if (ch === 'FINDINGS') {
    return ['RETURN_DEFECT', 'DEFECT_RETURN', 'WORKER_FIX', 'CRITIQUE'].includes(act)
      || Boolean(ev.findingId) || evCh === 'INTERROGATION';
  }
  if (ch === 'QA') return ['QA_DISPATCH', 'QA_REPORT', 'REVIEW_QUERY'].includes(act) || evCh === 'QA';
  if (ch === 'SYNC') return act === 'PEER_SYNC' || evCh === 'SYNC';
  if (ch === 'TASKS') {
    return ['ASSIGN_TASK', 'DELEGATE', 'ASSIGN_SUBTASK', 'SUBTASK_UPDATE', 'SUBTASKS_UPDATE'].includes(act)
      || Boolean(ev.workItemId) || evCh === 'SUBAGENTS';
  }
  if (ch === 'COUNCIL') {
    return ['PROPOSAL', 'COUNCIL_VOTE', 'VOTE', 'DECISION', 'GOVERNANCE', 'INTERROGATE', 'COMPLETE'].includes(act)
      || evCh === 'COUNCIL';
  }
  if (ch === 'USER') return ev.isOperator || ev.from === 'user' || act === 'USER_MESSAGE';
  return true;
}

function matchesQuery(ev, query, lang) {
  const q = String(query || '').trim().toLowerCase();
  if (!q) return true;
  const hay = [
    `#${ev.seq}`, ev.seq, ev.findingId, ev.workItemId, ev.action, actionLabel(ev.action, lang),
    ev.from, roleTitle(ev.from, lang, true), ev.to, roleTitle(ev.to, lang, true), ev.content,
  ].join(' ').toLowerCase();
  return hay.includes(q);
}

function activeSwimlaneRoles(events) {
  const present = new Set();
  for (const ev of events) {
    if (ev.from && ev.from !== 'all') present.add(ev.from);
    if (ev.to && ev.to !== 'all') present.add(ev.to);
  }
  const cols = [];
  if (present.has('user')) cols.push('user');
  for (const r of CANONICAL_ROLES) {
    if (present.has(r.id)) cols.push(r.id);
  }
  if (cols.length < 4) {
    for (const fallback of ['main_agent', 'team-manager', 'council-critic', 'code-reviewer']) {
      if (!cols.includes(fallback)) cols.push(fallback);
    }
  }
  return cols;
}

function ensureScaffold(container, doc, onAction) {
  if (container._chronRefs) return container._chronRefs;
  container.innerHTML = '';

  const stage = doc.createElement('section');
  stage.className = 'board-region surface-plate';

  const toolbar = doc.createElement('div');
  toolbar.className = 'chronicle-toolbar';
  const viewSwitch = doc.createElement('div');
  viewSwitch.className = 'view-switch';
  const btnSwim = doc.createElement('button');
  btnSwim.type = 'button';
  btnSwim.className = 'pill-filter';
  const btnFeed = doc.createElement('button');
  btnFeed.type = 'button';
  btnFeed.className = 'pill-filter';
  viewSwitch.append(btnSwim, btnFeed);

  btnSwim.addEventListener('click', () => onAction?.({ type: 'SET_CHRONICLE_VIEW', view: 'swimlane' }));
  btnFeed.addEventListener('click', () => onAction?.({ type: 'SET_CHRONICLE_VIEW', view: 'feed' }));

  const controls = doc.createElement('div');
  controls.className = 'chronicle-controls';
  const filterBar = doc.createElement('div');
  filterBar.className = 'filter-bar';
  const chBtns = new Map();
  for (const ch of CHANNELS) {
    const b = doc.createElement('button');
    b.type = 'button';
    b.className = 'pill-filter';
    b.addEventListener('click', () => onAction?.({ type: 'SET_CHRONICLE_CHANNEL', channel: ch }));
    filterBar.appendChild(b);
    chBtns.set(ch, b);
  }
  const searchInput = doc.createElement('input');
  searchInput.type = 'search';
  searchInput.className = 'field-input chronicle-search';
  searchInput.addEventListener('input', () => onAction?.({ type: 'SET_CHRONICLE_QUERY', query: searchInput.value }));
  controls.append(filterBar, searchInput);
  toolbar.append(viewSwitch, controls);

  const swimViewport = doc.createElement('div');
  swimViewport.className = 'swimlane-viewport';
  const swimHead = doc.createElement('div');
  swimHead.className = 'swimlane-head sticky-pin';
  const hSeq = doc.createElement('span');
  hSeq.className = 'seq-num';
  setText(hSeq, '#seq');
  const swimCols = doc.createElement('div');
  swimCols.className = 'swimlane-cols';
  const hAct = doc.createElement('span');
  swimHead.append(hSeq, swimCols, hAct);
  const swimList = doc.createElement('div');
  swimViewport.append(swimHead, swimList);

  const feedList = doc.createElement('div');
  feedList.className = 'feed-list';
  feedList.hidden = true;

  const emptyNote = doc.createElement('p');
  emptyNote.className = 'empty-note';

  stage.append(toolbar, swimViewport, feedList, emptyNote);

  const composer = doc.createElement('form');
  composer.className = 'steering-composer surface-plate';
  const compBar = doc.createElement('div');
  compBar.className = 'composer-bar';
  const compFromLabel = doc.createElement('span');
  compFromLabel.className = 'field-label';
  const compSelect = doc.createElement('select');
  compSelect.className = 'field-select btn-compact';
  for (const rid of TARGET_ROLES) {
    const opt = doc.createElement('option');
    opt.value = rid;
    compSelect.appendChild(opt);
  }
  compSelect.addEventListener('change', () => onAction?.({ type: 'SET_COMPOSER_TARGET', target: compSelect.value }));
  compBar.append(compFromLabel, compSelect);

  const compRow = doc.createElement('div');
  compRow.className = 'composer-row';
  const compTextarea = doc.createElement('textarea');
  compTextarea.className = 'field-textarea composer-input';
  compTextarea.rows = 2;
  const compSendBtn = doc.createElement('button');
  compSendBtn.type = 'submit';
  compSendBtn.className = 'btn btn-primary';
  compRow.append(compTextarea, compSendBtn);

  const compCheckLabel = doc.createElement('label');
  compCheckLabel.className = 'composer-check';
  const compForwardCheck = doc.createElement('input');
  compForwardCheck.type = 'checkbox';
  const compForwardSpan = doc.createElement('span');
  compCheckLabel.append(compForwardCheck, compForwardSpan);

  const submitChat = () => {
    const content = compTextarea.value.trim();
    if (!content) return;
    Promise.resolve(onAction?.({
      type: 'POST_USER_CHAT',
      content,
      targetRole: compSelect.value || 'all',
      forwardToHost: Boolean(compForwardCheck.checked),
    })).then((ok) => {
      if (ok !== false) compTextarea.value = '';
    });
  };
  composer.addEventListener('submit', (ev) => {
    ev.preventDefault();
    submitChat();
  });
  compTextarea.addEventListener('keydown', (ev) => {
    if ((ev.ctrlKey || ev.metaKey) && ev.key === 'Enter') {
      ev.preventDefault();
      submitChat();
    }
  });

  composer.append(compBar, compRow, compCheckLabel);
  container.append(stage, composer);

  container._chronRefs = {
    btnSwim, btnFeed, chBtns, searchInput,
    swimViewport, swimCols, hAct, swimList, feedList, emptyNote,
    compFromLabel, compSelect, compTextarea, compSendBtn, compForwardSpan,
  };
  return container._chronRefs;
}

export function renderChronicleBoard(container, state, { onAction, doc = globalThis.document } = {}) {
  if (!container || !doc) return;
  const refs = ensureScaffold(container, doc, onAction);
  const lang = state.lang || 'fa';
  const view = state.chronicleView === 'feed' ? 'feed' : 'swimlane';
  const activeCh = state.chronicleChannel || 'ALL';
  const query = state.chronicleQuery || '';

  refs.btnSwim.classList.toggle('is-selected', view === 'swimlane');
  refs.btnFeed.classList.toggle('is-selected', view === 'feed');
  setText(refs.btnSwim, t('chron.swimlane', {}, lang));
  setText(refs.btnFeed, t('chron.feed', {}, lang));

  for (const [ch, btn] of refs.chBtns.entries()) {
    btn.classList.toggle('is-selected', activeCh === ch);
    setText(btn, t(`ch.${ch}`, {}, lang));
  }
  refs.searchInput.placeholder = t('chron.searchPlaceholder', {}, lang);
  if (refs.searchInput.value !== query && doc.activeElement !== refs.searchInput) {
    refs.searchInput.value = query;
  }

  const allEvents = buildUnifiedEvents(state);
  const filtered = allEvents.filter((ev) => matchesChannel(ev, activeCh) && matchesQuery(ev, query, lang));

  refs.emptyNote.hidden = filtered.length > 0;
  setText(refs.emptyNote, t('chron.empty', {}, lang));
  refs.swimViewport.hidden = view !== 'swimlane' || filtered.length === 0;
  refs.feedList.hidden = view !== 'feed' || filtered.length === 0;

  if (view === 'swimlane') {
    const cols = activeSwimlaneRoles(filtered);
    const colIndex = new Map(cols.map((id, i) => [id, i]));
    refs.swimCols.style.setProperty('--swim-cols', String(cols.length));
    setText(refs.hAct, t('cmd.colStatus', {}, lang));

    patchKeyedChildren(
      refs.swimCols,
      cols,
      (rid) => rid,
      (rid) => {
        const mono = doc.createElement('span');
        mono.className = 'role-mono';
        setAttr(mono, 'data-shape', getRoleMeta(rid)?.frameShape || 'circle');
        return mono;
      },
      (mono, rid) => {
        setText(mono, roleMonogram(rid));
        setAttr(mono, 'title', roleTitle(rid, lang, false));
      },
      'data-role-col',
    );

    const colPct = (idx) => (((idx + 0.5) / cols.length) * 100).toFixed(4);
    patchKeyedChildren(
      refs.swimList,
      filtered,
      (ev) => ev.key,
      () => {
        const row = doc.createElement('div');
        row.className = 'swimlane-row';
        row.tabIndex = 0;
        row.setAttribute('role', 'button');

        const cSeq = doc.createElement('div');
        cSeq.className = 'swimlane-cell-seq';
        const seqSpan = doc.createElement('span');
        seqSpan.className = 'seq-num';
        const fidSpan = doc.createElement('span');
        fidSpan.className = 'finding-id';
        cSeq.append(seqSpan, fidSpan);

        const svg = createSvgEl(doc, 'svg', { class: 'swimlane-vector', overflow: 'visible', 'aria-hidden': 'true' });
        const guidesGroup = createSvgEl(doc, 'g');
        const line = createSvgEl(doc, 'line', { y1: '11', y2: '11', 'stroke-width': '1.6' });
        const tipSvg = createSvgEl(doc, 'svg', { y: '11', width: '1', height: '1', overflow: 'visible' });
        const head = createSvgEl(doc, 'polygon');
        tipSvg.appendChild(head);
        const nodeMark = createSvgEl(doc, 'circle', { cy: '11', r: '3.5' });
        svg.append(guidesGroup, line, tipSvg, nodeMark);

        const cAct = doc.createElement('div');
        cAct.className = 'swimlane-cell-action';
        const actTag = doc.createElement('span');
        actTag.className = 'status-tag';
        const sumEl = doc.createElement('span');
        sumEl.className = 'swimlane-summary';
        cAct.append(actTag, sumEl);

        row.append(cSeq, svg, cAct);
        row._refs = { seqSpan, fidSpan, svg, guidesGroup, line, tipSvg, head, nodeMark, actTag, sumEl };

        const openEv = () => {
          if (row._ev) onAction?.({ type: 'INSPECT', target: { type: 'event', seq: row._ev.seq, id: row._ev.id } });
        };
        row.addEventListener('click', openEv);
        row.addEventListener('keydown', (e) => {
          if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); openEv(); }
        });
        return row;
      },
      (row, ev) => {
        row._ev = ev;
        const r = row._refs;
        const isSel = state.inspector?.type === 'event'
          && ((ev.id && state.inspector?.id === ev.id) || (ev.seq && state.inspector?.seq === ev.seq));
        row.classList.toggle('is-selected', Boolean(isSel));

        setText(r.seqSpan, `#${formatNum(ev.seq || 0, lang)}`);
        r.fidSpan.hidden = !ev.findingId;
        setText(r.fidSpan, ev.findingId || '');

        patchKeyedChildren(
          r.guidesGroup,
          cols,
          (cid) => cid,
          () => createSvgEl(doc, 'line', { y1: '0', y2: '22', stroke: 'var(--color-rule)', 'stroke-width': '1' }),
          (gLine, _cid, idx) => {
            const pct = `${colPct(idx)}%`;
            setAttr(gLine, 'x1', pct);
            setAttr(gLine, 'x2', pct);
          },
          'data-guide',
        );

        const sIdx = colIndex.get(ev.from);
        const dIdx = colIndex.get(ev.to);
        const colorVar = edgeStrokeVar({ action: ev.action });
        if (sIdx !== undefined && dIdx !== undefined && sIdx !== dIdx) {
          const sxPct = `${colPct(sIdx)}%`;
          const dxPct = `${colPct(dIdx)}%`;
          const dir = dIdx > sIdx ? 1 : -1;
          r.line.removeAttribute('visibility');
          r.tipSvg.removeAttribute('visibility');
          r.nodeMark.setAttribute('visibility', 'hidden');
          setAttr(r.line, 'x1', sxPct);
          setAttr(r.line, 'x2', dxPct);
          setAttr(r.line, 'stroke', colorVar);
          setAttr(r.tipSvg, 'x', dxPct);
          setAttr(r.head, 'points', `0,0 ${-dir * 7},-4 ${-dir * 7},4`);
          setAttr(r.head, 'fill', colorVar);
        } else {
          const pxPct = `${colPct(sIdx ?? dIdx ?? 0)}%`;
          r.line.setAttribute('visibility', 'hidden');
          r.tipSvg.setAttribute('visibility', 'hidden');
          r.nodeMark.removeAttribute('visibility');
          setAttr(r.nodeMark, 'cx', pxPct);
          setAttr(r.nodeMark, 'fill', colorVar);
        }

        setText(r.actTag, actionLabel(ev.action, lang));
        setAttr(r.actTag, 'data-tone', toneForState(ev.action));
        setText(r.sumEl, ev.summary || '');
      },
      'data-ev-key',
    );
  } else {
    patchKeyedChildren(
      refs.feedList,
      filtered,
      (ev) => ev.key,
      () => {
        const card = doc.createElement('article');
        card.className = 'feed-row';
        card.tabIndex = 0;

        const head = doc.createElement('div');
        head.className = 'feed-head';
        const left = doc.createElement('div');
        left.className = 'feed-head-group';
        const seqSpan = doc.createElement('span');
        seqSpan.className = 'seq-num';
        const pair = doc.createElement('span');
        pair.className = 'role-pair';
        const fromMono = doc.createElement('span');
        fromMono.className = 'role-mono';
        const arrow = makeArrowIcon(doc);
        const toMono = doc.createElement('span');
        toMono.className = 'role-mono';
        pair.append(fromMono, arrow, toMono);
        const actTag = doc.createElement('span');
        actTag.className = 'status-tag';
        const fidSpan = doc.createElement('span');
        fidSpan.className = 'finding-id';
        left.append(seqSpan, pair, actTag, fidSpan);

        const timeCode = doc.createElement('span');
        timeCode.className = 'code-id';
        head.append(left, timeCode);

        const body = doc.createElement('div');
        body.className = 'feed-body';

        const details = doc.createElement('details');
        details.className = 'feed-details';
        const summary = doc.createElement('summary');
        const detailsBody = doc.createElement('div');
        detailsBody.className = 'feed-details-body';
        details.append(summary, detailsBody);

        card.append(head, body, details);
        card._refs = { seqSpan, fromMono, arrow, toMono, actTag, fidSpan, timeCode, body, details, summary, detailsBody };

        const openEv = (e) => {
          if (e?.target?.closest?.('details')) return;
          if (card._ev) onAction?.({ type: 'INSPECT', target: { type: 'event', seq: card._ev.seq, id: card._ev.id } });
        };
        card.addEventListener('click', openEv);
        card.addEventListener('keydown', (e) => {
          if (e.target.closest?.('details')) return;
          if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); openEv(e); }
        });
        return card;
      },
      (card, ev) => {
        card._ev = ev;
        const r = card._refs;
        const isSel = state.inspector?.type === 'event'
          && ((ev.id && state.inspector?.id === ev.id) || (ev.seq && state.inspector?.seq === ev.seq));
        card.classList.toggle('is-selected', Boolean(isSel));

        setText(r.seqSpan, `#${formatNum(ev.seq || 0, lang)}`);
        setText(r.fromMono, roleMonogram(ev.from));
        setAttr(r.fromMono, 'data-shape', getRoleMeta(ev.from)?.frameShape || 'circle');
        const hasTo = Boolean(ev.to && ev.to !== 'all');
        r.arrow.hidden = !hasTo;
        r.toMono.hidden = !hasTo;
        if (hasTo) {
          setText(r.toMono, roleMonogram(ev.to));
          setAttr(r.toMono, 'data-shape', getRoleMeta(ev.to)?.frameShape || 'circle');
        }
        setText(r.actTag, actionLabel(ev.action, lang));
        setAttr(r.actTag, 'data-tone', toneForState(ev.action));
        r.fidSpan.hidden = !ev.findingId;
        setText(r.fidSpan, ev.findingId || '');
        setText(r.timeCode, ev.timestamp || '');
        setText(r.body, ev.content || '');

        const extra = [ev.thoughts, ev.critique, ev.question, ev.report].filter(Boolean).join('\n\n');
        r.details.hidden = !extra;
        setText(r.summary, t('squad.inspectRole', {}, lang));
        setText(r.detailsBody, extra);
      },
      'data-ev-key',
    );
  }

  setText(refs.compFromLabel, t('chron.fromYou', {}, lang));
  for (const opt of Array.from(refs.compSelect.options)) {
    const rid = opt.value;
    setText(opt, rid === 'all' ? t('chron.targetAll', {}, lang) : `${roleMonogram(rid)} - ${roleTitle(rid, lang, true)}`);
  }
  const desiredTarget = state.composerTarget || 'all';
  if (refs.compSelect.value !== desiredTarget) refs.compSelect.value = desiredTarget;
  refs.compTextarea.placeholder = t('chron.placeholder', {}, lang);
  setText(refs.compSendBtn, t('chron.send', {}, lang));
  setText(refs.compForwardSpan, t('chron.forwardHost', {}, lang));
}
