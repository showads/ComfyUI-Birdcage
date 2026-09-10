import tempfile
import unittest
from pathlib import Path
import importlib.util
import sys

try:
    from PIL import Image
except Exception:
    Image = None

ROOT = Path(__file__).resolve().parents[1]
pkg = sys.modules.get("birdcage_testpkg") or type(sys)("birdcage_testpkg")
pkg.__path__ = [str(ROOT)]
sys.modules["birdcage_testpkg"] = pkg

spec = importlib.util.spec_from_file_location("birdcage_testpkg.image_utils", ROOT / "image_utils.py")
image_utils = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = image_utils
spec.loader.exec_module(image_utils)


@unittest.skipIf(Image is None, "Pillow unavailable")
class ImageUtilsTests(unittest.TestCase):
    def test_scene_plate_preserves_outside_mask(self):
        with tempfile.TemporaryDirectory() as td:
            td = Path(td)
            source = Image.new("RGB", (100, 100), "red")
            revealed = Image.new("RGB", (100, 100), "blue")
            mask = Image.new("L", (100, 100), 0)
            for x in range(30, 70):
                for y in range(30, 70):
                    mask.putpixel((x, y), 255)
            source.save(td / "source.png")
            revealed.save(td / "revealed.png")
            mask.save(td / "mask.png")
            out = td / "out"
            metadata = image_utils.build_scene_assets(td / "source.png", td / "revealed.png", td / "mask.png", out, expand=0, feather=0)
            plate = Image.open(out / "plate.png")
            self.assertEqual(plate.getpixel((5,5)), (255,0,0))
            self.assertEqual(plate.getpixel((50,50)), (0,0,255))
            self.assertGreater(metadata["cloth_bbox"]["width"], 0)


if __name__ == "__main__":
    unittest.main()
