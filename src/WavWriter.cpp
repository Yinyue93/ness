/*
 * NeSS Framework Code
 *
 * Copyright (c) The University of Edinburgh, 2012-2014. All rights reserved.
 */

#include "WavWriter.h"
#include "GlobalSettings.h"
#include "Logger.h"

#include <iostream>
#include <fstream>
#include <cmath>
using namespace std;

WavWriter::WavWriter(string filename)
{
    logMessage(1, "Initialising WavWriter for %s", filename.c_str());
    this->filename = filename;
}

WavWriter::~WavWriter()
{
}

/*
 * Small private random number generator for dither. Kept separate from
 * rand() so that dithering never changes the random sequence used by the
 * score generators or the brass noise input, and so output is repeatable.
 */
static unsigned int ditherState = 0x12345678u;
static inline double ditherRand()
{
    // xorshift32, returns uniform value in [0, 1)
    ditherState ^= ditherState << 13;
    ditherState ^= ditherState >> 17;
    ditherState ^= ditherState << 5;
    return ((double)ditherState) / 4294967296.0;
}

/*
 * Convert a sample (already scaled so that full scale is +/-32767) to
 * 16-bit, with TPDF dither (+/-1 LSB), rounding, and clamping so that an
 * out-of-range value saturates instead of wrapping around.
 */
static inline short quantise16(double v)
{
    double d = ditherRand() - ditherRand();
    double s = floor(v + d + 0.5);
    if (s > 32767.0) s = 32767.0;
    if (s < -32768.0) s = -32768.0;
    return (short)s;
}

/*
 * Linear-interpolation resampling of interleaved double data to 44.1kHz.
 * Same algorithm as before, but now done in floating point before
 * quantisation rather than on already-truncated 16-bit samples.
 * Returns a newly allocated buffer and sets len to the new length.
 */
static double *resampleTo44100(double *in, int &len, int sr, int channels)
{
    int newSize = (int)(((double)len*44100.0) / ((double)sr));
    double *out = new double[newSize * channels];
    double pos = 0.0;
    double incr = ((double)len) / ((double)newSize);
    int i, c;
    for (i = 0; i < newSize; i++) {
	// work out where we are in the old data
	int idx = (int)pos;
	double alpha = pos - ((double)idx);
	for (c = 0; c < channels; c++) {
	    if (idx >= (len-1)) {
		out[i*channels+c] = in[(len-1)*channels+c];
	    }
	    else {
		out[i*channels+c] = ((1.0 - alpha) * in[idx*channels+c]) +
		    (alpha * in[(idx+1)*channels+c]);
	    }
	}
	pos += incr;
    }
    len = newSize;
    return out;
}

bool WavWriter::writeMonoWavFile(Output *output, double max)
{
    logMessage(1, "Writing mono wav file to %s", filename.c_str());
    GlobalSettings *gs = GlobalSettings::getInstance();

    int sr = (int)gs->getSampleRate();
    int len = gs->getNumTimesteps();

    double *data = output->getData();

    // maxOut of 1.0 corresponds to digital full scale
    double scale = 0.0;
    if (max > 0.0) scale = (gs->getMaxOut() * 32767.0) / max;

    // normalise level
    double *scaled = new double[len];
    for (int i = 0; i < len; i++) {
	scaled[i] = data[i] * scale;
    }

    if ((gs->getResampleOuts()) && (sr != 44100)) {
	double *resampled = resampleTo44100(scaled, len, sr, 1);
	delete[] scaled;
	scaled = resampled;
	sr = 44100;
    }

    short *buffer = new short[len];
    for (int i = 0; i < len; i++) {
	buffer[i] = quantise16(scaled[i]);
    }
    delete[] scaled;

    bool result = writeMonoWav(buffer, len, sr);

    delete[] buffer;
    return result;
}

