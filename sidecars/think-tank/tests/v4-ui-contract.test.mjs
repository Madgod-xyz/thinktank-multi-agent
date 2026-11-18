import test from 'node:test';
import assert from 'node:assert/strict';
import { readFileSync, readdirSync, statSync } from 'node:fs';
import { dirname, join, resolve } from 'node:path';
import { fileURLToPath } from 'node:url';
import { patchKeyedChildren } from '../src/dom.mjs';

const HERE = dirname(fileURLToPath(import.meta.url));
const ROOT = resolve(HERE, '..');

function collectMjs(dir) {
  const out = [];
  for (const name of readdirSync(dir)) {
    const full = join(dir, name);
    const st = statSync(full);
    if (st.isDirectory()) out.push(...collectMjs(full));
    else if (name.endsWith('.mjs')) out.push(full);
  }
  return out;
}

function parseHex(hex) {
  const h = hex.replace('#', '').trim();
  const full = h.length === 3 ? h.split('').map((c) => c + c).join('') : h;
  return {
    r: parseInt(full.slice(0, 2), 16) / 255,
    g: parseInt(full.slice(2, 4), 16) / 255,
    b: parseInt(full.slice(4, 6), 16) / 255,
  };
}

function relLum({ r, g, b }) {
  const dec = (c) => (c <= 0.04045 ? c / 12.92 : ((c + 0.055) / 1.055) ** 2.4);
  return 0.2126 * dec(r) + 0.7152 * dec(g) + 0.0722 * dec(b);
}

function contrast(hexA, hexB) {
  const la = relLum(parseHex(hexA));
  const lb = relLum(parseHex(hexB));
  return (Math.max(la, lb) + 0.05) / (Math.min(la, lb) + 0.05);
}

function extractBlockTokens(blockText) {
  const map = {};
  for (const m of blockText.matchAll(/(--[a-z0-9-]+)\s*:\s*([^;]+);/gi)) {
    map[m[1]] = m[2].trim();
  }
  return map;
}

