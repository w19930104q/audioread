# This file is part of audioread.
# Copyright 2011, Adrian Sampson.
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

"""Uses standard-library modules to read AIFF, AIFF-C, and WAV files."""
import aifc
import array
import audioop
import sunau
import wave

from .exceptions import DecodeError
from .base import AudioFile

# Produce two-byte (16-bit) output samples.
TARGET_WIDTH = 2

# Python 3.4 added support for 24-bit (3-byte) samples.
SUPPORTED_WIDTHS = (1, 2, 3, 4)


class UnsupportedError(DecodeError):
    """File is not an AIFF, WAV, or Au file."""


class BitWidthError(DecodeError):
    """The file uses an unsupported bit width."""


def byteswap(s):
    """Swaps the endianness of the bytestring s, which must be an array
    of shorts (16-bit signed integers).
    """
    assert len(s) % 2 == 0
    values = array.array('h')
    values.frombytes(s)
    values.byteswap()
    return values.tobytes()


def _swap_bytes(data, width):
    """Swap the endianness of every sample of the given width (in
    bytes) in ``data``. Widths of 1, 2, 3 and 4 bytes are supported; a
    width of 1 leaves the data untouched.
    """
    if width <= 1:
        return data
    return audioop.byteswap(data, width)


class RawAudioFile(AudioFile):
    """An AIFF, WAV, or Au file that can be read by the Python standard
    library modules ``wave``, ``aifc``, and ``sunau``.

    By default, the audio data is delivered as 16-bit little-endian
    signed integer PCM, regardless of the bit width stored in the
    source file. If ``preserve_bit_depth`` is true, the samples are
    instead delivered using the source file's sample width (8-, 16-,
    24- or 32-bit). Big-endian source data (AIFF and Au) is still
    converted to little-endian so that the output byte order is
    consistent across all supported formats.
    """
    def __init__(self, filename, preserve_bit_depth=False):
        self.preserve_bit_depth = preserve_bit_depth
        self._fh = open(filename, 'rb')

        try:
            self._file = aifc.open(self._fh)
        except aifc.Error:
            # Return to the beginning of the file to try the next reader.
            self._fh.seek(0)
        else:
            self._needs_byteswap = True
            self._check()
            return

        try:
            self._file = wave.open(self._fh)
        except wave.Error:
            self._fh.seek(0)
            pass
        else:
            self._needs_byteswap = False
            self._check()
            return

        try:
            self._file = sunau.open(self._fh)
        except sunau.Error:
            self._fh.seek(0)
            pass
        else:
            self._needs_byteswap = True
            self._check()
            return

        # None of the three libraries could open the file.
        self._fh.close()
        raise UnsupportedError()

    def _check(self):
        """Check that the files' parameters allow us to decode it and
        raise an error otherwise.
        """
        if self._file.getsampwidth() not in SUPPORTED_WIDTHS:
            self.close()
            raise BitWidthError()

    def close(self):
        """Close the underlying file."""
        self._file.close()
        self._fh.close()

    @property
    def channels(self):
        """Number of audio channels."""
        return self._file.getnchannels()

    @property
    def samplerate(self):
        """Sample rate in Hz."""
        return self._file.getframerate()

    @property
    def duration(self):
        """Length of the audio in seconds (a float)."""
        return float(self._file.getnframes()) / self.samplerate

    @property
    def sample_width(self):
        """The width in bytes of the PCM samples this file yields.

        This is two bytes (16-bit) unless the file was opened with
        ``preserve_bit_depth=True``, in which case it matches the
        source file's sample width.
        """
        if self.preserve_bit_depth:
            return self._file.getsampwidth()
        return TARGET_WIDTH

    def read_data(self, block_samples=1024):
        """Generates blocks of PCM data found in the file."""
        old_width = self._file.getsampwidth()
        target_width = (
            old_width if self.preserve_bit_depth else TARGET_WIDTH
        )
        needs_conversion = old_width != target_width
        needs_byteswap = (
            self._needs_byteswap and self._file.getcomptype() != 'sowt'
        )
        channels = self._file.getnchannels()
        source_frame_width = old_width * channels
        remaining_frames = self._file.getnframes()

        while remaining_frames > 0:
            data = self._file.readframes(
                min(block_samples, remaining_frames)
            )
            if not data:
                break

            # Some standard-library readers (notably the AIFF reader
            # on 8-bit data) can append alignment padding that does not
            # make up a whole frame. Drop it so every block contains an
            # exact number of frames.
            usable = len(data) - (len(data) % source_frame_width)
            if usable != len(data):
                data = data[:usable]
            frames_read = len(data) // source_frame_width
            remaining_frames -= frames_read
            if not data:
                break

            # Make sure we have the desired bitdepth and endianness.
            if needs_conversion:
                data = audioop.lin2lin(data, old_width, target_width)
            if needs_byteswap and data:
                # Big-endian data. Swap to the output's little-endian
                # byte order, using the width actually delivered.
                data = _swap_bytes(data, target_width)
            yield data

    # Context manager.
    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.close()
        return False

    # Iteration.
    def __iter__(self):
        return self.read_data()