bool WavWriter::writeStereoMix(vector<Output*> *outputs, double max)
{
    logMessage(1, "Writing stereo mix wav file to %s", filename.c_str());
    GlobalSettings *gs = GlobalSettings::getInstance();

    int sr = (int)gs->getSampleRate();
    int len = gs->getNumTimesteps();

    // maxOut of 1.0 corresponds to digital full scale
    double scale = 0.0;
    if (max > 0.0) scale = (gs->getMaxOut() * 32767.0) / max;

    // mix and normalise
    double *scaled = new double[len * 2];
    for (int i = 0; i < len; i++) {
	double left = 0.0;
	double right = 0.0;
	for (int j = 0; j < outputs->size(); j++) {
	    // mix according to pan for that output
	    double v = outputs->at(j)->getData()[i];
	    left += outputs->at(j)->getLeftGain() * v;
	    right += outputs->at(j)->getRightGain() * v;
	}
	scaled[i*2] = left * scale;
	scaled[i*2+1] = right * scale;
    }

    if ((gs->getResampleOuts()) && (sr != 44100)) {
	double *resampled = resampleTo44100(scaled, len, sr, 2);
	delete[] scaled;
	scaled = resampled;
	sr = 44100;
    }

    short *buffer = new short[len * 2];
    for (int i = 0; i < (len * 2); i++) {
	buffer[i] = quantise16(scaled[i]);
    }
    delete[] scaled;

    bool result = writeStereoWav(buffer, len, sr);

    delete[] buffer;
    return result;
}

void WavWriter::initWavHeader(WavHeader *hdr, bool stereo, int sampleRate,
			      int len)
{
    logMessage(1, "initialising WavHeader: %d, %d, %d", (int)stereo, sampleRate, len);
    // FIXME: this won't work on a big endian system
    hdr->chunkID[0] = 'R';
    hdr->chunkID[1] = 'I';
    hdr->chunkID[2] = 'F';
    hdr->chunkID[3] = 'F';

    int nChannels = 1;
    if (stereo) nChannels = 2;

    hdr->chunkSize = 36 + (len * nChannels * 2);

    hdr->format[0] = 'W';
    hdr->format[1] = 'A';
    hdr->format[2] = 'V';
    hdr->format[3] = 'E';

    hdr->subChunkID[0] = 'f';
    hdr->subChunkID[1] = 'm';
    hdr->subChunkID[2] = 't';
    hdr->subChunkID[3] = ' ';

    hdr->subChunkSize = 16;
    hdr->audioFormat = 1;
    hdr->numChannels = nChannels;
    hdr->sampleRate = sampleRate;
    hdr->byteRate = sampleRate * nChannels * 2;
    hdr->blockAlign = nChannels * 2;
    hdr->bitsPerSample = 16;

    hdr->subChunkID2[0] = 'd';
    hdr->subChunkID2[1] = 'a';
    hdr->subChunkID2[2] = 't';
    hdr->subChunkID2[3] = 'a';

    hdr->subChunkSize2 = len * nChannels * 2;
}

bool WavWriter::writeMonoWav(short *data, int len, int sr)
{
    WavHeader hdr;

    initWavHeader(&hdr, false, sr, len);

    ofstream of(filename.c_str(), ios::out | ios::binary);
    if (!of.good()) {
	logMessage(5, "Error opening file %s for writing", filename.c_str());
	return false;
    }

    of.write((const char *)&hdr, sizeof(hdr));
    of.write((const char *)data, len * 2);

    of.close();
    return true;
}

bool WavWriter::writeStereoWav(short *data, int len, int sr)
{
    WavHeader hdr;

    initWavHeader(&hdr, true, sr, len);

    ofstream of(filename.c_str(), ios::out | ios::binary);
    if (!of.good()) {
	logMessage(5, "Error opening file %s for writing", filename.c_str());
	return false;
    }

    of.write((const char *)&hdr, sizeof(hdr));
    of.write((const char *)data, len * 2 * 2);

    of.close();
    return true;
}