function makeMockDoc() {
  function makeNode(tag) {
    const attrs = new Map();
    const children = [];
    const node = {
      tagName: tag.toUpperCase(),
      parentNode: null,
      textContent: '',
      children,
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
      insertBefore(child, ref) {
        if (child.parentNode) child.remove();
        child.parentNode = node;
        if (!ref) {
          children.push(child);
          return child;
        }
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
    };
    return node;
  }
  return { createElement: makeNode };
}

test('Hallmark Floor rules hold across tokens.css, app.css, index.html, and ESM sources', () => {
  const tokensCss = readFileSync(join(ROOT, 'tokens.css'), 'utf8');
  const appCss = readFileSync(join(ROOT, 'app.css'), 'utf8');
  const indexHtml = readFileSync(join(ROOT, 'index.html'), 'utf8');
  const mjsFiles = [join(ROOT, 'main.mjs'), ...collectMjs(join(ROOT, 'src'))];

  assert.match(tokensCss.split('\n')[0], /^\/\*\s*Hallmark\b/);
  assert.match(appCss.split('\n')[0], /^\/\*\s*Hallmark\b/);

  assert.doesNotMatch(tokensCss, /#(?:000|000000|fff|ffffff)\b/i);
  assert.doesNotMatch(tokensCss, /oklch\(\s*(?:0%|100%)\b/i);

  assert.doesNotMatch(appCss, /#(?:[0-9a-f]{3,8})\b/i);
  assert.doesNotMatch(appCss, /\b(?:rgb|rgba|hsl|hsla|oklch)\(/i);
  assert.doesNotMatch(appCss, /font-family\s*:\s*['"][^)]+/i);
  assert.doesNotMatch(appCss, /transition\s*:\s*all\b/i);

  assert.match(appCss, /:focus-visible\b/);
  assert.match(appCss, /@media\s*\(\s*prefers-reduced-motion\s*:\s*reduce\s*\)/);
  assert.match(appCss, /html,\s*body[\s\S]*overflow-x:\s*clip/);

  const emojiRe = /[\u{1F300}-\u{1FAFF}\u{2600}-\u{27BF}]/u;
  assert.equal(emojiRe.test(indexHtml), false);
  assert.equal(emojiRe.test(appCss), false);
  assert.equal(emojiRe.test(tokensCss), false);

  for (const file of mjsFiles) {
    const src = readFileSync(file, 'utf8');
    assert.equal(emojiRe.test(src), false, `Emoji found in ${file}`);
    assert.doesNotMatch(src, /#(?:[0-9a-f]{3}|[0-9a-f]{6})\b/i, `Hex literal found in ${file}`);
    assert.doesNotMatch(src, /font-family\s*:/i, `font-family literal found in ${file}`);
  }
});

test('WCAG AA (>= 4.5:1) holds for all foreground/background token pairs in light and dark themes', () => {
  const tokensCss = readFileSync(join(ROOT, 'tokens.css'), 'utf8');
  const rootMatch = tokensCss.match(/:root\s*\{([\s\S]*?)\n\}/);
  const darkMatch = tokensCss.match(/\[data-mode="dark"\][\s\S]*?\{([\s\S]*?)\n\}/);
  assert.ok(rootMatch, 'Missing :root block');
  assert.ok(darkMatch, 'Missing [data-mode="dark"] block');

  const lightTokens = extractBlockTokens(rootMatch[1]);
  const darkTokens = { ...lightTokens, ...extractBlockTokens(darkMatch[1]) };

  const pairs = [
    ['--color-ink', '--color-paper'],
    ['--color-ink-2', '--color-paper'],
    ['--color-muted', '--color-paper'],
    ['--color-ink', '--color-surface-1'],
    ['--color-ink-2', '--color-surface-1'],
    ['--color-ink', '--color-surface-2'],
    ['--color-accent-ink', '--color-accent'],
    ['--color-accent-text', '--color-accent-soft'],
    ['--status-open', '--status-open-soft'],
    ['--status-working', '--status-working-soft'],
    ['--status-review', '--status-review-soft'],
    ['--status-verified', '--status-verified-soft'],
  ];

  for (const [modeName, tok] of [['light', lightTokens], ['dark', darkTokens]]) {
    for (const [fgKey, bgKey] of pairs) {
      const ratio = contrast(tok[fgKey], tok[bgKey]);
      assert.ok(ratio >= 4.5, `${modeName} contrast ${fgKey} on ${bgKey} = ${ratio.toFixed(2)} < 4.5`);
    }
  }
});

test('index.html has required landmarks, ARIA roles, and panel IDs', () => {
  const html = readFileSync(join(ROOT, 'index.html'), 'utf8');
  for (const snippet of [
    '<header ', '<main ', '<aside ', 'role="tablist"', 'role="tabpanel"', 'role="dialog"',
    'id="panel-command"', 'id="panel-topology"', 'id="panel-chronicle"', 'id="panel-squad"',
    'id="dossier-drawer"', 'id="settings-sheet"', 'id="settings-dialog"',
  ]) {
    assert.ok(html.includes(snippet), `Missing required HTML element: ${snippet}`);
  }
  assert.equal(/<script\b[^>]*\btype=["']module["'][^>]*\bsrc=/i.test(html), false, 'index.html must not use <script type="module" src=...> which triggers 401 Origin CORS failures on plugin://');
  const fontsCss = readFileSync(join(ROOT, 'fonts.css'), 'utf8');
  assert.equal(/url\(\s*['"]?\/?fonts\//i.test(fontsCss), false, 'fonts.css must not use external url(/fonts/...) which triggers 401 Origin CORS failures on plugin://');
});

test('patchKeyedChildren preserves DOM element identity on reorder, update, insert, and remove', () => {
  const doc = makeMockDoc();
  const container = doc.createElement('div');

  const els1 = patchKeyedChildren(
    container,
    [{ id: 'a', v: 1 }, { id: 'b', v: 2 }, { id: 'c', v: 3 }],
    (x) => x.id,
    () => doc.createElement('div'),
    (el, x) => { el.textContent = String(x.v); },
  );
  const [elA, elB, elC] = els1;
  assert.equal(container.children.length, 3);

  const els2 = patchKeyedChildren(
    container,
    [{ id: 'c', v: 30 }, { id: 'a', v: 10 }, { id: 'd', v: 40 }],
    (x) => x.id,
    () => doc.createElement('div'),
    (el, x) => { el.textContent = String(x.v); },
  );

  assert.equal(container.children.length, 3);
  assert.equal(els2[0], elC);
  assert.equal(els2[1], elA);
  assert.notEqual(els2[2], elB);
  assert.equal(elC.textContent, '30');
  assert.equal(elA.textContent, '10');
  assert.equal(elB.parentNode, null);
});
