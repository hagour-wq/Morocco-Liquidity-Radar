"""Institutional banking liquidity research. Discover DEPF PDFs and quote context; no speculative scores."""
import json,re
from io import BytesIO
from pathlib import Path
from datetime import datetime,timezone,date
from urllib.request import Request,urlopen
from urllib.parse import urljoin
from pypdf import PdfReader
OUT=Path("data/bam_liquidity.json")
ROOT="https://www.finances.gov.ma/fr/Pages/publications.aspx"
URLS=["https://www.bkam.ma/Marches/Principaux-indicateurs/Marche-monetaire/Marche-monetaire",ROOT]
def fetch(url,limit=18000000):
 with urlopen(Request(url,headers={"User-Agent":"Mozilla/5.0","Accept":"application/pdf,text/html,*/*"}),timeout=18) as r:
  return r.read(limit+1)
def number(s):return float(s.replace(" ","").replace(",","."))
def extract_monthly(text):
 t=" ".join(text.split())
 # Restrict each match to a short clause around the statistical publication.
 req=re.search(r"se situant en moyenne hebdomadaire à\\s*([0-9]+(?:[,.][0-9]+)?)\\s*milliards? de dirhams? après\\s*([0-9]+(?:[,.][0-9]+)?)\\s*milliards?",t,re.I)
 inj=re.search(r"injections de liquidité.{0,110}?moyenne hebdomadaire à\\s*([0-9]+(?:[,.][0-9]+)?)\\s*milliards? de dirhams?,? après\\s*([0-9]+(?:[,.][0-9]+)?)\\s*milliards?",t,re.I)
 if not (req and inj):return None
 x={"liquidity_need_current_bn_mad":number(req.group(1)),"liquidity_need_previous_bn_mad":number(req.group(2)),"injections_current_bn_mad":number(inj.group(1)),"injections_previous_bn_mad":number(inj.group(2))}
 if not (30<x["liquidity_need_current_bn_mad"]<400 and 30<x["injections_current_bn_mad"]<400):return None
 return x
def pdf_report(url):
 raw=fetch(url)
 if len(raw)>18000000:raise ValueError("PDF exceeds 18 MB")
 if not raw.startswith(b"%PDF"):raise ValueError("Not a PDF response")
 reader=PdfReader(BytesIO(raw),strict=False)
 matches=[]
 extracted=[]
 for i,p in enumerate(reader.pages):
  t=" ".join((p.extract_text() or "").split())
  vals=extract_monthly(t)
  if vals:extracted.append({"page":i+1,**vals})
  for keyword in ("besoin de liquidité","besoins de liquidité","injections de liquidité","interventions de bank al-maghrib","liquidité bancaire"):
   for m in list(re.finditer(re.escape(keyword),t,re.I))[:2]:
    matches.append({"page":i+1,"keyword":keyword,"context":t[max(0,m.start()-220):m.end()+330]})
 return {"url":url,"pages":len(reader.pages),"bytes":len(raw),"matches":matches[:24],"numeric_candidates":extracted,"verified":False}
def main():
 d={"checked_at":datetime.now(timezone.utc).isoformat(),"verified":False,"candidates":[],"pdf_inspections":[],"metrics":["bank_liquidity_need","total_injections","7d_advances","repo","guaranteed_loans"],"note":"Unvalidated institutional excerpts never enter liquidity scoring."}
 pdfs=[]
 for url in URLS:
  try:
   raw=fetch(url,2000000)
   h=raw.decode("utf-8","ignore")
   links=re.findall(r'href=["\\\']([^"\\\']+)["\\\']',h,re.I)
   hits=[urljoin(url,x).replace("http://www.finances.gov.ma/","https://www.finances.gov.ma/") for x in links if "/depf/" in x.lower() and ".pdf" in x.lower()]
   for x in dict.fromkeys(hits):
    if "/2026/" in x and len(pdfs)<3:pdfs.append(x)
    d["candidates"].append({"url":x,"format":"link"})
  except Exception as e:d.setdefault("errors",[]).append({"url":url,"error":type(e).__name__})
 for url in pdfs[:2]:
  try:d["pdf_inspections"].append(pdf_report(url))
  except Exception as e:d.setdefault("errors",[]).append({"url":url,"error":type(e).__name__,"detail":str(e)[:150]})
 OUT.write_text(json.dumps(d,ensure_ascii=False,indent=2)+"\n",encoding="utf-8")
if __name__=="__main__":main()
