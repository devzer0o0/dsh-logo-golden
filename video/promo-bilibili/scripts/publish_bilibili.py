#!/usr/bin/env python3
"""Preflight and one-shot Bilibili upload for the dsh-logo-golden promo.

This script never prints cookie values. It reads the bili-duty credential file,
uses bilibili-api-python's web-cookie VideoUploader, and refuses to submit if an
archive with the exact same title already exists.

Usage:
  .venv/bin/python scripts/publish_bilibili.py --preflight
  .venv/bin/python scripts/publish_bilibili.py --submit
  .venv/bin/python scripts/publish_bilibili.py --status --bvid BV...
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import re
import subprocess
import sys
import time
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

from PIL import Image

BASE = Path(__file__).resolve().parents[1]
DEFAULT_META = BASE / "publish" / "metadata.json"
DEFAULT_CRED = Path.home() / ".dsh" / "bili-duty" / "bili_credential.json"
DEFAULT_PROXY = ""


def log(msg: str) -> None:
    print(msg, flush=True)


def load_json(path: Path) -> dict:
    with path.open("r", encoding="utf-8") as f:
        return json.load(f)


def write_json(path: Path, obj: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(obj, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def ffprobe(path: Path) -> dict:
    out = subprocess.check_output(
        [
            "ffprobe",
            "-v",
            "error",
            "-show_format",
            "-show_streams",
            "-of",
            "json",
            str(path),
        ]
    )
    return json.loads(out.decode("utf-8"))


def parse_srt(path: Path) -> list[tuple[float, float, str]]:
    text = path.read_text(encoding="utf-8-sig").replace("\r\n", "\n")
    blocks = [b.strip() for b in re.split(r"\n\s*\n", text) if b.strip()]
    cues: list[tuple[float, float, str]] = []
    for block in blocks:
        lines = block.split("\n")
        if len(lines) < 3:
            raise ValueError(f"bad SRT block: {block[:80]!r}")
        m = re.match(
            r"(\d{2}):(\d{2}):(\d{2}),(\d{3})\s*-->\s*(\d{2}):(\d{2}):(\d{2}),(\d{3})",
            lines[1].strip(),
        )
        if not m:
            raise ValueError(f"bad SRT time line: {lines[1]!r}")
        g = [int(x) for x in m.groups()]
        start = g[0] * 3600 + g[1] * 60 + g[2] + g[3] / 1000
        end = g[4] * 3600 + g[5] * 60 + g[6] + g[7] / 1000
        body = "\n".join(lines[2:]).strip()
        cues.append((start, end, body))
    return cues


def local_checks(meta_path: Path) -> tuple[dict, dict, list[tuple[float, float, str]]]:
    meta = load_json(meta_path)
    video = (BASE / meta["video"]).resolve()
    cover = (BASE / meta["cover"]).resolve()
    srt = (BASE / meta["srt"]).resolve()

    for p in (video, cover, srt):
        if not p.is_file():
            raise FileNotFoundError(p)

    log(f"video: {video} ({video.stat().st_size:,} bytes)")
    log(f"cover: {cover} ({cover.stat().st_size:,} bytes)")

    probe = ffprobe(video)
    fmt = probe.get("format", {})
    duration = float(fmt.get("duration", 0))
    streams = probe.get("streams", [])
    v = next((s for s in streams if s.get("codec_type") == "video"), None)
    a = next((s for s in streams if s.get("codec_type") == "audio"), None)
    if not v or not a:
        raise ValueError("video must contain one video and one audio stream")
    width, height = int(v["width"]), int(v["height"])
    fps = v.get("r_frame_rate", "")
    pix_fmt = v.get("pix_fmt", "")
    log(
        f"streams: {v.get('codec_name')} {width}x{height} {fps} {pix_fmt}; "
        f"audio {a.get('codec_name')} {a.get('sample_rate')}Hz {a.get('channels')}ch; "
        f"duration {duration:.3f}s"
    )
    if (width, height) != (1920, 1080):
        raise ValueError("expected 1920x1080")
    if fps != "30/1":
        raise ValueError(f"expected 30 fps, got {fps}")
    codec = v.get("codec_name")
    is_sdr = codec == "h264" and pix_fmt == "yuv420p"
    is_hdr = (
        codec == "hevc"
        and pix_fmt == "yuv420p10le"
        and v.get("color_transfer") == "smpte2084"
        and v.get("color_primaries") == "bt2020"
    )
    if not (is_sdr or is_hdr):
        raise ValueError("expected h264/yuv420p SDR or HEVC Main10 PQ/BT.2020 HDR")
    if a.get("codec_name") != "aac" or int(a.get("sample_rate", 0)) != 48000:
        raise ValueError("expected AAC 48 kHz audio")
    if not (66.8 <= duration <= 67.2):
        raise ValueError(f"expected ~67.0 s, got {duration:.3f}")

    with Image.open(cover) as im:
        cw, ch = im.size
    log(f"cover image: {cw}x{ch}, ratio {cw / ch:.4f}")
    if not (1.59 <= cw / ch <= 1.61):
        raise ValueError("cover should be 16:10")
    if cw < 1000:
        raise ValueError("cover width should be at least 1000 px")

    cues = parse_srt(srt)
    log(f"srt: {len(cues)} cues, {cues[0][0]:.3f}-{cues[-1][1]:.3f}s")
    if len(cues) != 11:
        raise ValueError("expected 11 SRT cues")
    if abs(cues[0][0]) > 0.001:
        raise ValueError("first cue should start at 0")
    for i, (start, end, body) in enumerate(cues):
        if end <= start:
            raise ValueError(f"cue {i + 1} has non-positive duration")
        if i and start < cues[i - 1][1] - 0.001:
            raise ValueError(f"cue {i + 1} overlaps previous")
        if len(body) > 200:
            raise ValueError(f"cue {i + 1} is too long")
    if cues[-1][1] > duration + 0.001:
        raise ValueError("last cue extends past video duration")

    title = meta["title"]
    desc = meta["desc"]
    tags = meta["tags"]
    log(f"metadata: title {len(title)} chars; desc {len(desc)} chars; tags {len(tags)}; tid {meta['tid']}")
    if len(title) > 80:
        raise ValueError("title > 80 chars")
    if len(desc) > 2000:
        raise ValueError("desc > 2000 chars")
    if not (1 <= len(tags) <= 10):
        raise ValueError("tags must be 1-10")
    if meta.get("copyright") != 1:
        raise ValueError("this promo must be marked original (copyright=1)")

    return meta, probe, cues


def cookie_header(cred: dict) -> str:
    return "; ".join(
        [
            f"SESSDATA={cred['sessdata']}",
            f"bili_jct={cred['bili_jct']}",
            f"DedeUserID={cred['dedeuserid']}",
            f"buvid3={cred['buvid3']}",
        ]
    )


def fetch_archives(
    cred: dict, status: str = "is_pubing,pubed,not_pubed", proxy: str | None = None
) -> list[dict]:
    """Read member.bilibili.com archive list. Returns flattened archive dicts."""
    headers = {
        "Cookie": cookie_header(cred),
        "User-Agent": (
            "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
            "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0 Safari/537.36"
        ),
        "Referer": "https://member.bilibili.com/",
    }
    archives: list[dict] = []
    for pn in range(1, 6):
        params = urllib.parse.urlencode(
            {"status": status, "pn": pn, "ps": 50, "interactive": 0, "coop": 0}
        )
        req = urllib.request.Request(
            "https://member.bilibili.com/x/web/archives?" + params, headers=headers
        )
        last_error = None
        for attempt in range(3):
            try:
                if proxy:
                    opener = urllib.request.build_opener(
                        urllib.request.ProxyHandler({"http": proxy, "https": proxy})
                    )
                    resp = opener.open(req, timeout=30)
                else:
                    resp = urllib.request.urlopen(req, timeout=30)
                with resp:
                    data = json.loads(resp.read().decode("utf-8"))
                last_error = None
                break
            except Exception as e:  # transient proxy/TLS failures are common here
                last_error = e
                time.sleep(1 + attempt)
        if last_error is not None:
            raise last_error
        if data.get("code") != 0:
            raise RuntimeError(f"archive list code={data.get('code')} msg={data.get('message')}")
        payload = data.get("data") or {}
        rows = payload.get("arc_audits") or payload.get("archives") or []
        if not rows:
            break
        for item in rows:
            if not isinstance(item, dict):
                continue
            archive = item.get("Archive") or item.get("archive") or item
            if isinstance(archive, dict):
                archives.append(archive)
        page = payload.get("page") or {}
        if len(archives) >= int(page.get("count", len(archives))):
            break
    return archives


def find_archive(archives: list[dict], *, bvid: str | None = None, title: str | None = None) -> dict | None:
    for a in archives:
        if bvid and a.get("bvid") == bvid:
            return a
        if title and a.get("title") == title:
            return a
    return None


def summarize_archive(a: dict) -> dict:
    keys = [
        "bvid",
        "aid",
        "title",
        "state",
        "state_desc",
        "reject_reason",
        "ctime",
        "pubtime",
        "duration",
        "copyright",
        "tid",
    ]
    out = {k: a.get(k) for k in keys if k in a}
    # Do not dump unrelated/private fields.
    return out


def fetch_nav(cred: dict, proxy: str | None = None) -> tuple[int, str]:
    """Return (mid, uname) for the current web cookie; never log cookie values."""
    req = urllib.request.Request(
        "https://api.bilibili.com/x/web-interface/nav",
        headers={
            "Cookie": cookie_header(cred),
            "User-Agent": (
                "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0 Safari/537.36"
            ),
            "Referer": "https://www.bilibili.com/",
        },
    )
    if proxy:
        opener = urllib.request.build_opener(
            urllib.request.ProxyHandler({"http": proxy, "https": proxy})
        )
        resp = opener.open(req, timeout=20)
    else:
        resp = urllib.request.urlopen(req, timeout=20)
    with resp:
        data = json.loads(resp.read().decode("utf-8"))
    if data.get("code") != 0:
        raise RuntimeError(f"nav check failed: code={data.get('code')}")
    payload = data.get("data") or {}
    return int(payload.get("mid") or 0), str(payload.get("uname") or "")


def fetch_buvid4(proxy: str | None) -> str:
    """Fetch buvid4 without triggering bilibili-api's activation retry loop."""
    req = urllib.request.Request(
        "https://api.bilibili.com/x/frontend/finger/spi",
        headers={
            "User-Agent": (
                "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0 Safari/537.36"
            ),
            "Referer": "https://www.bilibili.com/",
        },
    )
    if proxy:
        opener = urllib.request.build_opener(
            urllib.request.ProxyHandler({"http": proxy, "https": proxy})
        )
        resp = opener.open(req, timeout=20)
    else:
        resp = urllib.request.urlopen(req, timeout=20)
    with resp:
        data = json.loads(resp.read().decode("utf-8"))
    b4 = (data.get("data") or {}).get("b_4") or ""
    if not b4:
        raise RuntimeError(f"buvid4 fetch failed: code={data.get('code')}")
    return b4


