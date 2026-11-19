# This file is part of audioread.
# Copyright 2026, Adrian Sampson.
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

"""Helpers to build deterministic raw PCM test files (WAV, AIFF and Au).

The files are written with the standard library's ``wave``, ``aifc``
and ``sunau`` modules, so the tests do not depend on any external
tool for the raw backend.
"""

import audioop
import struct

import aifc
import sunau
import wave
# Sample widths (in bytes) supported by the raw backend.
WIDTHS = (1, 2, 3, 4)

# Deterministic signed sample values exercising sign bits and interior
# bytes. The list for each width is filtered to that width's range.
_SIGNED_SAMPLES = (
    0, 1, -1, 2, -2, 127, -128, 255, -256,
    256, -257, 32767, -32768,
    8388607, -8388608,           # 24-bit extremes
    65536, -65537,
    2147483647, -2147483648,     # 32-bit extremes
)


def samples_for_width(width):
    """Signed sample values that fit in a sample of the given width."""
    if width == 1:
        limit = 128
    else:
        limit = 1 << (8 * width - 1)
    return [v for v in _SIGNED_SAMPLES if -limit <= v < limit]


def encode_samples(values, width, endian='little', unsigned=True):
    """Encode signed integer ``values`` as raw PCM with the given width
    (in bytes) and byte order.

    When ``unsigned`` is true, width-1 samples are stored as unsigned
    bytes (the WAV and Au convention). Otherwise, width-1 samples stay
    signed (the AIFF convention). Wider samples are always signed.
    """
    parts = []
    for value in values:
        if width == 1 and unsigned:
            value = value + 128
        if width == 1:
            parts.append(struct.pack('B', value & 0xFF))
        else:
            # Always truncate/pack to exactly `width` bytes first...
            fmt = {2: 'h', 3: 'i', 4: 'i'}[width]
            packed = struct.pack('<' + fmt, value)
            if width == 3:
                packed = packed[:3]
            # ...then reverse only those bytes for big-endian storage.
            if endian == 'big':
                packed = packed[::-1]
            parts.append(packed)
    return b''.join(parts)


def _write_wav(path, data, channels, rate, width):
    with wave.open(path, 'wb') as f:
        f.setnchannels(channels)
        f.setsampwidth(width)
        f.setframerate(rate)
        f.writeframes(data)


def _write_aiff(path, data, channels, rate, width):
    # aifc always writes big-endian data.
    with aifc.open(path, 'wb') as f:
        f.setnchannels(channels)
        f.setsampwidth(width)
        f.setframerate(rate)
        f.writeframes(data)


def _write_au(path, data, channels, rate, width):
    # sunau always writes big-endian data.
    with sunau.open(path, 'wb') as f:
        f.setnchannels(channels)
        f.setsampwidth(width)
        f.setframerate(rate)
        f.writeframes(data)


# Au encoding constants from the NeXT/Sun file format specification.
_AU_MAGIC = 0x2E736E64  # ".snd"
_AU_ENCODINGS = {1: 2, 2: 3, 3: 4, 4: 5}  # LINEAR_8/16/24/32
_AU_MIN_HEADER = 24


def _write_au_correct(path, data, channels, rate, width):
    """Write a spec-compliant Au file.

    Used instead of ``sunau``'s writer because the ``standard-sunau``
    redistribution's reader miscalculates the frame size for widths
    other than 16 bits; a hand-written header keeps the tests honest
    about the data the backend actually consumes. The data segment is
    padded with zeroes to an eight-byte boundary, as the specification
    requires.
    """
    header_size = _AU_MIN_HEADER
    padding = (-len(data)) % 8
    payload = data + b'\x00' * padding
    with open(path, 'wb') as f:
        f.write(struct.pack(
            '>6I',
            _AU_MAGIC,
            header_size,
            len(payload),
            _AU_ENCODINGS[width],
            rate,
            channels,
        ))
        f.write(payload)


# (suffix, writer, native byte order of the container format).
FORMATS = (
    ('wav', _write_wav, 'little'),
    ('aiff', _write_aiff, 'big'),
    ('au', _write_au_correct, 'big'),
)


def build_file(tmp_path, fmt, width, channels, endian=None):
    """Create a PCM file and return ``(path, source_bytes)``.

    ``source_bytes`` is the exact on-disk frame payload (interleaved
    channels) in the container's native byte order.
    """
    suffix, writer, native_endian = fmt
    if endian is None:
        endian = native_endian

    values = samples_for_width(width)
    # Make the frame count a multiple of the channel count.
    while len(values) % channels:
        values.append(0)

    suffix, writer, native_endian = fmt
    # WAV and Au store 8-bit PCM unsigned; AIFF stores it signed.
    unsigned = width == 1 and suffix != 'aiff'
    source_bytes = encode_samples(
        values, width, native_endian, unsigned=unsigned
    )
    path = tmp_path / ('test_w%d_c%d.%s' % (width, channels, suffix))
    writer(str(path), source_bytes, channels, 8000, width)
    return str(path), source_bytes, values


def to_little_endian(data, width, source_endian):
    """Return ``data`` encoded as little-endian samples."""
    if source_endian == 'little' or width == 1:
        return data
    return audioop.byteswap(data, width)
