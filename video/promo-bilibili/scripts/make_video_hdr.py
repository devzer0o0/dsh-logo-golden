import os, sys, argparse, subprocess, time, bisect, functools
sys.path.insert(0, 'scripts')
import numpy as np
from PIL import Image, ImageDraw, ImageFilter

import make_video as mv
from design import W, H, smooth, rounded_mask

BRAND = np.load('hdr/capture/brand-hdr-linear.npy', mmap_mode='r')
BPTS = [float(l.split(',')[0]) for l in open('hdr/capture/brand-hdr-24.pts') if l.strip()]
assert len(BPTS) == BRAND.shape[0], (len(BPTS), BRAND.shape)

# sRGB EOTF LUT (white=1.0)
_x = np.arange(256, dtype=np.float32) / 255.0
_srgb = np.where(_x <= 0.04045, _x / 12.92, ((_x + 0.055) / 1.055) ** 2.4).astype(np.float32)
SRGB_LUT = _srgb

# linear BT.709 -> BT.2020
M709_2020 = np.array([
    [0.627404, 0.329283, 0.043313],
    [0.069097, 0.919540, 0.011362],
    [0.016391, 0.088013, 0.895595],
], dtype=np.float32)

WHITE_NITS = 100.0
GAIN_BRAND = 0.86
MASK_CACHE = {}
S3_SRC_HDR = [(3.30, 16.0), (4.00, 18.6), (7.55, 21.2)]

def brand_at(ts):
    i = bisect.bisect_right(BPTS, ts) - 1
    i = max(0, min(i, BRAND.shape[0] - 1))
    return np.asarray(BRAND[i], dtype=np.float32)

def resize_linear(a, w, h):
    out = np.empty((h, w, 3), dtype=np.float32)
    for c in range(3):
        im = Image.fromarray(np.ascontiguousarray(a[:, :, c]), mode='F')
        im = im.resize((w, h), Image.Resampling.BICUBIC)
        out[:, :, c] = np.asarray(im, dtype=np.float32)
    return np.maximum(out, 0.0)

def mask_for(w, h, radius):
    key = (w, h, radius)
    if key in MASK_CACHE:
        return MASK_CACHE[key]
    m = np.zeros((h, w), dtype=np.float32)
    inner = np.asarray(rounded_mask((w - 2, h - 2), radius), dtype=np.float32) / 255.0
    m[1:h-1, 1:w-1] = inner
    MASK_CACHE[key] = m
    return m

def full_mask(w, h, radius):
    return mask_for(w, h, radius)

def feather_mask(w, h, pad):
    m = np.zeros((h, w), dtype=np.float32)
    m[pad:h-pad, pad:w-pad] = 1.0
    im = Image.fromarray((m * 255).astype(np.uint8), 'L').filter(ImageFilter.GaussianBlur(pad))
    return np.asarray(im, dtype=np.float32) / 255.0

def overlay_linear(img, box, src, gain=1.0, mask=None, crop_src=None):
    x, y, w, h = box
    if crop_src is not None:
        sx, sy, sw, sh = crop_src
        src = src[sy:sy+sh, sx:sx+sw]
    b = resize_linear(src, w, h) * gain
    x0, y0 = max(0, x), max(0, y)
    x1, y1 = min(W, x + w), min(H, y + h)
    if x1 <= x0 or y1 <= y0:
        return
    sx0, sy0 = x0 - x, y0 - y
    b = b[sy0:sy0 + (y1 - y0), sx0:sx0 + (x1 - x0)]
    if mask is not None:
        mm = mask[sy0:sy0 + (y1 - y0), sx0:sx0 + (x1 - x0)]
        roi = img[y0:y1, x0:x1]
        img[y0:y1, x0:x1] = b * mm[..., None] + roi * (1.0 - mm[..., None])
    else:
        img[y0:y1, x0:x1] = b

def s3_linear(t, shot):
    src0, t0 = S3_SRC_HDR[shot]
    src = src0 + (t - t0)
    b = brand_at(src - 1.81) * GAIN_BRAND
    bx0, by0, bx1, by1 = mv.S3_BOX[shot]
    mask = Image.new('L', (400, 66), 0)
    md = ImageDraw.Draw(mask)
    md.rounded_rectangle([bx0 - 10, by0 - 8, bx1 + 10, by1 + 8], radius=10, fill=255)
    mask = mask.filter(ImageFilter.GaussianBlur(9))
    m = np.asarray(mask, dtype=np.float32)[..., None] / 255.0
    return b * m + b * 0.70 * (1.0 - m)

