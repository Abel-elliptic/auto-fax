# auto-fax

Windows 11 PC から富士フイルムBI複合機 Apeos C2360 のダイレクトファクス機能を使い、
指定フォルダのPDF/JPEG/PNGを定期的にFAX送信するためのツール（開発中）。

- 設計: [docs/設計プラン.md](docs/設計プラン.md)
- 現在の段階: **Step 1 デモ（送信なし）** と **Step 2 用の出力確認（Microsoft Print to PDF）**。FAX送信・定期実行はまだ実装していない。
- ⚠ 宛先グループ「一斉2」は社外の複数社に届くため、テストでは使わないこと（詳細は設計書の「テスト時の安全ルール」）。

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

## 環境チェック（Windows、読み取りのみ）

プリンター・FAXドライバー・ポート・Python・スリープ解除タイマーの設定を一覧表示する。設定変更・印刷・送信はしない。
`C:\FAX\ログ` があれば結果をファイルにも保存する。

```
powershell -ExecutionPolicy Bypass -File tools\check_env.ps1
```

## Step 2: 用紙サイズ・向きの出力確認（Windows）

デモと同じページ画像を、ページごとに用紙（A4/A3）と向きを指定して「Microsoft Print to PDF」に出力する。
出力されたPDFを開き、用紙サイズ・向き・余白が想定どおりかを確認する。紙もFAXも出ない。

```
py -m pip install -r requirements.txt
py -m faxjob print --printer "Microsoft Print to PDF" --input samples\送信 --master samples\master.csv --output-dir out\print_test
```

