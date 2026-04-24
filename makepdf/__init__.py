"""MakePDF - Complete PDF generation and manipulation toolkit."""

__version__ = "0.1.0"

# --- Original modules ---
from makepdf.core.creator import from_text, from_html, from_markdown, from_images
from makepdf.core.merger import merge, split, extract_pages, rotate_pages, reverse, delete_pages, interleave, reorder_pages
from makepdf.core.text_extractor import extract_text, extract_text_by_page, search_text
from makepdf.core.image_extractor import extract_images, count_images
from makepdf.core.editor import add_text, add_image, add_shape, add_annotation
from makepdf.core.watermark import add_text_watermark, add_image_watermark
from makepdf.core.encryption import encrypt, decrypt, is_encrypted
from makepdf.core.compressor import compress, get_pdf_info
from makepdf.core.forms import create_form, fill_form, extract_form_data, list_form_fields
from makepdf.core.headers_footers import add_headers_footers
from makepdf.core.toc import generate_toc, extract_toc, add_bookmarks
from makepdf.core.converter import pdf_to_images, images_to_pdf, pdf_to_text
from makepdf.core.signer import sign, create_self_signed_cert, verify
from makepdf.core.ocr import ocr_pdf, ocr_to_text

# --- New Acrobat-style modules ---
from makepdf.core.redaction import redact_area, redact_text, search_and_redact
from makepdf.core.cropper import crop_pages, resize_pages, trim_margins, set_page_boxes
from makepdf.core.stamps import add_stamp, add_custom_stamp, add_image_stamp
from makepdf.core.bates import add_bates_numbers, add_bates_to_batch
from makepdf.core.compare import compare_text, compare_metadata, compare_structure, generate_diff_report
from makepdf.core.flatten import flatten_forms, flatten_annotations, flatten_all
from makepdf.core.metadata import get_metadata, set_metadata, remove_metadata
from makepdf.core.attachments import add_attachment, extract_attachments, list_attachments, remove_attachments
from makepdf.core.links import add_link, add_internal_link, extract_links
from makepdf.core.page_labels import set_page_labels, get_page_labels
from makepdf.core.optimizer import optimize, remove_unused_objects, linearize, get_optimization_report
from makepdf.core.accessibility import set_language, get_language, set_title_display, check_accessibility
from makepdf.core.markup import highlight_area, underline_area, strikethrough_area, add_sticky_note, add_text_comment

__all__ = [
    # Creator
    "from_text", "from_html", "from_markdown", "from_images",
    # Merger
    "merge", "split", "extract_pages", "rotate_pages", "reverse", "delete_pages", "interleave", "reorder_pages",
    # Text extraction
    "extract_text", "extract_text_by_page", "search_text",
    # Image extraction
    "extract_images", "count_images",
    # Editor
    "add_text", "add_image", "add_shape", "add_annotation",
    # Watermark
    "add_text_watermark", "add_image_watermark",
    # Encryption
    "encrypt", "decrypt", "is_encrypted",
    # Compression
    "compress", "get_pdf_info",
    # Forms
    "create_form", "fill_form", "extract_form_data", "list_form_fields",
    # Headers & Footers
    "add_headers_footers",
    # TOC
    "generate_toc", "extract_toc", "add_bookmarks",
    # Converter
    "pdf_to_images", "images_to_pdf", "pdf_to_text",
    # Signer
    "sign", "create_self_signed_cert", "verify",
    # OCR
    "ocr_pdf", "ocr_to_text",
    # Redaction
    "redact_area", "redact_text", "search_and_redact",
    # Cropper
    "crop_pages", "resize_pages", "trim_margins", "set_page_boxes",
    # Stamps
    "add_stamp", "add_custom_stamp", "add_image_stamp",
    # Bates numbering
    "add_bates_numbers", "add_bates_to_batch",
    # Compare
    "compare_text", "compare_metadata", "compare_structure", "generate_diff_report",
    # Flatten
    "flatten_forms", "flatten_annotations", "flatten_all",
    # Metadata
    "get_metadata", "set_metadata", "remove_metadata",
    # Attachments
    "add_attachment", "extract_attachments", "list_attachments", "remove_attachments",
    # Links
    "add_link", "add_internal_link", "extract_links",
    # Page labels
    "set_page_labels", "get_page_labels",
    # Optimizer
    "optimize", "remove_unused_objects", "linearize", "get_optimization_report",
    # Accessibility
    "set_language", "get_language", "set_title_display", "check_accessibility",
    # Markup annotations
    "highlight_area", "underline_area", "strikethrough_area", "add_sticky_note", "add_text_comment",
]