def s3_hdr(t):
    if 18.45 < t < 18.75:
        a = smooth((t - 18.45) / 0.30)
        p = s3_linear(t, 0) * (1 - a) + s3_linear(t, 1) * a
    elif 21.05 < t < 21.35:
        a = smooth((t - 21.05) / 0.30)
        p = s3_linear(t, 1) * (1 - a) + s3_linear(t, 2) * a
    elif t < 18.6:
        p = s3_linear(t, 0)
    elif t < 21.2:
        p = s3_linear(t, 1)
    else:
        p = s3_linear(t, 2)
    return p

def apply_hdr(t, img):
    if t < 3.4:
        fade = 1.0 - t / 0.45 if t < 0.45 else 1.0
        b = brand_at(2.95 + t)
        overlay_linear(img, (440, 310, 1040, 172), b, GAIN_BRAND * fade, full_mask(1040, 172, 10))
    elif t < 9.2:
        # brand sits at (32,109) inside the 450x330 host crop; S1 panel is 1.6x
        b = brand_at(8.0 + (t - 3.4))
        overlay_linear(img, (1125, 480, 589, 56), b, 1.0, feather_mask(589, 56, 3), crop_src=(2, 12, 368, 36))
    elif t < 16.0:
        b = brand_at(3.0 + (t - 9.2) - 1.81)
        overlay_linear(img, (318, 416, 1320, 218), b, GAIN_BRAND, full_mask(1320, 218, 10))
    elif t < 24.0:
        p = s3_hdr(t)
        overlay_linear(img, (338, 448, 1280, 211), p, 1.0, full_mask(1280, 211, 10))
    elif t < 31.0:
        b = brand_at(9.25 - 1.81)
        overlay_linear(img, (86, 446, 840, 139), b, GAIN_BRAND, full_mask(840, 139, 10))
        b = brand_at(9.2 + (t - 24.0) - 1.81)
        overlay_linear(img, (994, 446, 840, 139), b, GAIN_BRAND, full_mask(840, 139, 10))
    elif t < 38.0:
        x = int(660 - 600 * (t - 31.0))
        for i in range(12):
            cx = x + i * 412
            if cx >= W or cx + 400 <= 0:
                continue
            b = brand_at(9.25 + i * 0.25 - 1.81)
            overlay_linear(img, (cx, 460, 400, 66), b, GAIN_BRAND)
    elif t < 45.0:
        pass
    elif t < 51.5:
        # brand sits at (32,109) inside the 450x330 host crop; S7 panel is 1.733x
        b = brand_at(12.0 + (t - 45.0))
        overlay_linear(img, (1069, 461, 638, 61), b, 1.0, feather_mask(638, 61, 3), crop_src=(2, 12, 368, 36))
    elif t < 58.0:
        lt = t - 51.5
        fade = lt / 0.4 if lt < 0.4 else 1.0
        b = brand_at(18.35 + lt * 0.5 - 1.81)
        overlay_linear(img, (388, 276, 1180, 195), b, GAIN_BRAND * fade, full_mask(1180, 195, 10))
    else:
        fade = 1.0 - (t - 66.2) / 0.8 if t > 66.2 else 1.0
        b = brand_at(19.8 - 1.81)
        overlay_linear(img, (568, 228, 820, 135), b, GAIN_BRAND * fade, full_mask(820, 135, 10))

def linear_base(im):
    a = np.asarray(im, dtype=np.uint8)
    lin = SRGB_LUT[a]
    return lin @ M709_2020.T

def pq_oetf(lin):
    # lin: relative to SDR white, white=WHITE_NITS
    L = np.maximum(lin, 0.0) * (WHITE_NITS / 10000.0)
    m1 = 2610.0 / 16384.0
    m2 = 2523.0 / 32.0
    c1 = 3424.0 / 4096.0
    c2 = 2413.0 / 128.0
    c3 = 2392.0 / 128.0
    p = np.power(L, m1)
    return np.power((c1 + c2 * p) / (1.0 + c3 * p), m2)

