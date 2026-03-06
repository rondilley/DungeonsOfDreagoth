"""Tests for command parser — parsing, completions."""

from dreagoth.core.command_parser import (
    parse_command, get_completions, get_all_command_names, COMMANDS,
)


class TestParseCommand:
    def test_parse_simple(self):
        cmd, args = parse_command("north")
        assert cmd is not None
        assert cmd.name == "north"
        assert args == []

    def test_parse_alias(self):
        cmd, args = parse_command("n")
        assert cmd is not None
        assert cmd.name == "north"

    def test_parse_with_args(self):
        cmd, args = parse_command("attack something")
        assert cmd is not None
        assert cmd.name == "attack"
        assert args == ["something"]

    def test_parse_unknown(self):
        cmd, args = parse_command("xyzzy")
        assert cmd is None
        assert args == []

    def test_parse_empty(self):
        cmd, args = parse_command("")
        assert cmd is None

    def test_parse_case_insensitive(self):
        cmd, args = parse_command("NORTH")
        assert cmd is not None
        assert cmd.name == "north"

    def test_all_commands_have_handlers(self):
        for cmd in COMMANDS:
            assert cmd.handler_name, f"Command {cmd.name} has no handler"


class TestCompletions:
    def test_complete_prefix(self):
        results = get_completions("no")
        assert "north" in results

    def test_complete_empty(self):
        results = get_completions("")
        assert len(results) == len(COMMANDS)

    def test_complete_unique(self):
        results = get_completions("qui")
        assert results == ["quit"]

    def test_complete_no_match(self):
        results = get_completions("zzz")
        assert results == []

    def test_all_names(self):
        names = get_all_command_names()
        assert "north" in names
        assert "attack" in names
        assert "quit" in names
        assert len(names) == len(COMMANDS)
