#!/usr/bin/env python
# -*- coding: utf-8 -*-
#
# Copyright (c) 2014 Michael Krause ( http://krause-software.com/ ).

# You are free to use this code under the MIT license:
# http://opensource.org/licenses/MIT

"""Tests for xcodeprojer."""

from __future__ import print_function

import sys
import unittest
import datetime
import subprocess
import os
import glob
from os.path import abspath, dirname, splitext
import calendar as cal
import re
import argparse
from io import StringIO
import json

# Set up the Python path so we find the xcodeprojer module in the parent directory
# relative to this file.
sys.path.insert(1, dirname(dirname(abspath(__file__))))

import xcodeprojer
from xcodeprojer import bytestr, unistr

u = unistr

PY2 = sys.version_info[0] == 2
PY3 = sys.version_info[0] == 3


if PY2:
    text_type = unicode
    binary_type = str
else:
    text_type = str


TEST_AGAINST_PLUTIL = False

# The unicode tests should be as thorough as possible but if we'd
# use characters which have a composed as well as a decomposed unicode form
# the relationship between our filesystem and our development tools (notably git)
# becomes strained to a point that even running a diff becomes non-trivial.
# We rather choose a clean git repository over ambiguous unicode representations,
# therefore no umlauts etc. in the filenames.
INTL_PROJECT_FILENAME = 'data/IŋƫƐrnætiønæl X©ødǝ ¶®øjæƈt.xcodeproj/project.pbxproj'
MINI_PROJECT_FILENAME = 'data/MiniProject/MiniProject.xcodeproj/project.pbxproj'


PROJECT_TEMPLATE = """// !$*UTF8*$!
{%(toplevel)s
\tobjectVersion = %(objectVersion)s;
\tobjects = {
\t%(objects)s};
}
"""

re_unisubst = re.compile('[^\x00-\x7f]')
re_uniglob = re.compile(r'\*+')


def unifilename(filename):
    if isinstance(filename, text_type) or PY3:
        return filename
    try:
        return filename.decode(sys.getfilesystemencoding())
    except UnicodeEncodeError:
        return filename.decode('utf-8')


def sysfilename(filename):
    if not isinstance(filename, text_type) or PY3:
        return filename
    try:
        return filename.encode(sys.getfilesystemencoding())
    except UnicodeEncodeError:
        return filename.encode('utf-8')


def here():
    return dirname(abspath(unifilename(__file__)))


def rel(filename):
    fn = os.path.join(here(), unistr(filename))
    try:
        if os.path.exists(fn):
            return fn
    except UnicodeEncodeError:
        pass
    return findfile(fn)


def uniglob(path):
    """This function transforms a path into a glob pattern
    in which every non-ascii character of the path is replaced by a '*'.
    Finally consecutive '*' characters are compressed into a single one.
    """
    filepath = os.path.normpath(path)
    pattern = re_unisubst.sub('*', filepath)
    pattern = re_uniglob.sub('*', pattern)
    return pattern


def findfile(filename):
    matches = glob.glob(uniglob(sysfilename(filename)))
    assert len(matches) == 1
    return matches[0]


def intl_filename():
    return rel(INTL_PROJECT_FILENAME)


def template(objectversion=46, objects='', top=''):
    return PROJECT_TEMPLATE % {'objectVersion': objectversion,
                               'objects': objects,
                               'toplevel': top}


def parse(prj, report=True, fp=None, **kwargs):
    root, parseinfo = xcodeprojer.parse(prj, **kwargs)
    if report:
        xcodeprojer.report_parse_status(root, parseinfo, filename=None, fp=fp)
    return root, parseinfo


def sparse(prj, **kwargs):
    """Parse without additional error reporting.
    """
    return parse(prj, report=False, **kwargs)


def unparse(root, **kwargs):
    return xcodeprojer.unparse(root, **kwargs).decode('utf-8')


def read_file(filename):
    with open(filename, 'rb') as f:
        return f.read()


def read_project(relpath):
    filename = rel(relpath)
    prj = read_file(filename)
    prj = unistr(prj)
    return prj, filename


def read_intl_project():
    return read_project(INTL_PROJECT_FILENAME)


