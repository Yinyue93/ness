/*
 * NeSS Framework Code
 *
 * Body filter for bowed-string instruments.
 *
 * The bowed-string model simulates the strings only, and its outputs are taken
 * next to the bridge, so they are proportional to the force each string puts on
 * the bridge. On a real violin, viola or cello the body turns that force into
 * sound, and its resonances shape the timbre. This filter stands in for the body:
 * a bank of damped resonators (a "modal" body), applied to each output after the
 * simulation and before the WAV files are written.
 *
 * The body is synthetic. The lowest modes (the air mode A0, the corpus mode CBR
 * and the B1-/B1+ pair) sit at typical values for each instrument. Above them real
 * bodies have dense, irregular modes, so those are drawn from a fixed-seed random
 * generator under a smooth envelope with a "bridge hill" peak. The resonator
 * frequencies and the overall frequency response don't depend on the sample
 * rate. The response is scaled to unit energy at 44.1 kHz, so the output level
 * stays comparable to the dry output.
 */
#ifndef _BODYFILTER_H_
#define _BODYFILTER_H_

#include <string>
#include <vector>
using namespace std;

struct BodyMode {
    double freq;   // Hz
    double Q;
    double gain;   // peak response of this mode, before normalisation
};

class BodyFilter {
 public:
    // returns NULL for "none" or "" (no body) and for unknown types; use
    // isValidType to tell those apart
    static BodyFilter *create(string type);
    static bool isValidType(string type);

    // filters n samples at sample rate sr in place
    void apply(double *data, int n, double sr);

    string getType() { return type; }
    vector<BodyMode> *getModes() { return &modes; }

 private:
    BodyFilter(string type, double hillFreq, double rolloffFreq, double denseStart,
	       double denseEnd, double density, double highPassFreq, unsigned long long seed);

    // filters without the unit-energy scaling
    void filter(double *data, int n, double sr);

    string type;
    vector<BodyMode> modes;
    double highPassFreq;
};

#endif
