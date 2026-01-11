# Fatura Parser

CLI tool to parse Brazilian credit card faturas (CSV/PDF) into structured formats, with YNAB export support.

## Installation

```bash
# From source
pip install -e .

# Or with pipx in editable mode (recommended for CLI tools)
pipx install -e .

# Or run directly without installing
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

# Parse password-protected PDF
fatura-parser fatura.pdf -p ~/.fatura-password

# Verbose output
fatura-parser fatura.csv -v
```

## Options

- `-o, --output`: Output file path
- `-f, --format`: Output format (`csv`, `json`, or `ynab`)
- `-t, --type`: Input file type (`csv` or `pdf`), auto-detected by default
- `-p, --password-file`: Path to file containing PDF password (for encrypted PDFs)
- `-v, --verbose`: Enable verbose output
- `--batch DIR`: Run interactive batch mode on all PDFs in DIR

## Interactive Batch Mode

Process multiple PDF faturas interactively with checksum verification:

```bash
# Export all PDFs in a directory to YNAB format
fatura-parser --batch /path/to/faturas --format ynab

# Batch export to JSON with password
fatura-parser --batch /path/to/faturas --format json -p ~/.fatura-password
```

Batch mode features:
- Recursively finds all PDF files in the directory
- Shows checksum verification for each file
- Prompts to accept or reject each export
- Handles existing files (skip, replace, or view)
- Creates a timestamped log file with all actions
- Colored terminal output for better visibility

## Development

```bash
# Install with dev dependencies
pip install -e ".[dev]"

# Run tests
pytest
```
