"""Run local regression checks without GitHub Actions."""
import pathlib
import shutil
import subprocess
import sys

root = pathlib.Path(__file__).resolve().parents[1]
node = shutil.which("node")
if not node:
    sys.exit("Node.js is required for frontend regression tests.")

def run(label, args, data=None):
    print("\n==", label, "==", flush=True)
    return subprocess.run(args, cwd=root, input=data).returncode

results = {}
results["Python syntax"] = run("Python syntax", [sys.executable, "-m", "compileall", "-q", "custom_components", "tests"])
results["Python tests"] = run("Python tests", [sys.executable, "-m", "pytest", "-q", "tests"])
for file in sorted((root / "custom_components/tiny_liveboard/frontend").glob("*.js")):
    label = "JS syntax: " + file.name
    results[label] = run(label, [node, "--input-type=module", "--check"], file.read_bytes())
for file in sorted((root / "tests").glob("*.test.mjs")):
    label = "JS tests: " + file.name
    results[label] = run(label, [node, "--test", str(file)])
print("\n== Summary ==")
for label, code in results.items():
    print("FAIL" if code else "PASS", label)
sys.exit(1 if any(results.values()) else 0)