- 結果は `out\print_test\` に元ファイルごとのPDFと `print_result.txt`（ページごとの要求用紙と、プリンターが実際に用意した用紙）として出る。
- FAXドライバーらしいプリンターを指定すると、`print.mode = 'test'` かつ `--allow-fax` の時以外は出力を拒否する。
- ⚠ 「FUJIFILM Apeos C2360」（ドライバー FF Apeos C2360）は**紙に印刷するプリンター**。指定すると紙が出る（FAXは出ない）ので、Step 2 では指定しない。

## FAXドライバーの調査（Windows、送信なし）

ダイレクトファクスドライバー（例：プリンター名「FUJIFILM Apeos C2360 FAX」）の対応用紙・解像度・既定値を読み、
A4/A3 × 縦/横 の指定をドライバーが受け入れるかを確認する。**印刷ジョブを作らないので、FAXは送信されない。**

```
py -m faxjob inspect --printer "FUJIFILM Apeos C2360 FAX"
```

結果は画面と `out\inspect.txt` に出る。

## Step 3: テスト宛先へのFAX送信（Windows）

テスト宛先は Brother のFAXテストサービス（052-824-4773）を使う。発信者番号を通知しないと返信されないため、**先頭に 186 を付けた `1860528244773`** を宛先にする。
送るのはサンプル原稿だけ（業務書類はメーカーに送らない）。**宛先グループ「一斉2」は絶対に使わない。**

**3a. ドライバーだけで手動確認（プログラム不要）**
1. 「FUJIFILM Apeos C2360 FAX」の印刷設定 → ファクス送信 → 宛先の一覧に `1860528244773` を1件だけ追加 → OK
2. メモ帳で1行書いて「FUJIFILM Apeos C2360 FAX」へ印刷 → 宛先確認などのダイアログが出るか記録（出たら画面を撮る）
3. 本体の通信管理レポート／ジョブ情報で送信結果、返信FAXの受信を確認
4. 終わったら印刷設定の宛先の一覧から `1860528244773` を削除する（残すと以後の印刷がすべてテストサービスへ送られる）

**3b. プログラムから1ファイル送信**（3a で宛先を設定した状態で行う）

```
py -m faxjob print --settings config\settings.test.toml --allow-fax --only 請求書.pdf --input samples\送信 --master samples\master.csv
```

- 安全装置：`print.mode = 'test'` と `--allow-fax` が両方ある時だけFAXへ出力。`--only` で1ファイル必須、3ページまで（`--max-pages`）。
- 送る直前にファイル名・ページ数・用紙を表示し、キーボードで「送信」と入力した時だけ送る。
- プログラムが確認できるのは「FAXドライバーへの投入」まで。実際に送れたかは通信管理レポートで確認する。

## 送信画面の自動操作（Windows）

FAXドライバーへ出力すると「ファクス送信の設定／確認」画面が出る。プログラムがこの画面を操作して宛先を設定し、「送信開始」を押す。
**座標は使わない**：部品は ID で特定し、ボタンは WM_COMMAND(BN_CLICKED)、文字は EM_REPLACESEL、リストは LVM_* メッセージで操作する。
操作のたびに画面を読み直して確認し、想定外なら「送信中止」を押して止める（印刷設定の既定宛先が残っている、宛先が2件以上、時刻指定がオン、など）。

**① リハーサル（送信しない）**：宛先の設定まで自動で行い、最後は「送信中止」を押す

```
py -m faxjob print --settings config\settings.test.toml --allow-fax --rehearsal --only 請求書.pdf --input samples\送信 --master samples\master.csv
```

本番宛先「一斉2」の選択だけを確かめる（宛先表で「一斉2」(Group) を完全一致で選ぶ。「一斉」とは区別。送信中止で終わる）：

```
py -m faxjob print --settings config\settings.group-rehearsal.toml --allow-fax --rehearsal --only 請求書.pdf --input samples\送信 --master samples\master.csv
```

**② テスト送信**：Brother テストサービス（`1860528244773`）へ1ファイル送る（キーボードで「送信」と入力した時だけ）

```
py -m faxjob print --settings config\settings.test.toml --allow-fax --only 請求書.pdf --input samples\送信 --master samples\master.csv
```

- 事前に FAXドライバーの印刷設定の「宛先の一覧」を**空**にしておく（入っていると安全のため中止する）。
- 押す直前の画面の画像は `C:\FAX\ログ\fax_gui\` に保存される。
- 本番（`mode='production'`）での送信は Step 8 まで無効（`--rehearsal` のみ可）。

## 送信時のFAX宛先画面の構造を読む（Windows、送信なし）

FAXドライバーへ印刷すると宛先を選ぶ画面が出る（本体宛先表の「一斉2」はこの画面でしか選べない）。
この画面を自動操作できるか判断するため、部品（ボタン・リスト・入力欄）の種類・名前・ID を読み取る。**クリック・入力は一切しないので送信されない。**

1. FAXドライバーの印刷設定の「宛先の一覧」を**空にしておく**
2. メモ帳で1行書き、「FUJIFILM Apeos C2360 FAX」へ印刷 → 宛先の画面が出たら**何も押さない**
3. 別の PowerShell で（最新のコードと pywinauto を入れてから）

```
py -m pip install -r requirements.txt
py -m faxjob uidump
```

4. 続けて、その画面の「宛先表から追加」を押し、宛先表（「一斉2」が見える状態）が出たら**何も選ばず**もう一度 `py -m faxjob uidump`
5. 2つの結果（`out\uidump_日時.txt` と画面の画像）を共有したら、両方の画面を「キャンセル」で閉じる

## 紙のレポートを止めるには

- 通信管理レポート／未送信レポートの自動出力は**複合機本体の設定**（Internet Services の［アプリ］→［ファクス］→［通信管理レポート］［未送信レポート］）。機械管理者ログインが必要なため、管理担当・販売店に「自動出力しない」への変更を依頼する。PC・このプログラムからは止められない。
- FAXドライバーの印刷設定 →「詳細設定」→「送信レポート」を「出力しない」にする（自分で変更可）。
- 紙を止めた分、送信結果は簡易ログ転送・ジョブ履歴・ジョブ終了メール通知のいずれかで確認する（いずれも本体側の管理者設定が必要）。

## スリープからの自動復帰テスト（Windows）

このPCには従来のスリープ（S3）が無く、「モダンスタンバイ」と「休止状態」のみ。
モダンスタンバイ中にタスクスケジューラで起きるかは公式に確認できないため、実際に試す。FAX送信や印刷はしない。

**事前準備（電源設定・手動）**：スリープ解除タイマーを有効にする
1. スタートメニューで「電源プランの編集」を検索して開く →「詳細な電源設定の変更」
2. 「スリープ」→「スリープ解除タイマーの許可」→「電源に接続」を **有効** にして OK

**テスト**（電源ケーブルはつないだまま）

```
powershell -ExecutionPolicy Bypass -File tools\wake_test.ps1 -Register -Minutes 10
```

表示された予定時刻より前に、スタート → 電源 → スリープ。予定時刻を数分過ぎるまで触らない。その後PCを起こして確認：

```
powershell -ExecutionPolicy Bypass -File tools\wake_test.ps1 -Check
```

終わったらテスト用タスクを削除：

```
powershell -ExecutionPolicy Bypass -File tools\wake_test.ps1 -Remove
```

- テスト用タスク（`\FAX\FAX_wake_test`）がすることは `C:\FAX\ログ\wake_test.log` に時刻を1行書くことだけ。
- 起きなかった場合の代替案：スリープさせず画面だけ消す運用（電源接続時のスリープ＝なし）、または休止状態からの復帰を試す。

## テスト

```
py -m pytest -q
```
