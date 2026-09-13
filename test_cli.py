"""
Tests for the Phase 4 CLI changes: directory support for `generate` and
`validate`, `--fail-below` on `coverage`, and .pycodecommenter.yaml config
wiring (exclude / coverage.threshold); plus `--version` and single-file
`coverage` error handling.

cli.main() reads sys.argv and calls sys.exit(), so each test drives it via
monkeypatched argv and catches SystemExit rather than shelling out to a
subprocess (faster, and keeps coverage instrumentation working if this
suite is ever run under `pytest --cov`).
"""

import sys
import json

import pytest

from PyCodeCommenter.cli import main


def run_cli(args, monkeypatch, capsys):
    """Invoke cli.main() with argv=[<prog>, *args], return (exit_code, stdout,
    stderr)."""
    monkeypatch.setattr(sys, "argv", ["pycodecommenter"] + args)
    exit_code = 0
    try:
        main()
    except SystemExit as e:
        exit_code = e.code if isinstance(e.code, int) else (0 if e.code is None else 1)
    captured = capsys.readouterr()
    return exit_code, captured.out, captured.err


@pytest.fixture
def project(tmp_path, monkeypatch):
    """A small project: one undocumented function at the root, one already
    documented function in a subdirectory. Tests chdir here so
    load_config()'s cwd-relative search finds .pycodecommenter.yaml when
    a test writes one.
    """
    (tmp_path / "a.py").write_text("def foo(x, y):\n    return x + y\n")
    sub = tmp_path / "sub"
    sub.mkdir()
    (sub / "b.py").write_text('def bar(z):\n    """Existing doc."""\n    return z\n')
    monkeypatch.chdir(tmp_path)
    return tmp_path


# --- validate: directory mode ---------------------------------------------


def test_validate_directory_aggregates_and_exits_1_on_errors(
    project, monkeypatch, capsys
):
    # a.py's foo() has no docstring -> ERROR -> non-zero exit, aggregated
    # across the whole directory.
    exit_code, out, _ = run_cli(["validate", "."], monkeypatch, capsys)
    assert exit_code == 1
    assert "a.py" in out
    assert "sub" in out or "b.py" in out


def test_validate_directory_json_is_a_list_of_reports(project, monkeypatch, capsys):
    exit_code, out, _ = run_cli(
        ["validate", ".", "--output-format", "json"], monkeypatch, capsys
    )
    assert exit_code == 1
    reports = json.loads(out)
    assert isinstance(reports, list)
    assert len(reports) == 2
    files = {r["file"] for r in reports}
    assert any(f.endswith("a.py") for f in files)
    assert any("b.py" in f for f in files)


def test_validate_single_file_still_works_unchanged(project, monkeypatch, capsys):
    # Single-file behavior must be untouched by the directory-mode addition.
    exit_code, out, _ = run_cli(["validate", "a.py"], monkeypatch, capsys)
    assert exit_code == 1
    assert "File: a.py" in out


def test_validate_no_python_files_exits_0(tmp_path, monkeypatch, capsys):
    empty = tmp_path / "empty"
    empty.mkdir()
    monkeypatch.chdir(tmp_path)
    exit_code, out, _ = run_cli(["validate", "empty"], monkeypatch, capsys)
    assert exit_code == 0
    assert "No Python files found" in out


# --- generate: directory mode ----------------------------------------------


def test_generate_directory_dry_run_shows_diff_and_exits_1(
    project, monkeypatch, capsys
):
    exit_code, out, _ = run_cli(["generate", ".", "--dry-run"], monkeypatch, capsys)
    assert exit_code == 1
    assert "a.py" in out
    assert "+" in out  # unified diff shows an added docstring


def test_generate_directory_inplace_patches_files(project, monkeypatch, capsys):
    exit_code, out, _ = run_cli(["generate", ".", "--inplace"], monkeypatch, capsys)
    assert exit_code == 0
    patched = (project / "a.py").read_text()
    assert '"""' in patched
    assert "Successfully patched" in out


def test_generate_directory_rejects_output_flag(project, monkeypatch, capsys):
    exit_code, out, _ = run_cli(
        ["generate", ".", "--output", "combined.py"], monkeypatch, capsys
    )
    assert exit_code == 1
    assert "--output cannot be used with a directory" in out


def test_generate_directory_output_dir_mirrors_tree_without_touching_originals(
    project, monkeypatch, capsys
):
    """Regression test for AUDIT_REPORT.md §6: a directory target must be
    writable to a separate, fully-documented output tree, leaving the
    originals untouched -- the gap that made document_folder.py necessary
    as a hand-rolled external script."""
    exit_code, out, _ = run_cli(
        ["generate", ".", "--output-dir", "out"], monkeypatch, capsys
    )
    assert exit_code == 0
    assert (project / "out" / "a.py").exists()
    assert (project / "out" / "sub" / "b.py").exists()
    assert '"""' in (project / "out" / "a.py").read_text()
    # Originals must be untouched.
    assert (project / "a.py").read_text() == "def foo(x, y):\n    return x + y\n"
    assert "Wrote 2/2 file(s)" in out


