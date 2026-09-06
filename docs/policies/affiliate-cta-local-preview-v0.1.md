# DATA LAB Affiliate CTA Local Preview v0.1

## Purpose

`scripts/affiliate_cta_local_preview.py` は、Affiliate CTA Presentation v0.1の許可表示を
実ブラウザで確認するため、OSの一時ディレクトリ内へ一枚のHTMLを生成する。

実商品、実アフィリエイトURL、DMM/FANZA API、DB、credential、本番設定は使用しない。
リンク先は予約済みダミードメイン `example.invalid` のみで、開かないことが正常である。

## Built-in validation

生成前に、許可fixtureが `CTA_READY`、未許可fixtureがCTA・PR文言とも完全非表示であることを確認する。
HTMLには次を必須とする。

- `noindex,nofollow`
- ローカル・非公開・ダミーリンク表示
- CTA直前のPR/アフィリエイト表示
- 外部サイト表記
- `noopener noreferrer sponsored`
- 430px以下のmobile layout
- 48px以上のCTA touch target

## Isolation

出力先はOS一時ディレクトリ配下の新規ディレクトリだけを許可する。
既存パス、temp root自体、repository配下、symlink parentはfail-closedとする。
safe resultには出力パスやダミーURLを含めない。

## Windows preview

PowerShellで新規出力先を作成する値だけを設定する。

```powershell
$CtaPreviewDir = Join-Path $env:TEMP ("data-lab-affiliate-cta-preview-" + [guid]::NewGuid().ToString("N"))
```

生成する。

```powershell
python .\scripts\affiliate_cta_local_preview.py --output $CtaPreviewDir
```

生成成功後、そのディレクトリでローカルHTTP serverを起動する。

```powershell
python -m http.server 8766 --bind 127.0.0.1 --directory $CtaPreviewDir
```

ブラウザで `http://127.0.0.1:8766/` を開く。確認後はserverを停止する。
この手順は公開・配備を行わず、Release GateやIssue #66を解除しない。
