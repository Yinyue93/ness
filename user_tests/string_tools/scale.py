"""Build an in-tune C major scale for a NESS bowed-string preset from its
pitch-vs-finger-position table (made by calibrate.py), then refine it by
rendering and measuring.

usage: python scale.py <exe> <calibration.json> <outdir> [options]
  --note 0.3      note length (s)          --last 1.0   last note length (s)
  --first 0.3     first note length (s); the first note starts from rest, so
                  on a slow-speaking string it may need longer
  --slide 0.03    finger shift time (s)    --iters 2    refinement passes
  --open          use open strings where the scale allows (D and A on the viola)
  --name NAME     output base name (default <instrument><index>_c_major)
  --tonic C2      start the scale on this note (first-position fingering from
                  the open strings); default: the instrument's usual layout
  --body cello    also render the final scale through the framework's body
                  filter (the tuning itself is measured on the bare strings)

The bow gesture (force, speed, position) and any string tuning come from the
calibration file, so the scale is played exactly the way the table was measured.

Writes <outdir>/instrument_<inst><idx>.m, <name>.m (score), <name>.json (plan
and measured cents) and the rendered <name>-mix.wav / per-string WAVs.
"""
import sys, os, json, argparse, numpy as np
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from stringlib import write_instrument, write_score, render, pitch, cents, note_hz, string_def, PRESETS
from calibrate import T_BOW, T_PRESS

# Strings carrying the scale (low, middle, high) and its tonic. All three
# instruments are tuned in fifths, so the same fingering pattern works.
LAYOUT = {'viola': ((3, 2, 1), 'C4'), 'violin': ((4, 3, 2), 'C4'), 'cello': ((3, 2, 1), 'C3')}
DEGREES = [0, 2, 4, 5, 7, 9, 11, 12]
NAMES = ['C', 'D', 'E', 'F', 'G', 'A', 'B', 'C']

FING_FORCE = -3.0
GOOD = dict(aperiodicity=0.05, drift=8.0, off=150.0)   # calibration points used

def fingering_from(inst, use_open, tonic, index=1):
    """First-position fingering for a C major scale from any tonic: each note goes
    on the string whose open note is nearest below it (open where allowed), so a
    scale from C2 on the cello is C string C D E F, G string G A B C."""
    opens = {s: int(round(69 + 12 * np.log2(f0 / 440.0)))
             for s, (f0, _, _, _) in enumerate(PRESETS[inst][index - 1], 1)}
    base = int(round(69 + 12 * np.log2(note_hz(tonic) / 440.0)))
    notes = []
    for d, nm in zip(DEGREES, NAMES):
        m = base + d
        name = f'{nm}{(m // 12) - 1}'
        cands = [(m - o, s) for s, o in opens.items() if m - o >= (0 if use_open else 1)]
        if not cands:
            raise ValueError(f'{name} is below the lowest string of the {inst}')
        k, s = min(cands)
        notes.append((name, s, k))
    return notes

def fingering(inst, use_open, tonic=None, index=1):
    if tonic is not None:
        return fingering_from(inst, use_open, tonic, index)
    (lo, mid, hi), tonic = LAYOUT[inst]
    octv = int(tonic[-1])
    notes = []
    for d, nm in zip(DEGREES, NAMES):
        name = f'{nm}{octv + (d >= 12)}'
        # semitones above each string's open note: low = tonic-5, mid = tonic+2, hi = tonic+9
        if d <= 2 and not (use_open and d == 2):
            notes.append((name, lo, d + 5))
        elif d <= 7 or (d == 9 and not use_open):
            notes.append((name, mid, d - 2))
        else:
            notes.append((name, hi, d - 9))
    return notes

class Table:
    """Measured semitones-above-nominal-open against finger position for one string."""
    def __init__(self, entry):
        self.f_open = entry['open_hz']
        pts = [r for r in entry['points'] if r['p'] > 0 and r['hz']
               and r['aperiodicity'] < GOOD['aperiodicity'] and r['drift'] is not None
               and abs(r['drift']) < GOOD['drift'] and abs(r['cents_vs_ideal']) < GOOD['off']]
        self.p = np.array([r['p'] for r in pts])
        self.st = np.array([12 * np.log2(r['hz'] / self.f_open) for r in pts])
        self.open_st = next(12 * np.log2(r['hz'] / self.f_open) for r in entry['points'] if r['p'] == 0)

    def position(self, st):
        """Finger position that plays st semitones above the nominal open note
        (local linear fit over the nearest measured points), and the local
        slope in semitones per unit position."""
        near = np.argsort(np.abs(self.st - st))[:7]
        if np.abs(self.st[near] - st).min() > 0.5:
            raise ValueError(f'no clean calibration point within half a semitone of {st:.2f}')
        slope, icpt = np.polyfit(self.p[near], self.st[near], 1)
        return (st - icpt) / slope, slope

