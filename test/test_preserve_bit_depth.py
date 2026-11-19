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

"""Tests for bit-depth preservation across the raw PCM backends."""

import audioop

import pytest

from audioread import audio_open
from audioread.rawread import RawAudioFile, TARGET_WIDTH

from raw_fixtures import FORMATS, WIDTHS, build_file, to_little_endian


CHANNELS = (1, 2)


def _sunau_8bit_broken():
    """Whether the installed ``sunau`` reader mis-sizes 8-bit frames.

    The ``standard-sunau`` 3.13 redistribution calculates the frame
    size of LINEAR_8 streams without accounting for the sample width,
    which inflates the reported frame count of mono 8-bit files. This
    helper detects that defect at test-collection time.
    """
    import struct
    import sunau
    import tempfile

    # Seven mono LINEAR_8 samples, padded to an eight-byte data segment
    # as the Au specification requires. A correct reader reports seven
    # frames; a reader that ignores the sample width counts eight.
    header = struct.pack('>6I', 0x2E736E64, 24, 8, 2, 8000, 1)
    with tempfile.NamedTemporaryFile(suffix='.au', delete=False) as f:
        f.write(header)
        f.write(b'\x00' * 8)
        name = f.name
    try:
        with sunau.open(name) as reader:
            return reader.getnframes() != 7
    except Exception:
        return False


SUNAU_8BIT_BROKEN = _sunau_8bit_broken()


def _maybe_skip_au_8bit(fmt, width):
    if fmt[0] == 'au' and width == 1 and SUNAU_8BIT_BROKEN:
        pytest.skip('standard-sunau misreads 8-bit Au frame sizes')


def _read_all(audio_file):
    return b''.join(audio_file.read_data())


@pytest.mark.parametrize('width', WIDTHS)
@pytest.mark.parametrize('channels', CHANNELS)
@pytest.mark.parametrize('fmt', FORMATS, ids=[f[0] for f in FORMATS])
def test_raw_preserve_width_matches_source(
    tmp_path, width, channels, fmt
):
    """With preservation enabled, the output width equals the source."""
    _maybe_skip_au_8bit(fmt, width)
    path, source_bytes, _ = build_file(tmp_path, fmt, width, channels)

    with RawAudioFile(path, preserve_bit_depth=True) as af:
        assert af.sample_width == width
        data = _read_all(af)
        source_frames = af._file.getnframes()

    # Every delivered frame uses the source width.
    assert len(data) % (width * channels) == 0
    # The output contains at least every frame the container stores
    # (Au files may include alignment padding beyond the payload).
    assert len(data) // (width * channels) >= source_frames
    assert len(data) >= len(source_bytes)


@pytest.mark.parametrize('width', WIDTHS)
@pytest.mark.parametrize('channels', CHANNELS)
@pytest.mark.parametrize('fmt', FORMATS, ids=[f[0] for f in FORMATS])
def test_raw_preserve_little_endian(tmp_path, width, channels, fmt):
    """Preserved output is always little-endian, even for AIFF/Au."""
    _maybe_skip_au_8bit(fmt, width)
    _, _, native_endian = fmt
    path, source_bytes, _ = build_file(tmp_path, fmt, width, channels)

    with RawAudioFile(path, preserve_bit_depth=True) as af:
        data = _read_all(af)

    expected = to_little_endian(source_bytes, width, native_endian)
    # Au files may append zero padding (a whole number of frames) beyond
    # the written payload, so only compare the payload-sized prefix.
    if len(data) > len(expected):
        assert len(data) % (width * channels) == 0
        assert data[len(expected):] == \
            b'\x00' * (len(data) - len(expected))
    assert data[:len(expected)] == expected


@pytest.mark.parametrize('width', WIDTHS)
@pytest.mark.parametrize('channels', CHANNELS)
@pytest.mark.parametrize('fmt', FORMATS, ids=[f[0] for f in FORMATS])
def test_raw_default_is_byte_identical(
    tmp_path, width, channels, fmt
):
    """The default (16-bit) path must be byte-for-byte unchanged."""
    _maybe_skip_au_8bit(fmt, width)
    _, _, native_endian = fmt
    path, source_bytes, _ = build_file(tmp_path, fmt, width, channels)

    # Reference output produced exactly as the original code did.
    if width != TARGET_WIDTH:
        expected = audioop.lin2lin(source_bytes, width, TARGET_WIDTH)
    else:
        expected = source_bytes
    if native_endian == 'big':
        expected = audioop.byteswap(expected, TARGET_WIDTH)

    # Default constructor flag.
    with RawAudioFile(path) as af:
        assert af.sample_width == TARGET_WIDTH
        data = _read_all(af)
        # Au files may include alignment padding after the payload.
        assert data[:len(expected)] == expected
        assert data[len(expected):] == \
            b'\x00' * (len(data) - len(expected))

    # Explicitly disabled flag gives the same bytes.
    with RawAudioFile(path, preserve_bit_depth=False) as af:
        assert _read_all(af) == data