def yuv420_10(lin):
    pq = pq_oetf(lin)
    R, G, B = pq[..., 0], pq[..., 1], pq[..., 2]
    Y = 0.2627 * R + 0.6780 * G + 0.0593 * B
    Cb = (B - Y) / 1.9404
    Cr = (R - Y) / 1.8814
    Yq = np.clip(np.round(64.0 + Y * 876.0), 0, 1023).astype(np.uint16)
    Cbq = np.clip(np.round(512.0 + Cb * 896.0), 0, 1023).astype(np.uint16)
    Crq = np.clip(np.round(512.0 + Cr * 896.0), 0, 1023).astype(np.uint16)
    Cbq = Cbq.reshape(H // 2, 2, W // 2, 2).mean(axis=(1, 3)).round().astype(np.uint16)
    Crq = Crq.reshape(H // 2, 2, W // 2, 2).mean(axis=(1, 3)).round().astype(np.uint16)
    return np.concatenate([Yq.ravel(), Cbq.ravel(), Crq.ravel()]).astype('<u2')

def preview(lin, path):
    # simple filmic tone map for SDR inspection only
    tm = 1.0 - np.exp(-np.maximum(lin, 0.0) * 1.25)
    srgb = np.where(tm <= 0.0031308, tm * 12.92, 1.055 * np.power(tm, 1/2.4) - 0.055)
    out = np.clip(srgb * 255.0 + 0.5, 0, 255).astype(np.uint8)
    Image.fromarray(out, 'RGB').save(path)

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--still', type=float)
    ap.add_argument('--out', default='build/hdr-preview.png')
    ap.add_argument('--render', action='store_true')
    ap.add_argument('--from', dest='t0', type=float, default=0.0)
    ap.add_argument('--to', dest='t1', type=float, default=67.0)
    ap.add_argument('--video', default='build/dsh-logo-golden-promo-hdr-noaudio.mp4')
    a = ap.parse_args()
    if a.still is not None:
        t = a.still
        st = time.time()
        im = mv.render(t)
        lin = linear_base(im)
        apply_hdr(t, lin)
        nits = lin * WHITE_NITS
        flat = nits.ravel()
        print('t', t, 'shape', lin.shape, 'max_nits', float(flat.max()), 'p99.99', float(np.percentile(flat, 99.99)), 'p99.9', float(np.percentile(flat, 99.9)), 'gt1000', int((flat > 1000).sum()), 'gt100', int((flat > 100).sum()))
        preview(lin, a.out)
        print('saved', a.out, 'in', round(time.time() - st, 2), 's')
    elif a.render:
        n0 = int(round(a.t0 * 30)); n1 = int(round(a.t1 * 30))
        cmd = ['ffmpeg', '-y', '-hide_banner', '-loglevel', 'error',
               '-f', 'rawvideo', '-pix_fmt', 'yuv420p10le', '-s', f'{W}x{H}', '-r', '30', '-i', '-',
               '-c:v', 'libx265', '-preset', 'medium', '-crf', '18', '-pix_fmt', 'yuv420p10le', '-profile:v', 'main10',
               '-color_primaries', 'bt2020', '-color_trc', 'smpte2084', '-colorspace', 'bt2020nc', '-color_range', 'tv',
               '-x265-params', 'hdr10=1:master-display=G(13250,34500)B(7500,3000)R(34000,16000)WP(15635,16450)L(40000000,50):max-cll=1700,800:repeat-headers=1',
               '-bsf:v', 'hevc_metadata=transfer_characteristics=16:colour_primaries=9:matrix_coefficients=9',
               '-movflags', '+faststart', a.video]
        print('encoding', a.video, 'frames', n1 - n0)
        p = subprocess.Popen(cmd, stdin=subprocess.PIPE)
        t0 = time.time(); peak = 0.0; peak_luma = 0.0
        for n in range(n0, n1):
            t = n / 30.0
            im = mv.render(t)
            lin = linear_base(im)
            apply_hdr(t, lin)
            peak = max(peak, float(lin.max() * WHITE_NITS))
            luma = 0.2627*lin[..., 0] + 0.6780*lin[..., 1] + 0.0593*lin[..., 2]
            peak_luma = max(peak_luma, float(luma.max() * WHITE_NITS))
            p.stdin.write(yuv420_10(lin).tobytes())
            if n % 60 == 0:
                print(f'{n}/{n1} t={t:.2f} peak={peak:.0f} elapsed={time.time()-t0:.1f}s', flush=True)
        p.stdin.close()
        rc = p.wait()
        print('ffmpeg rc', rc, 'peak_nits', peak, 'peak_luma', peak_luma, 'elapsed', round(time.time() - t0, 1))

if __name__ == '__main__':
    main()