def read_mini_project():
    return read_project(MINI_PROJECT_FILENAME)


def find_isa(node, isa):
    for v in node.values():
        if v.get('isa') == isa:
            return v
    return None


def run_args(*args):
    outbuf, errbuf = StringIO(), StringIO()
    with RedirectStdStreams(stdout=outbuf, stderr=errbuf):
        parser = xcodeprojer.cmdline_parser(ErrorRecordingArgumentParser)
        args = parser.parse_args(*args)
        ret = xcodeprojer.run_with_args(args, parser)
    return ret, outbuf.getvalue(), errbuf.getvalue()


class ParserTestCase(unittest.TestCase):

    XML_TEMPLATE = """<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>objectVersion</key>
    <string>46</string>
    <key>objects</key>
    <dict/>
    <key>list</key>
    <array>
        <string>1</string>
        <string>&gt;'.'&lt;</string>
    </array>
</dict>
</plist>"""

    def test_array(self):
        prj = template(top="""an_array = (1, 2, 3,);""")
        root, parseinfo = sparse(prj)
        self.assertEqual(root['an_array'], ['1', '2', '3'])

    def test_array_without_terminator(self):
        prj = template(top="""an_array = (1, 2, 3);""")
        root, parseinfo = sparse(prj)
        self.assertEqual(root['an_array'], ['1', '2', '3'])

    def test_array_without_separators(self):
        prj = template(top="""an_array = (1 2 3);""")
        root, parseinfo = sparse(prj)
        self.assertIsNone(root)

    def test_dictionary(self):
        prj = template(top="""a_dictionary = { KEY = VALUE; };""")
        root, parseinfo = sparse(prj)
        self.assertEqual(root['a_dictionary'], {'KEY': 'VALUE'})

    def test_dictionary_without_terminator(self):
        prj = template(top="""a_dictionary = { KEY = VALUE };""")
        root, parseinfo = sparse(prj)
        self.assertIsNone(root)

    def test_unparse(self):
        prj = template(top="""an_array  = (1 ,  2  ,  3);""")
        root, parseinfo = sparse(prj)
        assert root

        out = unparse(root)
        a = """
	an_array = (
		1,
		2,
		3,
	);"""
        self.assertEqual(out, template(top=a))

    def test_xml_parse(self):
        xml = self.XML_TEMPLATE
        root, parseinfo = parse(xml)
        self.assertEqual(root, {'objects': {}, 'list': ['1', '>\'.\'<'], 'objectVersion': '46'})

    def test_xml_parse_error(self):
        xml = self.XML_TEMPLATE
        xml = xml.replace('<plist version="1.0">', '<plist version=1.0">')
        buf = StringIO()
        root, parseinfo = parse(xml, report=True, fp=buf)
        self.assertIsNone(root)
        self.assertEqual(buf.getvalue(), 'File <stdin>, line 3, column 15\n'
                                         '<plist version=1.0">\n'
                                         '              ^\n'
                                         'Error: parsing XML failed\n')

    def test_recursionlimit(self):
        prj, filename = read_mini_project()
        one_comment = '/* Begin PBXBuildFile section */\n'
        for opener in '(', '{':
            many_dicts = one_comment + 200 * opener
            modprj = prj.replace(one_comment, many_dicts)
            root, parseinfo = parse(modprj, report=False, format='xcode', parsertype='classic')
            self.assertIsNone(root)


