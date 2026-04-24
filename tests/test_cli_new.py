"""Tests for new CLI sub-commands."""

from typer.testing import CliRunner

from makepdf.cli.app import app

runner = CliRunner()


class TestNewSubcommands:
    def test_redact_help(self):
        result = runner.invoke(app, ["redact", "--help"])
        assert result.exit_code == 0

    def test_crop_help(self):
        result = runner.invoke(app, ["crop", "--help"])
        assert result.exit_code == 0

    def test_stamp_help(self):
        result = runner.invoke(app, ["stamp", "--help"])
        assert result.exit_code == 0

    def test_bates_help(self):
        result = runner.invoke(app, ["bates", "--help"])
        assert result.exit_code == 0

    def test_compare_help(self):
        result = runner.invoke(app, ["compare", "--help"])
        assert result.exit_code == 0

    def test_flatten_help(self):
        result = runner.invoke(app, ["flatten", "--help"])
        assert result.exit_code == 0

    def test_metadata_help(self):
        result = runner.invoke(app, ["metadata", "--help"])
        assert result.exit_code == 0

    def test_attach_help(self):
        result = runner.invoke(app, ["attach", "--help"])
        assert result.exit_code == 0

    def test_link_help(self):
        result = runner.invoke(app, ["link", "--help"])
        assert result.exit_code == 0

    def test_label_help(self):
        result = runner.invoke(app, ["label", "--help"])
        assert result.exit_code == 0

    def test_optimize_help(self):
        result = runner.invoke(app, ["optimize", "--help"])
        assert result.exit_code == 0

    def test_a11y_help(self):
        result = runner.invoke(app, ["a11y", "--help"])
        assert result.exit_code == 0

    def test_markup_help(self):
        result = runner.invoke(app, ["markup", "--help"])
        assert result.exit_code == 0


class TestNewCLICommands:
    def test_metadata_get(self, tmp_path):
        import makepdf
        pdf = tmp_path / "test.pdf"
        makepdf.from_text("Hello", str(pdf))
        result = runner.invoke(app, ["metadata", "get", str(pdf)])
        assert result.exit_code == 0

    def test_flatten_all(self, tmp_path):
        import makepdf
        pdf = tmp_path / "test.pdf"
        makepdf.from_text("Hello", str(pdf))
        out = tmp_path / "flat.pdf"
        result = runner.invoke(app, ["flatten", "all", str(pdf), "-o", str(out)])
        assert result.exit_code == 0

    def test_optimize_report(self, tmp_path):
        import makepdf
        pdf = tmp_path / "test.pdf"
        makepdf.from_text("Hello", str(pdf))
        result = runner.invoke(app, ["optimize", "report", str(pdf)])
        assert result.exit_code == 0

    def test_a11y_check(self, tmp_path):
        import makepdf
        pdf = tmp_path / "test.pdf"
        makepdf.from_text("Hello", str(pdf))
        result = runner.invoke(app, ["a11y", "check", str(pdf)])
        assert result.exit_code == 0

    def test_stamp_add(self, tmp_path):
        import makepdf
        pdf = tmp_path / "test.pdf"
        makepdf.from_text("Hello", str(pdf))
        out = tmp_path / "stamped.pdf"
        result = runner.invoke(app, ["stamp", "add", str(pdf), "DRAFT", "-o", str(out)])
        assert result.exit_code == 0

    def test_bates_add(self, tmp_path):
        import makepdf
        pdf = tmp_path / "test.pdf"
        makepdf.from_text("Hello", str(pdf))
        out = tmp_path / "bates.pdf"
        result = runner.invoke(app, ["bates", "add", str(pdf), "-o", str(out)])
        assert result.exit_code == 0
