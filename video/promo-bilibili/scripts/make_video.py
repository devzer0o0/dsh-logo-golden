import os, sys, bisect, subprocess, argparse, json, time
sys.path.insert(0,'scripts')
from design import *
from PIL import Image, ImageDraw, ImageFont, ImageFilter

FRAME_DIR='footage/brand-60fps'
HOST_DIR='footage/host-30fps'
PTS=[float(l.split(',')[0]) for l in open('build/pts.txt') if l.strip()]
BRAND_CACHE={}
HOST_CACHE={}
W_FPS=30
DUR=67.0
N=int(round(DUR*W_FPS))

def bframe(ts):
    i=bisect.bisect_right(PTS,ts)-1
    i=clamp(i,0,len(PTS)-1)
    if i in BRAND_CACHE: return BRAND_CACHE[i]
    with Image.open(os.path.join(FRAME_DIR,f'{i+1:05d}.png')) as im:
        p=im.convert('RGB').crop((25,48,425,114))
    if len(BRAND_CACHE)>700:
        BRAND_CACHE.pop(next(iter(BRAND_CACHE)))
    p=grade(p)
    BRAND_CACHE[i]=p
    return p

def hframe(ts):
    i=clamp(int(round(ts*30))+1,1,720)
    if i in HOST_CACHE: return HOST_CACHE[i]
    with Image.open(os.path.join(HOST_DIR,f'{i:05d}.png')) as im:
        p=im.convert('RGB')
    if len(HOST_CACHE)>140:
        HOST_CACHE.pop(next(iter(HOST_CACHE)))
    HOST_CACHE[i]=p
    return p

def base(): return make_bg().copy()

def top_labels(frame,left,right):
    d=ImageDraw.Draw(frame)
    label(d,left,96,112,18)
    label(d,right,1824,112,18,anchor='ra')

def grad_title(frame,text,x,y,size,tracking=2,center=False):
    layer=text_gradient(text,size,0,tracking)
    if center: x=x-layer.width/2
    paste_grad(frame,layer,x-24,y-24)

def grad_line(frame,text,x,y,size,tracking=2,center=False):
    layer=text_gradient(text,size,0,tracking)
    if center: x=x-layer.width/2
    paste_grad(frame,layer,x-24,y-24)

def fit_mono(text,maxw,size,index=0):
    while size>16 and F(FONT_MONO,size,index).getlength(text)>maxw:
        size-=1
    return size

# ---------- scenes ----------
def s0(t):
    f=base()
    top_labels(f,'DSH / LOGO GOLDEN','A REAL HOST CAPTURE')
    p=panel(bframe(2.95+t),1040)
    place_panel(f,p,422,292)
    grad_title(f,'侧栏里的金色，会动。',960,596,62,center=True)
    d=ImageDraw.Draw(f)
    d.text((960,716),'DeepSeek Harness 桌面端  ·  真实录屏',font=F(FONT_HIRAGINO,28,0),fill=(196,190,178),anchor='ma')
    subtitle(f,'真实宿主 · 每 3.000 秒一个周期')
    if t<0.45: f=fade(f,1-t/0.45)
    return f

def s1(t):
    f=base()
    top_labels(f,'01 / REAL HOST','LIVE CAPTURE')
    grad_title(f,'不是渲染图。',120,252,58)
    d=ImageDraw.Draw(f)
    d.text((120,352),'是侧栏里的实时画面。',font=F(FONT_HIRAGINO,38,0),fill=PAPER)
    body(d,'DeepSeek Harness 桌面端\n左侧栏顶部，品牌组合原样保留。\n鲸鱼、字标、HARNESS 铭牌。',120,452,27,(172,166,154),line=1.8)
    p=panel_exact(hframe(9.2+(t-3.4)),720,528,pad=14,radius=14)
    place_panel(f,p,1060,292)
    d.ellipse([1084,260,1096,272],fill=(214,178,106))
    label(d,'LIVE',1106,252,18)
    subtitle(f,'真实宿主画面 · 1× 速度')
    return f

