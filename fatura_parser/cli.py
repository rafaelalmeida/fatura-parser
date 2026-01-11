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


class CardIssuer:
    """Supported card issuers."""
    ITAU = "itau"
    GENERIC = "generic"


def create_parser() -> argparse.ArgumentParser:
    """Create and configure the argument parser for single file mode."""
    parser = argparse.ArgumentParser(
        prog="fatura-parser",
        description="Parse Brazilian credit card faturas (CSV/PDF) into structured formats",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  %(prog)s fatura.pdf --issuer itau -o output.json
  %(prog)s fatura.csv -o output.csv
  %(prog)s fatura.pdf --format ynab -o transactions.csv
  
Batch mode:
  %(prog)s --batch /path/to/pdfs --format ynab
  %(prog)s --batch /path/to/pdfs --format json -p ~/.fatura-password
        """,
    )

    # Batch mode flag
    parser.add_argument(
        "--batch",
        type=Path,
        metavar="DIR",
        help="Run in interactive batch mode: process all PDFs in DIR",
    )

    parser.add_argument(
        "input",
        type=Path,
        nargs="?",
        help="Input fatura file (CSV or PDF)",
    )

    parser.add_argument(
        "-o", "--output",
        type=Path,
        help="Output file path (default: <input>_parsed.json for Itaú, .csv otherwise)",
    )

    parser.add_argument(
        "-f", "--format",
        type=str,
        choices=["csv", "ynab", "json"],
        default="json",
        help="Output format (default: json for Itaú PDFs)",
    )

    parser.add_argument(
        "-t", "--type",
        type=str,
        choices=[f.value for f in FileFormat],
        help="Input file type (default: auto-detect from extension)",
    )

    parser.add_argument(
        "-i", "--issuer",
        type=str,
        choices=[CardIssuer.ITAU, CardIssuer.GENERIC],
        default=CardIssuer.ITAU,
        help="Card issuer (default: itau)",
    )

    parser.add_argument(
        "-v", "--verbose",
        action="store_true",
        help="Enable verbose output",
    )

    parser.add_argument(
        "-p", "--password-file",
        type=Path,
        help="Path to file containing PDF password (for encrypted PDFs)",
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


def run_itau_parser(args: argparse.Namespace) -> int:
    """Run the Itaú-specific parser."""
    from fatura_parser.parsers.itau import ItauPDFParser

    input_path: Path = args.input
    
    # Read password from file if provided
    password: str | None = None
    if args.password_file:
        password_file: Path = args.password_file
        if not password_file.exists():
            print(f"Error: Password file not found: {password_file}", file=sys.stderr)
            return 1
        password = password_file.read_text().strip()
    
    # Determine output path
    output_path = args.output
    if output_path is None:
        ext = ".json" if args.format == "json" else ".csv"
        output_path = input_path.with_name(f"{input_path.stem}_parsed{ext}")

    if args.verbose:
        print(f"Input: {input_path}")
        print(f"Issuer: Itaú")
        print(f"Output: {output_path}")
        print(f"Format: {args.format}")

    try:
        parser = ItauPDFParser()
        fatura = parser.parse(input_path, password=password)

        # Export based on format
        if args.format == "json":
            parser.export_json(fatura, output_path)
        elif args.format == "ynab":
            from fatura_parser.core import YNABExporter
            exporter = YNABExporter()
            checksum = exporter.export(fatura, output_path)
            
            # Print YNAB-specific checksum (excludes payment)
            print(f"\n{'='*50}")
            print("YNAB EXPORT CHECKSUM")
            print(f"{'='*50}")
            print(f"Sum of transactions (excl. payment): R$ {checksum:,.2f}".replace(",", "X").replace(".", ",").replace("X", "."))
            print(f"PDF total (current charges):         R$ {fatura.total_amount:,.2f}".replace(",", "X").replace(".", ",").replace("X", "."))
            print(f"{'='*50}")
            print(f"Transactions exported:     {len(fatura.transactions)}")
            if fatura.iof_international > 0:
                print(f"IOF transaction added:     R$ {fatura.iof_international:,.2f}".replace(",", "X").replace(".", ",").replace("X", "."))
            if fatura.payment_made > 0:
                print(f"Payment credit added:      R$ {fatura.payment_made:,.2f}".replace(",", "X").replace(".", ",").replace("X", "."))
            print(f"Output written to:         {output_path}")
            return 0
        else:  # csv
            from fatura_parser.core import CSVExporter
            exporter = CSVExporter()
            exporter.export(fatura, output_path)

        # Print checksum information
        print(f"\n{'='*50}")
        print("CHECKSUM VERIFICATION")
        print(f"{'='*50}")
        print(f"Parsed total from PDF:     R$ {fatura.total_amount:,.2f}".replace(",", "X").replace(".", ",").replace("X", "."))
        print(f"Calculated from txns:      R$ {fatura.calculated_total:,.2f}".replace(",", "X").replace(".", ",").replace("X", "."))
        
        difference = fatura.total_amount - fatura.calculated_total
        if difference == 0:
            print(f"Difference:                R$ 0,00 ✓")
        else:
            print(f"Difference:                R$ {difference:,.2f}".replace(",", "X").replace(".", ",").replace("X", "."))
            print(f"  (IOF Internacional:      R$ {fatura.iof_international:,.2f})".replace(",", "X").replace(".", ",").replace("X", "."))
        
        print(f"{'='*50}")
        print(f"Transactions parsed:       {len(fatura.transactions)}")
        print(f"Output written to:         {output_path}")
        
        return 0

    except Exception as e:
        print(f"Error: {e}", file=sys.stderr)
        if args.verbose:
            import traceback
            traceback.print_exc()
        return 1


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

    # Use Itaú parser for PDFs when issuer is itau
    if args.issuer == CardIssuer.ITAU and file_format == FileFormat.PDF:
        return run_itau_parser(args)

    # Determine output path
    output_path = args.output
    if output_path is None:
        output_path = input_path.with_name(f"{input_path.stem}_parsed.csv")

    export_format = ExportFormat(args.format) if args.format in ["csv", "ynab"] else ExportFormat.CSV

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
    
    # Handle batch mode
    if args.batch:
        from fatura_parser.batch import run_batch
        sys.exit(run_batch(
            root_dir=args.batch,
            export_format=args.format,
            password_file=args.password_file,
            verbose=args.verbose,
        ))
    
    # Single file mode requires input
    if args.input is None:
        parser.error("the following arguments are required: input (or use --batch for batch mode)")
    
    sys.exit(run(args))


if __name__ == "__main__":
    main()
