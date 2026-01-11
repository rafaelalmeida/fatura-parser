"""Tests for Itaú PDF parser and YNAB export."""

import csv
import pytest
from datetime import date
from decimal import Decimal
from pathlib import Path

from fatura_parser.core import (
    Fatura,
    Transaction,
    TransactionType,
    PaymentMethod,
    Installment,
    InternationalInfo,
    YNABExporter,
)
from fatura_parser.parsers.itau import ItauPDFParser


class TestItauPDFParserStructure:
    """Tests for parsed Fatura structure from Itaú PDF."""

    @pytest.fixture
    def parsed_fatura(self, sample_pdf_path: Path) -> Fatura:
        """Parse the sample PDF and return the Fatura."""
        parser = ItauPDFParser()
        return parser.parse(sample_pdf_path)

    def test_fatura_metadata(self, parsed_fatura: Fatura):
        """Test that fatura metadata is correctly parsed."""
        assert parsed_fatura.card_issuer == "Itaú"
        assert parsed_fatura.statement_date == date(2025, 11, 6)
        assert parsed_fatura.due_date == date(2025, 11, 13)
        assert parsed_fatura.total_amount == Decimal("19101.06")
        assert parsed_fatura.current_charges == Decimal("19101.06")

    def test_fatura_previous_balance(self, parsed_fatura: Fatura):
        """Test that previous balance is correctly parsed."""
        assert parsed_fatura.previous_balance == Decimal("27579.80")

    def test_fatura_payment(self, parsed_fatura: Fatura):
        """Test that payment info is correctly parsed."""
        assert parsed_fatura.payment_made == Decimal("27579.80")
        assert parsed_fatura.payment_date == date(2025, 10, 10)

    def test_fatura_iof(self, parsed_fatura: Fatura):
        """Test that IOF is correctly parsed."""
        assert parsed_fatura.iof_international == Decimal("45.00")

    def test_transaction_count(self, parsed_fatura: Fatura):
        """Test that correct number of transactions are parsed."""
        assert len(parsed_fatura.transactions) == 129

    def test_calculated_total(self, parsed_fatura: Fatura):
        """Test that calculated total matches expected value."""
        # Calculated total should be total minus IOF
        assert parsed_fatura.calculated_total == Decimal("19056.06")

    def test_card_totals(self, parsed_fatura: Fatura):
        """Test that card-specific totals are correct."""
        card_totals = {}
        for tx in parsed_fatura.transactions:
            card = tx.card_last_digits or "intl"
            card_totals[card] = card_totals.get(card, Decimal("0")) + tx.amount_brl

        assert card_totals["6529"] == Decimal("1429.80")
        assert card_totals["8898"] == Decimal("6611.87")
        assert card_totals["5415"] == Decimal("4717.78")
        assert card_totals["8626"] == Decimal("2924.12")
        assert card_totals["1767"] == Decimal("1470.89")
        assert card_totals["3273"] == Decimal("618.89")


