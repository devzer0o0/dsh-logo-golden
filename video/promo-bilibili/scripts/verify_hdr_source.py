#!/usr/bin/env python3
"""Inspect the captured PQ signal and its cached linear frames, without a display measurement."""
import argparse
import json
import subprocess
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

import numpy as np

BASE = Path(__file__).resolve().parents[1]


def probe(path):
    result = subprocess.check_output([
        "ffprobe", "-v", "error", "-select_streams", "v:0",
        "-show_entries",
        "stream=codec_name,profile,width,height,pix_fmt,color_space,color_transfer,color_primaries,r_frame_rate:format=duration",
        "-of", "json", str(path),
    ])
    data = json.loads(result)
    return {**data["streams"][0], "duration": data["format"]["duration"]}


def first_linear_frame(path, width, height):
    # Decode the captured 10-bit YCbCr planes directly. Converting to integer RGB
    # first can clip out-of-gamut channels before PQ is inverted.
    raw = subprocess.check_output([
        "ffmpeg", "-v", "error", "-i", str(path), "-frames:v", "1",
        "-pix_fmt", "yuv420p10le", "-f", "rawvideo", "-",
    ])
    values = np.frombuffer(raw, dtype="<u2").astype(np.float64)
    pixels = width * height
    y = (values[:pixels].reshape(height, width) - 64) / 876
    cb = (values[pixels:pixels * 5 // 4].reshape(height // 2, width // 2) - 512) / 896
    cr = (values[pixels * 5 // 4:].reshape(height // 2, width // 2) - 512) / 896
    cb = cb.repeat(2, 0).repeat(2, 1)
    cr = cr.repeat(2, 0).repeat(2, 1)
    red = y + 1.4746 * cr
    blue = y + 1.8814 * cb
    green = (y - 0.2627 * red - 0.0593 * blue) / 0.6780
    pq = np.maximum(np.stack([red, green, blue], axis=-1), 0)
    m1, m2 = 2610 / 16384, 2523 / 32
    c1, c2, c3 = 3424 / 4096, 2413 / 128, 2392 / 128
    power = pq ** (1 / m2)
    # Relative to the compositor's 100-nit reference white; not measured nits.
    return (np.maximum(power - c1, 0) / (c2 - c3 * power)) ** (1 / m1) * 100


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", type=Path, default=BASE / "publish/hdr-verification.json")
    args = parser.parse_args()
    capture_path = BASE / "hdr/capture/brand-hdr-24.mov"
    capture = probe(capture_path)
    master = probe(BASE / "build/dsh-logo-golden-promo-1080p-hdr.mp4")
    for metadata in (capture, master):
        if (metadata["pix_fmt"], metadata["color_transfer"], metadata["color_primaries"], metadata["color_space"]) != (
            "yuv420p10le", "smpte2084", "bt2020", "bt2020nc"
        ):
            raise ValueError("Expected a 10-bit PQ / BT.2020 non-constant-luminance video")
    cached = np.load(BASE / "hdr/capture/brand-hdr-linear.npy", mmap_mode="r")
    actual = first_linear_frame(capture_path, capture["width"], capture["height"])
    first_cached = np.asarray(cached[0], dtype=np.float64)
    if actual.shape != first_cached.shape or not np.isfinite(cached).all():
        raise ValueError("The cached capture has an unexpected shape or non-finite values")
    peak = float(actual.max())
    if peak <= 1:
        raise ValueError("The first captured frame does not retain above-reference-white signal")
    result = {
        "checked_at": datetime.now(ZoneInfo("Asia/Shanghai")).isoformat(timespec="seconds"),
        "capture": {"file": "hdr/capture/brand-hdr-24.mov", **capture},
        "master": {"file": "build/dsh-logo-golden-promo-1080p-hdr.mp4", **master},
        "reference_white_nits_for_encoding": 100,
        "capture_first_frame_peak_relative_to_reference_white": peak,
        "cached_linear_shape": list(cached.shape),
        "cached_linear_peak": float(cached.max()),
        "cached_channels_above_reference_white": int(np.count_nonzero(cached > 1)),
        "first_frame_cache_correlation": float(np.corrcoef(actual.ravel(), first_cached.ravel())[0, 1]),
        "first_frame_cache_mean_absolute_difference": float(np.abs(actual - first_cached).mean()),
        "note": "真实采集文件的PQ信号核验；解码与色度重建方法可产生数值差异。未测量显示器物理亮度。",
    }
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
