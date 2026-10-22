import copy
import json
from pathlib import Path
import re
import subprocess
import sys
import tempfile
import unittest
import test_component_evidence

ROOT = Path(__file__).resolve().parent.parent


class ScopeAuditTests(unittest.TestCase):
    def setUp(self):
        self.samples = {}
        for kind, reference in [('component', 'third-stage-only-contract.md'), ('final', 'final-audit-contract.md')]:
            text = (ROOT / 'references' / reference).read_text().split('## JSON 结构', 1)[1]
            data = json.loads(re.search(r'```json\s*(.*?)```', text, re.S).group(1))
            if kind == 'component':
                data['visualValidation']['rootsCompared'] = 1
            self.samples[kind] = data

    def check(self, kind, data, expected):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / 'audit.json'
            data = copy.deepcopy(data)
            fixture = None
            try:
                if kind == 'component':
                    fixture = test_component_evidence.EvidenceTests()
                    fixture.setUp()
                    fixture.inventory['families'] = []
                    fixture.outcomes['families'] = []
                    for snap in (fixture.before, fixture.after):
                        snap['nodes'] = []
                        for root in snap['roots']:
                            root['id'] = {'source': '1:2', 'copy': '3:4'}.get(root['id'], root['id'])
                    fixture.data['nodeMappings'] = []
                    fixture.data['rootMappings'] = [{'sourceId': '1:2', 'copyId': '3:4'}]
                    if data.get('editMode') == 'in-place':
                        fixture.use_in_place('3:4')
                    else:
                        fixture.write()
                    data.update(schemaVersion=2, evidenceManifest=str(fixture.root/'evidence.json'),
                                affectedBeforeNodeIds=[], affectedAfterNodeIds=[])
                path.write_text(json.dumps(data))
                result = subprocess.run([sys.executable, str(ROOT / 'scripts' / f'validate_{kind}_audit.py'), str(path)], capture_output=True, text=True)
            finally:
                if fixture:
                    fixture.doCleanups()
        self.assertEqual(result.returncode, expected, result.stdout + result.stderr)

    def test_visible_and_legacy_valid(self):
        for kind, data in self.samples.items():
            self.check(kind, data, 0)
            del data['scope']
            self.check(kind, data, 1 if kind == 'component' else 0)

    def test_missing_dependency_or_changed_excluded_content_blocks(self):
        for kind, base in self.samples.items():
            for field in ['dependencyCheckPassed', 'excludedContentPreserved']:
                data = copy.deepcopy(base)
                data['scope'][field] = False
                self.check(kind, data, 1)
                data['status'] = 'incomplete'
                self.check(kind, data, 2)

    def test_scope_schema_and_expansion(self):
        for kind, base in self.samples.items():
            for field, value in [('mode', 'unknown'), ('processingRootIds', []), ('processingRootIds', ['x', 'x']), ('dependencyCheckPassed', 1)]:
                data = copy.deepcopy(base); data['scope'][field] = value
                self.check(kind, data, 1)
            data = copy.deepcopy(base); data['scope']['mode'] = 'explicit-expanded'
            self.check(kind, data, 1)
            data['scope']['requestedScope'] = '用户要求查看展开后的报告'
            self.check(kind, data, 0)

    def test_existing_gates_are_not_waived(self):
        for field in ['geometryRegressions', 'unexpectedPixelDifferences']:
            data = copy.deepcopy(self.samples['component'])
            data['visualValidation'][field] = 1; data['status'] = 'incomplete'
            self.check('component', data, 2)
        data = copy.deepcopy(self.samples['component'])
        data['targetProtection']['canvasBoundaryPassed'] = False; data['status'] = 'incomplete'
        self.check('component', data, 2)
        data = copy.deepcopy(self.samples['final'])
        data['typography']['unmapped'] = 1; data['p0Passed'] = False; data['status'] = 'incomplete'
        self.check('final', data, 2)

    def test_in_place_protection_and_root_scope_are_required(self):
        base = self.samples['component']
        data = copy.deepcopy(base)
        del data['targetProtection']
        self.check('component', data, 1)
        for field in ['scopeRespected', 'sharedDependenciesUnchanged']:
            data = copy.deepcopy(base)
            data['targetProtection'][field] = False
            data['status'] = 'incomplete'
            self.check('component', data, 2)
        data = copy.deepcopy(base)
        data['targetProtection']['targetNodeIds'] = ['other-root']
        self.check('component', data, 1)
        data = copy.deepcopy(base)
        data['scope']['processingRootIds'] = ['other-root']
        self.check('component', data, 1)
        data = copy.deepcopy(base)
        data['visualValidation']['rootsCompared'] = 2
        self.check('component', data, 1)

    def test_explicit_and_legacy_safe_copy_remain_valid(self):
        data = copy.deepcopy(self.samples['component'])
        del data['targetProtection']
        data['sourceProtection'] = dict(sourceNodeIds=['1:2'], copyNodeIds=['3:4'],
                                       mappingComplete=True, sourceUnchanged=True,
                                       canvasBoundaryPassed=True)
        data['editMode'] = 'safe-copy'
        self.check('component', data, 0)
        del data['editMode']
        self.check('component', data, 0)


if __name__ == '__main__':
    unittest.main()
