"""Live progress text for AI drafting: shown only on a terminal, always
cleared before anything else is printed, never allowed to break a run."""

import io
import logging

from PyCodeCommenter import PyCodeCommenter
from PyCodeCommenter.description_provider import (
    DescriptionProvider,
    DocstringDraft,
    DraftingStopped,
)
from PyCodeCommenter.progress import Progress

logging.disable(logging.CRITICAL)

CODE = """def total_due(invoice_id, discount):
    return discount


def ping():
    \"\"\"Check the service is up.\"\"\"
    return True
"""


class FakeStream(io.StringIO):
    def __init__(self, tty=True, columns=80):
        super().__init__()
        self._tty = tty
        self.columns = columns

    def isatty(self):
        return self._tty


def make_progress(tty=True, columns=80, provider="hosted"):
    stream = FakeStream(tty, columns)
    progress = Progress(stream=stream, columns=lambda: columns)
    progress.provider_label = lambda: provider
    return progress, stream


# ---------------------------------------------------------------------------
# The status line
# ---------------------------------------------------------------------------


def test_nothing_is_written_when_stderr_is_not_a_terminal():
    progress, stream = make_progress(tty=False)

    progress.start_file("a.py", 1, 3)
    progress.drafting("total_due")
    progress.waiting(30)
    progress.clear()

    assert stream.getvalue() == ""


def test_status_line_names_file_position_function_and_provider():
    progress, stream = make_progress()

    progress.start_file("product_service.py", 3, 12)
    progress.drafting("create_product")

    assert "[3/12] product_service.py - drafting create_product (hosted)" in (
        stream.getvalue()
    )


def test_a_single_file_shows_no_position():
    progress, stream = make_progress()

    progress.start_file("app.py", 1, 1)
    progress.drafting("main")

    assert "app.py - drafting main (hosted)" in stream.getvalue()
    assert "[1/1]" not in stream.getvalue()


def test_rate_limit_wait_is_visible():
    progress, stream = make_progress()

    progress.start_file("a.py", 1, 2)
    progress.waiting(30)

    assert "waiting 30 s for the rate limit" in stream.getvalue()


def test_clear_blanks_the_line_and_leaves_the_cursor_at_its_start():
    progress, stream = make_progress()
    progress.start_file("a.py", 1, 2)
    progress.drafting("total_due")

    progress.clear()

    tail = stream.getvalue().rsplit("\r", 2)
    assert tail[-1] == ""  # ends on a carriage return
    assert tail[-2].strip() == ""  # after blanking the text


def test_clear_writes_nothing_when_no_line_is_showing():
    progress, stream = make_progress()

    progress.clear()

    assert stream.getvalue() == ""


def test_a_shorter_line_fully_replaces_a_longer_one():
    progress, stream = make_progress()
    progress.start_file("a_long_file_name.py", 1, 2)
    progress.drafting("a_long_function_name")
    progress.drafting("f")

    last = stream.getvalue().rsplit("\r", 1)[-1]
    assert "a_long_function_name" not in last
    assert "drafting f" in last


def test_a_line_wider_than_the_terminal_is_cut_so_it_cannot_wrap():
    progress, stream = make_progress(columns=30)
    progress.start_file("a_very_long_file_name_indeed.py", 1, 2)
    progress.drafting("a_very_long_function_name")

    shown = stream.getvalue().rsplit("\r", 1)[-1]
    assert len(shown) < 30


def test_no_output_error_if_the_stream_cannot_be_written(capsys):
    class Broken(FakeStream):
        def write(self, text):
            raise OSError("closed")

    progress = Progress(stream=Broken(), columns=lambda: 80)

    progress.start_file("a.py", 1, 2)
    progress.drafting("total_due")
    progress.clear()  # must not raise


# ---------------------------------------------------------------------------
# Wiring into generation
# ---------------------------------------------------------------------------


class RecordingProgress:
    def __init__(self):
        self.events = []

    def drafting(self, name):
        self.events.append(("drafting", name))

    def clear(self):
        self.events.append(("clear", None))


class Provider(DescriptionProvider):
    def __init__(self, error=None):
        self.error = error

    def draft_docstring(self, context, known, slots):
        if self.error:
            raise self.error
        return DocstringDraft()


def generate(provider, progress):
    return (
        PyCodeCommenter(description_provider=provider, progress=progress)
        .from_string(CODE)
        .get_patched_code()
    )


def test_each_function_asked_about_is_announced_then_cleared():
    progress = RecordingProgress()

    generate(Provider(), progress)

    assert progress.events == [
        ("drafting", "total_due"),
        ("clear", None),
        ("drafting", "ping"),
        ("clear", None),
    ]


