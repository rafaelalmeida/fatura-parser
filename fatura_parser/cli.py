"""Command-line interface for fatura-parser."""

import argparse
import sys
from pathlib import Path

from fatura_parser.core import (
    ExportFormat,
    FileFormat,
    get_exporter,
    get_parser,
)


def create_parser() -> argparse.ArgumentParser:
    """Create and configure the argument parser."""
    parser = argparse.ArgumentParser(
        prog="fatura-parser",
        description="Parse Brazilian credit card faturas (CSV/PDF) into structured formats",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  %(prog)s fatura.csv -o output.csv
  %(prog)s fatura.pdf --format ynab -o transactions.csv
  %(prog)s fatura.csv --format ynab
        """,
    )

    parser.add_argument(
        "input",
        type=Path,
        help="Input fatura file (CSV or PDF)",
    )

    parser.add_argument(
        "-o", "--output",
        type=Path,
        help="Output file path (default: stdout or <input>_parsed.csv)",
    )

    parser.add_argument(
        "-f", "--format",
        type=str,
        choices=[f.value for f in ExportFormat],
        default=ExportFormat.CSV.value,
        help="Output format (default: csv)",
    )

    parser.add_argument(
        "-t", "--type",
        type=str,
        choices=[f.value for f in FileFormat],
        help="Input file type (default: auto-detect from extension)",
    )

    parser.add_argument(
        "-v", "--verbose",
        action="store_true",
        help="Enable verbose output",
    )

    parser.add_argument(
        "--version",
        action="version",
        version="%(prog)s 0.1.0",
    )

    return parser


def detect_file_format(file_path: Path) -> FileFormat:
    """Auto-detect file format from extension."""
    suffix = file_path.suffix.lower()
    format_map = {
        ".csv": FileFormat.CSV,
        ".pdf": FileFormat.PDF,
    }
    if suffix not in format_map:
        raise ValueError(f"Unsupported file extension: {suffix}")
    return format_map[suffix]


def run(args: argparse.Namespace) -> int:
    """Execute the main logic with parsed arguments."""
    input_path: Path = args.input

    # Validate input file exists
    if not input_path.exists():
        print(f"Error: File not found: {input_path}", file=sys.stderr)
        return 1

    # Determine file format
    try:
        if args.type:
            file_format = FileFormat(args.type)
        else:
            file_format = detect_file_format(input_path)
    except ValueError as e:
        print(f"Error: {e}", file=sys.stderr)
        return 1

    # Determine output path
    output_path = args.output
    if output_path is None:
        output_path = input_path.with_name(f"{input_path.stem}_parsed.csv")

    export_format = ExportFormat(args.format)

    if args.verbose:
        print(f"Input: {input_path}")
        print(f"Input format: {file_format.value}")
        print(f"Output: {output_path}")
        print(f"Export format: {export_format.value}")

    try:
        # Parse the fatura
        parser = get_parser(file_format)
        fatura = parser.parse(input_path)

        # Export to desired format
        exporter = get_exporter(export_format)
        exporter.export(fatura, output_path)

        if args.verbose:
            print(f"Successfully parsed {len(fatura.transactions)} transactions")
            print(f"Total: {fatura.total}")

        print(f"Output written to: {output_path}")
        return 0

    except NotImplementedError as e:
        print(f"Error: {e}", file=sys.stderr)
        return 1
    except Exception as e:
        print(f"Error: {e}", file=sys.stderr)
        return 1


def main() -> None:
    """Main entry point for the CLI."""
    parser = create_parser()
    args = parser.parse_args()
    sys.exit(run(args))


if __name__ == "__main__":
    main()
