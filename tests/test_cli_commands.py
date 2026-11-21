"""Tests for T239 (P20, 2026-11-21): stratos/__main__.py's _main was one 600-line if/elif chain over args.cmd.
Each command becomes its own function in the same module (tests patch cli.Gateway, cli.run_all and
cli.refresh_memory, so the functions stay in stratos/__main__.py and look those names up there):

- cli.COMMANDS: a dict from every subcommand name to its function: "add", "plan", "plan-critique", "plan-add",
  "plan-tests", "run", "run-all", "status", "report", "push", "clean", "reset", "drop", "accept", "cases",
  "replay", "memory", "dashboard". The function for name n is called cmd_<n with "-" as "_"> (cmd_run_all ...).
- Each function takes (args, store, parser) - parser is the argparse subparser of that command (add uses
  parser.error for a goal file it cannot read) - and returns the exit code the old branch returned.
- _main builds the parsers as before, keeps the subparsers in a dict by name, and ends with
  `return COMMANDS[args.cmd](args, store, parsers[args.cmd])`; no `args.cmd ==` comparison is left in the module.
- The old final `else:` branch printed the task list: that is cmd_status.
Behaviour is unchanged: every other test of the command line (cli.main) still passes."""
import ast
import inspect

from stratos import __main__ as cli

NAMES = ["add", "plan", "plan-critique", "plan-add", "plan-tests", "run", "run-all", "status", "report", "push",
         "clean", "reset", "drop", "accept", "cases", "replay", "memory", "dashboard"]


def test_commands_table():
    assert sorted(cli.COMMANDS) == sorted(NAMES)
    for name in NAMES:
        fn = cli.COMMANDS[name]
        assert fn.__name__ == "cmd_" + name.replace("-", "_"), name
        assert getattr(cli, fn.__name__) is fn
        assert list(inspect.signature(fn).parameters) == ["args", "store", "parser"], name


def test_no_dispatch_chain_left():
    src = inspect.getsource(cli)
    assert "args.cmd ==" not in src
    tree = ast.parse(src)
    main = next(n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name == "_main")
    last = main.body[-1]
    assert isinstance(last, ast.Return)
    assert ast.unparse(last.value) == "COMMANDS[args.cmd](args, store, parsers[args.cmd])"


def test_status_runs_through_the_table(capsys):
    assert cli.main(["status"]) == 0
