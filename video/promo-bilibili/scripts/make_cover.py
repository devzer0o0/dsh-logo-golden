import os, sys
sys.path.insert(0, 'scripts')
from design import *
from PIL import Image, ImageDraw, ImageFilter, ImageEnhance
import numpy as np

OUT = 'cover'
os.makedirs(OUT, exist_ok=True)
BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

def cover_canvas(W, H):
    bg = gradient(W, H, (13, 16, 22), (4, 5, 8)).convert('RGBA')
    bg = Image.alpha_composite(bg, radial_glow(W, H, W * 0.5, H * 0.30, W * 0.38, (196, 150, 76), 34))
    bg = Image.alpha_composite(bg, radial_glow(W, H, W * 0.12, H * 0.92, W * 0.36, (120, 90, 45), 16))
    yy, xx = np.mgrid[0:H, 0:W]
    rr = np.sqrt(((xx - W / 2) / (W * 0.64)) ** 2 + ((yy - H / 2) / (H * 0.64)) ** 2)
    v = np.clip(1.0 - 0.58 * np.clip(rr - 0.28, 0, 1) ** 1.5, 0, 1)
    vimg = Image.fromarray((v * 255).astype(np.uint8), 'L').convert('RGB')
    return ImageChops.multiply(bg.convert('RGB'), vimg).convert('RGB')

def rounded_panel(W, H, x, y, w, h, r=18):
    # draw at 2x, then composite
    layer = Image.new('RGBA', (W, H), (0, 0, 0, 0))
    d = ImageDraw.Draw(layer)
    d.rounded_rectangle([x + 8, y + 18, x + w + 8, y + h + 18], radius=r + 4, fill=(0, 0, 0, 150))
    layer = layer.filter(ImageFilter.GaussianBlur(30))
    d = ImageDraw.Draw(layer)
    d.rounded_rectangle([x - 3, y - 3, x + w + 3, y + h + 3], radius=r + 5, fill=(214, 176, 104, 34))
    layer = layer.filter(ImageFilter.GaussianBlur(22))
    d = ImageDraw.Draw(layer)
    d.rounded_rectangle([x, y, x + w, y + h], radius=r, fill=(9, 12, 17, 250))
    d.rounded_rectangle([x, y, x + w, y + h], radius=r, outline=(216, 181, 106, 76), width=2)
    return layer

def make_cover(W, H, out):
    S = W / 1146.0
    f = cover_canvas(W, H)
    d = ImageDraw.Draw(f)
    # top rules and labels
    line_y = int(74 * S)
    d.line([(int(72*S), line_y), (W-int(72*S), line_y)], fill=(205, 168, 100, 40), width=max(1, int(S)))
    label(d, 'DEEPSEEK HARNESS / PLUGIN', int(74*S), int(96*S), int(17*S), (201, 164, 94), tracking=int(4*S))
    label(d, 'v0.4.16', W-int(74*S), int(96*S), int(17*S), (150, 126, 84), tracking=int(3*S), anchor='ra')
    # brand screen panel
    px, py = int(105*S), int(148*S)
    pw, ph = int(936*S), int(192*S)
    f = Image.alpha_composite(f.convert('RGBA'), rounded_panel(W, H, px, py, pw, ph, int(18*S))).convert('RGB')
    d = ImageDraw.Draw(f)
    bx, by = px + int(18*S), py + int(24*S)
    bw = pw - int(36*S)
    bh = int(round(bw * 195 / 1200))
    brand = Image.open(os.path.join(BASE, 'build/crop-tight.png')).convert('RGB')
    brand = brand.crop((4, 0, 1192, brand.height))
    brand = brand.resize((bw, bh), Image.Resampling.LANCZOS)
    brand = brand.filter(ImageFilter.UnsharpMask(radius=2, percent=110, threshold=2))
    mask = rounded_mask((bw, bh), int(8*S), 0)
    f.paste(brand, (bx, by), mask)
    d.rounded_rectangle([bx, by, bx + bw - 1, by + bh - 1], radius=int(8*S), outline=(255, 255, 255, 24), width=max(1, int(S)))
    # title
    title = text_gradient('侧栏里的金色', int(88*S), 0, tracking=int(2*S))
    paste_grad(f, title, W/2 - title.width/2, int(372*S) - 24*S)
    # small rule
    ry = int(492*S)
    d.line([(W/2 - 90*S, ry), (W/2 + 90*S, ry)], fill=(196, 158, 92, 150), width=max(1, int(S)))
    # subtitle and tagline
    d.text((W/2, int(508*S)), 'dsh-logo-golden', font=F(FONT_MONO, int(29*S)), fill=(198, 162, 98), anchor='ma')
    d.text((W/2, int(554*S)), '真实宿主录屏  ·  3.000 秒扫光周期', font=F(FONT_HIRAGINO, int(20*S), 0), fill=(196, 190, 178), anchor='ma')
    # bottom
    by2 = int(664*S)
    d.line([(int(105*S), by2), (W-int(105*S), by2)], fill=(205, 168, 100, 28), width=max(1, int(S)))
    d.text((int(105*S), int(686*S)), 'DeepSeek Harness 侧栏品牌插件', font=F(FONT_HIRAGINO, int(16*S), 0), fill=(150, 144, 132), anchor='la')
    d.text((W-int(105*S), int(686*S)), 'Apache-2.0  ·  开源', font=F(FONT_HIRAGINO, int(16*S), 0), fill=(150, 144, 132), anchor='ra')
    # very subtle film grain
    arr = np.asarray(f, dtype=np.int16)
    rng = np.random.default_rng(11)
    arr = np.clip(arr + rng.normal(0, 2.0, (H, W))[:, :, None], 0, 255).astype(np.uint8)
    f = Image.fromarray(arr, 'RGB')
    f.save(out, quality=96)
    print('saved', out, f.size)
    return f

# 2x master for 16:10, then downscale
master = make_cover(2292, 1434, os.path.join(OUT, 'cover-master-2x.png'))
# 1146x717 Bilibili cover
master.resize((1146, 717), Image.Resampling.LANCZOS).save(os.path.join(OUT, 'dsh-logo-golden-cover-1146x717.png'))
print('done');
