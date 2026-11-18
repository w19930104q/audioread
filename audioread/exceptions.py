# This file is part of audioread.
# Copyright 2013, Adrian Sampson.
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


from dataclasses import dataclass


class DecodeError(Exception):
    """The base exception class for all decoding errors raised by this
    package.
    """


@dataclass(frozen=True)
class BackendFailure:
    """A record describing why a single backend failed to open a file.

    ``backend`` is the name of the backend class (e.g.
    ``'FFmpegAudioFile'``), ``exception_type`` is the fully qualified
    name of the exception class (the failure category, e.g.
    ``'audioread.ffdec.NotInstalledError'``), ``reason`` is a short
    human-readable summary of the failure (the exception's message, or
    the exception class name if it has no message), and ``exception``
    is the original exception instance.
    """
    backend: str
    exception_type: str
    reason: str
    exception: BaseException

    @classmethod
    def from_exception(cls, backend, exc):
        """Build a failure record from an exception raised by a
        backend.
        """
        reason = str(exc) or type(exc).__name__
        exc_type = type(exc)
        # Drop the traceback so the record does not keep the stack
        # frame (and any partially constructed backend object living in
        # it, such as an FFmpeg subprocess with daemon threads) alive
        # until the aggregate exception is garbage collected.
        exc.__traceback__ = None
        return cls(
            backend=backend,
            exception_type='{}.{}'.format(
                exc_type.__module__, exc_type.__name__
            ),
            reason=reason,
            exception=exc,
        )

    def __str__(self):
        simple_name = self.exception_type.rsplit('.', 1)[-1]
        if self.reason == simple_name:
            # The reason is just the class name, so the qualified type
            # already says everything there is to know.
            return self.exception_type
        return '{}: {}'.format(self.exception_type, self.reason)


class NoBackendError(DecodeError):
    """The file could not be decoded by any backend. Either no backends
    are available or each available backend failed to decode the file.

    The ``failures`` attribute is a tuple of :class:`BackendFailure`
    records, one per backend that was tried, in the order the backends
    were tried. It is empty when no backends were available at all.
    """
    def __init__(self, failures=()):
        self.failures = tuple(failures)
        if self.failures:
            details = '; '.join(
                '{}: {}'.format(failure.backend, failure)
                for failure in self.failures
            )
            super().__init__(
                'no backend could decode the file; '
                'per-backend failures: {}'.format(details)
            )
        else:
            # Preserve the legacy empty-exception behaviour.
            super().__init__()
