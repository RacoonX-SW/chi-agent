"""Package-external payer projection: 4-file legacy and 5-file t022 layouts.

Runs in the controller image because role_operator imports Docker/verifier
dependencies. No Docker call, world, model or credential is used.
"""
import hashlib
import tempfile
import unittest
from pathlib import Path

import role_operator
import make_role_manifest
import role_resource_preflight
from evaluation_bundle import BundleFailure


def make_files(root, names, *, scope='payer', content=b'pdf'):
    request = root / 'workspaces' / 'CASE-A' / scope / 'incoming_request'
    request.mkdir(parents=True, exist_ok=True)
    result = {}
    for name in names:
        path = request / name
        path.write_bytes(content + name.encode())
        result[name] = path
    return result


def make_manifest(names, paths):
    return {'files': [{
        'path': f'prior_auth_um/tasks/synthetic/fixtures/request/{name}',
        'size': paths[name].stat().st_size,
        'sha256': hashlib.sha256(paths[name].read_bytes()).hexdigest(),
    } for name in names]}


def write(path, content):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(content if isinstance(content, bytes) else content.encode())


class PayerProjectionTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)

    def tearDown(self):
        self.temp.cleanup()

    def test_four_file_legacy_projection_remains_valid(self):
        names = [f'0{i}_note.pdf' for i in range(1, 4)] + ['prior-auth-request-form.pdf']
        paths = make_files(self.root, names)
        result = role_operator._payer_projection(self.root, make_manifest(names, paths))
        self.assertEqual(result, {'status': 'ready', 'count': 4})

    def test_five_file_t022_projection_is_valid(self):
        names = ['01_rheumatology-clinic-visit-note.pdf',
                 '02_letter-of-medical-necessity-for-hospital-outpatient-site-of-care.pdf',
                 '03_infusion-visit-progress-note.pdf',
                 '04_site-of-care-availability-attestation.pdf',
                 'prior-auth-request-form.pdf']
        paths = make_files(self.root, names)
        result = role_operator._payer_projection(self.root, make_manifest(names, paths))
        self.assertEqual(result, {'status': 'ready', 'count': 5})

    def _reset(self):
        self.temp.cleanup()
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)

    def test_missing_file_is_rejected_in_isolation(self):
        names = ['01.pdf', '02.pdf', '03.pdf', '04.pdf', '05.pdf']
        paths = make_files(self.root, names)
        manifest = make_manifest(names, paths)
        paths['05.pdf'].unlink()
        with self.assertRaisesRegex(ValueError, 'payer_projection_invalid'):
            role_operator._payer_projection(self.root, manifest)

    def test_extra_file_is_rejected_in_isolation(self):
        names = ['01.pdf', '02.pdf', '03.pdf', '04.pdf', '05.pdf']
        paths = make_files(self.root, names)
        (paths['01.pdf'].parent / '99_extra.pdf').write_bytes(b'extra')
        with self.assertRaisesRegex(ValueError, 'payer_projection_invalid'):
            role_operator._payer_projection(self.root, make_manifest(names, paths))

    def test_duplicate_basename_with_same_total_is_rejected(self):
        names = ['01.pdf', '02.pdf', '03.pdf', '04.pdf', '05.pdf']
        paths = make_files(self.root, names)
        manifest = make_manifest(names, paths)
        other = self.root / 'workspaces' / 'CASE-B' / 'payer' / 'incoming_request'
        other.mkdir(parents=True)
        (other / '01.pdf').write_bytes(b'duplicate')
        # Keep the total at five but replace 05.pdf with a duplicate 01.pdf.
        paths['05.pdf'].unlink()
        with self.assertRaisesRegex(ValueError, 'payer_projection_invalid'):
            role_operator._payer_projection(self.root, manifest)

    def test_wrong_size_or_hash_is_rejected(self):
        names = ['01.pdf', '02.pdf', '03.pdf', '04.pdf', '05.pdf']
        paths = make_files(self.root, names)
        manifest = make_manifest(names, paths)
        manifest['files'][0]['size'] += 1
        with self.assertRaisesRegex(ValueError, 'payer_projection_invalid'):
            role_operator._payer_projection(self.root, manifest)
        manifest = make_manifest(names, paths)
        manifest['files'][0]['sha256'] = 'f' * 64
        with self.assertRaisesRegex(ValueError, 'payer_projection_invalid'):
            role_operator._payer_projection(self.root, manifest)

    def test_provider_scope_is_rejected(self):
        names = ['01.pdf', '02.pdf', '03.pdf', '04.pdf', '05.pdf']
        paths = make_files(self.root, names, scope='provider')
        with self.assertRaisesRegex(ValueError, 'payer_projection_invalid'):
            role_operator._payer_projection(self.root, make_manifest(names, paths))

    def test_symlink_is_rejected(self):
        names = ['01.pdf', '02.pdf', '03.pdf', '04.pdf', '05.pdf']
        paths = make_files(self.root, names)
        target = paths['01.pdf']
        target.unlink()
        target.symlink_to(paths['02.pdf'])
        with self.assertRaises((ValueError, BundleFailure)):
            role_operator._payer_projection(self.root, make_manifest(names, paths))

    def test_empty_and_oversized_manifest_are_rejected(self):
        with self.assertRaisesRegex(ValueError, 'payer_projection_invalid'):
            role_operator._payer_projection(self.root, {'files': []})
        names = [f'{i:02d}.pdf' for i in range(21)]
        paths = make_files(self.root, names)
        with self.assertRaisesRegex(ValueError, 'payer_projection_invalid'):
            role_operator._payer_projection(self.root, make_manifest(names, paths))

    def _dataset(self, count):
        dataset = self.root / 'dataset'
        task = 'pa_t022_t022_o001_p01_nurse_review_payer'
        prefix = f'prior_auth_um/tasks/{task}'
        write(dataset / 'REVISION', 'a' * 40 + '\n')
        write(dataset / 'prior_auth_provider/shared/worlds/healthverse-pa-v2-payer.json',
              '{"world_id":"healthverse-pa-v2-payer"}')
        write(dataset / 'prior_auth_provider/shared/worlds/healthverse-pa-v2-provider.json',
              '{"world_id":"healthverse-pa-v2-provider"}')
        write(dataset / prefix / 'instruction.md', 'instruction')
        write(dataset / prefix / 'task.toml', "version = '1.0'\n")
        write(dataset / prefix / 'tool_reference.md', 'reference')
        write(dataset / prefix / 'fixtures/manifest.json',
              '{"world_id":"healthverse-pa-v2-payer"}')
        write(dataset / prefix / 'fixtures/expectations.json', '{"hidden":true}')
        for index in range(count):
            write(dataset / prefix / f'fixtures/request/{index:02d}_doc.pdf',
                  b'%PDF-1.4 synthetic')
        return dataset, task

    def _chain(self, count, *, out='manifest.json'):
        dataset, task = self._dataset(count)
        manifest = make_role_manifest.build_manifest(dataset, 'prior_auth_um', task)
        target = self.root / out
        digest = make_role_manifest.write_manifest(
            manifest, target, dataset, preflight=role_resource_preflight.validate)
        artifacts = self.root / f'artifacts-{count}'
        for item in manifest['files']:
            if '/fixtures/request/' not in item['path']:
                continue
            name = Path(item['path']).name
            write(artifacts / 'workspaces' / 'CASE-A' / 'payer' / 'incoming_request' / name,
                  (dataset / item['path']).read_bytes())
        return dataset, task, manifest, digest, artifacts

    def test_manifest_preflight_projection_four_file_chain(self):
        _, _, manifest, _, artifacts = self._chain(4)
        self.assertEqual(role_operator._payer_projection(artifacts, manifest)['count'], 4)

    def test_manifest_preflight_projection_five_file_chain(self):
        _, _, manifest, _, artifacts = self._chain(5)
        self.assertEqual(role_operator._payer_projection(artifacts, manifest)['count'], 5)

    def test_manifest_generation_rejects_out_of_bounds_counts(self):
        for count in (0, 21):
            with self.subTest(count=count):
                with self.assertRaises(make_role_manifest.ManifestError):
                    self._dataset(count)
                    make_role_manifest.build_manifest(
                        self.root / 'dataset', 'prior_auth_um',
                        'pa_t022_t022_o001_p01_nurse_review_payer')

    def test_manifest_preflight_rejects_missing_file_after_generation(self):
        dataset, task = self._dataset(5)
        manifest = make_role_manifest.build_manifest(dataset, 'prior_auth_um', task)
        (dataset / 'prior_auth_um/tasks' / task / 'fixtures/request/00_doc.pdf').unlink()
        with self.assertRaises(Exception):
            make_role_manifest.write_manifest(
                manifest, self.root / 'missing.json', dataset,
                preflight=role_resource_preflight.validate)

    def test_projection_duplicate_with_same_total_after_manifest(self):
        _, _, manifest, _, artifacts = self._chain(5)
        request = artifacts / 'workspaces' / 'CASE-A' / 'payer' / 'incoming_request'
        (request / '04_doc.pdf').unlink()
        other = artifacts / 'workspaces' / 'CASE-B' / 'payer' / 'incoming_request'
        other.mkdir(parents=True)
        (other / '00_doc.pdf').write_bytes(b'duplicate')
        with self.assertRaisesRegex(ValueError, 'payer_projection_invalid'):
            role_operator._payer_projection(artifacts, manifest)


if __name__ == '__main__':
    unittest.main()
