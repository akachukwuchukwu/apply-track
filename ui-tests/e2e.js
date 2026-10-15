/*
 * End-to-end checks for the demo page. Loads the real page from a running
 * server in a simulated browser (jsdom) and drives it like a user: sign-in
 * (wrong and right password), filtering, search, changing a status, adding
 * records, pagination, session expiry, sign-out, and an injection attempt.
 *
 * Run against a FRESHLY SEEDED database; it adds records, so re-seed between runs:
 *   rm db.sqlite3 && python manage.py migrate && python manage.py seed_demo_data
 *   python manage.py runserver          (in another terminal)
 *   cd ui-tests && npm install && npm test
 *
 * Set BASE to test a server on another address (default http://localhost:8000).
 */
const { JSDOM } = require('jsdom');
const BASE = process.env.BASE || 'http://localhost:8000';

let passed = 0, failed = 0;
function check(name, cond, extra) {
  if (cond) { passed++; console.log('  PASS  ' + name); }
  else { failed++; console.log('  FAIL  ' + name + (extra ? '  -> ' + extra : '')); }
}
const sleep = (ms) => new Promise((r) => setTimeout(r, ms));
async function waitFor(fn, label, timeout = 6000) {
  const t0 = Date.now();
  while (Date.now() - t0 < timeout) {
    try { if (fn()) return true; } catch (e) { /* keep polling */ }
    await sleep(40);
  }
  console.log('  (timed out waiting for: ' + label + ')');
  return false;
}

async function apiToken() {
  const r = await fetch(BASE + '/api/token/', {
    method: 'POST', headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ username: 'demo', password: 'demo-password-123' }),
  });
  return (await r.json()).access;
}

