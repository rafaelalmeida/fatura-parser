# Fatura Parser

CLI tool to parse Brazilian credit card faturas (CSV/PDF) into structured formats, with YNAB export support.

## Installation

```bash
# From source
pip install -e .

# Or run directly
python -m fatura_parser.cli
```

## Usage

```bash
# Parse a CSV fatura to standard format
fatura-parser fatura.csv -o output.csv

# Parse to YNAB-compatible format
fatura-parser fatura.csv --format ynab -o transactions.csv

# Auto-detect format from PDF
fatura-parser fatura.pdf --format ynab

# Verbose output
fatura-parser fatura.csv -v
```

## Options

- `-o, --output`: Output file path
- `-f, --format`: Output format (`csv` or `ynab`)
- `-t, --type`: Input file type (`csv` or `pdf`), auto-detected by default
- `-v, --verbose`: Enable verbose output

## Development

```bash
# Install with dev dependencies
pip install -e ".[dev]"

# Run tests
pytest
```
