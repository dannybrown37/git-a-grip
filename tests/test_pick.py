"""`pick` is the interactive layer, so its tests are mostly about refusing."""

from __future__ import annotations

import subprocess

import pytest

from git_a_grip import pick


@pytest.fixture
def tty(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(pick.sys.stdin, 'isatty', lambda: True)
    monkeypatch.setattr(pick.sys.stderr, 'isatty', lambda: True)


@pytest.fixture
def no_fzf(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(pick.shutil, 'which', lambda _: None)


class TestOffATty:
    @pytest.mark.parametrize(
        'call',
        [
            lambda: pick.ask('term: ', missing='--term'),
            lambda: pick.choose(['a'], prompt='p', missing='--term'),
        ],
        ids=['ask', 'choose'],
    )
    def test_it_raises_naming_the_argument(
        self,
        monkeypatch: pytest.MonkeyPatch,
        call: object,
    ) -> None:
        monkeypatch.setattr(pick.sys.stdin, 'isatty', lambda: False)

        with pytest.raises(pick.NotInteractiveError, match='--term'):
            call()  # type: ignore[operator]


@pytest.mark.usefixtures('tty', 'no_fzf')
class TestNumberedFallback:
    def test_a_choice_comes_back(
        self,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        monkeypatch.setattr('builtins.input', lambda: '2')

        chosen = pick.choose(
            ['one', 'two'],
            prompt='pick: ',
            missing='--thing',
        )

        assert chosen == ['two']

    def test_several_come_back_in_order_asked_for(
        self,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        monkeypatch.setattr('builtins.input', lambda: '1, 3')

        chosen = pick.choose(
            ['one', 'two', 'three'],
            prompt='pick: ',
            missing='--thing',
            multi=True,
        )

        assert chosen == ['one', 'three']

    @pytest.mark.parametrize('answer', ['', '9', 'nope'])
    def test_a_blank_or_bad_answer_is_a_decline_not_a_default(
        self,
        monkeypatch: pytest.MonkeyPatch,
        answer: str,
    ) -> None:
        monkeypatch.setattr('builtins.input', lambda: answer)

        assert pick.choose(['one'], prompt='p: ', missing='--thing') == []

    def test_eof_is_a_decline(self, monkeypatch: pytest.MonkeyPatch) -> None:
        def raise_eof() -> str:
            raise EOFError

        monkeypatch.setattr('builtins.input', raise_eof)

        assert pick.ask('term: ', missing='--term') == ''


@pytest.mark.usefixtures('tty')
class TestFzf:
    def test_it_is_used_when_present(
        self,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        monkeypatch.delenv(pick.NO_FZF, raising=False)
        monkeypatch.setattr(pick.shutil, 'which', lambda _: '/usr/bin/fzf')
        seen: dict[str, object] = {}

        def fake_run(command: list[str], **kwargs: object):  # noqa: ANN202
            seen['command'] = command
            seen['input'] = kwargs['input']
            return subprocess.CompletedProcess(command, 0, 'two\n', '')

        monkeypatch.setattr(pick.subprocess, 'run', fake_run)

        chosen = pick.choose(
            ['one', 'two'],
            prompt='pick: ',
            missing='--thing',
        )

        assert chosen == ['two']
        assert seen['input'] == 'one\ntwo'
        assert '--prompt=pick: ' in seen['command']  # type: ignore[operator]

    def test_the_ui_is_left_on_the_terminal(
        self,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        monkeypatch.delenv(pick.NO_FZF, raising=False)
        monkeypatch.setattr(pick.shutil, 'which', lambda _: '/usr/bin/fzf')
        seen: dict[str, object] = {}

        def fake_run(command: list[str], **kwargs: object):  # noqa: ANN202
            seen.update(kwargs)
            return subprocess.CompletedProcess(command, 0, 'one\n')

        monkeypatch.setattr(pick.subprocess, 'run', fake_run)

        pick.choose(['one'], prompt='p: ', missing='--thing')

        assert seen.get('capture_output') is not True
        assert seen['stdout'] == subprocess.PIPE
        assert 'stderr' not in seen

    def test_a_nonzero_exit_is_a_decline(
        self,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        monkeypatch.delenv(pick.NO_FZF, raising=False)
        monkeypatch.setattr(pick.shutil, 'which', lambda _: '/usr/bin/fzf')
        monkeypatch.setattr(
            pick.subprocess,
            'run',
            lambda command, **_: subprocess.CompletedProcess(command, 130),
        )

        assert pick.choose(['one'], prompt='p: ', missing='--thing') == []

    def test_the_env_var_forces_the_fallback(
        self,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        monkeypatch.setenv(pick.NO_FZF, '1')
        monkeypatch.setattr(pick.shutil, 'which', lambda _: '/usr/bin/fzf')
        monkeypatch.setattr('builtins.input', lambda: '1')

        assert pick.choose(['one'], prompt='p: ', missing='--x') == ['one']
