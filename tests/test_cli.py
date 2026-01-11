"""Tests for CLI functionality."""

import pytest
from pathlib import Path
from unittest.mock import Mock, patch

from fatura_parser.cli import (
    create_parser,
    detect_file_format,
    run,
)
from fatura_parser.core import FileFormat


class TestArgumentParser:
    """Tests for argument parser."""

    def test_parser_creation(self):
        parser = create_parser()
        assert parser.prog == "fatura-parser"

    def test_required_input_argument(self):
        parser = create_parser()
        with pytest.raises(SystemExit):
            parser.parse_args([])

    def test_input_argument(self):
        parser = create_parser()
        args = parser.parse_args(["test.csv"])
        assert args.input == Path("test.csv")
        assert args.format == "json"
        assert args.output is None

    def test_output_argument(self):
        parser = create_parser()
        args = parser.parse_args(["test.csv", "-o", "output.csv"])
        assert args.output == Path("output.csv")

    def test_format_argument(self):
        parser = create_parser()
        args = parser.parse_args(["test.csv", "--format", "ynab"])
        assert args.format == "ynab"

    def test_type_argument(self):
        parser = create_parser()
        args = parser.parse_args(["test.pdf", "--type", "pdf"])
        assert args.type == "pdf"

    def test_verbose_flag(self):
        parser = create_parser()
        args = parser.parse_args(["test.csv", "-v"])
        assert args.verbose is True


class TestFileFormatDetection:
    """Tests for file format detection."""

    def test_detect_csv(self):
        assert detect_file_format(Path("file.csv")) == FileFormat.CSV

    def test_detect_pdf(self):
        assert detect_file_format(Path("file.pdf")) == FileFormat.PDF

    def test_detect_uppercase_extension(self):
        assert detect_file_format(Path("file.CSV")) == FileFormat.CSV

    def test_detect_unsupported_format(self):
        with pytest.raises(ValueError, match="Unsupported file extension"):
            detect_file_format(Path("file.txt"))


class TestRun:
    """Tests for main run function."""

    @pytest.fixture
    def mock_args(self, tmp_path: Path):
        """Create mock arguments."""
        args = Mock()
        args.input = tmp_path / "test.csv"
        args.output = tmp_path / "output.csv"
        args.format = "csv"
        args.type = None
        args.verbose = False
        return args

    def test_run_file_not_found(self, mock_args):
        exit_code = run(mock_args)
        assert exit_code == 1

    def test_run_unsupported_format(self, mock_args, tmp_path: Path):
        mock_args.input = tmp_path / "test.txt"
        mock_args.input.write_text("test")
        exit_code = run(mock_args)
        assert exit_code == 1

    @patch("fatura_parser.cli.get_parser")
    @patch("fatura_parser.cli.get_exporter")
    def test_run_not_implemented(self, mock_get_exporter, mock_get_parser, mock_args, tmp_path: Path):
        # Create the input file
        mock_args.input.write_text("test")
        
        # Mock parser to raise NotImplementedError
        mock_parser = Mock()
        mock_parser.parse.side_effect = NotImplementedError("Not implemented")
        mock_get_parser.return_value = mock_parser
        
        exit_code = run(mock_args)
        assert exit_code == 1

    def test_run_with_explicit_type(self, mock_args, tmp_path: Path):
        mock_args.input.write_text("test")
        mock_args.type = "csv"
        exit_code = run(mock_args)
        assert exit_code == 1  # Will fail with NotImplementedError
