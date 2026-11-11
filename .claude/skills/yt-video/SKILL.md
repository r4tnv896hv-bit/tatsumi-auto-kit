---
name: yt-video
description: >
  動画を作る・編集するスキル（2つのモード）。
  A 台本（script.json）とナレーション（yt-narration の出力）から、顔出しなしの解説動画（1920x1080・字幕焼き込み・mp4）を ffmpeg で作る。
  B 自分で撮った素材を、編集指示書（edit.json）どおりに カット・無音詰め（ジェットカット）・字幕・BGM・つなぎ・書き出し する。
  どちらも最後に予定と実物の長さを測って照合し、メタデータを消す。投稿・アップロードはしない。
  「動画にして」「動画を書き出して」「スライド動画を作って」「字幕つきの動画にして」「動画を編集して」「無音をカットして」
  「ジェットカットして」「字幕とBGMをつけて」「動画をつないで」と言われたときに使う。
  Use when the user asks to render the faceless video, or to cut / trim silences / caption / add BGM / concatenate their own footage.
---

# yt-video（動画を作る・編集するスキル）

最初に、どちらのモードかを決めます。

```
A 台本から作る   script.json と narration/ がある → 「モード A」へ（make_video.py）
B 素材を編集する  自分で撮った mp4 がある        → 「モード B」へ（vedit.py）
```

---

# モード A　台本＋ナレーション → 解説動画

文字のスライド（または自分の画像）＋ナレーション＋字幕 で、1本の mp4 を作ります。
公開・アップロードはしません。

---

## 準備（最初に1回）

```
1 ffmpeg   ffmpeg -version（無ければ Mac: brew install ffmpeg / Windows: winget install Gyan.FFmpeg）
2 Pillow   python3 -c "import PIL"（エラーなら pip3 install pillow。Windows は pip install pillow）
3 日本語フォント  Mac はヒラギノ、Windows は游ゴシック/メイリオ、Linux は Noto Sans CJK を自動で使う
              （Linux で無ければ sudo apt-get install fonts-noto-cjk）
              見つからないときは --font-bold / --font-regular でフォントファイルを指定
```

## 作り方

```
python3 <このスキルのフォルダ>/scripts/make_video.py \
  --script <作業フォルダ>/script.json \
  --narration <作業フォルダ>/narration \
  --out <作業フォルダ>/video/video.mp4
```

- パスは全部**絶対パス**で。
- `--theme dark` … 暗い背景のスライド
- `--no-subtitles` … 字幕を焼き込まない（YouTube の字幕機能だけ使うとき）

### 画面の出し方（script.json の visual）

- `"type": "text"` … `heading`（大きな文字）と `body`（小さな文字）のスライド
- `"type": "image"` … `"image": "/絶対パス/画像.png"`。16:9 でなくても、背景をぼかして収めます。
  画像が見つからないときは、文字スライドで代わりに作ります（注意が表示されます）。
  **使ってよい画像だけ**（自分で撮った・作った／利用条件を確かめた素材）。

### 字幕

- 台本の `narration`（表記用の文）を、句点ごとに区切って下の帯に焼き込みます。
- 切り替えの時刻は「文字数の割合」で決めています。だいたい合いますが、ぴったりではありません。
- 同じ字幕を `subtitles.srt` にも書き出します。YouTube に字幕としてアップロードすると、検索や自動翻訳に効きます。

## 自動で確かめること

書き出したあと、次の3つをナレーションの長さと比べます。

```
コンテナの長さ（Duration）  映像の長さ  音声の長さ
```

どれかが 0.25秒より大きくずれていたら `NG` を出して終了コード 1 で止まります。
`OK` が出るまで「できました」と言わないでください。

メタデータ（作成日時・タイトルなど全体の情報）は `-map_metadata -1` で消してあります。

## できあがったら確かめること

```
1 video.mp4 があるか（ls / dir）
2 OK の行と、表示された秒数
3 frames/ の中の画像を2〜3枚開いて、文字のはみ出し・誤字がないか見る
4 ご本人に、最初の10秒と最後の10秒を再生してもらう
```

文字がはみ出すときは、台本の `heading` を15文字以内、`body` を30文字以内に縮めて作り直します。

## 渡す

```
できたもの   /絶対パス/video/video.mp4（1920x1080）
             /絶対パス/video/subtitles.srt
長さ         ナレーション ○○秒 / 動画 ○○秒（OK）
次の一歩     「サムネを作って」と言ってください（yt-thumbnail）
```

## やってはいけないこと

