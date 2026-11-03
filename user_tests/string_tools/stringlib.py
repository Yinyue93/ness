"""Helpers for calibrating and scoring NESS bowed-string instruments.

The preset tables below are copied from src/BowedString.cpp (Percival 2013 data).
Strings are numbered as in NESS: 1 = highest ... 4 = lowest. A finger at
position p (fraction of the string length from the nut) ideally raises the
pitch by a factor 1/(1-p); in practice the finger's width and stiffness and
the string's bending stiffness move it, hence the measured tables.
"""
import os, subprocess, numpy as np
from scipy.io import wavfile

# f0 (Hz), diameter (m), rho (kg/m), E (Pa), from highest to lowest string
PRESETS = {
    'violin': [
        [(659.3, 3.3e-4, 4.1e-4, 6.25e10), (440.0, 6.0e-4, 7.2e-4, 1.95e10), (293.7, 8.8e-4, 0.0016, 4.56e9), (196.0, 8.5e-4, 0.0028, 4.79e9)],
        [(659.3, 2.9e-4, 5.0e-4, 1.34e11), (440.0, 6.1e-4, 8.8e-4, 2.22e10), (293.7, 7.8e-4, 9.9e-4, 6.87e9), (196.0, 7.8e-4, 0.0032, 5.51e9)],
        [(659.3, 2.8e-4, 5.7e-4, 1.86e11), (440.0, 7.5e-4, 5.8e-4, 4.92e9), (293.7, 7.4e-4, 0.0014, 1.29e10), (196.0, 6.5e-4, 0.0037, 1.9e10)],
        [(659.3, 3.2e-4, 4.1e-4, 7.51e10), (440.0, 6.3e-4, 8.6e-4, 2.31e10), (293.7, 6.2e-4, 9.7e-4, 1.83e10), (196.0, 9.8e-4, 0.0036, 2.84e9)],
        [(659.3, 2.4e-4, 3.6e-4, 1.86e11), (440.0, 6.5e-4, 8.6e-4, 1.84e10), (293.7, 7.8e-4, 0.0018, 1.63e10), (196.0, 7.3e-4, 0.0019, 8.91e9)],
    ],
    'viola': [
        [(440.0, 3.6e-4, 8.2e-4, 8.13e10), (293.7, 4.4e-4, 0.00126, 5.53e10), (196.0, 6.7e-4, 0.00217, 8.01e9), (130.8, 7.2e-4, 0.00487, 1.81e10)],
        [(440.0, 3.5e-4, 5.8e-4, 1.14e11), (293.7, 3.2e-4, 0.00122, 9.5e10), (196.0, 6.5e-4, 0.00335, 1.82e10), (130.8, 7.5e-4, 0.00442, 6.54e9)],
    ],
    'cello': [
        [(220.0, 7.5e-4, 0.0017, 2.5e10), (146.8, 8.8e-4, 0.0025, 2.5e10), (98.0, 0.0012, 0.0062, 8.6e9), (65.41, 0.0014, 0.0212, 2.24e10)],
        [(220.0, 7.7e-4, 0.0016, 2.12e10), (146.8, 0.001, 0.0025, 2.13e10), (98.0, 0.0011, 0.0062, 1.62e10), (65.41, 0.0015, 0.0175, 1.34e10)],
        [(220.0, 7.7e-4, 0.0015, 2.25e10), (146.8, 9.1e-4, 0.0036, 2.5e10), (98.0, 0.0011, 0.0079, 2.22e10), (65.41, 0.0014, 0.0192, 2.38e10)],
    ],
}
LENGTH = {'violin': 0.32, 'viola': 0.38, 'cello': 0.69}
T60 = (10.0, 5.0)          # the presets' loss settings (s at DC, s at 1 kHz)

# Bow and finger contact parameters, as in examples/instrument_bowed_string.m
BOW = dict(Kw=1e6, alpha=2.0, beta=20, **{'lambda': 10}, M=0.1)
FING = dict(Kw=1e5, Ku=1e3, alpha=2.2, beta=50, **{'lambda': 20}, M=0.05)

