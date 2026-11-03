"""A/B listening test: does a body, a room and a finer grid make the bowed string
sound like a real instrument?

    python body_ab.py <ness-framework.exe> <workdir> <inst.m> <score.m> <outdir> [plan.json]

Renders the score at 44.1, 88.2 and 176.4 kHz (raw per-string outputs, -r), then
post-processes in Python. Nothing here changes the NESS model itself.

The framework now has this body built in (src/BodyFilter.cpp, `body = 'viola';`
in the instrument file). Its dense modes come from a different random generator,
so it is the same kind of body as this prototype, not the identical one.

Variants written to <outdir> (all 44.1 kHz stereo, matched loudness):
  1-dry-44k        the string signal as NESS writes it today
  2-body-44k       through a synthetic viola body (modal filter bank)
  3-body-room-44k  body + small-hall reverb
  4-dry-88k        rendered at 88.2 kHz, downsampled; no body
  5-body-room-88k
  6-dry-176k       rendered at 176.4 kHz, downsampled; no body
  7-body-room-176k

The string output is the displacement at x = 0.99. That is within the last grid
interval for every viola string, so it is proportional to the string slope at the
bridge, i.e. to the transverse force on the bridge: the right input for a body.

The body is a synthetic impulse response, not a measured one. The lowest modes are
placed at typical viola values (air A0, corpus CBR, the B1-/B1+ pair). Above about
700 Hz real bodies have dense, irregular modes, so those are drawn at random
(fixed seed) under a smooth envelope with a "bridge hill" around 2 kHz. The
irregular peaks and dips are what matter for the timbre, not the exact frequencies.
"""
import os, sys, json, subprocess
import numpy as np
from scipy.io import wavfile
from scipy.signal import fftconvolve, resample_poly, butter, sosfilt

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from stringlib import pitch

OUT_SR = 44100


def render(exe, inst, score, workdir, fs):
    d = os.path.join(workdir, f'r{fs}')
    os.makedirs(d, exist_ok=True)
    txt = open(inst).read()
    lines = [f'Fs = {fs};' if l.strip().startswith('Fs') and '=' in l else l
             for l in txt.splitlines()]
    open(os.path.join(d, 'inst.m'), 'w').write('\n'.join(lines) + '\n')
    open(os.path.join(d, 'score.m'), 'w').write(open(score).read())
    r = subprocess.run([exe, '-i', 'inst.m', '-s', 'score.m', '-o', 'v', '-r'],
                       cwd=d, capture_output=True, text=True)
    if r.returncode != 0:
        raise RuntimeError(r.stdout + r.stderr)
    sigs, k = [], 1
    while os.path.exists(os.path.join(d, f'v-string{k}-{k}.f64')):
        sigs.append(np.fromfile(os.path.join(d, f'v-string{k}-{k}.f64'), dtype='<f8'))
        k += 1
    x = np.sum(sigs, axis=0)          # all strings drive the same bridge
    if fs != OUT_SR:
        x = resample_poly(x, OUT_SR, fs)
    return x


def viola_body_ir(sr=OUT_SR, dur=0.6, seed=1):
    rng = np.random.default_rng(seed)
    t = np.arange(int(dur * sr)) / sr
    # (frequency Hz, Q, linear gain): typical viola signature modes
    modes = [(230, 25, 0.9),    # A0 air (Helmholtz) mode
             (330, 30, 0.5),    # CBR
             (395, 35, 1.0),    # B1-
             (490, 35, 1.2),    # B1+
             (600, 30, 0.6)]
    # dense region: about 6 modes per 100 Hz from 700 Hz to 9 kHz
    f = 700.0
    while f < 9000.0:
        f += rng.exponential(1.0 / 0.06) * (1 + f / 3000.0) ** 0.5
        hill = np.exp(-0.5 * (np.log(f / 2000.0) / 0.45) ** 2)      # bridge hill
        env = 0.35 + 0.9 * hill
        env /= (1 + (f / 5500.0) ** 4) ** 0.5                       # roll-off
        gain = env * rng.lognormal(0.0, 0.6) * rng.choice([-1, 1])
        modes.append((f, rng.uniform(25, 60), gain))
    h = np.zeros_like(t)
    for f0, q, g in modes:
        a = np.pi * f0 / q
        # a decaying sinusoid peaks at g/(2a) = g*Q/(2*pi*f0) in the frequency
        # domain; scale by f0/Q so `g` is the peak response itself
        h += g * (f0 / q) * np.exp(-a * t) * np.sin(2 * np.pi * f0 * t)
    # weak radiation below the air mode
    h = sosfilt(butter(2, 160, 'highpass', fs=sr, output='sos'), h)
    return h / np.sqrt(np.sum(h ** 2))