class ParserErrorTestCase(unittest.TestCase):

    def test_space_in_unquoted(self):
        prj, filename = read_mini_project()
        pos = prj.find('DeploymentPostprocessing')
        prj = prj[:pos] + ' ' + prj[pos:]

        for format, parsertype in [(None, 'normal'), ('xcode', 'fast'), ('xcode', 'classic')]:
            buf = StringIO()
            root, parseinfo = parse(prj, format=format, parsertype=parsertype,
                                 report=True, fp=buf)
            self.assertIsNone(root)
            report = unistr(buf.getvalue())

            if parsertype == 'fast':
                self.assertTrue(report.find('Error: parsing Xcode plist via JSON failed') >= 0)
            else:
                self.assertEqual(report, 'File <stdin>, line 21, column 24\n'
                                         '\t\t\trunOnlyFor DeploymentPostprocessing = 1;\n'
                                         '\t\t\t           ^~~~~~~~~~~~~~~~~~~~~~~~\n'
                                         'Error: parsing Xcode plist classically failed\n')

    def test_outoftokens(self):
        prj, filename = read_mini_project()
        closingbracepos = prj.rfind('}')
        # Without a closing brace the parsers should run out of tokens
        # and report the parse error.
        prj = prj[:closingbracepos]
        expected_line_columns = {
            (None, 'normal'): (168, 62),
            ('xcode', 'fast'): (1, 2994),
            ('xcode', 'classic'): (168, 62),
        }
        for format, parsertype in [(None, 'normal'), ('xcode', 'fast'), ('xcode', 'classic')]:
            buf = StringIO()
            root, parseinfo = parse(prj, format=format, parsertype=parsertype,
                                    report=True, fp=buf)
            self.assertIsNone(root)
            report = buf.getvalue()
            expline, expcolumn = expected_line_columns[(format, parsertype)]
            numbers = [int(x) for x in re.split(r'\D+', report) if x]
            line, column = numbers[:2]
            self.assertEqual(line, expline)
            # The JSON parser column report differs between Python versions.
            self.assertTrue(column == expcolumn or column == expcolumn + 1)


class IntlTestCase(unittest.TestCase):

    def test_i18n(self):
        prj, filename = read_intl_project()
        prj = bytestr(prj)
        prjname = xcodeprojer.projectname_for_path(filename)

        for parsertype in ['fast', 'classic']:
            root, parseinfo = parse(prj, format='xcode', parsertype=parsertype)
            self.assertIsNotNone(root, "parsing with parsertype %s failed" % parsertype)
            pbxproject = find_isa(root['objects'], 'PBXProject')
            orgname = pbxproject['attributes']['ORGANIZATIONNAME']
            self.assertEqual(orgname, u('🎫'),
                             "unexpected ORGANIZATIONNAME '%s' after parsing with parsertype %s."
                             % (pbxproject['attributes']['ORGANIZATIONNAME'], parsertype))

            output = xcodeprojer.unparse(root, format='xcode', projectname=prjname)
            if prj != output:
                xcodeprojer.print_diff(prj, output, filename=filename)

            self.assertEqual(prj, output)

    def check_format_tree(self, format):
        prj, filename = read_intl_project()
        prj = bytestr(prj)
        prjname = xcodeprojer.projectname_for_path(filename)
        plistroot, parseinfo = parse(prj, format='xcode')
        self.assertIsNotNone(plistroot)

        fmtfilename = os.path.join(dirname(filename), 'project.%s' % format)
        formattext = read_file(fmtfilename)
        root, parseinfo = parse(formattext, format=format)
        self.assertIsNotNone(root)
        self.assertEqual(root, plistroot)

        root, parseinfo = parse(prj)
        output = xcodeprojer.unparse(root, format=format, projectname=prjname)
        if formattext != output:
            xcodeprojer.print_diff(formattext, output, filename=filename)
        self.assertEqual(formattext, output)

    def test_xml(self):
        self.check_format_tree('xml')

    def test_json(self):
        self.check_format_tree('json')

    def test_unicode_in_unquoted(self):
        prj, filename = read_mini_project()
        prj = prj.replace(u('ORGANIZATIONNAME = "ACME Inc.";'),
                          u('ORGANIZATIONNAME = 🍏;'))
        prj = bytestr(prj)
        for format, parsertype in [(None, 'normal'), ('xcode', 'fast'), ('xcode', 'classic')]:
            buf = StringIO()
            root, parseinfo = parse(prj, format=format, parsertype=parsertype,
                                    report=True, fp=buf)
            self.assertIsNone(root)


