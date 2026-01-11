"""Core business logic for parsing credit card faturas."""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import date
from decimal import Decimal
from enum import Enum
from pathlib import Path
from typing import Any, Optional, List, Dict, Protocol


class FileFormat(Enum):
    """Supported input file formats."""
    CSV = "csv"
    PDF = "pdf"


class ExportFormat(Enum):
    """Supported export formats."""
    CSV = "csv"
    YNAB = "ynab"


class TransactionType(Enum):
    """Type of transaction."""
    A_VISTA = "A_VISTA"
    PARCELADA = "PARCELADA"


class PaymentMethod(Enum):
    """Payment method used for transaction."""
    CHIP = "chip"
    CONTACTLESS = "contactless"
    APPLE_PAY = "apple_pay"
    GOOGLE_PAY = "google_pay"
    ONLINE = "online"
    UNKNOWN = "unknown"


@dataclass
class Installment:
    """Installment information for parcelada transactions."""
    current: int
    total: int


@dataclass
class InternationalInfo:
    """Information about international transactions."""
    original_amount: Decimal
    original_currency: str
    exchange_rate: Decimal
    city: Optional[str] = None


@dataclass
class Transaction:
    """Represents a single credit card transaction."""
    date: date
    description: str
    amount_brl: Decimal
    category: Optional[str] = None
    location: Optional[str] = None
    card_last_digits: Optional[str] = None
    transaction_type: TransactionType = TransactionType.A_VISTA
    installment: Optional[Installment] = None
    international: Optional[InternationalInfo] = None
    payment_method: PaymentMethod = PaymentMethod.UNKNOWN

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for JSON serialization."""
        result: Dict[str, Any] = {
            "date": self.date.isoformat(),
            "description": self.description,
            "amount_brl": str(self.amount_brl),
            "category": self.category,
            "location": self.location,
            "card_last_digits": self.card_last_digits,
            "transaction_type": self.transaction_type.value,
            "payment_method": self.payment_method.value,
        }
        if self.installment:
            result["installment"] = {
                "current": self.installment.current,
                "total": self.installment.total,
            }
        if self.international:
            result["international"] = {
                "original_amount": str(self.international.original_amount),
                "original_currency": self.international.original_currency,
                "exchange_rate": str(self.international.exchange_rate),
                "city": self.international.city,
            }
        return result

    def to_ynab_row(self) -> dict[str, str]:
        """Convert transaction to YNAB-compatible format."""
        return {
            "Date": self.date.strftime("%Y-%m-%d"),
            "Payee": self.description,
            "Memo": "",
            "Outflow": str(self.amount_brl) if self.amount_brl > 0 else "",
            "Inflow": str(abs(self.amount_brl)) if self.amount_brl < 0 else "",
        }


@dataclass
class Fatura:
    """Represents a parsed credit card statement (fatura)."""
    transactions: List[Transaction] = field(default_factory=list)
    source_file: str = ""
    card_issuer: Optional[str] = None
    statement_date: Optional[date] = None
    due_date: Optional[date] = None
    payment_date: Optional[date] = None
    previous_balance: Decimal = Decimal("0")
    payment_made: Decimal = Decimal("0")
    current_charges: Decimal = Decimal("0")
    total_amount: Decimal = Decimal("0")
    iof_international: Decimal = Decimal("0")

    @property
    def calculated_total(self) -> Decimal:
        """Calculate total from transactions."""
        return sum((t.amount_brl for t in self.transactions), Decimal("0"))

    @property
    def total(self) -> Decimal:
        """Calculate total amount of all transactions (alias for calculated_total)."""
        return self.calculated_total

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for JSON serialization."""
        return {
            "source_file": self.source_file,
            "card_issuer": self.card_issuer,
            "statement_date": self.statement_date.isoformat() if self.statement_date else None,
            "due_date": self.due_date.isoformat() if self.due_date else None,
            "payment_date": self.payment_date.isoformat() if self.payment_date else None,
            "previous_balance": str(self.previous_balance),
            "payment_made": str(self.payment_made),
            "current_charges": str(self.current_charges),
            "total_amount": str(self.total_amount),
            "iof_international": str(self.iof_international),
            "calculated_total": str(self.calculated_total),
            "transactions": [t.to_dict() for t in self.transactions],
        }


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
                    "amount": str(tx.amount_brl),
                    "category": tx.category or "",
                })


