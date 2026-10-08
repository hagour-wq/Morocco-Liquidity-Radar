"""BAM institutional source fallback: DEPF PDF discovery; never score unvalidated extracts."""
import json,re
from pathlib import Path
from datetime import datetime,timezone
from urllib.request import Request,urlopen
from urllib.parse import urljoin
OUT=Path("data/bam_liquidity.json")
URLS=[
 "https://www.bkam.ma/Marches/Principaux-indicateurs/Marche-monetaire/Marche-monetaire",
 "https://www.finances.gov.ma/fr/Pages/publications.aspx",
 "https://www.finances.gov.ma/Publication/depf/2026/Note-conjoncture347.pdf",
]
def main():
 d={"checked_at":datetime.now(timezone.utc).isoformat(),"verified":False,"candidates":[],"metrics":["bank_liquidity_need","total_injections","7d_advances","repo","guaranteed_loans"],"note":"Discovery only; no unverified score."}
 for u in URLS:
  try:
   with urlopen(Request(u,headers={"User-Agent":"Mozilla/5.0","Accept":"text/html,application/pdf,*/*"}),timeout=12) as r:
    content_type=r.headers.get("Content-Type","")
    raw=r.read(12000000)
   if raw.startswith(b"%PDF"):
    from io import BytesIO
    from pypdf import PdfReader
    reader=PdfReader(BytesIO(raw),strict=False)
    txt=" ".join((p.extract_text() or "") for p in reader.pages[:8])
    d["candidates"].append({"url":u,"format":"pdf","bytes":len(raw),"text_available":bool(txt),"mentions_liquidity":bool(re.search("liquidit",txt,re.I)),"sample":txt[:500]})
   else:
    h=raw.decode("utf-8","ignore")
    links=re.findall(r'href=["\\\']([^"\\\']+)["\\\']',h,re.I)
    hits=[urljoin(u,x) for x in links if any(z in x.lower() for z in ("liquid","conjonct","moneta","/depf/","nc_","publication"))]
    d["candidates"].extend({"url":x,"format":"link"} for x in hits[:20])
  except Exception as e:d.setdefault("errors",[]).append({"url":u,"error":type(e).__name__})
 OUT.write_text(json.dumps(d,ensure_ascii=False,indent=2)+"\n")
if __name__=="__main__":main()