async def prepare_meta(meta: dict, cred_path: Path, proxy: str | None):
    from bilibili_api import Credential, video_uploader
    from bilibili_api.utils import network

    network.select_client("aiohttp")
    if proxy:
        network.request_settings.set_proxy(proxy)
        log("network: proxy enabled (host omitted)")
    else:
        log("network: no explicit proxy")
    network.request_settings.set_trust_env(True)
    network.request_settings.set_timeout(60)

    c = load_json(cred_path)
    for key in ("sessdata", "bili_jct", "buvid3", "dedeuserid"):
        if not c.get(key):
            raise ValueError(f"credential missing {key}")

    buvid4 = c.get("buvid4") or fetch_buvid4(proxy)
    log("auth: buvid4 available")
    cred = Credential(
        sessdata=c["sessdata"],
        bili_jct=c["bili_jct"],
        buvid3=c["buvid3"],
        buvid4=buvid4,
        dedeuserid=c["dedeuserid"],
    )
    if not await cred.check_valid():
        raise RuntimeError("Bilibili credential check failed (not logged in)")

    cover_path = str((BASE / meta["cover"]).resolve())
    video_meta = video_uploader.VideoMeta(
        tid=int(meta["tid"]),
        title=meta["title"],
        desc=meta["desc"],
        cover=cover_path,
        tags=list(meta["tags"]),
        original=True,
        no_reprint=bool(meta.get("no_reprint", False)),
        neutral_mark=meta.get("neutral_mark"),
    )
    # bilibili-api 5.x does not set these when no topic is passed, but __dict__ uses them.
    video_meta.mission_id = None
    video_meta.topic_id = 0
    video_meta.delay_time = None
    video_meta.source = None
    payload = video_meta.__dict__()
    log(
        "meta payload: keys="
        + ",".join(sorted(payload.keys()))
        + f"; copyright={payload.get('copyright')}; tid={payload.get('tid')}"
    )
    if not video_meta._check_tid():
        raise ValueError(f"tid {meta['tid']} not in uploader tid list")
    # The member tag-check endpoint currently returns -400 for every tag even
    # with a valid web session, so it is not a reliable preflight signal.
    # Tags are still validated server-side by the final submit call.
    log("auth: credential valid; tid accepted; tag check endpoint skipped (unreliable -400)")
    return cred, video_meta


