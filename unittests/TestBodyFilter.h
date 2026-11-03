/*
 * NeSS Framework Code
 *
 * Unit tests for BodyFilter
 */
#ifndef _TESTBODYFILTER_H_
#define _TESTBODYFILTER_H_

#include "cppunit/TestFixture.h"
#include "cppunit/TestSuite.h"
#include "cppunit/TestCaller.h"

#include "BodyFilter.h"

class TestBodyFilter : public CppUnit::TestFixture {
 public:
    virtual void setUp();
    virtual void tearDown();

    void testCreate();
    void testModes();
    void testUnitEnergy();
    void testResonance();
    void testSampleRate();
    void testParser();

    static CppUnit::Test *suite() {
        CppUnit::TestSuite *suiteOfTests = new CppUnit::TestSuite("BodyFilterTest");
        suiteOfTests->addTest(new CppUnit::TestCaller<TestBodyFilter>("testCreate", &TestBodyFilter::testCreate));
        suiteOfTests->addTest(new CppUnit::TestCaller<TestBodyFilter>("testModes", &TestBodyFilter::testModes));
        suiteOfTests->addTest(new CppUnit::TestCaller<TestBodyFilter>("testUnitEnergy", &TestBodyFilter::testUnitEnergy));
        suiteOfTests->addTest(new CppUnit::TestCaller<TestBodyFilter>("testResonance", &TestBodyFilter::testResonance));
        suiteOfTests->addTest(new CppUnit::TestCaller<TestBodyFilter>("testSampleRate", &TestBodyFilter::testSampleRate));
        suiteOfTests->addTest(new CppUnit::TestCaller<TestBodyFilter>("testParser", &TestBodyFilter::testParser));
        return suiteOfTests;
    }
};

#endif
