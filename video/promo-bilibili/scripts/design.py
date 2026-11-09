from PIL import Image, ImageDraw, ImageFont, ImageFilter, ImageChops, ImageEnhance
import numpy as np, os, functools

W,H=1920,1080
BASE=os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
FONT_HIRAGINO='/System/Library/Fonts/Hiragino Sans GB.ttc'
FONT_SONGTI='/System/Library/Fonts/Supplemental/Songti.ttc'
FONT_HELV='/System/Library/Fonts/HelveticaNeue.ttc'
FONT_MONO='/System/Library/Fonts/SFNSMono.ttf'
GOLD=(216,181,106); GOLD_BRIGHT=(244,216,150); GOLD_DEEP=(138,100,42)
INK=(8,10,14); PAPER=(244,241,234); MUTED=(168,162,150); DIM=(120,114,104)
M=48  # panel shadow margin

_fonts={}
def F(path,size,index=0):
    k=(path,size,index)
    if k not in _fonts: _fonts[k]=ImageFont.truetype(path,size,index=index)
    return _fonts[k]

def clamp(v,a,b): return max(a,min(b,v))
def smooth(v): return v*v*(3-2*v)

def gradient(w,h,top,bottom):
    a=np.zeros((h,w,3),np.uint8)
    for i in range(3):
        a[:,:,i]=np.linspace(top[i],bottom[i],h,dtype=np.uint8)[:,None]
    return Image.fromarray(a,'RGB')

def radial_glow(w,h,cx,cy,sigma,color,peak):
    yy,xx=np.mgrid[0:h,0:w]
    d=((xx-cx)**2+(yy-cy)**2)/(2*sigma*sigma)
    a=np.exp(-d)*peak
    layer=np.zeros((h,w,4),np.uint8)
    layer[:,:,:3]=color
    layer[:,:,3]=np.clip(a,0,255).astype(np.uint8)
    return Image.fromarray(layer,'RGBA')

@functools.lru_cache(maxsize=1)
def make_bg():
    bg=gradient(W,H,(12,15,21),(4,5,8)).convert('RGBA')
    bg=Image.alpha_composite(bg,radial_glow(W,H,960,430,560,(196,150,76),30))
    bg=Image.alpha_composite(bg,radial_glow(W,H,300,880,480,(120,90,45),14))
    d=ImageDraw.Draw(bg)
    d.line([(80,96),(1840,96)],fill=(205,168,100,34),width=1)
    d.line([(80,96),(80,116)],fill=(205,168,100,50),width=1)
    d.line([(1840,96),(1840,116)],fill=(205,168,100,50),width=1)
    yy,xx=np.mgrid[0:H,0:W]
    rr=np.sqrt(((xx-W/2)/(W*0.64))**2+((yy-H/2)/(H*0.64))**2)
    v=np.clip(1.0-0.60*np.clip(rr-0.30,0,1)**1.5,0,1)
    vimg=Image.fromarray((v*255).astype(np.uint8),'L').convert('RGB')
    bg=ImageChops.multiply(bg.convert('RGB'),vimg).convert('RGBA')
    return bg.convert('RGB')

def rounded_mask(size,radius,feather=0):
    w,h=size
    m=Image.new('L',(w,h),0)
    d=ImageDraw.Draw(m)
    d.rounded_rectangle([0,0,w-1,h-1],radius=radius,fill=255)
    if feather: m=m.filter(ImageFilter.GaussianBlur(feather))
    return m

@functools.lru_cache(maxsize=24)
def panel_canvas(w,h,pad,radius=16):
    cw,ch=w+2*pad+2*M,h+2*pad+2*M
    canvas=Image.new('RGBA',(cw,ch),(0,0,0,0))
    sh=Image.new('RGBA',(cw,ch),(0,0,0,0))
    d=ImageDraw.Draw(sh)
    d.rounded_rectangle([M+4,M+18,M+4+w+2*pad,M+18+h+2*pad],radius=radius+2,fill=(0,0,0,150))
    sh=sh.filter(ImageFilter.GaussianBlur(26))
    canvas=Image.alpha_composite(canvas,sh)
    glow=Image.new('RGBA',(cw,ch),(0,0,0,0))
    gd=ImageDraw.Draw(glow)
    gd.rounded_rectangle([M-2,M-2,M+w+2*pad+2,M+h+2*pad+2],radius=radius+4,fill=(214,176,104,30))
    glow=glow.filter(ImageFilter.GaussianBlur(30))
    canvas=Image.alpha_composite(canvas,glow)
    d=ImageDraw.Draw(canvas)
    d.rounded_rectangle([M,M,M+w+2*pad,M+h+2*pad],radius=radius,fill=(10,13,18,250))
    d.rounded_rectangle([M,M,M+w+2*pad,M+h+2*pad],radius=radius,outline=(216,181,106,58),width=1)
    return canvas,(M+pad,M+pad)

