"""Default-off calculator artifact transform; build capability is not publication authority.

Unlike the review transform this accepts only an already-public coupon artifact,
never removes noindex, and preserves every baseline response header and CSP.
No serving, analytics invocation, filesystem writes or source mutation.
"""
from scripts.coupon_calculator_candidate_bundle import (
    ANCHOR, OUTPUT_CSS, OUTPUT_JS, ROOT_ID, SOURCE_ASSETS, TAGS, _Markup,
    collect_assets,
)

CANONICAL = '<link rel="canonical" href="https://datalabx.jp/coupon-help">'
REVIEW_NOTE = '<p class="muted">入力は保存・外部送信しません。未公開の組込み候補です。</p>'
PUBLIC_NOTE = '<p class="muted">入力した数字は、このページ内での計算だけに使います。保存・外部送信はしません。</p>'
NOSCRIPT = '<noscript><p>この計算補助にはJavaScriptが必要です。上の計算例と公式案内で確かめてください。</p></noscript>\n'
INPUT_GROUP = '<div role="group" aria-label="計算する条件">'


def _replace_once(text, old, new):
    if text.count(old) != 1:
        raise ValueError('CALCULATOR_RELEASE_TEMPLATE_CHANGED')
    return text.replace(old, new, 1)


def _button_only_script(source):
    """Reuse exact arithmetic; avoid native form events without changing GA4 settings."""
    replacements = (
        ("const form=document.querySelector('#datalab-coupon-calculator form'),", 'const '),
        ("form.addEventListener('input',", "root.addEventListener('input',"),
        ("form.addEventListener('submit',",
         "root.querySelector('[data-calculator-action=\"calculate\"]').addEventListener('click',"),
        ("form.addEventListener('reset',()=>{clear();",
         "root.querySelector('[data-calculator-action=\"reset\"]').addEventListener('click',()=>{"
         "for(const key of keys.slice(1)){get(key).value=get(key).defaultValue;}"
         "scope.checked=scope.defaultChecked;clear();"),
    )
    for old, new in replacements:
        source = _replace_once(source, old, new)
    return source


def build_release_bundle(baseline, assets, *, enabled=False):
    if type(enabled) is not bool:
        raise ValueError('EXPLICIT_BOOLEAN_REQUIRED')
    result = dict(baseline)
    if not enabled:
        return result
    if set(assets) != set(SOURCE_ASSETS) or not {'coupon-help.html', '_headers'} <= set(baseline):
        raise ValueError('CALCULATOR_RELEASE_INPUTS_MISSING')
    if any(not isinstance(value, bytes) for value in (*baseline.values(), *assets.values())):
        raise ValueError('CALCULATOR_BYTES_REQUIRED')
    if any(not value.strip() for value in assets.values()):
        raise ValueError('CALCULATOR_EMPTY_ASSET')
    if any(name.startswith('coupon-calculator/') for name in baseline):
        raise ValueError('CALCULATOR_PRISTINE_BASELINE_REQUIRED')
    article = baseline['coupon-help.html'].decode('utf-8')
    fragment = assets['fragment'].decode('utf-8')
    if ROOT_ID in article or '/coupon-calculator/' in article:
        raise ValueError('CALCULATOR_PRISTINE_BASELINE_REQUIRED')
    if (article.count(CANONICAL) != 1 or '未公開' in article
            or article.count(ANCHOR) != 1 or article.count('</head>') != 1):
        raise ValueError('CALCULATOR_PUBLIC_ARTICLE_REQUIRED')
    original, widget = _Markup(), _Markup()
    original.feed(article)
    widget.feed(fragment)
    if any('noindex' in value.lower().replace(' ', '').split(',') for value in original.robots):
        raise ValueError('CALCULATOR_NOINDEX_ARTICLE_REFUSED')
    if (widget.active or widget.ids.count(ROOT_ID) != 1
            or len(widget.ids) != len(set(widget.ids))
            or set(original.ids) & set(widget.ids)
            or not set(widget.refs) <= set(widget.ids)):
        raise ValueError('CALCULATOR_FRAGMENT_INVALID')
    fragment = _replace_once(fragment, 'この試作は、', 'この計算補助は、')
    fragment = _replace_once(fragment, REVIEW_NOTE, PUBLIC_NOTE)
    fragment = _replace_once(fragment, '<form novalidate>', NOSCRIPT + INPUT_GROUP)
    fragment = _replace_once(fragment, '</form>', '</div>')
    fragment = _replace_once(fragment, 'type="submit"', 'type="button" data-calculator-action="calculate"')
    fragment = _replace_once(fragment, 'type="reset"', 'type="button" data-calculator-action="reset"')
    if '未公開' in fragment or 'この試作' in fragment:
        raise ValueError('CALCULATOR_REVIEW_COPY_REMAINING')
    article = _replace_once(article, ANCHOR, '    </section>\n' + fragment
                            + '    <p class="note"><strong>最後に確認するのは、')
    article = _replace_once(article, '</head>', TAGS + '</head>')
    result['coupon-help.html'] = article.encode('utf-8')
    result[OUTPUT_CSS] = assets['css']
    result[OUTPUT_JS] = _button_only_script(assets['js'].decode('utf-8')).encode('utf-8')
    return result
