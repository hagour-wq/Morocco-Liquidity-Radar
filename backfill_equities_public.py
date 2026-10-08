"""Backfill selected Casablanca shares from publicly displayed historical price tables.
Only explicitly mapped issuer pages and parseable dated price/volume records qualify.
Provider can block automated requests: failures recorded, no invented observations.
"""
import json,re
from pathlib import Path
from datetime import datetime,date,timezone
from urllib.request import Request,urlopen
from html.parser import HTMLParser
HIST=Path("data/equity_history.json")
OUT=Path("data/equity_public_history_diagnostic.json")
SOURCES={"ATW":{"name":"Attijariwafa bank","url":"https://fr.investing.com/equities/attijariwafa-bk-historical-data"}}
class TableReader(HTMLParser):
 def __init__(self):
  super().__init__();self.depth=0;self.rows=[];self.row=None;self.cell=None;self.capture=0
 def handle_starttag(self,tag,attrs):
  if tag=="tr":self.row=[] if self.row is None else self.row
  if tag in ("td","th") and self.row is not None:self.cell=""
 def handle_data(self,data):
  if self.cell is not None:self.cell+=data
 def handle_endtag(self,tag):
  if tag in ("td","th") and self.cell is not None and self.row is not None:
   self.row.append(self.cell.strip());self.cell=None
  if tag=="tr" and self.row is not None:
   if len(self.row)>=6:self.rows.append(self.row)
   self.row=None
def number(s):
 s=re.sub(r"[^0-9,.-]","",s.replace("\u202f","").replace(" ",""))
 if "," in s and "." in s:s=s.replace(".","").replace(",",".")
 elif "," in s:s=s.replace(",",".")
 return float(s)
def volume(s):
 s=s.replace(" ","").replace("\u202f","").upper()
 factor=1000 if s.endswith("K") else 1000000 if s.endswith("M") else 1
 return number(s[:-1] if factor>1 else s)*factor
def parse_date(s):
 s=s.strip()
 for fmt in ("%d/%m/%Y","%Y-%m-%d"):
  try:return datetime.strptime(s,fmt).date().isoformat()
  except ValueError:pass
 return None
def parse_table(html):
 p=TableReader();p.feed(html)
 rows={}
 for cells in p.rows:
  dt=parse_date(cells[0])
  if not dt:continue
  try:
   close=number(cells[1]);vol=volume(cells[5])
   if close>0 and vol>=0 and dt<=date.today().isoformat():rows[dt]={"date":dt,"close":close,"volume":vol}
  except (ValueError,TypeError):continue
 return sorted(rows.values(),key=lambda x:x["date"])
def main():
 old=json.loads(HIST.read_text()) if HIST.exists() else {"companies":[]}
 items={x["ticker"]:x for x in old.get("companies",[])}
 diag={"checked_at":datetime.now(timezone.utc).isoformat(),"provider":"Investing.com displayed history","accepted":[],"rejected":[]}
 for ticker,src in SOURCES.items():
  try:
   req=Request(src["url"],headers={"User-Agent":"Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 Chrome/126.0.0.0 Safari/537.36","Accept-Language":"fr-FR,fr;q=0.9","Accept":"text/html"})
   with urlopen(req,timeout=15) as response:html=response.read(5000000).decode("utf-8","replace")
   if not ("Casablanca" in html and ("MAD" in html or "Dirham" in html)):raise ValueError("market_currency_not_confirmed")
   rows=parse_table(html)
   if len(rows)<25:raise ValueError("only_"+str(len(rows))+"_valid_sessions")
   record=items.get(ticker,{"ticker":ticker,"name":src["name"],"rows":[]})
   bydate={q["date"]:q for q in record.get("rows",[]) if q.get("date")}
   for x in rows:
    if x["date"] not in bydate:bydate[x["date"]]=dict(x,source="Investing.com",source_url=src["url"],quality="secondary_displayed_daily_history")
   record["rows"]=sorted(bydate.values(),key=lambda x:x["date"])
   items[ticker]=record
   diag["accepted"].append({"ticker":ticker,"sessions":len(rows),"earliest":rows[0]["date"],"latest":rows[-1]["date"]})
  except Exception as e:diag["rejected"].append({"ticker":ticker,"error":type(e).__name__+":"+str(e)[:160]})
 diag["status"]="SUCCESS" if diag["accepted"] else "UNAVAILABLE"
 OUT.write_text(json.dumps(diag,ensure_ascii=False,indent=2)+"\n")
 if diag["accepted"]:HIST.write_text(json.dumps({"schema_version":1,"updated_at":diag["checked_at"],"companies":list(items.values())},ensure_ascii=False,indent=2)+"\n")
 print(json.dumps(diag,ensure_ascii=False))
if __name__=="__main__":main()
