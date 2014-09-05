#!/usr/bin/env python
# -*- coding: utf-8 -*-
#
# Copyright (c) 2014 Michael Krause ( http://krause-software.com/ ).

# You are free to use this code under the MIT license:
# http://opensource.org/licenses/MIT

"""Show some histograms for a directory a Xcode project files."""

from __future__ import print_function

import sys
import argparse
from os.path import abspath, dirname, join
import multiprocessing
from collections import defaultdict, Counter
import codecs

# Set up the Python path so we find the xcodeprojer module in the parent directory
# relative to this file.
sys.path.insert(1, dirname(dirname(abspath(__file__))))

import utils
import xcodeprojer
from xcodeprojer import bytestr, unistr


PY2 = sys.version_info[0] == 2
PY3 = sys.version_info[0] == 3

if PY2:
    text_type = unicode
    binary_type = str
else:
    text_type = str
    binary_type = bytes
    unichr = chr


try:
    NARROW_BUILD = len(unichr(0x1f300)) == 2
except ValueError:
    NARROW_BUILD = True


DEFAULT_FIRSTNAMES = 200

user_hash = xcodeprojer.UniqueXcodeIDGenerator.user_hash

emojis = []


def here():
    return dirname(abspath(__file__))


def rel(filename):
    return join(here(), filename)


def write(s, end='\n'):
    s = unistr(s) + unistr(end)
    s = s.encode('utf-8')
    if PY2:
        sys.stdout.write(s)
    else:
        sys.stdout.buffer.write(s)


def writeline():
    write('\n')


def uniord(s):
    """ord that works on surrogate pairs.
    """
    try:
        return ord(s)
    except TypeError:
        pass

    if len(s) != 2:
        raise

    return 0x10000 + ((ord(s[0]) - 0xd800) << 10) | (ord(s[1]) - 0xdc00)


def iterchars(text):
    if not NARROW_BUILD:
        for c in text:
            yield c

    idx = 0
    while idx < len(text):
        c = text[idx]
        if ord(c) >= 0x100:
            # When we are running on a narrow Python build
            # we have to deal with surrogate pairs ourselves.
            if ((0xD800 < ord(c) <= 0xDBFF)
                and (idx < len(text) - 1)
                and (0xDC00 < ord(text[idx + 1]) <= 0xDFFF)):
                c = text[idx:idx+2]
                # Skip the other half of the lead and trail surrogate
                idx += 1
        idx += 1
        yield c


def build_emoji_table():
    with codecs.open(rel('emojis.txt'), 'r', encoding='utf-8') as f:
        text = f.read()

    uniques = set()
    for c in iterchars(text):
        # Only use unicode chars >= 0x100 (emoji etc.)
        if len(c) >= 2 or ord(c) >= 0x100:
            if c not in uniques:
                emojis.append(c)
                uniques.add(c)


def print_emoji_table():
    per_line = 32

    for i in range(len(emojis)):
        if i % per_line == 0:
            write("%3d" % i, end=' ')
        write(emojis[i], end=' ')
        if i % per_line == per_line - 1:
            writeline()
    writeline()


def print_emoji_histo(histo):
    all_users = set()
    for year, users in histo.items():
        all_users.update(users)
    all_users = sorted(all_users)
    num_users = len(all_users)

    for year, users in histo.items():
        chars = [str(year), ' ']
        for i in range(num_users):
            if all_users[i] in users:
                c = emojis[all_users[i]] + ' '
            else:
                c = '  '
            chars.append(c)
        write(''.join(chars))
    write('\n')


def print_histo(histo, utcoffset=0):
    maximum = max(histo.values())
    max_display = 60
    for k in sorted(histo):
        if utcoffset != 0:
            localhour = (k - utcoffset) % 24
        else:
            localhour = k
        v = histo.get(localhour, 0)
        stars = '*' * int(v * max_display / float(maximum))
        write("%3d %5d  %s" % (k, v, stars))
    writeline()


def gidtable(filename):
    with open(filename, 'rb') as f:
        xcodeproj = f.read()
        root, parseinfo = xcodeprojer.parse(xcodeproj)
        if root is not None:
            unparser = xcodeprojer.Unparser(root)
            # We don't need the parse tree, only access to the gidcomments
            # that are built during the unparse.
            _ = unparser.unparse(root, projectname=xcodeprojer.projectname_for_path(filename))
            gidcomments = unparser.gidcomments
            c = '.'
        else:
            gidcomments = {}
            c = 'X'
        sys.stdout.write(c)
        sys.stdout.flush()
        return filename, gidcomments


