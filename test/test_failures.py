# This file is part of audioread.
# Copyright 2024, Adrian Sampson.
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


import os

import pytest

import audioread
from audioread import ffdec, rawread
from audioread.exceptions import BackendFailure, NoBackendError


class _StubDecodeError(audioread.DecodeError):
    pass


class _FirstBackend:
    """A backend that always reports a decode failure."""

    def __init__(self, path):
        raise _StubDecodeError("first backend reason")


class _SecondBackend:
    """Another backend that always reports a decode failure."""

    def __init__(self, path):
        raise _StubDecodeError("second backend reason")


class _WorkingBackend:
    def __init__(self, path):
        self.path = path


class _NonDecodeError(Exception):
    pass


class _ExplodingBackend:
    """A backend that fails with an exception that is not a DecodeError."""

    def __init__(self, path):
        raise _NonDecodeError("not a decode error")


def test_no_backend_error_aggregates_failures():
    """Every tried backend contributes one BackendFailure record."""
    with pytest.raises(NoBackendError) as exc_info:
        audioread.audio_open(
            "whatever", backends=[_FirstBackend, _SecondBackend]
        )

    error = exc_info.value
    assert isinstance(error.failures, tuple)
    assert len(error.failures) == 2

    first, second = error.failures
    assert first.backend == "_FirstBackend"
    assert second.backend == "_SecondBackend"

    # The failure category is the qualified exception type...
    assert first.exception_type == (
        _StubDecodeError.__module__ + "._StubDecodeError"
    )
    # ...and the reason summary carries the original message.
    assert first.reason == "first backend reason"
    assert second.reason == "second backend reason"

    # The original exception instances are retained.
    assert isinstance(first.exception, _StubDecodeError)
    assert str(first.exception) == "first backend reason"

    # The summary string names each backend and its category/reason.
    message = str(error)
    assert "_FirstBackend" in message
    assert "_SecondBackend" in message
    assert "_StubDecodeError" in message
    assert "first backend reason" in message
    assert "second backend reason" in message


def test_backend_failure_records_keep_fallback_order():
    """Records appear in the order in which backends are tried."""
    with pytest.raises(NoBackendError) as exc_info:
        audioread.audio_open(
            "whatever", backends=[_SecondBackend, _FirstBackend]
        )

    assert [f.backend for f in exc_info.value.failures] == [
        "_SecondBackend",
        "_FirstBackend",
    ]


def test_fallback_chain_still_reaches_a_working_backend():
    """A failing backend must not stop the later backends from being
    tried, and no exception is raised once one succeeds.
    """
    result = audioread.audio_open(
        "whatever", backends=[_FirstBackend, _WorkingBackend]
    )
    assert isinstance(result, _WorkingBackend)


def test_non_decode_errors_are_not_swallowed():
    """Only DecodeError participates in the fallback chain."""
    with pytest.raises(_NonDecodeError):
        audioread.audio_open(
            "whatever", backends=[_ExplodingBackend, _WorkingBackend]
        )


def test_no_backends_keeps_legacy_empty_exception():
    """With no backends available the exception behaves exactly as
    before: no message and an empty failure list.
    """
    with pytest.raises(NoBackendError) as exc_info:
        audioread.audio_open("whatever", backends=[])

    error = exc_info.value
    assert error.failures == ()
    assert error.args == ()
    assert str(error) == ""


def test_backend_failure_without_message_uses_class_name():
    """An exception with an empty message still yields a useful
    reason summary.
    """
    failure = BackendFailure.from_exception(
        "RawAudioFile", rawread.UnsupportedError()
    )
    assert failure.backend == "RawAudioFile"
    assert failure.exception_type == (
        "audioread.rawread.UnsupportedError"
    )
    assert failure.reason == "UnsupportedError"
    assert str(failure) == "audioread.rawread.UnsupportedError"


def test_backend_failure_str_combines_category_and_reason():
    failure = BackendFailure.from_exception(
        "FFmpegAudioFile", ffdec.CommunicationError("stream info not found")
    )
    assert str(failure) == (
        "audioread.ffdec.CommunicationError: stream info not found"
    )


# ---------------------------------------------------------------------------
# Acceptance: corrupt material against the real backends.
# ---------------------------------------------------------------------------

