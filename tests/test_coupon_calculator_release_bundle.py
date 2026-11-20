"""Pure public-artifact transform tests, never served or transmitted."""
from pathlib import Path
import re
import json
import shutil
import subprocess
import unittest

from scripts.coupon_help_candidate_bundle import REQUIRED_INPUTS, build_candidate_bundle
from scripts.coupon_help_public_release import build_public_release
from scripts.coupon_calculator_release_bundle import (
    build_release_bundle, collect_assets, ANCHOR, CANONICAL, OUTPUT_CSS,
    OUTPUT_JS, TAGS, ROOT_ID, REVIEW_NOTE, PUBLIC_NOTE, NOSCRIPT,
)

ROOT = Path(__file__).resolve().parents[1]


class CalculatorReleaseTests(unittest.TestCase):
    def setUp(self):
        self.sources = {name: (ROOT / name).read_bytes() for name in REQUIRED_INPUTS}
        self.baseline = build_public_release(self.sources)
        self.baseline['_headers'] = (ROOT / '_headers').read_bytes()
        self.assets = collect_assets(ROOT)

    def build(self, baseline=None, assets=None):
        return build_release_bundle(self.baseline if baseline is None else baseline,
                                    self.assets if assets is None else assets, enabled=True)

    def test_default_disabled_is_exact_and_does_not_require_assets(self):
        self.assertEqual(build_release_bundle(self.baseline, {}), self.baseline)
        for enabled in [0, 1, None, 'true']:
            with self.assertRaises(ValueError):build_release_bundle(self.baseline, {}, enabled=enabled)

    def test_only_article_and_two_new_assets_change(self):
        before, assets_before = dict(self.baseline), dict(self.assets)
        result = self.build()
        self.assertEqual(set(result) - set(before), {OUTPUT_CSS, OUTPUT_JS})
        self.assertEqual({n for n in before if result[n] != before[n]}, {'coupon-help.html'})
        self.assertEqual(self.baseline, before)
        self.assertEqual(self.assets, assets_before)
        self.assertEqual(self.build(), result)
        self.assertEqual(result['_headers'], before['_headers'])

    def test_existing_content_metadata_links_and_csp_restore_exactly(self):
        old = self.baseline['coupon-help.html'].decode('utf-8')
        article = self.build()['coupon-help.html'].decode('utf-8')
        self.assertEqual(article.count(TAGS), 1)
        self.assertEqual(article.count(CANONICAL), 1)
        self.assertEqual(article.count('<h1>'), 1)
        self.assertEqual(re.findall(r'href="(?!/coupon-calculator/)[^"]*"', article),
                         re.findall(r'href="[^"]*"', old))
        start = article.index('<section id="' + ROOT_ID + '"')
        end = article.index('    <p class="note"><strong>最後に確認するのは、', start)
        restored = (article[:start] + article[end:]).replace(TAGS, '', 1)
        self.assertEqual(restored, old)
        self.assertNotIn('noindex', article)

    def test_reader_copy_no_tracking_claim_and_noscript(self):
        article = self.build()['coupon-help.html'].decode('utf-8')
        self.assertNotIn(REVIEW_NOTE, article)
        self.assertIn(PUBLIC_NOTE, article)
        self.assertIn(NOSCRIPT, article)
        self.assertNotIn('この試作', article)
        self.assertNotIn('未公開', article)
        self.assertIn('FANZAブックス、別キャンペーン', article)
        self.assertIn('対象になるかを自動で判断しません', article)
        self.assertIn('/analytics-consent.js', article)
        self.assertNotIn('解析はありません', article)
        marker = b"const root=document.getElementById"
        self.assertEqual(self.build()[OUTPUT_JS].split(marker)[0], self.assets['js'].split(marker)[0])
        self.assertNotIn('<form', article)
        self.assertNotIn('type="submit"', article)
        self.assertNotIn('type="reset"', article)

    def test_review_article_is_never_promoted(self):
        review = build_candidate_bundle(self.sources)
        with self.assertRaises(ValueError):self.build(review)
        article = self.baseline['coupon-help.html']
        for marker in (b'<meta name="robots" content="noindex,nofollow">',
                       b'<meta name="robots" content="NOINDEX, follow">'):
            with self.assertRaises(ValueError):
                self.build(dict(self.baseline, **{'coupon-help.html':article.replace(b'</head>', marker+b'</head>')}))

    def test_missing_wrong_or_duplicate_canonical_rejected(self):
        article = self.baseline['coupon-help.html']
        for replacement in (b'', CANONICAL.replace('/coupon-help', '/other').encode(), CANONICAL.encode()*2):
            with self.assertRaises(ValueError):
                self.build(dict(self.baseline, **{'coupon-help.html':article.replace(CANONICAL.encode(), replacement)}))

    def test_anchor_drift_and_repeat_integration_rejected(self):
        article = self.baseline['coupon-help.html']
        for replacement in (b'', ANCHOR.encode()*2):
            with self.assertRaises(ValueError):
                self.build(dict(self.baseline, **{'coupon-help.html':article.replace(ANCHOR.encode(), replacement)}))
        with self.assertRaises(ValueError):self.build(self.build())

    def test_input_set_types_empty_and_utf8_fail_closed(self):
        for assets in ({}, {**self.assets, 'extra':b'bad'}, {**self.assets, 'js':'not-bytes'},
                       {**self.assets, 'css':b''}, {**self.assets, 'fragment':b'\xff'}):
            with self.assertRaises((ValueError, UnicodeError)):self.build(assets=assets)
        with self.assertRaises(ValueError):self.build({})

    def test_fragment_ids_references_and_active_inputs_rejected(self):
        for addition in (b'<input id="missing">', b'<label for="absent">bad</label>',
                         b'<script>bad</script>', b'<a href="https://example.invalid">bad</a>'):
            with self.assertRaises(ValueError):self.build(assets={**self.assets, 'fragment':self.assets['fragment']+addition})

    def test_review_copy_and_form_template_drift_rejected(self):
        fragment = self.assets['fragment']
        for old, new in ((REVIEW_NOTE.encode(), b''), ('この試作は、'.encode(), b''),
                         (b'<form novalidate>', b'<form>')):
            with self.assertRaises(ValueError):self.build(assets={**self.assets, 'fragment':fragment.replace(old,new)})

    def test_javascript_adapter_drift_rejected_without_mutating_source(self):
        source = self.assets['js']
        for old in (b"form.addEventListener('submit',", b"form.addEventListener('reset',()=>{clear();"):
            with self.assertRaises(ValueError):self.build(assets={**self.assets, 'js':source.replace(old,b'changed')})
        self.assertEqual(source,self.assets['js'])

    def test_public_button_ui_has_no_native_form_or_analytics_calls(self):
        bundle = self.build()
        html = bundle['coupon-help.html'].decode('utf-8')
        script = bundle[OUTPUT_JS].decode('utf-8')
        for forbidden in ('fetch(', 'sendBeacon(', 'gtag(', 'dispatchEvent(', 'localStorage',
                          'sessionStorage', 'document.cookie', "addEventListener('submit'",
                          "addEventListener('reset'", 'document.querySelector('):
            self.assertNotIn(forbidden,script)
        node = shutil.which('node')
        self.assertIsNotNone(node,'Node required for public-button runtime verification')
        result = subprocess.run([node,'-e',BUTTON_HARNESS],
                                input=json.dumps({'html':html,'script':script}),
                                capture_output=True,text=True,timeout=30,check=False)
        self.assertEqual(result.returncode,0,result.stderr)
        self.assertIn('PASS',result.stdout)