- 他人の動画・画像・音楽（BGM）を入れない。BGM を足すなら、利用条件を確かめた音源だけ
- 動画をアップロードしない（アップロードはご本人が YouTube の画面で行う）
- 同じ台本・同じ見た目で、言葉だけ入れかえた動画を大量に作らない（README の注意を参照）

---

# モード B　自分で撮った素材を編集する（vedit.py）

素材と「編集指示書」から、カット・無音詰め・字幕・BGM・つなぎ・書き出しまでを ffmpeg で行い、
最後に予定と実物の長さを照合して `edit_report.md` を出します。以下 `VEDIT` は `<このスキルのフォルダ>/scripts/vedit.py` です。

```
1 受け取り     素材フォルダ（絶対パス）と templates/handoff_sheet.md（編集指示書）を埋めてもらう
2 素材を測る    python3 VEDIT probe <素材フォルダ>/*.mp4
3 無音詰めの下書き  python3 VEDIT silence <素材>.mp4 --out <作業フォルダ>/edit.json
4 指示を足す    指示書に合わせて clips の順番・caption・bgm・srt を edit.json に書き足す（見本 templates/edit_example.json）
5 点検         python3 VEDIT check  <作業フォルダ>/edit.json   （NG 0 まで）
6 書き出し     python3 VEDIT render <作業フォルダ>/edit.json
7 実物を見る    edit_report.md の判定、冒頭・つなぎ目・最後の静止画3枚
8 渡す         ファイルの場所・判定・実物の長さ（測った時刻つき）・人が見るべき所
```

## 無音詰め（silence）の調整

| 指定 | 既定 | 変えるとき |
|---|---|---|
| `--noise` | -35dB | 部屋がうるさくて切れない → -30dB。小声が切れる → -40dB |
| `--min` | 0.6 | テンポを上げたい → 0.4。間を残したい → 1.0 |
| `--pad` | 0.12 | 語尾が切れる → 0.2 |

下書きは「たたき台」です。言い間違い・言い直しまでは見つけられません。区間の一覧をご本人に見せ、切りたい所・残したい所を聞いてから直します。

## edit.json の項目

| 項目 | 中身 |
|---|---|
| output | 書き出し先（edit.json からの相対パス可） |
| size / fps | 仕上がりのサイズと1秒のコマ数（向きが違う素材は黒帯で収める） |
| clips[] | 上から順につなぐ。`src` 素材 / `in` 開始秒 / `out` 終了秒 / `caption` 短い字幕（任意） |
| srt | 全文字幕を焼き込むときの .srt（**つないだ後の時間**で書く）。caption とは併用しない |
| bgm | `src` / `volume`（0.10〜0.15）/ `fade_out`（秒）/ `loudnorm`（既定 true） |
| fade_video | true でクリップごとに 0.15 秒の黒フェード |

## 点検と判定

- check は書き出さずに「素材が在るか」「in/out が素材の長さに収まるか」を見ます（NG で終了コード 1）。
- render は クリップごとに切り出す → 長さを測る → つなぐ → 字幕 → BGM → メタデータを消す → 全体を測る の順。
- 予定と実物の差がクリップごと 0.10 秒、全体 0.30 秒を超えたら NG（終了コード 2）。
- 静止画の書き出し： `ffmpeg -y -ss 1 -i <output> -frames:v 1 <作業フォルダ>/check_head.png`

## もっと本格的にしたいとき（任意・外部の無料ツール）

キットには入れていません。使うときは、ご本人が各公式ページの手順で入れ、ライセンスを確かめてください。

```
auto-editor   無音カットの定番。Premiere / DaVinci Resolve / Final Cut 用の書き出しも（Unlicense）
              https://github.com/WyattBlue/auto-editor
whisper.cpp   手元で文字起こし（MIT）  https://github.com/ggml-org/whisper.cpp
```

AGPL などの「改変したら公開が必要」になるライセンスのツールは、キットの中に組み込まない方針です。

## モード B のつまずき

| 症状 | 対処 |
|---|---|
| `No such filter: 'subtitles'` | libass 入りの ffmpeg（brew 版など）を入れる。または srt をやめて caption を使う |
| つなぎ目で音がプツッと鳴る | `--pad` を広げる／in を 0.05 秒前に |
| 字幕の時間がずれる | srt は「つないだ後」の時間で書く |
| 長さの判定が NG | edit_report.md の表でどのクリップがずれたか見る。可変フレームレートの素材が原因のことが多い |

## モード B でやってはいけないこと

- 他人の動画・音楽・画像を、許可や利用条件の確認なしに使う
- 予定の長さだけ見て「できました」と言う（必ず render 後の実物を測る）
- 素材の元ファイルを上書きする（書き出しは必ず別のファイルに）
