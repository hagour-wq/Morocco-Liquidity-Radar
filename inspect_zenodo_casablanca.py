"""Inspect CC-BY-4.0 academic Casablanca stock-return dataset on Zenodo.
Never convert returns into official closing prices or invent volume.
Record archives' listing, shapes, dates, and parseable columns.
"""
import json,io,zipfile,csv,re
from datetime import datetime,timezone
from pathlib import Path
from urllib.request import Request,urlopen
OUT=Path("data/zenodo_casablanca_inspection.json")
RECORD="https://zenodo.org/api/records/21879963"
def get(url,limit=12000000):
 req=Request(url,headers={"User-Agent":"EquityBourseResearch/1.0","Accept":"application/json,application/zip,*/*"})
 with urlopen(req,timeout=35) as response:
  buf=response.read(limit+1)
 if len(buf)>limit:raise ValueError("File exceeds size limit")
 return buf
def main():
 data={"checked_at":datetime.now(timezone.utc).isoformat(),"record_url":"https://zenodo.org/records/21879963","status":"UNVERIFIED","metadata":{},"archive":[],"errors":[],"source_type":"academic_daily_log_returns","license":"CC BY 4.0"}
 try:
  record=json.loads(get(RECORD))
  files=record.get("files",[])
  data["metadata"]={"title":record.get("metadata",{}).get("title"),"published":record.get("metadata",{}).get("publication_date"),"files":[{"key":x.get("key"),"size":x.get("size"),"links":x.get("links",{})} for x in files]}
  z=next((x for x in files if x.get("key","").lower().endswith(".zip")),None)
  if z is None:raise ValueError("No zip in Zenodo record")
  url=(z.get("links") or {}).get("self") or (z.get("links") or {}).get("content")
  if not url:raise ValueError("No downloadable archive link")
  arc=zipfile.ZipFile(io.BytesIO(get(url)))
  for entry in arc.infolist():
   if entry.is_dir():continue
   item={"name":entry.filename,"size":entry.file_size,"ext":entry.filename.rsplit(".",1)[-1].lower()}
   if item["ext"] in ("csv","txt","tsv") and entry.file_size<3000000:
    raw=arc.read(entry).decode("utf-8-sig","replace")
    item["preview"]=raw.splitlines()[:5]
   data["archive"].append(item)
  data["status"]="ARCHIVE_INSPECTED"
 except Exception as e:data["status"]="FAILED";data["errors"].append(type(e).__name__+": "+str(e)[:400])
 OUT.write_text(json.dumps(data,ensure_ascii=False,indent=2)+"\n",encoding="utf-8")
 print(json.dumps({"status":data["status"],"files":len(data["archive"]),"errors":data["errors"]},ensure_ascii=False))
if __name__=="__main__":main()