def build_score(notes, tables, args, targets, bow):
    """notes: (name, string, semitones); targets: semitones to aim for per note;
    bow: dict(pos, force_w, force_u). Returns (Tf, bows, fingers, plan)."""
    BOW_POS, FW, FU = bow['pos'], bow['force_w'], bow['force_u']
    t = 0.15; plan = []
    for i, (nm, s, k) in enumerate(notes):
        d = args.last if i == len(notes) - 1 else (args.first if i == 0 else args.note)
        if k == 0:
            p = 0.0
        else:
            p, _ = tables[s].position(targets[i])
        plan.append(dict(name=nm, string=s, semitones=k, target_st=targets[i], p=p, start=t, end=t + d)); t += d
    Tf = t + 0.6
    bows, fingers = [], []
    for s in sorted({n['string'] for n in plan}):
        mine = [n for n in plan if n['string'] == s]
        # one slurred bow stroke per run of consecutive notes on this string
        segs = []
        for n in mine:
            if segs and abs(segs[-1][1] - n['start']) < 1e-9: segs[-1][1] = n['end']
            else: segs.append([n['start'], n['end']])
        pts = [(0.0, BOW_POS, 0, 0)]
        for a, b in segs:
            # press the bow onto the string, then push it; stop pushing before
            # lifting. The attack is timed exactly as in the calibration (press
            # starts T_BOW before the push and is complete 50 ms before it):
            # a quicker press can leave the bow bouncing when the push starts.
            pts += [(a - T_BOW, BOW_POS, 0, 0), (a - 0.05, BOW_POS, FW, 0), (a, BOW_POS, FW, 0), (a + 0.03, BOW_POS, FW, FU),
                    (b, BOW_POS, FW, FU), (b + 0.02, BOW_POS, FW, 0), (b + 0.05, BOW_POS, 0, 0)]
        pts.append((Tf, BOW_POS, 0, 0))
        pts = [q for i, q in enumerate(pts) if i == 0 or q[0] > pts[i - 1][0]]
        bows.append(dict(stringnumber=s, pts=pts))
        stopped = [n for n in mine if n['p'] > 0]
        if not stopped:
            continue
        # finger: down before the string's first bowed note, then slide between notes
        first = stopped[0]
        fp = [(0.0, first['p'], 0, 0)]
        if first is mine[0]:
            # pressed together with the bow, as in the calibration
            fp += [(first['start'] - T_BOW, first['p'], 0, 0), (first['start'] - T_BOW + T_PRESS, first['p'], FING_FORCE, 0)]
        else:
            # open note(s) first: press the finger at the start of its note
            fp += [(first['start'] - 0.02, first['p'], 0, 0), (first['start'] + 0.01, first['p'], FING_FORCE, 0)]
        cur = first['p']
        for n in stopped[1:]:
            fp += [(n['start'] - args.slide, cur, FING_FORCE, 0), (n['start'], n['p'], FING_FORCE, 0)]; cur = n['p']
        fp.append((Tf, cur, FING_FORCE, 0))
        fp = [q for i, q in enumerate(fp) if i == 0 or q[0] > fp[i - 1][0]]
        fingers.append(dict(stringnumber=s, pts=fp))
    return Tf, bows, fingers, plan

def measure(sigs, sr, plan):
    """Per-note pitch error (cents) over the steady part, and the time the
    note takes to settle within 15 cents of its target."""
    out = []
    for n in plan:
        x = sigs[n['string'] - 1]; ref = note_hz(n['name']); a, b = n['start'], n['end']
        guard = min(0.10, 0.4 * (b - a))
        f, ap = pitch(x, sr, a + guard, b - 0.01, fmin=ref / 1.6, fmax=ref * 2.2)
        # stop before the finger slides to the next note (the last 30 ms)
        # window of at least 3 periods of fmin (the detector needs that), so
        # longer than 40 ms on low notes
        win = max(0.04, 3.3 * 1.6 / ref)
        tr = []; t = a; stop = b - (0.03 if n is not plan[-1] else 0.0)
        while t + win <= stop + 1e-9:
            g, _ = pitch(x, sr, t, t + win, fmin=ref / 1.6, fmax=ref * 2.2); tr.append(cents(g, ref) if g else 999.0); t += 0.01
        settle = next((10 * i for i in range(len(tr)) if all(abs(c) < 15 for c in tr[i:])), None)
        out.append(dict(cents=cents(f, ref) if f else None, aperiodicity=ap, settle_ms=settle))
    return out