def test_corrupt_file_collects_each_real_backend_failure(tmp_path):
    corrupt = tmp_path / "corrupt.bin"
    corrupt.write_bytes(
        b"this is definitely not any kind of audio file"
        b"\x00\x01\x02garbage-padding"
    )

    backends = audioread.available_backends(flush_cache=True)
    assert backends, "this environment should provide at least one backend"

    with pytest.raises(NoBackendError) as exc_info:
        audioread.audio_open(str(corrupt), backends=backends)

    error = exc_info.value
    tried = [backend.__name__ for backend in backends]
    assert [f.backend for f in error.failures] == tried
    assert len(error.failures) == len(backends)

    # Every record is well-formed and mentions a failure category.
    for failure in error.failures:
        assert failure.backend
        assert failure.reason
        assert "." in failure.exception_type
        assert isinstance(failure.exception, audioread.DecodeError)

    # The raw backend rejects the file through its own, unchanged
    # exception type.
    raw_failure = next(
        f for f in error.failures if f.backend == "RawAudioFile"
    )
    assert raw_failure.exception_type == (
        "audioread.rawread.UnsupportedError"
    )
    assert isinstance(
        raw_failure.exception, rawread.UnsupportedError
    )

    # The diagnostic message lets us tell the backends apart even when
    # they share an exception class name.
    message = str(error)
    assert "RawAudioFile" in message
    assert "audioread.rawread.UnsupportedError" in message


def test_single_backend_exception_types_and_messages_unchanged(tmp_path):
    """The individual backends still raise their own exceptions with
    their original messages when called directly.
    """
    corrupt = tmp_path / "corrupt.bin"
    corrupt.write_bytes(b"not an audio file")

    with pytest.raises(rawread.UnsupportedError) as exc_info:
        rawread.RawAudioFile(str(corrupt))
    assert str(exc_info.value) == ""


# ---------------------------------------------------------------------------
# Acceptance: ffmpeg missing from the environment.
# ---------------------------------------------------------------------------

def test_missing_ffmpeg_reports_not_installed_category(tmp_path, monkeypatch):
    """When neither ffmpeg nor avconv can be found, the aggregate error
    explains that the FFmpeg backend failed because the binary is not
    installed.
    """
    monkeypatch.setattr(ffdec, "COMMANDS", ("no-such-ffmpeg-binary-xyz",))
    assert ffdec.available() is False

    some_file = tmp_path / "corrupt.bin"
    some_file.write_bytes(b"not an audio file")

    with pytest.raises(NoBackendError) as exc_info:
        audioread.audio_open(
            str(some_file),
            backends=[rawread.RawAudioFile, ffdec.FFmpegAudioFile],
        )

    error = exc_info.value
    ffmpeg_failure = next(
        f for f in error.failures if f.backend == "FFmpegAudioFile"
    )
    assert ffmpeg_failure.exception_type == (
        "audioread.ffdec.NotInstalledError"
    )
    assert ffmpeg_failure.reason == "NotInstalledError"
    assert isinstance(
        ffmpeg_failure.exception, ffdec.NotInstalledError
    )

    assert "NotInstalledError" in str(error)
    # The raw backend was still tried before giving up.
    assert [f.backend for f in error.failures] == [
        "RawAudioFile",
        "FFmpegAudioFile",
    ]


def test_ffmpeg_absent_from_path_is_not_available(tmp_path, monkeypatch):
    """Simulate a real environment without ffmpeg: an empty PATH means
    the availability check reports the backend as unavailable.
    """
    monkeypatch.setenv("PATH", "")
    # The subprocess resolves the binary through PATH, so an empty PATH
    # makes ffmpeg unfindable regardless of the host installation.
    assert ffdec.available() is False

    # With only the FFmpeg backend "installed", audio_open raises an
    # empty (legacy) NoBackendError: there is nothing to aggregate.
    monkeypatch.setattr(audioread, "BACKENDS", [])
    monkeypatch.setattr(
        audioread,
        "available_backends",
        lambda flush_cache=False: [],
    )
    with pytest.raises(NoBackendError) as exc_info:
        audioread.audio_open(str(tmp_path / "anything.bin"))
    assert exc_info.value.failures == ()
