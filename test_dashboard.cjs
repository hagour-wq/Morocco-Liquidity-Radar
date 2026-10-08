const fs=require('node:fs'),vm=require('node:vm'),assert=require('node:assert/strict');
const html=fs.readFileSync('index.html','utf8');
const script=html.match(/<script>([\s\S]*?)<\/script>/)?.[1];
assert.ok(script,'Dashboard script must exist');
const dash=JSON.parse(fs.readFileSync('data/dashboard.json','utf8'));
const hist=JSON.parse(fs.readFileSync('data/market_history.json','utf8'));
const nodes=new Map();
function node(id){if(!nodes.has(id))nodes.set(id,{id,textContent:'',innerHTML:'',className:'',style:{},clientWidth:800,clientHeight:220,getContext(){return {scale(){},clearRect(){},beginPath(){},moveTo(){},lineTo(){},stroke(){},fillText(){}}}});return nodes.get(id)}
const sandbox={document:{getElementById:node},fetch:async url=>({ok:true,json:async()=>url.includes('dashboard')?dash:hist}),Date,Number,Math,window:{addEventListener(){}},devicePixelRatio:1,console};
vm.runInNewContext(script,sandbox,{timeout:3000});
setImmediate(()=>{
 assert.ok(!node('conclusion').textContent.includes('Erreur de chargement'),'No runtime error');
 assert.ok(node('liqparts').innerHTML.includes('Vérifié'),'Liquidity rows must render');
 assert.ok(node('range').textContent.includes('séances'),'Chart range must render');
 assert.ok(node('sources').innerHTML.length>0,'Source rows must render');
 console.log('Dashboard smoke test passed');
});
