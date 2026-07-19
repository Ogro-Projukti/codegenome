"""Module entry point for the unified CodeGenome CLI."""

from __future__ import annotations

from codegenome.cli import cli


def main() -> None:
    """Run the same Click command group exposed by the console script."""
    cli(prog_name="python -m codegenome")


if __name__ == "__main__":
    main()
