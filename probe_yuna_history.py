"""Probe Yuna's historical Casablanca sessions without guessing undocumented endpoints.
Only capture explicitly dated Casablanca/MAD records. Do not mix intraday and close.
"""
import json,re,ssl,certifi
from datetime import datetime,timezone
from html.parser import HTMLParser
from urllib.request import Request,urlopen
from pathlib import Path
OUT=Path("data/yuna_history_probe.json")
URL="https://www.yuna.ma/bourse/en-direct"
class Links(HTMLParser):
 def __init__(self):super().__init__();self.links=[];self.current=None
 def handle_starttag(self,tag,attrs):
  if tag=="a":self.current=dict(attrs).get("href")
  if self.current and tag=="a":self.links.append(self.current)
 def handle_endtag(self,tag):
  if tag=="a":self.current=None
def main():
 d={"checked_at":datetime.now(timezone.utc).isoformat(),"url":URL,"status":"UNVERIFIED","access":False,"source_policy":"No undocumented CSV endpoints and no fabricated historical bars"}
 try:
  req=Request(URL,headers={"User-Agent":"Mozilla/5.0","Accept-Language":"fr-FR,fr;q=0.9","Accept":"text/html,application/json"})
  with urlopen(req,timeout=14,context=ssl.create_default_context(cafile=certifi.where())) as response:
   raw=response.read(3000000)
   d["http_status"]=response.status
   d["content_type"]=response.headers.get("Content-Type")
  html=raw.decode("utf-8","replace")
  d["access"]=True
  d["bytes"]=len(raw)
  d["has_casablanca"]=bool(re.search(r"Casablanca|Bourse de Casablanca",html,re.I))
  d["has_isin"]=bool(re.search(r"MA[0-9]{10}",html))
  d["has_mad"]=bool(re.search(r"\bMAD\b",html))
  d["historical_ui"]=bool(re.search(r"s[ée]ance pass[ée]e|Exporter en CSV|Choisissez une date",html,re.I))
  dates=re.findall(r"20[0-9]{2}-[01][0-9]-[0-3][0-9]",html)
  d["dates_sample"]=list(dict.fromkeys(dates))[:20]
  p=Links();p.feed(html)
  d["relevant_links"]=list(dict.fromkeys(x for x in p.links if any(k in x.lower() for k in ("csv","histor","bourse","api","export"))))[:40]
  d["scripts"]=list(dict.fromkeys(re.findall(r'<script[^>]*src=["\']([^"\']+)',html,re.I)))[:30]
  d["status"]="REACHABLE_HTML_DISCOVERY" if d["has_casablanca"] and d["has_isin"] else "HTML_UNVERIFIED"
 except Exception as e:d["status"]="NETWORK_FAILED";d["error"]=type(e).__name__+": "+str(e)[:230]
 OUT.write_text(json.dumps(d,ensure_ascii=False,indent=2)+"\n",encoding="utf-8")
 print(json.dumps(d,ensure_ascii=False))
if __name__=="__main__":main()