NOTE_NAMES = ['C', 'C#', 'D', 'D#', 'E', 'F', 'F#', 'G', 'G#', 'A', 'A#', 'B']

def note_hz(name):
    """'C4' -> 261.63 (equal temperament, A4 = 440)."""
    pc, octv = name[:-1], int(name[-1])
    midi = 12 * (octv + 1) + NOTE_NAMES.index(pc)
    return 440.0 * 2 ** ((midi - 69) / 12)

def string_def(instrument, index, string, tune_cents=0.0):
    """Physical parameters of preset string (1-based index and string number),
    optionally tuned up/down by tune_cents (tension changes, nothing else)."""
    f0, d, rho, E = PRESETS[instrument][index - 1][string - 1]
    return dict(f0=f0 * 2 ** (tune_cents / 1200), rho=rho, rad=d / 2, E=E, T60=T60, L=LENGTH[instrument])

def write_instrument(path, strings, Fs=44100, title='bowed string instrument', body=None):
    """Manual-definition instrument file: strings is a list of string_def dicts;
    body is an optional body filter type ('violin', 'viola', 'cello')."""
    s = [f'% {title}', f'Fs = {Fs};'] + ([f"body = '{body}';"] if body else []) + [f'Nstrings = {len(strings)};', 'strings = struct;']
    for i, st in enumerate(strings, 1):
        s += [f'strings({i}).f0 = {num(st["f0"], ".10g")};', f'strings({i}).rho = {num(st["rho"], ".10g")};',
              f'strings({i}).rad = {num(st["rad"], ".10g")};', f'strings({i}).E = {num(st["E"], ".10g")};',
              f'strings({i}).T60 = [{st["T60"][0]:g};{st["T60"][1]:g}];', f'strings({i}).L = {st["L"]:g};']
    s.append('bow = struct();')
    s += [f'bow.{k} = {num(v)};' for k, v in BOW.items()]
    s.append('fing = struct();')
    s += [f'fing.{k} = {num(v)};' for k, v in FING.items()]
    open(path, 'w').write('\n'.join(s) + '\n')

def num(x, fmt='.7g'):
    """Number formatted without 'e+' (older NESS parsers reject 1e+06)."""
    return format(x, fmt).replace('e+', 'e')

def _arr(xs):
    return '[' + ' '.join(num(x) for x in xs) + ']'

def write_score(path, Tf, bows, fingers, title='bowed string score'):
    """bows / fingers: lists of dicts with stringnumber and a list of breakpoints
    pts = [(t, pos, force_w, force_u), ...]. Fingers may have 'vibrato' rows
    [start end ramp amplitude freq]."""
    s = [f'% {title}', f'Tf = {Tf:.4f};']
    for kind, items in (('bowgest', bows), ('finggest', fingers)):
        s.append(f'{kind} = struct;')
        for i, g in enumerate(items, 1):
            p = g['pts']
            s += [f'{kind}({i}).stringnumber = {g["stringnumber"]};', f'{kind}({i}).w0 = 1e-8;',
                  f'{kind}({i}).vw0 = 0;', f'{kind}({i}).u0 = 0;', f'{kind}({i}).vu0 = 0;',
                  f'{kind}({i}).times = {_arr(q[0] for q in p)};', f'{kind}({i}).pos = {_arr(q[1] for q in p)};',
                  f'{kind}({i}).force_w = {_arr(q[2] for q in p)};', f'{kind}({i}).force_u = {_arr(q[3] for q in p)};']
            if kind == 'finggest':
                vib = g.get('vibrato', [])
                s.append(f'{kind}({i}).vibrato = [' + '; '.join(' '.join(f'{x:g}' for x in v) for v in vib) + '];')
    open(path, 'w').write('\n'.join(s) + '\n')