def test_generate_directory_output_dir_rejects_inplace(project, monkeypatch, capsys):
    exit_code, out, _ = run_cli(
        ["generate", ".", "--output-dir", "out", "--inplace"], monkeypatch, capsys
    )
    assert exit_code == 1
    assert "--output-dir cannot be combined with --inplace" in out
    assert not (project / "out").exists()


def test_generate_single_file_rejects_output_dir(project, monkeypatch, capsys):
    exit_code, out, _ = run_cli(
        ["generate", "a.py", "--output-dir", "out"], monkeypatch, capsys
    )
    assert exit_code == 1
    assert "--output-dir cannot be used with a single-file target" in out


# --- exclude: CLI flag and config wiring ------------------------------------


def test_exclude_flag_skips_matching_files(project, monkeypatch, capsys):
    exit_code, out, _ = run_cli(
        ["validate", ".", "--exclude", "sub"], monkeypatch, capsys
    )
    assert "b.py" not in out
    assert "a.py" in out


def test_config_exclude_is_used_as_default(project, monkeypatch, capsys):
    (project / ".pycodecommenter.yaml").write_text("exclude:\n  - sub\n")
    exit_code, out, _ = run_cli(["validate", "."], monkeypatch, capsys)
    # sub/b.py should be skipped via config, same effect as an explicit
    # --exclude, without passing the flag.
    assert "b.py" not in out
    assert "a.py" in out


def test_explicit_exclude_flag_overrides_config(project, monkeypatch, capsys):
    (project / ".pycodecommenter.yaml").write_text("exclude:\n  - sub\n")
    # Passing --exclude with no patterns clears the exclude list entirely,
    # which should override (not merge with) the config's default.
    exit_code, out, _ = run_cli(["validate", ".", "--exclude"], monkeypatch, capsys)
    assert "b.py" in out


# --- coverage: --fail-below and config.coverage.threshold ------------------


def test_coverage_fail_below_explicit_flag(project, monkeypatch, capsys):
    exit_code, _, err = run_cli(
        ["coverage", ".", "--exclude", "--fail-below", "90"], monkeypatch, capsys
    )
    # a.py (0% documented) + sub/b.py (100%) averages well under 90%.
    assert exit_code == 1
    assert "below the 90" in err


def test_coverage_fail_below_passes_when_above_threshold(project, monkeypatch, capsys):
    exit_code, _, _ = run_cli(
        ["coverage", ".", "--exclude", "--fail-below", "0"], monkeypatch, capsys
    )
    assert exit_code == 0


def test_coverage_fail_below_defaults_from_config(project, monkeypatch, capsys):
    (project / ".pycodecommenter.yaml").write_text("coverage:\n  threshold: 90\n")
    exit_code, _, err = run_cli(["coverage", ".", "--exclude"], monkeypatch, capsys)
    assert exit_code == 1
    assert "below the 90" in err


def test_coverage_explicit_fail_below_overrides_config(project, monkeypatch, capsys):
    (project / ".pycodecommenter.yaml").write_text("coverage:\n  threshold: 90\n")
    exit_code, _, _ = run_cli(
        ["coverage", ".", "--exclude", "--fail-below", "0"], monkeypatch, capsys
    )
    assert exit_code == 0


def test_coverage_without_fail_below_or_config_never_exits_nonzero_for_it(
    project, monkeypatch, capsys
):
    # No --fail-below, no config threshold -> the fail-below check must be a
    # no-op regardless of how low coverage is.
    exit_code, _, _ = run_cli(["coverage", ".", "--exclude"], monkeypatch, capsys)
    assert exit_code == 0


# --- --version ---------------------------------------------------------


def test_version_flag_prints_version_and_exits_0(monkeypatch, capsys):
    from PyCodeCommenter import __version__

    exit_code, out, _ = run_cli(["--version"], monkeypatch, capsys)
    assert exit_code == 0
    assert __version__ in out


# --- coverage: single-file error handling -----------------------------


def test_coverage_single_file_syntax_error_exits_cleanly(tmp_path, monkeypatch, capsys):
    """A single-file `coverage` target that fails to parse must print a
    clean error and exit 1, not crash with an unhandled traceback -- same
    contract `generate`/`validate` already have for a broken single file.
    """
    bad_file = tmp_path / "broken.py"
    bad_file.write_text("def f(:\n")
    exit_code, _, err = run_cli(["coverage", str(bad_file)], monkeypatch, capsys)
    assert exit_code == 1
    assert "broken.py" in err


# --- generate: --ai-draft flag gating (no real network calls in any of
# these -- urlopen is mocked, and the consent file is isolated to a tmp
# home directory so tests never touch the real ~/.pycodecommenter/) -------


class _FakeAIResponse:
    def __init__(self, body):
        self._body = json.dumps(body).encode("utf-8")

    def read(self):
        return self._body

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False


