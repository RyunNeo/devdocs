import json
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]


def next_config(env):
    script = """
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');
const ts = require('typescript');
const file = path.resolve('apps/web/next.config.ts');
const code = ts.transpileModule(fs.readFileSync(file, 'utf8'), {
  compilerOptions: { module: ts.ModuleKind.CommonJS, esModuleInterop: true }
}).outputText;
const context = { exports: {}, require, __dirname: path.dirname(file),
                  process: { env: JSON.parse(process.argv[1]) } };
vm.runInNewContext(code, context);
const config = context.exports.default;
config.rewrites().then(rewrites => console.log(JSON.stringify({
  output: config.output ?? null, root: config.outputFileTracingRoot ?? null,
  distDir: config.distDir, rewrites
})));
"""
    result = subprocess.run(
        ["node", "-e", script, json.dumps(env)],
        cwd=ROOT,
        text=True,
        capture_output=True,
        check=True,
        timeout=20,
    )
    return json.loads(result.stdout)


def test_normal_development_config_is_unchanged():
    result = next_config({})
    assert result["output"] is None and result["root"] is None
    assert result["rewrites"][0]["destination"] == "http://127.0.0.1:8000/:path*"


def test_standalone_config_traces_monorepo_and_uses_internal_api():
    result = next_config({"DEPLOY_STANDALONE": "1", "API_BASE_URL": "http://api:8000"})
    assert result["output"] == "standalone"
    assert Path(result["root"]) == ROOT
    assert result["rewrites"][0]["destination"] == "http://api:8000/:path*"


def test_custom_test_output_directory_still_works():
    assert next_config({"NEXT_DIST_DIR": ".next-test"})["distDir"] == ".next-test"