def render(exe, inst, score, out, cwd=None):
    """Run NESS; returns (sr, [per-string signals]) from the raw per-string outputs."""
    r = subprocess.run([exe, '-i', inst, '-s', score, '-o', out], capture_output=True, text=True, cwd=cwd)
    if r.returncode != 0:
        raise RuntimeError(r.stdout + r.stderr)
    base = os.path.join(cwd or '.', out)
    sigs = []; k = 1
    while os.path.exists(f'{base}-string{k}-{k}.wav'):
        sr, x = wavfile.read(f'{base}-string{k}-{k}.wav'); sigs.append(x.astype(float)); k += 1
    if not sigs:                       # single-output instrument: just <out>.wav
        sr, x = wavfile.read(base + '.wav')
        sigs = [x.astype(float) if x.ndim == 1 else x.astype(float).mean(axis=1)]
    return sr, sigs

def pitch(x, sr, a, b, fmin=50.0, fmax=2000.0, thresh=0.15):
    """YIN pitch estimate of x[a:b] (seconds). Returns (Hz, aperiodicity);
    aperiodicity near 0 = clean periodic tone, above ~0.2 = not a steady note."""
    seg = x[int(a * sr):int(b * sr)].astype(float)
    seg = seg - seg.mean()
    if len(seg) < 3 * sr / fmin or not np.any(seg):
        return 0.0, 1.0
    W = len(seg) // 2
    tmax = int(sr / fmin) + 2
    W = min(W, len(seg) - tmax)
    # difference function via FFT
    n = 1 << int(np.ceil(np.log2(len(seg) + W)))
    X = np.fft.rfft(seg, n); Y = np.fft.rfft(seg[:W][::-1], n)
    corr = np.fft.irfft(X * Y, n)[W - 1:W - 1 + tmax]
    e = np.concatenate(([0], np.cumsum(seg ** 2)))
    energy0 = e[W]
    energy_t = e[np.arange(tmax) + W] - e[np.arange(tmax)]
    d = energy0 + energy_t - 2 * corr
    d[0] = 0
    cmnd = d * np.arange(tmax) / np.maximum(np.cumsum(d), 1e-30)
    cmnd[0] = 1
    lo = max(2, int(sr / fmax))
    cand = np.where(cmnd[lo:] < thresh)[0]
    if len(cand):
        k = lo + cand[0]
        while k + 1 < tmax and cmnd[k + 1] < cmnd[k]:
            k += 1
    else:
        k = lo + int(np.argmin(cmnd[lo:]))
    if 1 <= k < tmax - 1:
        a_, b_, c_ = cmnd[k - 1], cmnd[k], cmnd[k + 1]
        den = a_ - 2 * b_ + c_
        dk = 0.5 * (a_ - c_) / den if den else 0.0
    else:
        dk = 0.0
    return sr / (k + dk), float(cmnd[k])

def cents(f, ref):
    return 1200 * np.log2(max(f, 1e-9) / ref)

def write_preset_instrument(path, instrument, index, Fs=44100):
    """Instrument file using one of the built-in presets (all four strings)."""
    s = [f'% {instrument} {index} from the built-in preset table', f'Fs = {Fs};', 'Nstrings = 4;',
         f"instrument = '{instrument}';", f'instr_numb = {index};', 'bow = struct();']
    s += [f'bow.{k} = {num(v)};' for k, v in BOW.items()]
    s.append('fing = struct();')
    s += [f'fing.{k} = {num(v)};' for k, v in FING.items()]
    open(path, 'w').write('\n'.join(s) + '\n')

def grid_intervals(sdef, Fs=44100):
    """Number of grid intervals N NESS uses for this string (as in BowedString::init).
    Bows and fingers must stay at least 2/N from either end of the string."""
    import math
    k = 1.0 / Fs; L = sdef['L']; c = 2 * L * sdef['f0']
    kap = math.sqrt(sdef['E'] * math.pi * sdef['rad'] ** 4 / 4 / sdef['rho'])
    lc2 = (-(c * c) / (L * L) + math.sqrt((c / L) ** 4 + 4 * kap * kap * 1e6)) / (2 * kap * kap)
    lam2 = 12 * math.log(10) / lc2 * (-1 / sdef['T60'][0] + 1 / sdef['T60'][1])
    a = c * c * k * k + 2 * lam2 * k
    return int(L / math.sqrt((a + math.sqrt(a * a + 16 * k * k * kap * kap)) / 2))
