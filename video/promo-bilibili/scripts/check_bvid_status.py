#!/usr/bin/env python3
"""Check a Bilibili archive's audit/transcode state and HDR ladder.

Prints no cookie values. Uses the target web-cookie credential only.
"""
from __future__ import annotations
import argparse, json, time, urllib.parse, urllib.request
from pathlib import Path

UA = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36"

def cookie_header(c):
    return "; ".join([
        f"SESSDATA={c['sessdata']}", f"bili_jct={c['bili_jct']}",
        f"buvid3={c['buvid3']}", f"DedeUserID={c['dedeuserid']}",
    ])

def get(url, cookie):
    req = urllib.request.Request(url, headers={
        "User-Agent": UA, "Referer": "https://www.bilibili.com/", "Cookie": cookie,
    })
    with urllib.request.urlopen(req, timeout=30) as resp:
        return json.loads(resp.read().decode())

def archive(c, bvid):
    q = urllib.parse.urlencode({"status": "pubed,is_pubing,not_pubed", "pn": 1, "ps": 50})
    d = get("https://member.bilibili.com/x/web/archives?" + q, cookie_header(c))
    if d.get("code") != 0:
        return {"error": f"code={d.get('code')} msg={d.get('message')}"}
    rows = (d.get("data") or {}).get("arc_audits") or []
    for item in rows:
        a = item.get("Archive") or item
        if a.get("bvid") == bvid:
            return {k: a.get(k) for k in ("bvid","aid","title","state","state_desc","duration","tid","cover","ctime","pubtime") if k in a}
    return {"error": "bvid not found in archive list", "count": len(rows)}

def view(bvid):
    d = get("https://api.bilibili.com/x/web-interface/view?bvid=" + bvid, "")
    if d.get("code") != 0:
        return {"error": f"code={d.get('code')} msg={d.get('message')}"}
    x = d.get("data") or {}
    return {k: x.get(k) for k in ("bvid","aid","cid","title","state","state_desc","duration","pubdate","owner","pages") if k in x}

def playurl(bvid, cid, c):
    q = urllib.parse.urlencode({"bvid": bvid, "cid": cid, "qn": 127, "fnval": 4048, "fnver": 0, "fourk": 1})
    d = get("https://api.bilibili.com/x/player/playurl?" + q, cookie_header(c))
    if d.get("code") != 0:
        return {"error": f"code={d.get('code')} msg={d.get('message')}"}
    x = d.get("data") or {}
    dash = x.get("dash") or {}
    vids = dash.get("video") or []
    return {
        "quality": x.get("quality"),
        "format": x.get("format"),
        "accept_quality": x.get("accept_quality"),
        "accept_description": x.get("accept_description"),
        "support_formats": [
            {"quality": s.get("quality"), "desc": s.get("new_description"), "codecs": s.get("codecs")}
            for s in (x.get("support_formats") or [])
        ],
        "hdr_quality_125": 125 in (x.get("accept_quality") or []),
        "video_streams": [
            {"id": v.get("id"), "codecid": v.get("codecid"), "codecs": v.get("codecs"),
             "width": v.get("width"), "height": v.get("height"),
             "fps": v.get("frameRate"), "bandwidth": v.get("bandwidth")}
            for v in sorted(vids, key=lambda z: z.get("id") or 0, reverse=True)
        ],
    }

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--bvid", required=True)
    ap.add_argument("--credential", required=True, type=Path)
    ap.add_argument("--out", type=Path, required=True)
    ap.add_argument("--attempts", type=int, default=8)
    ap.add_argument("--interval", type=float, default=20)
    args = ap.parse_args()
    c = json.loads(args.credential.read_text(encoding="utf-8"))
    result = {"checked_at": None, "bvid": args.bvid}
    for i in range(args.attempts):
        result["checked_at"] = time.strftime("%Y-%m-%dT%H:%M:%S%z")
        result["archive"] = archive(c, args.bvid)
        result["view"] = view(args.bvid)
        cid = (result["view"] or {}).get("cid")
        if cid:
            result["playurl"] = playurl(args.bvid, cid, c)
        print(json.dumps(result, ensure_ascii=False, indent=2), flush=True)
        state = (result.get("archive") or {}).get("state_desc")
        hdr = (result.get("playurl") or {}).get("hdr_quality_125")
        if state and state != "转码中" and (cid or i == args.attempts - 1):
            break
        if hdr:
            break
        if i + 1 < args.attempts:
            time.sleep(args.interval)
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print("wrote", args.out, flush=True)

if __name__ == "__main__":
    main()
