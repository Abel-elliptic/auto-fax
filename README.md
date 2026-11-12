# auto-fax

Windows 11 PC から富士フイルムBI複合機 Apeos C2360 のダイレクトファクス機能を使い、
指定フォルダのPDF/JPEG/PNGを定期的にFAX送信するためのツール（開発中）。

- 設計: [docs/設計プラン.md](docs/設計プラン.md)
- 現在の段階: **Step 1 デモ（送信なし）**。FAX送信・定期実行はまだ実装していない。

## デモ（FAXは送信しない）

送信フォルダのファイルを、マスタ（ファイル名ごとの用紙・向き）と照らし合わせて判定し、
FAXドライバーへ渡す予定の白黒ページ画像をHTMLで表示する。

```
py -m pip install -r requirements-dev.txt
py samples\make_samples.py
py -m faxjob demo --input samples\送信 --master samples\master.csv --out out\preview --open
```

本番フォルダ構成（`C:\FAX\送信` など）で試す場合:

```
py -m faxjob demo --settings C:\FAX\設定\settings.toml --stable-check --open
```

- 設定例: `config/settings.example.toml`、マスタ例: `config/master.example.csv`
- マスタは UTF-8 のCSV（列: ファイル名,用紙サイズ,印刷方向,有効）。拡張子を除いたファイル名と完全一致で照合する。
- 同名で拡張子違いがあるときは PDF > JPEG > PNG の順に1つだけ送る。
- PDFは各ページのサイズ・向き（回転含む）に合わせてA4/A3・縦横を選ぶ（`pdf_layout = 'auto'`）。マスタと違うときは画面に注意を出す。画像はマスタの設定で出す。

## テスト

```
py -m pytest -q
```
