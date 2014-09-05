#!/usr/bin/env python
# -*- coding: utf-8 -*-
#
# Copyright (c) 2014 Michael Krause ( http://krause-software.com/ ).

# You are free to use this code under the MIT license:
# http://opensource.org/licenses/MIT

"""An example how to add a buildphase with xcodeprojer."""

from __future__ import print_function

import sys
import codecs
from os.path import abspath, dirname, join

# Set up the Python path so we find the xcodeprojer module in the parent directory
# relative to this file.
sys.path.insert(1, dirname(dirname(abspath(__file__))))

import xcodeprojer

PY2 = sys.version_info[0] == 2
PY3 = sys.version_info[0] == 3


INTL_PROJECT_FILENAME = '../tests/data/IŋƫƐrnætiønæl X©ødǝ ¶®øjæƈt.xcodeproj/project.pbxproj'
OK = 0
PARSING_FAILED = 1


def here():
    return dirname(abspath(__file__))


def rel(filename):
    return join(here(), filename)


def getobj(root, gid):
    return root['objects'][gid]


def find_isas(root, isa):
    for key, obj in root['objects'].items():
        if obj['isa'] == isa:
            yield key, obj


def find_first(root, isa):
    return find_isas(root, isa).next()[1]


def main():
    filename = rel(INTL_PROJECT_FILENAME)
    with open(filename, 'rb') as f:
        xcodeproj = f.read()

    root, parseinfo = xcodeprojer.parse(xcodeproj, format='xcode')
    xcodeprojer.report_parse_status(root, parseinfo, filename=filename)
    if root is None:
        return PARSING_FAILED

    gen = xcodeprojer.UniqueXcodeIDGenerator()

    pbxproject = find_first(root, 'PBXProject')
    firsttarget = getobj(root, pbxproject['targets'][0])

    # Construct a new buildphase as any other JSON object
    newbuildphase = {'isa': 'PBXShellScriptBuildPhase',
                     'buildActionMask': '2147483647',
                     'files': [],
                     'inputPaths': [],
                     'outputPaths': [],
                     'runOnlyForDeploymentPostprocessing': '0',
                     'shellPath': '/bin/sh',
                     'shellScript': "echo 'A new buildphase says hi!'"}
    id_newbuildphase = gen.generate()
    root['objects'][id_newbuildphase] = newbuildphase
    firsttarget['buildPhases'].insert(0, id_newbuildphase)

    projectname = xcodeprojer.projectname_for_path(filename)
    proj = xcodeprojer.unparse(root,
                               format='xcode',
                               projectname=projectname,
                               parseinfo=parseinfo)

    with open(filename, 'wb') as f:
        f.write(proj)

    xcodeprojer.print_diff(xcodeproj, proj, filename=filename)
    return OK

if __name__ == '__main__':
    if PY3:
        sys.stdout = codecs.getwriter('utf8')(sys.stdout.buffer)
        sys.stderr = codecs.getwriter('utf8')(sys.stderr.buffer)
    sys.exit(main())