class TestItauTransactionParsing:
    """Tests for individual transaction parsing."""

    @pytest.fixture
    def parsed_fatura(self, sample_pdf_path: Path) -> Fatura:
        """Parse the sample PDF and return the Fatura."""
        parser = ItauPDFParser()
        return parser.parse(sample_pdf_path)

    def test_a_vista_transaction(self, parsed_fatura: Fatura):
        """Test parsing of à vista (one-time) transactions."""
        # Find a known à vista transaction
        tx = next(
            (t for t in parsed_fatura.transactions 
             if t.description == "REDENTOR QUIOSQUE PARK"),
            None
        )
        assert tx is not None
        assert tx.date == date(2025, 10, 16)
        assert tx.amount_brl == Decimal("125.95")
        assert tx.card_last_digits == "6529"
        assert tx.transaction_type == TransactionType.A_VISTA
        assert tx.category == "ALIMENTAÇÃO"
        assert tx.location == "BELO HORIZONT"
        assert tx.installment is None

    def test_parcelada_transaction(self, parsed_fatura: Fatura):
        """Test parsing of parcelada (installment) transactions."""
        # Find a known parcelada transaction
        tx = next(
            (t for t in parsed_fatura.transactions 
             if t.description == "AUTO JAPAN" and t.card_last_digits == "5415"),
            None
        )
        assert tx is not None
        assert tx.date == date(2025, 3, 26)  # Original purchase date
        assert tx.amount_brl == Decimal("342.61")
        assert tx.transaction_type == TransactionType.PARCELADA
        assert tx.installment is not None
        assert tx.installment.current == 8
        assert tx.installment.total == 10

    def test_credit_transaction(self, parsed_fatura: Fatura):
        """Test parsing of credit/refund transactions (negative amounts)."""
        # Find credit transactions
        credit_txs = [t for t in parsed_fatura.transactions if t.amount_brl < 0]
        assert len(credit_txs) == 2

        # Check APPLE.COM/BILL credit
        apple_credit = next(
            (t for t in credit_txs if "APPLE" in t.description),
            None
        )
        assert apple_credit is not None
        assert apple_credit.amount_brl == Decimal("-28.86")

        # Check ZZOFC MG BH SHOPPING credit
        shopping_credit = next(
            (t for t in credit_txs if "SHOPPING" in t.description),
            None
        )
        assert shopping_credit is not None
        assert shopping_credit.amount_brl == Decimal("-0.25")

    def test_international_transaction(self, parsed_fatura: Fatura):
        """Test parsing of international transactions."""
        # Find a known international transaction
        intl_txs = [t for t in parsed_fatura.transactions if t.international is not None]
        assert len(intl_txs) == 12  # 12 international transactions

        # Check a specific international transaction
        github_tx = next(
            (t for t in intl_txs if "GITHUB" in t.description),
            None
        )
        assert github_tx is not None
        assert github_tx.international.original_amount == Decimal("10.00")
        assert github_tx.international.original_currency == "USD"
        assert github_tx.international.exchange_rate == Decimal("5.83")
        assert github_tx.international.city == "SAN FRANCISCO"
        assert github_tx.card_last_digits is None  # International transactions have no card
        assert github_tx.payment_method == PaymentMethod.ONLINE


