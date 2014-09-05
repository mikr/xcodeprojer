#!/usr/bin/env python
# -*- coding: utf-8 -*-
#
# Copyright (c) 2014 Michael Krause ( http://krause-software.com/ ).

# You are free to use this code under the MIT license:
# http://opensource.org/licenses/MIT

"""
Check what characters Xcode accepts in quoted or unquoted strings.

We modify a project.pbxproj repeatedly and run xcodebuild -list
to see if Xcode refuses to parse the modified project.
From the result we get acceptable character ranges.

The MiniProject is a template that actually contains a test program
that we could actually try to build to see if the project
still makes sense to Xcode after the changes apply.

Additionally test for various edge cases to see what Xcode
accepts as valid projects to accept or reject them likewise
in our parsers.
"""

from __future__ import print_function

import sys
import argparse
import os
import codecs
import tempfile
import subprocess
from os.path import abspath, basename, dirname, join


# Set up the Python path so we find the xcodeprojer module in the parent directory
# relative to this file.
sys.path.insert(1, dirname(dirname(abspath(__file__))))

import xcodeprojer
from xcodeprojer import bytestr, unistr

PY2 = sys.version_info[0] == 2
PY3 = sys.version_info[0] == 3

XCODEBUILD = '/usr/bin/xcodebuild'
MINI_PROJECT_FILENAME = 'data/MiniProject/MiniProject.xcodeproj/project.pbxproj'


OK = True
ERR = False

diverse_variations = [
    [ERR, 'missing_semicolon_terminator', 'SDKROOT = macosx10.9;', 'SDKROOT = macosx10.9'],
    [OK,  'missing_comma_terminator', ',\n\t\t\t);', '\n\t\t\t);'],
    [OK,  'whitespace_before_utf8_header', '// !$*UTF8*$!', '\n// !$*UTF8*$!'],
    [ERR, 'unquoted_unicode_apple', 'ORGANIZATIONNAME = "ACME Inc.";', 'ORGANIZATIONNAME = 🍏;'],
    [OK,  'quoted_unicode_apple', 'ORGANIZATIONNAME = "ACME Inc.";', 'ORGANIZATIONNAME = "🍏";'],
]


def rel(filename):
    return os.path.join(dirname(abspath(__file__)), filename)


def _color(col, text):
    if not text:
        return text
    return '\x1b[0;0;%dm%s\x1b[0;0m' % (col, text)


def red(text):
    return _color(31, text)


def green(text):
    return _color(32, text)


def xcodebuild_list(pbxfilename):
    xcodeargs = [XCODEBUILD, '-list', '-project', dirname(pbxfilename)]
    client = subprocess.Popen(xcodeargs,
                              stdin=subprocess.PIPE,
                              stdout=subprocess.PIPE,
                              stderr=subprocess.PIPE)
    stdout, stderr = client.communicate()
    return client.returncode, stdout, stderr


def list_project(pbxfilename, data):
    with codecs.open(pbxfilename, 'w', encoding='utf-8') as f:
        f.write(data)
    return xcodebuild_list(pbxfilename)


def safe_replace(text, a, b):
    a = unistr(a)
    b = unistr(b)
    result = text.replace(a, b)
    if result == text:
        raise ValueError("Error: replacing '%s' with '%s' did not change the text." % (a, b))
    return result


def report(text, a, b, ret, expected):
    if expected == (ret == 0):
        exptext = green('as expected: ')
    else:
        exptext = red(' unexpected: ')
    if ret == 0:
        print(exptext + " OK : " + green(text))
        bcol = green
    else:
        print(exptext + "ERR : " + red(text))
        bcol = red
    print("    when we replace '" + green(a) + "'")
    print("               with '" + bcol(b) + "'")


def parsable_variation(pbxdata, expected, desc, a, b):
    pbxfilename, data = pbxdata
    if sys.platform == 'darwin' and os.path.exists(XCODEBUILD):
        ret, stdout, stderr = list_project(pbxfilename, safe_replace(data, a, b))
    else:
        print("Skipping 'xcodebuild -list' because we don't have it")
        ret, stdout, stderr = not expected, '', ''
    report(desc, a, b, ret, expected)
    return ret


