"""Calibrate a NESS brass instrument for a melody and tune the melody by iteration.

usage: python tune.py <exe> <instrument> <workdir> <key: Bb|Eb> <iterations>
"""
import json, sys, os, subprocess, numpy as np
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from brasslib import write_score, f0
from scipy.io import wavfile

NOTE_HZ = {'F4':349.23,'G4':392.00,'A4':440.00,'Bb4':466.16,'C5':523.25,'D5':587.33,
           'Eb5':622.25,'F5':698.46,'G5':783.99,'Ab5':830.61,'Bb5':932.33}
# candidate fingerings per note, standard trumpet fingering first
CANDS = {'F4':['0'],'G4':['12','13','23'],'A4':['2'],'Bb4':['0'],'C5':['1'],'D5':['12','0'],
         'Eb5':['1','23'],'F5':['0','1'],'G5':['12','0'],'Ab5':['1','23'],'Bb5':['0']}

def tune_for(key):
    # Happy Birthday (traditional). Scale degrees: 5 5 6 5 1' 7 | 5 5 6 5 2' 1' | 5 5 5' 3' 1' 7 6 | 4' 4' 3' 1' 2' 1'
    deg = {'Bb': dict(s5='F4',s6='G4',s7='A4',s1='Bb4',s2='C5',s3='D5',s4='Eb5',s5h='F5'),
           'Eb': dict(s5='Bb4',s6='C5',s7='D5',s1='Eb5',s2='F5',s3='G5',s4='Ab5',s5h='Bb5')}[key]
    d = lambda k: deg[k]
    return [(d('s5'),.75),(d('s5'),.25),(d('s6'),1),(d('s5'),1),(d('s1'),1),(d('s7'),2,'br'),
            (d('s5'),.75),(d('s5'),.25),(d('s6'),1),(d('s5'),1),(d('s2'),1),(d('s1'),2,'br'),
            (d('s5'),.75),(d('s5'),.25),(d('s5h'),1),(d('s3'),1),(d('s1'),1),(d('s7'),1),(d('s6'),1.6,'br'),
            (d('s4'),.75),(d('s4'),.25),(d('s3'),1),(d('s1'),1),(d('s2'),1),(d('s1'),3,'end')]

BEAT = 0.6; TONGUE = 0.035; BREATH = 0.16

def render(exe, inst, score, out):
    r = subprocess.run([exe,'-i',inst,'-s',score,'-o',out], capture_output=True, text=True)
    if r.returncode != 0: raise RuntimeError(r.stdout + r.stderr)
    sr, x = wavfile.read(out + '.wav'); return sr, x.astype(float)/32768

def settle_ms(x, sr, s, e, ref):
    tr = []; d = 0.005
    while s + d + 0.025 <= e:
        f,_ = f0(x, sr, s+d, s+d+0.025); tr.append(1200*np.log2(max(f,1)/ref)); d += 0.01
    return next((5+10*i for i in range(len(tr)) if all(abs(v) < 20 for v in tr[i:])), 999)

def calibrate(exe, inst, names):
    notes=[]; plan=[]; t=0.2
    for nm in names:
        for v in CANDS[nm]:
            for r in np.arange(0.82, 1.045, 0.01):
                lip = NOTE_HZ[nm]*r
                notes.append(dict(start=t, dur=0.4, valves=v, lip=lip, p=3e3)); plan.append((nm,v,lip,t)); t += 0.5
    write_score('score_cal.m', notes, t+0.1, 'calibration sweep')
    sr, x = render(exe, inst, 'score_cal.m', 'cal')
    data = {}
    for nm,v,lip,t0 in plan:
        fin,_ = f0(x, sr, t0+0.25, t0+0.38)
        rms = np.sqrt((x[int((t0+.25)*sr):int((t0+.38)*sr)]**2).mean())
        c = 1200*np.log2(max(fin,1)/NOTE_HZ[nm])
        st = settle_ms(x, sr, t0, t0+0.38, max(fin,1)) if rms > 0.01 else 999
        data.setdefault((nm,v), []).append((lip, c, st))
    fing = {}
    for nm in names:
        best = None
        for rank, v in enumerate(CANDS[nm]):
            pts = data[(nm,v)]
            for (l1,c1,s1),(l2,c2,s2) in zip(pts, pts[1:]):
                # bracket 0 cents, both points stable and close to pitch, monotonic
                if c1 <= 0 <= c2 and c2 - c1 < 30 and max(s1,s2) < 999:
                    lip = l1 + (l2-l1)*(-c1)/(c2-c1)
                    slope = (c2-c1)/(100*(l2-l1)/l1)          # cents per 1% lip
                    score = (max(s1,s2), rank)
                    if best is None or score < best[0]: best = (score, v, lip, slope)
        if best is None: raise RuntimeError(f'no in-tune setting found for {nm}')
        (st, rank), v, lip, slope = best
        fing[nm] = (v, lip, slope)
        print(f'  {nm:4s} valves {v:3s} lip {lip:6.1f} Hz ({lip/NOTE_HZ[nm]:.2f}x)  settles ~{st} ms  slope {slope:.1f} c/%', flush=True)
    return fing

