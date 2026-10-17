"""Offline build/rollback and VM consent tests; never serve generated artifacts."""
from contextlib import redirect_stdout, redirect_stderr
from io import StringIO
import json
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest

from scripts.article_navigation_local_build import (
    ASSETS, PAGES, ROOT, TAG, CONSENT_NEW, build_local_bundle, collect_local_bundle, main)
from scripts.books_device_local_build import collect_rehearsal


class ArticleNavigationLocalBuildTests(unittest.TestCase):
    def test_default_off_and_explicit_rollback_match_baseline(self):
        baseline = collect_rehearsal('release')
        self.assertEqual(collect_local_bundle(), baseline)
        self.assertEqual(collect_local_bundle(enabled=False), baseline)

    def test_opt_in_changes_only_three_pages_consent_and_four_assets(self):
        baseline = collect_rehearsal('release')
        before = dict(baseline)
        enabled = collect_local_bundle(enabled=True)
        self.assertEqual(set(enabled) - set(baseline), set(ASSETS))
        self.assertEqual({name for name in baseline if baseline[name] != enabled[name]},
                         set(PAGES) | {'analytics-consent.js'})
        self.assertEqual(baseline, before)
        for name in PAGES:
            self.assertEqual(enabled[name].count(TAG.encode()), 1)
        self.assertEqual(enabled['books-device-check.html'].count(
            b'data-datalab-article-navigation="true"'), 1)
        self.assertIn(CONSENT_NEW.encode(), enabled['analytics-consent.js'])
        self.assertEqual(enabled['_headers'], baseline['_headers'])
        self.assertEqual(enabled['sitemap.xml'], baseline['sitemap.xml'])
        self.assertEqual(enabled['items/discovery.js'], baseline['items/discovery.js'])

    def test_input_drift_duplicate_build_and_non_boolean_rejected(self):
        baseline = collect_rehearsal('release')
        enabled = collect_local_bundle(enabled=True)
        assets = {name: enabled[name] for name in ASSETS}
        for value in (None, 1, 'true'):
            with self.subTest(value=value), self.assertRaises(ValueError):
                build_local_bundle(baseline, assets, enabled=value)
        with self.assertRaises(ValueError):
            build_local_bundle(enabled, assets, enabled=True)
        with self.assertRaises(ValueError):
            build_local_bundle(baseline, {}, enabled=True)
        for name in (*PAGES, 'analytics-consent.js'):
            changed = dict(baseline)
            changed[name] = b'changed'
            with self.subTest(name=name), self.assertRaises(ValueError):
                build_local_bundle(changed, assets, enabled=True)

    def test_cli_default_on_and_off_use_distinct_new_temp_outputs(self):
        with tempfile.TemporaryDirectory(prefix='navigation-build-test-') as folder:
            parent = Path(folder)
            with redirect_stdout(StringIO()), redirect_stderr(StringIO()):
                for flag, name in ((None, 'default'), ('--with-article-navigation', 'on'),
                                   ('--without-article-navigation', 'off')):
                    args = ['--output', str(parent / name)]
                    if flag:
                        args.append(flag)
                    self.assertEqual(main(args), 0)
                self.assertEqual(main(['--output', str(parent / 'on')]), 1)
                self.assertEqual(main(['--output', str(ROOT / 'dist')]), 1)
                dry = parent / 'dry'
                self.assertEqual(main(['--with-article-navigation', '--dry-run',
                                       '--output', str(dry)]), 0)
                self.assertFalse(dry.exists())
            def output(name):
                return {p.relative_to(parent / name).as_posix(): p.read_bytes()
                        for p in (parent / name).rglob('*') if p.is_file()}
            self.assertEqual(output('default'), output('off'))
            self.assertEqual(len(output('on')), len(output('off')) + 4)

    def test_generated_consent_uses_existing_offline_runtime_harness(self):
        node = shutil.which('node')
        if node is None:
            self.skipTest('Node.js is not available')
        consent = collect_local_bundle(enabled=True)['analytics-consent.js'].decode('utf-8')
        program = r'''
const fs = require('fs'); const path = require('path'); const vm = require('vm');
const original = fs.readFileSync('tests/analytics_consent_runtime_harness.js', 'utf8');
const start = original.indexOf('const script = fs.readFileSync(');
const end = original.indexOf('\n);', start) + 4;
if (start < 0 || end < 4) throw Error('HARNESS_TEMPLATE_CHANGED');
const modified = original.slice(0, start) + 'const script = ' + process.argv[1] + ';' + original.slice(end);
const extra = `
const x = scenario(null);
assert(x.window.dataLabAnalytics.readConsent() === null, 'unknown consent');
x.bodyChildren[0].querySelector('.analytics-consent__accept').trigger('click');
assert(x.window.dataLabAnalytics.readConsent() === 'granted', 'grant missing');
x.bodyChildren[0].querySelector('.analytics-consent__deny').trigger('click');
assert(x.window.dataLabAnalytics.readConsent() === 'denied', 'withdrawal missing');
`;
vm.runInNewContext(modified + extra, {require, __dirname: path.resolve('tests'), console, URLSearchParams});
'''
        result = subprocess.run([node, '-e', program, json.dumps(consent)], cwd=ROOT,
                                capture_output=True, text=True, timeout=30, check=False)
        self.assertEqual(result.returncode, 0, result.stderr)

    def test_bootstrap_mock_composition_without_network(self):
        node = shutil.which('node')
        if node is None:
            self.skipTest('Node.js is not available')
        program = r'''
import fs from 'node:fs'; import vm from 'node:vm'; import assert from 'node:assert/strict';
import {installArticleNavigationAdapter} from './runtime-candidates/article-navigation-dom-adapter-candidate.mjs';
import {createArticleNavigationRecorder} from './runtime-candidates/article-navigation-ga4-bridge-candidate.mjs';
const source = fs.readFileSync('runtime-candidates/article-navigation-bootstrap-candidate.mjs', 'utf8')
  .replace(/^import .*;$/gm, '').replace('export function', 'function');
const sandbox = {installArticleNavigationAdapter, createArticleNavigationRecorder};
vm.runInNewContext(source, sandbox);
const listeners = new Set(); const calls = [];
const root = {contains: () => true, addEventListener: (_, f) => listeners.add(f),
              removeEventListener: (_, f) => listeners.delete(f)};
let choice = null;
const page = {location: {pathname: '/books-device-check'},
              dataLabAnalytics: {readConsent: () => choice},
              gtag: (...args) => calls.push(args)};
const link = {closest: key => key === 'a[href]' ? link : key === 'main' ? {} : null,
              hasAttribute: () => false,
              getAttribute: key => key === 'href' ? '/column-price' :
                key === 'data-datalab-article-navigation' ? 'true' : null};
const click = () => {for (const f of listeners) f({button: 0, target: link});};
const stop = sandbox.installNavigationBootstrap(page, root);
assert.equal(typeof stop, 'function'); assert.equal(calls.length, 0);
click(); assert.equal(calls.length, 0);
choice = 'granted'; click(); assert.equal(calls.length, 1);
assert.equal(calls[0][2].navigation_route, 'device_to_price');
const originalClosest = link.closest;
const originalAttribute = link.getAttribute;
link.getAttribute = key => key === 'href' ? '/column-price' : null;
click(); assert.equal(calls.length, 1); // unmarked main link is excluded
link.getAttribute = originalAttribute;
link.closest = key => key === 'footer' ? {} : originalClosest(key);
click(); assert.equal(calls.length, 1); // even marked footer link is excluded
link.closest = key => key === 'main' ? null : originalClosest(key);
click(); assert.equal(calls.length, 1); // must be inside main
link.closest = originalClosest;
choice = 'denied'; click(); assert.equal(calls.length, 1);
choice = 'granted'; page.gtag = null; click(); assert.equal(calls.length, 1);
stop(); assert.equal(listeners.size, 0);
assert.equal(sandbox.installNavigationBootstrap({location: {pathname: '/items/'}}, root), null);
'''
        result = subprocess.run([node, '--input-type=module', '-e', program], cwd=ROOT,
                                capture_output=True, text=True, timeout=30, check=False)
        self.assertEqual(result.returncode, 0, result.stderr)

    def test_ordinary_builder_and_sources_remain_unconnected(self):
        for path in ('scripts/build-static-site.py', 'analytics-consent.js',
                     'column-price.html', 'scripts/books_device_release_bundle.py'):
            source = (ROOT / path).read_text(encoding='utf-8')
            self.assertNotIn('/article-navigation/bootstrap.mjs', source)
            self.assertNotIn(CONSENT_NEW, source)


if __name__ == '__main__':
    unittest.main()