@pytest.fixture
def isolated_consent_home(tmp_path, monkeypatch):
    """Points consent.py's ~/.pycodecommenter/ at a throwaway directory, so
    a test that records real consent (e.g. via --yes-send-code-to-hosted-ai)
    never writes to the actual developer machine's consent file."""
    import PyCodeCommenter.consent as consent

    fake_home = tmp_path / "fake_home"
    fake_home.mkdir()
    monkeypatch.setattr(consent.Path, "home", staticmethod(lambda: fake_home))
    return fake_home


@pytest.fixture
def fake_ai_backend(monkeypatch, isolated_consent_home):
    """Mocks the hosted backend's HTTP response and pre-grants consent, so
    CLI wiring (flag gating, consent gate, provider construction) is proven
    without touching the network or the real consent file."""
    import PyCodeCommenter.consent as consent

    consent.record_consent()

    captured = {"calls": 0}

    def fake_urlopen(request, timeout):
        captured["calls"] += 1
        return _FakeAIResponse({"description": "A fake AI-drafted description."})

    monkeypatch.setattr(
        "PyCodeCommenter.remote_provider.urllib.request.urlopen", fake_urlopen
    )
    return captured


def test_ai_draft_with_inplace_requires_accept_ai_drafts(project, monkeypatch, capsys):
    exit_code, out, _ = run_cli(
        ["generate", "a.py", "--ai-draft", "--inplace"], monkeypatch, capsys
    )
    assert exit_code == 1
    assert "--accept-ai-drafts" in out
    # Must not have written anything.
    assert "def foo" in (project / "a.py").read_text()
    assert "AI-drafted" not in (project / "a.py").read_text()


def test_ai_draft_without_consent_prompts_and_aborts_on_decline(
    project, monkeypatch, capsys, isolated_consent_home
):
    monkeypatch.setattr("builtins.input", lambda: "n")

    exit_code, out, _ = run_cli(
        ["generate", "a.py", "--ai-draft", "--dry-run"], monkeypatch, capsys
    )

    assert exit_code == 1
    assert "consent" in out.lower()
    assert "def foo" in (project / "a.py").read_text()


def test_ai_draft_with_dry_run_needs_no_extra_flag(
    project, monkeypatch, capsys, fake_ai_backend
):
    exit_code, out, _ = run_cli(
        ["generate", "a.py", "--ai-draft", "--dry-run"], monkeypatch, capsys
    )
    assert exit_code == 1  # dry-run's own "changes detected" exit code
    assert "A fake AI-drafted description." in out


def test_ai_draft_with_inplace_and_accept_flag_writes_marked_text(
    project, monkeypatch, capsys, fake_ai_backend
):
    exit_code, out, _ = run_cli(
        [
            "generate",
            "a.py",
            "--ai-draft",
            "--accept-ai-drafts",
            "--inplace",
        ],
        monkeypatch,
        capsys,
    )
    assert exit_code == 0
    patched = (project / "a.py").read_text()
    assert "A fake AI-drafted description." in patched
    assert "(AI-drafted, unreviewed)" in patched


def test_ai_draft_yes_flag_records_consent_non_interactively(
    project, monkeypatch, capsys, isolated_consent_home
):
    import PyCodeCommenter.consent as consent

    assert consent.has_given_consent() is False
    monkeypatch.setattr(
        "builtins.input", lambda: (_ for _ in ()).throw(AssertionError())
    )
    monkeypatch.setattr(
        "PyCodeCommenter.remote_provider.urllib.request.urlopen",
        lambda request, timeout: _FakeAIResponse({"description": "ok."}),
    )

    exit_code, out, _ = run_cli(
        [
            "generate",
            "a.py",
            "--ai-draft",
            "--dry-run",
            "--yes-send-code-to-hosted-ai",
        ],
        monkeypatch,
        capsys,
    )

    assert exit_code == 1  # dry-run's own "changes detected" exit code
    assert consent.has_given_consent() is True


def test_ai_draft_backend_url_is_overridable_via_env_var(
    project, monkeypatch, capsys, fake_ai_backend
):
    monkeypatch.setenv("PYCODECOMMENTER_AI_BACKEND_URL", "https://staging.example.test")
    captured_url = {}

    def fake_urlopen(request, timeout):
        captured_url["url"] = request.full_url
        return _FakeAIResponse({"description": "ok."})

    monkeypatch.setattr(
        "PyCodeCommenter.remote_provider.urllib.request.urlopen", fake_urlopen
    )

    run_cli(["generate", "a.py", "--ai-draft", "--dry-run"], monkeypatch, capsys)

    assert captured_url["url"] == "https://staging.example.test/v1/draft-description"


def test_ai_draft_shared_across_directory_run(
    project, monkeypatch, capsys, fake_ai_backend
):
    """Both files in the `project` fixture (2 functions total) should be
    processed in one run without errors, sharing the same provider
    instance."""
    exit_code, out, _ = run_cli(
        ["generate", ".", "--ai-draft", "--dry-run"], monkeypatch, capsys
    )
    assert fake_ai_backend["calls"] >= 1
