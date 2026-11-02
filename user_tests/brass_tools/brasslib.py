"""Write NESS brass score files from a list of notes, with step-wise controls."""
import numpy as np
LIP_DEFAULTS = {"Sr": 1.46e-5, "mu": 5.37e-5, "sigma": 10.0, "H": 0.00029, "w": 0.01}
VALVES = {'0':(1,1,1),'2':(1,0,1),'1':(0,1,1),'12':(0,0,1),'23':(1,0,0),'13':(0,1,0),'123':(0,0,0)}

def write_score(path, notes, T, title='brass score', vib=(0.0,5.0), valve_time=0.012,
                attack=0.002, release=0.02, maxout=0.95, noise=0.0, vibrato_delay=None):
    """notes: list of dicts with start, dur, valves, lip, p (Pa). Each note: pressure
    attack ramp, hold, release ramp to 0 at start+dur. Lips/valves change in the gap
    before the note (or at the note start if there is no gap)."""
    P=[[0,0]]; LF=[]; V=[]; VA=[[0,0]]; floor_prev=0.0
    for i,n in enumerate(notes):
        s, e = n['start'], n['start']+n['dur']
        prev_end = notes[i-1]['start']+notes[i-1]['dur'] if i else 0.0
        tc = max(prev_end - 0.002, s - 0.03) if i else max(0.0, s-0.03)  # change point
        v = VALVES[n['valves']]
        if LF:
            LF.append([tc-0.001, LF[-1][1]]); V.append([tc-valve_time, *V[-1][1:]])
        lip0 = n.get('lip0', n['lip'])
        LF.append([tc, lip0]); V.append([tc, *v])
        if 'lip0' in n:                      # glide lips from lip0 to lip at the attack
            LF += [[s, lip0], [s+n['glide'], n['lip']]]
        att = n.get('attack', attack); floor = n.get('floor', 0.0)
        P += [[s,floor_prev],[s+att,n['p']],[e-release,n.get('p_end',n['p'])],[e,floor]]
        floor_prev = floor
        if vibrato_delay is not None and n['dur'] > 2*vibrato_delay:
            VA += [[s,0],[s+vibrato_delay,0],[e,vib[0]],[e+0.001,0]]
    def arr(name, rows):
        rows = sorted(rows, key=lambda r: r[0])
        return name+'=[' + ';\n'.join(','.join(f'{x:.7g}' for x in r) for r in rows) + '];\n'
    s = f'% {title}\n'
    s += f'maxout={maxout};\nT={T:.4g};\n'
    # lip (embouchure) parameters: default values, optionally overridden per note
    # as a multiplier (e.g. note['H'] = 0.6). They change in the gap before a note.
    for k, dv in LIP_DEFAULTS.items():
        if not any(k in n for n in notes):
            s += f'{k}=[0,{dv:g}];\n'; continue
        rows = []; cur = None
        for i, n in enumerate(notes):
            val = dv * n.get(k, 1.0)
            prev_end = notes[i-1]['start']+notes[i-1]['dur'] if i else 0.0
            tc = max(prev_end + 0.003, n['start'] - 0.02) if i else 0.0
            if cur is None: rows.append([0.0, val])
            elif val != cur: rows += [[tc - 0.008, cur], [tc, val]]   # 8 ms embouchure change
            cur = val
        s += arr(k, rows)
    s += arr('lip_frequency', LF) + arr('pressure', P)
    s += arr('vibamp', VA) if vibrato_delay is not None else f'vibamp=[0,{vib[0]}];\n'
    s += f'vibfreq=[0,{vib[1]}];\ntremamp=[0,0];\ntremfreq=[0,0];\nnoiseamp=[0,{noise}];\n'
    s += arr('valveopening', V) + 'valvevibfreq=[0,0,0,0];\nvalvevibamp=[0,0,0,0];\n'
    open(path,'w').write(s)

def f0(x, sr, a, b):
    seg = x[int(a*sr):int(b*sr)]; seg = seg-seg.mean(); n=len(seg)
    r = np.fft.irfft(np.abs(np.fft.rfft(seg,2*n))**2)[:n]
    if r[0] <= 0: return 0.0, 0.0
    r=r/r[0]; lo,hi=int(sr/1500),int(sr/150); k=lo+np.argmax(r[lo:hi])
    a_,b_,c_=r[k-1],r[k],r[k+1]; d=0.5*(a_-c_)/(a_-2*b_+c_)
    return sr/(k+d), b_
