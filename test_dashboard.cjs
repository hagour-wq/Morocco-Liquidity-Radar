const fs=require('node:fs'),vm=require('node:vm'),assert=require('node:assert/strict');
const html=fs.readFileSync('index.html','utf8');
const script=html.match(/<script>([\s\S]*?)<\/script>/)?.[1];
assert.ok(script,'Dashboard script must exist');
const dash=JSON.parse(fs.readFileSync('data/dashboard.json','utf8'));
const hist=JSON.parse(fs.readFileSync('data/market_history.json','utf8'));
const ranks=JSON.parse(fs.readFileSync('data/equity_rankings.json','utf8'));
const tbt=fs.existsSync('data/technical_backtest.json')?JSON.parse(fs.readFileSync('data/technical_backtest.json','utf8')):null;
const nodes=new Map();
function node(id){if(!nodes.has(id))nodes.set(id,{id,textContent:'',innerHTML:'',className:'',style:{},clientWidth:800,clientHeight:220,querySelectorAll(){return []},value:id==='techcat'?'ok':'',options:[],appendChild(o){this.options.push(o)},getContext(){return {scale(){},clearRect(){},beginPath(){},moveTo(){},lineTo(){},stroke(){},fillText(){}}}});return nodes.get(id)}
const sandbox={document:{getElementById:node,createElement(){return {}}},fetch:async url=>({ok:true,json:async()=>url.includes('dashboard')?dash:url.includes('equity_rankings')?ranks:url.includes('technical_backtest')?tbt:hist}),Date,Number,Math,window:{addEventListener(){}},devicePixelRatio:1,console};
vm.runInNewContext(script,sandbox,{timeout:3000});
setImmediate(()=>{
 assert.ok(!node('conclusion').textContent.includes('Erreur de chargement'),'No runtime error');
 assert.ok(node('liqparts').innerHTML.includes('Vérifié'),'Liquidity rows must render');
 assert.ok(node('range').textContent.includes('séances'),'Chart range must render');
 assert.ok(node('sources').innerHTML.length>0,'Source rows must render');
 assert.ok(node('longrank').textContent.length>0 || node('longrank').innerHTML.length>0,'Fundamentals panel must render');
 assert.ok(node('shortrank').textContent.length>0 || node('shortrank').innerHTML.length>0,'Technical panel must render');
 if(tbt){assert.ok(node('btgrid').innerHTML.includes('<table'),'Backtest table must render');assert.ok(!node('btgrid').innerHTML.includes('NaN'),'No NaN in backtest');}
 const lt=ranks.long_term||{};if((lt.ranked||[]).length){assert.ok(node('longrank').innerHTML.includes('<table'),'Fundamental ranking must render');for(const x of lt.ranked)assert.ok(node('longrank').innerHTML.includes('>'+x.ticker+'<'),'Fundamental ticker '+x.ticker);assert.ok(!node('longrank').innerHTML.includes('NaN'),'No NaN in fundamental table');}
 const st=ranks.short_term||{};const n=(st.ranked||[]).length+(st.watch||[]).length;
 if(n){assert.ok(node('shortrank').innerHTML.includes('<table'),'Technical ranking must render as a table');
  for(const x of (st.ranked||[]))assert.ok(node('shortrank').innerHTML.includes('>'+x.ticker+'<'),'Ticker '+x.ticker+' must be listed');
  assert.ok(!node('shortrank').innerHTML.includes('NaN'),'No NaN in technical table');}
 assert.ok(node('watchlist').innerHTML.length>0,'Snapshot watchlist must render');
 console.log('Dashboard smoke test passed');
});
