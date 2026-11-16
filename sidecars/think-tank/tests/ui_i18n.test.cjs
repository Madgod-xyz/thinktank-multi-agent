const test = require('node:test');
const assert = require('node:assert/strict');
require('../i18n.js');
const { locales, translate, roleText, formatNumber, skillNames } = globalThis.ThinkTankI18n;
const roles = require('../role_catalog.json');

test('locales.fa and locales.en have 100% key parity and non-empty strings', () => {
  assert.ok(locales && typeof locales === 'object', 'ThinkTankI18n.locales must be exported');
  assert.ok(locales.fa && typeof locales.fa === 'object', 'locales.fa must exist');
  assert.ok(locales.en && typeof locales.en === 'object', 'locales.en must exist');

  const faKeys = Object.keys(locales.fa).sort();
  const enKeys = Object.keys(locales.en).sort();
  assert.ok(enKeys.length >= 20, 'locales must expose structured UI translation keys');
  assert.deepEqual(faKeys, enKeys, 'locales.fa and locales.en must have identical key sets');

  for (const key of enKeys) {
    assert.equal(typeof locales.fa[key], 'string', `locales.fa[${key}] must be a string`);
    assert.equal(typeof locales.en[key], 'string', `locales.en[${key}] must be a string`);
    assert.ok(locales.fa[key].trim().length > 0, `locales.fa[${key}] must be non-empty`);
    assert.ok(locales.en[key].trim().length > 0, `locales.en[${key}] must be non-empty`);
    assert.equal(translate(key, 'en'), locales.en[key], `translate(${key}, 'en') must return locales.en value`);
    assert.equal(translate(key, 'fa'), locales.fa[key], `translate(${key}, 'fa') must return locales.fa value`);
  }
});

test('translates known keys and preserves unrecognized user text', () => {
  assert.equal(translate('custom user message', 'en'), 'custom user message');
  assert.equal(translate('custom user message', 'fa'), 'custom user message');
});

test('provides English titles, specialties, and descriptions for all 9 team roles and all skills', () => {
  assert.equal(roles.length, 9);
  for (const role of roles) {
    for (const field of ['title', 'specialty', 'description']) {
      assert.notEqual(roleText(role, field, 'en'), role[field], `${role.id} ${field} should have English copy`);
      assert.ok(roleText(role, field, 'en').length > 0, `${role.id} ${field} should not be empty`);
    }
    for (const skill of role.skills || []) {
      assert.ok(skillNames[skill], `${role.id} skill ${skill} should have an English label`);
    }
  }
});

test('formats numbers using the selected panel language', () => {
  assert.equal(formatNumber(1234, 'en'), '1,234');
  assert.equal(formatNumber(1234, 'fa'), '۱٬۲۳۴');
});