def check_all_parsers(pbxdata, expected, desc, a, b):
    pbxfilename, data = pbxdata
    ret = parsable_variation(pbxdata, expected, desc, a, b)

    moddata = safe_replace(data, a, b)
    for parsertype in 'fast', 'classic':
        root, parseinfo = xcodeprojer.parse(moddata, format='xcode',
                                            parsertype=parsertype)
        if ret == 0:
            # Xcode parsed this. So if our parsers have anything to report, now is the time.
            xcodeprojer.report_parse_status(root, parseinfo, filename=pbxfilename)
            if root is None:
                print("Error: parsertype %s failed where Xcode succeeded:\n %s: %r %r" % (parsertype, desc, a, b))
        else:
            if root is not None:
                print("Warning: parsertype %s succeeded where Xcode failed:\n  %s: %r %r" % (parsertype, desc, a, b))
        flush()


def run_diverse(pbxfilename, data):
    pbxdata = (pbxfilename, data)

    for expected, desc, a, b in diverse_variations:
        check_all_parsers(pbxdata, expected, desc, a, b)


def flush():
    sys.stdout.flush()
    sys.stderr.flush()


def rangefor(args):
    start = args.firstchar or 0
    end = args.lastchar
    if end is None:
        end = 127
    end = min(end, 127)

    for i in range(start, end + 1):
        c = unichr(i)
        if (not args.alnums) and c.isalnum():
            # We usually don't check for [0-9a-zA-Z]
            continue
        yield i, c


def run_xcodebuild(args, pbxfilename, data):
    srctext = 'developmentRegion = English;'
    parts = 'developmentRegion = Eng', 'lish;'

    validchars = set()
    invalidchars = set()
    for i, c in rangefor(args):
        desttext = parts[0] + c + parts[1]
        destdata = safe_replace(data, srctext, desttext)

        ret, stdout, stderr = list_project(pbxfilename, destdata)
        if ret == 0:
            theset = validchars
            col = green
        else:
            theset = invalidchars
            col = red

        theset.add(c)
        print(col("(%d %r)" % (i, c)), end=' ')
        flush()

    print()
    print("  valid: '%s'" % green(''.join(sorted(validchars))))
    print("invalid: '%s'" % red(''.join(sorted(invalidchars))))


def run_selected_checks(args, parser, projdata, destpbxfilename):
    if args.unquoted:
        run_xcodebuild(args, destpbxfilename, projdata)
    elif args.diverse:
        run_diverse(destpbxfilename, projdata)
    else:
        parser.error('Something is wrong with the options or the handling of them.')


def run_checks(args, parser):
    print("Starting Xcode checks, meaning we run xcodebuild repeatedly with almost the same project.")

    pbxfilename = rel(MINI_PROJECT_FILENAME)

    with codecs.open(pbxfilename, 'r', encoding='utf-8') as f:
        projdata = f.read()

    xcproj = basename(dirname(pbxfilename))
    tmprootdir = tempfile.mkdtemp(prefix=xcodeprojer.timestamp())
    destpbxfilename = join(tmprootdir, xcproj, basename(pbxfilename))
    try:
        os.makedirs(dirname(destpbxfilename))
        run_selected_checks(args, parser, projdata, destpbxfilename)
    finally:
        try:
            os.remove(destpbxfilename)
        except OSError:
            pass
        for d in [dirname(destpbxfilename), tmprootdir]:
            try:
                os.remove(d)
            except OSError:
                pass


def main():
    parser = argparse.ArgumentParser(description='Find and test local project files.')

    actions = 'unquoted diverse'.split()
    parser.add_argument('--unquoted', action='store_true', help='which characters does Xcode accept without double quotes')
    parser.add_argument('--diverse', action='store_true', help='tests various behaviours')
    parser.add_argument('-f', '--first', action='store', type=int, dest='firstchar', help='ASCII code of first character')
    parser.add_argument('-l', '--last', action='store', type=int, dest='lastchar', help='ASCII code of last character')
    parser.add_argument('--alnums', action='store_true', help='also process alnums [a-zA-Z0-9]')

    args = parser.parse_args()

    num_actions = 0
    for act in actions:
        if getattr(args, act):
            num_actions += 1

    if num_actions != 1:
        parser.error('Please specify exactly one of the options %s.' % ', '.join('--' + x for x in actions))

    run_checks(args, parser)


if __name__ == '__main__':
    if PY3:
        sys.stdout = codecs.getwriter('utf8')(sys.stdout.buffer)
        sys.stderr = codecs.getwriter('utf8')(sys.stderr.buffer)
    main()
