#!/usr/bin/env python3
"""Merge public event observations produced this run with latest remote repository
after fetch/reset. Preserve earliest first_seen and never retroactively backdate."""
import json,sys
from pathlib import Path
p=Path("/tmp/byma-state")
dst=Path("radar_byma/state")
dst.mkdir(parents=True,exist_ok=True)
def read(path,default):
    try:return json.loads(path.read_text(encoding="utf-8"))
    except (OSError,ValueError):return default
prior=read(dst/"event_history.json",{"version":1,"events":{}})
new=read(p/"event_history.json",{"version":1,"events":{}})
if new.get("version")!=1 or prior.get("version")!=1:raise ValueError("Version conflict")
merged=dict(prior["events"])
for key,v in new["events"].items():
    old=merged.get(key)
    if old is None:
        merged[key]=v
    else:
        dates=[v.get("first_seen"),old.get("first_seen")]
        dates=[d for d in dates if isinstance(d,str) and d]
        if dates:
            original=min(dates)
            old["first_seen"]=original
            pub=old.get("published")
            old["asof_usable"]=max(pub,original) if isinstance(pub,str) and pub else original
            merged[key]=old
if len(merged)>3500:
    keys=sorted(merged,key=lambda k:merged[k].get("first_seen",""))
    for k in keys[:len(merged)-3500]:del merged[k]
(dst/"event_history.json").write_text(json.dumps({"version":1,"events":merged},ensure_ascii=False,indent=2),encoding="utf-8")
for src,name in [("events_latest.json","events_latest.json"),("events_study_latest.json","events_study_latest.json")]:
    raw=read(p/src,None)
    if raw is None:raise ValueError("Missing "+src)
    (dst/name).write_text(json.dumps(raw,ensure_ascii=False,indent=2),encoding="utf-8")
print("MERGED_EVENT_HISTORY",json.dumps({"old":len(prior["events"]),"new":len(new["events"]),"merged":len(merged)}))
