/*
 * NeSS Framework Code
 *
 * Copyright (c) The University of Edinburgh, 2014. All rights reserved.
 */

#include "Parser.h"

#include "Logger.h"

#include <iostream>
#include <fstream>
#include <sstream>
#include <cstdio>
#include <cstdlib>
#include <cstring>
using namespace std;

Parser::Parser(string filename)
{
    this->filename = filename;
}

Parser::~Parser()
{
}

int Parser::parseTextFile()
{
    int result = 1;

    ifstream in(filename.c_str());
    if (!in.good()) {
	logMessage(5, "Unable to open input file %s", filename.c_str());
	exit(1);
    }

    while ((in.good()) && (result)) {
	char linebuf[1000];
	in.getline(linebuf, 1000);

	// ignore comments
	char *hash = strchr(linebuf, '#');
	if (hash) *hash = 0;

	stringstream ss(linebuf, stringstream::in);
	string type;

	ss >> type;
	// skip only lines with no token at all. (Checking good() here used to
	// also skip any line consisting of a single token, because reading it
	// reaches end-of-line. That made Matlab-style files such as brass
	// scores, which have no spaces, look like valid but empty text files.)
	if (ss.fail()) continue;

	// call class-specific type handler
	result = handleItem(type, ss);
    }
    in.close();

    return result;
}

// don't make this abstract because not all subclasses implement their own version of it
int Parser::handleItem(string type, istream &in)
{
    return 0;
}
