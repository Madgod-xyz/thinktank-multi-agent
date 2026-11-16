import assert from 'node:assert/strict';
import { readdir, readFile, stat } from 'node:fs/promises';
import test from 'node:test';
import vm from 'node:vm';

const root = new URL('../', import.meta.url);
const pluginRoot = new URL('../../../', import.meta.url);
const html = await readFile(new URL('index.html', root), 'utf8');
const fonts = await readFile(new URL('fonts.css', root), 'utf8');
const appCss = await readFile(new URL('app.css', root), 'utf8');
const appJs = await readFile(new URL('app.js', root), 'utf8');
const i18nJs = await readFile(new URL('i18n.js', root), 'utf8');
const mainMjs = await readFile(new URL('main.mjs', root), 'utf8');
const roles = JSON.parse(await readFile(new URL('role_catalog.json', root), 'utf8'));

function extractCssVars(css, selectorPattern) {
  const vars = {};
  const re = new RegExp(`${selectorPattern}\\s*\\{([^{}]*)\\}`, 'gi');
  for (const match of css.matchAll(re)) {
    const body = match[1];
    for (const decl of body.matchAll(/(--[a-z0-9-]+)\s*:\s*([^;]+);/gi)) {
      vars[decl[1].trim()] = decl[2].trim();
    }
  }
  return vars;
}

function resolveCssVar(vars, name, seen = new Set()) {
  const raw = vars[name];
  if (!raw) return null;
  const varRef = /^var\(\s*(--[a-z0-9-]+)\s*\)$/i.exec(raw);
  if (!varRef) return raw;
  if (seen.has(name)) return null;
  seen.add(name);
  return resolveCssVar(vars, varRef[1], seen);
}

function parseHexColor(hex) {
  const m = /^#([0-9a-f]{3}|[0-9a-f]{6})$/i.exec((hex || '').trim());
  if (!m) return null;
  let h = m[1];
  if (h.length === 3) h = h.split('').map((c) => c + c).join('');
  return [
    parseInt(h.slice(0, 2), 16) / 255,
    parseInt(h.slice(2, 4), 16) / 255,
    parseInt(h.slice(4, 6), 16) / 255,
  ];
}

function relativeLuminance(rgb) {
  const lin = rgb.map((c) => (c <= 0.03928 ? c / 12.92 : ((c + 0.055) / 1.055) ** 2.4));
  return 0.2126 * lin[0] + 0.7152 * lin[1] + 0.0722 * lin[2];
}

function contrastRatio(fgHex, bgHex) {
  const fg = parseHexColor(fgHex);
  const bg = parseHexColor(bgHex);
  assert.ok(fg, `Expected valid hex foreground color, got ${fgHex}`);
  assert.ok(bg, `Expected valid hex background color, got ${bgHex}`);
  const l1 = relativeLuminance(fg);
  const l2 = relativeLuminance(bg);
  const [hi, lo] = l1 >= l2 ? [l1, l2] : [l2, l1];
  return (hi + 0.05) / (lo + 0.05);
}

