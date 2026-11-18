export const SVG_NS = 'http://www.w3.org/2000/svg';

const ESC_MAP = { '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' };

export function escapeHtml(raw) {
  return String(raw ?? '').replace(/[&<>"']/g, (ch) => ESC_MAP[ch] || ch);
}

export function setText(el, nextValue) {
  if (!el) return;
  const text = String(nextValue ?? '');
  if (el.textContent !== text) el.textContent = text;
}

export function setAttr(el, name, value) {
  if (!el) return;
  if (value === null || value === undefined || value === false) {
    if (el.hasAttribute?.(name)) el.removeAttribute(name);
    return;
  }
  const str = String(value);
  if (el.getAttribute?.(name) !== str) el.setAttribute(name, str);
}

export function createSvgEl(doc, tag, attrs = {}) {
  const el = doc.createElementNS(SVG_NS, tag);
  for (const [k, v] of Object.entries(attrs)) setAttr(el, k, v);
  return el;
}

export function patchKeyedChildren(container, items, keyFn, createFn, updateFn, keyAttr = 'data-key') {
  if (!container) return [];
  const existing = new Map();
  const initialChildren = Array.from(container.children || []);
  for (const child of initialChildren) {
    const k = child.getAttribute?.(keyAttr);
    if (k !== null && k !== undefined && k !== '') existing.set(k, child);
    else child.remove?.();
  }

  const nextEls = [];
  const seenKeys = new Set();
  for (let i = 0; i < items.length; i += 1) {
    const item = items[i];
    const key = String(keyFn(item, i));
    if (seenKeys.has(key)) continue;
    seenKeys.add(key);
    let el = existing.get(key);
    if (!el) {
      el = createFn(item, i);
      setAttr(el, keyAttr, key);
    } else {
      existing.delete(key);
    }
    if (updateFn) updateFn(el, item, i);
    nextEls.push(el);
  }

  for (const stale of existing.values()) stale.remove?.();

  let cursor = container.firstElementChild || container.children?.[0] || null;
  for (const el of nextEls) {
    if (cursor === el) {
      cursor = cursor.nextElementSibling || null;
    } else {
      container.insertBefore(el, cursor);
    }
  }
  return nextEls;
}
