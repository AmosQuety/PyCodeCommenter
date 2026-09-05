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