test('UI loads bundled Vazirmatn & Outfit fonts cleanly without embedding font payloads in HTML', async () => {
  assert.ok(/href=["']\/?fonts\.css["']/i.test(html), 'index.html must load /fonts.css');
  assert.ok(!/data:font\//i.test(html), 'index.html must not embed inline font payloads');
  assert.ok(/font-family:\s*["']?Vazirmatn/i.test(fonts), 'fonts.css should register Vazirmatn');
  assert.ok(/font-family:\s*["']?Outfit/i.test(fonts), 'fonts.css should register Outfit');
  assert.ok(/font-display:\s*swap/i.test(fonts), 'fonts must use swap display');
  assert.ok(/data:font\/ttf;base64,/i.test(fonts), 'fonts.css should include base64 fallback data URIs');

  for (const file of ['Vazirmatn-Regular.ttf', 'Vazirmatn-Bold.ttf', 'Outfit-VariableFont_wght.ttf']) {
    const data = await readFile(new URL(`fonts/${file}`, root));
    assert.ok(data.length > 50_000, `${file} should be a bundled font asset`);
    assert.deepEqual([...data.subarray(0, 4)], [0, 1, 0, 0], `${file} should be a TrueType font`);
  }
});

test('Case Ledger CSS tokens, anti-AI-slop rules, and programmatic WCAG AA contrast (>= 4.5:1)', () => {
  assert.ok(!/--violet\b/i.test(appCss), 'Case Ledger forbids --violet token');
  assert.ok(!/#38bdf8\b/i.test(appCss), 'Case Ledger forbids #38bdf8 sky color');
  assert.ok(!/transition\s*:\s*all\b/i.test(appCss), 'Hallmark forbids transition: all');
  assert.ok(/:focus-visible/.test(appCss), 'interactive controls should define :focus-visible');
  assert.ok(/prefers-reduced-motion:\s*reduce/i.test(appCss), 'reduced-motion media query must exist');
  assert.ok(/overflow-x:\s*clip/i.test(appCss), 'root/body should guard horizontal overflow with clip');
  assert.ok(/@container\b/i.test(appCss), 'Sidecar layout must use @container queries');
  assert.ok(/font-family:\s*['"]Vazirmatn['"][^;]*!important/i.test(appCss), 'global RTL font stack should prioritize Vazirmatn');
  assert.ok(/font-family:\s*['"]Outfit['"],\s*['"]Vazirmatn['"]/i.test(appCss), 'LTR CSS must include Vazirmatn fallback');

  const darkVars = {
    ...extractCssVars(appCss, ':root'),
    ...extractCssVars(appCss, '(?:html)?\\[data-theme=["\']dark["\']\\]'),
  };
  const lightVars = extractCssVars(appCss, '(?:html)?\\[data-theme=["\']light["\']\\]');

  const catTokens = ['--cat-referral', '--cat-inquiry', '--cat-defect', '--cat-rewrite', '--cat-sync', '--cat-verify'];
  const requiredTokens = ['--paper', '--sheet', '--ink', '--ink-muted', '--open', '--working', '--review', '--verified', ...catTokens];
  for (const [themeName, vars] of [['dark', darkVars], ['light', lightVars]]) {
    for (const token of requiredTokens) {
      assert.ok(resolveCssVar(vars, token), `${themeName} theme must define ${token}`);
    }
    for (const bgToken of ['--paper', '--sheet']) {
      const bg = resolveCssVar(vars, bgToken);
      for (const fgToken of ['--ink', '--ink-muted', '--open', '--working', '--review', '--verified', ...catTokens]) {
        const fg = resolveCssVar(vars, fgToken);
        const ratio = contrastRatio(fg, bg);
        assert.ok(
          ratio >= 4.5,
          `WCAG AA contrast failed in ${themeName} theme: ${fgToken} (${fg}) on ${bgToken} (${bg}) = ${ratio.toFixed(2)}:1 (< 4.5:1)`
        );
      }
    }
  }
});

test('language and theme controls expose and persist state cleanly', () => {
  assert.ok(/id="language-toggle"/i.test(html), 'Language toggle control should exist');
  assert.ok(/id="theme-toggle"/i.test(html), 'Theme toggle control should exist');
  assert.ok(/aria-pressed/i.test(appJs), 'theme state should update aria-pressed');
  assert.ok(/data-theme="dark"/.test(html), 'Dark theme should be default');
  assert.ok(/document\.documentElement\.lang/.test(appJs) && /document\.documentElement\.dir/.test(appJs), 'language toggle should update lang/dir');
  assert.ok(!/سامان سا|عطر نبی/i.test(html), 'default HTML must not hardcode private customer projects');
});

test('3 Case Ledger ARIA tabs (flow, map, team) and Settings sheet', () => {
  assert.ok(/class="primary-nav"/i.test(html), 'primary navigation should exist');
  for (const tab of ['flow', 'map', 'team']) {
    assert.ok(new RegExp(`data-tab="${tab}"`).test(html), `${tab} nav button should exist`);
  }
  for (const legacyTab of ['overview', 'conversations', 'graph', 'settings']) {
    assert.ok(!new RegExp(`data-tab="${legacyTab}"`).test(html), `legacy tab ${legacyTab} must not exist in primary nav`);
  }
  assert.ok(/id="settings-sheet"/.test(html), '#settings-sheet drawer/sheet must exist');
  const shellIdx = html.indexOf('id="tt-shell"');
  const sheetIdx = html.indexOf('id="settings-sheet"');
  assert.ok(shellIdx > 0 && sheetIdx > shellIdx, '#settings-sheet must be inside #tt-shell container root');
  const between = html.slice(shellIdx, sheetIdx);
  const openDivs = (between.match(/<div\b/g) || []).length;
  const closeDivs = (between.match(/<\/div>/g) || []).length;
  assert.ok(openDivs > closeDivs, '#tt-shell must remain open around #settings-sheet for @container sidecar queries');
  assert.ok(/aria-selected/.test(appJs), 'tabs should update aria-selected');
  assert.ok(/e\.key === 'ArrowRight'/.test(appJs) && /e\.key === 'ArrowLeft'/.test(appJs), 'arrow keys should navigate tabs');
  assert.ok(/e\.key === 'Home'/.test(appJs) && /e\.key === 'End'/.test(appJs), 'Home/End keys should navigate tabs');
  assert.ok(/#tab-flow[^]*keydown[^]*\.finding-card\[data-finding-id\]/.test(appJs), 'focusable finding cards and ledger rows must support keyboard activation');
});

test('Canonical 7+1 + main_agent role_catalog contract (9 roles, monogram + frameShape, hierarchy)', async () => {
  assert.equal(roles.length, 9, 'role_catalog.json should contain exactly 9 canonical roles');
  const byId = new Map(roles.map((r) => [r.id, r]));

  const expectedShapes = {
    main_agent: ['MA', 'hexagon'],
    'team-manager': ['TM', 'square'],
    'council-critic': ['CC', 'square'],
    'code-reviewer': ['CR', 'square'],
    'qa-reviewer': ['QA', 'diamond'],
    'ui-frontend-designer': ['UI', 'circle'],
    'backend-auditor': ['BE', 'circle'],
    ecommerce_seo_operator: ['SE', 'circle'],
    wp_technical_operator: ['WP', 'circle'],
  };

  for (const [id, [monogram, frameShape]] of Object.entries(expectedShapes)) {
    assert.ok(byId.has(id), `role_catalog.json must include canonical role ${id}`);
    assert.equal(byId.get(id).monogram, monogram, `${id} monogram must be ${monogram}`);
    assert.equal(byId.get(id).frameShape, frameShape, `${id} frameShape must be ${frameShape}`);
  }

  for (const supId of ['team-manager', 'council-critic', 'code-reviewer']) {
    assert.equal(byId.get(supId).tier, 'supervisor', `${supId} must be tier supervisor`);
    assert.equal(byId.get(supId).canInterrogate, true, `${supId} must have canInterrogate: true`);
  }
  assert.equal(byId.get('qa-reviewer').tier, 'tester', 'qa-reviewer must be tier tester');
  assert.equal(byId.get('qa-reviewer').reportsTo, 'code-reviewer', 'qa-reviewer must report to code-reviewer');
  for (const workerId of ['ui-frontend-designer', 'backend-auditor', 'ecommerce_seo_operator', 'wp_technical_operator']) {
    assert.equal(byId.get(workerId).tier, 'worker', `${workerId} must be tier worker`);
    assert.equal(byId.get(workerId).canPeerSync, true, `${workerId} must allow canPeerSync`);
  }

  const sidecarJson = JSON.parse(await readFile(new URL('sidecar.json', root), 'utf8'));
  assert.ok(/Think Tank/i.test(sidecarJson.display_name), 'sidecar display_name should reference Think Tank');
  assert.ok(!/Codex/i.test(sidecarJson.display_name), 'sidecar display_name must not contain Codex');
  assert.ok(/'Content-Type':\s*['"]font\/ttf['"]/i.test(mainMjs), 'main.mjs must serve font/ttf');
  assert.ok(/'Content-Type':\s*['"]text\/html;\s*charset=utf-8['"]/i.test(mainMjs), 'main.mjs must serve HTML UTF-8');
});

test('Case Ledger UI contracts: Now strip, Findings lifecycle rail, Inspector, user-only composer, Sequence map, Closure receipt, empty state', () => {
  for (const id of [
    'now-strip',
    'findings-progress-bar',
    'case-inspector',
    'user-composer-form',
    'sequence-diagram-wrap',
    'closure-receipt',
    'empty-session-screen',
    'btn-init-session',
  ]) {
    assert.ok(new RegExp(`id="${id}"`).test(html), `index.html must include #${id}`);
  }
  assert.ok(/lifecycle-rail/.test(html) || /lifecycle-rail/.test(appJs), 'Finding cards must render .lifecycle-rail');

  // Zero 8-mode impersonation buttons
  for (const legacyMode of ['return-defect', 'worker-fix', 'review-query', 'interrogate', 'peer-sync', 'qa-dispatch', 'qa-report']) {
    assert.ok(!new RegExp(`data-mode="${legacyMode}"`).test(html), `User composer must not expose impersonation mode ${legacyMode}`);
  }
  assert.ok(!/دقیقاً مشابه Swarm/i.test(html + appJs + i18nJs), 'Product UI must not contain "دقیقاً مشابه Swarm" wording');
});

test('Zero Unicode emojis across UI and docs + release kit presence', async () => {
  const emojiRegex = /[\u{1F300}-\u{1FAFF}\u{2600}-\u{26FF}\u{2700}-\u{27BF}]/u;
  for (const [name, content] of [
    ['index.html', html],
    ['app.js', appJs],
    ['app.css', appCss],
    ['i18n.js', i18nJs],
  ]) {
    assert.ok(!emojiRegex.test(content), `${name} must use SVG icons or clean text, zero emojis`);
  }
  for (const r of roles) {
    assert.ok(!emojiRegex.test(JSON.stringify(r)), `role_catalog entry ${r.id} must have zero emojis`);
  }

  for (const rel of ['package.json', 'tools/install_plugin.py', 'tools/verify_release.py', 'README.md', 'CHANGELOG.md', 'CONTRIBUTING.md']) {
    const content = await readFile(new URL(rel, pluginRoot), 'utf8');
    assert.ok(content.trim().length > 0, `Release kit file ${rel} must exist and be non-empty`);
    if (rel.endsWith('.md')) {
      assert.ok(!emojiRegex.test(content), `${rel} must contain zero Unicode emojis`);
    }
  }
});

test('Case Ledger remediation contracts: proxy routes, proposal/review actions, zero gradients, Escape & keyboard sequence access', async () => {
  assert.ok(!/linear-gradient\(/i.test(appCss), 'app.css must not contain linear-gradient()');
  assert.ok(/\/api\/findings\/action/.test(mainMjs), 'main.mjs must proxy /api/findings/action');
  assert.ok(/\/api\/telemetry\/host_tool/.test(mainMjs), 'main.mjs must proxy /api/telemetry/host_tool');
  assert.ok(/action:\s*['"]request_revision['"]|data-act="request_revision"/.test(appJs), 'app.js must send request_revision for proposal revisions');
  assert.ok(/\boptionId\b/.test(appJs), 'app.js must send optionId for proposal selection/approval');
  assert.ok(!/window\.prompt\(/.test(appJs), 'app.js must not rely on blocking window.prompt()');
  assert.ok(/\/api\/governance\/review_decision/.test(appJs), 'app.js must wire <95% human review_decision actions');
  assert.ok(/state\.inspectorItem/.test(appJs) && /closeInspector\(\)/.test(appJs), 'app.js must close #case-inspector on Escape');
  assert.ok(/seq-event-row.*tabindex="0"/s.test(appJs), 'Sequence event rows must be keyboard-focusable with tabindex="0"');

  const convContext = await readFile(new URL('conversation-context.mjs', root), 'utf8');
  assert.match(convContext, /'flow'[\s\S]*'map'[\s\S]*'team'/);
  assert.ok(!/'overview'/.test(convContext), 'conversation-context MAIN_TABS must reflect v3 flow/map/team tabs');
});

test('Role minimal SVG symbols, clickable edge arrows, and requestType contracts', async () => {
  for (const r of roles) {
    const svgText = await readFile(new URL(`assets/avatars/${r.avatar}`, root), 'utf8');
    assert.match(svgText, /<svg[^>]*viewBox="0 0 20 20"/, `${r.avatar} must be a 20x20 minimal vector glyph`);
    assert.ok(!/linearGradient/i.test(svgText), `${r.avatar} must not use gradients`);
    assert.ok(svgText.length < 600, `${r.avatar} must remain lightweight (<600 chars)`);
  }
  assert.ok(/ROLE_GLYPHS/.test(appJs), 'app.js must embed ROLE_GLYPHS for inline role SVGs');
  assert.ok(/requestTypeLabel/.test(appJs), 'app.js must map explicit/inferred requestType labels');
  assert.ok(/item\.type\s*===\s*'edge'/.test(appJs), 'app.js must support inspecting clicked network edges');
  assert.ok(/class="net-edge-arrow(?:\$\{[^}]+\}|[^"]*)"/.test(appJs), 'app.js must render clickable .net-edge-arrow elements');
  for (const reqCode of ['REWRITE', 'REFERRAL', 'QUESTION', 'INTERROGATION', 'DEFECT_RETURN', 'CRITIQUE', 'QA_REPORT', 'PEER_SYNC', 'DECISION', 'MESSAGE']) {
    assert.match(i18nJs, new RegExp(`['"]reqType\\.${reqCode}['"]`), `i18n.js must define reqType.${reqCode}`);
  }
});

test('F-08, F-09, F-13, F-14, F-15: Typography scale >=12px, weights 400/600/700, monograms, 44px touch targets, and scoped aria-live', () => {
  for (const [name, content] of [['app.css', appCss], ['app.js', appJs], ['index.html', html]]) {
    for (const m of content.matchAll(/font-size\s*[:=]\s*["']?([0-9.]+)(?:px)?/gi)) {
      assert.ok(parseFloat(m[1]) >= 12, `${name} contains <12px font-size: ${m[0]}`);
    }
    assert.ok(!/font-weight\s*[:=]\s*["']?500\b/i.test(content), `${name} must only use weights 400/600/700 (no 500)`);
  }

  assert.match(appJs, /class="role-monogram-code"/, 'renderRoleMonogram must render readable two-letter monogram badge alongside SVG glyph');
  assert.match(appJs, /const headerH = 44;[\s\S]*?<text[^>]*font-size="12" font-weight="700"[^>]*>\$\{esc\(monogram\)\}<\/text>/, 'Sequence headers must reserve 44px and render 12px bold monograms beneath SVG glyph');

  assert.match(appJs, /↺\$\{num\(f\.returnCount\)\}/, 'Finding cards must show compact ↺ return counter');
  assert.ok(!/R\$\{num\(f\.returnCount\)\}/.test(appJs), 'Legacy R0/R1 finding return counter must be removed');
  assert.match(appCss, /\.req-type-chip\s*\{[^}]*padding:\s*0;[^}]*border:\s*none;[^}]*background:\s*transparent;[^}]*font-size:\s*12px;/, '.req-type-chip must be borderless 12px inline metadata');

  assert.match(appCss, /\.finding-pin-btn\s*\{[^}]*width:\s*44px;[^}]*height:\s*44px;[^}]*min-width:\s*44px;[^}]*min-height:\s*44px;/, '.finding-pin-btn must meet 44x44px touch target');
  for (const sel of ['.tt-compact-btn', '.tt-input-compact', '.tt-select-compact', '.segment-btn', '.locked-files-details summary', '.segmented-toggle .seg-btn', '.replay-slider']) {
    const escaped = sel.replace(/[.*+?^${}()|[\]\\]/g, '\\$&');
    assert.match(appCss, new RegExp(`${escaped}[^{]*\\{[^}]*min-height:\\s*44px`), `${sel} must meet 44px minimum target height`);
  }

  const nowStripTag = html.match(/<section[^>]*id="now-strip"[^>]*>/i)?.[0] || '';
  assert.ok(nowStripTag && !/aria-live/i.test(nowStripTag), '#now-strip must not broadcast whole-section aria-live updates');
  const awaitingTag = html.match(/<div[^>]*id="awaiting-user-box"[^>]*>/i)?.[0] || '';
  assert.match(awaitingTag, /aria-live="polite"/, '#awaiting-user-box must scope aria-live="polite"');
});

test('F-03, F-10, F-11, F-12, F-16: Case reopen/reset, replay status tones, network affordances, single-line header, and dimmed inactive nodes', () => {
  assert.match(i18nJs, /['"]receipt\.reopenCase['"]/, 'i18n.js must define receipt.reopenCase');
  assert.match(appJs, /id="btn-receipt-reopen-case"/, 'Closure receipt must render #btn-receipt-reopen-case');
  assert.match(appJs, /#btn-receipt-reopen-case[\s\S]*reopen:\s*true/, 'Reopen action must send reopen: true');
  assert.match(appJs, /state\.pendingResetCase/, 'New-case action must stage state.pendingResetCase');
  assert.match(appJs, /payload\.resetCase\s*=\s*true/, 'Session form submit must include resetCase: true when resetting from receipt');

  const recordedBlock = appJs.match(/function buildRecordedEvents\(\)\s*\{[\s\S]*?\n\s{2}\}/)?.[0] || '';
  assert.ok(recordedBlock.length > 0 && !/\|\|\s*state\.isClosed/.test(recordedBlock), 'buildRecordedEvents must not override historical resolved state with state.isClosed');
  assert.match(appJs, /function eventTone\(ev\b/, 'app.js must define status-driven eventTone()');
  for (const marker of ['seq-arrow-verified', 'seq-arrow-open', 'seq-arrow-review', 'seq-arrow-working', 'seq-arrow-muted']) {
    assert.ok(appJs.includes(marker), `Sequence diagram must declare/use ${marker}`);
  }

  assert.match(appJs, /class="net-edge-stroke"/, 'Network edge curves must carry .net-edge-stroke for hover/focus/select CSS');
  assert.match(appJs, /paint-order="stroke"\s+stroke="var\(--paper\)"/, 'Network edge labels must paint paper halo behind curve labels');
  assert.match(appJs, /function openInspector[\s\S]*if \(state\.activeTab === 'map'\) renderMap\(\);/, 'openInspector must trigger renderMap() so selected arrows highlight immediately');
  assert.match(appJs, /function closeInspector[\s\S]*if \(state\.activeTab === 'map'\) renderMap\(\);/, 'closeInspector must trigger renderMap() so selection clears immediately');
  assert.match(appJs, /ev\.seq <= cutoff && ev\.from === fromId && ev\.to === toId/, 'Edge inspector must filter recorded events by replay cutoff');
  assert.match(appJs, /<span class="dir-arrow">\$\{SVG_ICONS\.arrow\}<\/span>/, 'Edge inspector header must use SVG dir-arrow instead of literal "->"');

  const headerHtml = html.match(/<header[^>]*>[\s\S]*?<\/header>/i)?.[0] || '';
  assert.ok(headerHtml && !/id="conv-search-input"/.test(headerHtml), 'Top header must stay single-line without #conv-search-input');
  const settingsHtml = html.match(/<div id="settings-sheet"[\s\S]*$/i)?.[0] || '';
  assert.match(settingsHtml, /id="conv-search-input"/, 'Case search/switcher must live inside #settings-sheet');
  assert.match(appCss, /\.tt-header\s*\{[^}]*height:\s*48px;[^}]*flex-wrap:\s*nowrap;/, '.tt-header must enforce single-line 48px height');
  assert.match(appJs, /c\.isClosed\s*\?\s*'○'\s*:\s*'●'/, 'Session switcher options must use ○/● symbols instead of bracket status tags');

  assert.match(appJs, /function isRoleActiveInCase\(roleId\)/, 'app.js must compute active roles via isRoleActiveInCase()');
  assert.match(appJs, /class="net-node-group"[\s\S]*opacity="\$\{isActive \? '1' : '0\.42'\}"/, 'Inactive roles in Network View must dim to 0.42 opacity');
});

test('F-17, F-18, F-19: Deduplicated fonts.css, render signature caches & open <details> preservation, and dead asset cleanup', async () => {
  const fontsBytes = Buffer.byteLength(fonts, 'utf8');
  assert.ok(fontsBytes < 600_000, `fonts.css must stay compact after deduplication (<600KB, got ${fontsBytes}B)`);
  const localIdx = fonts.indexOf("url('/fonts/");
  const dataIdx = fonts.indexOf("url('data:font/ttf;base64,");
  assert.ok(localIdx >= 0 && dataIdx > localIdx, 'fonts.css must prefer /fonts/ TTF URLs before inline base64 fallback');

  for (const deadRel of ['roles.css', 'tailwind.js', 'assets/fonts']) {
    await assert.rejects(stat(new URL(deadRel, root)), `${deadRel} must be deleted`);
    assert.ok(!mainMjs.includes(deadRel), `main.mjs must not serve deleted asset ${deadRel}`);
  }

  const avatarFiles = (await readdir(new URL('assets/avatars', root))).sort();
  const expectedAvatars = roles.map((r) => r.avatar).sort();
  assert.deepEqual(avatarFiles, expectedAvatars, 'assets/avatars must contain only the 9 role_catalog SVGs');

  for (const sigKey of ['signatures.flow', 'signatures.map', 'signatures.team', 'signatures.inspector']) {
    assert.ok(appJs.includes(sigKey), `app.js must memoize render pass via ${sigKey}`);
  }
  assert.match(appJs, /function preserveDetailsOpen/, 'app.js must preserve open <details> elements across DOM updates');
});

test('Critic F-03, F-05, F-06 fixes: roleUsage keys, replay-safe eventTone/network colors, and ACTION_TO_REQUEST_TYPE/i18n/reopen proxy parity', () => {
  // F-03: Settings roleUsage keys
  assert.match(appJs, /usage\.main\s*\?\?\s*usage\.main_agent/, 'Settings usage meter must read usage.main with main_agent fallback');
  assert.match(appJs, /usage\.manager\s*\?\?\s*usage\['team-manager'\]/, 'Settings usage meter must read usage.manager with team-manager fallback');
  assert.match(appJs, /usage\.subagents\s*!==\s*undefined/, 'Settings usage meter must read usage.subagents directly before extra-key fallback');

  // F-05: Replay-safe finding tone + Testing->working + no action-name fallback + 5-tone network edges
  assert.match(appJs, /function resolveFindingStateAt\(/, 'app.js must compute replay-safe finding states via resolveFindingStateAt()');
  assert.match(appJs, /if \(st === 'Fixing' \|\| st === 'Testing'\) return 'working';/, "Finding state 'Testing' must map to 'working' tone");
  const eventToneBlock = appJs.match(/function eventTone\([\s\S]*?\n\s{2}\}/)?.[0] || '';
  assert.ok(eventToneBlock.length > 0, 'app.js must define eventTone()');
  assert.ok(!/WORKER_FIX|QA_DISPATCH/.test(eventToneBlock), 'eventTone() must not color events by raw WORKER_FIX/QA_DISPATCH action fallback');
  assert.match(eventToneBlock, /state\.replayLive\s*&&\s*ev\.resolved/, 'eventTone() may only consider ev.resolved while replayLive is true');
  assert.ok(!/openCount\s*>\s*0\s*\?\s*'var\(--open\)'\s*:\s*'var\(--verified\)'/.test(appJs), 'renderNetworkView must not default non-open edges to var(--verified)');
  for (const marker of ['net-open', 'net-working', 'net-review', 'net-verified', 'net-muted']) {
    assert.ok(appJs.includes(marker), `renderNetworkView must define/use ${marker}`);
  }

  // F-06: ACTION_TO_REQUEST_TYPE, i18n action.* keys, and /api/governance/reopen proxy
  const reqTypeBlock = appJs.match(/const ACTION_TO_REQUEST_TYPE\s*=\s*\{[\s\S]*?\};/)?.[0] || '';
  for (const act of ['SUBTASK_UPDATE', 'GOVERNANCE', 'INTERROGATE_REPLY', 'REVISION_REQUESTED', 'REWRITE', 'REFERRAL', 'QUESTION', 'INTERROGATION', 'DEFECT_RETURN']) {
    assert.match(reqTypeBlock, new RegExp(`\\b${act}:`), `ACTION_TO_REQUEST_TYPE must map ${act}`);
  }
  for (const act of ['ASSIGN_SUBTASK', 'SUBTASK_UPDATE', 'QA_REOPEN', 'CRITIQUE', 'APPROVE', 'DECIDE', 'PROPOSAL', 'COMPLETE', 'GOVERNANCE', 'INTERROGATE_REPLY', 'REVISION_REQUESTED']) {
    assert.match(i18nJs, new RegExp(`"action\\.${act}"`), `i18n.js must define action.${act}`);
  }
  assert.ok(mainMjs.includes("'/api/governance/reopen'"), 'main.mjs postRoutes must expose /api/governance/reopen');

  // Behavioral VM verification of production replay tone functions in app.js
  const toneSliceMatch = appJs.match(/function resolveFindingStateAt[\s\S]*?function eventToneColor\(/);
  assert.ok(toneSliceMatch, 'Could not locate resolveFindingStateAt..eventTone slice in app.js');
  const fnCode = toneSliceMatch[0].replace(/\n\s*function eventToneColor\($/, '');
  const sandbox = {
    state: {
      replayLive: false,
      replaySeq: 1,
      findings: [{ id: 'F-01', state: 'Verified' }],
    },
    buildRecordedEvents: () => [],
  };
  vm.runInNewContext(`${fnCode}\nthis.__exports = { resolveFindingStateAt, findingStateToTone, eventTone };`, sandbox);
  const { resolveFindingStateAt, eventTone } = sandbox.__exports;
  const evs = [
    { seq: 1, action: 'RETURN_DEFECT', findingId: 'F-01', resolved: true, result: '' },
    { seq: 2, action: 'WORKER_FIX', findingId: 'F-01', resolved: true, result: '' },
    { seq: 3, action: 'QA_DISPATCH', findingId: 'F-01', resolved: true, result: '' },
    { seq: 4, action: 'QA_REPORT', findingId: 'F-01', resolved: true, result: 'FAIL' },
    { seq: 5, action: 'PEER_SYNC', findingId: '', resolved: true, result: '' },
    { seq: 6, action: 'QA_REPORT', findingId: 'F-01', resolved: true, result: 'PASS' },
  ];
  assert.equal(resolveFindingStateAt('F-01', 1, evs), 'Open');
  assert.equal(eventTone(evs[0], 1, evs).tone, 'open');
  assert.equal(resolveFindingStateAt('F-01', 2, evs), 'InReview');
  assert.equal(eventTone(evs[1], 2, evs).tone, 'review');
  assert.equal(resolveFindingStateAt('F-01', 3, evs), 'Testing');
  assert.equal(eventTone(evs[2], 3, evs).tone, 'working');
  assert.equal(resolveFindingStateAt('F-01', 4, evs), 'Fixing');
  assert.equal(eventTone(evs[3], 4, evs).tone, 'working');
  assert.equal(eventTone(evs[4], 5, evs).tone, 'muted');
  assert.equal(resolveFindingStateAt('F-01', 6, evs), 'Verified');
  assert.equal(eventTone(evs[5], 6, evs).tone, 'verified');
});

test('Step 3: Categorical colors, legend, smooth arrows, bilingual tooltip, multi-run isolation & verified subagent badge', () => {
  // Categorical tokens, legend, ledger accents, and i18n keys
  assert.match(html, /id="map-category-legend"/, 'index.html must include #map-category-legend');
  assert.match(appJs, /function requestCategoryMeta\(/, 'app.js must define requestCategoryMeta()');
  assert.match(appJs, /data-req-category="/, 'Event ledger and chips must emit data-req-category');
  assert.match(appCss, /\.ledger-row\[data-req-category="referral"\]/, 'app.css must style categorical ledger accents');
  assert.match(appCss, /\.map-category-legend\b/, 'app.css must style .map-category-legend');

  for (const cat of ['referral', 'inquiry', 'defect', 'rewrite', 'sync', 'verify']) {
    assert.ok(appJs.includes(`seq-arrow-cat-${cat}`), `Sequence diagram must declare seq-arrow-cat-${cat}`);
    assert.ok(appJs.includes(`net-cat-${cat}`), `Network view must declare net-cat-${cat}`);
    assert.match(i18nJs, new RegExp(`"map\\.legend\\.${cat}"`), `i18n.js must define map.legend.${cat}`);
  }
  for (const act of ['QUESTION', 'DECISION', 'REWRITE', 'REFERRAL', 'INTERROGATION', 'DEFECT_RETURN']) {
    assert.match(i18nJs, new RegExp(`"action\\.${act}"`), `i18n.js must define action.${act}`);
  }

  // Smooth arrow geometry & reduced-motion-safe animation
  for (const cls of ['.seq-edge-flow', '.net-edge-flow', '.net-node-halo']) {
    assert.ok(appCss.includes(cls), `app.css must style ${cls}`);
  }
  assert.match(appCss, /@keyframes netFlowDash/, 'app.css must define @keyframes netFlowDash');
  assert.match(appJs, /class="seq-label-pill"/, 'Sequence diagram must render rounded pill backdrops for labels');
  assert.match(appJs, /class="net-label-pill"/, 'Network view must render rounded pill backdrops for labels');
  assert.match(appJs, /class="net-tier-guides"/, 'Network view must render subtle tier guide bands/labels');

  // Bilingual hover tooltip & tt-/agent- prefix normalization
  assert.match(html, /id="role-hover-tooltip"/, 'index.html must include #role-hover-tooltip');
  assert.match(appCss, /\.role-hover-tooltip\b/, 'app.css must style .role-hover-tooltip');
  assert.match(appJs, /function roleBilingualLabel\(/, 'app.js must define roleBilingualLabel()');
  assert.match(appJs, /data-role-tooltip="/, 'app.js must attach data-role-tooltip attributes');
  assert.match(appJs, /\(\?:agent\|tt\)\[_-\]/, 'normalizeRoleId must strip leading agent-/tt- prefixes');

  // Multi-run history isolation & verified subagent badge
  assert.match(html, /id="run-history-bar"/, 'index.html must include #run-history-bar');
  assert.match(html, /id="btn-new-run"/, 'index.html must include #btn-new-run');
  assert.match(appJs, /newRun:\s*true/, '#btn-new-run must submit newRun: true');
  assert.match(appJs, /parentConvId|isArchivedRun|runIndex/, 'app.js must consume backend multi-run metadata');
  assert.match(appJs, /verifiedSubagent/, 'app.js must render verifiedSubagent indicator');
  assert.match(appJs, /subagentConvId/, 'app.js must surface subagentConvId indicator');
  assert.match(appCss, /\.run-history-bar\b/, 'app.css must style .run-history-bar');
  assert.match(appCss, /\.verified-subagent-badge\b/, 'app.css must style .verified-subagent-badge');
  for (const k of ['header.newRun', 'header.runsTitle', 'team.verifiedSubagent']) {
    assert.match(i18nJs, new RegExp(`"${k.replace('.', '\\.')}"`), `i18n.js must define ${k}`);
  }

  // VM behavioral check for requestCategoryMeta & normalizeRoleId
  const reqMapCode = appJs.match(/const ACTION_TO_REQUEST_TYPE\s*=\s*\{[\s\S]*?\};/)?.[0] || '';
  const resolveReqCode = appJs.match(/function resolveRequestType\(item\)\s*\{[\s\S]*?\n\s{2}\}/)?.[0] || '';
  const reqCatCode = appJs.match(/function requestCategoryMeta\(item\)\s*\{[\s\S]*?\n\s{2}\}/)?.[0] || '';
  const normCode = appJs.match(/function normalizeRoleId\(raw\)\s*\{[\s\S]*?\n\s{2}\}/)?.[0] || '';
  assert.ok(reqMapCode && resolveReqCode && reqCatCode && normCode, 'Expected helpers must exist in app.js');
  const sb = {};
  vm.runInNewContext(`${reqMapCode}\n${resolveReqCode}\n${reqCatCode}\n${normCode}\nthis.__exports = { requestCategoryMeta, normalizeRoleId };`, sb);
  assert.equal(sb.__exports.requestCategoryMeta({ action: 'DELEGATE' }).category, 'referral');
  assert.equal(sb.__exports.requestCategoryMeta({ action: 'INTERROGATE' }).category, 'inquiry');
  assert.equal(sb.__exports.requestCategoryMeta({ action: 'RETURN_DEFECT' }).category, 'defect');
  assert.equal(sb.__exports.requestCategoryMeta({ action: 'WORKER_FIX' }).category, 'rewrite');
  assert.equal(sb.__exports.requestCategoryMeta({ action: 'PEER_SYNC' }).category, 'sync');
  assert.equal(sb.__exports.requestCategoryMeta({ action: 'QA_REPORT' }).category, 'verify');
  assert.equal(sb.__exports.normalizeRoleId('tt-ui-frontend-designer'), 'ui-frontend-designer');
  assert.equal(sb.__exports.normalizeRoleId('agent_backend_auditor'), 'backend-auditor');
});

test('F-01, F-03, F-04, F-06: Parent session resolution, WORKING status helper, WS sync/onclose race, and sequence SVG scroll', () => {
  // F-01: main.mjs parentConversationId + subagent_links.json resolution
  const ctxMatch = mainMjs.match(/function getActiveSessionContext\(\)\s*\{[\s\S]*?\n\}/);
  assert.ok(ctxMatch, 'main.mjs must define getActiveSessionContext()');
  assert.match(ctxMatch[0], /parentConversationId/, 'getActiveSessionContext must prefer parentConversationId');
  assert.match(ctxMatch[0], /subagent_links\.json/, 'getActiveSessionContext must resolve subagent_links.json');

  const ctxSb = {
    app: { config: {} },
    homedir: () => '/tmp/test-home',
    join: (...parts) => parts.join('/'),
    existsSync: (p) => p.endsWith('active_antigravity_session.json') || p.endsWith('subagent_links.json'),
    readFileSync: (p) => (p.endsWith('active_antigravity_session.json')
      ? JSON.stringify({ conversationId: 'child-uuid-1', projectId: 'proj-1' })
      : JSON.stringify({ 'child-uuid-1': { parentConversationId: 'parent-uuid-9' } })),
    process: { env: {} },
  };
  vm.runInNewContext(`${ctxMatch[0]}\nthis.__ctx = getActiveSessionContext();`, ctxSb);
  assert.equal(ctxSb.__ctx.conversationId, 'parent-uuid-9');
  assert.equal(ctxSb.__ctx.projectId, 'proj-1');

  // F-03: isWorkingAgentStatus used in renderNowStrip & isRoleActiveInCase
  assert.match(appJs, /function isWorkingAgentStatus\(/, 'app.js must define isWorkingAgentStatus()');
  const nowMatch = appJs.match(/function renderNowStrip\(\)\s*\{[\s\S]*?\n\s{2}\}/)?.[0] || '';
  const activeRoleMatch = appJs.match(/function isRoleActiveInCase\(roleId\)\s*\{[\s\S]*?\n\s{2}\}/)?.[0] || '';
  assert.match(nowMatch, /isWorkingAgentStatus\(ag\.status\)/, 'renderNowStrip must check isWorkingAgentStatus(ag.status)');
  assert.match(activeRoleMatch, /isWorkingAgentStatus\(ag\.status\)/, 'isRoleActiveInCase must check isWorkingAgentStatus(ag.status)');

  const workingFn = appJs.match(/function isWorkingAgentStatus\(st\)\s*\{[\s\S]*?\n\s{2}\}/)?.[0] || '';
  const workSb = {};
  vm.runInNewContext(`${workingFn}\nthis.__w = isWorkingAgentStatus;`, workSb);
  assert.equal(workSb.__w('WORKING'), true);
  assert.equal(workSb.__w('IN_PROGRESS'), true);
  assert.equal(workSb.__w('ACTIVE'), true);
  assert.equal(workSb.__w('IDLE'), false);

  // F-04: applyIncrementalWsMsg clears stale tt fields, updates conversationsList, clears inspector on runIndex change, and ws.onclose guards state.ws
  const incMatch = appJs.match(/function applyIncrementalWsMsg\(msg\)\s*\{[\s\S]*?\n\s{2}\}/)?.[0] || '';
  assert.ok(incMatch, 'app.js must define applyIncrementalWsMsg()');
  assert.match(incMatch, /Array\.isArray\(msg\.conversationsList\)/, 'applyIncrementalWsMsg must sync msg.conversationsList');
  assert.match(incMatch, /'project' in tt \? \(tt\.project \?\? ''\) : state\.project/, 'applyIncrementalWsMsg must clear stale state.project when tt.project is empty');
  assert.match(appJs, /ws\.onclose\s*=\s*\(\)\s*=>\s*\{\s*if\s*\(state\.ws\s*!==\s*ws\)\s*return;/, 'ws.onclose must ignore stale socket closes when state.ws !== ws');
  assert.match(appJs, /ws\.onerror\s*=\s*\(\)\s*=>\s*\{\s*if\s*\(state\.ws\s*===\s*ws\)\s*ws\.close\(\);/, 'ws.onerror must guard state.ws === ws');

  const computeHasMatch = appJs.match(/function computeHasSession\(data, tt\)\s*\{[\s\S]*?\n\s{2}\}/)?.[0] || '';
  const incSb = {
    dataRevision: 0,
    lastSnapshotHash: 'prev',
    getMaxRecordedSeq: () => 0,
    state: {
      project: 'Old Project',
      directive: 'Old Directive',
      phase: 'Old Phase',
      status: 'COMPLETED',
      progress: 100,
      round: 5,
      maxRounds: 7,
      runIndex: 1,
      roleCaps: {},
      triageDecision: null,
      closureReceipt: { totalEvents: 3 },
      hasSession: true,
      agents: [],
      messages: [],
      interactions: [],
      findings: [],
      fileLocks: [],
      subtasks: [],
      conversations: [],
      inspectorItem: { type: 'finding', id: 'F-01' },
      selectedProposalOption: 'opt-1',
      replayLive: true,
      replaySeq: 0,
      isClosed: true,
    },
  };
  vm.runInNewContext(`${computeHasMatch}\n${incMatch}\nthis.__inc = applyIncrementalWsMsg;`, incSb);
  const applied = incSb.__inc({
    thinkTank: { project: '', directive: '', phase: '', status: 'ACTIVE', runIndex: 2 },
    conversationsList: [{ id: 'c--run-1', runIndex: 1, isClosed: true }, { id: 'c', runIndex: 2, isClosed: false }],
  });
  assert.equal(applied, true);
  assert.equal(incSb.state.project, '');
  assert.equal(incSb.state.directive, '');
  assert.equal(incSb.state.runIndex, 2);
  assert.equal(incSb.state.conversations.length, 2);
  assert.equal(incSb.state.inspectorItem, null);
  assert.equal(incSb.state.selectedProposalOption, null);

  // F-06: Sequence diagram SVG preserves intrinsic pixel width for horizontal scrolling without shrinking 12px text
  assert.match(appCss, /\.sequence-diagram-canvas svg\s*\{[^}]*width:\s*auto;[^}]*max-width:\s*none;/, '.sequence-diagram-canvas svg must use width: auto; max-width: none;');
  assert.match(appCss, /#swarm-interaction-svg\s*\{[^}]*width:\s*100%;/, '#swarm-interaction-svg must retain width: 100%');

  // Portability: main.mjs resolveBackendPython reads thinktank/runtime.json and respects THINKTANK_PYTHON + platform default
  const pyMatch = mainMjs.match(/function resolveBackendPython\(\)\s*\{[\s\S]*?\n\}/);
  assert.ok(pyMatch, 'main.mjs must define resolveBackendPython()');
  const pyRuntimeSb = {
    homedir: () => '/tmp/test-home',
    join: (...parts) => parts.join('/'),
    existsSync: (p) => p.endsWith('runtime.json') || p === '/venv/bin/python',
    readFileSync: () => JSON.stringify({ pythonExecutable: '/venv/bin/python' }),
    process: { env: {}, platform: 'linux' },
  };
  vm.runInNewContext(`${pyMatch[0]}\nthis.__py = resolveBackendPython();`, pyRuntimeSb);
  assert.equal(pyRuntimeSb.__py, '/venv/bin/python');

  const pyFallbackSb = {
    homedir: () => '/tmp/test-home',
    join: (...parts) => parts.join('/'),
    existsSync: () => false,
    readFileSync: () => '',
    process: { env: {}, platform: 'linux' },
  };
  vm.runInNewContext(`${pyMatch[0]}\nthis.__py = resolveBackendPython();`, pyFallbackSb);
  assert.equal(pyFallbackSb.__py, 'python3');
});

test('Cross-tab live sync: continuous host-context watch, parent-resolved snapshot acceptance, and empty-state recovery controls', () => {
  assert.match(html, /id="btn-sync-host-session"/, 'index.html must render #btn-sync-host-session in empty state');
  assert.match(html, /id="empty-active-sessions"/, 'index.html must render #empty-active-sessions container');
  assert.match(appJs, /function startHostContextWatch\(/, 'app.js must define continuous startHostContextWatch()');
  assert.match(appJs, /startHostContextWatch\(\);/, 'app.js init() must invoke startHostContextWatch()');
  assert.doesNotMatch(
    mainMjs,
    /window\.sidecar\s*=\s*Object\.assign\(window\.sidecar\s*\|\|\s*\{\},\s*\{\s*conversationId:/,
    'main.mjs must not unconditionally overwrite preload.js window.sidecar.conversationId',
  );

  // VM test 1: normalizeWorkspaceUri & cross-workspace active_antigravity_session isolation in main.mjs
  const wsNormMatch = mainMjs.match(/function normalizeWorkspaceUri\(raw\)\s*\{[\s\S]*?\n\}/);
  const ctxMatch = mainMjs.match(/function getActiveSessionContext\(\)\s*\{[\s\S]*?\n\}/);
  assert.ok(wsNormMatch && ctxMatch, 'main.mjs must define normalizeWorkspaceUri and getActiveSessionContext');
  const mainCtxSb = {
    app: { config: {} },
    homedir: () => '/tmp/test-home',
    join: (...parts) => parts.join('/'),
    existsSync: (p) => p.endsWith('active_antigravity_session.json'),
    readFileSync: () => JSON.stringify({
      conversationId: 'conv-ws-a',
      workspaceUri: 'file:///c:/workspaces/repo-a',
      sessionsByWorkspace: { 'file:///c:/workspaces/repo-a': { conversationId: 'conv-ws-a' } },
    }),
    process: { env: {}, platform: 'win32' },
  };
  vm.runInNewContext(
    `${wsNormMatch[0]}\n${ctxMatch[0]}\nthis.__norm = normalizeWorkspaceUri('file:///C%3A/workspaces/Dev/Repo/');\nthis.__otherWs = getActiveSessionContext('file:///c:/workspaces/repo-b');\nthis.__sameWs = getActiveSessionContext('file:///C%3A/workspaces/repo-a/');`,
    mainCtxSb,
  );
  assert.equal(mainCtxSb.__norm, 'file:///c:/workspaces/dev/repo');
  assert.equal(mainCtxSb.__otherWs.conversationId, '');
  assert.equal(mainCtxSb.__otherWs.workspaceMatched, false);
  assert.equal(mainCtxSb.__sameWs.conversationId, 'conv-ws-a');

  // VM test 2: resolveHostConvId ignores stale ?conversationId= when live ctx has newer tab or workspaceMatched === false
  const resolveFnMatch = appJs.match(/function resolveHostConvId\(ctx\)\s*\{[\s\S]*?\n\s{2}\}/);
  assert.ok(resolveFnMatch, 'app.js must define resolveHostConvId(ctx)');
  const resSb = {
    window: {
      location: { search: '?conversationId=stale-tab-1' },
      __ANTIGRAVITY_HOST_CONTEXT__: { conversationId: 'stale-tab-1' },
      sidecar: { conversationId: 'stale-tab-1' },
    },
    URLSearchParams,
  };
  vm.runInNewContext(
    `${resolveFnMatch[0]}\nthis.__live = resolveHostConvId({ conversationId: 'live-tab-2', workspaceMatched: true });\nthis.__unmatched = resolveHostConvId({ conversationId: '', workspaceMatched: false });`,
    resSb,
  );
  assert.equal(resSb.__live, 'live-tab-2');
  assert.equal(resSb.__unmatched, '');

  // VM test 3: applySnapshot resolves child -> parent and rejects stale lower sync.seq
  const computeFnMatch = appJs.match(/function computeHasSession\(data, tt\)\s*\{[\s\S]*?\n\s{2}\}/);
  const applyFnMatch = appJs.match(/function applySnapshot\(data, requestedCid = null\)\s*\{[\s\S]*?\n\s{2}\}/);
  assert.ok(computeFnMatch && applyFnMatch, 'app.js must define computeHasSession & applySnapshot');
  const snapSb = {
    dataRevision: 0,
    lastSnapshotHash: '',
    getMaxRecordedSeq: () => 5,
    renderAll: () => {},
    state: {
      activeConvId: 'child-uuid-1',
      userPinnedConv: false,
      hasSession: false,
      runIndex: 1,
      lastSeenSeq: 0,
      replayLive: true,
      replaySeq: 0,
      project: '',
      directive: '',
      phase: '',
      status: 'DISCONNECTED',
      progress: 0,
      round: 0,
      maxRounds: 50,
      roleCaps: {},
      agents: [],
      messages: [],
      interactions: [],
      findings: [],
      fileLocks: [],
      subtasks: [],
    },
  };
  vm.runInNewContext(`${computeFnMatch[0]}\n${applyFnMatch[0]}\nthis.__apply = applySnapshot;`, snapSb);
  snapSb.__apply(
    { convId: 'parent-uuid-9', parentConvId: 'parent-uuid-9', hasSession: true, thinkTank: { project: 'Live Case', status: 'ACTIVE' }, sync: { seq: 10, generation: 'g1' } },
    'child-uuid-1',
  );
  assert.equal(snapSb.state.activeConvId, 'parent-uuid-9');
  assert.equal(snapSb.state.hasSession, true);
  assert.equal(snapSb.state.lastSeenSeq, 10);
  // Stale HTTP response (seq 4 < lastSeenSeq 10) for same convId must be ignored
  snapSb.__apply(
    { convId: 'parent-uuid-9', parentConvId: 'parent-uuid-9', hasSession: true, thinkTank: { project: 'Stale Case', status: 'ACTIVE' }, sync: { seq: 4, generation: 'g1' } },
    'parent-uuid-9',
  );
  assert.equal(snapSb.state.project, 'Live Case');

  // VM test 4: fetchStatusForConv('') uses convId=default + workspaceUri when workspaceUri is set
  const fetchFnMatch = appJs.match(/async function fetchStatusForConv\(cid\)\s*\{[\s\S]*?\n\s{2}\}/);
  assert.ok(fetchFnMatch, 'app.js must define fetchStatusForConv(cid)');
  const calledUrls = [];
  const fetchSb = {
    state: { activeConvId: '', workspaceUri: 'file:///c:/workspaces/ws-b' },
    URLSearchParams,
    apiGet: async (url) => { calledUrls.push(url); return {}; },
  };
  vm.runInNewContext(`${fetchFnMatch[0]}\nfetchStatusForConv('');`, fetchSb);
  assert.equal(calledUrls[0], '/api/status?convId=default&workspaceUri=file%3A%2F%2F%2Fc%3A%2Fworkspaces%2Fws-b');

  // VM test 5: connectWebSocket().onmessage promotes child-uuid-1 -> parent-uuid-9 on SYNC_SNAPSHOT
  const wsFnMatch = appJs.match(/function connectWebSocket\(\)\s*\{[\s\S]*?\n\s{2}\}/);
  assert.ok(wsFnMatch, 'app.js must define connectWebSocket()');
  let capturedWs = null;
  class FakeWebSocket {
    static OPEN = 1;
    static CONNECTING = 0;
    constructor(url) {
      this.url = url;
      this.readyState = 1;
      capturedWs = this;
    }
    close() {}
  }
  const wsSb = {
    WebSocket: FakeWebSocket,
    URLSearchParams,
    clearTimeout: () => {},
    setTimeout: () => 0,
    startFallbackPoll: () => {},
    stopFallbackPoll: () => {},
    renderHeaderAndVisibility: () => {},
    renderAll: () => {},
    refreshStatus: () => {},
    applySnapshot: snapSb.__apply,
    state: snapSb.state,
  };
  wsSb.state.activeConvId = 'child-uuid-1';
  wsSb.state.userPinnedConv = false;
  wsSb.state.hasSession = false;
  wsSb.state.lastSeenSeq = 0;
  wsSb.state.ws = null;
  vm.runInNewContext(`${wsFnMatch[0]}\nconnectWebSocket();`, wsSb);
  assert.ok(capturedWs && typeof capturedWs.onmessage === 'function');
  capturedWs.onmessage({
    data: JSON.stringify({
      type: 'SYNC_SNAPSHOT',
      convId: 'parent-uuid-9',
      parentConvId: 'parent-uuid-9',
      hasSession: true,
      seq: 12,
      generation: 'g2',
      conversationsList: [{ id: 'parent-uuid-9', project: 'Live WS Case' }],
      snapshot: { thinkTank: { project: 'Live WS Case', status: 'ACTIVE' } },
    }),
  });
  assert.equal(wsSb.state.activeConvId, 'parent-uuid-9');
  assert.equal(wsSb.state.hasSession, true);
  assert.equal(wsSb.state.project, 'Live WS Case');
  assert.equal(wsSb.state.conversations.length, 1);
});
