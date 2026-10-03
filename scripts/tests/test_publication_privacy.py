"""Run: python -m unittest discover -s scripts/tests -v"""
import io
import json
from pathlib import Path
import sys
import tempfile
import unittest

from PIL import Image, PngImagePlugin

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import publication_privacy as privacy


class PublicationPrivacyTests(unittest.TestCase):
    def image(self, fmt, **kwargs):
        stream = io.BytesIO()
        Image.new('RGB', (7, 9), (30, 90, 120)).save(stream, format=fmt, **kwargs)
        return stream.getvalue()

    def test_png_pixels_and_profile_survive_history_removal(self):
        metadata = PngImagePlugin.PngInfo()
        metadata.add_text('File', chr(67)+':/'+ 'Users/example/scene.blend')
        metadata.add_text('Date', 'private date')
        before = self.image('PNG', pnginfo=metadata, icc_profile=b'profile')
        after, removed = privacy.sanitize_png(before)
        self.assertEqual(removed, 2)
        with Image.open(io.BytesIO(before)) as a, Image.open(io.BytesIO(after)) as b:
            self.assertEqual(a.tobytes(), b.tobytes())
            self.assertEqual(b.info['icc_profile'], b'profile')
            self.assertNotIn('File', b.info)
        self.assertEqual(privacy.findings(after, '.png'), [])

    def test_jpeg_pixels_survive_exif_removal(self):
        exif = Image.Exif()
        exif[315] = 'private owner'
        before = self.image('JPEG', exif=exif)
        after, removed = privacy.sanitize_jpeg(before)
        self.assertEqual(removed, 1)
        with Image.open(io.BytesIO(before)) as a, Image.open(io.BytesIO(after)) as b:
            self.assertEqual(a.tobytes(), b.tobytes())
            self.assertFalse(b.getexif())

    def test_json_paths_removed_license_preserved(self):
        value = {'source': chr(67)+':/'+ 'Users/example/asset.blend',
                 'copyright': 'consomme hollywood', 'bones': [1, 2, 3]}
        result = privacy.clean_json(value)
        self.assertEqual(result['source'], '[local path removed]')
        self.assertEqual(result['copyright'], value['copyright'])
        self.assertEqual(result['bones'], value['bones'])

    def test_credentials_cause_failure(self):
        with self.assertRaises(ValueError):
            privacy.clean_json({'key': 'sk-'+ 'x'*30})

    def test_existing_files_never_overwritten(self):
        with tempfile.TemporaryDirectory() as folder:
            source, target = Path(folder)/'in.txt', Path(folder)/'out.txt'
            source.write_text('original')
            target.write_text('keep')
            with self.assertRaises(FileExistsError):
                privacy.clean_file(source, target)
            self.assertEqual(target.read_text(), 'keep')
            self.assertEqual(source.read_text(), 'original')

    def test_zip_cleaning_requires_explicit_rebuild(self):
        with tempfile.TemporaryDirectory() as folder:
            source = Path(folder)/'in.zip'
            source.write_bytes(b'not read as ZIP')
            with self.assertRaises(ValueError):
                privacy.clean_file(source, Path(folder)/'out.zip')

    def test_truncated_images_fail(self):
        for fn, data in ((privacy.sanitize_png, self.image('PNG')[:-12]),
                         (privacy.sanitize_jpeg, b'\xff\xd8\xff')):
            with self.assertRaises(ValueError):
                fn(data)


if __name__ == '__main__':
    unittest.main()
