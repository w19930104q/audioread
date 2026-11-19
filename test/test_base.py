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

"""Tests for the shared ``AudioFile`` contract."""

from audioread.base import AudioFile


def test_base_sample_width_defaults_to_16_bit():
    """Every backend reports 16-bit samples unless it overrides this."""
    audio_file = AudioFile.__new__(AudioFile)
    assert audio_file.sample_width == 2
