"""Tests for core business logic."""

import pytest
from datetime import date
from decimal import Decimal
from pathlib import Path

from fatura_parser.core import (
    CSVExporter,
    CSVFaturaParser,
    ExportFormat,
    Fatura,
    FileFormat,
    PDFFaturaParser,
    Transaction,
    YNABExporter,
    get_exporter,
    get_parser,
)


class TestTransaction:
    """Tests for Transaction dataclass."""

    def test_transaction_creation(self):
        tx = Transaction(
            date=date(2026, 1, 5),
            description="Restaurant XYZ",
            amount_brl=Decimal("150.50"),
        )
        assert tx.date == date(2026, 1, 5)
        assert tx.description == "Restaurant XYZ"
        assert tx.amount_brl == Decimal("150.50")
        assert tx.category is None

    def test_transaction_to_ynab_row_positive(self):
        tx = Transaction(
            date=date(2026, 1, 5),
            description="Restaurant XYZ",
            amount_brl=Decimal("150.50"),
        )
        row = tx.to_ynab_row()
        assert row["Date"] == "2026-01-05"
        assert row["Payee"] == "Restaurant XYZ"
        assert row["Outflow"] == "150.50"
        assert row["Inflow"] == ""

    def test_transaction_to_ynab_row_negative(self):
        tx = Transaction(
            date=date(2026, 1, 5),
            description="Credit/Refund",
            amount_brl=Decimal("-50.00"),
        )
        row = tx.to_ynab_row()
        assert row["Outflow"] == ""
        assert row["Inflow"] == "50.00"


class TestFatura:
    """Tests for Fatura dataclass."""

    def test_fatura_total(self):
        transactions = [
            Transaction(date(2026, 1, 1), "Item 1", Decimal("100")),
            Transaction(date(2026, 1, 2), "Item 2", Decimal("200")),
            Transaction(date(2026, 1, 3), "Refund", Decimal("-50")),
        ]
        fatura = Fatura(transactions=transactions, source_file="test.csv")
        assert fatura.total == Decimal("250")

    def test_fatura_empty(self):
        fatura = Fatura(transactions=[], source_file="test.csv")
        assert fatura.total == Decimal("0")


class TestCSVFaturaParser:
    """Tests for CSV parser."""

    def test_parse_nonexistent_file(self):
        parser = CSVFaturaParser()
        with pytest.raises(FileNotFoundError):
            parser.parse(Path("/nonexistent/file.csv"))

    def test_parse_not_implemented(self, sample_csv_path: Path):
        parser = CSVFaturaParser()
        # Create a dummy file if it doesn't exist
        if not sample_csv_path.exists():
            sample_csv_path.parent.mkdir(parents=True, exist_ok=True)
            sample_csv_path.write_text("date,description,amount\n")
        
        with pytest.raises(NotImplementedError):
            parser.parse(sample_csv_path)


class TestPDFFaturaParser:
    """Tests for PDF parser."""

    def test_parse_not_implemented(self, sample_pdf_path: Path):
        parser = PDFFaturaParser()
        # Create a dummy file if it doesn't exist
        if not sample_pdf_path.exists():
            sample_pdf_path.parent.mkdir(parents=True, exist_ok=True)
            sample_pdf_path.write_bytes(b"%PDF-1.4\n")
        
        with pytest.raises(NotImplementedError):
            parser.parse(sample_pdf_path)


class TestExporters:
    """Tests for exporters."""

    @pytest.fixture
    def sample_fatura(self) -> Fatura:
        """Create a sample fatura for testing."""
        return Fatura(
            transactions=[
                Transaction(date(2026, 1, 1), "Store A", Decimal("100.50")),
                Transaction(date(2026, 1, 2), "Store B", Decimal("200.00"), category="Food"),
            ],
            source_file="test.csv",
            statement_date=date(2026, 1, 11),
        )

    def test_csv_exporter(self, sample_fatura: Fatura, output_dir: Path):
        exporter = CSVExporter()
        output_path = output_dir / "output.csv"
        exporter.export(sample_fatura, output_path)
        
        assert output_path.exists()
        content = output_path.read_text()
        assert "date,description,amount,category" in content
        assert "2026-01-01,Store A,100.50," in content
        assert "2026-01-02,Store B,200.00,Food" in content

    def test_ynab_exporter(self, sample_fatura: Fatura, output_dir: Path):
        exporter = YNABExporter()
        output_path = output_dir / "output.csv"
        exporter.export(sample_fatura, output_path)
        
        assert output_path.exists()
        content = output_path.read_text()
        assert "Date,Payee,Memo,Outflow,Inflow" in content
        assert "01/01/2026,Store A" in content
        assert "100.50" in content


class TestFactoryFunctions:
    """Tests for factory functions."""

    def test_get_parser_csv(self):
        parser = get_parser(FileFormat.CSV)
        assert isinstance(parser, CSVFaturaParser)

    def test_get_parser_pdf(self):
        parser = get_parser(FileFormat.PDF)
        assert isinstance(parser, PDFFaturaParser)

    def test_get_exporter_csv(self):
        exporter = get_exporter(ExportFormat.CSV)
        assert isinstance(exporter, CSVExporter)

    def test_get_exporter_ynab(self):
        exporter = get_exporter(ExportFormat.YNAB)
        assert isinstance(exporter, YNABExporter)
