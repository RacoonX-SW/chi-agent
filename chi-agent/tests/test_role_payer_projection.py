"""Package-external payer projection: 4-file legacy and 5-file t022 layouts.

Runs in the controller image because role_operator imports Docker/verifier
dependencies. No Docker call, world, model or credential is used.
"""
import hashlib
import tempfile
import unittest
from pathlib import Path

import role_operator
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

    def test_missing_extra_and_duplicate_files_are_rejected(self):
        names = ['01.pdf', '02.pdf', '03.pdf', '04.pdf', '05.pdf']
        paths = make_files(self.root, names)
        manifest = make_manifest(names, paths)
        (paths['05.pdf']).unlink()
        with self.assertRaisesRegex(ValueError, 'payer_projection_invalid'):
            role_operator._payer_projection(self.root, manifest)

        paths = make_files(self.root, names)
        extra = paths['01.pdf'].parent / '99_extra.pdf'
        extra.write_bytes(b'extra')
        with self.assertRaisesRegex(ValueError, 'payer_projection_invalid'):
            role_operator._payer_projection(self.root, make_manifest(names, paths))

        # Duplicate basenames across case directories must not satisfy a count.
        other = self.root / 'workspaces' / 'CASE-B' / 'payer' / 'incoming_request'
        other.mkdir(parents=True)
        (other / '01.pdf').write_bytes(b'duplicate')
        with self.assertRaisesRegex(ValueError, 'payer_projection_invalid'):
            role_operator._payer_projection(self.root, make_manifest(names, paths))

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


if __name__ == '__main__':
    unittest.main()