def test_the_line_is_cleared_when_the_provider_fails():
    progress = RecordingProgress()

    generate(Provider(error=RuntimeError("boom")), progress)

    assert progress.events == [
        ("drafting", "total_due"),
        ("clear", None),
        ("drafting", "ping"),
        ("clear", None),
    ]


def test_the_line_is_cleared_when_drafting_stops():
    progress = RecordingProgress()

    generate(Provider(error=DraftingStopped("limit", "Daily limit reached.")), progress)

    assert progress.events[-1] == ("clear", None)


def test_nothing_is_announced_without_a_provider():
    progress = RecordingProgress()

    generate(None, progress)

    assert progress.events == []


def test_generation_works_without_any_progress_object():
    assert "def total_due" in generate(Provider(), None)


def test_output_is_identical_with_or_without_progress():
    with_progress = generate(Provider(), RecordingProgress())
    without = generate(Provider(), None)

    assert with_progress == without


# ---------------------------------------------------------------------------
# Wiring into AI setup
# ---------------------------------------------------------------------------


def test_hosted_provider_is_labelled_and_reports_its_rate_limit_waits(
    monkeypatch,
):
    from PyCodeCommenter import ai_setup

    monkeypatch.setattr(ai_setup, "ensure_consent", lambda **_: True)
    progress, stream = make_progress()
    provider = ai_setup.build_ai_provider("hosted", None, None, progress=progress)

    assert progress.provider_label() == "hosted"

    provider.active._on_wait(30)
    assert "waiting 30 s" in stream.getvalue()


def test_own_key_provider_is_labelled_with_vendor_and_model():
    from PyCodeCommenter import ai_setup
    from PyCodeCommenter.description_provider import SwitchOnStop

    class Own(DescriptionProvider):
        label = "Anthropic"
        model = "claude-haiku-4-5-20251001"

    assert (
        ai_setup.provider_label(SwitchOnStop(Own(), lambda s: None))
        == "Anthropic, claude-haiku-4-5-20251001"
    )


def test_a_provider_without_a_name_still_gets_a_label():
    from PyCodeCommenter import ai_setup
    from PyCodeCommenter.description_provider import SwitchOnStop

    assert ai_setup.provider_label(SwitchOnStop(Provider(), lambda s: None)) == ""


def test_status_line_is_cleared_before_the_own_key_prompt(monkeypatch):
    from PyCodeCommenter import ai_setup

    monkeypatch.setattr(ai_setup, "ensure_consent", lambda **_: True)
    monkeypatch.setattr(ai_setup, "is_interactive", lambda: True)
    progress, stream = make_progress()
    seen = []
    monkeypatch.setattr(
        ai_setup,
        "offer_own_key",
        lambda stopped: seen.append(stream.getvalue()) or None,
    )
    provider = ai_setup.build_ai_provider("hosted", None, None, progress=progress)

    progress.start_file("a.py", 1, 2)
    progress.drafting("total_due")
    provider.on_stop(DraftingStopped("limit", "Daily limit reached."))

    assert seen and seen[0].endswith("\r")  # the line was blanked first


def test_generate_writes_no_progress_when_output_is_not_a_terminal(
    tmp_path, monkeypatch, capsys
):
    import sys

    from PyCodeCommenter.cli import main
    from PyCodeCommenter.description_provider import SwitchOnStop

    source = tmp_path / "a.py"
    source.write_text("def foo(x):\n    return x\n")
    monkeypatch.setattr(
        "PyCodeCommenter.cli.build_ai_provider",
        lambda *a, **k: SwitchOnStop(Provider(), lambda stopped: None),
    )
    monkeypatch.setattr(
        sys,
        "argv",
        ["pycodecommenter", "generate", str(source), "--ai-draft", "--dry-run"],
    )
    try:
        main()
    except SystemExit:
        pass

    assert "\r" not in capsys.readouterr().err


def test_own_key_provider_reports_its_rate_limit_waits_on_the_status_line(monkeypatch):
    from PyCodeCommenter import ai_setup

    class Own(DescriptionProvider):
        label = "Gemini"
        model = "gemini-2.5-flash"

    monkeypatch.setattr(ai_setup, "direct_provider", lambda *a, **k: Own())
    progress, stream = make_progress()

    provider = ai_setup.build_ai_provider("gemini", None, None, progress=progress)
    progress.start_file("a.py", 1, 2)
    provider.active.on_wait(20)

    assert "waiting 20 s for the rate limit" in stream.getvalue()