class YNABExporter:
    """Export fatura to YNAB-compatible CSV format.
    
    Features:
    - Transaction details (card, parcela, intl info) in memo field
    - Parcelada transactions use first of statement month as effective date
    - IOF as separate transaction on first of month
    - Previous fatura payment as credit on payment date
    """

    YNAB_HEADERS = ["Date", "Payee", "Memo", "Outflow", "Inflow"]

    def _format_date(self, d: date) -> str:
        """Format date as DD/MM/YYYY for YNAB."""
        return d.strftime("%d/%m/%Y")

    def _first_of_month(self, d: date) -> date:
        """Return the first day of the month for a given date."""
        return date(d.year, d.month, 1)

    def _build_memo(self, tx: Transaction, original_date: Optional[date] = None) -> str:
        """Build compact memo with transaction details separated by ';'."""
        parts: List[str] = []
        
        # Card info
        if tx.card_last_digits:
            parts.append(f"card:{tx.card_last_digits}")
        
        # Original date for parcelada
        if original_date:
            parts.append(f"orig:{original_date.strftime('%d/%m/%Y')}")
        
        # Installment info
        if tx.installment:
            parts.append(f"parcela:{tx.installment.current}/{tx.installment.total}")
        
        # International info
        if tx.international:
            intl = tx.international
            parts.append(f"intl:{intl.original_amount}{intl.original_currency}@{intl.exchange_rate}")
            if intl.city:
                parts.append(f"city:{intl.city}")
        
        # Category
        if tx.category:
            parts.append(f"cat:{tx.category}")
        
        # Location
        if tx.location:
            parts.append(f"loc:{tx.location}")
        
        return "; ".join(parts)

    def _format_amount(self, amount: Decimal) -> str:
        """Format amount with 2 decimal places."""
        return f"{abs(amount):.2f}"

    def export(self, fatura: Fatura, output_path: Path) -> Decimal:
        """Export fatura transactions to YNAB format.
        
        Returns the checksum (sum of all transactions except payment).
        """
        import csv
        
        rows: List[Dict[str, str]] = []
        checksum = Decimal("0")
        
        # Get statement first of month for parcelada effective date
        if fatura.statement_date:
            effective_date = self._first_of_month(fatura.statement_date)
        else:
            effective_date = date.today().replace(day=1)
        
        # Process all transactions
        for tx in fatura.transactions:
            # For parcelada, use first of statement month as effective date
            if tx.transaction_type == TransactionType.PARCELADA:
                tx_date = effective_date
                original_date = tx.date
            else:
                tx_date = tx.date
                original_date = None
            
            memo = self._build_memo(tx, original_date)
            
            row = {
                "Date": self._format_date(tx_date),
                "Payee": tx.description,
                "Memo": memo,
                "Outflow": self._format_amount(tx.amount_brl) if tx.amount_brl > 0 else "",
                "Inflow": self._format_amount(tx.amount_brl) if tx.amount_brl < 0 else "",
            }
            rows.append(row)
            checksum += tx.amount_brl
        
        # Add IOF as a transaction on first of month
        if fatura.iof_international > 0:
            row = {
                "Date": self._format_date(effective_date),
                "Payee": "IOF Internacional",
                "Memo": "iof",
                "Outflow": self._format_amount(fatura.iof_international),
                "Inflow": "",
            }
            rows.append(row)
            checksum += fatura.iof_international
        
        # Add payment of previous fatura as credit (negative/inflow)
        if fatura.payment_made > 0 and fatura.payment_date:
            row = {
                "Date": self._format_date(fatura.payment_date),
                "Payee": "Pagamento Fatura Anterior",
                "Memo": "payment",
                "Outflow": "",
                "Inflow": self._format_amount(fatura.payment_made),
            }
            rows.append(row)
            # Note: payment is NOT included in checksum per requirements
        
        # Write to file
        with output_path.open("w", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=self.YNAB_HEADERS)
            writer.writeheader()
            for row in rows:
                writer.writerow(row)
        
        return checksum


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
