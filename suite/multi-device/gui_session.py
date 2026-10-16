"""Offline GUI state; compatibility and archive creation belong to suite_builder."""
from __future__ import annotations
import copy
import json
from pathlib import Path
import subprocess
import zipfile

import intake
import suite_builder as b


FAILURES = (ValueError, OSError, TypeError, KeyError, AttributeError,
            subprocess.SubprocessError, zipfile.BadZipFile)
PASSED = ('reviewed-recipe', 'reviewed-components', 'candidate-static-pass')


class Session:
    def __init__(self):
        self.profile = None
        self.base = Path.cwd().resolve()
        self.materials = None
        self.report = None
        self._checked = None

    def _invalidate(self):
        self.report = None
        self._checked = None

    def _lock_wallet(self):
        if self.profile and self.profile.get('mode') == 'apk-overlay':
            for c in self.profile.get('components', []):
                if isinstance(c, dict) and b.wallet(str(c.get('package', ''))):
                    if c.get('enabled') is not False:
                        c['enabled'] = False
                        self._invalidate()

    def _fingerprint(self):
        return json.dumps([self.profile, str(self.base), self.materials], sort_keys=True)

    def load_profile(self, path):
        self._invalidate()
        path = Path(path).expanduser().resolve()
        profile = b.load(path)
        b.require(isinstance(profile, dict), 'Profile must be a JSON object')
        b.require(profile.get('schema') == 1, 'Unsupported profile schema')
        pid = profile.get('id')
        b.require(isinstance(pid, str) and b.TOKEN.fullmatch(pid), 'Invalid profile id')
        b.require(profile.get('mode') in ('reviewed-suite', 'selected-suite', 'apk-overlay'), 'Unknown profile mode')
        b.require(isinstance(profile.get('target'), dict), 'Target must be an object')
        b.require(profile.get('wallet_policy') == 'separate-validation-no-reset', 'Wallet must remain separate, no reset')
        if profile['mode'] == 'apk-overlay':
            components = profile.get('components')
            b.require(isinstance(components, list) and all(isinstance(c, dict) for c in components),
                      'Components must be a list of objects')
        for key in ('source_input', 'source_inputs'):
            if key in profile:
                value = profile[key]
                b.require((key == 'source_input' and isinstance(value, str))
                          or (isinstance(value, list) and all(isinstance(p, str) for p in value)),
                          'Invalid source paths: ' + key)
        materials = profile.get('gui_materials')
        materials = str(b.path_of(materials, path.parent)) if materials else None
        self.profile = profile
        self.base = path.parent
        self.materials = materials
        self._lock_wallet()
        return self.profile

    def use_reviewed(self, profile_path, materials=None):
        profile = self.load_profile(profile_path)
        if materials is not None:
            self.configure_materials(materials)
        return profile

    def analyse(self, target_path, sources: list[Path], profile_id):
        self._invalidate()
        b.require(isinstance(profile_id, str) and b.TOKEN.fullmatch(profile_id), 'Invalid profile id')
        b.require(sources, 'Select at least one source APK or directory')
        target_path = Path(target_path).expanduser().resolve()
        sources = [Path(p).expanduser().resolve() for p in sources]
        target = intake.scan(target_path)
        scans = [intake.scan(p) for p in sources]
        model = {key: copy.deepcopy(target.get(key)) for key in ('device', 'sdk', 'incremental', 'abis')}
        originals = {}
        for apk in target.get('apks', []):
            originals.setdefault(apk.get('package'), []).append(apk)
        rows, warnings = [], list(target.get('warnings', []))
        ota = target.get('kind') == 'ota' or any(s.get('kind') == 'ota' for s in scans)
        for source in scans:
            b.require(not source.get('device') or source['device'] == model['device'],
                      'Source firmware belongs to a different device; not auto-ported')
            warnings.extend(source.get('warnings', []))
            for apk in source.get('apks', []) if not ota else []:
                matches = originals.get(apk.get('package'), [])
                original = matches[0] if len(matches) == 1 else {}
                package = apk.get('package') or 'unknown'
                rows.append({'id': 'app' + str(len(rows) + 1), 'enabled': False, 'package': package,
                             'source_apk': apk['path'], 'source_sha256': apk['sha256'],
                             'target_apk': original.get('path'), 'target_sha256': original.get('sha256'),
                             'target_path': original.get('partition_path'),
                             'note': 'Wallet: separate validation only' if b.wallet(package) else
                                     'Select explicitly; check before build. Missing/duplicate target means reviewed recipe required.'})
        if ota:
            warnings.append('OTA payload not extracted; no APK components proposed. Extract firmware explicitly before analysis; no automatic extraction.')
        paths = [str(p) for p in sources]
        self.profile = {'schema': 1, 'id': profile_id, 'mode': 'apk-overlay', 'target': model,
                        'target_input': str(target_path), 'source_input': paths[0],
                        'wallet_policy': 'separate-validation-no-reset', 'hooks': [], 'components': rows,
                        'note': 'All proposed components start disabled. Unknown values are not compatibility approval.',
                        'warnings': warnings}
        if len(paths) > 1:
            self.profile['source_inputs'] = paths
        self.base = target_path.parent
        self.materials = None
        return self.profile

    def rows(self):
        self._lock_wallet()
        if self.profile and self.profile.get('mode') == 'selected-suite':
            import selected_suite as s
            rows = self.profile.get('components', [])
            b.require(isinstance(rows, list) and all(isinstance(c, dict) for c in rows)
                      and [c.get('id') for c in rows] == list(s.IDS), 'Invalid reviewed selection')
            return [{'id': key, 'title': title, 'package': '', 'enabled': c.get('enabled') is True,
                     'selectable': True, 'reason': '复用现有适配模块；小爱依赖智能助理'}
                    for c, key, title in zip(rows, s.IDS, s.TITLES)]
        if not self.profile or self.profile.get('mode') != 'apk-overlay':
            return []
        components = self.profile.get('components', [])
        ids = [c.get('id') for c in components if isinstance(c, dict)]
        rows = []
        for c in components:
            if not isinstance(c, dict):
                continue
            cid, package = c.get('id'), c.get('package')
            valid = (isinstance(cid, str) and b.TOKEN.fullmatch(cid) and ids.count(cid) == 1
                     and isinstance(package, str) and b.PACKAGE.fullmatch(package))
            locked = b.wallet(str(package))
            reason = ('Wallet/NFC/TSM/eSE requires separate validation; automatic selection forbidden.' if locked else
                      'Invalid or duplicate component id/package.' if not valid else c.get('note', 'Check before build.'))
            rows.append({'id': cid, 'title': package, 'package': package, 'enabled': c.get('enabled') is True,
                         'selectable': bool(valid and not locked), 'reason': reason})
        return rows

    def set_selected(self, ids: list):
        self._invalidate()
        self._lock_wallet()
        b.require(self.profile is not None and self.profile.get('mode') in ('apk-overlay', 'selected-suite'),
                  'Reviewed suites keep their existing phone selection UI')
        available = {r['id'] for r in self.rows() if r['selectable']}
        b.require(all(isinstance(cid, str) and cid in available for cid in ids),
                  'Unknown, invalid or wallet-locked component selection')
        if self.profile['mode'] == 'selected-suite' and 'xiaoai' in ids:
            ids = list(set(ids) | {'assistant'})
        for c in self.profile['components']:
            c['enabled'] = c.get('id') in ids

    def configure_materials(self, path):
        self._invalidate()
        self.materials = str(Path(path).expanduser().resolve()) if path else None

    def check(self):
        self._invalidate()
        try:
            self._lock_wallet()
            b.require(self.profile is not None, 'Load or analyse a profile first')
            fingerprint = self._fingerprint()
            profile = copy.deepcopy(self.profile)
            report = b.check_profile(profile, self.base, self.materials)
            b.require(self._fingerprint() == fingerprint, 'Profile changed during check; check again')
            if report.get('state') in PASSED:
                self._checked = fingerprint
            else:
                report['state'] = 'blocked'
                report.setdefault('errors', [e for c in report.get('components', []) for e in c.get('errors', [])]
                                  or ['Compatibility checks failed'])
            self.report = report
        except FAILURES as error:
            self.report = {'state': 'blocked', 'errors': [str(error)], 'components': []}
        return self.report

    def build(self, output, candidate=False):
        try:
            self._lock_wallet()
            fingerprint = self._fingerprint()
            b.require(self._checked is not None and self._checked == fingerprint
                      and self.report is not None and self.report.get('state') in PASSED,
                      'Run a successful check for the current selection and materials before building')
            profile = copy.deepcopy(self.profile)
            self._invalidate()
            # build() checks actual files again; the prior report is never passed in.
            report = b.build(profile, self.base, Path(output), materials=self.materials, candidate=candidate)
            b.require(report.get('state') in PASSED, 'Compatibility checks failed during build')
            b.require(self._fingerprint() == fingerprint, 'Profile changed during build; check again')
            self.report = report
            self._checked = fingerprint
            return report
        except FAILURES as error:
            self._checked = None
            self.report = {'state': 'blocked', 'errors': [str(error)], 'components': []}
            raise

    def save_profile(self, path):
        b.require(self.profile is not None, 'Load or analyse a profile first')
        self._lock_wallet()
        profile = copy.deepcopy(self.profile)
        for key in ('target_input', 'source_input', 'source_inputs'):
            value = profile.get(key)
            if value:
                profile[key] = ([str(b.path_of(p, self.base)) for p in value] if isinstance(value, list)
                                else str(b.path_of(value, self.base)))
        if profile.get('artifact'):
            # Registry matching requires the original artifact name. Carry its
            # directory separately so saving elsewhere preserves that identity.
            artifact_base = Path(self.materials) if self.materials else self.base
            profile['gui_materials'] = str(b.path_of(profile['artifact'], artifact_base).parent)
        for c in profile.get('components', []):
            for key in ('source_apk', 'target_apk'):
                if c.get(key):
                    c[key] = str(b.path_of(c[key], self.base))
        b.write_new(Path(path).expanduser().resolve(), profile)
        return profile