BUTTON_HARNESS = r'''
const fs=require('node:fs'),vm=require('node:vm'),assert=require('node:assert/strict');
const {html,script}=JSON.parse(fs.readFileSync(0,'utf8'));
assert.equal(/<form\b/i.test(html),false);
let focused,checks=0;
const ids=[...html.matchAll(/\bid="([^"]+)"/g)].map(m=>m[1]);
assert.equal(new Set(ids).size,ids.length);
const elements=Object.fromEntries(ids.map(id=>[id,{value:'',defaultValue:'',checked:false,defaultChecked:false,
 hidden:true,textContent:'',attrs:{},setAttribute(k,v){this.attrs[k]=v},removeAttribute(k){delete this.attrs[k]},focus(){focused=id}}]));
for(const tag of html.match(/<input\b[^>]*>/g)||[]){
 const id=tag.match(/\bid="([^"]+)"/)[1],value=tag.match(/\bvalue="([^"]*)"/)?.[1]||'';
 elements[id].value=elements[id].defaultValue=value;
}
const handlers={},buttons={};
for(const action of ['calculate','reset'])buttons[action]={addEventListener(type,fn){assert.equal(type,'click');assert.equal(handlers[action],undefined);handlers[action]=fn}};
const root=elements['datalab-coupon-calculator'];
root.addEventListener=(type,fn)=>{assert.equal(type,'input');handlers.input=fn};
root.querySelector=selector=>{const id=selector.match(/^\[id="([^"]+)"\]$/)?.[1];if(id){assert.ok(elements[id]);return elements[id]}
 const action=selector.match(/^\[data-calculator-action="([^"]+)"\]$/)?.[1];assert.ok(buttons[action]);return buttons[action]};
const context=vm.createContext({document:{getElementById(id){assert.equal(id,'datalab-coupon-calculator');return root}},fetch(){throw Error('NETWORK_FORBIDDEN')}});
const globals=Object.keys(context);vm.runInContext(script,context);assert.deepEqual(Object.keys(context),globals);
const get=id=>elements['calc-'+id];
function calculate(t,d,p,scope=true){get('total').value=t;get('discount').value=d;get('points').value=p;get('scope').checked=scope;handlers.input();handlers.calculate({preventDefault(){}});checks++;
 for(const e of Object.values(elements))for(const attr of ['aria-describedby','aria-labelledby'])for(const id of (e.attrs[attr]||'').split(/\s+/).filter(Boolean))assert.ok(elements[id]);
 return !get('result').hidden;}
assert.equal(calculate('2000','500','200',false),false);assert.equal(focused,'calc-scope');
assert.equal(calculate('2000','500','200'),true);assert.equal(get('payment-result').textContent,'1,500円');assert.equal(get('points-result').textContent,'150ポイント');
get('discount').value='3000';handlers.input();assert.equal(get('result').hidden,true);
assert.equal(calculate('2000','3000','200'),false);assert.equal(focused,'calc-discount');
for(const bad of ['', '-1','1.5','1e3','２０００','2,000','10000000','<script>'])for(let i=0;i<3;i++){let values=['2000','500','200'];values[i]=bad;assert.equal(calculate(...values),false)}
assert.equal(calculate('0','0','0'),false);
for(let t=1;t<=50;t++){let previous=138n;for(let d=0;d<=t;d++){
 assert.equal(calculate(String(t),String(d),'137'),true);
 const parse=id=>BigInt(get(id).textContent.replace(/[^0-9]/g,''));
 const payment=parse('payment-result'),awarded=parse('points-result');
 assert.equal(payment+BigInt(d),BigInt(t));assert.equal(awarded+parse('difference-result'),137n);
 assert.ok(awarded>=0n&&awarded<=previous);assert.ok(awarded*BigInt(t)<=137n*payment);assert.ok((awarded+1n)*BigInt(t)>137n*payment);previous=awarded;
}}
assert.equal(calculate('9999999','1','9999999'),true);
handlers.reset();assert.equal(get('scope').checked,false);assert.equal(get('total').value,'2000');assert.equal(get('discount').value,'500');assert.equal(get('points').value,'200');assert.equal(get('result').hidden,true);assert.equal(get('discount-error').textContent,'');
assert.deepEqual(Object.keys(handlers).sort(),['calculate','input','reset']);
vm.runInNewContext(script,{document:{getElementById(){return null}}});
console.log('PASS '+checks+' public-button calculations; no form, submit, reset event or network capability used');
'''


if __name__ == '__main__':unittest.main()
