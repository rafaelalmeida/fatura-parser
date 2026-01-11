"""Test fixtures and configuration for pytest."""

import pytest
from pathlib import Path


@pytest.fixture
def fixtures_dir() -> Path:
    """Return path to test fixtures directory."""
    return Path(__file__).parent / "fixtures"


@pytest.fixture
def sample_csv_path(fixtures_dir: Path) -> Path:
    """Return path to sample CSV fatura file."""
    return fixtures_dir / "sample_fatura.csv"


@pytest.fixture
def sample_pdf_path(fixtures_dir: Path) -> Path:
    """Return path to sample PDF fatura file."""
    return fixtures_dir / "sample_fatura.pdf"


@pytest.fixture
def output_dir(tmp_path: Path) -> Path:
    """Return a temporary directory for test outputs."""
    return tmp_path
