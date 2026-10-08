"""Discover and inspect official Casablanca monthly PDF archives without inventing daily OHLCV.
Produces publication metadata and issuer passages for later manual/schema validation.
Monthly observations are deliberately NOT added to daily equity_history.json.
"""
import json,re,ssl,certifi
from io import BytesIO
from pathlib import Path
from datetime import datetime,timezone
from urllib.request import Request,urlopen
from urllib.parse import urljoin
from pypdf import PdfReader
ROOT=Path("data")
OUT=ROOT/"official_equity_archive.json"
ARCHIVE="https://www.casablanca-bourse.com/market-data/editions-statistiques"
SEEDS=[
 ("2026-01","https://media.casablanca-bourse.com/sites/default/files/2026-02/rapport_mensuel_1_2026.pdf"),
 ("2026-03","https://media.casablanca-bourse.com/sites/default/files/2026-04/rapport_mensuel_3_2026_0.pdf")
]
ISSUERS={"ATW":["ATTIJARIWAFA"],"BCP":["BANQUE CENTRALE POPULAIRE","BCP"],"MSA":["MARSA MAROC"],"ADH":["ADDOHA"],"LHM":["LAFARGEHOLCIM"],"SNP":["SNEP"],"DHO":["DELTA HOLDING"],"LES":["LESIEUR CRISTAL"],"MNG":["MANAGEM"],"TGCC":["TGCC"]}
def fetch(url,limit=18000000):
 req=Request(url,headers={"User-Agent":"Mozilla/5.0","Accept":"application/pdf,text/html,*/*"})
 ctx=ssl.create_default_context(cafile=certifi.where())
 with urlopen(req,timeout=16,context=ctx) as res:
  body=res.read(limit+1)
 if len(body)>limit:raise ValueError("Too large")
 return body
def discover():
 try:
  html=fetch(ARCHIVE,4000000).decode("utf-8","ignore")
  links=re.findall(r'href=["\\\']([^"\\\']+)["\\\']',html,re.I)
  result=[]
  for u in links:
   absolute=urljoin(ARCHIVE,u)
   if absolute.lower().endswith(".pdf") and any(word in absolute.lower() for word in ("mensuel","stat","rapport")):
    result.append(absolute)
  return list(dict.fromkeys(result)),None
 except Exception as e:return [],type(e).__name__+":"+str(e)[:120]
def inspect(period,url):
 raw=fetch(url)
 if not raw.startswith(b"%PDF"):raise ValueError("Not PDF")
 pdf=PdfReader(BytesIO(raw),strict=False)
 matches=[]
 for i,page in enumerate(pdf.pages):
  txt=" ".join((page.extract_text() or "").split())
  for ticker,names in ISSUERS.items():
   found=next((re.search(re.escape(n),txt,re.I) for n in names if re.search(re.escape(n),txt,re.I)),None)
   if found:
    a=max(0,found.start()-65);b=min(len(txt),found.end()+210)
    matches.append({"ticker":ticker,"page":i+1,"context":txt[a:b]})
 return {"period":period,"url":url,"pages":len(pdf.pages),"issuer_passages":matches[:80],"status":"TEXT_INSPECTED_NO_DAILY_RANKING"}
def main():
 result={"checked_at":datetime.now(timezone.utc).isoformat(),"policy":"Monthly reports are NOT daily price history; extracts require schema verification.","publications":[],"errors":[]}
 links,err=discover()
 if err:result["errors"].append({"url":ARCHIVE,"error":err})
 candidates=SEEDS[:]
 for u in links[:8]:
  if u not in [s[1] for s in candidates]:candidates.append(("discovered",u))
 for period,url in candidates[:8]:
  try:result["publications"].append(inspect(period,url))
  except Exception as e:result["errors"].append({"url":url,"error":type(e).__name__+":"+str(e)[:180]})
 result["status"]="INSPECTED" if result["publications"] else "SOURCES_UNAVAILABLE"
 OUT.write_text(json.dumps(result,ensure_ascii=False,indent=2)+"\n",encoding="utf-8")
 print(json.dumps({"status":result["status"],"inspected":len(result["publications"]),"errors":len(result["errors"])},ensure_ascii=False))
if __name__=="__main__":main()
