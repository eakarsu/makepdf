"""Tests for the CLI interface."""

from typer.testing import CliRunner

from makepdf.cli.app import app

runner = CliRunner()


class TestCLI:
    def test_help(self):
        result = runner.invoke(app, ["--help"])
        assert result.exit_code == 0
        assert "makepdf" in result.output.lower() or "PDF" in result.output

    def test_create_text(self, tmp_path):
        # CLI create text takes a file path, not inline text
        txt_file = tmp_path / "input.txt"
        txt_file.write_text("Hello CLI Test")
        out = tmp_path / "test.pdf"
        result = runner.invoke(app, ["create", "text", str(txt_file), "-o", str(out)])
        assert result.exit_code == 0

    def test_create_help(self):
        result = runner.invoke(app, ["create", "--help"])
        assert result.exit_code == 0