async def submit(meta: dict, cred, video_meta, video_path: Path, cover_path: Path) -> dict:
    from bilibili_api import video_uploader
    from bilibili_api.utils import network
    from bilibili_api.utils.network import BiliAPIResponse
    import aiohttp

    # The local HTTP proxy is required for api/member endpoints but stalls on
    # multi-megabyte upos PUTs. Route upos through a direct session; keep the
    # proxy for everything else.
    client = network.get_client()
    original_request = client.request
    direct_session = aiohttp.ClientSession(
        trust_env=False, connector=aiohttp.TCPConnector()
    )

    async def routed_request(
        method="",
        url="",
        params=None,
        data=None,
        files=None,
        headers=None,
        cookies=None,
        allow_redirects=True,
    ):
        if "bilivideo.com" in url and not files:
            resp = await direct_session.request(
                method=method,
                url=url,
                params=params or {},
                data=data if data is not None else {},
                headers=headers or {},
                cookies=cookies or {},
                allow_redirects=allow_redirects,
                proxy=None,
                timeout=aiohttp.ClientTimeout(total=300),
            )
            bili_resp = BiliAPIResponse(
                code=resp.status,
                headers=dict(resp.headers),
                cookies={k: v.value for k, v in resp.cookies.items()},
                raw=await resp.read(),
                url=str(resp.url),
            )
            resp.release()
            await resp.wait_for_close()
            return bili_resp
        return await original_request(
            method=method,
            url=url,
            params=params or {},
            data=data if data is not None else {},
            files=files or {},
            headers=headers or {},
            cookies=cookies or {},
            allow_redirects=allow_redirects,
        )

    client.request = routed_request

    page = video_uploader.VideoUploaderPage(str(video_path), meta.get("page_title", "正片"), "")
    # Use a known-good line instead of the library's multi-host probe; the
    # probe can stall behind the local HTTP proxy even when BDA2 is reachable.
    uploader = video_uploader.VideoUploader(
        [page], video_meta, cred, cover=str(cover_path), line=video_uploader.Lines.BDA2
    )

    def onevent(payload):
        if not isinstance(payload, dict):
            return
        name = str(payload.get("name") or "").upper()
        data = payload.get("data") or ()
        info = data[0] if isinstance(data, tuple) and data and isinstance(data[0], dict) else {}
        if name in {"PREUPLOAD", "AFTER_PAGE", "PRE_COVER", "AFTER_COVER", "PRE_SUBMIT", "AFTER_SUBMIT", "COMPLETE", "FAILED"}:
            log(f"upload event: {name}")
        if name in {"FAILED", "SUBMIT_FAILED", "COVER_FAILED"}:
            err = info.get("err") if isinstance(info, dict) else None
            if err:
                log(f"upload error detail: {type(err).__name__}: {err}")

    uploader.add_event_listener("__ALL__", onevent)
    try:
        return await uploader.start()
    finally:
        client.request = original_request
        await direct_session.close()


