---
name: yt-thumbnail
description: >
  YouTube動画のタイトルから、文字だけのシンプルなサムネイル案を3つ出し、HTML→PNG（1280x720）に書き出すスキル。顔写真やAIで作った人物は使わない。
  「サムネを作って」「サムネイル案を出して」「YouTubeのサムネ」「サムネ画像にして」と言われたときに使う。
  Use when the user asks for YouTube thumbnail ideas or images, or says "make a thumbnail", "thumbnail concepts", "render thumbnail".
---

# yt-thumbnail（文字だけのサムネイルのスキル）

タイトルから「文字だけのサムネイル」を3案作り、PNG（1280x720）にします。
公開・アップロードはしません。

---

## 流れ

```
1 タイトルと、見てほしい人を確かめる（script.json があれば title と audience を読む）
2 3案を考える（下のルール）→ 文で見せて、ご本人の意見を聞く
3 concepts.json を書く（templates/concepts_example.json をコピー）
4 render_thumbnail.py で PNG にする
5 3枚を見比べてもらい、1枚選んでもらう
```

## 3案のルール

- 3案は「切り口」を変える
  - A 中央に大きな一言（`layout: center`）… いちばん無難
  - B 左に大きな数字（`layout: split`）… 数字が入るテーマ向き
  - C 暗い背景＋上下の帯（`layout: band`）… 目立たせたいとき
- 大きな文字は 1行 8文字前後・2〜3行まで。スマホの小さい画面で読めるか考える
- タイトルと同じ文をそのまま載せない（サムネは「一言で気になる」、タイトルは「中身の説明」）
- 動画の中身と違うこと・大げさな数字は書かない（クリックさせるためのうそは、YouTube のルール違反）
- 顔写真・AI で作った人物・他人のロゴやキャラクターは使わない
- `[[ ]]` で囲んだ文字が強調色になる（1案に1〜2か所まで）

## PNG にする

```
python3 <このスキルのフォルダ>/scripts/render_thumbnail.py <作業フォルダ>/concepts.json --out <作業フォルダ>/thumbnail
```

- Google Chrome か Microsoft Edge があれば、追加のインストールは不要です（裏で画面を開いて写します）。
- どちらも無いときは: `pip install playwright` → `python -m playwright install chromium`
- できた PNG が 1280x720 か自動で確かめ、文字情報（メタデータ）を消します。
- `thumb_A.html` などをブラウザで開けば、その場で見た目を確かめられます。
- 文字の大きさは自動で決まります。変えたいときは案に `"size": 120` のように書きます。

## できあがったら確かめること

```
1 thumb_A.png / thumb_B.png / thumb_C.png があるか（ls / dir）
2 OK の行に（1280x720）と出ているか
3 画像を開いて、文字が切れていないか・誤字がないか
```

## 渡す

```
できたもの   /絶対パス/thumbnail/thumb_A.png（B, C も）
それぞれの狙い  A: … / B: … / C: …
次の一歩     1枚選んで、YouTube の投稿画面でご本人がアップロード
```

## やってはいけないこと

- 顔写真・AI で作った人物・他人の写真/ロゴ/キャラクターを使わない
- 動画の中身に無いことを書かない
- 勝手にアップロードしない
