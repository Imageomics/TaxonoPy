"""Generate CLI help pages for MkDocs without shell execution."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

import mkdocs_gen_files

ROOT = Path(__file__).resolve().parents[2]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from taxonopy.cli import create_parser  # noqa: E402


def get_subparser(parser: argparse.ArgumentParser, name: str) -> argparse.ArgumentParser:
    for action in parser._actions:
        if isinstance(action, argparse._SubParsersAction):
            if name in action.choices:
                return action.choices[name]
    raise KeyError(f"Subparser '{name}' not found")


def render_section(title: str, help_text: str) -> str:
    return f"## `{title}`\n\n```console\n{help_text.rstrip()}\n```\n"


def main() -> None:
    parser = create_parser()
    parser.prog = "taxonopy"
    resolve_parser = get_subparser(parser, "resolve")
    trace_parser = get_subparser(parser, "trace")
    trace_entry_parser = get_subparser(trace_parser, "entry")
    common_parser = get_subparser(parser, "common-names")

    resolve_parser.prog = "taxonopy resolve"
    trace_parser.prog = "taxonopy trace"
    trace_entry_parser.prog = "taxonopy trace entry"
    common_parser.prog = "taxonopy common-names"

    sections = [
        ("taxonopy --help", parser.format_help()),
        ("taxonopy resolve --help", resolve_parser.format_help()),
        ("taxonopy trace --help", trace_parser.format_help()),
        ("taxonopy trace entry --help", trace_entry_parser.format_help()),
        ("taxonopy common-names --help", common_parser.format_help()),
    ]

    with mkdocs_gen_files.open("command_line_usage/help.md", "w") as file_handle:
        file_handle.write("# Help\n\n")
        file_handle.write("Command reference for the TaxonoPy CLI.\n\n")
        for title, help_text in sections:
            file_handle.write(render_section(title, help_text))
            file_handle.write("\n")


if __name__ in {"__main__", "<run_path>"}:
    main()