def build(tune, fing, lips):
    notes=[]; t=0.15
    for i,item in enumerate(tune):
        nm, beats = item[0], item[1]; tag = item[2] if len(item) > 2 else ''
        span = beats*BEAT; dur = span if tag == 'end' else span - (BREATH if tag == 'br' else TONGUE)
        hi = NOTE_HZ[nm] >= NOTE_HZ[tune[14][0]]                    # climax register
        n = dict(start=t, dur=dur, valves=fing[nm][0], lip=lips[i], p=3500.0 if hi else 3000.0, name=nm)
        if tag == 'end': n['p_end'] = 1400.0
        notes.append(n); t += span
    return notes, t + 0.5

def measure(x, sr, notes):
    out=[]; st=[]
    for n in notes:
        s, e = n['start'], n['start']+n['dur']
        a = s + min(0.06, 0.3*n['dur']); b = e - min(0.06, 0.15*n['dur'])
        f,_ = f0(x, sr, a, b); out.append(1200*np.log2(max(f,1)/NOTE_HZ[n['name']]))
        st.append(settle_ms(x, sr, s, e, NOTE_HZ[n['name']]))
    return np.array(out), st

if __name__ == '__main__':
    exe, inst, wd, key, iters = sys.argv[1], os.path.abspath(sys.argv[2]), sys.argv[3], sys.argv[4], int(sys.argv[5])
    os.makedirs(wd, exist_ok=True); os.chdir(wd)
    tune = tune_for(key); names = sorted({n[0] for n in tune}, key=lambda n: NOTE_HZ[n])
    print('calibrating', ', '.join(names))
    fing = calibrate(exe, inst, names)
    lips = [fing[it[0]][1] for it in tune]
    for k in range(iters+1):
        notes, T = build(tune, fing, lips)
        write_score('score.m', notes, T, f'Happy Birthday (traditional), trumpet in concert {key}',
                    vib=(0.008, 5.2), vibrato_delay=0.3)
        sr, x = render(exe, inst, 'score.m', 'melody')
        c, st = measure(x, sr, notes)
        print(f'pass {k}: max |err| {np.abs(c).max():5.1f} c, mean {np.abs(c).mean():4.1f} c; slowest settle {max(st)} ms :: '
              + ' '.join(f"{n['name']}{e:+.0f}" for n,e in zip(notes,c)), flush=True)
        if k == iters: break
        for i,e in enumerate(c):
            # Short notes are mostly attack transient, which starts sharp on every
            # note; "correcting" that average would lower the lip and lengthen the
            # transient. Keep them at the calibrated lip and only correct long notes.
            if notes[i]['dur'] < 0.2: continue
            lips[i] *= 1 + np.clip(-0.8*e/fing[tune[i][0]][2], -4, 4)/100
    json.dump(dict(fing={k:list(v) for k,v in fing.items()}, lips=lips, settle=st, cents=list(c)), open('result.json','w'))
    words = 'Hap py birth day to you Hap py birth day to you Hap py birth day dear na- me Hap py birth day to you'.split()
    print('settle per note: ' + ' '.join(f'{w}/{n["name"]}:{s}' for w,n,s in zip(words, notes, st)))
