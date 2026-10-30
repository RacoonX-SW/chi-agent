"""Synthetic test of the official payer PDF materializer and role read boundary."""
import tempfile
from pathlib import Path
from types import SimpleNamespace

from pypdf import PdfWriter
from pypdf.generic import DecodedStreamObject, DictionaryObject, NameObject
from chi_bench.core.context import ServiceContext
from go_chi_resources import workspace_path
from pdf_resource_reader import read_allowed_file


def test_payer_materialization_and_pdf_read():
    with tempfile.TemporaryDirectory() as d:
        root = Path(d)
        fixtures = root / 'fixtures'; source = fixtures / 'request'; source.mkdir(parents=True)
        writer = PdfWriter(); page = writer.add_blank_page(width=300, height=300)
        font = DictionaryObject({NameObject('/Type'): NameObject('/Font'), NameObject('/Subtype'): NameObject('/Type1'),
                                 NameObject('/BaseFont'): NameObject('/Helvetica')})
        page[NameObject('/Resources')] = DictionaryObject({NameObject('/Font'): DictionaryObject({NameObject('/F1'): writer._add_object(font)})})
        stream = DecodedStreamObject(); stream.set_data(b'BT /F1 12 Tf 20 250 Td (Synthetic incoming) Tj ET')
        page[NameObject('/Contents')] = writer._add_object(stream)
        with (source / 'request.pdf').open('wb') as handle: writer.write(handle)
        workspace = root / 'workspaces'
        artifacts = []
        ctx = SimpleNamespace(fixtures_dir=fixtures, _scenario=SimpleNamespace(target_case_id='case'), workspace_root=workspace,
            workspace_relative_path=lambda case, scope, directory: Path(case) / scope.value / directory,
            register_workspace_artifact=lambda **kwargs: artifacts.append(kwargs))
        ServiceContext._materialize_incoming_request_pdfs(ctx)
        target = workspace / 'case/payer/incoming_request/request.pdf'
        assert len(artifacts) == 1 and target.read_bytes() == (source / 'request.pdf').read_bytes()
        assert workspace_path(workspace, str(target), 'payer') == target
        assert workspace_path(workspace, str(target), 'provider') is None
        assert 'Synthetic incoming' in read_allowed_file(target, None, None, pdf_enabled=True)