(async () => {
  const html = await (await fetch(BASE + '/')).text();
  const errors = [];
  const dom = new JSDOM(html, {
    url: BASE + '/', runScripts: 'dangerously', pretendToBeVisual: true,
    beforeParse(window) {
      window.fetch = (u, o) => fetch(new URL(u, BASE), o);
      window.addEventListener('error', (e) => errors.push(e.message));
    },
  });
  const { window } = dom;
  const doc = window.document;
  const $ = (id) => doc.getElementById(id);
  const fire = (node, type) => node.dispatchEvent(new window.Event(type, { bubbles: true, cancelable: true }));
  const rows = () => [...doc.querySelectorAll('#rows tr')].filter((r) => !r.querySelector('.empty'));

  console.log('\n[1] first load');
  check('sign-in form is visible', !$('login').hidden);
  check('app is hidden before sign-in', $('app').hidden);

  console.log('\n[2] wrong password');
  $('username').value = 'demo'; $('password').value = 'not-the-password';
  fire($('login-form'), 'submit');
  await waitFor(() => $('login-msg').textContent !== '', 'login error');
  check('friendly error shown', $('login-msg').textContent === 'Wrong username or password.', $('login-msg').textContent);
  check('app stays hidden', $('app').hidden);
  check('button re-enabled after failure', !$('login-btn').disabled);

  console.log('\n[3] correct sign-in via the demo button');
  $('fill-demo').click();
  check('demo button fills both fields', $('username').value === 'demo' && $('password').value === 'demo-password-123');
  fire($('login-form'), 'submit');
  await waitFor(() => rows().length > 0, 'applications table');
  // summary and list load in parallel, so wait for the summary explicitly
  await waitFor(() => $('stat-total').textContent === '10' && $('by-status').children.length > 0, 'summary loaded');
  check('app is shown, sign-in hidden', !$('app').hidden && $('login').hidden);
  check('username shown in header', $('who-name').textContent === 'demo');
  check('total = 10', $('stat-total').textContent === '10', $('stat-total').textContent);
  check('response rate = 70%', $('stat-rate').textContent === '70%', $('stat-rate').textContent);
  check('average days = 4.7', $('stat-days').textContent === '4.7', $('stat-days').textContent);
  check('10 rows rendered', rows().length === 10, String(rows().length));
  check('status chips rendered', $('by-status').children.length >= 4);
  check('company picker populated', $('company-list').children.length === 10, String($('company-list').children.length));

  console.log('\n[4] filter by status');
  $('filter').value = 'REJECTED'; fire($('filter'), 'change');
  await waitFor(() => rows().length === 3, 'filtered rows');
  check('3 rejected applications', rows().length === 3, String(rows().length));
  check('every visible row says Rejected', rows().every((r) => r.textContent.includes('Rejected')));
  $('filter').value = ''; fire($('filter'), 'change');
  await waitFor(() => rows().length === 10, 'filter cleared');
  check('clearing the filter restores all 10', rows().length === 10);

  console.log('\n[5] search (debounced)');
  $('search').value = 'Anchorpoint'; fire($('search'), 'input');
  await waitFor(() => rows().length === 1, 'search results', 3000);
  check('search narrows to one match', rows().length === 1, String(rows().length));
  check('the match is the right company', rows()[0].textContent.includes('Anchorpoint AI'));
  $('search').value = 'zzzz-nothing'; fire($('search'), 'input');
  await waitFor(() => doc.querySelector('#rows .empty'), 'empty state', 3000);
  check('empty state shown for no matches', !!doc.querySelector('#rows .empty'));
  $('search').value = ''; fire($('search'), 'input');
  await waitFor(() => rows().length === 10, 'search cleared', 3000);

  console.log('\n[6] open an application and change its status');
  rows()[0].querySelector('button').click();
  await waitFor(() => $('change-form'), 'detail panel');
  check('detail panel rendered', !!$('change-form'));
  check('history list present', [...doc.querySelectorAll('#detail h3')].some((h) => h.textContent === 'Status history'));
  const before = doc.querySelectorAll('#detail ul')[0].children.length;
  const current = $('change-status').value;
  $('change-status').value = current === 'OFFER' ? 'ACCEPTED' : 'OFFER';
  $('change-note').value = 'e2e status change';
  fire($('change-form'), 'submit');
  await waitFor(() => doc.querySelectorAll('#detail ul')[0] && doc.querySelectorAll('#detail ul')[0].children.length === before + 1, 'history grows');
  const hist = doc.querySelectorAll('#detail ul')[0];
  check('history gained exactly one event', hist.children.length === before + 1, `${before} -> ${hist.children.length}`);
  check('new event carries the note', hist.lastElementChild.textContent.includes('e2e status change'));
  check('selected row is highlighted', !!doc.querySelector('#rows tr.selected'));

  console.log('\n[7] add an application (new company)');
  $('add-company').value = 'Brand New Co'; $('add-role').value = 'Staff Engineer'; $('add-status').value = 'APPLIED';
  fire($('add-form'), 'submit');
  await waitFor(() => $('stat-total').textContent === '11', 'total becomes 11');
  check('total is now 11', $('stat-total').textContent === '11', $('stat-total').textContent);
  await waitFor(() => doc.querySelector('#detail h2') && doc.querySelector('#detail h2').textContent === 'Staff Engineer', 'new app opens');
  check('the new application opens in the detail panel', doc.querySelector('#detail h2').textContent === 'Staff Engineer');
  check('new company added to the picker', $('company-list').children.length === 11, String($('company-list').children.length));
  check('form was reset', $('add-company').value === '' && $('add-role').value === '');

  console.log('\n[8] add an application for an EXISTING company (different letter case)');
  $('add-company').value = 'northwind ANALYTICS'; $('add-role').value = 'Second Role'; $('add-status').value = 'WISHLIST';
  fire($('add-form'), 'submit');
  await waitFor(() => $('stat-total').textContent === '12', 'total becomes 12');
  check('total is now 12', $('stat-total').textContent === '12');
  check('no duplicate company was created', $('company-list').children.length === 11, String($('company-list').children.length));

  console.log('\n[9] hostile input is displayed as text, never executed');
  $('add-company').value = '<img src=x onerror="window.__pwned=1">';
  $('add-role').value = '<b>bold-attempt</b>';
  fire($('add-form'), 'submit');
  await waitFor(() => $('stat-total').textContent === '13', 'total becomes 13');
  await sleep(300);
  check('injected script did not run', window.__pwned === undefined);
  check('no <img> element was created', doc.querySelectorAll('#rows img, #detail img').length === 0);
  check('markup shown literally as text', doc.querySelector('#detail h2').textContent === '<b>bold-attempt</b>');
  check('no <b> element was created', doc.querySelectorAll('#detail h2 b, #rows b').length === 0);

  console.log('\n[10] pagination');
  const tok = await apiToken();
  const cos = await (await fetch(BASE + '/api/companies/?page=1', { headers: { Authorization: 'Bearer ' + tok } })).json();
  for (let i = 0; i < 9; i++) {
    await fetch(BASE + '/api/applications/', {
      method: 'POST', headers: { 'Content-Type': 'application/json', Authorization: 'Bearer ' + tok },
      body: JSON.stringify({ company: cos.results[0].id, role_title: 'Bulk ' + i, status: 'APPLIED' }),
    });
  }
  fire($('filter'), 'change');   // reload the list
  await waitFor(() => $('count').textContent === '22 applications', 'count 22');
  check('count reflects 22 applications', $('count').textContent === '22 applications', $('count').textContent);
  check('first page shows 20 rows', rows().length === 20, String(rows().length));
  check('Previous disabled on page 1', $('prev').disabled);
  check('Next enabled on page 1', !$('next').disabled);
  $('next').click();
  await waitFor(() => rows().length === 2, 'page 2');
  check('page 2 shows the remaining 2', rows().length === 2, String(rows().length));
  check('page label says Page 2', $('page-label').textContent === 'Page 2', $('page-label').textContent);
  check('Next disabled on the last page', $('next').disabled);
  check('Previous enabled on page 2', !$('prev').disabled);

  console.log('\n[11] session expiry');
  const realFetch = window.fetch;
  window.fetch = (u, o) => String(u).includes('/api/applications/?')
    ? Promise.resolve(new Response(JSON.stringify({ detail: 'Token expired' }), { status: 401 }))
    : realFetch(u, o);
  fire($('filter'), 'change');
  await waitFor(() => !$('login').hidden, 'sign-in returns');
  check('expired token sends the user back to sign-in', !$('login').hidden && $('app').hidden);
  check('explains why', $('login-msg').textContent.includes('expired'), $('login-msg').textContent);
  window.fetch = realFetch;

  console.log('\n[12] sign out');
  $('fill-demo').click();
  fire($('login-form'), 'submit');
  await waitFor(() => !$('app').hidden && rows().length > 0, 'signed in again');
  $('logout').click();
  check('sign-out shows the sign-in form', !$('login').hidden && $('app').hidden);
  check('password field is cleared', $('password').value === '');
  check('table is not left readable after sign-out', $('app').hidden);

  console.log('\n[13] page health');
  check('no uncaught JavaScript errors', errors.length === 0, errors.join(' | '));

  console.log(`\n==== ${passed} passed, ${failed} failed ====`);
  window.close();
  process.exit(failed ? 1 : 0);
})().catch((e) => { console.error('SCRIPT CRASHED:', e); process.exit(2); });