@pytest.mark.parametrize('width', WIDTHS)
@pytest.mark.parametrize('channels', CHANNELS)
@pytest.mark.parametrize('fmt', FORMATS, ids=[f[0] for f in FORMATS])
def test_raw_preserve_roundtrip_values(
    tmp_path, width, channels, fmt
):
    """Decoding the preserved output recovers the original samples."""
    _maybe_skip_au_8bit(fmt, width)
    suffix, _, _ = fmt
    path, _, values = build_file(tmp_path, fmt, width, channels)

    with RawAudioFile(path, preserve_bit_depth=True) as af:
        data = _read_all(af)

    # Re-interpret little-endian frames back to signed integers. Au
    # files may carry alignment padding after the payload, so compare
    # against the leading samples.
    unsigned = width == 1 and suffix != 'aiff'
    decoded = list(_iter_samples(data, width, unsigned))
    assert decoded[:len(values)] == values
    assert all(v == 0 for v in decoded[len(values):])


@pytest.mark.parametrize('width', WIDTHS)
@pytest.mark.parametrize('channels', CHANNELS)
@pytest.mark.parametrize('fmt', FORMATS, ids=[f[0] for f in FORMATS])
def test_raw_default_matches_legacy_algorithm(
    tmp_path, width, channels, fmt
):
    """The default output equals the pre-feature 16-bit conversion.

    The only permitted difference is trailing alignment padding that
    does not form a whole frame (which the older code passed through or
    even crashed on); every actual sample frame must be identical.
    """
    _maybe_skip_au_8bit(fmt, width)
    _, _, native_endian = fmt
    path, source_bytes, _ = build_file(tmp_path, fmt, width, channels)

    with RawAudioFile(path) as af:
        new_output = _read_all(af)
        frame_width = TARGET_WIDTH * channels
        # Reference length from the source payload alone.
        ref_len = (len(source_bytes) // (width * channels)) * frame_width

    assert len(new_output) >= ref_len
    assert new_output[:ref_len] == _legacy_convert(
        source_bytes, width, native_endian
    )
    # Any extra bytes are whole zero frames from container padding.
    trailing = new_output[ref_len:]
    assert len(trailing) % frame_width == 0
    assert trailing == b'\x00' * len(trailing)


def _legacy_convert(source_bytes, width, native_endian):
    """Reproduce the pre-feature raw backend conversion exactly."""
    if width != TARGET_WIDTH:
        out = audioop.lin2lin(source_bytes, width, TARGET_WIDTH)
    else:
        out = source_bytes
    if native_endian == 'big':
        out = audioop.byteswap(out, TARGET_WIDTH)
    return out


@pytest.mark.parametrize('width', WIDTHS)
@pytest.mark.parametrize('fmt', FORMATS, ids=[f[0] for f in FORMATS])
def test_audio_open_passes_flag(tmp_path, width, fmt):
    """``audio_open`` forwards the flag to the selected backend."""
    _maybe_skip_au_8bit(fmt, width)
    path, _, _ = build_file(tmp_path, fmt, width, 1)
    backends = [RawAudioFile]

    with audio_open(path, backends=backends, preserve_bit_depth=True) as af:
        assert isinstance(af, RawAudioFile)
        assert af.sample_width == width
        assert len(_read_all(af)) % width == 0  # mono: frame == sample

    with audio_open(path, backends=backends) as af:
        assert af.sample_width == TARGET_WIDTH


def _iter_samples(data, width, unsigned=False):
    """Yield signed integer samples from little-endian PCM bytes."""
    if width == 1:
        for byte in data:
            yield byte - 128 if unsigned else byte - 256 if byte >= 128 \
                else byte
        return

    step = width
    for offset in range(0, len(data), step):
        chunk = data[offset:offset + step]
        if width == 3:
            chunk = chunk + b'\x00' if chunk[2] < 0x80 \
                else chunk + b'\xff'
        value = int.from_bytes(chunk, 'little', signed=True)
        yield value
