"""BAM liquidity collector: discovery/probing only until a current official 2026 schema is validated."""
import json,re
from pathlib import Path
from datetime import datetime,timezone
from urllib.request import Request,urlopen
OUT=Path("data/bam_liquidity.json")
URLS=[
 "https://www.bkam.ma/Marches/Principaux-indicateurs/Marche-monetaire/Marche-monetaire",
 "https://www.bkam.ma/Publications-statistiques-et-recherche/Documents-statistiques"
]
def main():
 d={"checked_at":datetime.now(timezone.utc).isoformat(),"verified":False,"candidates":[],"metrics":["bank_liquidity_need","total_injections","7d_advances","repo","guaranteed_loans"]}
 for u in URLS:
  try:
   req=Request(u,headers={"User-Agent":"Mozilla/5.0","Accept":"text/html,*/*"})
   with urlopen(req,timeout=30) as r:
    h=r.read().decode("utf-8","ignore")
   links=re.findall(r'href=["\\\']([^"\\\']+)["\\\']',h,re.I)
   hits=[x for x in links if any(z in x.lower() for z in ("liquid","bulletin","trimestr","conjonct","moneta"))]
   d["candidates"].extend(hits[:30])
  except Exception as e:d.setdefault("errors",[]).append({"url":u,"error":type(e).__name__})
 OUT.write_text(json.dumps(d,ensure_ascii=False,indent=2)+"\n")
if __name__=="__main__":main()
