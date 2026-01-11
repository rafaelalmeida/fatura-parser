"""Parser for Itaú credit card fatura PDFs."""

from __future__ import annotations

import re
from datetime import date
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Any, Optional, List, Dict, Tuple
import json

from ..core import (
    Transaction,
    Fatura,
    TransactionType,
    PaymentMethod,
    Installment,
    InternationalInfo,
)

try:
    import pdfplumber
except ImportError:
    pdfplumber = None  # type: ignore


class ItauPDFParser:
    """Parser for Itaú credit card fatura PDFs."""

    # Column boundaries for two-column layout (x coordinates)
    LEFT_COLUMN_START = 140
    LEFT_COLUMN_END = 355
    RIGHT_COLUMN_START = 355
    
    # Text extraction settings - use x_tolerance=1 for proper word spacing
    TEXT_EXTRACTION_SETTINGS = {"x_tolerance": 1}
    
    # Regex patterns (updated for properly spaced text)
    # Note: Credit transactions have "- " (minus with space) before amount
    DATE_PATTERN = re.compile(r"^(\d{2}/\d{2})\s+")
    AMOUNT_PATTERN = re.compile(r"((?:-\s*)?\d{1,3}(?:[\. ]\d{3})*,\d{2})$")
    CATEGORY_LOCATION_PATTERN = re.compile(r"^([A-ZÇÃÕÉÊÍÓÚÀÂÔÜ][A-ZÇÃÕÉÊÍÓÚÀÂÔÜ ]*?)\s*\.\s*([A-Za-zçãõéêíóúàâôü ]+)$")
    INSTALLMENT_PATTERN = re.compile(r"(\d{2})/(\d{2})\s+((?:-\s*)?\d{1,3}(?:[\. ]\d{3})*,\d{2})$")
    CARD_FINAL_PATTERN = re.compile(r"final\s*(\d{4})")
    TOTAL_FATURA_PATTERN = re.compile(r"Total\s*desta\s*fatura\s+(-?\d{1,3}(?:[\. ]\d{3})*,\d{2})")
    PREVIOUS_BALANCE_PATTERN = re.compile(r"Total\s*da\s*fatura\s*anterior\s+(-?\d{1,3}(?:[\. ]\d{3})*,\d{2})")
    PAYMENT_PATTERN = re.compile(r"Pagamento\s*efetuado\s*em\s*(\d{2}/\d{2}/\d{4})\s*[-\s]+(\d{1,3}(?:[.\s]\d{3})*,\d{2})")
    CURRENT_CHARGES_PATTERN = re.compile(r"Lançamentos\s*atuais\s+(-?\d{1,3}(?:[\. ]\d{3})*,\d{2})")
    DUE_DATE_PATTERN = re.compile(r"Vencimento\s*:\s*(\d{2}/\d{2}/\d{4})")
    STATEMENT_DATE_PATTERN = re.compile(r"Emissão\s*:\s*(\d{2}/\d{2}/\d{4})")
    CARD_SUBTOTAL_PATTERN = re.compile(r"Lançamentos\s*no\s*cartão\s*\(\s*final\s*(\d{4})\s*\)\s+(-?\d{1,3}(?:[\. ]\d{3})*,\d{2})")
    INTL_TOTAL_PATTERN = re.compile(r"Total\s*transações\s*inter\.?\s*em\s*R\s*\$\s*(-?\d{1,3}(?:[\. ]\d{3})*,\d{2})")
    IOF_INTL_PATTERN = re.compile(r"Repasse\s*de\s*IOF\s*em\s*R\s*\$\s*(-?\d{1,3}(?:[\. ]\d{3})*,\d{2})")
    EXCHANGE_RATE_PATTERN = re.compile(r"Dólar\s*de\s*Conversão\s*R\s*\$\s*(\d+,\d{2})")
    INTL_DETAILS_PATTERN = re.compile(r"([A-Z][A-Z0-9\- ]+?)\s+(\d+,\d{2})\s+(USD|BRL|EUR)\s+(\d+,\d{2})")

    def __init__(self):
        if pdfplumber is None:
            raise ImportError("pdfplumber is required for PDF parsing. Install with: pip install pdfplumber")

    def parse(self, file_path: Path) -> Fatura:
        """Parse an Itaú fatura PDF and return structured data."""
        if not file_path.exists():
            raise FileNotFoundError(f"File not found: {file_path}")

        fatura = Fatura(source_file=str(file_path), card_issuer="Itaú")
        
        with pdfplumber.open(file_path) as pdf:
            # First pass: extract summary from page 1
            self._parse_summary(pdf.pages[0], fatura)
            
            # Track state across pages and columns
            state: Dict[str, Any] = {
                "current_card": None,
                "in_future_section": False,
                "in_intl_section": False,
            }
            
            # Second pass: extract transactions using column cropping
            for page in pdf.pages:
                self._parse_page_columns(page, fatura, state)
            
            # Third pass: parse international transactions
            self._parse_international_from_text(pdf, fatura)
        
        return fatura

    def _parse_brl_amount(self, amount_str: str) -> Decimal:
        """Parse a Brazilian format amount string to Decimal.
        
        Handles formats like:
        - "1.234,56" -> 1234.56
        - "-1.234,56" -> -1234.56
        - "- 1.234,56" -> -1234.56 (space after minus, used for credits)
        """
        # Remove spaces first (handles "- 123,45" format for credits)
        cleaned = amount_str.replace(" ", "").replace(".", "").replace(",", ".")
        try:
            return Decimal(cleaned)
        except InvalidOperation:
            return Decimal("0")

    def _parse_date(self, date_str: str, year: int = 2025) -> date:
        """Parse a date string in DD/MM format."""
        parts = date_str.strip().split("/")
        day = int(parts[0])
        month = int(parts[1])
        return date(year, month, day)

    def _parse_full_date(self, date_str: str) -> date:
        """Parse a full date string in DD/MM/YYYY format."""
        parts = date_str.strip().split("/")
        return date(int(parts[2]), int(parts[1]), int(parts[0]))

    def _parse_summary(self, page, fatura: Fatura) -> None:
        """Parse the summary section from page 1."""
        text = page.extract_text(**self.TEXT_EXTRACTION_SETTINGS) or ""
        
        match = self.TOTAL_FATURA_PATTERN.search(text)
        if match:
            fatura.total_amount = self._parse_brl_amount(match.group(1))
        
        match = self.PREVIOUS_BALANCE_PATTERN.search(text)
        if match:
            fatura.previous_balance = self._parse_brl_amount(match.group(1))
        
        match = self.PAYMENT_PATTERN.search(text)
        if match:
            fatura.payment_date = self._parse_full_date(match.group(1))
            fatura.payment_made = self._parse_brl_amount(match.group(2))
        
        match = self.CURRENT_CHARGES_PATTERN.search(text)
        if match:
            fatura.current_charges = self._parse_brl_amount(match.group(1))
        
        match = self.DUE_DATE_PATTERN.search(text)
        if match:
            fatura.due_date = self._parse_full_date(match.group(1))
        
        match = self.STATEMENT_DATE_PATTERN.search(text)
        if match:
            fatura.statement_date = self._parse_full_date(match.group(1))

    def _parse_page_columns(self, page, fatura: Fatura, state: Dict[str, Any]) -> None:
        """Parse a page by cropping into left and right columns.
        
        Args:
            page: The PDF page to parse
            fatura: The fatura object to populate
            state: Mutable dict tracking current_card, in_future_section, in_intl_section
        """
        full_text = page.extract_text(**self.TEXT_EXTRACTION_SETTINGS) or ""
        
        # Skip pages without transaction content (check with spaces)
        if "Lançamentos" not in full_text or "compras e saques" not in full_text:
            return
        
        statement_year = fatura.statement_date.year if fatura.statement_date else 2025
        
        # Crop and parse left column
        try:
            left = page.crop((self.LEFT_COLUMN_START, 0, self.LEFT_COLUMN_END, page.height))
            left_text = left.extract_text(**self.TEXT_EXTRACTION_SETTINGS) or ""
            self._parse_column_text(left_text, fatura, statement_year, state)
        except Exception:
            pass
        
        # Crop and parse right column
        try:
            right = page.crop((self.RIGHT_COLUMN_START, 0, page.width, page.height))
            right_text = right.extract_text(**self.TEXT_EXTRACTION_SETTINGS) or ""
            self._parse_column_text(right_text, fatura, statement_year, state)
        except Exception:
            pass

    def _parse_column_text(self, text: str, fatura: Fatura, year: int, state: Dict[str, Any]) -> None:
        """Parse transactions from a single column's text.
        
        Args:
            text: The extracted text from the column
            fatura: The fatura object to populate  
            year: The year for parsing dates
            state: Mutable dict tracking:
                - current_card: Last seen card number (persists across pages/columns)
                - in_future_section: Whether we're in "próximas faturas"
                - in_intl_section: Whether we're in international section
        """
        lines = text.split("\n")
        
        i = 0
        while i < len(lines):
            line = lines[i].strip()
            
            if not line:
                i += 1
                continue
            
            # Check for future installments section (skip these)
            if "próximas faturas" in line.lower() or "Compras parceladas" in line:
                state["in_future_section"] = True
                i += 1
                continue
            
            # Check for international section (handled separately by _parse_international_from_text)
            if "Lançamentos internacionais" in line:
                state["in_intl_section"] = True
                i += 1
                continue
            
            # New card header resets future section but NOT intl section
            if "RAFAEL" in line.upper() and "final" in line.lower():
                card_match = self.CARD_FINAL_PATTERN.search(line)
                if card_match:
                    state["current_card"] = card_match.group(1)
                    state["in_future_section"] = False
                    # Don't reset in_intl_section - international has no card header per-section
                i += 1
                continue
            
            # "Lançamentos : compras e saques" header resets international section (back to regular)
            if "Lançamentos" in line and "compras" in line and "saques" in line:
                state["in_intl_section"] = False
                i += 1
                continue
            
            # Skip if we're in a section we don't want to parse here
            if state.get("in_future_section") or state.get("in_intl_section"):
                i += 1
                continue
            
            # Skip headers and metadata
            if any(skip in line for skip in [
                "DATA", "ESTABELECIMENTO", "VALOR EM R$", "VALOR EM R $",
                "Continua", "Previsão", "Consulte", 
                "30033030", "08007203030", "PC-",
                "Caso", "pagamento", "parcelamento",
                "crédito", "rotativo", "Demais faturas",
                "Próxima fatura", "Total para próximas"
            ]):
                i += 1
                continue
            
            # Skip subtotal lines but extract for verification
            if "Lançamentos no cartão" in line:
                i += 1
                continue
            
            # Skip total lines
            if line.startswith("Total") or "LTotal" in line:
                i += 1
                continue
            
            # Try to parse as transaction
            date_match = self.DATE_PATTERN.match(line)
            if not date_match:
                i += 1
                continue
            
            date_str = date_match.group(1)
            rest = line[date_match.end():].strip()
            
            # Check for installment pattern (e.g., "AUTOJAPAN 08/10 342,61")
            installment_match = self.INSTALLMENT_PATTERN.search(rest)
            if installment_match:
                current_inst = int(installment_match.group(1))
                total_inst = int(installment_match.group(2))
                amount_str = installment_match.group(3)
                description = rest[:installment_match.start()].strip()
                
                try:
                    tx_date = self._parse_date(date_str, year)
                    tx = Transaction(
                        date=tx_date,
                        description=description,
                        amount_brl=self._parse_brl_amount(amount_str),
                        card_last_digits=state.get("current_card"),
                        transaction_type=TransactionType.PARCELADA,
                        installment=Installment(current=current_inst, total=total_inst),
                    )
                    
                    # Look for category on next line
                    if i + 1 < len(lines):
                        next_line = lines[i + 1].strip()
                        cat_match = self.CATEGORY_LOCATION_PATTERN.match(next_line)
                        if cat_match:
                            tx = Transaction(
                                date=tx.date,
                                description=tx.description,
                                amount_brl=tx.amount_brl,
                                category=cat_match.group(1).strip(),
                                location=cat_match.group(2).strip().upper(),
                                card_last_digits=tx.card_last_digits,
                                transaction_type=tx.transaction_type,
                                installment=tx.installment,
                            )
                            i += 1
                    
                    fatura.transactions.append(tx)
                except (ValueError, IndexError):
                    pass
                
                i += 1
                continue
            
            # Regular transaction
            amount_match = self.AMOUNT_PATTERN.search(rest)
            if amount_match:
                amount_str = amount_match.group(1)
                description = rest[:amount_match.start()].strip()
                
                # Skip if description is empty or too short
                if not description or len(description) < 2:
                    i += 1
                    continue
                
                try:
                    tx_date = self._parse_date(date_str, year)
                    tx = Transaction(
                        date=tx_date,
                        description=description,
                        amount_brl=self._parse_brl_amount(amount_str),
                        card_last_digits=state.get("current_card"),
                        transaction_type=TransactionType.A_VISTA,
                    )
                    
                    # Look for category on next line
                    if i + 1 < len(lines):
                        next_line = lines[i + 1].strip()
                        cat_match = self.CATEGORY_LOCATION_PATTERN.match(next_line)
                        if cat_match:
                            tx = Transaction(
                                date=tx.date,
                                description=tx.description,
                                amount_brl=tx.amount_brl,
                                category=cat_match.group(1).strip(),
                                location=cat_match.group(2).strip().upper(),
                                card_last_digits=tx.card_last_digits,
                                transaction_type=tx.transaction_type,
                            )
                            i += 1
                    
                    fatura.transactions.append(tx)
                except (ValueError, IndexError):
                    pass
            
            i += 1

    def _parse_international_from_text(self, pdf, fatura: Fatura) -> None:
        """Parse international transactions from cropped columns on pages with international section."""
        statement_year = fatura.statement_date.year if fatura.statement_date else 2025
        
        for page in pdf.pages:
            full_text = page.extract_text(**self.TEXT_EXTRACTION_SETTINGS) or ""
            
            # Only process pages that have international section
            if "Lançamentos internacionais" not in full_text:
                continue
            
            # Parse both columns separately for international transactions
            for column_start, column_end in [
                (self.LEFT_COLUMN_START, self.LEFT_COLUMN_END),
                (self.RIGHT_COLUMN_START, page.width)
            ]:
                try:
                    col = page.crop((column_start, 0, column_end, page.height))
                    col_text = col.extract_text(**self.TEXT_EXTRACTION_SETTINGS) or ""
                except Exception:
                    continue
                
                # Skip if this column doesn't have international section
                if "Lançamentos internacionais" not in col_text:
                    continue
                
                lines = col_text.split("\n")
                current_card: Optional[str] = None
                in_intl_section = False
                pending: Optional[Dict[str, Any]] = None
                
                for i, line in enumerate(lines):
                    # Detect international section start
                    if "Lançamentos internacionais" in line:
                        in_intl_section = True
                        # Check for card info
                        card_match = self.CARD_FINAL_PATTERN.search(line)
                        if card_match:
                            current_card = card_match.group(1)
                        continue
                    
                    if not in_intl_section:
                        continue
                    
                    # End of international section
                    if "Total transa" in line and "inter" in line:
                        if pending:
                            self._finalize_intl_transaction(pending, fatura)
                            pending = None
                        # Don't set in_intl_section = False yet - IOF line comes next
                        continue
                    
                    # Parse IOF line (comes after Total transações inter)
                    if "Repasse" in line and "IOF" in line:
                        iof_match = self.IOF_INTL_PATTERN.search(line)
                        if iof_match:
                            fatura.iof_international = self._parse_brl_amount(iof_match.group(1))
                        continue
                    
                    # End after total with IOF
                    if "Total lan" in line and "inter" in line:
                        in_intl_section = False
                        continue
                    
                    if "Total dos lan" in line:
                        if pending:
                            self._finalize_intl_transaction(pending, fatura)
                            pending = None
                        in_intl_section = False
                        continue
                    
                    # Card header within international section
                    if "RAFAEL" in line.upper() and "final" in line.lower():
                        card_match = self.CARD_FINAL_PATTERN.search(line)
                        if card_match:
                            current_card = card_match.group(1)
                        continue
                    
                    # Exchange rate line (completes previous transaction)
                    if "Dólar" in line and "Conversão" in line:
                        if pending:
                            rate_match = self.EXCHANGE_RATE_PATTERN.search(line)
                            if rate_match:
                                pending["exchange_rate"] = self._parse_brl_amount(rate_match.group(1))
                            self._finalize_intl_transaction(pending, fatura)
                            pending = None
                        continue
                    
                    # Parse transaction start line (DATE MERCHANT AMOUNT)
                    date_match = self.DATE_PATTERN.match(line)
                    if date_match:
                        # Finalize any pending transaction
                        if pending:
                            self._finalize_intl_transaction(pending, fatura)
                        
                        date_str = date_match.group(1)
                        rest = line[date_match.end():].strip()
                        amount_match = self.AMOUNT_PATTERN.search(rest)
                        
                        if amount_match:
                            try:
                                tx_date = self._parse_date(date_str, statement_year)
                                pending = {
                                    "date": tx_date,
                                    "description": rest[:amount_match.start()].strip(),
                                    "amount_brl": self._parse_brl_amount(amount_match.group(1)),
                                    "card": current_card,
                                }
                            except (ValueError, IndexError):
                                pending = None
                        continue
                    
                    # Parse city/currency details line
                    intl_match = self.INTL_DETAILS_PATTERN.search(line)
                    if intl_match and pending:
                        pending["city"] = intl_match.group(1)
                        pending["orig_amount"] = self._parse_brl_amount(intl_match.group(2))
                        pending["currency"] = intl_match.group(3)

    def _finalize_intl_transaction(self, data: Dict[str, Any], fatura: Fatura) -> None:
        """Create an international transaction from accumulated data."""
        intl_info = None
        if "orig_amount" in data and "currency" in data:
            intl_info = InternationalInfo(
                original_amount=data.get("orig_amount", Decimal("0")),
                original_currency=data.get("currency", "USD"),
                exchange_rate=data.get("exchange_rate", Decimal("0")),
                city=data.get("city"),
            )
        
        transaction = Transaction(
            date=data["date"],
            description=data["description"],
            amount_brl=data["amount_brl"],
            # International transactions are tracked separately, not by card
            card_last_digits=None,
            transaction_type=TransactionType.A_VISTA,
            international=intl_info,
            payment_method=PaymentMethod.ONLINE,
        )
        fatura.transactions.append(transaction)

    def export_json(self, fatura: Fatura, output_path: Path) -> None:
        """Export the parsed fatura to a JSON file."""
        with output_path.open("w", encoding="utf-8") as f:
            json.dump(fatura.to_dict(), f, ensure_ascii=False, indent=2)
