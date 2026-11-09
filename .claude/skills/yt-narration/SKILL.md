---
name: yt-narration
description: >
  YouTube台本（script.json）から、AIナレーション音声（シーンごとのwav・全体のwav/mp3・タイミング表）を作るスキル。
  標準はパソコン内蔵の声（Mac の say / Windows の音声合成）で、回数制限なしに最後まで作れる。
  声を良くしたいときだけ、任意で Gemini TTS（GEMINI_API_KEY と --engine gemini）を使う。
  「ナレーションを作って」「台本を読み上げて」「AI音声にして」「動画の声を作って」「ナレーション音声」と言われたときに使う。
  Use when the user asks to generate narration / voice-over / TTS audio for a YouTube script, or says "make the narration", "text to speech", "AI voice".
---

# yt-narration（AIナレーションのスキル）

`yt-script` で作った `script.json` を読み上げて、音声ファイルにします。
公開・投稿・送信はしません。

**標準の音声（パソコン内蔵の声）だけで、最後まで作れます。** 何も指定しなければ内蔵の声を使います。
Gemini TTS は「声を良くしたいときに使う」任意の追加です。ご本人が選んだときだけ使ってください。

---

## 最初に1回だけ（準備の確認）

順に確かめ、無いものだけ入れてもらいます。

```
1 ffmpeg       ffmpeg -version が動くか
               Mac: brew install ffmpeg / Windows: winget install Gyan.FFmpeg
               入れたら、ターミナルを開き直す
2 Python       python3 --version（Windows は python --version）が 3.8 以上か
3 Gemini のキー（任意・声を良くしたいときだけ）  無くても最後まで作れます
               Google AI Studio でキーを作り、ご本人に環境変数 GEMINI_API_KEY に入れてもらう
               Mac: ~/.zshrc に export GEMINI_API_KEY="..." を書いてターミナルを開き直す
               Windows: setx GEMINI_API_KEY "..." を実行してターミナルを開き直す
```

**キーの中身を画面に出さないでください。** 確かめるときは「入っているか」だけ見ます。

```
Mac:     zsh -ic 'test -n "$GEMINI_API_KEY" && echo 入っています || echo 入っていません'
Windows: powershell -Command "if($env:GEMINI_API_KEY){'入っています'}else{'入っていません'}"
```

Mac で日本語の声が無いときは、システム設定 > アクセシビリティ > 読み上げコンテンツ > システムの声 で「Kyoko」などを追加します。

Mac で ~/.zshrc にキーを書いた場合、Claude Code から実行するときは `zsh -ic '<コマンド>'` で包むとキーが読み込まれます。

---

## 作り方

```
python3 <このスキルのフォルダ>/scripts/narrate.py <作業フォルダ>/script.json --out <作業フォルダ>/narration --mp3
```

- パスは全部**絶対パス**で書く。
- 何もつけない … **標準。パソコン内蔵の声**（Mac: Kyoko / Windows: Haruka など）。回数制限なし。
- `--os-voice Kyoko` … 内蔵の声の名前を指定（省略時は日本語の声を自動で選ぶ）
- `--rate 180` … 内蔵の声の速さ（Mac: 1分の語数 / Windows: -10〜10）
- `--only s03,s05` … そのシーンだけ作り直す（台本を一部直したとき）
- `--gap 0.5` … シーンの間の無音（秒）

### 任意: Gemini TTS で声を良くする

ご本人が「声を良くしたい」と選び、GEMINI_API_KEY が入っているときだけ使います。

```
python3 <このスキルのフォルダ>/scripts/narrate.py <作業フォルダ>/script.json --out <作業フォルダ>/narration --mp3 --engine gemini
```

- `--voice Kore` … Gemini の声の名前（初期値 Kore。ほかに Puck, Charon, Aoede など）
- キーが無い・途中で上限に達したときは、声がちぐはぐにならないよう**全シーンを内蔵の声で作り直して**最後まで仕上げます。
- `--strict` をつけると、切り替えずに止まります（翌日に同じコマンドで続きから作れます）。
- モデルは `gemini-2.5-flash-preview-tts`（無ければ `gemini-2.5-flash-tts`、それも無ければ使える TTS モデルを自動で探す）。
  新しいモデルを使いたいときは環境変数 `GEMINI_TTS_MODEL` に名前を入れる（カンマ区切りで複数可）。

### Gemini の回数制限について

- Gemini の無料枠は「1分に数回」「1日に数回〜十数回」程度の上限があります（時期で変わる）。
- 1シーン = 1回の呼び出しです。8〜10分の動画（20〜30シーン）は、無料枠だと1日で作り切れないことがあります。
- 混雑・1分の上限（HTTP 429/503）は、自動で待って再試行します（最大6回、だんだん待ち時間をのばす）。
- 1日の上限に達したら、待っても回復しないので、すぐ内蔵の声に切り替えます（`--strict` のときは止まる）。
- 作り終わったシーンは保存され、次に実行したとき作り直しません。翌日に続きから作れます。

### 読み間違いを減らすコツ

- 数字・英字は、台本の `yomi` にひらがなで書く（3つ → みっつ、AI → えーあい）。
- 助詞の「は」「へ」は、`yomi` では発音どおり「わ」「え」と書く（例：最終判断は → さいしゅうはんだんわ）。ひらがなの「は」のままだと「ハ」と読まれることがあります。
- ひらがなにすると区切りがおかしくなる言葉（例：公式情報）は、`yomi` でも漢字のまま残す。
- できた音声は必ず耳で聞いて確かめる（AIは音を聞けません）。
- 区切りたい所に「、」を足すと、間ができます。
- 「明るく読んで」などの指示を台本に書かない（**指示の文まで読み上げられます**）。

---

## できあがったら確かめること

```
1 narration.wav があるか（ls / dir）
2 表示された「合計 ○○秒」がだいたい想定どおりか
3 1シーンだけでいいので、ご本人に聞いてもらう（読み間違い・変な間）
```

読み間違いがあれば `yomi` を直して `--only <そのシーン>` で作り直します。

## 渡す

```
できたもの   /絶対パス/narration/narration.wav（mp3 も）
使った声     os:Darwin:Kyoko（標準）または gemini:…:Kore
長さ         合計 ○○秒
次の一歩     「動画にして」と言ってください（yt-video）
```

## やってはいけないこと

- API キーを画面・ファイル・チャットに出さない
- 実在の人の声をまねさせない（声優・有名人の名前を指定しない）
- 音声を勝手にアップロード・送信しない