class PlutilTestCase(unittest.TestCase):

    # Verifying that our XML generator matches plutil(1)
    # would only check if plutil has changed and slow down the unit tests.
    def test_plutil(self):
        if TEST_AGAINST_PLUTIL:
            filename = intl_filename()
            fmtfilename = os.path.join(dirname(filename), 'project.json')
            jsondata = read_file(fmtfilename)

            fmtfilename = os.path.join(dirname(filename), 'project.xml')
            ourxml = read_file(fmtfilename)

            plutil_xml = plutil(jsondata, '-convert', 'xml1', '-o', '-')
            self.assertEqual(ourxml, plutil_xml)

# ---------------------------------------------------------------
# This is RedirectStdStreams from an answer by Rob Cowie on
# http://stackoverflow.com/questions/6796492/python-temporarily-redirect-stdout-stderr/6796752#6796752
# which is used to record the output of xcoderprojer as if called from the command line.


class RedirectStdStreams(object):
    def __init__(self, stdout=None, stderr=None):
        self._stdout = stdout or sys.stdout
        self._stderr = stderr or sys.stderr

    def __enter__(self):
        self.old_stdout, self.old_stderr = sys.stdout, sys.stderr
        self.old_stdout.flush(); self.old_stderr.flush()
        sys.stdout, sys.stderr = self._stdout, self._stderr

    def __exit__(self, exc_type, exc_value, traceback):
        self._stdout.flush(); self._stderr.flush()
        sys.stdout = self.old_stdout
        sys.stderr = self.old_stderr

# ---------------------------------------------------------------


class ErrorRecordingArgumentParser(argparse.ArgumentParser):

    def __init__(self, *args, **kwargs):
        super(ErrorRecordingArgumentParser, self).__init__(*args, **kwargs)
        self.testerrors = []

    def error(self, message):
        self.testerrors.append(message)


class CmdlineTestCase(unittest.TestCase):

    def test_convert(self):
        prj, filename = read_intl_project()
        ret, outtxt, errtxt = run_args(['-o', '-', '--convert', 'xcode', filename])
        self.assertEqual(ret, xcodeprojer.OK)
        self.assertEqual(outtxt, prj)

    def test_convert_multiple_filenames(self):
        prj, filename = read_intl_project()
        ret, outtxt, errtxt = run_args(['-o', '-', '--convert', 'xcode', filename, filename])
        self.assertEqual(ret, xcodeprojer.ERROR)
        self.assertEqual(outtxt, '')

    def test_lint(self):
        filename = rel(INTL_PROJECT_FILENAME)
        ret, outtxt, errtxt = run_args(['--lint', '-o', '-', filename])
        self.assertEqual(ret, xcodeprojer.OK)
        self.assertEqual(outtxt, '')

        filename = splitext(filename)[0] + '.json'
        ret, outtxt, errtxt = run_args(['--lint', '-o', '-', filename])
        self.assertEqual(ret, xcodeprojer.LINT_FAILED)
        expectedend = 'is in json which is nothing that Xcode can read.\n'
        self.assertEqual(outtxt[-len(expectedend):], expectedend)

        filename = splitext(filename)[0] + '.xml'
        ret, outtxt, errtxt = run_args(['--lint', '-o', '-', filename])
        self.assertEqual(ret, xcodeprojer.LINT_FAILED)
        expectedend = 'is in XML which is a clearly a failed lint.\n'
        self.assertEqual(outtxt[-len(expectedend):], expectedend)

    def test_gidsplit(self):
        ret, outtxt, errtxt = run_args(['--gidsplit', '4CDE96A219B3613C009DF310'])
        self.assertEqual(ret, 0)

    def test_giddump(self):
        filename = rel(INTL_PROJECT_FILENAME)
        self.assertTrue(os.path.exists(filename))
        ret, outtxt, errtxt = run_args(['--gid-format', 'json', '--giddump', filename])
        self.assertEqual(ret, 0)

        # Only test a part of the dump.
        root = json.loads(outtxt)
        self.assertEqual(len(root['gids']), 18)
        gid = '4C36A8C719A0D91D00F6C76D'
        for obj in root['gids']:
            if obj['gid'] == gid:
                jobj = json.dumps(obj, sort_keys=True, indent=20, separators=(',', ':'))
                self.assertEqual(jobj, r"""{
                    "comment":"Build configuration list for PBXProject \"I\u014b\u01ab\u0190rn\u00e6ti\u00f8n\u00e6l X\u00a9\u00f8d\u01dd \u00b6\u00ae\u00f8j\u00e6\u0188t\"",
                    "date":"2014-08-17T12:35:41Z",
                    "gid":"4C36A8C719A0D91D00F6C76D",
                    "pid":54,
                    "random":16172909,
                    "seq":43207,
                    "user":76
}""")
                break
        else:
            self.assertFalse("The object %r cound not be found." % gid)

