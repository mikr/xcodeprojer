#!/usr/bin/env python

try:
    from setuptools import setup, Command
except ImportError:
    from distutils.core import setup, Command


class RunTest(Command):

    user_options = []

    def initialize_options(self):
        pass

    def finalize_options(self):
        pass

    def run(self):
        import sys
        import subprocess
        errno = subprocess.call([sys.executable, 'tests/test_xcodeprojer.py'])
        raise SystemExit(errno)


with open('README.rst') as f:
    readme = f.read()

setup(
    name='xcodeprojer',
    version='0.1',
    url='https://github.com/mikr/xcodeprojer',
    license='MIT',
    author='Michael Krause',
    author_email='michael@krause-software.com',
    description='xcodeprojer is a Python script that brings your project.pbxproj files in order.',
    long_description=readme,
    py_modules=['xcodeprojer'],
    cmdclass={'test': RunTest},
    zip_safe=False,
    platforms='any',
    keywords='xcode plist json xml',
    classifiers=[
        'Development Status :: 3 - Alpha',
        'Environment :: Console',
        'Environment :: MacOS X',
        'Intended Audience :: Developers',
        'License :: OSI Approved :: MIT License',
        'Natural Language :: English',
        'Operating System :: MacOS :: MacOS X',
        'Operating System :: OS Independent',
        'Programming Language :: Python :: 2.7',
        'Programming Language :: Python :: 3.2',
        'Programming Language :: Python :: 3.3',
        'Programming Language :: Python :: 3.4',
        'Topic :: Software Development :: Libraries :: Python Modules',
        'Topic :: Software Development :: Quality Assurance',
        'Topic :: Utilities',
    ],
    entry_points={
        'console_scripts': [
            'xcodeprojer = xcodeprojer:main'
        ]
    },
)