def histogram(args, utcoffset=0):
    if args.emoji or args.emojitable:
        write("Please be patient when your computer is caching emoji fonts for you. This might take a minute.\n")

    build_emoji_table()
    if args.emojitable:
        print_emoji_table()
        return

    path = args.directory
    histo_year = Counter()
    histo_hour = Counter()
    users_per_year = defaultdict(set)

    pool = multiprocessing.Pool(initializer=utils.per_process_init)

    filenames = xcodeprojer.find_projectfiles(path)
    results = []

    write("Looking for Xcode ids in project files...")
    sys.stdout.flush()

    for idx, filename in enumerate(filenames):
        results.append(pool.apply_async(gidtable, [filename]))
        if args.max_files is not None and idx + 1 >= args.max_files:
            break
    pool.close()

    try:
        for asyncresult in results:
            filename, gids = asyncresult.get()
            for gid in gids:
                fields = xcodeprojer.gidfields(gids, gid)
                refdate = fields['date']
                dt = xcodeprojer.datetime_from_utc(refdate)
                histo_hour[dt.hour] += 1
                year = dt.year
                if args.startyear <= year <= args.endyear:
                    histo_year[year] += 1
                    users_per_year[year].add(fields['user'])
    except (KeyboardInterrupt, GeneratorExit):
        pool.terminate()
    finally:
        pool.join()

    writeline()
    write("At which hours are new Xcode ids created (UTC time offset: %d)" % args.utcoffset)
    print_histo(histo_hour, utcoffset=utcoffset)

    write("In which years were the Xcode ids created (we only look at %s-%s)" % (args.startyear, args.endyear))
    print_histo(histo_year)

    write("Estimated number of users creating new Xcode ids by year")
    user_histo = {k: len(v) for (k, v) in users_per_year.items()}
    print_histo(user_histo)

    writeline()
    write("The following is a list of names that might be completely unrelated to the examined Xcode projects.")
    write("For something for tangible replace firstnames.txt with your own list.")
    writeline()

    max_firstnames_limited = print_names(args, users_per_year, emoji=args.emoji)

    if args.emoji:
        write("Looking for Xcode ids in project files...")
        print_emoji_histo(users_per_year)

    if max_firstnames_limited and args.max_firstnames is None:
        write("The number of first names to consider was limited to %d, this can be changed with --max-firstnames" % max_firstnames_limited)


def print_names(args, users_per_year, emoji=False):
    userhashes = defaultdict(list)
    max_firstnames = args.max_firstnames
    if max_firstnames is None:
        max_firstnames = DEFAULT_FIRSTNAMES
    max_firstnames_limited = None
    with codecs.open(rel('firstnames.txt'), 'r', encoding='utf-8') as f:
        firstnames = f.read().splitlines()
        for idx, name in enumerate(firstnames):
            if idx >= max_firstnames:
                max_firstnames_limited = max_firstnames
                break
            userhashes[user_hash(name)].append(name)

    for year, hashes in sorted(users_per_year.items()):
        write(str(year), end=' ')
        for h in sorted(hashes):
            candidates = userhashes[h]
            if candidates:
                if emoji:
                    symbol = emojis[h] + '  '
                else:
                    symbol = ''
                write(' (%s' % symbol + ' | '.join(candidates) + ')', end=' ')
        writeline()

    return max_firstnames_limited


def main():
    parser = argparse.ArgumentParser(description='Show some histograms for a directory a Xcode project files.')
    parser.add_argument('-u', '--utcoffset', type=int, default=-8, metavar='UTCOFFSET', help='UTC time offset, e.g. "-8" for California')
    parser.add_argument('--startyear', type=int, default=2006)
    parser.add_argument('--endyear', type=int, default=2014)
    parser.add_argument('-n', '--max-files', action='store', type=int, default=None, help='maximum number of files to process')
    parser.add_argument('--max-firstnames', action='store', type=int, default=None, help='maximum number first names to consider')
    parser.add_argument('--emoji', action='store_true', help='add emoji characters to userhashes')
    parser.add_argument('--emojitable', action='store_true', help='only print the emoji table')
    parser.add_argument('--profile', action='store_true', help='run everything through the profiler')
    parser.add_argument('directory', help='directory with Xcode project files')

    args = parser.parse_args()

    if args.profile:
        write('Profiling...')
        utils.profile('call_command(args, parser)', locals(), globals())
    else:
        call_command(args)


def call_command(args):
    histogram(args, utcoffset=args.utcoffset)


if __name__ == '__main__':
    main()
