# TESTS.md（動作確認の記録）

## 測った環境と時刻

- 日時：2026-11-09 20:21:20〜20:22:59（JST）
- パソコン：macOS（Apple シリコン）、Python 3.9.6、ffmpeg 6.0（libass 入り。ffprobe なし）、Pillow 11.3.0、Google Chrome
- 声：Mac 内蔵の Kyoko（say）
- 実行したコマンド：`bash scripts/run_tests.sh --full`
- 結果：**PASS 49 / FAIL 0（終了コード 0）**

すべて一時フォルダの中で動かし、キットのフォルダには何も書いていません。ネットへの接続・投稿・送信はしていません。

## 何を確かめたか

| 分野 | 確かめたこと | 結果 |
|---|---|---|
| キットの形 | kit_doctor.py（スキル14・担当6・手順書に書かれたファイルの有無・秘密の混入・GPL/AGPL の文・settings.json） | NG 0 |
| 初期設定 | selftest.py（全14スキルの文法・使い方表示・見本の点検・試し運転でフォルダが変わらないこと） | OK 81 / NG 0 |
| 初期設定 | make_workspace.py（作業フォルダ9つ＋MEMORY.md）、install_skills.py（dry-run・本番・2回目は何もしない・担当もコピー）、env_check.py | 合格 |
| yt-research | 空のボードは NG（rc=1）、埋めたボードは合格（rc=0） | 合格 |
| yt-script | 見本の台本（4場面）の点検 | 合格 |
| 字幕の改行 | jp_linebreak の単体テスト（yt-video・short-clip・short-from-article の3か所） | 合格 |
| note-article | 短い見本で字数不足の NG が出る（rc=1）／有料ラインの目印を見つける | 合格 |
| 有料ラインの目印 | `=== ここから有料 ===`（新）と `――――― ここから有料（有料ライン） ―――――`（旧）の両方で、sns-to-note の plan.md・posts.md に有料部分の見出し・本文が出ないこと／note-article の SKILL.md が新しい目印を書くこと | 合格 |
| sns-to-note | 1週間の予定表と下書きの枠、見本の下書きの点検 | 合格 |
| sns-post | 見本の下書きは合格／過去の下書きと同じ文は NG／「誰でも稼げます」・ハッシュタグ3個は NG と注意／見本の数字から振り返りを作成 | 合格 |
| secretary | add・summary・remind、run_daily.sh（相対パスは断る rc=2、絶対パスは合格） | 合格 |
| yt-ops | init・add・week・review（見本の Studio CSV） | 合格 |
| weekly-report | 作業フォルダ・YouTube CSV・SNS CSV・タスク帳から週報を作成 | 合格 |
| short-clip | whisper が無いときに案内して rc=2 で止まる | 合格 |
| yt-narration | 見本の台本を内蔵の声で読み上げ（wav・mp3・timing.json） | 合格 |
| yt-video モードA | スライド動画（1920x1080・字幕）を作り、全体・映像・音声の長さがナレーションと一致 | 合格（約37秒） |
| yt-thumbnail | 3案を 1280x720 の PNG に（Chrome で描画） | 合格 |
| yt-video モードB | probe → silence（無音詰め 37.77秒→36.18秒）→ check → render（予定 36.19秒／実物 36.23秒、差 0.04秒） | 合格 |
| short-clip | 見本の長尺（約2分20秒・23.976fps）から2本、縦長1080x1920・字幕・長さ照合 | 合格（32.17秒・32.90秒） |
| short-from-article | 見本の台本1本目を say で動画に（5場面） | 合格 |

目で確かめたもの：サムネ B 案の PNG、yt-video の5秒目のコマ、short-from-article の3秒目のコマ（文字のはみ出し・字幕の位置・日本語フォント）。

## この版で直したこと

| 直したこと | 内容 |
|---|---|
| vedit.py（yt-video モードB） | `silence --out` の保存先フォルダが無いと止まっていた（FileNotFoundError）。フォルダを作るように修正 |
| 有料ラインの目印 | note-article が `――――― ここから有料（有料ライン） ―――――`、sns-to-note が `=== ここから有料 ===` と別々で、有料部分の見出しが SNS の下書きに漏れていた。`=== ここから有料 ===` に統一。sns-to-note は古い形も読む。check_draft.py は目印の位置・重複・古い形を知らせる |
| install_skills.py | 新しいフォルダの形（.claude/skills）に対応、14スキル、`--with-agents` で担当もコピー |
| make_workspace.py | research・sns・reports・memory・logs を追加、MEMORY.md を作る |
| selftest.py | 新しいスキル（yt-research・yt-ops・sns-to-note・sns-post・weekly-report・secretary）と vedit.py を追加 |
| make_sample_long.py | 部品の場所を新しいフォルダの形に合わせた |
| yt-script・note-article | 保存先を作業フォルダ（kit-work/youtube・kit-work/note）にそろえた |

## 確かめられなかったこと

| もの | 理由 | 代わりに確かめたこと |
|---|---|---|
| Gemini の声（yt-narration・short-from-article の `--engine gemini` / `--tts gemini`） | 有料の API キーを使わない条件のため | 使い方表示と、キーが無いときに内蔵の声へ切り替える作り（コードを読んで確認） |
| whisper での文字起こし | このパソコンに whisper が入っていない | 入っていないときの案内（rc=2）と、.srt を渡す流れ |
| Windows | Windows のパソコンが無い | Windows 用の分岐はコードを読んだだけ |
| Claude Code 上でスキル・担当が自動で選ばれるか | このテストはスクリプトの動作確認のため | SKILL.md・担当の name / description の形（kit_doctor.py） |
| ウェブ検索（yt-research の調べる段） | ネットにつながない条件のため | ボードの作成と点検 |
| 各SNSの文字数の上限・予約機能・規約 | 公式ページを開いていない | 点検の数字は 2026-11-09 時点の把握。README と教科書に【要確認】を付けた |

## もう一度確かめるとき

```
python3 scripts/kit_doctor.py            読むだけの健康診断
bash scripts/run_tests.sh                速い点検（動画・音声は作らない）
bash scripts/run_tests.sh --full         動画・音声・サムネまで（Mac）
bash scripts/run_tests.sh --full --keep  作ったものを残して目で確かめる
```
