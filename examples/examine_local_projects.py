#!/usr/bin/env python
# -*- coding: utf-8 -*-
#
# Copyright (c) 2014 Michael Krause ( http://krause-software.com/ ).

# You are free to use this code under the MIT license:
# http://opensource.org/licenses/MIT

"""Test local project.pbxproj files.

This script basically runs a lint over many Xcode project files and
reports every file when the unparse of the parse look different
then the original project file contents.

To use it first run
    $ test_local_projects.py --find

which creates local-projects.txt in the tests directory containing
filenames that look like valid project files.

Then run
    $ test_local_projects.py --test

which reports the findings about the filenames listed in local-projects.txt.
"""

from __future__ import print_function

import sys
import argparse
import time
import codecs
import types
import os
from os.path import abspath, dirname

from io import StringIO

import multiprocessing
import traceback
import errno
from collections import namedtuple

import utils

# Set up the Python path so we find the xcodeprojer module in the parent directory
# relative to this file.
sys.path.insert(1, dirname(dirname(abspath(__file__))))

import xcodeprojer
from xcodeprojer import bytestr, unistr

PY2 = sys.version_info[0] == 2
PY3 = sys.version_info[0] == 3


LISTFILENAME = 'local-projects.txt'
IGNOREDFILENAME = 'ignored-local-projects.txt'

PBXPROJNAME = 'project.pbxproj'

ExcInfo = namedtuple('ExcInfo', 'exc_info')

LintResult = namedtuple('LintResult', ['filename', 'success', 'text', 'parsetime', 'unparsetime', 'numbytes'])

if PY2:
    exec ('def reraise(tp, value, tb):\n raise tp, value, tb')
else:
    def reraise(tp, value, tb):
        raise value.with_traceback(tb)


def rel(filename):
    return os.path.join(dirname(abspath(__file__)), filename)


def write(s='', end='\n'):
    s = unistr(s) + unistr(end)
    s = s.encode('utf-8')
    sys.stdout.write(s)


def handle_file(pbxfilename, parsertype='normal'):
    try:
        with open(bytestr(pbxfilename), 'rb') as f:
            xcodeproj = f.read()
            t0 = time.time()
            root, parseinfo = xcodeprojer.parse(xcodeproj, dictionarytype=dict, parsertype=parsertype)
            buf = StringIO()
            xcodeprojer.report_parse_status(root, parseinfo, filename=pbxfilename, fp=buf)
            if root is None:
                return LintResult(pbxfilename, False, buf.getvalue(), 0, 0, len(xcodeproj))
            t1 = time.time()
            projname = xcodeprojer.projectname_for_path(pbxfilename)
            text = xcodeprojer.unparse(root, format='xcode', projectname=projname, parseinfo=parseinfo)
            t2 = time.time()
            return LintResult(pbxfilename, True, text, t1-t0, t2-t1, len(xcodeproj))
    except Exception as e:
        e.traceback = traceback.format_exc()
        raise


def filenames_to_examine():
    xcodeprojects = projects_from_list()
    ignored_projects = set()
    try:
        ignxcodeprojects = codecs.open(rel(IGNOREDFILENAME), 'r', encoding='utf-8').read()
        for filename in ignxcodeprojects.strip().splitlines():
            ignored_projects.add(filename)
    except IOError:
        pass

    projects_filenames = xcodeprojects
    filenames = [x for x in projects_filenames if x not in ignored_projects]
    return filenames


def run_lint(args, filtered_idx_filenames):
    use_pool = not args.disable_parallel

    if not use_pool:
        for pbxfilename in filtered_idx_filenames:
            try:
                yield handle_file(pbxfilename, parsertype=args.parser)
            except Exception:
                yield ExcInfo(sys.exc_info())

    if use_pool:
        pool = multiprocessing.Pool(initializer=utils.per_process_init)
        try:
            async_results = [pool.apply_async(handle_file, [x], {'parsertype': args.parser}) for x in filtered_idx_filenames]
            pool.close()
            while async_results:
                try:
                    asyncres = async_results.pop(0)
                    yield asyncres.get()
                except (KeyboardInterrupt, GeneratorExit):
                    raise
                except Exception as e:
                    t, v, tb = sys.exc_info()
                    try:
                        # Report the textual traceback of the subprocess rather than
                        # this local exception that was triggered by the other side.
                        tb = e.traceback
                    except AttributeError:
                        pass
                    yield ExcInfo((t, v, tb))
        except (KeyboardInterrupt, GeneratorExit):
            pool.terminate()
        finally:
            pool.join()


