"""`gag hooks`: the only way to read what a hook does without the repo."""

from __future__ import annotations

from typing import TYPE_CHECKING

from git_a_grip import hook_docs, version

if TYPE_CHECKING:
    import pytest

BAD_ARGS_CODE = 2
ESC = '\x1b['


def test_the_bare_command_lists_every_hook_in_one_line_each(
    capsys: pytest.CaptureFixture[str],
) -> None:
    # The point of the list: it has to fit a screen, or nobody reads to the
    # hook they came for.
    assert hook_docs.main([]) == 0

    out = capsys.readouterr().out
    for hook_id, doc in hook_docs.DOCS.items():
        assert hook_id in out
        assert doc.summary in out
    assert len(out.splitlines()) < len(hook_docs.DOCS) * 3


def test_the_list_is_alphabetical(
    capsys: pytest.CaptureFixture[str],
) -> None:
    # DOCS is ordered by what a reader should meet first; the list is
    # ordered by where a reader will look. Scanning for a known id in a
    # curated order means reading all eight lines.
    assert hook_docs.main([]) == 0

    out = capsys.readouterr().out
    seen = [
        hook_id
        for line in out.splitlines()
        for hook_id in hook_docs.DOCS
        if line.startswith(f'  {hook_id} ')
    ]
    assert seen == sorted(hook_docs.DOCS)


def test_the_list_says_where_the_detail_is(
    capsys: pytest.CaptureFixture[str],
) -> None:
    assert hook_docs.main([]) == 0

    out = capsys.readouterr().out
    assert 'gag hooks <id>' in out
    assert '--all' in out


def test_the_list_withholds_the_detail(
    capsys: pytest.CaptureFixture[str],
) -> None:
    assert hook_docs.main([]) == 0

    out = capsys.readouterr().out
    assert hook_docs.DOCS['tsc'].notes not in out
    assert 'by hand:' not in out


def test_all_documents_every_hook_in_full(
    capsys: pytest.CaptureFixture[str],
) -> None:
    assert hook_docs.main(['--all']) == 0

    out = capsys.readouterr().out
    for hook_id, doc in hook_docs.DOCS.items():
        assert doc.name in out
        # The hooks have no console scripts, so a person debugging one has
        # no way to guess this line.
        assert f'python -m git_a_grip.hooks {hook_id}' in out


def test_the_header_pins_the_installed_version(
    capsys: pytest.CaptureFixture[str],
) -> None:
    # The snippet is meant to be pasted, so its `rev` has to be a real tag.
    assert hook_docs.main([]) == 0

    out = capsys.readouterr().out
    assert version.as_rev(version.installed_version()) in out
    assert version.REPO_URL in out


def test_the_header_states_the_version_exactly_once(
    capsys: pytest.CaptureFixture[str],
) -> None:
    # A second copy of the version in the title line had no owner: commitizen
    # rewrites the `rev` at bump time and left the title a release behind in
    # the committed README.
    assert hook_docs.main([]) == 0

    out = capsys.readouterr().out
    assert out.count(version.installed_version()) == 1


def test_naming_a_hook_documents_only_that_one(
    capsys: pytest.CaptureFixture[str],
) -> None:
    assert hook_docs.main(['tsc']) == 0

    out = capsys.readouterr().out
    assert 'tsc' in out
    assert 'ruff-check' not in out
    # No header either: one hook is an answer, not an index.
    assert 'repos:' not in out


def test_unknown_hook_lists_the_known_ones(
    capsys: pytest.CaptureFixture[str],
) -> None:
    assert hook_docs.main(['ruff']) == BAD_ARGS_CODE

    err = capsys.readouterr().err
    assert 'ruff' in err
    assert 'ruff-check' in err


def test_help_names_every_hook(capsys: pytest.CaptureFixture[str]) -> None:
    assert hook_docs.main(['--help']) == 0

    out = capsys.readouterr().out
    assert 'usage: gag hooks' in out
    for hook_id in hook_docs.DOCS:
        assert hook_id in out


def test_a_pipe_gets_no_escape_codes(
    capsys: pytest.CaptureFixture[str],
) -> None:
    # capsys is not a tty, which is the case that matters: escapes in a pipe
    # end up in whatever the output was piped into.
    assert hook_docs.main([]) == 0
    assert hook_docs.main(['--all']) == 0

    assert ESC not in capsys.readouterr().out


def test_no_color_wins_over_a_tty(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv('NO_COLOR', '1')

    assert not hook_docs.style_for(_Tty()).enabled


def test_a_dumb_terminal_gets_no_color(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv('NO_COLOR', raising=False)
    monkeypatch.setenv('TERM', 'dumb')

    assert not hook_docs.style_for(_Tty()).enabled


def test_a_real_terminal_gets_color(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv('NO_COLOR', raising=False)
    monkeypatch.setenv('TERM', 'xterm-256color')
    paint = hook_docs.style_for(_Tty())

    assert paint.enabled
    assert paint('tsc', 'bold').startswith(ESC)
    # Colored or not, the text itself is unchanged.
    assert 'tsc' in paint('tsc', 'bold')


class _Tty:
    """Stand-in for a terminal: the one thing Style asks a stream."""

    def isatty(self) -> bool:
        return True
