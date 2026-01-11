"""Interactive batch processing for fatura PDFs."""

from __future__ import annotations

import os
import sys
from datetime import datetime
from enum import Enum
from pathlib import Path
from typing import Optional, List, Tuple

try:
    from colorama import init, Fore, Style
    init(autoreset=True)
except ImportError:
    # Fallback if colorama not installed
    class Fore:
        GREEN = RED = YELLOW = CYAN = MAGENTA = WHITE = BLUE = ""
    class Style:
        BRIGHT = RESET_ALL = DIM = ""


class FileStatus(Enum):
    """Status of a processed file."""
    ACCEPTED = "accepted"
    REJECTED = "rejected"
    SKIPPED = "skipped"
    ERROR = "error"


class BatchLogger:
    """Logger for batch processing operations."""
    
    def __init__(self, log_dir: Path, export_format: str):
        self.log_dir = log_dir
        self.log_dir.mkdir(parents=True, exist_ok=True)
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        self.log_file = self.log_dir / f"batch_export_{export_format}_{timestamp}.log"
        self.entries: List[Tuple[datetime, FileStatus, Path, str]] = []
        
        # Write header
        with open(self.log_file, "w") as f:
            f.write(f"Fatura Parser Batch Export Log\n")
            f.write(f"Started: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
            f.write(f"Export format: {export_format}\n")
            f.write(f"Root directory: {log_dir}\n")
            f.write("=" * 60 + "\n\n")
    
    def log(self, status: FileStatus, file_path: Path, message: str = ""):
        """Log a file processing result."""
        timestamp = datetime.now()
        self.entries.append((timestamp, status, file_path, message))
        
        with open(self.log_file, "a") as f:
            status_str = status.value.upper()
            time_str = timestamp.strftime("%H:%M:%S")
            f.write(f"[{time_str}] [{status_str:8}] {file_path}\n")
            if message:
                f.write(f"           {message}\n")
    
    def write_summary(self):
        """Write final summary to log file."""
        counts = {status: 0 for status in FileStatus}
        for _, status, _, _ in self.entries:
            counts[status] += 1
        
        with open(self.log_file, "a") as f:
            f.write("\n" + "=" * 60 + "\n")
            f.write("SUMMARY\n")
            f.write("=" * 60 + "\n")
            f.write(f"Finished: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
            f.write(f"Total files processed: {len(self.entries)}\n")
            f.write(f"  Accepted: {counts[FileStatus.ACCEPTED]}\n")
            f.write(f"  Rejected: {counts[FileStatus.REJECTED]}\n")
            f.write(f"  Skipped:  {counts[FileStatus.SKIPPED]}\n")
            f.write(f"  Errors:   {counts[FileStatus.ERROR]}\n")
        
        return counts


def colored_print(message: str, color: str = "", style: str = ""):
    """Print a colored message."""
    print(f"{style}{color}{message}{Style.RESET_ALL}")


def prompt_yes_no(message: str, default: Optional[bool] = None) -> bool:
    """Prompt user for yes/no input with optional default."""
    if default is True:
        suffix = "[Y/n]"
    elif default is False:
        suffix = "[y/N]"
    else:
        suffix = "[y/n]"
    
    while True:
        response = input(f"{Fore.CYAN}{message} {suffix}: {Style.RESET_ALL}").strip().lower()
        if response == "":
            if default is not None:
                return default
            continue
        if response in ("y", "yes"):
            return True
        if response in ("n", "no"):
            return False
        print(f"{Fore.YELLOW}Please enter 'y' or 'n'{Style.RESET_ALL}")


def prompt_skip_replace(file_path: Path) -> str:
    """Prompt user to skip, replace, or view existing file."""
    while True:
        response = input(
            f"{Fore.CYAN}File exists. [s]kip, [r]eplace, or [v]iew? {Style.RESET_ALL}"
        ).strip().lower()
        if response in ("s", "skip"):
            return "skip"
        if response in ("r", "replace"):
            return "replace"
        if response in ("v", "view"):
            return "view"
        print(f"{Fore.YELLOW}Please enter 's', 'r', or 'v'{Style.RESET_ALL}")


def format_brl(value) -> str:
    """Format a value as Brazilian currency."""
    return f"R$ {value:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")


def print_file_header(pdf_path: Path, index: int, total: int):
    """Print header for a file being processed."""
    print()
    print(f"{Fore.BLUE}{Style.BRIGHT}{'=' * 60}{Style.RESET_ALL}")
    print(f"{Fore.BLUE}{Style.BRIGHT}[{index}/{total}] {pdf_path.name}{Style.RESET_ALL}")
    print(f"{Fore.BLUE}{Style.BRIGHT}{'=' * 60}{Style.RESET_ALL}")
    colored_print(f"Path: {pdf_path}", Fore.WHITE, Style.DIM)


def print_summary(fatura, export_format: str):
    """Print fatura summary with checksum."""
    print()
    colored_print("CHECKSUM VERIFICATION", Fore.WHITE, Style.BRIGHT)
    colored_print("-" * 40, Fore.WHITE, Style.DIM)
    
    print(f"  Statement date:    {Fore.WHITE}{fatura.statement_date}{Style.RESET_ALL}")
    print(f"  Due date:          {Fore.WHITE}{fatura.due_date}{Style.RESET_ALL}")
    print(f"  Transactions:      {Fore.WHITE}{len(fatura.transactions)}{Style.RESET_ALL}")
    
    # Calculate checksum
    calculated = sum(t.amount_brl for t in fatura.transactions)
    pdf_total = fatura.total_amount
    difference = pdf_total - calculated
    
    print(f"  PDF total:         {Fore.WHITE}{format_brl(pdf_total)}{Style.RESET_ALL}")
    print(f"  Calculated:        {Fore.WHITE}{format_brl(calculated)}{Style.RESET_ALL}")
    
    # IOF explains the difference
    if fatura.iof_international > 0:
        print(f"  IOF Internacional: {Fore.YELLOW}{format_brl(fatura.iof_international)}{Style.RESET_ALL}")
    
    if abs(difference) < 0.01 or abs(difference - fatura.iof_international) < 0.01:
        colored_print("  ✓ Checksum OK", Fore.GREEN, Style.BRIGHT)
    else:
        colored_print(f"  ✗ Difference: {format_brl(difference)}", Fore.RED, Style.BRIGHT)
    
    if export_format == "ynab":
        print()
        colored_print("YNAB Export includes:", Fore.WHITE, Style.DIM)
        print(f"  - {len(fatura.transactions)} transactions")
        if fatura.iof_international > 0:
            print(f"  - 1 IOF transaction ({format_brl(fatura.iof_international)})")
        if fatura.payment_made > 0:
            print(f"  - 1 payment credit ({format_brl(fatura.payment_made)})")


def print_cards_summary(fatura):
    """Print summary of cards found."""
    if fatura.cards:
        print()
        colored_print(f"Cards found: {len(fatura.cards)}", Fore.WHITE, Style.DIM)
        for digits, card in fatura.cards.items():
            txn_count = len([t for t in fatura.transactions if t.card and t.card.last_digits == digits])
            print(f"  {card.display_id}: {txn_count} transactions")


def find_pdf_files(root_dir: Path) -> List[Path]:
    """Recursively find all PDF files in a directory."""
    pdf_files = []
    for path in root_dir.rglob("*.pdf"):
        pdf_files.append(path)
    for path in root_dir.rglob("*.PDF"):
        if path not in pdf_files:
            pdf_files.append(path)
    return sorted(pdf_files)


def run_batch(
    root_dir: Path,
    export_format: str,
    password_file: Optional[Path] = None,
    verbose: bool = False,
) -> int:
    """Run interactive batch processing on all PDFs in a directory.
    
    Args:
        root_dir: Root directory to search for PDFs
        export_format: Export format ('json' or 'ynab')
        password_file: Optional path to file containing PDF password
        verbose: Enable verbose output
    
    Returns:
        Exit code (0 for success)
    """
    from fatura_parser.parsers.itau import ItauPDFParser
    from fatura_parser.core import YNABExporter
    
    # Validate inputs
    if not root_dir.exists():
        colored_print(f"Error: Directory not found: {root_dir}", Fore.RED)
        return 1
    
    if not root_dir.is_dir():
        colored_print(f"Error: Not a directory: {root_dir}", Fore.RED)
        return 1
    
    # Read password if provided
    password: Optional[str] = None
    if password_file:
        if not password_file.exists():
            colored_print(f"Error: Password file not found: {password_file}", Fore.RED)
            return 1
        password = password_file.read_text().strip()
    
    # Find all PDFs
    pdf_files = find_pdf_files(root_dir)
    
    if not pdf_files:
        colored_print(f"No PDF files found in {root_dir}", Fore.YELLOW)
        return 0
    
    # Initialize
    print()
    colored_print(f"Fatura Parser - Interactive Batch Mode", Fore.MAGENTA, Style.BRIGHT)
    colored_print("=" * 60, Fore.MAGENTA)
    print(f"Root directory: {root_dir}")
    print(f"Export format:  {export_format}")
    print(f"PDFs found:     {len(pdf_files)}")
    if password_file:
        print(f"Password file:  {password_file}")
    print()
    
    if not prompt_yes_no("Continue?", default=True):
        colored_print("Aborted.", Fore.YELLOW)
        return 0
    
    # Initialize logger
    logger = BatchLogger(root_dir, export_format)
    colored_print(f"Log file: {logger.log_file}", Fore.WHITE, Style.DIM)
    
    # Initialize parser
    parser = ItauPDFParser()
    
    # Process each file
    for i, pdf_path in enumerate(pdf_files, 1):
        print_file_header(pdf_path, i, len(pdf_files))
        
        # Determine output path
        if export_format == "json":
            output_path = pdf_path.with_suffix(".json")
        else:  # ynab
            output_path = pdf_path.with_suffix(".csv")
        
        # Check if output already exists
        if output_path.exists():
            colored_print(f"Output exists: {output_path.name}", Fore.YELLOW)
            
            while True:
                action = prompt_skip_replace(output_path)
                if action == "skip":
                    colored_print("Skipped.", Fore.YELLOW)
                    logger.log(FileStatus.SKIPPED, pdf_path, f"Output already exists: {output_path.name}")
                    break
                elif action == "view":
                    # Show first few lines of existing file
                    print()
                    colored_print(f"Contents of {output_path.name}:", Fore.WHITE, Style.DIM)
                    with open(output_path) as f:
                        lines = f.readlines()[:10]
                        for line in lines:
                            print(f"  {line.rstrip()}")
                        if len(lines) == 10:
                            print(f"  {Fore.WHITE}{Style.DIM}... (truncated){Style.RESET_ALL}")
                    print()
                    continue
                else:  # replace
                    # Continue to process
                    break
            else:
                continue
            
            if action == "skip":
                continue
        
        # Parse the PDF
        try:
            colored_print("Parsing...", Fore.WHITE, Style.DIM)
            fatura = parser.parse(pdf_path, password=password)
            
            if not fatura.transactions:
                colored_print("Warning: No transactions found!", Fore.YELLOW)
                if not prompt_yes_no("Continue anyway?", default=False):
                    logger.log(FileStatus.REJECTED, pdf_path, "No transactions found, user rejected")
                    continue
            
            # Show summary
            print_summary(fatura, export_format)
            print_cards_summary(fatura)
            
        except Exception as e:
            colored_print(f"Error parsing: {e}", Fore.RED)
            logger.log(FileStatus.ERROR, pdf_path, str(e))
            if verbose:
                import traceback
                traceback.print_exc()
            continue
        
        # Export to temp location first
        print()
        if prompt_yes_no("Accept and save?", default=True):
            try:
                if export_format == "json":
                    parser.export_json(fatura, output_path)
                else:  # ynab
                    exporter = YNABExporter()
                    exporter.export(fatura, output_path)
                
                colored_print(f"✓ Saved: {output_path.name}", Fore.GREEN, Style.BRIGHT)
                logger.log(FileStatus.ACCEPTED, pdf_path, f"Exported to {output_path.name}")
                
            except Exception as e:
                colored_print(f"Error saving: {e}", Fore.RED)
                logger.log(FileStatus.ERROR, pdf_path, f"Export error: {e}")
        else:
            colored_print("Rejected.", Fore.YELLOW)
            # Remove file if it was created
            if output_path.exists():
                output_path.unlink()
                colored_print(f"Removed: {output_path.name}", Fore.YELLOW, Style.DIM)
            logger.log(FileStatus.REJECTED, pdf_path, "User rejected")
    
    # Print final summary
    counts = logger.write_summary()
    
    print()
    colored_print("=" * 60, Fore.MAGENTA, Style.BRIGHT)
    colored_print("BATCH PROCESSING COMPLETE", Fore.MAGENTA, Style.BRIGHT)
    colored_print("=" * 60, Fore.MAGENTA, Style.BRIGHT)
    print(f"  {Fore.GREEN}Accepted:{Style.RESET_ALL} {counts[FileStatus.ACCEPTED]}")
    print(f"  {Fore.YELLOW}Rejected:{Style.RESET_ALL} {counts[FileStatus.REJECTED]}")
    print(f"  {Fore.YELLOW}Skipped:{Style.RESET_ALL}  {counts[FileStatus.SKIPPED]}")
    print(f"  {Fore.RED}Errors:{Style.RESET_ALL}   {counts[FileStatus.ERROR]}")
    print()
    colored_print(f"Log file: {logger.log_file}", Fore.WHITE, Style.DIM)
    
    return 0
