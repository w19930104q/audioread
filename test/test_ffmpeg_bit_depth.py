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

"""End-to-end bit-depth tests for the FFmpeg backend."""

import subprocess

import pytest

from audioread import audio_open
from audioread.ffdec import FFmpegAudioFile, available

pytestmark = pytest.mark.skipif(
    not available(), reason='ffmpeg is not installed'
)

# ffmpeg PCM encoder name per source width (in bytes).
PCM_ENCODERS = {
    1: 'pcm_u8',
    2: 'pcm_s16le',
    3: 'pcm_s24le',
    4: 'pcm_s32le',
}


def _make_pcm(tmp_path, width, codec, suffix):
    """Generate a deterministic PCM file with ffmpeg and return its path."""
    path = tmp_path / ('source_w%d%s' % (width, suffix))
    subprocess.run(
        [
            'ffmpeg', '-loglevel', 'error', '-y',
            '-f', 'lavfi',
            '-i', 'sine=frequency=440:duration=0.2',
            '-c:a', codec,
            '-ar', '8000', '-ac', '1',
            str(path),
        ],
        check=True,
    )
    return str(path)


def _read_all(audio_file):
    return b''.join(audio_file.read_data())


@pytest.mark.parametrize('width', (1, 2, 3, 4))
def test_ffmpeg_preserve_width(tmp_path, width):
    """Preservation yields samples as wide as the source's bit depth."""
    path = _make_pcm(tmp_path, width, PCM_ENCODERS[width], '.wav')

    with FFmpegAudioFile(path, preserve_bit_depth=True) as af:
        assert af.sample_width == width
        data = _read_all(af)

    # Every delivered byte belongs to a whole sample and we got real
    # audio data.
    assert data
    assert len(data) % width == 0


def test_ffmpeg_preserve_defaults_to_16_bit(tmp_path):
    """Without the flag, output and reported width stay at 16 bits."""
    path = _make_pcm(tmp_path, 3, PCM_ENCODERS[3], '.wav')

    with FFmpegAudioFile(path) as af:
        assert af.sample_width == 2
        default_data = _read_all(af)

    with FFmpegAudioFile(path, preserve_bit_depth=False) as af:
        assert af.sample_width == 2
        assert _read_all(af) == default_data


def test_ffmpeg_preserve_24bit_roundtrip(tmp_path):
    """24-bit preserved output decodes back to the same PCM samples."""
    import wave

    path = _make_pcm(tmp_path, 3, PCM_ENCODERS[3], '.wav')

    with FFmpegAudioFile(path, preserve_bit_depth=True) as af:
        assert af.sample_width == 3
        data = _read_all(af)

    # Decode the same source independently with ffmpeg to a 24-bit WAV
    # and compare the raw payload.
    reference = tmp_path / 'reference.wav'
    subprocess.run(
        [
            'ffmpeg', '-loglevel', 'error', '-y',
            '-i', path, '-c:a', 'pcm_s24le', str(reference),
        ],
        check=True,
    )
    with wave.open(str(reference)) as f:
        assert f.getsampwidth() == 3
        expected = f.readframes(f.getnframes())

    assert data == expected


def test_ffmpeg_lossy_source_keeps_16_bit(tmp_path):
    """MP3 has no source bit depth: preservation falls back to 16 bits."""
    source = tmp_path / 'lossy.mp3'
    subprocess.run(
        [
            'ffmpeg', '-loglevel', 'error', '-y',
            '-f', 'lavfi', '-i', 'sine=frequency=440:duration=0.1',
            str(source),
        ],
        check=True,
    )

    with FFmpegAudioFile(str(source), preserve_bit_depth=True) as af:
        assert af.sample_width == 2
        preserved = _read_all(af)

    with FFmpegAudioFile(str(source)) as af:
        assert af.sample_width == 2
        assert _read_all(af) == preserved


def test_audio_open_ffmpeg_preserve(tmp_path):
    """``audio_open`` propagates the flag through backend selection."""
    path = _make_pcm(tmp_path, 3, PCM_ENCODERS[3], '.wav')

    # Force the FFmpeg backend even though the raw backend also reads
    # WAV files.
    from audioread.ffdec import FFmpegAudioFile
    with audio_open(
        path, backends=[FFmpegAudioFile], preserve_bit_depth=True
    ) as af:
        assert isinstance(af, FFmpegAudioFile)
        assert af.sample_width == 3
        assert len(_read_all(af)) % 3 == 0
