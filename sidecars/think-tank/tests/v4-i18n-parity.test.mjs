import test from 'node:test';
import assert from 'node:assert/strict';
import {
  TRANSLATIONS,
  actionLabel,
  dirForLang,
  formatNum,
  normalizeLang,
  stateLabel,
  t,
  toneForState,
} from '../src/i18n.mjs';

function extractPlaceholders(str) {
  return Array.from(str.matchAll(/\{(\w+)\}/g)).map((m) => m[1]).sort();
}

test('TRANSLATIONS has 100% key and placeholder parity between fa and en', () => {
  const faKeys = Object.keys(TRANSLATIONS.fa).sort();
  const enKeys = Object.keys(TRANSLATIONS.en).sort();
  assert.deepEqual(faKeys, enKeys);

  for (const key of faKeys) {
    const faVal = TRANSLATIONS.fa[key];
    const enVal = TRANSLATIONS.en[key];
    assert.equal(typeof faVal, 'string');
    assert.equal(typeof enVal, 'string');
    assert.ok(faVal.trim().length > 0, `Empty fa string for ${key}`);
    assert.ok(enVal.trim().length > 0, `Empty en string for ${key}`);
    assert.deepEqual(
      extractPlaceholders(faVal),
      extractPlaceholders(enVal),
      `Placeholder mismatch for ${key}`,
    );
  }
});

test('formatNum, dirForLang, normalizeLang, and t behave consistently', () => {
  assert.equal(normalizeLang('fa-IR'), 'fa');
  assert.equal(normalizeLang('en-US'), 'en');
  assert.equal(dirForLang('fa'), 'rtl');
  assert.equal(dirForLang('en'), 'ltr');

  assert.equal(formatNum(2049, 'fa'), '۲۰۴۹');
  assert.equal(formatNum('105', 'en'), '105');

  const roundFa = t('pipe.round', { round: 2, max: 50 }, 'fa');
  const roundEn = t('pipe.round', { round: 2, max: 50 }, 'en');
  assert.ok(roundFa.includes('۲') && roundFa.includes('۵۰'));
  assert.equal(roundEn, 'Round 2 of 50');
});

test('actionLabel, stateLabel, and toneForState resolve all canonical actions and states', () => {
  for (const act of ['ASSIGN_TASK', 'RETURN_DEFECT', 'WORKER_FIX', 'PEER_SYNC', 'QA_DISPATCH', 'QA_REPORT', 'INTERROGATE', 'COMPLETE']) {
    assert.ok(actionLabel(act, 'fa').length > 0);
    assert.ok(actionLabel(act, 'en').length > 0);
    assert.notEqual(actionLabel(act, 'fa'), act);
  }

  for (const st of ['Open', 'Fixing', 'InReview', 'Testing', 'Verified', 'Closed', 'WontFix', 'WORKING', 'IDLE', 'COMPLETED']) {
    assert.ok(stateLabel(st, 'fa').length > 0);
    assert.ok(stateLabel(st, 'en').length > 0);
  }

  assert.equal(toneForState('CRITICAL'), 'open');
  assert.equal(toneForState('Fixing'), 'working');
  assert.equal(toneForState('InReview'), 'review');
  assert.equal(toneForState('Verified'), 'verified');
});
