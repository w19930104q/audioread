# This file is part of audioread.
# Copyright 2018, Sam Thursfield
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


import audioread


# The 'audiofile' fixture is defined in conftest.py.


def test_audioread_early_exit(audiofile):
    """Abort the read before it is completed.

    This test guards against regressions such as
    https://github.com/beetbox/audioread/pull/78

    """
    with audioread.audio_open(audiofile.path) as a:
        assert int(a.duration) == int(audiofile.duration)
        assert a.channels == audiofile.channels
        assert a.samplerate == audiofile.samplerate
        # Now we exit the context manager without reading any data.


def test_audioread_full(audiofile):
    """Read the audio data from the file."""
    with audioread.audio_open(audiofile.path) as a:
        assert int(a.duration) == int(audiofile.duration)
        assert a.channels == audiofile.channels
        assert a.samplerate == audiofile.samplerate

        # Now read all the data and assert that it's the correct type.
        for block in a:
            assert type(block) == bytes


def test_audioread_read_twice(audiofile):
    """Reading the same file object twice yields identical data."""
    with audioread.audio_open(audiofile.path) as a:
        first = b''.join(a)
        second = b''.join(a)

    assert len(first) > 0
    assert first == second


def test_audioread_preview_then_full(audiofile):
    """A partial read followed by a full read yields the full data.

    Each new iteration starts from the beginning of the file, so a
    "preview" does not consume data from the subsequent full read.
    """
    with audioread.audio_open(audiofile.path) as a:
        # Preview: read only the first block.
        for _ in a:
            break
        preview_then_full = b''.join(a)

    with audioread.audio_open(audiofile.path) as a:
        full = b''.join(a)

    assert preview_then_full == full
