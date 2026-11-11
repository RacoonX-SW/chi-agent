"""Synthetic PDF and guarded local tool regressions; no protected input."""
import asyncio
import json
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from pypdf import PdfWriter
from pypdf.generic import DecodedStreamObject, DictionaryObject, NameObject

import live_development as live
import pdf_resource_reader as reader


def make_text_pdf(path: Path, *, encrypted: bool = False) -> None:
    writer = PdfWriter()
    for line in ("First page line", "Second page line"):
        page = writer.add_blank_page(width=300, height=300)
        font = DictionaryObject({NameObject("/Type"): NameObject("/Font"),
                                 NameObject("/Subtype"): NameObject("/Type1"),
                                 NameObject("/BaseFont"): NameObject("/Helvetica")})
        page[NameObject("/Resources")] = DictionaryObject({
            NameObject("/Font"): DictionaryObject({NameObject("/F1"): writer._add_object(font)})})
        stream = DecodedStreamObject()
        stream.set_data(f"BT /F1 12 Tf 20 250 Td ({line}) Tj ET".encode())
        page[NameObject("/Contents")] = writer._add_object(stream)
    if encrypted:
        writer.encrypt("synthetic-password")
    with path.open("wb") as handle:
        writer.write(handle)


class PdfReaderTests(unittest.TestCase):
    def test_text_pdf_lines_utf8_and_failure_cases(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            pdf = root / "synthetic.pdf"
            make_text_pdf(pdf)
            text = reader.read_allowed_file(pdf, None, None, pdf_enabled=True)
            self.assertIn("First page line", text)
            self.assertIn("Second page line", text)
            self.assertEqual(reader.read_allowed_file(pdf, 2, 1, pdf_enabled=True),
                             "".join(text.splitlines(keepends=True)[1:2]))
            with patch.object(reader, "MAX_PDF_PAGES", 1):
                self.assertIn("page limit", reader.read_allowed_file(pdf, None, None, pdf_enabled=True))
            with patch.object(reader, "MAX_RESULT_CHARS", 5):
                self.assertIn("output limit", reader.read_allowed_file(pdf, None, None, pdf_enabled=True))
            plain = root / "plain.txt"
            plain.write_text("一\n二\n三\n", encoding="utf-8")
            self.assertEqual(reader.read_allowed_file(plain, 2, 1, pdf_enabled=True), "二\n")
            plain.write_bytes(b"\xff\x00")
            self.assertTrue(reader.read_allowed_file(plain, None, None, pdf_enabled=True).startswith("ERROR:"))
            pdf.write_bytes(b"%PDF-corrupt")
            self.assertTrue(reader.read_allowed_file(pdf, None, None, pdf_enabled=True).startswith("ERROR:"))
            make_text_pdf(pdf, encrypted=True)
            self.assertIn("encrypted", reader.read_allowed_file(pdf, None, None, pdf_enabled=True))
            with patch.object(reader, "MAX_PDF_BYTES", 10):
                self.assertIn("size limit", reader.read_allowed_file(pdf, None, None, pdf_enabled=True))

    def test_dependency_missing_or_wrong_version_fails_k_identity(self):
        import importlib.metadata
        version = importlib.metadata.version
        with patch("importlib.metadata.version", side_effect=lambda name: "0.0.0" if name == "pypdf" else version(name)):
            with self.assertRaises(live.LiveFailure) as error:
                live._execution_identity(k=True)
            self.assertEqual(error.exception.code, "pdf_dependency_unavailable_or_mismatch")
        with patch("pdf_resource_reader.dependency_identity", side_effect=ModuleNotFoundError):
            with self.assertRaises(live.LiveFailure) as error:
                live._execution_identity(k=True)
            self.assertEqual(error.exception.code, "pdf_dependency_unavailable_or_mismatch")

    def test_local_tool_pdf_and_denied_path(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            workspace = root / "workspaces"
            provider = workspace / "case-1" / "provider"
            provider.mkdir(parents=True)
            pdf = provider / "document.pdf"
            make_text_pdf(pdf)
            outside = root / "outside.pdf"
            make_text_pdf(outside)
            ledger = SimpleNamespace(pending_calls=[])
            class Journal:
                policy = SimpleNamespace(scope="real_development")
                def start_dispatch(self, **kwargs): pass
                def finish_dispatch(self, **kwargs): pass
                def record_effect(self, effect): pass
            with patch.object(live, "WORKSPACE_CONTAINER_ROOT", workspace):
                tool = next(t for t in live._live_tools("c-once", root, root, Journal(), {}, ledger)
                            if t.name == "local-fs-read")
                def call(path):
                    args = {"path": str(path)}
                    ledger.pending_calls.append({"tool": "local-fs-read", "arguments": args, "call_id": "test"})
                    return asyncio.run(tool.on_invoke_tool(None, json.dumps(args)))
                self.assertIn("First page line", call(pdf))
                self.assertIn("outside", call(outside))
                link = provider / "link.pdf"
                link.symlink_to(outside)
                self.assertIn("outside", call(link))
                make_text_pdf(pdf, encrypted=True)
                self.assertIn("encrypted", call(pdf))
                pdf.write_bytes(b"broken")
                self.assertTrue(call(pdf).startswith("ERROR:"))


if __name__ == "__main__":
    unittest.main()
