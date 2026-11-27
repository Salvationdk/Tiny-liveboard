"""Run from repository root: python scripts/test-local.py."""
import pathlib
import shutil
import subprocess
import sys
root=pathlib.Path(__file__).resolve().parents[1]
def run(args):
    print("+", *map(str,args),flush=True)
    return subprocess.run(args,cwd=root).returncode
node=shutil.which("node")
if not node:
    sys.exit("Node.js is required for frontend regression tests.")
commands=[[sys.executable,"-m","compileall","-q","custom_components"],[sys.executable,"-m","unittest","discover","-s","tests"]]
for file in sorted((root/"tests").glob("*.test.mjs")):
    commands.append([node,"--test",str(file)])
for file in sorted((root/"custom_components/tiny_liveboard/frontend").glob("*.js")):
    commands.append([node,"--input-type=module","--check"])
    # JS syntax check uses stdin to support ES modules without package.json.
    commands.pop()
    result=subprocess.run([node,"--input-type=module","--check"],input=file.read_bytes(),cwd=root)
    if result.returncode: sys.exit(result.returncode)
results=[run(command) for command in commands]
sys.exit(1 if any(results) else 0)
