"""Tests for PDF file attachments."""

import pytest

import makepdf


class TestAddAttachment:
    def test_add_attachment(self, sample_pdf, tmp_dir):
        # Create a file to attach
        attach_file = tmp_dir / "data.txt"
        attach_file.write_text("This is attached data")

        out = tmp_dir / "with_attachment.pdf"
        result = makepdf.add_attachment(
            str(sample_pdf), str(attach_file), str(out), description="Test data"
        )
        assert result.exists()


class TestListAttachments:
    def test_list_on_pdf_without_attachments(self, sample_pdf):
        result = makepdf.list_attachments(str(sample_pdf))
        assert isinstance(result, list)
        assert len(result) == 0

    def test_list_after_adding(self, sample_pdf, tmp_dir):
        attach_file = tmp_dir / "notes.txt"
        attach_file.write_text("Some notes")

        out = tmp_dir / "with_attachment.pdf"
        makepdf.add_attachment(str(sample_pdf), str(attach_file), str(out))

        result = makepdf.list_attachments(str(out))
        assert isinstance(result, list)
        assert len(result) >= 1


class TestExtractAttachments:
    def test_extract_from_pdf_with_attachment(self, sample_pdf, tmp_dir):
        attach_file = tmp_dir / "data.csv"
        attach_file.write_text("a,b,c\n1,2,3")

        with_att = tmp_dir / "attached.pdf"
        makepdf.add_attachment(str(sample_pdf), str(attach_file), str(with_att))

        extract_dir = tmp_dir / "extracted"
        extract_dir.mkdir()
        results = makepdf.extract_attachments(str(with_att), str(extract_dir))
        assert isinstance(results, list)


class TestRemoveAttachments:
    def test_remove_attachments(self, sample_pdf, tmp_dir):
        out = tmp_dir / "cleaned.pdf"
        result = makepdf.remove_attachments(str(sample_pdf), str(out))
        assert result.exists()
