"""Core business logic for parsing credit card faturas."""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from enum import Enum
from pathlib import Path
from typing import Optional, Protocol


class FileFormat(Enum):
    """Supported input file formats."""
    CSV = "csv"
    PDF = "pdf"


class ExportFormat(Enum):
    """Supported export formats."""
    CSV = "csv"
    YNAB = "ynab"


@dataclass(frozen=True)
class Transaction:
    """Represents a single credit card transaction."""
    date: date
    description: str
    amount: Decimal
    category: str | None = None

    def to_ynab_row(self) -> dict[str, str]:
        """Convert transaction to YNAB-compatible format."""
        return {
            "Date": self.date.strftime("%Y-%m-%d"),
            "Payee": self.description,
            "Memo": "",
            "Outflow": str(self.amount) if self.amount > 0 else "",
            "Inflow": str(abs(self.amount)) if self.amount < 0 else "",
        }


@dataclass
class Fatura:
    """Represents a parsed credit card statement (fatura)."""
    transactions: list[Transaction]
    source_file: str
    card_issuer: str | None = None

    @property
    def total(self) -> Decimal:
        """Calculate total amount of all transactions."""
        return sum((t.amount for t in self.transactions), Decimal("0"))


class FaturaParser(Protocol):
    """Protocol for fatura parsers."""

    def parse(self, file_path: Path) -> Fatura:
        """Parse a fatura file and return structured data."""
        ...


class BaseFaturaParser(ABC):
    """Abstract base class for fatura parsers."""

    @abstractmethod
    def parse(self, file_path: Path) -> Fatura:
        """Parse a fatura file and return structured data."""
        raise NotImplementedError

    def _validate_file(self, file_path: Path) -> None:
        """Validate that the file exists and is readable."""
        if not file_path.exists():
            raise FileNotFoundError(f"File not found: {file_path}")
        if not file_path.is_file():
            raise ValueError(f"Not a file: {file_path}")


class CSVFaturaParser(BaseFaturaParser):
    """Parser for CSV fatura files."""

    def parse(self, file_path: Path) -> Fatura:
        """Parse a CSV fatura file."""
        self._validate_file(file_path)
        # TODO: Implement CSV parsing logic
        raise NotImplementedError("CSV parsing not yet implemented")


class PDFFaturaParser(BaseFaturaParser):
    """Parser for PDF fatura files."""

    def parse(self, file_path: Path) -> Fatura:
        """Parse a PDF fatura file."""
        self._validate_file(file_path)
        # TODO: Implement PDF parsing logic
        raise NotImplementedError("PDF parsing not yet implemented")


class FaturaExporter(Protocol):
    """Protocol for fatura exporters."""

    def export(self, fatura: Fatura, output_path: Path) -> None:
        """Export fatura to a file."""
        ...


class CSVExporter:
    """Export fatura to standard CSV format."""

    def export(self, fatura: Fatura, output_path: Path) -> None:
        """Export fatura transactions to CSV."""
        import csv

        with output_path.open("w", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=["date", "description", "amount", "category"])
            writer.writeheader()
            for tx in fatura.transactions:
                writer.writerow({
                    "date": tx.date.isoformat(),
                    "description": tx.description,
                    "amount": str(tx.amount),
                    "category": tx.category or "",
                })


class YNABExporter:
    """Export fatura to YNAB-compatible CSV format."""

    YNAB_HEADERS = ["Date", "Payee", "Memo", "Outflow", "Inflow"]

    def export(self, fatura: Fatura, output_path: Path) -> None:
        """Export fatura transactions to YNAB format."""
        import csv

        with output_path.open("w", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=self.YNAB_HEADERS)
            writer.writeheader()
            for tx in fatura.transactions:
                writer.writerow(tx.to_ynab_row())


def get_parser(file_format: FileFormat) -> BaseFaturaParser:
    """Factory function to get the appropriate parser."""
    parsers: dict[FileFormat, type[BaseFaturaParser]] = {
        FileFormat.CSV: CSVFaturaParser,
        FileFormat.PDF: PDFFaturaParser,
    }
    return parsers[file_format]()


def get_exporter(export_format: ExportFormat) -> CSVExporter | YNABExporter:
    """Factory function to get the appropriate exporter."""
    exporters: dict[ExportFormat, type[CSVExporter] | type[YNABExporter]] = {
        ExportFormat.CSV: CSVExporter,
        ExportFormat.YNAB: YNABExporter,
    }
    return exporters[export_format]()