def examine_projects(args):
    start_index = args.start_index
    max_files = args.max_files

    filenames = filenames_to_examine()
    filenames = filenames[start_index:]
    if max_files is not None:
        filenames = filenames[:max_files]

    total_numbytes = 0
    total_parsetime = 0
    total_unparsetime = 0
    num_files = 0
    num_successes = 0
    t0 = time.time()
    for idx, result in enumerate(run_lint(args, filenames)):
        num_files += 1
        globalidx = start_index + idx
        try:
            tbtext = None
            if isinstance(result, ExcInfo):
                t, v, tb = result.exc_info
                if not isinstance(tb, types.TracebackType):
                    tbtext = tb
                    tb = None
                reraise(t, v, tb)

            sys.stdout.write("%d " % globalidx)
            sys.stdout.flush()
            handle_result(args, result.success, result.text, result.filename)
            if result.success:
                num_successes += 1
                if args.reportstats:
                    total_numbytes += result.numbytes
                    total_parsetime += result.parsetime
                    total_unparsetime += result.unparsetime
        except IOError as e:
            write('\n%d "%s" failed: %s' % (globalidx, unistr(filenames[idx]), repr(e)))
        except Exception as e:
            write('\n%d "%s" failed:' % (globalidx, unistr(filenames[idx])))
            if tbtext is not None:
                print(tbtext)
            else:
                traceback.print_exc()

    if args.reportstats and num_successes > 0:
        tdelta = time.time() - t0
        print("\nparse rate:%9d Bps    unparse rate:%9d Bps (per core)" % (total_numbytes / total_parsetime, total_numbytes / total_unparsetime))
        print("Processed %d Bps, avg. time per project: %f" % (total_numbytes / tdelta, tdelta / num_successes))
    if args.reportstats:
        print("Processed %d project files of which %d were unsuccessful" % (num_files, num_files - num_successes))


def handle_result(args, success, text, filename):
    if not success:
        print()
        print(text)
        return

    try:
        with open(bytestr(filename), 'rb') as f:
            origtext = f.read()
            if origtext[:1] not in [b'/', b'{']:
                # Only handle files in plist format.
                return
    except IOError as e:
        if e.errno not in (errno.ENOTDIR, errno.ENOENT):
            raise
        return

    if text == origtext:
        return

    xcodeprojer.print_diff(origtext, text, difftype=args.diff, filename=filename)


def find_projects(args, parser):
    root = args.find
    filenames = []
    for name in xcodeprojer.find_projectfiles(root):
        filenames.append(name)
        # This might take a while, report progress
        sys.stdout.write('.')
        sys.stdout.flush()
    print()

    if not filenames:
        print('No project.pbxproj files found in "%s"' % root)
        return

    fn = rel(LISTFILENAME)
    with open(fn, 'wb') as f:
        text = '\n'.join(filenames) + '\n'
        f.write(bytestr(text))
        print('\nWrote %d filename to "%s"' % (len(filenames), fn))

def projects_from_list():
    filename = rel(LISTFILENAME)
    with codecs.open(filename, 'r', encoding='utf-8') as f:
        return f.read().splitlines()

def examine_filelist(args, parser):
    filename = rel(LISTFILENAME)
    filelist = []
    try:
        filelist = projects_from_list()
        errmsg = 'does not contain any filenames.'
    except IOError:
        errmsg = 'does not exist or is not readable.'

    if len(filelist) < 1:
        print('"%s" %s\n'
              'If you could run something like:\n'
              '  %s --find /some/path/with/project/files/beneath\n'
              'before running the test, so we know about some project files to examine,'
              ' that would be great.' % (filename, errmsg, sys.argv[0]))
        return

    t0 = time.time()
    examine_projects(args)
    t1 = time.time() - t0
    print()
    if args.reportstats:
        print("Elapsed time: %f seconds" % t1)


def main():
    parser = argparse.ArgumentParser(description='Find and test local project files.')
    parser.add_argument('--parser', choices=['normal', 'fast', 'classic'], default='normal')
    parser.add_argument('-f', '--find', metavar='PATH', help='find local project files')
    parser.add_argument('-t', '--test', action='store_true', help='run all tests')
    parser.add_argument('-s', '--start-index', action='store', type=int, dest='start_index', default=0)
    parser.add_argument('-n', '--max-files', action='store', type=int, dest='max_files', help='maximum number of files to process')
    parser.add_argument('-d', '--disable-parallel', action='store_true', help='do not run tests in parallel')
    parser.add_argument('--diff', choices=['unified', 'html', 'opendiff'], default='opendiff',
                        help='how to display the diffs')
    parser.add_argument('--reportstats', action='store_true', help='print performance statistics')
    parser.add_argument('--profile', action='store_true', help='run everything through the profiler')

    args = parser.parse_args()

    num_actions = 0
    actions = 'find test'.split()
    for act in actions:
        if getattr(args, act):
            num_actions += 1

    if num_actions != 1:
        parser.error('Please specify exactly one of the options %s.' % ', '.join('--' + x for x in actions))

    if args.profile:
        print('Profiling...')
        utils.profile('call_command(args, parser)', locals(), globals())
    else:
        call_command(args, parser)


def call_command(args, parser):
    if args.find:
        find_projects(args, parser)
    elif args.test:
        examine_filelist(args, parser)
    else:
        parser.error('Something is wrong with the options or the handling of them.')


if __name__ == '__main__':
    if PY3:
        sys.stdout = codecs.getwriter('utf8')(sys.stdout.buffer)
        sys.stderr = codecs.getwriter('utf8')(sys.stderr.buffer)
    main()