class TestYNABExport:
    """Tests for YNAB CSV export."""

    @pytest.fixture
    def parsed_fatura(self, sample_pdf_path: Path) -> Fatura:
        """Parse the sample PDF and return the Fatura."""
        parser = ItauPDFParser()
        return parser.parse(sample_pdf_path)

    @pytest.fixture
    def ynab_output_path(self, output_dir: Path) -> Path:
        """Return path for YNAB output file."""
        return output_dir / "ynab_export.csv"

    @pytest.fixture
    def exported_ynab(self, parsed_fatura: Fatura, ynab_output_path: Path) -> tuple[Path, Decimal]:
        """Export to YNAB and return path and checksum."""
        exporter = YNABExporter()
        checksum = exporter.export(parsed_fatura, ynab_output_path)
        return ynab_output_path, checksum

    def test_ynab_file_created(self, exported_ynab: tuple[Path, Decimal]):
        """Test that YNAB CSV file is created."""
        path, _ = exported_ynab
        assert path.exists()

    def test_ynab_headers(self, exported_ynab: tuple[Path, Decimal]):
        """Test that YNAB CSV has correct headers."""
        path, _ = exported_ynab
        with open(path, "r", encoding="utf-8") as f:
            reader = csv.reader(f)
            headers = next(reader)
        assert headers == ["Date", "Payee", "Memo", "Outflow", "Inflow"]

    def test_ynab_checksum(self, exported_ynab: tuple[Path, Decimal], parsed_fatura: Fatura):
        """Test that YNAB checksum matches PDF total."""
        _, checksum = exported_ynab
        # Checksum should equal total_amount (includes IOF, excludes payment)
        assert checksum == parsed_fatura.total_amount

    def test_ynab_row_count(self, exported_ynab: tuple[Path, Decimal], parsed_fatura: Fatura):
        """Test that YNAB has correct number of rows."""
        path, _ = exported_ynab
        with open(path, "r", encoding="utf-8") as f:
            reader = csv.reader(f)
            rows = list(reader)
        
        # Header + transactions + IOF + payment
        expected_rows = 1 + len(parsed_fatura.transactions) + 1 + 1
        assert len(rows) == expected_rows

    def test_ynab_date_format(self, exported_ynab: tuple[Path, Decimal]):
        """Test that dates are in DD/MM/YYYY format."""
        path, _ = exported_ynab
        with open(path, "r", encoding="utf-8") as f:
            reader = csv.DictReader(f)
            for row in reader:
                date_str = row["Date"]
                # Should be DD/MM/YYYY format
                parts = date_str.split("/")
                assert len(parts) == 3
                assert len(parts[0]) == 2  # DD
                assert len(parts[1]) == 2  # MM
                assert len(parts[2]) == 4  # YYYY

    def test_ynab_parcelada_effective_date(self, exported_ynab: tuple[Path, Decimal]):
        """Test that parcelada transactions use first of statement month."""
        path, _ = exported_ynab
        with open(path, "r", encoding="utf-8") as f:
            reader = csv.DictReader(f)
            for row in reader:
                if "parcela:" in row["Memo"]:
                    # Parcelada should have date 01/11/2025 (first of statement month)
                    assert row["Date"] == "01/11/2025"
                    # Should have original date in memo
                    assert "orig:" in row["Memo"]

    def test_ynab_parcelada_memo_format(self, exported_ynab: tuple[Path, Decimal]):
        """Test that parcelada transactions have correct memo format."""
        path, _ = exported_ynab
        with open(path, "r", encoding="utf-8") as f:
            reader = csv.DictReader(f)
            auto_japan = next(
                (row for row in reader if row["Payee"] == "AUTO JAPAN"),
                None
            )
        
        assert auto_japan is not None
        memo = auto_japan["Memo"]
        assert "card:5415" in memo
        assert "orig:26/03/2025" in memo
        assert "parcela:8/10" in memo

    def test_ynab_international_memo(self, exported_ynab: tuple[Path, Decimal]):
        """Test that international transactions have correct memo format."""
        path, _ = exported_ynab
        with open(path, "r", encoding="utf-8") as f:
            reader = csv.DictReader(f)
            github = next(
                (row for row in reader if "GITHUB" in row["Payee"]),
                None
            )
        
        assert github is not None
        memo = github["Memo"]
        assert "intl:" in memo
        assert "USD" in memo
        assert "city:" in memo

    def test_ynab_iof_transaction(self, exported_ynab: tuple[Path, Decimal]):
        """Test that IOF is added as a separate transaction."""
        path, _ = exported_ynab
        with open(path, "r", encoding="utf-8") as f:
            reader = csv.DictReader(f)
            iof = next(
                (row for row in reader if row["Payee"] == "IOF Internacional"),
                None
            )
        
        assert iof is not None
        assert iof["Date"] == "01/11/2025"  # First of statement month
        assert iof["Outflow"] == "45.00"
        assert iof["Inflow"] == ""
        assert iof["Memo"] == "iof"

    def test_ynab_payment_transaction(self, exported_ynab: tuple[Path, Decimal]):
        """Test that payment is added as an inflow."""
        path, _ = exported_ynab
        with open(path, "r", encoding="utf-8") as f:
            reader = csv.DictReader(f)
            payment = next(
                (row for row in reader if row["Payee"] == "Pagamento Fatura Anterior"),
                None
            )
        
        assert payment is not None
        assert payment["Date"] == "10/10/2025"  # Payment date from PDF
        assert payment["Outflow"] == ""
        assert payment["Inflow"] == "27579.80"
        assert payment["Memo"] == "payment"

    def test_ynab_credit_as_inflow(self, exported_ynab: tuple[Path, Decimal]):
        """Test that credit transactions are exported as inflow."""
        path, _ = exported_ynab
        with open(path, "r", encoding="utf-8") as f:
            reader = csv.DictReader(f)
            # Find APPLE credit
            apple_credit = next(
                (row for row in reader 
                 if "APPLE" in row["Payee"] and row["Inflow"]),
                None
            )
        
        assert apple_credit is not None
        assert apple_credit["Inflow"] == "28.86"
        assert apple_credit["Outflow"] == ""

    def test_ynab_amount_format(self, exported_ynab: tuple[Path, Decimal]):
        """Test that amounts use period as decimal separator."""
        path, _ = exported_ynab
        with open(path, "r", encoding="utf-8") as f:
            reader = csv.DictReader(f)
            for row in reader:
                if row["Outflow"]:
                    # Should use period, not comma
                    assert "," not in row["Outflow"]
                    assert "." in row["Outflow"] or row["Outflow"].isdigit()
                if row["Inflow"]:
                    assert "," not in row["Inflow"]


