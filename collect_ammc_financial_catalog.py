"""Catalogue discoverable AMMC issuer financial reports; does not infer issuer financial ratios."""
import json,re,ssl,certifi
from pathlib import Path
from datetime import datetime,timezone
from urllib.request import Request,urlopen
from urllib.parse import urljoin
from html.parser import HTMLParser
ROOT=Path("data")
OUT=ROOT/"ammc_fundamental_catalog.json"
BASE="https://www.ammc.ma/fr/liste-etats-financiers-emetteurs"
class Links(HTMLParser):
 def __init__(self):
  super().__init__();self.links=[];self.href=None;self.label=""
 def handle_starttag(self,tag,attrs):
  if tag=="a":
   self.href=dict(attrs).get("href");self.label=""
 def handle_data(self,data):
  if self.href is not None:self.label+=data
 def handle_endtag(self,tag):
  if tag=="a" and self.href:
   self.links.append({"url":self.href,"text":" ".join(self.label.split())})
   self.href=None
def scan(url):
 req=Request(url,headers={"User-Agent":"Mozilla/5.0","Accept-Language":"fr-FR,fr;q=0.9"})
 ctx=ssl.create_default_context(cafile=certifi.where())
 with urlopen(req,timeout=15,context=ctx) as resp:
  html=resp.read(4000000).decode("utf-8","ignore")
 p=Links();p.feed(html)
 records=[]
 for a in p.links:
  absolute=urljoin(url,a["url"])
  label=a["text"]
  financial_terms=("résultats financiers","resultats financiers","états financiers","etats financiers","comptes consolidés","rapport financier","rapport annuel","financial results","financial statements")
  if absolute.startswith("https://") and absolute.lower().split("?")[0].endswith(".pdf") and any(term in label.casefold() or term in absolute.casefold() for term in financial_terms):
   records.append({"label":label[:160],"url":absolute})
 return list({x["url"]:x for x in records}.values())
def main():
 output={"checked_at":datetime.now(timezone.utc).isoformat(),"source":BASE,"reports":[],"errors":[],"status":"DISCOVERY_ONLY","policy":"Issuer PDF links are source candidates, not verified numerical EPS, PER or dividend observations."}
 for i in range(6):
  url=BASE+"?field_annee_value_1=2025&field_emetteur_target_id_verf=All&page="+str(i)
  try:
   for item in scan(url):
    if item["url"] not in {x["url"] for x in output["reports"]}:output["reports"].append(item)
  except Exception as e:output["errors"].append({"url":url,"error":type(e).__name__+":"+str(e)[:150]})
 # Discover linked financial disclosures on AMMC issuer-announcement pages.
 announcement="https://www.ammc.ma/fr/actualites/lammc-met-sur-son-site-internet-les-publications-realisees-par-les-emetteurs-en-1042"
 try:
  for item in scan(announcement):
   if item["url"] not in {x["url"] for x in output["reports"]}:output["reports"].append(item)
 except Exception as e:output["errors"].append({"url":announcement,"error":type(e).__name__+":"+str(e)[:150]})
 output["report_count"]=len(output["reports"])
 output["link_policy"]="Only direct PDF document links; navigation and press-release pages are excluded"
 output["status"]="FOUND_LINKS" if output["reports"] else "NO_LINKS_VERIFIED"
 OUT.write_text(json.dumps(output,ensure_ascii=False,indent=2)+"\n",encoding="utf-8")
 print(json.dumps({"status":output["status"],"report_count":output["report_count"],"errors":len(output["errors"])},ensure_ascii=False))
if __name__=="__main__":main()
