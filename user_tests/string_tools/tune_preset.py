"""Make an in-tune C major scale for one bowed-string preset, end to end.

1. Bow gesture: try a grid of bow forces / speeds / positions on every
   (string, finger position) the scale needs, each bowed from rest, and keep
   the gesture that speaks cleanly everywhere and whose neighbours in the grid
   also do (a gesture on the edge of the working region is fragile).
2. Open strings: tune each string so that, bowed with that gesture, it plays
   its nominal pitch (bowing flattens the string a little).
3. Calibrate pitch against finger position on each string the scale uses.
4. Build the scale from the tables and refine it by rendering and measuring.

usage: python tune_preset.py <exe> <workdir> <instrument> <index> [--note 0.3] [--first 0.5] [--iters 3]
                             [--tonic C2] [--body cello]
Writes everything into <workdir>/<instrument><index>/ and prints a summary.
"""
import sys, os, json, argparse, itertools, types, numpy as np
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from stringlib import string_def, cents
from calibrate import run_points, calibrate
import scale

FWS = [-0.3, -0.5, -0.8]
FUS = [2.0, 3.0, 4.0]
POSS = [0.86, 0.90, 0.93]
# The cello strings are much heavier: with the violin/viola grid most gestures
# jump an octave or a fifth (bow force too low for the string), so the cello
# searches heavier bowing a little nearer the bridge.
GRIDS = {'cello': ([-0.8, -1.2, -1.8], [2.0, 4.0, 6.0], [0.82, 0.86, 0.90])}

def good(r):
    return (r['hz'] and r['aperiodicity'] < 0.05 and r['drift'] is not None and abs(r['drift']) < 8
            and r['speak'] is not None and abs(r['cents_vs_ideal']) < 150)

def needed_cases(inst, tonic=None, idx=1):
    """(string, ideal finger position) for every scale note, open strings included."""
    return sorted({(s, round(1 - 2 ** (-k / 12), 4)) for _, s, k in scale.fingering(inst, True, tonic, idx)})

def choose_gesture(exe, wd, inst, idx, log, tonic=None):
    cases = needed_cases(inst, tonic, idx)
    FWS, FUS, POSS = GRIDS.get(inst, (globals()['FWS'], globals()['FUS'], globals()['POSS']))
    grid = list(itertools.product(range(len(FWS)), range(len(FUS)), range(len(POSS))))
    jobs = [((g, c), string_def(inst, idx, c[0]), c[1], dict(fw=FWS[g[0]], fu=FUS[g[1]], pos=POSS[g[2]]))
            for g in grid for c in cases]
    res = {}
    for (g, c), r in run_points(exe, os.path.join(wd, 'gesture'), jobs):
        res.setdefault(g, {})[c] = r
    ok = {g: all(good(r) for r in res[g].values()) for g in grid}
    def neighbours(g):
        for ax in range(3):
            for d in (-1, 1):
                n = list(g); n[ax] += d
                if tuple(n) in ok: yield tuple(n)
    def rank(g):
        nb = list(neighbours(g))
        speaks = [r['speak'] for r in res[g].values() if r['speak'] is not None]
        nfail = sum(not good(r) for r in res[g].values())
        return (nfail, -sum(ok[n] for n in nb) / len(nb), max(speaks, default=9), sum(speaks))
    best = min(grid, key=rank)
    gest = dict(fw=FWS[best[0]], fu=FUS[best[1]], pos=POSS[best[2]])
    nfail, nbfrac, smax, _ = rank(best)
    log(f'  gesture: {sum(ok.values())}/{len(grid)} gestures work for all {len(cases)} positions; chose '
        f'fw {gest["fw"]} fu {gest["fu"]} pos {gest["pos"]} ({-nbfrac:.0%} of its neighbours also work, '
        f'slowest note speaks in {smax*1000:.0f} ms{", %d positions FAIL" % nfail if nfail else ""})')
    return gest, res[best], dict(working=sum(ok.values()), total=len(grid), failures=nfail,
                                 neighbours_ok=-nbfrac, slowest_speak=smax)

def tune_open(exe, wd, inst, idx, gest, strings, first, log):
    """Cents to tune each string so the bowed open string plays its nominal pitch."""
    tune = {s: -first[s] for s in strings}
    jobs = [(s, string_def(inst, idx, s, tune[s]), 0.0, gest) for s in strings]
    for s, r in run_points(exe, os.path.join(wd, 'tune'), jobs):
        # one refinement step; cents_vs_ideal is relative to the tuned string
        tune[s] -= r['cents_vs_ideal'] + tune[s]
    log('  open strings: bowed flat by ' + ', '.join(f'string {s} {first[s]:+.1f} c' for s in strings)
        + '; tuned ' + ', '.join(f'{tune[s]:+.1f} c' for s in strings))
    return tune

def run(exe, workdir, inst, idx, note=0.3, first=0.5, iters=3, log=print, tonic=None, body=None):
    wd = os.path.join(os.path.abspath(workdir), f'{inst}{idx}'); os.makedirs(wd, exist_ok=True)
    log(f'== {inst} {idx}')
    gest, gres, gsum = choose_gesture(exe, wd, inst, idx, log, tonic)
    strings = sorted({s for s, _ in needed_cases(inst, tonic, idx)})
    open_off = {s: gres[(s, 0.0)]['cents_vs_ideal'] for s in strings if (s, 0.0) in gres}
    tune = tune_open(exe, wd, inst, idx, gest, sorted(open_off), open_off, log)
    pmax = max(p for _, p in needed_cases(inst, tonic, idx)) + 0.08
    cal = calibrate(exe, wd, inst, idx, strings, pmax, 0.005, gest['fw'], gest['fu'], gest['pos'], tune)
    args = types.SimpleNamespace(exe=exe, cal=cal, outdir=wd, note=note, last=1.0, first=first, slide=0.03,
                                 iters=iters, open=True, tonic=tonic, body=body,
                                 name=f'{inst}{idx}_c_major' + (f'_{tonic}' if tonic else ''))
    plan = scale.run(args)
    errs = [n['cents'] for n in plan]
    summary = dict(instrument=inst, index=idx, gesture=gest, gesture_search=gsum, tune_cents=tune,
                   max_err=max(abs(e) for e in errs if e is not None) if all(e is not None for e in errs) else None,
                   mean_err=float(np.mean([abs(e) for e in errs if e is not None])),
                   settle_ms=[n['settle_ms'] for n in plan], notes=[(n['name'], n['string'], n['p'], n['cents']) for n in plan])
    json.dump(summary, open(os.path.join(wd, 'summary.json'), 'w'), indent=1)
    return summary

if __name__ == '__main__':
    ap = argparse.ArgumentParser()
    ap.add_argument('exe'); ap.add_argument('workdir'); ap.add_argument('instrument'); ap.add_argument('index', type=int)
    ap.add_argument('--note', type=float, default=0.3); ap.add_argument('--first', type=float, default=0.5)
    ap.add_argument('--iters', type=int, default=3)
    ap.add_argument('--tonic', help='start the scale here, e.g. C2')
    ap.add_argument('--body', help="also render the final scale through this body filter")
    a = ap.parse_args()
    run(os.path.abspath(a.exe), a.workdir, a.instrument, a.index, a.note, a.first, a.iters,
        log=lambda m: print(m, flush=True), tonic=a.tonic, body=a.body)
