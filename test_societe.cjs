// Test de la fiche société (societe.html) : rendu de chaque valeur cotée avec les données de production,
// sans erreur d'exécution, sans NaN / undefined, et message explicite pour les titres sans historique exploitable.
const fs = require('node:fs'), vm = require('node:vm'), assert = require('node:assert/strict');
const html = fs.readFileSync('societe.html', 'utf8');
const script = html.match(/<script>([\s\S]*?)<\/script>/)?.[1];
assert.ok(script, 'Le script de la fiche doit exister');
const read = p => JSON.parse(fs.readFileSync(p.split('?')[0], 'utf8'));
const index = read('data/equities/index.json');
const ctx = new Proxy({}, { get: () => () => {}, set: () => true });
const results = [];

async function render(ticker) {
  const nodes = new Map();
  const node = id => {
    if (!nodes.has(id)) nodes.set(id, { id, textContent: '', innerHTML: '', hidden: true, value: '', style: {}, children: [],
      clientWidth: 900, clientHeight: 300, offsetWidth: 120, setAttribute() {}, addEventListener() {},
      getBoundingClientRect: () => ({ left: 0, width: 900 }), getContext: () => ctx, width: 0, height: 0 });
    return nodes.get(id);
  };
  const errors = [];
  const sandbox = {
    document: { getElementById: node, title: '' }, history: { replaceState() {} }, location: { search: '?t=' + ticker },
    URLSearchParams, Date, Number, Math, String, Object, Promise, isFinite, encodeURIComponent, devicePixelRatio: 1, addEventListener() {},
    console: { ...console, error: e => errors.push(String(e)) },
    fetch: async url => { const p = url.split('?')[0]; return fs.existsSync(p) ? { ok: true, status: 200, json: async () => read(p) } : { ok: false, status: 404 }; },
  };
  vm.runInNewContext(script, sandbox, { timeout: 5000 });
  for (let i = 0; i < 20; i++) await new Promise(r => setImmediate(r));
  return { node, errors };
}

(async () => {
  for (const c of index.companies) {
    const { node, errors } = await render(c.ticker);
    assert.deepEqual(errors, [], c.ticker + ' : erreur console');
    if (node('content').hidden) {
      assert.match(node('err').innerHTML, /Fiche indisponible : .+suspendu de cotation/, c.ticker + ' : seul un titre suspendu peut être indisponible — ' + node('err').innerHTML);
      results.push(c.ticker + ' (indisponible)');
      continue;
    }
    for (const id of ['tech', 'fund', 'stmts', 'div', 'quality', 'last', 'mcap', 'var', 'chartnote'])
      for (const bad of ['NaN', 'undefined', 'Infinity'])
        assert.ok(!(node(id).innerHTML + node(id).textContent).includes(bad), c.ticker + ' : ' + bad + ' dans #' + id);
    assert.match(node('chartnote').textContent, /séances affichées/, c.ticker + ' : graphique');
    assert.match(node('quality').innerHTML, /Séances en base/, c.ticker + ' : qualité des données');
    results.push(c.ticker);
  }
  const ok = results.filter(x => !x.includes('indisponible'));
  assert.ok(ok.length >= 70, 'Au moins 70 fiches rendues (' + ok.length + ')');
  // valeur inconnue : message, pas de page blanche
  const { node } = await render('ZZZ');
  assert.ok(node('content').hidden && /HTTP 404/.test(node('err').innerHTML), 'Ticker inconnu : message 404');
  console.log('Fiches société : ' + ok.length + ' rendues, indisponibles : ' + results.filter(x => x.includes('indisponible')).join(', '));
})().catch(e => { console.error(e); process.exit(1); });
