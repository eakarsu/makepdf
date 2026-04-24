"""macOS MakePDF app — native PDF viewer/editor using Cocoa + PDFKit.

Menu structure mirrors Adobe Acrobat Reader/Pro tools.
"""

import os
import subprocess
import sys
import tempfile
import threading
from pathlib import Path

import objc
from AppKit import (
    NSApplication,
    NSApp,
    NSApplicationActivationPolicyRegular,
    NSWindow,
    NSBackingStoreBuffered,
    NSMakeRect,
    NSOpenPanel,
    NSSavePanel,
    NSAlert,
    NSAlertStyleInformational,
    NSFont,
    NSColor,
    NSScreen,
    NSMenu,
    NSMenuItem,
    NSWindowStyleMaskTitled,
    NSWindowStyleMaskClosable,
    NSWindowStyleMaskMiniaturizable,
    NSWindowStyleMaskResizable,
    NSTextField,
    NSTextAlignmentCenter,
    NSScrollView,
    NSTextView,
)
from Foundation import NSURL

objc.loadBundle(
    "PDFKit",
    bundle_path="/System/Library/Frameworks/Quartz.framework",
    module_globals=globals(),
)
from Quartz import PDFDocument, PDFView


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def pick_pdf(title="Select PDF", multiple=False):
    panel = NSOpenPanel.openPanel()
    panel.setTitle_(title)
    panel.setAllowedFileTypes_(["pdf"])
    panel.setAllowsMultipleSelection_(multiple)
    if panel.runModal():
        if multiple:
            return [str(u.path()) for u in panel.URLs()]
        return str(panel.URL().path())
    return None


def pick_file(title="Select File", file_types=None):
    panel = NSOpenPanel.openPanel()
    panel.setTitle_(title)
    if file_types:
        panel.setAllowedFileTypes_(file_types)
    if panel.runModal():
        return str(panel.URL().path())
    return None


def pick_files(title="Select Files", file_types=None):
    panel = NSOpenPanel.openPanel()
    panel.setTitle_(title)
    panel.setAllowsMultipleSelection_(True)
    if file_types:
        panel.setAllowedFileTypes_(file_types)
    if panel.runModal():
        return [str(u.path()) for u in panel.URLs()]
    return None


def save_pdf_dialog(title="Save PDF", default_name=None):
    panel = NSSavePanel.savePanel()
    panel.setTitle_(title)
    panel.setAllowedFileTypes_(["pdf"])
    if default_name:
        panel.setNameFieldStringValue_(default_name)
    if panel.runModal():
        return str(panel.URL().path())
    return None


def save_file_dialog(title="Save File", file_types=None, default_name=None):
    panel = NSSavePanel.savePanel()
    panel.setTitle_(title)
    if file_types:
        panel.setAllowedFileTypes_(file_types)
    if default_name:
        panel.setNameFieldStringValue_(default_name)
    if panel.runModal():
        return str(panel.URL().path())
    return None


def show_alert(title, message):
    alert = NSAlert.alloc().init()
    alert.setAlertStyle_(NSAlertStyleInformational)
    alert.setMessageText_(title)
    alert.setInformativeText_(str(message))
    alert.runModal()


def get_current_pdf_path():
    """Get the file path of the PDF in the current active window."""
    win = NSApp.keyWindow()
    if not win:
        return None
    title = str(win.title())
    if title.startswith("MakePDF - "):
        return title[len("MakePDF - "):]
    return None


def get_current_pdf_view():
    """Get the PDFView from the current active window."""
    win = NSApp.keyWindow()
    if not win:
        return None
    cv = win.contentView()
    if isinstance(cv, PDFView):
        return cv
    return None


def get_current_doc_path():
    """Get the full file path from the current PDF document."""
    pv = get_current_pdf_view()
    if pv:
        doc = pv.document()
        if doc:
            url = doc.documentURL()
            if url:
                return str(url.path())
    return None


def reload_pdf_in_window(path):
    """Reload a PDF into the current window after modification."""
    win = NSApp.keyWindow()
    if not win:
        show_pdf(path)
        return
    url = NSURL.fileURLWithPath_(str(path))
    doc = PDFDocument.alloc().initWithURL_(url)
    if doc:
        cv = win.contentView()
        if isinstance(cv, PDFView):
            cv.setDocument_(doc)
            win.setTitle_(f"MakePDF - {os.path.basename(path)}")
            return
    show_pdf(path)


def require_open_pdf():
    """Get current PDF path or prompt user to open one. Returns path or None."""
    path = get_current_doc_path()
    if path:
        return path
    path = pick_pdf("Select a PDF first")
    if path:
        show_pdf(path)
    return path


