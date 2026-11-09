#!/usr/bin/env python3
"""Original ambient score for the dsh-logo-golden promo (no external samples)."""
import wave, struct
import numpy as np

SR=48000
DUR=67.0
N=int(SR*DUR)
rng=np.random.default_rng(20261108)

NOTE={
 'Bb1':58.270,'C2':65.406,'D2':73.416,'F2':87.307,'G2':98.000,
 'A2':110.000,'Bb2':116.541,'C3':130.813,'D3':146.832,'E3':164.814,
 'F3':174.614,'G3':196.000,'A3':220.000,'Bb3':233.082,'C4':261.626,
 'D4':293.665,'F4':349.228,'A4':440.000,'C5':523.251,'D5':587.330,
 'F5':698.456,'A5':880.000,'C6':1046.502,'D6':1174.659,
}

def t_axis(n): return np.arange(n,dtype=np.float64)/SR

def pane(n):
    return np.zeros((n,2),dtype=np.float64)

def add(dst, src, at):
    i=int(round(at*SR))
    if i>=len(dst): return
    m=min(len(src),len(dst)-i)
    dst[i:i+m]+=src[:m]

def pad_chord(start,end,names,amp=0.055):
    dur=max(0.1,end-start)
    n=int((dur+1.6)*SR)
    t=t_axis(n)
    a=np.clip(t/1.15,0,1)
    r=np.clip((dur+1.5-t)/1.5,0,1)
    env=a*r
    # slow breathing
    env*=1.0+0.07*np.sin(2*np.pi*0.061*t+0.4)
    out=pane(n)
    for j,name in enumerate(names):
        f=NOTE[name]
        det=1.0+(j-2)*0.00055
        ph=2*np.pi*f*det*t+0.55*j
        sub=0.20*np.sin(ph/2+0.3)
        tone=np.sin(ph)+0.26*np.sin(2*ph+0.4)+0.10*np.sin(3*ph+0.9)
        tone=(tone+sub)*env*amp
        # stereo spread: low notes near centre, upper notes wider
        pan=0.5+0.28*np.sin(0.9*j+0.7)
        out[:,0]+=tone*(1.0-pan)*1.35
        out[:,1]+=tone*pan*1.35
    # gentle low-pass by averaging (removes fizz above ~8k)
    out[1:]=(out[1:]*0.82+out[:-1]*0.18)
    return out

def bell(at,f,amp=0.09,decay=0.75,pan=0.5):
    n=int(2.8*SR); t=t_axis(n)
    env=np.exp(-t/decay)*(1-np.exp(-t/0.008))
    mod=1.9*np.exp(-t/0.22)*np.sin(2*np.pi*f*2.005*t+0.2)
    x=np.sin(2*np.pi*f*t+mod)*env*amp
    x+=0.35*np.sin(2*np.pi*f*3.01*t)*np.exp(-t/(decay*0.5))*amp
    out=pane(n)
    out[:,0]+=x*(1-pan)*1.4
    out[:,1]+=x*pan*1.4
    add(MASTER,out,at)

def glass(at,f,amp=0.018,pan=0.5,decay=1.35):
    n=int(2.2*SR); t=t_axis(n)
    env=np.exp(-t/decay)*(1-np.exp(-t/0.012))
    mod=0.9*np.exp(-t/0.28)*np.sin(2*np.pi*f*2.002*t)
    x=np.sin(2*np.pi*f*t+mod)*env*amp
    out=pane(n)
    out[:,0]+=x*(1-pan)*1.35
    out[:,1]+=x*pan*1.35
    add(MASTER,out,at)

def pulse(at,amp=0.075,f0=58.0):
    n=int(0.8*SR); t=t_axis(n)
    f=f0*np.exp(-t*5.5)+36.0
    ph=2*np.pi*np.cumsum(f)/SR
    env=np.exp(-t/0.20)*(1-np.exp(-t/0.006))
    x=np.sin(ph)*env*amp
    out=pane(n)
    out[:,0]+=x; out[:,1]+=x*0.96
    add(MASTER,out,at)

def tick(at,amp=0.0055,pan=0.5):
    n=int(0.09*SR); t=t_axis(n)
    env=np.exp(-t/0.026)*(1-np.exp(-t/0.004))
    x=np.sin(2*np.pi*880*t)*env*amp
    x[1:]=x[1:]*0.72+x[:-1]*0.28
    out=pane(n)
    out[:,0]+=x*(1-pan)*1.2
    out[:,1]+=x*pan*1.2
    add(MASTER,out,at)

