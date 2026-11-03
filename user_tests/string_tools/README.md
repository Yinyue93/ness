# Bowed-string tuning tools

Tools for getting in-tune scales out of the NESS bowed-string model (violin,
viola and cello presets). They follow the same idea as `brass_tools`: measure
the instrument first, then write the score from the measurements.

## Workflow

```
python tune_preset.py <ness-framework.exe> <workdir> viola 1
```

runs everything for one preset and writes into `<workdir>/viola1/`. Options:

- `--tonic C2` starts the scale on another note, with first-position fingering
  worked out from the open strings (e.g. cello from C2: C string C D E F, G string
  G A B C).
- `--body cello` also renders the final scale through the framework's body filter.
  The tuning is still measured on the bare strings.

The steps are:

1. **Bow gesture.** Every (string, finger position) the scale needs is bowed
   from rest with a 3x3x3 grid of bow normal force, pushing force and bow
   position. The chosen gesture speaks cleanly at every position, and so do
   its neighbours in the grid. Gestures at the edge of the working region
   fail badly (octave jumps, silence) when anything changes.
2. **Open strings.** Bowing flattens the string (by 15-60 cents here), so each
   open string the scale uses is retuned until it plays its nominal pitch
   when bowed with that gesture. This is the same idea as the trumpet's
   tuning slide, and it is how players tune too.
3. **Calibration** (`calibrate.py`). Finger position is swept in steps of
   0.005 on each string. Every point is a separate short simulation of one
   string with the finger held still, and the settled pitch, drift,
   aperiodicity and speaking time are recorded.
4. **Scale** (`scale.py`). Each note's finger position comes from a local
   linear fit of the table around its target pitch, using only clean points.
   The scale is then rendered and measured, and the targets are corrected
   from the measurements. A note is only corrected when it sounds as a
   clean, settled tone, so a bad attack can never drag a finger off.

The scale uses first-position fingering, with open strings where the scale
allows (D and A on the viola). Fingered notes high on the lower strings are
the least stable part of the model.

`calibrate.py` and `scale.py` also run on their own; see their docstrings.

## Things learned about the model

- Bows and fingers were placed one grid point (1/N of the string) nearer the
  bridge than requested (fixed in `BowedString.cpp`). At 44.1 kHz the grid is
  coarse, with N = 18-30 intervals on the highest strings, so this made every
  fingered note sharp by up to ~60 cents. With the fix, the pitch at a given
  finger position no longer depends on the sample rate.
- A finger pressed onto a string that is already vibrating could stall the
  finger friction solver for up to a million iterations per time step
  (fixed).
- The attack must be timed exactly as in the calibration: press the bow
  (and the finger) 100 ms before pushing, and finish the press 50 ms before
  the push. A quicker press leaves the bow bouncing and can lock a note into
  a wrong regime.
- Fingered notes play 10-60 cents flat of the ideal 1/(1-p) position, more
  so higher up the string and with more bow force. The table absorbs this.
- Notes on the lower strings take longer to settle from rest (up to ~0.2 s
  on the viola G string), so the first note of the scale is longer.
