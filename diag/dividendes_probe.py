"""Diagnostic : structure de /emetteurs/calendrier-financier (données des dividendes)."""
import json, re, sys
sys.path.insert(0, ".")
import casablanca_source as cb
h = cb.get_html("/emetteurs/calendrier-financier")
open("data/diag_calendrier.html", "w").write(h)
ds = cb.drupal_settings(h)
json.dump(ds.get("boursenova"), open("data/diag_calendrier_settings.json", "w"), ensure_ascii=False, indent=1)
print(len(h), list((ds.get("boursenova") or {}).keys()))
