#!/usr/bin/env python
# -*- coding: utf-8 -*-
#
# Copyright (c) 2014 Michael Krause ( http://krause-software.com/ ).

# You are free to use this code under the MIT license:
# http://opensource.org/licenses/MIT

import os
import signal


def per_process_init():
    os.nice(19)
    # A keyboard interrupt disrupts the communication between a
    # Python script and its subprocesses when using multiprocessing.
    # The child can ignore SIGINT and is properly shut down
    # by a pool.terminate() call in case of a keyboard interrupt
    # or an early generator exit.
    signal.signal(signal.SIGINT, signal.SIG_IGN)


def profile(sourcecode, p_locals, p_globals):
    import cProfile
    import pstats
    import tempfile

    prof_filename = os.path.join(tempfile.gettempdir(), "pyapp.prof")
    cProfile.runctx(sourcecode, p_locals, p_globals, prof_filename)

    p = pstats.Stats(prof_filename)
    p.sort_stats('time').print_stats(40)
    os.remove(prof_filename)