def s2(t):
    f=base()
    top_labels(f,'02 / FULL CYCLE','1× REAL TIME')
    grad_title(f,'完整扫光周期',96,168,82)
    d=ImageDraw.Draw(f)
    d.text((98,294),'进入  /  掠过  /  离开',font=F(FONT_HIRAGINO,28,0),fill=(190,184,172))
    lt=t-9.2
    src=3.0+lt
    p=panel(bframe(src),1320)
    place_panel(f,p,300,398)
    # cycle meter: entry 250 / surface 2200 / exit 250 / rest 300 ms
    x0,x1,y=300,1620,744
    phase=((src-3.25)%3.0)/3.0
    segs=[(0.00,0.0833,(128,102,58),'ENTER 0.25'),(0.0833,0.8167,(178,142,82),'SURFACE 2.20'),
          (0.8167,0.9000,(128,102,58),'EXIT 0.25'),(0.9000,1.0000,(58,50,38),None)]
    d.rectangle([x0,y-1,x1,y+4],fill=(38,34,28))
    for a,b,c,_ in segs:
        d.rectangle([x0+int((x1-x0)*a),y,x0+int((x1-x0)*b),y+3],fill=c)
    d.rectangle([x0,y,x0+int((x1-x0)*phase),y+3],fill=(236,204,140))
    for a,b,c,lab in segs:
        if lab:
            cx=int(x0+(x1-x0)*(a+b)/2)
            d.text((cx,y+18),lab,font=F(FONT_MONO,15),fill=(196,164,106),anchor='ma')
    pname='ENTER' if phase<0.0833 else ('SURFACE' if phase<0.8167 else ('EXIT' if phase<0.9 else 'REST'))
    label(d,'PHASE',96,714,14,(150,124,80))
    d.text((96,740),pname,font=F(FONT_MONO,26),fill=(214,178,106))
    cx=x0+int((x1-x0)*phase)
    d.rectangle([cx,y-8,cx+1,y+12],fill=(250,226,170))
    d.ellipse([cx-3,y-3,cx+4,y+4],fill=(250,226,170))
    cyc=clamp(int((src-3.25)//3.0)+1,1,2)
    label(d,f'CYCLE  {cyc:02d} / 02',x1,y-64,16,(196,164,106),anchor='ra')
    label(d,'PERIOD  3.000 s',x1,y-32,16,(190,156,96),anchor='ra')
    subtitle(f,'真实速度 · 3.000 秒一个周期')
    return f

S3_TEXT=[
 ('鲸鱼','24 px / ORIGINAL VECTOR','侧栏最左侧的金属标记'),
 ('字标','GOLD GRADIENT','光沿着字形边缘移动'),
 ('铭牌','DARK ENGRAVING','金属底座上的深色刻字'),
]
S3_BOX=[(7,16,56,50),(59,16,242,50),(273,16,377,50)]
S3_SRC=[(3.30,16.0),(4.00,18.6),(5.00,21.2)]

def s3_shot(t,shot):
    f=base()
    top_labels(f,'03 / DETAILS','ORIGINAL VECTOR')
    d=ImageDraw.Draw(f)
    name,spec,note=S3_TEXT[shot]
    grad_title(f,name,96,170,70)
    label(d,spec,98,278,22,(196,160,96))
    d.text((98,320),note,font=F(FONT_HIRAGINO,26,0),fill=(176,170,158))
    src0,t0=S3_SRC[shot]
    src=src0+(t-t0)
    p=bframe(src)
    # spotlight dim outside element, soft
    bx0,by0,bx1,by1=S3_BOX[shot]
    mask=Image.new('L',(400,66),0)
    md=ImageDraw.Draw(mask)
    md.rounded_rectangle([bx0-10,by0-8,bx1+10,by1+8],radius=10,fill=255)
    mask=mask.filter(ImageFilter.GaussianBlur(9))
    dim=Image.blend(p,Image.new('RGB',p.size,(0,0,0)),0.30)
    p=Image.composite(p,dim,mask)
    pan=panel(p,1280)
    X,Y=320,430
    place_panel(f,pan,X,Y)
    # bracket
    sc=1280/400.0
    px,py=X+18,Y+18
    x0=px+(bx0-6)*sc; y0=py+(by0-5)*sc; x1=px+(bx1+6)*sc; y1=py+(by1+5)*sc
    gold=(196,158,92)
    d.rounded_rectangle([x0,y0,x1,y1],radius=4,outline=gold,width=1)
    tick=9
    for (cx,cy,dx,dy) in [(x0,y0,1,1),(x1,y0,-1,1),(x0,y1,1,-1),(x1,y1,-1,-1)]:
        d.line([(cx,cy),(cx+dx*tick,cy)],fill=gold,width=2)
        d.line([(cx,cy),(cx,cy+dy*tick)],fill=gold,width=2)
    # step row
    xx=98
    for i in range(3):
        active=(i==shot)
        txt=f'0{i+1}  '+['鲸鱼','字标','铭牌'][i]
        ft=F(FONT_HIRAGINO,18,2 if active else 0)
        col=(222,186,118) if active else (92,84,70)
        d.text((xx,738),txt,font=ft,fill=col)
        wd=d.textlength(txt,font=ft)
        if active: d.rectangle([xx,764,xx+wd,766],fill=(196,158,92))
        xx+=wd+46
    subtitle(f,['鲸鱼：24 px 的金属重量','字标：光沿着字形走','铭牌：HARNESS 保持深色'][shot])
    return f

def s3(t):
    if 18.45<t<18.75:
        a=smooth((t-18.45)/0.30); return Image.blend(s3_shot(t,0),s3_shot(t,1),a)
    if 21.05<t<21.35:
        a=smooth((t-21.05)/0.30); return Image.blend(s3_shot(t,1),s3_shot(t,2),a)
    if t<18.6: return s3_shot(t,0)
    if t<21.2: return s3_shot(t,1)
    return s3_shot(t,2)

def s4(t):
    f=base()
    top_labels(f,'04 / A–B','SAME CROP · DIFFERENT TIME')
    grad_title(f,'静止，是金属。',96,158,52)
    grad_title(f,'掠过，是光。',96,224,52)
    d=ImageDraw.Draw(f)
    d.text((1824,158),'1× REAL TIME',font=F(FONT_MONO,16),fill=(150,126,82),anchor='ra')
    left=bframe(9.25)
    right=bframe(9.2+(t-24.0))
    pl=panel(left,840,pad=16); pr=panel(right,840,pad=16)
    place_panel(f,pl,70,430); place_panel(f,pr,978,430)
    label(d,'REST  /  9.25 s',88,386,16,(160,132,80))
    label(d,'SWEEP  /  9.20 s →',996,386,16,(196,160,96))
    d.line([(960,372),(960,660)],fill=(70,60,42),width=1)
    d.polygon([(960,505),(968,517),(960,529),(952,517)],outline=(150,124,76))
    label(d,'STATIC FRAME',88,636,14,(120,110,92))
    label(d,'REAL PLAYBACK',996,636,14,(160,132,80))
    subtitle(f,'同一裁切，唯一变量是时间')
    return f

STRIP=None
def strip_img():
    global STRIP
    if STRIP is not None: return STRIP
    tw,th,gap=400,66,12
    total=12*tw+11*gap
    im=Image.new('RGB',(total,120),(7,9,13))
    d=ImageDraw.Draw(im)
    for i in range(12):
        p=bframe(9.25+i*0.25).resize((tw,th),Image.Resampling.LANCZOS)
        x=i*(tw+gap)
        im.paste(p,(x,0))
        d.rectangle([x,0,x+tw-1,th-1],outline=(72,60,40))
        d.text((x+4,th+7),f'{i*0.25:.2f}',font=F(FONT_MONO,13),fill=(150,126,82))
    STRIP=im
    return im

def s5(t):
    f=base()
    top_labels(f,'05 / FRAME BY FRAME','0.25 s / FRAME')
    grad_title(f,'一个周期，12 帧',96,148,56)
    d=ImageDraw.Draw(f)
    d.text((98,226),'全部来自真实录屏，按 0.25 秒取样',font=F(FONT_HIRAGINO,25,0),fill=(176,170,158))
    strip=strip_img()
    x=int(660-600*(t-31.0))
    f.paste(strip,(x,460))
    idx=int((960-x)/(400+12))
    idx=clamp(idx,0,11)
    # playhead
    d.line([(960,438),(960,600)],fill=(216,181,106),width=1)
    d.polygon([(952,438),(968,438),(960,450)],fill=(216,181,106))
    label(d,f'FRAME  {idx:02d} / 12',1600,398,18,(196,160,96),anchor='ra')
    label(d,f'T + {idx*0.25:.2f} s',1600,428,18,(160,132,80),anchor='ra')
    d.line([(100,640),(1820,640)],fill=(58,50,36),width=1)
    label(d,'ONE CYCLE / 3.000 s',100,652,15,(140,116,76))
    label(d,'0.25 s GRID / REAL CAPTURE',1820,652,15,(140,116,76),anchor='ra')
    subtitle(f,'从进入到离开，光带扫过')
    return f

def s6(t):
    f=base()
    top_labels(f,'06 / INSTALL','v0.4.16')
    grad_title(f,'一条命令。',96,166,80)
    d=ImageDraw.Draw(f)
    d.text((98,304),'在 DeepSeek Harness 桌面端安装',font=F(FONT_HIRAGINO,28,0),fill=(190,184,172))
    box=[96,416,1216,520]
    d.rounded_rectangle(box,radius=10,fill=(12,15,20),outline=(84,70,42),width=1)
    cmd='dsh plugin --profile desktop add dsh-logo-golden'
    fs=fit_mono(cmd,1020,28)
    fm=F(FONT_MONO,fs)
    n=int(clamp((t-38.3)*30,0,len(cmd)))
    shown=cmd[:n]
    d.text((130,452),'$',font=fm,fill=(216,181,106))
    d.text((162,452),shown,font=fm,fill=(238,234,226))
    cw=d.textlength(shown,font=fm)
    if n<len(cmd) or (t*2)%1<0.5:
        d.rectangle([162+cw+3,454,162+cw+15,486],fill=(200,166,100))
    label(d,'README / INSTALL',96,552,18,(160,132,80))
    d.text((96,600),'github.com/devzer0o0/dsh-logo-golden',font=F(FONT_MONO,26),fill=(220,196,150))
    d.text((96,648),'v0.4.16  ·  Apache-2.0  ·  开源',font=F(FONT_HIRAGINO,20,0),fill=(150,144,132))
    d.line([(1300,416),(1300,672)],fill=(62,54,40),width=1)
    label(d,'SPEC',1360,416,14,(180,148,90))
    rows=[('PACKAGE','dsh-logo-golden'),('VERSION','0.4.16'),('LICENSE','Apache-2.0'),('PROFILE','desktop')]
    for i,(k,v) in enumerate(rows):
        y=458+i*54
        label(d,k,1360,y,13,(150,138,112))
        d.text((1360,y+20),v,font=F(FONT_MONO,20),fill=(218,210,196))
    subtitle(f,'README 安装命令 · 与当前版本核对')
    return f

def s7(t):
    f=base()
    top_labels(f,'07 / IN THE HOST','LIVE')
    grad_title(f,'它就在侧栏里。',96,168,58)
    d=ImageDraw.Draw(f)
    d.text((98,276),'不打开额外窗口，也不遮挡对话。',font=F(FONT_HIRAGINO,26,0),fill=(190,184,172))
    label(d,'DETAILS',98,352,14,(150,124,80))
    items=['真实 DOM / 真实宿主','WebGPU overlay / 3.000 s 周期','无 WebGPU 时静态金回退']
    for i,s in enumerate(items):
        y=400+i*60
        d.ellipse([98,y+10,105,y+17],fill=(196,158,92))
        d.text((122,y),s,font=F(FONT_HIRAGINO,25,0),fill=(188,182,170))
    d.line([(98,640),(150,640)],fill=(150,124,76),width=1)
    d.text((98,666),'光在品牌上走，界面不动。',font=F(FONT_HIRAGINO,25,0),fill=(198,162,98))
    p=panel_exact(hframe(15.3+(t-45.0)),780,572,pad=14,radius=14)
    place_panel(f,p,1000,258)
    d.ellipse([1024,228,1036,240],fill=(214,178,106))
    label(d,'LIVE',1046,220,18)
    subtitle(f,'每 3.000 秒，扫过一次')
    return f

def s8(t):
    f=base()
    top_labels(f,'08 / ONE MORE','0.5×')
    lt=t-51.5
    p=panel(bframe(18.35+lt*0.5),1180)
    place_panel(f,p,370,258)
    grad_title(f,'给终端，一点金色。',960,566,64,center=True)
    d=ImageDraw.Draw(f)
    d.text((960,656),'dsh-logo-golden',font=F(FONT_MONO,26),fill=(198,162,98),anchor='ma')
    subtitle(f,'一个周期，3.000 秒')
    if lt<0.4: f=fade(f,1-lt/0.4)
    return f

def s9(t):
    f=base()
    top_labels(f,'DSH / LOGO GOLDEN','THANK YOU')
    p=panel(bframe(19.8),820)
    place_panel(f,p,550,210)
    d=ImageDraw.Draw(f)
    d.text((960,455),'dsh-logo-golden',font=F(FONT_HELV,52,1),fill=(244,241,234),anchor='ma')
    d.text((960,517),'DeepSeek Harness 品牌插件',font=F(FONT_HIRAGINO,24,0),fill=(198,162,98),anchor='ma')
    box=[460,590,1460,674]
    d.rounded_rectangle(box,radius=8,fill=(12,15,20),outline=(84,70,42),width=1)
    cmd='dsh plugin --profile desktop add dsh-logo-golden'
    fs=fit_mono(cmd,900,26)
    d.text((490,614),'$',font=F(FONT_MONO,fs),fill=(216,181,106))
    d.text((516,614),cmd,font=F(FONT_MONO,fs),fill=(238,234,226))
    d.text((960,728),'github.com/devzer0o0/dsh-logo-golden',font=F(FONT_MONO,24),fill=(220,196,150),anchor='ma')
    d.text((960,778),'v0.4.16  ·  Apache-2.0  ·  原创配乐',font=F(FONT_HIRAGINO,18,0),fill=(150,144,132),anchor='ma')
    d.text((960,824),'真实录屏  ·  AI 辅助脚本与剪辑',font=F(FONT_HIRAGINO,17,0),fill=(110,104,94),anchor='ma')
    if t>66.2: f=fade(f,(t-66.2)/0.8)
    return f

def render(t):
    if t<3.4: f=s0(t)
    elif t<9.2: f=s1(t)
    elif t<16.0: f=s2(t)
    elif t<24.0: f=s3(t)
    elif t<31.0: f=s4(t)
    elif t<38.0: f=s5(t)
    elif t<45.0: f=s6(t)
    elif t<51.5: f=s7(t)
    elif t<58.0: f=s8(t)
    else: f=s9(t)
    return grain_frame(f,int(t*30))

if __name__=='__main__':
    ap=argparse.ArgumentParser()
    ap.add_argument('--still',type=float)
    ap.add_argument('--out',default='build/still.png')
    ap.add_argument('--render',action='store_true')
    ap.add_argument('--from',dest='t0',type=float,default=0)
    ap.add_argument('--to',dest='t1',type=float,default=DUR)
    ap.add_argument('--video',default='build/video-noaudio.mp4')
    a=ap.parse_args()
    if a.still is not None:
        t=time.time(); im=render(a.still); im.save(a.out); print('saved',a.out,'in',round(time.time()-t,2),'s')
    elif a.render:
        n0=int(round(a.t0*W_FPS)); n1=int(round(a.t1*W_FPS))
        cmd=['ffmpeg','-y','-hide_banner','-loglevel','error','-f','rawvideo','-pix_fmt','rgb24','-s',f'{W}x{H}','-r',str(W_FPS),'-i','-',
             '-c:v','libx264','-preset','medium','-crf','16','-pix_fmt','yuv420p','-profile:v','high','-level','4.1',
             '-color_primaries','bt709','-color_trc','bt709','-colorspace','bt709','-movflags','+faststart',a.video]
        p=subprocess.Popen(cmd,stdin=subprocess.PIPE)
        t0=time.time()
        for n in range(n0,n1):
            fr=render(n/W_FPS)
            p.stdin.write(fr.tobytes())
            if (n-n0)%60==0: print(n-n0,'/',n1-n0,round(time.time()-t0,1),'s',flush=True)
        p.stdin.close(); p.wait()
        print('done',a.video,round(time.time()-t0,1),'s')
