"""Smoke tests for the initial command-line composition root."""

import pytest

from regista.cli import build_parser, main


def test_parser_uses_product_name() -> None:
    assert build_parser().prog == "regista"


def test_empty_command_prints_help(capsys: pytest.CaptureFixture[str]) -> None:
    exit_code = main([])

    assert exit_code == 0
    assert "Explainable soccer player ratings" in capsys.readouterr().out