def show_text_window(title, text):
    """Show text in a new scrollable window."""
    w, h = 700, 500
    win = NSWindow.alloc().initWithContentRect_styleMask_backing_defer_(
        NSMakeRect(200, 200, w, h),
        NSWindowStyleMaskTitled | NSWindowStyleMaskClosable
        | NSWindowStyleMaskMiniaturizable | NSWindowStyleMaskResizable,
        NSBackingStoreBuffered, False,
    )
    win.setTitle_(title)
    scroll = NSScrollView.alloc().initWithFrame_(NSMakeRect(0, 0, w, h))
    scroll.setHasVerticalScroller_(True)
    scroll.setAutoresizingMask_(0x12)
    tv = NSTextView.alloc().initWithFrame_(NSMakeRect(0, 0, w, h))
    tv.setEditable_(False)
    tv.setFont_(NSFont.fontWithName_size_("Menlo", 12))
    tv.setString_(text)
    scroll.setDocumentView_(tv)
    win.setContentView_(scroll)
    win.center()
    win.makeKeyAndOrderFront_(None)
    if not hasattr(NSApp, "_extra_windows"):
        NSApp._extra_windows = []
    NSApp._extra_windows.append(win)


# ---------------------------------------------------------------------------
# PDF Viewer
# ---------------------------------------------------------------------------

def show_pdf(path):
    url = NSURL.fileURLWithPath_(str(path))
    doc = PDFDocument.alloc().initWithURL_(url)
    if doc is None:
        show_alert("Error", f"Could not open: {os.path.basename(path)}")
        return

    screen = NSScreen.mainScreen().frame()
    w = min(int(screen.size.width * 0.75), 1200)
    h = min(int(screen.size.height * 0.85), 950)

    win = NSWindow.alloc().initWithContentRect_styleMask_backing_defer_(
        NSMakeRect(100, 50, w, h),
        NSWindowStyleMaskTitled | NSWindowStyleMaskClosable
        | NSWindowStyleMaskMiniaturizable | NSWindowStyleMaskResizable,
        NSBackingStoreBuffered, False,
    )
    win.setTitle_(f"MakePDF - {os.path.basename(path)}")

    pdf_view = PDFView.alloc().initWithFrame_(NSMakeRect(0, 0, w, h))
    pdf_view.setDocument_(doc)
    pdf_view.setAutoScales_(True)
    pdf_view.setDisplayMode_(1)
    pdf_view.setDisplaysPageBreaks_(True)
    pdf_view.setAutoresizingMask_(0x12)

    win.setContentView_(pdf_view)
    win.center()
    win.makeKeyAndOrderFront_(None)

    if not hasattr(NSApp, "_pdf_windows"):
        NSApp._pdf_windows = []
    NSApp._pdf_windows.append(win)


# ---------------------------------------------------------------------------
# AppDelegate with full Acrobat-style menus
# ---------------------------------------------------------------------------

