import tempfile
import unittest
from pathlib import Path
import importlib.util
import sys

ROOT = Path(__file__).resolve().parents[1]
pkg = type(sys)("birdcage_testpkg")
pkg.__path__ = [str(ROOT)]
sys.modules["birdcage_testpkg"] = pkg

for name in ("config", "workflow_manager"):
    spec = importlib.util.spec_from_file_location(f"birdcage_testpkg.{name}", ROOT / f"{name}.py")
    mod = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = mod
    spec.loader.exec_module(mod)

wm = sys.modules["birdcage_testpkg.workflow_manager"]


class WorkflowManagerTests(unittest.TestCase):
    def sample(self):
        return {
            "1": {"class_type": "LoadImage", "inputs": {"image": "old.png"}, "_meta": {"title": "Source"}},
            "2": {"class_type": "Sampler", "inputs": {"steps": 20, "seed": 1, "model": ["9", 0]}},
            "3": {"class_type": "PreviewImage", "inputs": {"images": ["2", 0]}},
        }

    def test_inspect_only_literal_inputs_bindable(self):
        nodes = wm.WorkflowManager.inspect_workflow(self.sample())
        sampler = next(x for x in nodes if x["id"] == "2")
        inputs = {x["name"]: x for x in sampler["inputs"]}
        self.assertTrue(inputs["steps"]["bindable"])
        self.assertFalse(inputs["model"]["bindable"])

    def test_save_and_apply_profile(self):
        with tempfile.TemporaryDirectory() as td:
            mgr = wm.WorkflowManager(Path(td))
            mgr.save_profile(stage="reveal", name="demo", workflow=self.sample(), bindings={"source_image": {"node": "1", "input": "image"}, "steps": {"node": "2", "input": "steps"}}, output_node="3")
            profile = mgr.load_profile("reveal", "demo")
            applied = mgr.apply(profile, {"source_image": "new.png", "steps": 4})
            self.assertEqual(applied["1"]["inputs"]["image"], "new.png")
            self.assertEqual(applied["2"]["inputs"]["steps"], 4)
            self.assertEqual(self.sample()["2"]["inputs"]["steps"], 20)

    def test_graph_format_rejected(self):
        with self.assertRaises(ValueError):
            wm.WorkflowManager.inspect_workflow({"nodes": []})


if __name__ == "__main__":
    unittest.main()