def parser():
    ap = argparse.ArgumentParser()
    ap.add_argument('exe'); ap.add_argument('cal'); ap.add_argument('outdir')
    ap.add_argument('--note', type=float, default=0.3); ap.add_argument('--last', type=float, default=1.0)
    ap.add_argument('--first', type=float, default=None)
    ap.add_argument('--slide', type=float, default=0.03); ap.add_argument('--iters', type=int, default=2)
    ap.add_argument('--open', action='store_true'); ap.add_argument('--name')
    ap.add_argument('--tonic', help='start the scale here, e.g. C2 (default: the usual layout for the instrument)')
    ap.add_argument('--body', help="also render the final scale through this body filter ('violin', 'viola', 'cello')")
    return ap

def run(args):
    """Build, render and refine the scale; returns the final plan with measurements."""
    if args.first is None: args.first = args.note
    cal = json.load(open(args.cal)) if isinstance(args.cal, str) else args.cal
    inst, idx = cal['instrument'], cal['index']
    exe = os.path.abspath(args.exe); os.makedirs(args.outdir, exist_ok=True)
    name = args.name or f'{inst}{idx}_c_major'
    tables = {int(s): Table(e) for s, e in cal['strings'].items()}
    notes = fingering(inst, args.open, getattr(args, 'tonic', None), idx)
    f_open = {s: string_def(inst, idx, s)['f0'] for s in tables}
    # target: the note's pitch in semitones above the string's nominal (preset) open frequency
    targets = [12 * np.log2(note_hz(nm) / f_open[s]) for nm, s, k in notes]
    # all four strings, tuned as they were for the calibration
    tune = {int(s): e.get('tune_cents', 0.0) for s, e in cal['strings'].items()}
    inst_file = f'instrument_{inst}{idx}.m'
    write_instrument(os.path.join(args.outdir, inst_file), [string_def(inst, idx, s, tune.get(s, 0.0)) for s in (1, 2, 3, 4)],
                     title=f'{inst} preset {idx}' + (', open strings tuned (cents): ' + ' '.join(f'{s}:{c:+.1f}' for s, c in sorted(tune.items())) if any(tune.values()) else ''))
    for it in range(args.iters + 1):
        Tf, bows, fingers, plan = build_score(notes, tables, args, targets, cal['bow'])
        write_score(os.path.join(args.outdir, name + '.m'), Tf, bows, fingers,
                    title=f'C major scale on {inst} preset {idx}, finger positions from the measured pitch table')
        sr, sigs = render(exe, inst_file, name + '.m', name, cwd=args.outdir)
        res = measure(sigs, sr, plan)
        errs = [r['cents'] for r in res]
        ok = [e for e in errs if e is not None]
        print(f'{inst}{idx} pass {it}: max |err| {max(abs(e) for e in ok):5.1f} c, mean {np.mean(np.abs(ok)):4.1f} c :: '
              + ' '.join(f"{n['name']}{'?' if e is None else f'{e:+.0f}'}" for n, e in zip(plan, errs))
              + ' | settle ms ' + ' '.join(str(r['settle_ms']) for r in res), flush=True)
        if it == args.iters:
            break
        for i, (n, r) in enumerate(zip(plan, res)):
            # only correct notes that sound as a clean, settled tone near the
            # target; an attack transient or a wrong regime is not intonation
            if n['p'] == 0 or r['cents'] is None or r['aperiodicity'] > 0.1 or abs(r['cents']) > 80:
                continue
            targets[i] -= 0.9 * r['cents'] / 100
    for n, r in zip(plan, res):
        n.update(r)
    body = getattr(args, 'body', None)
    if body:
        # the tuning above is measured on the bare strings; the body only
        # colours the final render
        body_file = f'instrument_{inst}{idx}_{body}_body.m'
        write_instrument(os.path.join(args.outdir, body_file), [string_def(inst, idx, s, tune.get(s, 0.0)) for s in (1, 2, 3, 4)],
                         title=f'{inst} preset {idx} with the {body} body filter', body=body)
        render(exe, body_file, name + '.m', name + '_body', cwd=args.outdir)
        print(f'rendered {os.path.join(args.outdir, name + "_body-mix.wav")}', flush=True)
    json.dump(dict(instrument=inst, index=idx, bow=cal['bow'], tune_cents=tune, notes=plan),
              open(os.path.join(args.outdir, name + '.json'), 'w'), indent=1)
    return plan

if __name__ == '__main__':
    run(parser().parse_args())