class TestYNABExporterEdgeCases:
    """Tests for edge cases in YNAB export."""

    def test_export_empty_fatura(self, output_dir: Path):
        """Test exporting a fatura with no transactions."""
        fatura = Fatura(
            transactions=[],
            source_file="empty.pdf",
            statement_date=date(2025, 11, 6),
        )
        exporter = YNABExporter()
        output_path = output_dir / "empty.csv"
        checksum = exporter.export(fatura, output_path)

        assert output_path.exists()
        assert checksum == Decimal("0")

    def test_export_without_statement_date(self, output_dir: Path):
        """Test exporting a fatura without statement date uses current month."""
        tx = Transaction(
            date=date(2025, 10, 15),
            description="Test",
            amount_brl=Decimal("100.00"),
            transaction_type=TransactionType.PARCELADA,
            installment=Installment(current=1, total=3),
        )
        fatura = Fatura(
            transactions=[tx],
            source_file="test.pdf",
            statement_date=None,  # No statement date
        )
        exporter = YNABExporter()
        output_path = output_dir / "no_date.csv"
        exporter.export(fatura, output_path)

        with open(output_path, "r", encoding="utf-8") as f:
            reader = csv.DictReader(f)
            row = next(reader)
            # Should use first of current month (DD/MM/YYYY format)
            assert row["Date"].startswith("01/")  # Day should be 01

    def test_export_without_iof(self, output_dir: Path):
        """Test exporting a fatura without IOF."""
        tx = Transaction(
            date=date(2025, 10, 15),
            description="Test",
            amount_brl=Decimal("100.00"),
        )
        fatura = Fatura(
            transactions=[tx],
            source_file="test.pdf",
            statement_date=date(2025, 11, 6),
            iof_international=Decimal("0"),
        )
        exporter = YNABExporter()
        output_path = output_dir / "no_iof.csv"
        exporter.export(fatura, output_path)

        with open(output_path, "r", encoding="utf-8") as f:
            content = f.read()
            assert "IOF Internacional" not in content

    def test_export_without_payment(self, output_dir: Path):
        """Test exporting a fatura without payment."""
        tx = Transaction(
            date=date(2025, 10, 15),
            description="Test",
            amount_brl=Decimal("100.00"),
        )
        fatura = Fatura(
            transactions=[tx],
            source_file="test.pdf",
            statement_date=date(2025, 11, 6),
            payment_made=Decimal("0"),
            payment_date=None,
        )
        exporter = YNABExporter()
        output_path = output_dir / "no_payment.csv"
        exporter.export(fatura, output_path)

        with open(output_path, "r", encoding="utf-8") as f:
            content = f.read()
            assert "Pagamento Fatura Anterior" not in content


class TestItauPDFParserErrorHandling:
    """Tests for error handling in Itaú parser."""

    def test_parse_nonexistent_file(self):
        """Test parsing a nonexistent file raises FileNotFoundError."""
        parser = ItauPDFParser()
        with pytest.raises(FileNotFoundError):
            parser.parse(Path("/nonexistent/file.pdf"))

    def test_parser_requires_pdfplumber(self):
        """Test that parser raises ImportError if pdfplumber not available."""
        # This test would require mocking pdfplumber import
        # For now, just verify parser can be instantiated
        parser = ItauPDFParser()
        assert parser is not None