def panel(patch,width,pad=18,radius=16,sharpen=True):
    h=round(width*66/400)
    canvas,pos=panel_canvas(width,h,pad,radius)
    im=canvas.copy()
    p=patch.resize((width,h),Image.Resampling.LANCZOS)
    if sharpen: p=p.filter(ImageFilter.UnsharpMask(radius=2,percent=80,threshold=2))
    m=rounded_mask((width,h),10,0)
    im.paste(p,pos,m)
    d=ImageDraw.Draw(im)
    d.rounded_rectangle([pos[0],pos[1],pos[0]+width-1,pos[1]+h-1],radius=10,outline=(255,255,255,22),width=1)
    return im

def panel_exact(patch,w,h,pad=12,radius=12):
    canvas,pos=panel_canvas(w,h,pad,radius)
    im=canvas.copy()
    p=patch.resize((w,h),Image.Resampling.LANCZOS)
    im.paste(p,pos,rounded_mask((w,h),8,0))
    d=ImageDraw.Draw(im)
    d.rounded_rectangle([pos[0],pos[1],pos[0]+w-1,pos[1]+h-1],radius=8,outline=(255,255,255,22),width=1)
    return im

def place_panel(frame,im,X,Y):
    # X,Y = outer frame top-left
    frame.paste(im,(X-M,Y-M),im)

@functools.lru_cache(maxsize=1)
def bottom_gradient():
    g=Image.new('RGBA',(W,240),(0,0,0,0))
    a=np.linspace(0,150,240,dtype=np.uint8)
    arr=np.zeros((240,W,4),np.uint8)
    arr[:,:,:3]=0
    arr[:,:,3]=a[:,None]
    g=Image.fromarray(arr,'RGBA')
    return g

def tracked(draw,xy,text,font,fill,tracking=0,anchor='la'):
    widths=[draw.textlength(ch,font=font) for ch in text]
    total=sum(widths)+tracking*max(0,len(text)-1)
    x,y=xy
    if anchor[0]=='m': x-=total/2
    elif anchor[0]=='r': x-=total
    for ch,w in zip(text,widths):
        draw.text((x,y),ch,font=font,fill=fill,anchor='l'+anchor[1])
        x+=w+tracking
    return total

@functools.lru_cache(maxsize=64)
def text_gradient(text,size,index=0,tracking=2,pad=24,top=(250,226,170),bottom=(178,132,58)):
    font=F(FONT_SONGTI,size,index)
    tmp=Image.new('L',(10,10)); td=ImageDraw.Draw(tmp)
    widths=[td.textlength(ch,font=font) for ch in text]
    tw=int(sum(widths)+tracking*max(0,len(text)-1)); th=int(size*1.45)
    mask=Image.new('L',(tw+pad*2,th+pad*2),0)
    md=ImageDraw.Draw(mask)
    x=pad
    for ch,wd in zip(text,widths):
        md.text((x,pad),ch,font=font,fill=255,anchor='la')
        x+=wd+tracking
    grad=gradient(mask.width,mask.height,top,bottom)
    out=Image.new('RGBA',mask.size,(0,0,0,0))
    out.paste(grad,(0,0),mask)
    return out

def paste_grad(frame,layer,x,y):
    frame.paste(layer,(int(x),int(y)),layer)

def label(d,text,x,y,size=20,color=(201,164,94),tracking=3,anchor='la',font=None):
    f=font or F(FONT_MONO,size)
    return tracked(d,(x,y),text,f,color,tracking,anchor)

def body(d,text,x,y,size=30,color=MUTED,font_index=0,line=1.55,anchor='la',maxwidth=None):
    f=F(FONT_HIRAGINO,size,font_index)
    lines=text.split('\n')
    yy=y
    for ln in lines:
        d.text((x,yy),ln,font=f,fill=color,anchor=anchor)
        yy+=int(size*line)
    return yy

def subtitle(frame,text,size=40,y=986):
    bg=bottom_gradient()
    frame.paste(bg,(0,H-240),bg)
    f=F(FONT_HIRAGINO,size,2)
    d=ImageDraw.Draw(frame)
    # shadow
    d.text((W/2+2,y+3),text,font=f,fill=(0,0,0),anchor='ma')
    d.text((W/2,y),text,font=f,fill=(246,243,236),anchor='ma')

def grade(p):
    return ImageEnhance.Color(ImageEnhance.Brightness(p).enhance(0.86)).enhance(0.90)

def fade(frame,k):
    if k<=0: return frame
    return Image.blend(frame,Image.new('RGB',(W,H),(0,0,0)),min(1,k))

def grain_frame(frame,idx):
    arr=np.asarray(frame,dtype=np.int16)
    n=GRAIN[idx%len(GRAIN)]
    arr=np.clip(arr+n[:,:,None],0,255).astype(np.uint8)
    return Image.fromarray(arr,'RGB')

_rng=np.random.default_rng(7)
GRAIN=[_rng.normal(0,3.0,(H,W)).astype(np.int16) for _ in range(4)]