MASTER=pane(N)

# --- harmony: one chord per scene, overlapping the change -----------------
CH=[
 (0.0,   9.2,  ['D2','A2','D3','F3','A3'],0.044),
 (8.7,  16.0,  ['Bb1','F2','Bb2','D3','F3'],0.052),
 (15.5, 24.0,  ['F2','C3','F3','A3','C4'],0.048),
 (23.5, 31.0,  ['C2','G2','C3','E3','G3'],0.050),
 (30.5, 38.0,  ['G2','D3','G3','Bb3','D4'],0.044),
 (37.5, 45.0,  ['D2','A2','D3','F3','A3'],0.048),
 (44.5, 51.5,  ['Bb1','F2','Bb2','D3','F3'],0.052),
 (51.0, 58.0,  ['F2','C3','F3','A3','C4'],0.064),
 (57.5, 67.0,  ['D2','A2','D3','F3','A3'],0.056),
]
for a,b,names,amp in CH:
    add(MASTER,pad_chord(a,b,names,amp),a)

# --- sparse glass arpeggio: midrange movement for phone speakers ----------
for i,(at,name) in enumerate([(9.35,'D4'),(10.55,'A4'),(11.75,'F4'),(12.95,'D4'),(14.15,'A4'),(15.35,'F4')]):
    glass(at,NOTE[name],amp=0.016,pan=0.38 if i%2 else 0.62)
for i,(at,name) in enumerate([(51.7,'F4'),(52.9,'A4'),(54.1,'C5' if 'C5' in NOTE else 'C6'),(55.3,'F4'),(56.5,'A4')]):
    glass(at,NOTE[name],amp=0.018,pan=0.32 if i%2 else 0.68)
for i,(at,name) in enumerate([(58.2,'D4'),(60.4,'F4'),(62.6,'A4')]):
    glass(at,NOTE[name],amp=0.015,pan=0.42 if i%2 else 0.58)

# --- scene bells and low pulses -------------------------------------------
for at,f in [(9.2,'D5'),(16.0,'F5'),(31.0,'C6'),(51.5,'A5'),(58.0,'D6')]:
    bell(at,NOTE[f],amp=0.075,decay=0.85,pan=0.5)
for at in [0.35,3.45,9.45,12.45,15.45,24.0,31.0,38.0,45.0,51.5,58.0]:
    pulse(at,amp=0.075 if at not in (3.45,9.45,12.45) else 0.095)
# soft 0.25 s frame ticks through the filmstrip
for i in range(28):
    tick(31.0+i*0.25,amp=0.010,pan=0.35 if i%2 else 0.65)

# --- wide stereo taps (short, no feedback) --------------------------------
def wide(x, taps):
    y=x.copy()
    for d,g,cross in taps:
        k=int(d*SR)
        if k<=0: continue
        y[k:,0]+=g*(x[:-k,0]*(1-cross)+x[:-k,1]*cross)
        y[k:,1]+=g*(x[:-k,1]*(1-cross)+x[:-k,0]*cross)
    return y

MASTER=wide(MASTER,[(0.113,0.16,0.30),(0.197,0.11,0.30),(0.293,0.07,0.35),(0.419,0.045,0.35)])

# --- section dynamics: let the picture breathe ----------------------------
t=t_axis(N)
mark_t=[0.0,3.4,9.2,16.0,24.0,31.0,38.0,45.0,51.5,58.0,63.0,67.0]
mark_g=[0.58,0.74,1.00,0.84,0.96,0.74,0.82,0.86,1.00,0.92,0.86,0.86]
MASTER*=np.interp(t,mark_t,mark_g)[:,None]

# --- fades, soft limit, normalise ----------------------------------------
fade_in=np.clip(t/1.2,0,1)
fade_out=np.clip((DUR-t)/4.0,0,1)
MASTER*=fade_in[:,None]*fade_out[:,None]
MASTER=np.tanh(MASTER*1.15)
peak=float(np.max(np.abs(MASTER)))
MASTER*=0.70/peak
rms=float(np.sqrt(np.mean(MASTER**2)))
print('peak',round(float(np.max(np.abs(MASTER))),3),'rms',round(rms,4),'dbfs',round(20*np.log10(rms),1))

pcm=np.clip(MASTER*32767.0,-32768,32767).astype('<i2')
with wave.open('build/music.wav','wb') as w:
    w.setnchannels(2); w.setsampwidth(2); w.setframerate(SR)
    w.writeframes(pcm.tobytes())
print('wrote build/music.wav',pcm.shape)
