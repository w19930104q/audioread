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
    """

    @property
    def sample_width(self):
        """The width, in bytes, of the PCM samples produced by this
        backend (i.e., the width of every block yielded by ``read_data``).

        By default, backends emit 16-bit (two-byte) samples. Backends
        that are opened with ``preserve_bit_depth=True`` may emit wider
        samples that reflect the source file's bit depth instead.

        Subclasses that support non-16-bit output override this
        property.
        """
        return 2
