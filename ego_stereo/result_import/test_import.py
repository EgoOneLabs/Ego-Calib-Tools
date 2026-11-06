import hashlib
import json
from pathlib import Path
import shutil
import tempfile
import unittest
from unittest.mock import patch
from import_existing_calibration import import_result, validate_chain, load_yaml, FILES, EXPECTED_SHA


class ImportTest(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix='ego_profile_test_')
        self.root = Path(self.temp.name)
        self.source = self.root / 'source'
        self.source.mkdir()
        shutil.copyfile(Path(__file__).with_name('reference_camera_ds.yaml'), self.source / FILES[0])
        # Test fixtures only: PDF copying/signature check, not report rendering/quality.
        (self.source / FILES[1]).write_bytes(b'%PDF-1.4\nfixture only\n%%EOF\n')
        chain = load_yaml((self.source / FILES[0]).read_text(), 'unused')
        report = ''
        for eye in (0, 1):
            report += 'cam%d (/cam%d/image_raw):\n type: DoubleSphereCameraGeometry\n projection: [%s]\n' % (eye, eye, ' '.join(str(v) for v in chain['cam%d' % eye]['intrinsics']))
        report += '\nbaseline T_1_0:\n t: [%s]\n' % ' '.join(str(chain['cam1']['T_cn_cnm1'][i][3]) for i in range(3))
        (self.source / FILES[2]).write_text(report)
        self.pdf_patch = patch('import_existing_calibration.pdf_summary', return_value=report)
        self.pdf_patch.start()

    def tearDown(self):
        self.pdf_patch.stop()
        self.temp.cleanup()

    def test_import_preserves_source_and_pending(self):
        original = {name: (self.source / name).read_bytes() for name in FILES}
        out = import_result(self.source, self.root / 'profiles')
        p = json.loads((out / 'camera_profile.json').read_text())
        self.assertEqual(p['status'], 'EXISTING_CAMERA_RESULT_IMPORTED_REVIEW_PENDING')
        self.assertFalse(p['calibration_quality_accepted'])
        self.assertFalse(p['activated_in_android_app'])
        self.assertAlmostEqual(p['geometry_checks']['baseline_m'] * 1000, 89.271190, places=5)
        for name in FILES:
            self.assertEqual((self.source / name).read_bytes(), original[name])
            self.assertEqual((out / 'original_results' / name).read_bytes(), original[name])
        self.assertEqual(p['result_files'][FILES[0]]['sha256'], EXPECTED_SHA)

    def test_wrong_yaml_rejected(self):
        with (self.source / FILES[0]).open('a') as f:
            f.write('\n# Changed input\n')
        with self.assertRaisesRegex(ValueError, 'SHA256 differs'):
            import_result(self.source, self.root / 'profiles')

    def test_missing_report_rejected(self):
        (self.source / FILES[1]).unlink()
        with self.assertRaisesRegex(ValueError, 'missing/empty'):
            import_result(self.source, self.root / 'profiles')

    def test_reflected_rotation_rejected(self):
        p = load_yaml((self.source / FILES[0]).read_text(), 'unused')
        for i in range(3):
            p['cam1']['T_cn_cnm1'][i][0] *= -1
        with self.assertRaisesRegex(ValueError, 'proper orthonormal'):
            validate_chain(p)

    def test_wrong_model_report_rejected(self):
        p = self.source / FILES[2]
        p.write_text(p.read_text().replace('DoubleSphere', 'EquidistantPinhole'))
        with self.assertRaisesRegex(ValueError, 'Report model is not DS'):
            import_result(self.source, self.root / 'profiles')


if __name__ == '__main__':
    unittest.main()
