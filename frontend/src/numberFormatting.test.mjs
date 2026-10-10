import assert from 'node:assert/strict';
import test from 'node:test';

import * as formatting from './shared/format/number.mjs';
const spaces = value => value.replace(/[\u00a0\u202f]/g, ' ');

test('display numbers preserve zero and identifiers, and never show non-finite values', () => {
  assert.equal(typeof formatting.formatNumber, 'function');
  assert.equal(formatting.formatNumber(0), '0');
  assert.equal(formatting.formatNumber(null), '—');
  assert.equal(formatting.formatNumber(NaN), '—');
  assert.equal(formatting.formatNumber(Infinity), '—');
  assert.equal(formatting.formatNumber('0017'), '0017');
  assert.equal(spaces(formatting.formatNumber(-1234.567)), '-1 234,57');
});

test('metric precision follows units without changing source values', () => {
  assert.equal(typeof formatting.formatMetric, 'function');
  assert.equal(formatting.formatMetric(.5954, 'о.е.'), '0,595');
  assert.equal(formatting.formatMetric(3.8846, 'кВт·ч/м³'), '3,885');
  assert.equal(spaces(formatting.formatMetric(696414.508, 'кВт·ч/год')), '696 415');
  assert.equal(spaces(formatting.formatMetric(3259.225, 'тыс. ₽/год')), '3 259,23');
  assert.equal(formatting.formatMetric(366.667, 'кВт'), '366,7');
  assert.equal(formatting.formatMetric(.5954, 'о.е.', 2), '0,6');
});
