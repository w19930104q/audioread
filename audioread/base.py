# This file is part of audioread.
# Copyright 2021, Adrian Sampson.
#
# Permission is hereby granted, free of charge, to any person obtaining
# a copy of this software and associated documentation files (the
# "Software"), to deal in the Software without restriction, including
# without limitation the rights to use, copy, modify, merge, publish,
# distribute, sublicense, and/or sell copies of the Software, and to
# permit persons to whom the Software is furnished to do so, subject to
# the following conditions:
#
# The above copyright notice and this permission notice shall be
# included in all copies or substantial portions of the Software.


class AudioFile:
    """The base class for all audio file types.

    All audio files yield their decoded PCM data by iteration (or via
    the backend's ``read_data`` method). Every new iteration starts
    reading from the *beginning* of the file, so reading the same
    object multiple times always produces the same sequence of
    samples, regardless of the backend or file format.

    Note that iterators over the same file object share one
    underlying decoder: starting a new iteration rewinds the stream,
    so a previous iterator that is still in progress should be
    discarded.
    """