async def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--metadata", type=Path, default=DEFAULT_META)
    ap.add_argument("--credential", type=Path, default=DEFAULT_CRED)
    ap.add_argument("--proxy", default=os.environ.get("BILI_PROXY", DEFAULT_PROXY))
    ap.add_argument("--preflight", action="store_true")
    ap.add_argument("--submit", action="store_true")
    ap.add_argument("--status", action="store_true")
    ap.add_argument("--bvid")
    ap.add_argument("--record-dir", type=Path)
    args = ap.parse_args()
    if not (args.preflight or args.submit or args.status):
        ap.error("choose --preflight, --submit or --status")

    meta, _probe, _cues = local_checks(Path(args.metadata))

    if args.status:
        cred = load_json(args.credential)
        archives = fetch_archives(cred, proxy=args.proxy)
        a = find_archive(archives, bvid=args.bvid)
        if not a:
            log(f"status: no archive found for {args.bvid!r} (total {len(archives)})")
            return 1
        log(json.dumps(summarize_archive(a), ensure_ascii=False, indent=2))
        return 0

    cred = load_json(args.credential)
    target_uid = int(meta.get("target_uid") or 0)
    if target_uid <= 0:
        raise ValueError("metadata.target_uid is required for a target-account upload")
    mid, uname = fetch_nav(cred, args.proxy)
    if mid != target_uid:
        raise RuntimeError(f"credential belongs to uid {mid}, expected target uid {target_uid}")
    log(f"account: {uname} (uid {mid}) matches target uid {target_uid}")
    record_dir = (
        args.record_dir.resolve()
        if args.record_dir
        else BASE / "publish" / "records" / f"target-{target_uid}"
    )
    record_dir.mkdir(parents=True, exist_ok=True)
    existing = find_archive(fetch_archives(cred, proxy=args.proxy), title=meta["title"])
    if existing:
        log(
            "ABORT: an archive with the exact same title already exists: "
            + json.dumps(summarize_archive(existing), ensure_ascii=False)
        )
        return 3
    log("existing check: no archive with this exact title")

    cred_obj, video_meta = await prepare_meta(meta, args.credential, args.proxy)
    result = {"preflight_at": datetime.now(timezone.utc).isoformat(), "title": meta["title"], "video": meta["video"]}
    write_json(record_dir / "preflight.json", result)
    log("preflight: OK")
    if args.preflight:
        return 0

    # Real submit: only one call, no automatic retry.
    video_path = (BASE / meta["video"]).resolve()
    cover_path = (BASE / meta["cover"]).resolve()
    log("submit: starting one-shot upload; do not run this command again")
    started = time.time()
    try:
        resp = await submit(meta, cred_obj, video_meta, video_path, cover_path)
    except Exception as e:
        err = {
            "submitted_at": datetime.now(timezone.utc).isoformat(),
            "status": "failed",
            "error_type": type(e).__name__,
            "error": str(e)[:1000],
        }
        write_json(record_dir / "upload-error.json", err)
        log(f"SUBMIT FAILED: {type(e).__name__}: {e}")
        return 1

    elapsed = time.time() - started
    out = {
        "submitted_at": datetime.now(timezone.utc).isoformat(),
        "elapsed_seconds": round(elapsed, 2),
        "status": "submitted",
        "result": resp,
        "title": meta["title"],
        "bvid": resp.get("bvid") if isinstance(resp, dict) else None,
        "aid": resp.get("aid") if isinstance(resp, dict) else None,
    }
    write_json(record_dir / "upload-result.json", out)
    log("submit response: " + json.dumps(resp, ensure_ascii=False))

    # Re-read archive state, but do not call the upload endpoint again.
    try:
        archives = fetch_archives(cred, proxy=args.proxy)
        a = find_archive(archives, bvid=out.get("bvid"))
        if a:
            out["archive"] = summarize_archive(a)
            write_json(record_dir / "upload-result.json", out)
            log("archive: " + json.dumps(out["archive"], ensure_ascii=False))
        else:
            log("archive: submitted, not yet visible in member archive list")
    except Exception as e:
        log(f"archive check warning: {type(e).__name__}: {e}")
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
