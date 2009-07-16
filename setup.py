#!/usr/bin/python
"""mp4seek
=======

A library for seeking inside MP4 files. Contains utilities to
split ISO MPEG-4 files and rebuild the necessary headers for
the output to be compliant with the MP4 specification.
"""

from distutils.core import setup

setup(name="mp4seek",
      version="1.0",
      description="Seeking inside MP4 files",
      long_description=__doc__,
      platforms=["any"],
      license="MIT",
      author="Arek Korbik",
      maintainer="Arek Korbik",
      author_email="arkadini@gmail.com",
      maintainer_email="arkadini@gmail.com",
      packages=["mp4seek"],
      scripts=["scripts/mp4-faststart"])
