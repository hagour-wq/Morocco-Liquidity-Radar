"""Official liquidity collector skeleton.
Never fabricates values: only writes a component after a source-specific parser
has produced a numeric value, a comparison basis and a reference date.
"""
import json
import re
import time
from pathlib import Path
from datetime import datetime, timezone
from urllib.request import Request, urlopen
from urllib.error import URLError, HTTPError
from io import BytesIO

P=Path("data/liquidity_inputs.json")

def load():
    return json.loads(P.read_text(encoding="utf-8"))

def save(d):
    d["collector_checked_at"]=datetime.now(timezone.utc).isoformat()
    P.write_text(json.dumps(d,ensure_ascii=False,indent=2)+"\n",encoding="utf-8")

def validate_component(x):
    if not x.get("verified"): return True
    return isinstance(x.get("score"),(int,float)) and bool(x.get("reference_date")) and bool(x.get("source"))

def fetch_text(url):
    req=Request(url,headers={"User-Agent":"Mozilla/5.0 EquityBourse/1.0"})
    with urlopen(req,timeout=25) as r:
        return r.read().decode("utf-8","ignore")


def probe(url):
    try:
        req=Request(url,headers={"User-Agent":"Mozilla/5.0 EquityBourse/1.0"})
        with urlopen(req,timeout=20) as r:
            head=r.read(8)
            return {"ok":True,"status":getattr(r,"status",200),"content_type":r.headers.get("Content-Type"),"magic":head.hex()}
    except Exception as e:
        return {"ok":False,"error":type(e).__name__}

def discover_links(page_url, patterns):
    """Return candidate official files/endpoints without trusting their contents."""
    try: html=fetch_text(page_url)
    except Exception as e:
        print("Discovery failed",page_url,type(e).__name__); return []
    links=re.findall(r'''href=["']([^"']+)["']''',html,re.I)
    out=[]
    for href in links:
        low=href.lower()
        if any(p in low for p in patterns):
            if href.startswith("/"):
                from urllib.parse import urljoin
                href=urljoin(page_url,href)
            if href.startswith("http"): out.append(href)
    return list(dict.fromkeys(out))


def download_with_retry(url, attempts=4):
    agents=["Mozilla/5.0","Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/154 Safari/537.36","EquityBourse/1.0"]
    last=None
    for i in range(attempts):
        try:
            req=Request(url,headers={"User-Agent":agents[i%len(agents)],"Accept":"*/*","Connection":"close"})
            with urlopen(req,timeout=35) as r: return r.read()
        except Exception as e:
            last=e
            if i<attempts-1: time.sleep(2*(i+1))
    raise last

def inspect_excel(url):
    """Download an official AMMC workbook and expose schema only; no scoring."""
    try:
        raw=download_with_retry(url)
        info={"url":url,"bytes":len(raw)}
        if url.lower().endswith(".xlsx"):
            import openpyxl
            wb=openpyxl.load_workbook(BytesIO(raw),read_only=True,data_only=True)
            info["sheets"]=wb.sheetnames
            samples={}
            for ws in wb.worksheets[:5]:
                rows=[]
                first_nonempty=None
                for idx,row in enumerate(ws.iter_rows(min_row=1,max_row=250,values_only=True),start=1):
                    vals=[str(v)[:120] if v is not None else None for v in row[:30]]
                    if any(v is not None for v in vals):
                        if first_nonempty is None: first_nonempty=idx
                        rows.append({"row":idx,"values":vals})
                        if len(rows)>=30: break
                samples[ws.title]={"first_nonempty_row":first_nonempty,"rows":rows}
            info["samples"]=samples
        else:
            import xlrd
            book=xlrd.open_workbook(file_contents=raw)
            info["sheets"]=book.sheet_names()
            samples={}
            for sh in book.sheets()[:5]:
                rows=[]
                first_nonempty=None
                for i in range(min(sh.nrows,250)):
                    vals=[str(sh.cell_value(i,j))[:120] for j in range(min(sh.ncols,30))]
                    if any(v.strip() for v in vals):
                        if first_nonempty is None: first_nonempty=i+1
                        rows.append({"row":i+1,"values":vals})
                        if len(rows)>=30: break
                samples[sh.name]={"first_nonempty_row":first_nonempty,"rows":rows}
            info["samples"]=samples
        info["status"]="SCHEMA_READ"
        return info
    except Exception as e:
        return {"url":url,"status":"ERROR","error":type(e).__name__}

def main():
    d=load()
    # Discovery layer: official pages only. Parsing/scoring remains gated.
    candidates={
      "ammc":discover_links("https://www.ammc.ma/fr/donnees-statistiques",["opcvm",".xlsx",".xls",".csv"]),
      "bam":discover_links("https://www.bkam.ma/Marches/Principaux-indicateurs/Marche-monetaire/Marche-monetaire",[".xlsx",".xls",".csv","marche","monetaire"])
    }
    d["discovery"]={k:{"count":len(v),"candidates":v[:20],"status":"FOUND" if v else "NO_CANDIDATE"} for k,v in candidates.items()}
    discovered_files=[u for u in candidates.get("ammc",[]) if u.lower().split("?")[0].endswith((".xls",".xlsx"))]
    cached_files=d.get("official_file_cache",{}).get("ammc_opcvm",[])
    ammc_files=list(dict.fromkeys(discovered_files+cached_files))
    d["ammc_workbook_inspection"]=[inspect_excel(u) for u in ammc_files[:2]]
    d["ammc_file_pool"]={"discovered":len(discovered_files),"cached":len(cached_files),"usable_candidates":len(ammc_files)}
    known=d.get("data_endpoints",{})
    d["endpoint_probes"]={name:probe(url) for name,url in known.items() if isinstance(url,str) and url.startswith("http")}
    d["collector_status"]={
      "ammc":"schema_inspection_active_no_scoring_until_flow_fields_validated",
      "bam":"discovery_only_until_parser_validates_schema",
      "safety":"preserve_last_verified_value_on_failure"
    }
    # Safety gate: until a parser validates comparable official observations,
    # existing verified values are preserved and unavailable components remain null.
    for name,x in d.get("components",{}).items():
        if not validate_component(x):
            raise ValueError(f"Invalid verified liquidity component: {name}")
    save(d)
    active=[k for k,v in d["components"].items() if v.get("verified")]
    print("Verified liquidity components:", ", ".join(active) or "none")

if __name__=="__main__": main()
