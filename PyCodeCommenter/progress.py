"""Live progress text for AI drafting.

A hosted request can take a minute (the free service sleeps when idle) and
a rate limit can hold a run for up to a minute more, so a run with nothing
on screen looks hung. This shows one status line on stderr while a request
is in flight, and only on a terminal: in CI or with redirected output
nothing is written, as before. The line is plain text redrawn with a
carriage return -- no animation thread, no escape codes, no dependency --
and is always cleared before anything else is printed.
"""

import shutil
import sys
from typing import Callable, Optional, TextIO


class Progress:
    """One live status line on stderr.

    Attributes:
        provider_label (Callable[[], str]): Names the provider doing the
            drafting right now; a callable because the run can switch
            providers part way through.
    """

    def __init__(
        self,
        stream: Optional[TextIO] = None,
        columns: Optional[Callable[[], int]] = None,
    ):
        """
        Args:
            stream (Optional[TextIO]): Where to write; stderr by default.
            columns (Optional[Callable[[], int]]): The terminal width; read
                from the terminal by default.
        """
        self._stream = stream if stream is not None else sys.stderr
        self._columns = columns or (lambda: shutil.get_terminal_size().columns)
        self.provider_label: Callable[[], str] = lambda: ""
        self._file = ""
        self._shown_width = 0

    @property
    def enabled(self) -> bool:
        """Whether the output is a terminal a person is watching."""
        try:
            return bool(self._stream.isatty())
        except (AttributeError, ValueError):
            return False

    def start_file(self, name: str, position: int = 1, total: int = 1) -> None:
        """Sets the file the following status lines are about."""
        self._file = f"[{position}/{total}] {name}" if total > 1 else name

    def drafting(self, function_name: str) -> None:
        """Shows that a draft for ``function_name`` has been requested."""
        label = self.provider_label()
        where = f" ({label})" if label else ""
        self._show(f"{self._file} - drafting {function_name}{where}")

    def waiting(self, seconds: float) -> None:
        """Shows that the run is waiting out the service's rate limit."""
        self._show(
            f"{self._file} - waiting {seconds:.0f} s for the rate limit, "
            "then trying again"
        )

    def clear(self) -> None:
        """Removes the status line, if one is showing."""
        if self._shown_width:
            self._write("\r" + " " * self._shown_width + "\r")
            self._shown_width = 0

    def _show(self, text: str) -> None:
        if not self.enabled:
            return
        # One column short of the terminal width, so it can never wrap.
        text = text[: max(self._columns() - 1, 1)]
        self._write("\r" + text.ljust(self._shown_width))
        self._shown_width = len(text)

    def _write(self, text: str) -> None:
        # Progress is a courtesy: a closed or broken stream must never stop
        # a run.
        try:
            self._stream.write(text)
            self._stream.flush()
        except (OSError, ValueError):
            pass


__all__ = ["Progress"]
