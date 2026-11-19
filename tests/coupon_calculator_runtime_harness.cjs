'use strict';
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');
const assert = require('node:assert/strict');
const root = path.resolve(__dirname, '..');
const source = fs.readFileSync(path.join(root, 'runtime-candidates/coupon-calculator-candidate.js'), 'utf8');
const fragment = fs.readFileSync(path.join(root, 'preview/coupon-calculator-fragment.html'), 'utf8');
const ids = [...fragment.matchAll(/\bid="([^"]+)"/g)].map(match => match[1]);
assert.equal(ids.length, new Set(ids).size);
let checks = 0;

function fixture() {
  let focused;
  const elements = Object.fromEntries(ids.map(id => [id, {
    value: '', checked: false, hidden: true, textContent: '', attributes: {},
    setAttribute(key, value) { this.attributes[key] = value; },
    removeAttribute(key) { delete this.attributes[key]; },
    focus() { focused = id; },
  }]));
  const handlers = {};
  const form = { addEventListener(key, callback) { assert.equal(handlers[key], undefined); handlers[key] = callback; } };
  elements['datalab-coupon-calculator'].querySelector = selector => {
    const id = selector.match(/^\[id="([^"]+)"\]$/)?.[1];
    assert.ok(elements[id], selector); return elements[id];
  };
  const context = vm.createContext({ document: {
    getElementById(id) { assert.equal(id, 'datalab-coupon-calculator'); return elements[id]; },
    querySelector(selector) { assert.equal(selector, '#datalab-coupon-calculator form'); return form; },
  } });
  const globals = Object.keys(context);
  vm.runInContext(source, context);
  assert.deepEqual(Object.keys(context), globals, 'candidate must not export globals');
  function checkDynamicReferences() {
    for (const element of Object.values(elements)) {
      for (const attribute of ['aria-describedby', 'aria-labelledby']) {
        for (const id of (element.attributes[attribute] || '').split(/\s+/).filter(Boolean)) {
          assert.ok(elements[id], 'runtime reference must resolve: ' + id);
        }
      }
    }
  }
  checkDynamicReferences();
  const get = name => elements['calc-' + name];
  function submit(total, discount, points, confirmed = true) {
    get('total').value = total; get('discount').value = discount; get('points').value = points;
    get('scope').checked = confirmed;
    handlers.input();
    let prevented = false;
    handlers.submit({ preventDefault() { prevented = true; } });
    checkDynamicReferences();
    assert.ok(prevented, 'never submit the form');
    checks++;
    return !get('result').hidden;
  }
  return { get, submit, handlers, focus: () => focused };
}
const f = fixture();
function valid(t, d, p, payment, awarded, difference) {
  assert.equal(f.submit(t, d, p), true);
  const format = text => BigInt(text).toLocaleString('ja-JP');
  assert.equal(f.get('payment-result').textContent, format(payment) + '円');
  assert.equal(f.get('points-result').textContent, format(awarded) + 'ポイント');
  assert.equal(f.get('difference-result').textContent, format(difference) + 'ポイント');
}
valid('2000', '500', '200', '1500', '150', '50');
valid('2000', '0', '200', '2000', '200', '0');
valid('2000', '2000', '200', '0', '0', '200');
valid('3', '1', '100', '2', '66', '34');
valid('1', '0', '0', '1', '0', '0');
valid('9999999', '1', '9999999', '9999998', '9999998', '1');
for (const value of ['', '-1', '1.5', '1e3', 'Infinity', 'NaN', '２０００', '2,000', ' 2', '2 ', '10000000', '<script>', null, 12]) {
  for (let index = 0; index < 3; index++) {
    const raw = ['2000', '500', '200']; raw[index] = value;
    assert.equal(f.submit(...raw), false);
    assert.equal(f.get(['total', 'discount', 'points'][index]).attributes['aria-invalid'], 'true');
  }
}
assert.equal(f.submit('2000', '500', '200', false), false);
assert.equal(f.focus(), 'calc-scope');
assert.equal(f.submit('0', '0', '0'), false);
assert.equal(f.submit('10', '11', '0'), false);
assert.equal(f.focus(), 'calc-discount');
for (let total = 1; total <= 50; total++) {
  let previous = 138n;
  for (let discount = 0; discount <= total; discount++) {
    assert.equal(f.submit(String(total), String(discount), '137'), true);
    const parse = id => BigInt(f.get(id).textContent.replace(/[^0-9]/g, ''));
    const payment = parse('payment-result');
    const awarded = parse('points-result');
    const difference = parse('difference-result');
    assert.equal(payment + BigInt(discount), BigInt(total));
    assert.equal(awarded + difference, 137n);
    assert.ok(awarded <= previous && awarded >= 0n);
    assert.ok(awarded * BigInt(total) <= 137n * payment);
    assert.ok((awarded + 1n) * BigInt(total) > 137n * payment);
    previous = awarded;
  }
}
valid('2000', '500', '200', '1500', '150', '50');
f.get('discount').value = '3000'; f.handlers.input();
assert.equal(f.get('result').hidden, true);
assert.match(f.get('message').textContent, /もう一度/);
f.submit('2000', '3000', '200');
valid('2000', '500', '200', '1500', '150', '50');
assert.equal(f.get('discount').attributes['aria-invalid'], undefined);
f.handlers.reset();
assert.equal(f.get('result').hidden, true);
assert.equal(f.get('discount-error').textContent, '');
assert.match(f.get('message').textContent, /もう一度確認/);
// No widget on a page must be inert, and must not even query a form.
vm.runInNewContext(source, { document: {
  getElementById() { return null; }, querySelector() { throw Error('unexpected form access'); },
} });
for (const match of fragment.matchAll(/\b(?:for|aria-describedby|aria-labelledby)="([^"]+)"/g)) {
  for (const id of match[1].split(/\s+/)) assert.ok(ids.includes(id), id);
}
console.log(`PASS ${checks} inert-DOM submissions plus scope, stale results, focus, reset handler, missing-root and no-global checks; no browser rendering or network`);
