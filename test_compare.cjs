// Test de fumée du comparateur : la page se rend avec les données réelles, sans erreur ni NaN.
const fs=require('node:fs'),vm=require('node:vm'),assert=require('node:assert/strict');
const html=fs.readFileSync('compare.html','utf8');
const script=html.match(/<script>([\s\S]*?)<\/script>/)?.[1];
assert.ok(script,'Le script du comparateur doit exister');
const ranks=JSON.parse(fs.readFileSync('data/equity_rankings.json','utf8'));
const dash=JSON.parse(fs.readFileSync('data/dashboard.json','utf8'));
const nodes=new Map();
const node=id=>{if(!nodes.has(id))nodes.set(id,{id,innerHTML:'',value:'',addEventListener(){},onclick:null});return nodes.get(id)};
const sandbox={document:{getElementById:node,querySelectorAll:()=>[],addEventListener(){}},URLSearchParams,history:{replaceState(){}},location:{search:''},
 fetch:async u=>({json:async()=>u.includes('rankings')?ranks:dash}),console};
vm.runInNewContext(script,sandbox,{timeout:3000});
setTimeout(()=>{
 const out=node('out').innerHTML;
 assert.ok(out.includes('<table'),'Le tableau comparatif doit être rendu');
 assert.ok(!out.includes('NaN')&&!out.includes('undefined'),'Pas de NaN / undefined');
 assert.ok(node('short').innerHTML.length>0&&node('wait').innerHTML.length>0,'Short-lists rendues');
 assert.ok(node('ctx').innerHTML.includes('Régime'),'Contexte de marché rendu');
 for(const x of (ranks.long_term.ranked||[]).filter(x=>x.profile==='Solide'))
  assert.ok((node('short').innerHTML+node('wait').innerHTML).includes('data-t="'+x.ticker+'"'),'Titre Solide '+x.ticker+' proposé');
 console.log('Comparateur : test de fumée réussi');
},50);
