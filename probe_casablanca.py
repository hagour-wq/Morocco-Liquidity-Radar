"""Diagnostic one-shot de l'accès au site de la Bourse de Casablanca depuis GitHub Actions.
Écrit diag/casablanca_probe.json et diag/home.html ; ne modifie aucune donnée de production."""
import json, re, ssl, subprocess, certifi
from pathlib import Path
from urllib.request import Request, urlopen
from urllib.parse import urljoin
from datetime import datetime, timezone

OUT=Path("diag"); OUT.mkdir(exist_ok=True)
UA="Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/128.0 Safari/537.36"
HOME="https://www.casablanca-bourse.com/fr"
report={"run_at":datetime.now(timezone.utc).isoformat(),"attempts":[]}

def get(url,ctx,accept="text/html,*/*"):
    req=Request(url,headers={"User-Agent":UA,"Accept":accept,"Accept-Language":"fr-FR,fr;q=0.9"})
    with urlopen(req,timeout=30,context=ctx) as r:
        return r.status,dict(r.headers),r.read()

contexts={"default":ssl.create_default_context(),"certifi":ssl.create_default_context(cafile=certifi.where())}
body=None
for name,ctx in contexts.items():
    for url in ("https://www.casablanca-bourse.com/","https://www.casablanca-bourse.com/fr"):
        a={"url":url,"ctx":name}
        try:
            st,h,b=get(url,ctx); a.update(status=st,bytes=len(b),content_type=h.get("Content-Type"),server=h.get("Server"))
            if body is None: body=b.decode("utf-8","ignore"); report["home_url_ok"]=url
        except Exception as e: a["error"]=f"{type(e).__name__}: {e}"
        report["attempts"].append(a)

try:
    r=subprocess.run("echo | openssl s_client -connect www.casablanca-bourse.com:443 -servername www.casablanca-bourse.com -showcerts 2>&1 | grep -E 's:|i:|Verify return|verify error' | head -20",shell=True,capture_output=True,text=True,timeout=40)
    report["openssl_chain"]=r.stdout.splitlines()
except Exception as e: report["openssl_chain"]=str(e)
try:
    r=subprocess.run(["curl","-sS","-o","/dev/null","-w","%{http_code} %{ssl_verify_result}","-A",UA,HOME],capture_output=True,text=True,timeout=40)
    report["curl"]=(r.stdout+" "+r.stderr).strip()
except Exception as e: report["curl"]=str(e)

# Récupération du certificat intermédiaire manquant via l'AIA du certificat feuille.
try:
    sh=lambda c:subprocess.run(c,shell=True,capture_output=True,text=True,timeout=60)
    sh("echo | openssl s_client -connect www.casablanca-bourse.com:443 -servername www.casablanca-bourse.com 2>/dev/null | openssl x509 -outform PEM > diag/leaf.pem")
    aia=sh("openssl x509 -in diag/leaf.pem -noout -ext authorityInfoAccess").stdout
    report["leaf_aia"]=aia.strip().splitlines()
    url=re.search(r"CA Issuers - URI:(\S+)",aia).group(1)
    sh(f"curl -sS -o diag/intermediate.der {url} && openssl x509 -inform DER -in diag/intermediate.der -out diag/intermediate.pem")
    report["intermediate_url"]=url
    report["intermediate_subject"]=sh("openssl x509 -in diag/intermediate.pem -noout -subject -issuer -enddate -fingerprint -sha256").stdout.strip().splitlines()
    report["chain_verify"]=sh(f"openssl verify -CAfile {certifi.where()} -untrusted diag/intermediate.pem diag/leaf.pem").stdout.strip()
    ctx=ssl.create_default_context(cafile=certifi.where()); ctx.load_verify_locations(cafile="diag/intermediate.pem")
    contexts["certifi+intermediate"]=ctx
    for url in ("https://www.casablanca-bourse.com/","https://www.casablanca-bourse.com/fr"):
        a={"url":url,"ctx":"certifi+intermediate"}
        try:
            st,h,bb=get(url,ctx); a.update(status=st,bytes=len(bb),content_type=h.get("Content-Type"),server=h.get("Server"))
            if body is None: body=bb.decode("utf-8","ignore"); report["home_url_ok"]=url
        except Exception as e: a["error"]=f"{type(e).__name__}: {e}"
        report["attempts"].append(a)
except Exception as e: report["intermediate_error"]=f"{type(e).__name__}: {e}"

if body:
    (OUT/"home.html").write_text(body,encoding="utf-8")
    report["has_next_data"]="__NEXT_DATA__" in body
    report["masi_mentions"]=len(re.findall("MASI",body))
    report["api_strings_home"]=sorted(set(re.findall(r"[\"'](/api/[^\"'\s]{3,200}|https://[^\"'\s]*api[^\"'\s]{0,200})[\"']",body)))[:80]
    scripts=re.findall(r"<script[^>]+src=[\"']([^\"']+)",body)
    report["scripts"]=scripts[:60]
    found=set()
    ctx=contexts.get("certifi+intermediate",contexts["certifi"])
    for s in scripts[:60]:
        try:
            _,_,js=get(urljoin("https://www.casablanca-bourse.com/",s),ctx,"*/*")
            js=js.decode("utf-8","ignore")
            for m in re.findall(r"[\"'`]((?:/api|api/)[A-Za-z0-9_\-/{}.?=&$]{3,200})[\"'`]",js): found.add(m)
            for m in re.findall(r"[\"'`](https?://[A-Za-z0-9.\-]*casablanca-bourse[^\"'`\s]{0,200})[\"'`]",js): found.add(m)
        except Exception as e: found.add(f"ERR {s}: {type(e).__name__}")
    report["api_strings_js"]=sorted(found)[:200]
    m=re.search(r'<script id="__NEXT_DATA__"[^>]*>(.*?)</script>',body,re.S)
    if m: (OUT/"next_data.json").write_text(m.group(1),encoding="utf-8")

(OUT/"casablanca_probe.json").write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding="utf-8")
print(json.dumps({k:v for k,v in report.items() if k not in ("api_strings_js","scripts")},ensure_ascii=False,indent=1))

# Pages secondaires (étape 2)
pages={"actions":"https://www.casablanca-bourse.com/live-market/actions","indices":"https://www.casablanca-bourse.com/live-market/indices",
       "volume":"https://www.casablanca-bourse.com/market-data/volume","capitalisation":"https://www.casablanca-bourse.com/market-data/capitalisation",
       "fiche_atw":"https://www.casablanca-bourse.com/fr/live-market/instruments/ATW","historique":"https://www.casablanca-bourse.com/fr/historique-des-cours"}
report["pages"]={}
ctx=contexts.get("certifi+intermediate",contexts["certifi"])
for k,u in pages.items():
    try:
        st,h,b=get(u,ctx); t=b.decode("utf-8","ignore"); (OUT/f"page_{k}.html").write_text(t,encoding="utf-8")
        report["pages"][k]={"status":st,"bytes":len(b),"tables":t.count("<table"),"rows":t.count("<tr"),
           "api":sorted(set(re.findall(r"[\"'](/api/[^\"'\s]{3,200})[\"']",t)))[:40],
           "links":sorted(set(re.findall(r'href="([^"]*(?:histori|instrument|telecharg|download|\.xlsx|\.csv|\.pdf)[^"]*)"',t,re.I)))[:40]}
    except Exception as e: report["pages"][k]={"error":f"{type(e).__name__}: {e}"}
(OUT/"casablanca_probe.json").write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding="utf-8")
