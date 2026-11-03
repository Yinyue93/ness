/*
 * NeSS Framework Code
 *
 * Unit tests for BodyFilter
 */

#include "TestBodyFilter.h"
#include "InstrumentParser.h"
#include "Instrument.h"

#include <cmath>
#include <cstdio>
#include <fstream>
using namespace std;

void TestBodyFilter::setUp()
{
}

void TestBodyFilter::tearDown()
{
}

// steady-state amplitude of the filter's response to a sine at freq
static double sineGain(BodyFilter *bf, double freq, double sr)
{
    int n = (int)(1.5 * sr);
    double *x = new double[n];
    for (int i = 0; i < n; i++) x[i] = sin(2.0 * M_PI * freq * (double)i / sr);
    bf->apply(x, n, sr);
    double peak = 0.0;
    for (int i = n - (int)(0.25 * sr); i < n; i++) {   // after the transient
	if (fabs(x[i]) > peak) peak = fabs(x[i]);
    }
    delete[] x;
    return peak;
}

void TestBodyFilter::testCreate()
{
    CPPUNIT_ASSERT(BodyFilter::create("none") == NULL);
    CPPUNIT_ASSERT(BodyFilter::create("") == NULL);
    CPPUNIT_ASSERT(BodyFilter::create("guitar") == NULL);
    CPPUNIT_ASSERT(BodyFilter::isValidType("none"));
    CPPUNIT_ASSERT(BodyFilter::isValidType("cello"));
    CPPUNIT_ASSERT(!BodyFilter::isValidType("guitar"));

    const char *types[] = { "violin", "viola", "cello" };
    double a0[] = { 275.0, 230.0, 100.0 };
    for (int t = 0; t < 3; t++) {
	BodyFilter *bf = BodyFilter::create(types[t]);
	CPPUNIT_ASSERT(bf != NULL);
	CPPUNIT_ASSERT(bf->getType() == types[t]);
	CPPUNIT_ASSERT(bf->getModes()->size() > 100);
	CPPUNIT_ASSERT_DOUBLES_EQUAL(a0[t], bf->getModes()->at(0).freq, 1e-12);
	delete bf;
    }
}

void TestBodyFilter::testModes()
{
    // the modes are generated deterministically, ascending in frequency.
    // These values pin the viola body as it was tuned by ear; if they change,
    // the instrument sounds different.
    BodyFilter *a = BodyFilter::create("viola");
    BodyFilter *b = BodyFilter::create("viola");
    vector<BodyMode> *ma = a->getModes(), *mb = b->getModes();
    CPPUNIT_ASSERT_EQUAL(ma->size(), mb->size());
    for (int i = 0; i < ma->size(); i++) {
	CPPUNIT_ASSERT_EQUAL(ma->at(i).freq, mb->at(i).freq);
	CPPUNIT_ASSERT_EQUAL(ma->at(i).Q, mb->at(i).Q);
	CPPUNIT_ASSERT_EQUAL(ma->at(i).gain, mb->at(i).gain);
	if (i > 0) CPPUNIT_ASSERT(ma->at(i).freq > ma->at(i-1).freq);
	CPPUNIT_ASSERT(ma->at(i).Q >= 25.0 && ma->at(i).Q <= 60.0);
    }
    CPPUNIT_ASSERT_EQUAL(320, (int)ma->size());
    CPPUNIT_ASSERT_DOUBLES_EQUAL(709.72880368469976, ma->at(5).freq, 1e-9);
    CPPUNIT_ASSERT_DOUBLES_EQUAL(0.28388391643285155, ma->at(5).gain, 1e-12);
    delete a;
    delete b;
}

void TestBodyFilter::testUnitEnergy()
{
    // at 44.1 kHz the impulse response has unit energy
    BodyFilter *bf = BodyFilter::create("violin");
    int n = 44100;
    double *x = new double[n];
    for (int i = 0; i < n; i++) x[i] = 0.0;
    x[0] = 1.0;
    bf->apply(x, n, 44100.0);
    double e = 0.0;
    for (int i = 0; i < n; i++) e += x[i] * x[i];
    CPPUNIT_ASSERT_DOUBLES_EQUAL(1.0, e, 1e-9);

    // silence in, silence out
    for (int i = 0; i < n; i++) x[i] = 0.0;
    bf->apply(x, n, 44100.0);
    for (int i = 0; i < n; i++) CPPUNIT_ASSERT_EQUAL(0.0, x[i]);
    delete[] x;
    delete bf;
}

void TestBodyFilter::testResonance()
{
    // the viola body's B1+ mode (490 Hz) passes much more than a frequency
    // well below the air mode, which the high-pass removes
    BodyFilter *bf = BodyFilter::create("viola");
    double g490 = sineGain(bf, 490.0, 44100.0);
    double g40 = sineGain(bf, 40.0, 44100.0);
    CPPUNIT_ASSERT(g490 > 30.0 * g40);
    delete bf;
}

void TestBodyFilter::testSampleRate()
{
    // the frequency response doesn't depend on the sample rate
    BodyFilter *bf = BodyFilter::create("viola");
    double freqs[] = { 230.0, 490.0, 2000.0 };
    for (int i = 0; i < 3; i++) {
	double g44 = sineGain(bf, freqs[i], 44100.0);
	double g176 = sineGain(bf, freqs[i], 176400.0);
	double db = 20.0 * log10(g176 / g44);
	CPPUNIT_ASSERT_DOUBLES_EQUAL(0.0, db, 0.5);
    }
    delete bf;
}

void TestBodyFilter::testParser()
{
    const char *fn = "testbody_instrumentfile.m";
    const char *bodies[] = { "body = 'cello';", "", "body = 'none';", "body = 'guitar';" };
    for (int t = 0; t < 4; t++) {
	{
	    ofstream f(fn);
	    f << "Fs = 44100;\nNstrings = 1;\n" << bodies[t] << "\n"
	      << "strings = struct;\nstrings(1).f0 = 220;\nstrings(1).rho = 0.0015;\n"
	      << "strings(1).rad = 0.0003;\nstrings(1).E = 2e10;\nstrings(1).T60 = [10;5];\n"
	      << "strings(1).L = 0.69;\n";
	}
	Instrument *instr = InstrumentParser::parseInstrument(fn, "bowedstring");
	if (t == 3) {
	    CPPUNIT_ASSERT(instr == NULL);      // unknown body is an error
	}
	else {
	    CPPUNIT_ASSERT(instr != NULL);
	    if (t == 0) {
		CPPUNIT_ASSERT(instr->getBody() != NULL);
		CPPUNIT_ASSERT(instr->getBody()->getType() == "cello");
	    }
	    else {
		CPPUNIT_ASSERT(instr->getBody() == NULL);
	    }
	    delete instr;
	}
    }
    remove(fn);
}