def room_ir(sr=OUT_SR, rt60=1.7, seed=2):
    """Stereo small-hall reverb: a few early reflections + decaying filtered noise."""
    rng = np.random.default_rng(seed)
    n = int(rt60 * 1.3 * sr)
    t = np.arange(n) / sr
    out = np.zeros((n, 2))
    for ch in range(2):
        tail = rng.standard_normal(n) * np.exp(-6.9 * t / rt60)
        tail = sosfilt(butter(1, 5000, 'lowpass', fs=sr, output='sos'), tail)
        tail[:int(0.025 * sr)] = 0                       # pre-delay
        er = np.zeros(n)
        for _ in range(8):
            er[int(rng.uniform(0.008, 0.045) * sr)] += rng.uniform(0.3, 0.7) * rng.choice([-1, 1])
        out[:, ch] = er / np.sqrt(np.sum(er ** 2)) * 0.5 + tail / np.sqrt(np.sum(tail ** 2))
    return out


def finish(x, body=None, room=None, wet=0.3):
    x = x - np.mean(x)
    if body is not None:
        x = fftconvolve(x, body)[:len(x)]
    x = x / np.sqrt(np.mean(x ** 2))
    if room is None:
        st = np.stack([x, x], 1)
    else:
        w = np.stack([fftconvolve(x, room[:, c])[:len(x) + len(room) // 2] for c in range(2)], 1)
        w /= np.sqrt(np.mean(w[:len(x)] ** 2))
        d = np.pad(x, (0, len(w) - len(x)))
        st = (1 - wet) * d[:, None] + wet * w
    fade = int(0.01 * OUT_SR)
    st[-fade:] *= np.linspace(1, 0, fade)[:, None]
    return st


def write(path, st, rms_db=-21.0):
    st = st * (10 ** (rms_db / 20) / np.sqrt(np.mean(st ** 2)))
    peak = np.abs(st).max()
    if peak > 0.97:
        st *= 0.97 / peak
    wavfile.write(path, OUT_SR, (st * 32767).astype(np.int16))
    return 20 * np.log10(np.sqrt(np.mean(st ** 2)))


def pitch_report(x, plan, label):
    names = 'C C# D D# E F F# G G# A A# B'.split()
    cents = []
    for n in plan['notes']:
        nm, octv = n['name'][:-1], int(n['name'][-1])
        ftarget = 440 * 2 ** ((names.index(nm) + 12 * (octv + 1) - 69) / 12)
        a = n['start'] + n.get('settle_ms', 0) / 1000 + 0.05
        hz, ap = pitch(x, OUT_SR, a, n['end'] - 0.03)
        cents.append(f"{n['name']}:{1200 * np.log2(hz / ftarget):+.0f}" if hz > 0 else f"{n['name']}:--")
    print(f'  pitch vs target ({label}): ' + ' '.join(cents))


def main():
    exe, workdir, inst, score, outdir = sys.argv[1:6]
    plan = json.load(open(sys.argv[6])) if len(sys.argv) > 6 else None
    os.makedirs(outdir, exist_ok=True)
    body, room = viola_body_ir(), room_ir()
    sig = {}
    for fs in (44100, 88200, 176400):
        print(f'rendering at {fs} Hz ...')
        sig[fs] = render(exe, inst, score, workdir, fs)
        if plan:
            pitch_report(sig[fs], plan, f'{fs // 1000}k')
    variants = [('1-dry-44k', 44100, False, False),
                ('2-body-44k', 44100, True, False),
                ('3-body-room-44k', 44100, True, True),
                ('4-dry-88k', 88200, False, False),
                ('5-body-room-88k', 88200, True, True),
                ('6-dry-176k', 176400, False, False),
                ('7-body-room-176k', 176400, True, True)]
    for name, fs, b, r in variants:
        st = finish(sig[fs], body if b else None, room if r else None)
        path = os.path.join(outdir, f'viola-ab-{name}.wav')
        write(path, st)
        print(f'wrote {path}')


if __name__ == '__main__':
    main()
