"""Measure pitch against finger position for each string of a bowed-string preset.

Every point is its own short simulation of a single string: the finger is
pressed down before the bow starts and stays still, then the string is bowed
with the same bow gesture the scale uses. We record the settled pitch, how
steady it is, and how long the note takes to speak.

usage: python calibrate.py <exe> <outdir> <instrument> <index> [options]
  --strings 1,2,3,4   --pmax 0.45   --step 0.005
  --fw -0.3 --fu 2.0 --pos 0.86     bow normal force, tangential force, position
  --tune c1,c2,c3,c4                per-string tuning in cents (default 0)
Writes <outdir>/<instrument><index>.json.
"""
import sys, os, json, argparse, numpy as np
from concurrent.futures import ThreadPoolExecutor
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from stringlib import string_def, write_instrument, write_score, render, pitch, cents, grid_intervals

# Default bow gesture: bow pressed onto the string first, then pushed.
BOW_POS, FW, FU = 0.86, -0.3, 2.0
FING_FORCE = -3.0
T_PRESS, T_BOW, TF = 0.03, 0.10, 0.80

def ideal_hz(f_open, p):
    return f_open / (1 - p)

def one_point(exe, workdir, sdef, p, fw=FW, fu=FU, pos=BOW_POS, ramp=0.03):
    """Bow one string from rest with the finger held still at p; measure it."""
    os.makedirs(workdir, exist_ok=True)
    write_instrument(os.path.join(workdir, 'i.m'), [sdef])
    bow = dict(stringnumber=1, pts=[(0, pos, 0, 0), (T_BOW - 0.05, pos, fw, 0), (T_BOW, pos, fw, 0),
                                    (T_BOW + ramp, pos, fw, fu), (TF, pos, fw, fu)])
    fing = [dict(stringnumber=1, pts=[(0, p, 0, 0), (T_PRESS, p, FING_FORCE, 0), (TF, p, FING_FORCE, 0)])] if p > 0 else []
    write_score(os.path.join(workdir, 's.m'), TF, [bow], fing)
    sr, sig = render(exe, 'i.m', 's.m', 'o', cwd=workdir)
    x = sig[0]
    ref = ideal_hz(sdef['f0'], p)
    f1, ap1 = pitch(x, sr, 0.40, 0.58, fmin=ref / 2.5, fmax=ref * 2.5)
    f2, ap2 = pitch(x, sr, 0.58, 0.78, fmin=ref / 2.5, fmax=ref * 2.5)
    # speaking time: start of the first 50 ms window after which pitch stays
    # within 15 cents of the settled pitch
    # (the pitch detector needs 3 periods of fmin, so the window is longer on
    # low notes: 50 ms is too short below about 90 Hz)
    win = max(0.05, 3.3 * 1.5 / ref)
    tr = []; t = T_BOW
    while t + win <= 0.78:
        f, _ = pitch(x, sr, t, t + win, fmin=ref / 1.5, fmax=ref * 2.5); tr.append((t, cents(f, f2) if f2 else 999)); t += 0.01
    speak = next((tt - T_BOW for i, (tt, _) in enumerate(tr) if all(abs(c) < 15 for _, c in tr[i:])), None)
    rms = float(np.sqrt((x[int(0.4 * sr):int(0.78 * sr)] ** 2).mean()))
    return dict(p=p, hz=f2, cents_vs_ideal=cents(f2, ref) if f2 else None, drift=cents(f2, f1) if f1 and f2 else None,
                aperiodicity=max(ap1, ap2), speak=speak, rms=rms)

def run_points(exe, workdir, jobs, workers=None):
    """jobs: list of (key, sdef, p, gesture dict). Returns list of (key, result)."""
    def run(j):
        i, (key, sdef, p, g) = j
        return key, one_point(exe, os.path.join(workdir, f'pt{i:05d}'), sdef, p, **g)
    with ThreadPoolExecutor(max_workers=workers or max(1, os.cpu_count() - 2)) as ex:
        return list(ex.map(run, enumerate(jobs)))

def calibrate(exe, outdir, inst, idx, strings=(1, 2, 3, 4), pmax=0.45, step=0.005,
              fw=FW, fu=FU, pos=BOW_POS, tune=None):
    """Sweep finger position on each string; returns (and writes) the table."""
    tune = tune or {}
    gesture = dict(fw=fw, fu=fu, pos=pos)
    sdefs = {s: string_def(inst, idx, s, tune.get(s, 0.0)) for s in strings}
    # open string plus fingered positions; a finger must be at least 2 grid
    # intervals from the nut (NESS clamps it otherwise)
    ps = np.round(np.arange(step, pmax + 1e-9, step), 6)
    jobs = [(s, sdefs[s], 0.0, gesture) for s in strings]
    jobs += [(s, sdefs[s], float(p), gesture) for s in strings for p in ps if p >= 2.0 / grid_intervals(sdefs[s]) + 1e-6]
    res = {s: [] for s in strings}
    for s, r in run_points(exe, os.path.join(outdir, 'work', f'{inst}{idx}'), jobs):
        res[s].append(r)
    out = dict(instrument=inst, index=idx, bow=dict(pos=pos, force_w=fw, force_u=fu), finger_force=FING_FORCE,
               strings={str(s): dict(open_hz=string_def(inst, idx, s)['f0'], tune_cents=tune.get(s, 0.0),
                                    grid_intervals=grid_intervals(sdefs[s]), points=res[s]) for s in strings})
    json.dump(out, open(os.path.join(outdir, f'{inst}{idx}.json'), 'w'), indent=1)
    return out

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('exe'); ap.add_argument('outdir'); ap.add_argument('instrument'); ap.add_argument('index', type=int)
    ap.add_argument('--strings', default='1,2,3,4'); ap.add_argument('--pmax', type=float, default=0.45)
    ap.add_argument('--step', type=float, default=0.005)
    ap.add_argument('--fw', type=float, default=FW); ap.add_argument('--fu', type=float, default=FU)
    ap.add_argument('--pos', type=float, default=BOW_POS); ap.add_argument('--tune', default='')
    a = ap.parse_args()
    strings = [int(s) for s in a.strings.split(',')]
    tune = {i + 1: float(c) for i, c in enumerate(a.tune.split(','))} if a.tune else {}
    out = calibrate(os.path.abspath(a.exe), os.path.abspath(a.outdir), a.instrument, a.index, strings,
                    a.pmax, a.step, a.fw, a.fu, a.pos, tune)
    print(f'wrote {a.instrument}{a.index}.json ({sum(len(v["points"]) for v in out["strings"].values())} points)')

if __name__ == '__main__':
    main()