class AppDelegate(objc.lookUpClass("NSObject")):

    # -- Lifecycle ----------------------------------------------------------

    def applicationDidFinishLaunching_(self, notification):
        self._setup_menu_bar()

    def applicationShouldHandleReopen_hasVisibleWindows_(self, app, has_visible):
        if not has_visible:
            self.onOpen_(None)
        return True

    def application_openFile_(self, app, filename):
        if filename and str(filename).lower().endswith(".pdf"):
            show_pdf(filename)
            return True
        return False

    # -- Menu bar -----------------------------------------------------------

    @objc.python_method
    def _menu_item(self, menu, title, action, key=""):
        item = menu.addItemWithTitle_action_keyEquivalent_(title, action, key)
        item.setTarget_(self)
        return item

    @objc.python_method
    def _setup_menu_bar(self):
        menubar = NSMenu.alloc().init()

        # ---- App menu ----
        app_mi = NSMenuItem.alloc().init()
        menubar.addItem_(app_mi)
        app_menu = NSMenu.alloc().init()
        app_menu.addItemWithTitle_action_keyEquivalent_("About MakePDF", b"orderFrontStandardAboutPanel:", "")
        app_menu.addItem_(NSMenuItem.separatorItem())
        app_menu.addItemWithTitle_action_keyEquivalent_("Quit MakePDF", b"terminate:", "q")
        app_mi.setSubmenu_(app_menu)

        # ---- File menu ----
        file_mi = NSMenuItem.alloc().init()
        menubar.addItem_(file_mi)
        fm = NSMenu.alloc().initWithTitle_("File")
        self._menu_item(fm, "Open...", b"onOpen:", "o")
        self._menu_item(fm, "Create PDF from Text...", b"onCreateFromText:", "")
        self._menu_item(fm, "Create PDF from Images...", b"onCreateFromImages:", "")
        fm.addItem_(NSMenuItem.separatorItem())
        self._menu_item(fm, "Export as Text...", b"onExportText:", "")
        self._menu_item(fm, "Export as Images...", b"onExportImages:", "")
        fm.addItem_(NSMenuItem.separatorItem())
        self._menu_item(fm, "Print...", b"onPrint:", "p")
        fm.addItem_(NSMenuItem.separatorItem())
        self._menu_item(fm, "Properties / Metadata...", b"onMetadataView:", "")
        file_mi.setSubmenu_(fm)

        # ---- Edit menu ----
        edit_mi = NSMenuItem.alloc().init()
        menubar.addItem_(edit_mi)
        em = NSMenu.alloc().initWithTitle_("Edit")
        em.addItemWithTitle_action_keyEquivalent_("Copy", b"copy:", "c")
        em.addItemWithTitle_action_keyEquivalent_("Select All", b"selectAll:", "a")
        em.addItem_(NSMenuItem.separatorItem())
        self._menu_item(em, "Find Text...", b"onFindText:", "f")
        edit_mi.setSubmenu_(em)

        # ---- View menu ----
        view_mi = NSMenuItem.alloc().init()
        menubar.addItem_(view_mi)
        vm = NSMenu.alloc().initWithTitle_("View")
        self._menu_item(vm, "Zoom In", b"onZoomIn:", "+")
        self._menu_item(vm, "Zoom Out", b"onZoomOut:", "-")
        self._menu_item(vm, "Zoom to Fit", b"onZoomFit:", "0")
        vm.addItem_(NSMenuItem.separatorItem())
        self._menu_item(vm, "Single Page", b"onViewSingle:", "")
        self._menu_item(vm, "Single Page Continuous", b"onViewContinuous:", "")
        self._menu_item(vm, "Two Pages", b"onViewTwoPage:", "")
        view_mi.setSubmenu_(vm)

        # ---- Pages menu (Organize Pages) ----
        pages_mi = NSMenuItem.alloc().init()
        menubar.addItem_(pages_mi)
        pm = NSMenu.alloc().initWithTitle_("Pages")
        self._menu_item(pm, "Merge / Combine Files...", b"onMerge:", "")
        self._menu_item(pm, "Split PDF...", b"onSplit:", "")
        pm.addItem_(NSMenuItem.separatorItem())
        self._menu_item(pm, "Extract Pages...", b"onExtractPages:", "")
        self._menu_item(pm, "Delete Pages...", b"onDeletePages:", "")
        self._menu_item(pm, "Rotate Pages...", b"onRotatePages:", "")
        self._menu_item(pm, "Reorder Pages...", b"onReorderPages:", "")
        pm.addItem_(NSMenuItem.separatorItem())
        self._menu_item(pm, "Crop Pages...", b"onCropPages:", "")
        self._menu_item(pm, "Resize Pages...", b"onResizePages:", "")
        pages_mi.setSubmenu_(pm)

        # ---- Tools menu (All Acrobat tools) ----
        tools_mi = NSMenuItem.alloc().init()
        menubar.addItem_(tools_mi)
        tm = NSMenu.alloc().initWithTitle_("Tools")

        # -- Edit PDF --
        self._menu_item(tm, "Add Text...", b"onAddText:", "")
        self._menu_item(tm, "Add Image...", b"onAddImage:", "")
        self._menu_item(tm, "Add Watermark...", b"onAddWatermark:", "")
        self._menu_item(tm, "Add Stamp...", b"onAddStamp:", "")
        tm.addItem_(NSMenuItem.separatorItem())

        # -- Protect & Redact --
        self._menu_item(tm, "Encrypt / Password Protect...", b"onEncrypt:", "")
        self._menu_item(tm, "Decrypt / Remove Password...", b"onDecrypt:", "")
        self._menu_item(tm, "Redact Text...", b"onRedactText:", "")
        tm.addItem_(NSMenuItem.separatorItem())

        # -- Comments / Markup --
        self._menu_item(tm, "Add Highlight...", b"onHighlight:", "")
        self._menu_item(tm, "Add Sticky Note...", b"onStickyNote:", "")
        self._menu_item(tm, "Add Comment...", b"onAddComment:", "")
        tm.addItem_(NSMenuItem.separatorItem())

        # -- Forms --
        self._menu_item(tm, "Prepare a Form...", b"onPrepareForm:", "")
        self._menu_item(tm, "Fill Form...", b"onFillForm:", "")
        self._menu_item(tm, "Flatten Forms...", b"onFlattenForms:", "")
        self._menu_item(tm, "Flatten Annotations...", b"onFlattenAnnotations:", "")
        tm.addItem_(NSMenuItem.separatorItem())

        # -- Measure & Compare --
        self._menu_item(tm, "Compare PDFs...", b"onCompare:", "")
        tm.addItem_(NSMenuItem.separatorItem())

        # -- Bates / Legal --
        self._menu_item(tm, "Add Bates Numbers...", b"onBatesNumber:", "")
        tm.addItem_(NSMenuItem.separatorItem())

        # -- Optimize / Compress --
        self._menu_item(tm, "Optimize / Compress PDF...", b"onOptimize:", "")
        self._menu_item(tm, "Optimization Report...", b"onOptimizeReport:", "")
        tm.addItem_(NSMenuItem.separatorItem())

        # -- Scan & OCR --
        self._menu_item(tm, "Scan & OCR...", b"onOCR:", "")
        tm.addItem_(NSMenuItem.separatorItem())

        # -- Accessibility --
        self._menu_item(tm, "Accessibility Check...", b"onA11yCheck:", "")
        self._menu_item(tm, "Set Language...", b"onSetLanguage:", "")
        tm.addItem_(NSMenuItem.separatorItem())

        # -- Attachments --
        self._menu_item(tm, "Add Attachment...", b"onAddAttachment:", "")
        self._menu_item(tm, "List Attachments...", b"onListAttachments:", "")
        self._menu_item(tm, "Extract Attachments...", b"onExtractAttachments:", "")
        tm.addItem_(NSMenuItem.separatorItem())

        # -- Links & Bookmarks --
        self._menu_item(tm, "Extract Links...", b"onExtractLinks:", "")
        self._menu_item(tm, "Table of Contents...", b"onTOC:", "")
        tm.addItem_(NSMenuItem.separatorItem())

        # -- Metadata --
        self._menu_item(tm, "Edit Metadata...", b"onMetadataEdit:", "")
        self._menu_item(tm, "Remove Metadata...", b"onMetadataRemove:", "")
        tm.addItem_(NSMenuItem.separatorItem())

        # -- Signatures --
        self._menu_item(tm, "Fill & Sign...", b"onSign:", "")
        self._menu_item(tm, "Request e-Signatures...", b"onRequestSign:", "")
        tm.addItem_(NSMenuItem.separatorItem())

        # -- Convert --
        self._menu_item(tm, "Convert to PDF...", b"onConvertToPDF:", "")
        tm.addItem_(NSMenuItem.separatorItem())

        # -- Web UI --
        self._menu_item(tm, "Open Web UI (All Features)...", b"onWebUI:", "")

        tools_mi.setSubmenu_(tm)

        # ---- Window menu ----
        window_mi = NSMenuItem.alloc().init()
        menubar.addItem_(window_mi)
        wm = NSMenu.alloc().initWithTitle_("Window")
        wm.addItemWithTitle_action_keyEquivalent_("Minimize", b"performMiniaturize:", "")
        wm.addItemWithTitle_action_keyEquivalent_("Zoom", b"performZoom:", "")
        window_mi.setSubmenu_(wm)

        NSApp.setMainMenu_(menubar)
        NSApp.setWindowsMenu_(wm)

    # ======================================================================
    # File actions
    # ======================================================================

    @objc.typedSelector(b"v@:@")
    def onOpen_(self, sender):
        path = pick_pdf("Open PDF")
        if path:
            show_pdf(path)

    @objc.typedSelector(b"v@:@")
    def onCreateFromText_(self, sender):
        path = pick_file("Select text file", ["txt", "md", "text"])
        if not path:
            return
        out = save_pdf_dialog("Save PDF as", "created.pdf")
        if not out:
            return
        from makepdf.core.creator import from_text
        text = Path(path).read_text(encoding="utf-8")
        from_text(text, Path(out))
        show_pdf(out)

    @objc.typedSelector(b"v@:@")
    def onCreateFromImages_(self, sender):
        paths = pick_files("Select images", ["png", "jpg", "jpeg", "tiff", "bmp", "gif"])
        if not paths:
            return
        out = save_pdf_dialog("Save PDF as", "images.pdf")
        if not out:
            return
        from makepdf.core.creator import from_images
        from_images([Path(p) for p in paths], Path(out))
        show_pdf(out)

    @objc.typedSelector(b"v@:@")
    def onExportText_(self, sender):
        path = require_open_pdf()
        if not path:
            return
        from makepdf.core.text_extractor import extract_text
        text = extract_text(Path(path))
        show_text_window(f"Text - {os.path.basename(path)}", text)

    @objc.typedSelector(b"v@:@")
    def onExportImages_(self, sender):
        path = require_open_pdf()
        if not path:
            return
        out_dir = save_file_dialog("Save images to folder")
        if not out_dir:
            return
        from makepdf.core.image_extractor import extract_images
        result = extract_images(Path(path), Path(out_dir))
        show_alert("Export Images", f"Extracted images to:\n{out_dir}")

    @objc.typedSelector(b"v@:@")
    def onPrint_(self, sender):
        pv = get_current_pdf_view()
        if pv:
            pv.print_(sender)

    @objc.typedSelector(b"v@:@")
    def onMetadataView_(self, sender):
        path = require_open_pdf()
        if not path:
            return
        from makepdf.core.metadata import get_metadata
        meta = get_metadata(Path(path))
        lines = [f"{k}: {v}" for k, v in meta.items()]
        show_text_window(f"Metadata - {os.path.basename(path)}", "\n".join(lines))

    # ======================================================================
    # Edit actions
    # ======================================================================

    @objc.typedSelector(b"v@:@")
    def onFindText_(self, sender):
        pv = get_current_pdf_view()
        if not pv:
            return
        # Use PDFKit built-in search UI — trigger via performFindPanelAction
        NSApp.sendAction_to_from_(b"performFindPanelAction:", None, sender)

    # ======================================================================
    # View actions
    # ======================================================================

    @objc.typedSelector(b"v@:@")
    def onZoomIn_(self, sender):
        pv = get_current_pdf_view()
        if pv:
            pv.zoomIn_(None)

    @objc.typedSelector(b"v@:@")
    def onZoomOut_(self, sender):
        pv = get_current_pdf_view()
        if pv:
            pv.zoomOut_(None)

    @objc.typedSelector(b"v@:@")
    def onZoomFit_(self, sender):
        pv = get_current_pdf_view()
        if pv:
            pv.setAutoScales_(True)

    @objc.typedSelector(b"v@:@")
    def onViewSingle_(self, sender):
        pv = get_current_pdf_view()
        if pv:
            pv.setDisplayMode_(0)  # kPDFDisplaySinglePage

    @objc.typedSelector(b"v@:@")
    def onViewContinuous_(self, sender):
        pv = get_current_pdf_view()
        if pv:
            pv.setDisplayMode_(1)  # kPDFDisplaySinglePageContinuous

    @objc.typedSelector(b"v@:@")
    def onViewTwoPage_(self, sender):
        pv = get_current_pdf_view()
        if pv:
            pv.setDisplayMode_(2)  # kPDFDisplayTwoUp

    # ======================================================================
    # Pages actions
    # ======================================================================

    @objc.typedSelector(b"v@:@")
    def onMerge_(self, sender):
        paths = pick_pdf("Select PDFs to merge", multiple=True)
        if not paths or len(paths) < 2:
            show_alert("Merge", "Please select at least 2 PDF files.")
            return
        out = save_pdf_dialog("Save merged PDF as", "merged.pdf")
        if not out:
            return
        from makepdf.core.merger import merge
        merge([Path(p) for p in paths], Path(out))
        show_pdf(out)

    @objc.typedSelector(b"v@:@")
    def onSplit_(self, sender):
        path = require_open_pdf()
        if not path:
            return
        out = save_pdf_dialog("Save split PDF prefix", "split.pdf")
        if not out:
            return
        from makepdf.core.merger import split
        results = split(Path(path), output_dir=Path(os.path.dirname(out)))
        show_alert("Split", f"Split into {len(results)} files in:\n{os.path.dirname(out)}")

    @objc.typedSelector(b"v@:@")
    def onExtractPages_(self, sender):
        path = require_open_pdf()
        if not path:
            return
        # Simple prompt — extract first page as demo; full UI would need input dialog
        out = save_pdf_dialog("Save extracted pages as", "extracted.pdf")
        if not out:
            return
        from makepdf.core.merger import extract_pages
        extract_pages(Path(path), [0], Path(out))
        show_pdf(out)

    @objc.typedSelector(b"v@:@")
    def onDeletePages_(self, sender):
        path = require_open_pdf()
        if not path:
            return
        out = save_pdf_dialog("Save PDF without deleted pages", "trimmed.pdf")
        if not out:
            return
        from makepdf.core.merger import delete_pages
        delete_pages(Path(path), [0], Path(out))
        show_pdf(out)

    @objc.typedSelector(b"v@:@")
    def onRotatePages_(self, sender):
        path = require_open_pdf()
        if not path:
            return
        out = save_pdf_dialog("Save rotated PDF", "rotated.pdf")
        if not out:
            return
        from makepdf.core.merger import rotate_pages
        rotate_pages(Path(path), None, 90, Path(out))
        show_pdf(out)

    @objc.typedSelector(b"v@:@")
    def onReorderPages_(self, sender):
        path = require_open_pdf()
        if not path:
            return
        out = save_pdf_dialog("Save reordered PDF", "reordered.pdf")
        if not out:
            return
        from makepdf.core.merger import reverse
        reverse(Path(path), Path(out))
        show_pdf(out)

    @objc.typedSelector(b"v@:@")
    def onCropPages_(self, sender):
        path = require_open_pdf()
        if not path:
            return
        out = save_pdf_dialog("Save cropped PDF", "cropped.pdf")
        if not out:
            return
        from makepdf.core.cropper import trim_margins
        trim_margins(Path(path), margin=36, output=Path(out))
        show_pdf(out)

    @objc.typedSelector(b"v@:@")
    def onResizePages_(self, sender):
        path = require_open_pdf()
        if not path:
            return
        out = save_pdf_dialog("Save resized PDF", "resized.pdf")
        if not out:
            return
        from makepdf.core.cropper import resize_pages
        resize_pages(Path(path), width=612, height=792, output=Path(out))
        show_pdf(out)

    # ======================================================================
    # Tools — Edit PDF
    # ======================================================================

    @objc.typedSelector(b"v@:@")
    def onAddText_(self, sender):
        path = require_open_pdf()
        if not path:
            return
        out = save_pdf_dialog("Save PDF with text", "text_added.pdf")
        if not out:
            return
        from makepdf.core.editor import add_text
        add_text(Path(path), 0, 72, 700, "Sample text added by MakePDF", Path(out))
        show_pdf(out)

    @objc.typedSelector(b"v@:@")
    def onAddImage_(self, sender):
        path = require_open_pdf()
        if not path:
            return
        img = pick_file("Select image to add", ["png", "jpg", "jpeg", "tiff"])
        if not img:
            return
        out = save_pdf_dialog("Save PDF with image", "image_added.pdf")
        if not out:
            return
        from makepdf.core.editor import add_image
        add_image(Path(path), 0, Path(img), 72, 500, 200, 200, Path(out))
        show_pdf(out)

    @objc.typedSelector(b"v@:@")
    def onAddWatermark_(self, sender):
        path = require_open_pdf()
        if not path:
            return
        out = save_pdf_dialog("Save watermarked PDF", "watermarked.pdf")
        if not out:
            return
        from makepdf.core.watermark import add_text_watermark
        add_text_watermark(Path(path), "CONFIDENTIAL", Path(out))
        show_pdf(out)

    @objc.typedSelector(b"v@:@")
    def onAddStamp_(self, sender):
        path = require_open_pdf()
        if not path:
            return
        out = save_pdf_dialog("Save stamped PDF", "stamped.pdf")
        if not out:
            return
        from makepdf.core.stamps import add_stamp
        add_stamp(Path(path), stamp_type="approved", output=Path(out))
        show_pdf(out)

    # ======================================================================
    # Tools — Protect & Redact
    # ======================================================================

    @objc.typedSelector(b"v@:@")
    def onEncrypt_(self, sender):
        path = require_open_pdf()
        if not path:
            return
        out = save_pdf_dialog("Save encrypted PDF", "encrypted.pdf")
        if not out:
            return
        from makepdf.core.security import encrypt
        encrypt(Path(path), "password", Path(out))
        show_alert("Encrypt", "PDF encrypted with password: 'password'\nChange this in production!")
        show_pdf(out)

    @objc.typedSelector(b"v@:@")
    def onDecrypt_(self, sender):
        path = require_open_pdf()
        if not path:
            return
        out = save_pdf_dialog("Save decrypted PDF", "decrypted.pdf")
        if not out:
            return
        from makepdf.core.security import decrypt
        decrypt(Path(path), "password", Path(out))
        show_pdf(out)

    @objc.typedSelector(b"v@:@")
    def onRedactText_(self, sender):
        path = require_open_pdf()
        if not path:
            return
        out = save_pdf_dialog("Save redacted PDF", "redacted.pdf")
        if not out:
            return
        from makepdf.core.redaction import search_and_redact
        search_and_redact(Path(path), "CONFIDENTIAL", output=Path(out))
        show_alert("Redact", "Redacted all occurrences of 'CONFIDENTIAL'.\nUse Web UI for custom text.")
        show_pdf(out)

    # ======================================================================
    # Tools — Comments / Markup
    # ======================================================================

    @objc.typedSelector(b"v@:@")
    def onHighlight_(self, sender):
        path = require_open_pdf()
        if not path:
            return
        out = save_pdf_dialog("Save highlighted PDF", "highlighted.pdf")
        if not out:
            return
        from makepdf.core.markup import highlight_area
        highlight_area(Path(path), 0, 72, 700, 200, 20, Path(out))
        show_pdf(out)

    @objc.typedSelector(b"v@:@")
    def onStickyNote_(self, sender):
        path = require_open_pdf()
        if not path:
            return
        out = save_pdf_dialog("Save PDF with note", "noted.pdf")
        if not out:
            return
        from makepdf.core.markup import add_sticky_note
        add_sticky_note(Path(path), 0, 200, 700, "Note added by MakePDF", Path(out))
        show_pdf(out)

    @objc.typedSelector(b"v@:@")
    def onAddComment_(self, sender):
        path = require_open_pdf()
        if not path:
            return
        out = save_pdf_dialog("Save PDF with comment", "commented.pdf")
        if not out:
            return
        from makepdf.core.markup import add_text_comment
        add_text_comment(Path(path), 0, 72, 650, "Comment by MakePDF", Path(out))
        show_pdf(out)

    # ======================================================================
    # Tools — Forms
    # ======================================================================

    @objc.typedSelector(b"v@:@")
    def onPrepareForm_(self, sender):
        out = save_pdf_dialog("Save new form PDF", "form.pdf")
        if not out:
            return
        from makepdf.core.forms import create_form
        fields = [
            {"name": "name", "field_type": "text", "x": 100, "y": 700, "width": 200, "height": 20},
            {"name": "email", "field_type": "text", "x": 100, "y": 660, "width": 200, "height": 20},
        ]
        create_form(fields, Path(out))
        show_pdf(out)

    @objc.typedSelector(b"v@:@")
    def onFillForm_(self, sender):
        path = require_open_pdf()
        if not path:
            return
        out = save_pdf_dialog("Save filled form", "filled.pdf")
        if not out:
            return
        from makepdf.core.forms import fill_form
        fill_form(Path(path), {"name": "MakePDF User", "email": "user@example.com"}, Path(out))
        show_pdf(out)

    @objc.typedSelector(b"v@:@")
    def onFlattenForms_(self, sender):
        path = require_open_pdf()
        if not path:
            return
        out = save_pdf_dialog("Save flattened PDF", "flattened.pdf")
        if not out:
            return
        from makepdf.core.flatten import flatten_forms
        flatten_forms(Path(path), output=Path(out))
        show_pdf(out)

    @objc.typedSelector(b"v@:@")
    def onFlattenAnnotations_(self, sender):
        path = require_open_pdf()
        if not path:
            return
        out = save_pdf_dialog("Save flattened PDF", "flattened.pdf")
        if not out:
            return
        from makepdf.core.flatten import flatten_annotations
        flatten_annotations(Path(path), output=Path(out))
        show_pdf(out)

    # ======================================================================
    # Tools — Compare
    # ======================================================================

    @objc.typedSelector(b"v@:@")
    def onCompare_(self, sender):
        a = pick_pdf("Select first PDF")
        if not a:
            return
        b = pick_pdf("Select second PDF")
        if not b:
            return
        from makepdf.core.compare import compare_text
        result = compare_text(Path(a), Path(b))
        text = "\n".join(f"{k}: {v}" for k, v in result.items()) if isinstance(result, dict) else str(result)
        show_text_window("PDF Comparison", text)

    # ======================================================================
    # Tools — Bates Numbering
    # ======================================================================

    @objc.typedSelector(b"v@:@")
    def onBatesNumber_(self, sender):
        path = require_open_pdf()
        if not path:
            return
        out = save_pdf_dialog("Save Bates-numbered PDF", "bates.pdf")
        if not out:
            return
        from makepdf.core.bates import add_bates_numbers
        add_bates_numbers(Path(path), prefix="DOC", start=1, output=Path(out))
        show_pdf(out)

    # ======================================================================
    # Tools — Optimize / Compress
    # ======================================================================

    @objc.typedSelector(b"v@:@")
    def onOptimize_(self, sender):
        path = require_open_pdf()
        if not path:
            return
        out = save_pdf_dialog("Save optimized PDF", "optimized.pdf")
        if not out:
            return
        from makepdf.core.optimizer import optimize
        optimize(Path(path), output=Path(out))
        orig = os.path.getsize(path)
        new = os.path.getsize(out)
        pct = ((orig - new) / orig * 100) if orig > 0 else 0
        show_alert("Optimize", f"Original: {orig:,} bytes\nOptimized: {new:,} bytes\nSaved: {pct:.1f}%")
        show_pdf(out)

    @objc.typedSelector(b"v@:@")
    def onOptimizeReport_(self, sender):
        path = require_open_pdf()
        if not path:
            return
        from makepdf.core.optimizer import get_optimization_report
        report = get_optimization_report(Path(path))
        text = "\n".join(f"{k}: {v}" for k, v in report.items()) if isinstance(report, dict) else str(report)
        show_text_window(f"Optimization Report - {os.path.basename(path)}", text)

    # ======================================================================
    # Tools — OCR
    # ======================================================================

    @objc.typedSelector(b"v@:@")
    def onOCR_(self, sender):
        show_alert("OCR", "OCR requires pytesseract and pdf2image.\nInstall with: pip install makepdf[ocr]\nThen use the Web UI for full OCR support.")

    # ======================================================================
    # Tools — Accessibility
    # ======================================================================

    @objc.typedSelector(b"v@:@")
    def onA11yCheck_(self, sender):
        path = require_open_pdf()
        if not path:
            return
        from makepdf.core.accessibility import check_accessibility
        result = check_accessibility(Path(path))
        lines = [f"{k}: {v}" for k, v in result.items()] if isinstance(result, dict) else [str(result)]
        show_text_window(f"Accessibility - {os.path.basename(path)}", "\n".join(lines))

    @objc.typedSelector(b"v@:@")
    def onSetLanguage_(self, sender):
        path = require_open_pdf()
        if not path:
            return
        out = save_pdf_dialog("Save PDF with language set", os.path.basename(path))
        if not out:
            return
        from makepdf.core.accessibility import set_language
        set_language(Path(path), "en-US", output=Path(out))
        show_alert("Language", "Language set to en-US")
        show_pdf(out)

    # ======================================================================
    # Tools — Attachments
    # ======================================================================

    @objc.typedSelector(b"v@:@")
    def onAddAttachment_(self, sender):
        path = require_open_pdf()
        if not path:
            return
        att = pick_file("Select file to attach")
        if not att:
            return
        out = save_pdf_dialog("Save PDF with attachment", "attached.pdf")
        if not out:
            return
        from makepdf.core.attachments import add_attachment
        add_attachment(Path(path), Path(att), output=Path(out))
        show_pdf(out)

    @objc.typedSelector(b"v@:@")
    def onListAttachments_(self, sender):
        path = require_open_pdf()
        if not path:
            return
        from makepdf.core.attachments import list_attachments
        atts = list_attachments(Path(path))
        if atts:
            show_text_window("Attachments", "\n".join(str(a) for a in atts))
        else:
            show_alert("Attachments", "No attachments found.")

    @objc.typedSelector(b"v@:@")
    def onExtractAttachments_(self, sender):
        path = require_open_pdf()
        if not path:
            return
        out_dir = save_file_dialog("Save attachments to folder")
        if not out_dir:
            return
        from makepdf.core.attachments import extract_attachments
        extract_attachments(Path(path), Path(os.path.dirname(out_dir)))
        show_alert("Extract", f"Attachments extracted to:\n{os.path.dirname(out_dir)}")

    # ======================================================================
    # Tools — Links & Bookmarks
    # ======================================================================

    @objc.typedSelector(b"v@:@")
    def onExtractLinks_(self, sender):
        path = require_open_pdf()
        if not path:
            return
        from makepdf.core.links import extract_links
        links = extract_links(Path(path))
        if links:
            show_text_window("Links", "\n".join(str(l) for l in links))
        else:
            show_alert("Links", "No links found.")

    @objc.typedSelector(b"v@:@")
    def onTOC_(self, sender):
        path = require_open_pdf()
        if not path:
            return
        from makepdf.core.toc import get_toc
        toc = get_toc(Path(path))
        if toc:
            lines = [f"{'  ' * (item.get('level', 0))}• {item.get('title', '')}" for item in toc]
            show_text_window("Table of Contents", "\n".join(lines))
        else:
            show_alert("TOC", "No table of contents found.")

    # ======================================================================
    # Tools — Metadata
    # ======================================================================

    @objc.typedSelector(b"v@:@")
    def onMetadataEdit_(self, sender):
        path = require_open_pdf()
        if not path:
            return
        from makepdf.core.metadata import get_metadata
        meta = get_metadata(Path(path))
        lines = [f"{k}: {v}" for k, v in meta.items()]
        show_text_window(f"Metadata - {os.path.basename(path)}", "\n".join(lines))

    @objc.typedSelector(b"v@:@")
    def onMetadataRemove_(self, sender):
        path = require_open_pdf()
        if not path:
            return
        out = save_pdf_dialog("Save PDF without metadata", "clean.pdf")
        if not out:
            return
        from makepdf.core.metadata import remove_metadata
        remove_metadata(Path(path), output=Path(out))
        show_alert("Metadata", "Metadata removed.")
        show_pdf(out)

    # ======================================================================
    # Tools — Signatures
    # ======================================================================

    @objc.typedSelector(b"v@:@")
    def onSign_(self, sender):
        show_alert("Sign", "Digital signatures require certificate files.\nUse the Web UI or CLI for full signing support:\n\nmakepdf sign apply input.pdf cert.p12 -o signed.pdf")

    @objc.typedSelector(b"v@:@")
    def onRequestSign_(self, sender):
        show_alert("e-Signatures", "e-Signature requests require integration with a signing service.\nThis feature is available through the Web UI.")

    # ======================================================================
    # Tools — Convert
    # ======================================================================

    @objc.typedSelector(b"v@:@")
    def onConvertToPDF_(self, sender):
        path = pick_file("Select file to convert", ["txt", "md", "html", "png", "jpg", "jpeg", "tiff"])
        if not path:
            return
        out = save_pdf_dialog("Save converted PDF", "converted.pdf")
        if not out:
            return
        ext = os.path.splitext(path)[1].lower()
        if ext in (".png", ".jpg", ".jpeg", ".tiff", ".bmp", ".gif"):
            from makepdf.core.creator import from_images
            from_images([Path(path)], Path(out))
        elif ext in (".txt", ".text"):
            from makepdf.core.creator import from_text
            from_text(Path(path).read_text(encoding="utf-8"), Path(out))
        elif ext == ".md":
            from makepdf.core.creator import from_markdown
            from_markdown(Path(path).read_text(encoding="utf-8"), Path(out))
        elif ext in (".html", ".htm"):
            from makepdf.core.creator import from_html
            from_html(Path(path).read_text(encoding="utf-8"), Path(out))
        else:
            show_alert("Convert", f"Unsupported format: {ext}")
            return
        show_pdf(out)

    # ======================================================================
    # Web UI
    # ======================================================================

    @objc.typedSelector(b"v@:@")
    def onWebUI_(self, sender):
        def _run():
            import uvicorn
            from makepdf.web.app import app as web_app
            uvicorn.run(web_app, host="127.0.0.1", port=8899, log_level="warning")

        t = threading.Thread(target=_run, daemon=True)
        t.start()
        import time
        time.sleep(1.5)
        subprocess.Popen(["open", "http://127.0.0.1:8899"])


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    app = NSApplication.sharedApplication()
    app.setActivationPolicy_(NSApplicationActivationPolicyRegular)
    delegate = AppDelegate.alloc().init()
    app.setDelegate_(delegate)
    app.activateIgnoringOtherApps_(True)
    app.run()


if __name__ == "__main__":
    main()