# ---------------------------------------------------------------------
#
# plutil(1) can be used to verify correct translation for XML and JSON.
#

def plutil(inputdata, *args):
    """
    e.g.:
        plutil(inputdata, '-convert', 'xml1', '-o', '-')
    """
    try:
        plargs = ['/usr/bin/plutil'] + list(args) + ['-']
        client = subprocess.Popen(plargs, stdin=subprocess.PIPE, stdout=subprocess.PIPE)
        output = client.communicate(input=inputdata)[0]
        return output
    except OSError:
        return


# ---------------------------------------------------------------

class GlobalIDTestCase(unittest.TestCase):

    def setUp(self):
        pass

    def tearDown(self):
        pass

    def timefunc(self):
        t = self.seconds
        self.seconds += self.seconds_increment
        return t

    def test_globalid(self):
        # When the generator is initialized this timestamp feeds into the random generator.
        # On the first call of generate() the timefunc is called for the second time,
        # that is why the first gid has a timestamp 10 seconds later than the time we specified.
        utctimestamp = "2014-07-29 17:04:20Z"
        testdate = datetime.datetime.strptime(utctimestamp, "%Y-%m-%d %H:%M:%SZ")
        secs = xcodeprojer.UniqueXcodeIDGenerator.reftime(cal.timegm(testdate.utctimetuple()))
        self.seconds = secs
        self.seconds_increment = 10

        gen = xcodeprojer.UniqueXcodeIDGenerator(username='unrecompiled', pid=56007, refdatefunc=self.timefunc)
        if PY2:
            self.assertEqual(gen.generate(), '4CC7BE4419880B9E009C9D7C')
            self.assertEqual(gen.generate(), '4CC7BE4519880BA8009C9D7C')
            self.assertEqual(gen.generate(), '4CC7BE4619880BB2009C9D7C')
            self.assertEqual(gen.generate(), '4CC7BE4719880BBC009C9D7C')
        else:
            # Python 3 has a different random number generator
            self.assertEqual(gen.generate(), '4CC742AD19880B9E00393AF0')
            self.assertEqual(gen.generate(), '4CC742AE19880BA800393AF0')
            self.assertEqual(gen.generate(), '4CC742AF19880BB200393AF0')
            self.assertEqual(gen.generate(), '4CC742B019880BBC00393AF0')

    def test_gidsplit(self):
        buf = StringIO()
        xcodeprojer.gidsplit(['4CC7BE4419880B9E009C9D7C', '4CC7BE4719880BBC009C9D7C'], buf=buf)
        text = buf.getvalue()
        expected = '2014-07-29T17:04:30Z  76 199   10263932 48708 4CC7BE4419880B9E009C9D7C\n' \
                   '2014-07-29T17:05:00Z  76 199   10263932 48711 4CC7BE4719880BBC009C9D7C\n'
        self.assertEqual(text, expected)

        buf = StringIO()
        xcodeprojer.gidsplit(['4CC7BE4419880B9E009C9D7C', '4CC7BE4719880BBC009C9D7C'], format='json', buf=buf)
        text = buf.getvalue()
        expected = """{
  "gids":[
    {
      "date":"2014-07-29T17:04:30Z",
      "gid":"4CC7BE4419880B9E009C9D7C",
      "pid":199,
      "random":10263932,
      "seq":48708,
      "user":76
    },
    {
      "date":"2014-07-29T17:05:00Z",
      "gid":"4CC7BE4719880BBC009C9D7C",
      "pid":199,
      "random":10263932,
      "seq":48711,
      "user":76
    }
  ]
}
"""
        self.assertEqual(text, expected)

# ---------------------------------------------------------------

if __name__ == '__main__':
    unittest.main()
