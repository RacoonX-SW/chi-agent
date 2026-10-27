"""Bounded local text/PDF reading; caller is responsible for path authorization."""
from __future__ import annotations

import hashlib
import importlib.metadata
import io
from pathlib import Path

PDF_VERSION = "6.20.1"
PDF_WHEEL_SHA256 = "aa5a55ddcffdc5e5ab291d5decb23f6383f4e56f8e3263dc39af41fff03885ad"
PDF_SDIST_SHA256 = "28f5a9d2fdc2749264612d94e6a58de54c11d730d9f0cabf8ad34117c4942b45"
MAX_PDF_BYTES = 8 * 1024 * 1024
MAX_PDF_PAGES = 100
MAX_EXTRACTED_CHARS = 1_000_000
MAX_RESULT_CHARS = 100_000


def dependency_identity(lock_path: Path) -> dict[str, str]:
    """Bind the installed addon, its exact lock, and the source package bytes."""
    import pypdf
    lock = lock_path.read_bytes()
    expected = (f"pypdf=={PDF_VERSION} \\\n    --hash=sha256:{PDF_WHEEL_SHA256} \\\n"
                f"    --hash=sha256:{PDF_SDIST_SHA256}\n").encode()
    if lock != expected or pypdf.__version__ != PDF_VERSION or importlib.metadata.version("pypdf") != PDF_VERSION:
        raise ValueError("pdf_dependency_identity_mismatch")
    package = Path(pypdf.__file__).resolve().parent
    package.relative_to(Path("/pdf-deps").resolve())
    digest = hashlib.sha256()
    for path in sorted(package.rglob("*.py")):
        if path.is_symlink():
            raise ValueError("pdf_dependency_identity_mismatch")
        digest.update(str(path.relative_to(package)).encode() + b"\0" + path.read_bytes() + b"\0")
    return {"version": PDF_VERSION, "lock_sha256": hashlib.sha256(lock).hexdigest(),
            "wheel_sha256": PDF_WHEEL_SHA256, "package_sha256": digest.hexdigest()}


def read_allowed_file(path: Path, offset: int | None, limit: int | None, *, pdf_enabled: bool) -> str:
    try:
        with path.open("rb") as handle:
            header = handle.read(5)
        is_pdf = path.suffix.lower() == ".pdf" or header == b"%PDF-"
        if not is_pdf:
            text = path.read_text(encoding="utf-8")
        else:
            if not pdf_enabled:
                return "ERROR: PDF reading is unavailable in this execution mode"
            with path.open("rb") as handle:
                pdf_bytes = handle.read(MAX_PDF_BYTES + 1)
            if len(pdf_bytes) > MAX_PDF_BYTES:
                return "ERROR: PDF exceeds the input size limit"
            from pypdf import PdfReader
            from pypdf._configuration import apply_configuration
            with apply_configuration(maximum_declared_stream_length=8_388_608,
                                     array_based_stream_maximum_output_length=8_388_608,
                                     zlib_maximum_output_length=8_388_608,
                                     lzw_maximum_output_length=8_388_608,
                                     run_length_maximum_output_length=8_388_608,
                                     brotli_maximum_output_length=8_388_608,
                                     stream_decoding_work_maximum_length=16_777_216,
                                     page_tree_maximum_entries=1000, page_tree_maximum_depth=50,
                                     jbig2dec_binary=None, disable_legacy_handling=True):
                reader = PdfReader(io.BytesIO(pdf_bytes), strict=True)
                if reader.is_encrypted:
                    return "ERROR: encrypted PDF is not supported"
                if len(reader.pages) > MAX_PDF_PAGES:
                    return "ERROR: PDF exceeds the page limit"
                pages, total = [], 0
                for page in reader.pages:
                    value = page.extract_text() or ""
                    total += len(value)
                    if total > MAX_EXTRACTED_CHARS:
                        return "ERROR: PDF extracted text exceeds the processing limit"
                    pages.append(value)
                text = "\n".join(pages)
        if offset is not None or limit is not None:
            lines = text.splitlines(keepends=True)
            start = max(int(offset or 1) - 1, 0)
            text = "".join(lines[start:start + int(limit)] if limit is not None else lines[start:])
        if is_pdf and len(text) > MAX_RESULT_CHARS:
            return "ERROR: PDF text exceeds the output limit; use offset and limit"
        return text
    except (UnicodeError, OSError):
        return "ERROR: file is unreadable or is not supported UTF-8 text"
    except Exception:
        return "ERROR: PDF is damaged or unsupported"
