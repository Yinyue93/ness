/*
 * NeSS Framework Code
 *
 * Copyright (c) The University of Edinburgh, 2015. All rights reserved.
 */

#include "MatlabFunction_StringDefGen.h"
#include "Logger.h"

#include <cmath>
#include <cstdlib>
using namespace std;

#ifndef M_PI
#define M_PI 3.1415926536
#endif

MatlabFunction_StringDefGen::MatlabFunction_StringDefGen()
    : MatlabFunction("string_def_gen", 7, 8)
{
}

MatlabFunction_StringDefGen::~MatlabFunction_StringDefGen()
{
}

bool MatlabFunction_StringDefGen::execute(MatlabCellContent *result)
{
    logMessage(1, "Executing Matlab function string_def_gen");

    // check parameters
    if (!checkParameter2DArray(0, 2)) return false;
    if (!checkParameter1DArray(1)) return false;
    if (!checkParameter1DArray(2)) return false;
    if (!checkParameter1DArray(3)) return false;
    if (!checkParameterScalar(4)) return false;
    if (!checkParameter1DArray(5)) return false;
    if (!checkParameter1DArray(6)) return false;

    // work out number of strings
    int string_num = params[1].array.width;

    // check it matches the other per-string parameters
    if ((params[2].array.width != string_num) ||
	(params[3].array.width != string_num) ||
	(params[5].array.width != string_num) ||
	(params[6].array.width != string_num)) {
	logMessage(5, "Error: array sizes must match for string_def_gen");
	return false;
    }

    // optional 8th parameter: tension in Newtons for each string
    bool haveTension = (paramCount >= 8);
    if (haveTension) {
	if (!checkParameter1DArray(7)) return false;
	if (params[7].array.width != string_num) {
	    logMessage(5, "Error: tension array size must match number of strings for string_def_gen");
	    return false;
	}
    }

    int lowTensionCount = 0;
    double lowestTension = 1e30;

    // allocate the output array
    result->type = CELL_ARRAY;
    result->array.width = 7;
    result->array.height = string_num;
    result->array.data = new double[7 * string_num];

    int i;
    // generate the data for each string
    double L = params[4].scalar.value;
    for (i = 0; i < string_num; i++) {
	// handle material
	int matidx = ((int)params[2].array.data[i]) - 1;
	double E = params[0].array.data[(matidx * 2) + 1];
	double rho = params[0].array.data[(matidx * 2) + 0];

	// compute frequency
	double note = params[1].array.data[i];
	double freq = 261.6 * pow(2.0, note / 12.0);

	double inharmonicity = params[3].array.data[i];

	double r, A, T;
	if (haveTension) {
	    /*
	     * Tension given. Solve for the radius r and an effective density
	     * so that the string has the requested pitch, tension and
	     * inharmonicity B, using the material's Young's modulus:
	     *
	     *   T = 4 L^2 f^2 rho A,   B = pi^2 E I / (T L^2),   I = pi r^4 / 4
	     *   =>  r^4 = 4 T L^2 B / (pi^3 E),   rho = T / (4 pi L^2 f^2 r^2)
	     *
	     * For a plain string with a realistic B the density comes out
	     * close to the material's. For a wound string it comes out higher,
	     * because the winding adds mass but little bending stiffness. The
	     * model only depends on rho*A and E*I, so this "equivalent" string
	     * behaves like the real wound one.
	     */
	    T = params[7].array.data[i];
	    if ((T <= 0.0) || (inharmonicity <= 0.0)) {
		logMessage(5, "Error: tension and inharmonicity must be positive in string_def_gen");
		return false;
	    }
	    r = pow((4.0 * T * L * L * inharmonicity) / (M_PI * M_PI * M_PI * E), 0.25);
	    A = M_PI * r * r;
	    rho = T / (4.0 * L * L * freq * freq * A);
	    logMessage(1, "string_def_gen: string %d, T=%f N, r=%e m, effective density=%f",
		       i+1, T, r, rho);
	}
	else {
	    // original behaviour: solid string of the given material. The
	    // radius is fixed by the inharmonicity, and the tension follows
	    r = ((4.0 * L * L) / M_PI) * freq * sqrt(rho * inharmonicity / E);
	    A = M_PI * r * r;
	    T = (4.0 * L * L) * rho * A * freq * freq;

	    if (T < 20.0) {
		lowTensionCount++;
		if (T < lowestTension) lowestTension = T;
	    }
	}

	// fetch loss parameters
	double T60_0 = params[5].array.data[i];
	double T60_1000 = params[6].array.data[i];

	result->array.data[7*i + 0] = L; // length
	result->array.data[7*i + 1] = E;
	result->array.data[7*i + 2] = T;
	result->array.data[7*i + 3] = r;
	result->array.data[7*i + 4] = rho;
	result->array.data[7*i + 5] = T60_0;
	result->array.data[7*i + 6] = T60_1000;
    }

    // the instrument file may be parsed more than once (format detection),
    // so only print the warning the first time
    static bool lowTensionWarned = false;
    if ((lowTensionCount > 0) && (!lowTensionWarned)) {
	lowTensionWarned = true;
	logMessage(5, "Warning: string_def_gen produced %d string(s) with very low tension "
		   "(lowest %.2f N; real guitar strings are around 60-140 N). Plucks will "
		   "displace these strings far more than a real instrument. Pass the "
		   "tensions as an optional 8th argument for realistic strings.",
		   lowTensionCount, lowestTension);
    }

    return true;
}

