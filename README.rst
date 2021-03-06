xcodeprojer
=============

xcodeprojer is a Python script that brings your ``project.pbxproj`` files in order.
It can transform any kind of JSON, XML or plist format into an internal
representation and generate exactly the same commented plist format
that Xcode itself uses.

Without relying on Xcode at all this can be used for tasks like this:

- Ensure the canonical plist format of the project before checking in a new version.
- Perform custom modifications via these steps

    1. transform your project into JSON or XML.
    2. manipulate the JSON or XML object tree in a language of your choice.
    3. emit JSON or XML and let xcodeprojer create the proper plist for you.
- Perform custom modifications directly via Python with xcodeprojer as a module.
- Repair broken projects, a failed parse reports the line and column where the parser failed. [#f1]_
- Doing all of the above even on a non-Mac computer because it is written in pure Python.

xcodeprojer needs at least Python 2.7, the installation that comes with OS X works nicely
and it works as well with Python 3.2, 3.3 and 3.4. It has no other requirements.

Converting formats
------------------

To convert the ``project.pbxproj`` into the proper plist format of the same version (e.g. 46)
simply run:

.. code-block:: bash

    $ xcodeprojer --convert xcode project.pbxproj

This should be equivalent to Xcode writing the file itself, e.g. by renaming a file within Xcode
and renaming it back to actually trigger a project save. Let's call that the *canonical format*.

You may also want to call xcodeprojer from another scripting language, for this
we support reading the data from stdin and writing the output to stdout as follows:

.. code-block:: bash

    $ cat project.pbxproj | xcodeprojer --convert xcode --projectname HelloWorld -o -

In this case you should supply the project name which is the name of the parent directory of the ``project.pbxproj``
without the ``.xcodeproj`` suffix. We need this to create some of the comments.

If the file you are trying to convert is in the filesystem, you can also run:

.. code-block:: bash

    $ xcodeprojer --convert xcode -o - HelloWorld.xcodeproj/project.pbxproj

and still get the result on stdout.

Linting
----------

If you are already running some kind of buildbot or checkin hooks for quality control
you can add something like

.. code-block:: bash

    $ xcodeprojer --lint project.pbxproj

which gives you feedback via the return code if the file is syntactically

    0. perfectly in the canonical format.
    1. parsable but not in the canonical format.
    2. not parsable at all by Xcode.

When linting several files at once, only the worst error code is returned.
If you need more detail, please lint several files one after another.


Global ids
----------

xcodeprojer has options to create the Xcode gids and take them apart.

.. code-block:: bash

        $ xcodeprojer --giddump --gid-format=json project.pbxproj

.. code-block:: json

    {
      "gids":[
        {
          "comment":"Build configuration list for PBXProject \"MiniProject\"",
          "date":"2014-08-31T13:57:16Z",
          "gid":"4CDE969D19B3613C009DF310",
          "pid":222,
          "random":10351376,
          "seq":38557,
          "user":76
        }
      ]
    }

Without the ``--gid-format`` a column layout of the same information is written that you might prefer when just want to look at the data.

For a taste of what you can get by sorting and aggregating the Xcode ids
run something like:

.. code-block:: bash

    $ examples/gidhistograms.py /path/with/many/sampleprojects

``gidhistograms.py`` also has an ``--emoji`` option that shows the users
working on the projects over the years in a compact format.

Likewise you can conceal information about your own projects.
You can generate ids to e.g. hide the number of users working
on the project or in the timeframe in which they were doing so::

    $ xcodeprojer --gid 2 --gid-pid 50000 --gid-user notme --gid-date 2007-01-09T16:41:00Z
    0350F9550B53EF0C00A125FD
    0350F9560B53EF0C00A125FD

Syntax checking only
-----------------------

The parser and unparser only care about the syntactic validity of the plist format.
Xcode performs many checks and corrections based on the actual object types.
This project is useful mostly for converting into the Xcode plist format and
for correcting sloppy merges of the project including indentation, reordering
and comment correction.

Upgrading the file format version
------------------------------------

You should not use this script to change the file format version, e.g. from 43 to 46
because ``isa`` types and attributes change between versions.
The only reason to convert a file format into a different version is to
prepare versions of the same project for a diff inspection to reduce syntactic noise
much like you use 'ignore whitespace'.
Please don't try to open a project file whose version you have changed with this script in Xcode.

Installation
---------------

Standalone script use
'''''''''''''''''''''

If you are only planning to use this only as a shell script, don't bother with
the Python way of installing things and just copy the script into a ``PATH``
of your choice while dropping the ``.py`` extension, e.g.:

.. code-block:: bash

    $ sudo cp xcodeprojer.py /usr/local/bin/xcodeprojer

Python module
'''''''''''''

To use xcodeprojer.py as a module, ``cd`` into the xcodeprojer directory and install it with either

.. code-block:: bash

    $ pip install -e .

or

.. code-block:: bash

     $ python setup.py install

Here are some lines how to use xcodeprojer from Python

.. code-block:: python

        import xcodeprojer

        filename = 'UICatalog.xcodeproj/project.pbxproj'
        prj = open(filename, 'rb').read()
        root, parseinfo = xcodeprojer.parse(prj)
        # The text nodes of a parse tree are always unicode strings
        # (unicode for Python 2, str for Python 3).
        xcodeprojer.report_parse_status(root, parseinfo, filename=filename)
        if root is not None:
            prjname = xcodeprojer.projectname_for_path(filename)
            # The result from xcodeprojer.unparse is always a UTF-8 encoded
            # byte string (str for Python 2, bytes for Python 3).
            output = xcodeprojer.unparse(root, format='xcode', projectname=prjname)

The script ``examples/add_buildphase.py`` shows how to use xcodeprojer as a module
to add a buildphase to one of the test projects.

Ruby
''''

The script ``examples/add_buildphase.rb`` is an example how you can call xcodeprojer as
an external command while shuffling data back and forth in JSON with the end result
in the canonical Xcode plist format. Most users who are already manipulating Xcode projects
via scripts have all modifications up to the final JSON representation ready
and may only want to use the last step of generating the commented plist format.


Author
------

xcodeprojer was written by `Michael Krause <http://krause-software.com>`_.

License
-------

xcodeprojer is available under the `MIT license <http://opensource.org/licenses/MIT>`_. See the LICENSE file for more info.

.. rubric:: Footnotes

.. [#f1] Of course Xcode has error reporting as well:

    .. code-block:: bash

        $ grep CFPropertyListCreateFromXMLData /var/log/system.log

