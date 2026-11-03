/*
 * NeSS Framework Code
 *
 * Body filter for bowed-string instruments. See BodyFilter.h.
 */

#include "BodyFilter.h"
#include "Logger.h"

#include <cmath>
#include <cstring>

#ifndef M_PI
#define M_PI 3.14159265358979323846
#endif

// small self-contained generator (splitmix64) so that the modes are the same on
// every platform and compiler
namespace {
class BodyRandom {
 public:
    BodyRandom(unsigned long long seed) : state(seed) {}
    double uniform() {        // in (0, 1)
	unsigned long long z = (state += 0x9E3779B97F4A7C15ULL);
	z = (z ^ (z >> 30)) * 0xBF58476D1CE4E5B9ULL;
	z = (z ^ (z >> 27)) * 0x94D049BB133111EBULL;
	z = z ^ (z >> 31);
	return ((double)(z >> 11) + 0.5) * (1.0 / 9007199254740992.0);
    }
    double normal() {         // Box-Muller
	double u1 = uniform(), u2 = uniform();
	return sqrt(-2.0 * log(u1)) * cos(2.0 * M_PI * u2);
    }
 private:
    unsigned long long state;
};
}

bool BodyFilter::isValidType(string type)
{
    return (type == "" || type == "none" || type == "violin" ||
	    type == "viola" || type == "cello");
}

BodyFilter *BodyFilter::create(string type)
{
    BodyFilter *bf = NULL;
    // signature modes: (frequency, Q, peak gain)
    static const double violin[][3] = {
	{ 275.0, 25.0, 0.9 },   // A0 air mode
	{ 405.0, 30.0, 0.5 },   // CBR
	{ 470.0, 35.0, 1.0 },   // B1-
	{ 540.0, 35.0, 1.2 },   // B1+
	{ 650.0, 30.0, 0.6 } };
    static const double viola[][3] = {
	{ 230.0, 25.0, 0.9 },
	{ 330.0, 30.0, 0.5 },
	{ 395.0, 35.0, 1.0 },
	{ 490.0, 35.0, 1.2 },
	{ 600.0, 30.0, 0.6 } };
    static const double cello[][3] = {
	{ 100.0, 25.0, 0.9 },
	{ 145.0, 30.0, 0.5 },
	{ 175.0, 35.0, 1.0 },
	{ 215.0, 35.0, 1.2 },
	{ 265.0, 30.0, 0.6 } };
    const double (*sig)[3] = NULL;

    if (type == "violin") {
	bf = new BodyFilter(type, 2500.0, 6500.0, 750.0, 10000.0, 0.05, 190.0, 1);
	sig = violin;
    }
    else if (type == "viola") {
	bf = new BodyFilter(type, 2000.0, 5500.0, 700.0, 9000.0, 0.06, 160.0, 2);
	sig = viola;
    }
    else if (type == "cello") {
	bf = new BodyFilter(type, 1300.0, 4500.0, 320.0, 7000.0, 0.09, 70.0, 3);
	sig = cello;
    }
    if (bf) {
	for (int i = 0; i < 5; i++) {
	    BodyMode m = { sig[i][0], sig[i][1], sig[i][2] };
	    bf->modes.insert(bf->modes.begin() + i, m);
	}
    }
    return bf;
}

BodyFilter::BodyFilter(string type, double hillFreq, double rolloffFreq,
		       double denseStart, double denseEnd, double density,
		       double highPassFreq, unsigned long long seed)
{
    this->type = type;
    this->highPassFreq = highPassFreq;

    // dense modes: random spacing with mean 1/density Hz, widening slowly with
    // frequency; random gains (log-normal, random sign) under a smooth envelope
    // with the bridge hill and a high-frequency roll-off
    BodyRandom rng(seed);
    double f = denseStart;
    while (true) {
	f += (-log(rng.uniform()) / density) * sqrt(1.0 + f / 3000.0);
	if (f >= denseEnd) break;
	double lh = log(f / hillFreq) / 0.45;
	double env = 0.35 + 0.9 * exp(-0.5 * lh * lh);
	double r = f / rolloffFreq;
	env /= sqrt(1.0 + r * r * r * r);
	double gain = env * exp(0.6 * rng.normal());
	if (rng.uniform() < 0.5) gain = -gain;
	BodyMode m = { f, 25.0 + 35.0 * rng.uniform(), gain };
	modes.push_back(m);
    }
}

void BodyFilter::filter(double *data, int n, double sr)
{
    int i, j;
    double *in = new double[n];
    memcpy(in, data, n * sizeof(double));
    memset(data, 0, n * sizeof(double));

    // each mode is a two-pole resonator whose impulse response is
    // gain * (f/Q) * exp(-pi f t / Q) * sin(2 pi f t), sampled at t = n/sr.
    // (A decaying sinusoid peaks at Q/(2 pi f) in the frequency domain, so the
    // f/Q factor makes `gain` the mode's peak response.)
    for (j = 0; j < modes.size(); j++) {
	double f = modes[j].freq;
	if (f >= 0.45 * sr) continue;
	double a = M_PI * f / modes[j].Q;
	double r = exp(-a / sr);
	double w = 2.0 * M_PI * f / sr;
	double c1 = 2.0 * r * cos(w);
	double c2 = -r * r;
	double b = modes[j].gain * (f / modes[j].Q) * r * sin(w);
	double y1 = 0.0, y2 = 0.0, x1 = 0.0;
	for (i = 0; i < n; i++) {
	    double y = c1 * y1 + c2 * y2 + b * x1;
	    data[i] += y;
	    y2 = y1;
	    y1 = y;
	    x1 = in[i];
	}
    }
    delete[] in;

    // second-order Butterworth high-pass: real bodies radiate little below the
    // air mode
    double K = tan(M_PI * highPassFreq / sr);
    double norm = 1.0 / (1.0 + sqrt(2.0) * K + K * K);
    double b0 = norm, b1 = -2.0 * norm, b2 = norm;
    double a1 = 2.0 * (K * K - 1.0) * norm;
    double a2 = (1.0 - sqrt(2.0) * K + K * K) * norm;
    double x1 = 0.0, x2 = 0.0, y1 = 0.0, y2 = 0.0;
    for (i = 0; i < n; i++) {
	double x = data[i];
	double y = b0 * x + b1 * x1 + b2 * x2 - a1 * y1 - a2 * y2;
	x2 = x1; x1 = x;
	y2 = y1; y1 = y;
	data[i] = y;
    }
}

void BodyFilter::apply(double *data, int n, double sr)
{
    // Scale the filter so that its impulse response has unit energy at 44.1 kHz
    // and its frequency response is the same at any sample rate. (The energy of
    // the sampled response grows in proportion to sr, and its gain at a given
    // frequency grows in proportion to sr too, so dividing by
    // sqrt(energy * sr / 44100) cancels both.) One second covers the decay of
    // every mode to well below -60 dB.
    int len = (int)sr;
    double *ir = new double[len];
    memset(ir, 0, len * sizeof(double));
    ir[0] = 1.0;
    filter(ir, len, sr);
    double energy = 0.0;
    for (int i = 0; i < len; i++) energy += ir[i] * ir[i];
    delete[] ir;

    logMessage(1, "Applying %s body filter (%d modes)", type.c_str(), (int)modes.size());
    filter(data, n, sr);
    if (energy > 0.0) {
	double scale = 1.0 / sqrt(energy * sr / 44100.0);
	for (int i = 0; i < n; i++) data[i] *= scale;
    }
}
