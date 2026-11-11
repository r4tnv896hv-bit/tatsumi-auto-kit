---
name: kit-setup
description: >
  「Claude Code × 完全自動化キット」の初期設定をするスキル。道具の点検（OS・Python・ffmpeg・Pillow・Chrome/Edge）→足りないものを公式の入れ方で案内→作業フォルダ作成→キットのスキルをスキル置き場へコピー→各スキルの試し運転→「次にやること」の順で進める。
  「キットの初期設定をして」「キットのセットアップをして」「キットを使えるようにして」「スキルを入れて」「環境チェックして」「動くか確かめて」と言われたときに使う。
  Use when the user says "set up the kit", "install the kit skills", "kit setup", "check my environment for the kit", or "is the kit ready".
---

# kit-setup（キットの初期設定スキル）

キットを買った方が、最初の1回だけ使うスキルです。
相手はエンジニアではありません。専門用語を使わず、短い文で話しかけてください。

このスキルがすること・しないこと：

```
する    道具の点検 / 作業フォルダ作り / スキルのコピー / 試し運転 / 次にやることの案内
しない  道具のインストールを勝手に実行する（入れ方を案内し、ご本人に打ってもらう）
しない  パスワード・APIキーを聞く、ファイルに書く、画面に出す
しない  投稿・送信・購入・支払い
```

このスキルのフォルダの中身：

```
SKILL.md                  この手順書
scripts/env_check.py      道具の点検（読むだけ）
scripts/make_workspace.py 作業フォルダを作る（あるものには触らない）
scripts/install_skills.py スキルをコピーする（同名があれば退避してから）
scripts/selftest.py       入れたスキルの試し運転（dry-run。動画も音声も作らない）
```

以下 `$S` は、このファイルと同じフォルダの `scripts/` の絶対パスです。
`python3` は、Windows では `python` に読み替えてください（以下すべて同じ）。

---

## 全体の流れ（この順で、1段ずつ。各段の終わりに結果を短く伝える）

```
1 道具の点検        env_check.py
2 作業フォルダ      make_workspace.py   （置き場所を1回だけ確認）
3 スキルを入れる    install_skills.py   （どこに入れるかを必ず聞く）
4 試し運転          selftest.py
5 次にやること      決まった文面で伝える
```

---

## 1 道具の点検

```
python3 $S/env_check.py
```

- 終了コード 0 = 必須の道具がそろっている / 1 = 足りないものがある。
- 足りないものは、出力の「→」の行をそのまま、やさしい言葉で伝えます。
- 入れ方の案内は、**公式ページのリンクと、公式が案内しているコマンドだけ**にします。
  知らないサイトや、まとめ記事のリンクを出さないでください。

```
Python        https://www.python.org/downloads/
ffmpeg        https://ffmpeg.org/download.html
              Mac: Homebrew（https://brew.sh/）を入れてから  brew install ffmpeg
              Windows: winget install Gyan.FFmpeg
              Linux: sudo apt-get install ffmpeg fonts-noto-cjk open-jtalk open-jtalk-mecab-naist-jdic hts-voice-nitech-jp-atr503-m001
              （Linux は ffmpeg・日本語フォント・読み上げをまとめて入れる）
Pillow        pip3 install pillow（Windows は pip install pillow）
Chrome        https://www.google.com/chrome/
Edge          https://www.microsoft.com/edge
（任意）whisper  pip3 install -U openai-whisper（長い動画の文字起こしを自動にしたい人だけ）
```

- インストールのコマンドは、**こちらで勝手に実行しません**。
  「このコマンドをターミナルに貼って Enter を押してください」と案内し、終わったと言われたら、もう一度 env_check.py を走らせます。
  ご本人が「代わりに打って」とはっきり頼んだときだけ実行してよいです（パスワードを求められたら、ご本人に打ってもらう）。
- Python 自体が無いときは、このスクリプトも動きません。そのときは `python3 --version`（Windows は `python --version`）の結果を見て、Python の公式ページを案内します。
- 入れたあとは **ターミナルを開き直す** よう必ず伝えます（開き直さないと新しい道具が見えません）。
- 足りないものがあっても、2 と 3 は先に進めてかまいません。4 の試し運転で「準備不足」と出るだけです。

### GEMINI_API_KEY（任意）について

聞かれたとき、または env_check.py で「入っていません」と出たときだけ、次の要点を伝えます。

```
- 無くても、キットは最後まで使えます（声は パソコン内蔵の声 になります）
- 声をもっと自然にしたい人だけ、Google AI Studio（https://aistudio.google.com/）でキーを作ります
- キーは「環境変数」に、ご本人が自分で入れます
    Mac:     ~/.zshrc に  export GEMINI_API_KEY="ここにキー"  の1行を足し、ターミナルを開き直す
    Windows: setx GEMINI_API_KEY "ここにキー"  を実行し、ターミナルを開き直す
- キーはパスワードと同じです。チャットに貼らない・メモ帳に残さない・スクショに写さない
```

**キーを、こちらに貼ってもらわないでください。** 貼られてしまったら、使わずに
「このキーは他の人に見られた可能性があります。AI Studio で削除して作り直してください」と伝えます。
キーを作業フォルダ・メモ・ログ・このファイルに書くことは、どんな理由でもしません。
入っているかの確認は「入っています／入っていません」だけを出す方法で行います（env_check.py がそうしています）。

---

## 2 作業フォルダ

初期値は、ホームの下の `kit-work` です。1回だけ「ここでよいですか」と聞きます。
作ったら、キットの `CLAUDE.md` の「フォルダの地図」の【】に、キットと作業フォルダの絶対パスを書き込むか、ご本人に聞いてから書き込みます。

```
python3 $S/make_workspace.py                      ← 初期値（~/kit-work）
python3 $S/make_workspace.py --base /絶対パス      ← 別の場所にしたいとき
```

できるもの：

```
kit-work/research  リサーチボード
kit-work/youtube   YouTube の台本・声・動画・サムネ
kit-work/shorts    ショート動画
kit-work/note      note の下書き
kit-work/sns       投稿文の下書き
kit-work/reports   振り返り・週報
kit-work/memory    業務日誌（MEMORY.md が目次）
kit-work/memo      数字のメモ・作業メモ
kit-work/logs      定期実行の記録
```

すでにあるフォルダ・ファイルには触りません。2回走らせても大丈夫です。

---

## 3 スキルを入れる

**どこに入れるかを、必ず聞いてから**コピーします。聞き方の例：

```
スキルの使い方を3つから選んでください。
  C いちばん簡単：キットのフォルダ（tatsumi-auto-kit）で Claude Code を起動して使う
    → スキルも担当（サブエージェント）も最初から入っています。コピーは要りません
  A このパソコンのどこからでも使う（ホームの .claude/skills と .claude/agents にコピー）
  B 別の作業フォルダの中だけで使う（そのフォルダの .claude/skills と .claude/agents にコピー）
分からなければ C で大丈夫です。
```

C を選んだら、コピーは飛ばして 4 の試し運転へ進みます（`--skills <キット>/.claude/skills`）。

まず `--dry-run` で「何をコピーするか」を見せ、OK をもらってから本番を走らせます。

```
A:  python3 $S/install_skills.py --target user --with-agents --dry-run
    python3 $S/install_skills.py --target user --with-agents
B:  python3 $S/install_skills.py --target project --project /絶対パス --with-agents --dry-run
    python3 $S/install_skills.py --target project --project /絶対パス --with-agents
```

- キットのフォルダは、このファイルの4つ上（`tatsumi-auto-kit`）を自動で使います。
  違う場所なら `--kit /絶対パス` を付けます。
- 入るスキル（14個）：kit-setup / yt-research / yt-script / yt-narration / yt-video / yt-thumbnail / yt-ops /
  short-clip / short-from-article / note-article / sns-to-note / sns-post / weekly-report / secretary
- `--with-agents` を付けると、担当6人（researcher / scriptwriter / editor / thumbnail-designer / publisher-drafts / analyst）も入ります
- 同じ名前のスキルがすでにあって中身が違うときは、消さずに `名前.bak-日時` に退避してから入れます。退避したものがあれば、名前を伝えます。
- コピーのあと、全ファイルの中身が元と同じかを自動で確かめます（終了コード 0 が合格）。
- 新しく入れたスキルは、**Claude Code を一度終了して開き直すと**使えるようになります。これを必ず伝えます。

---

## 4 試し運転（dry-run）

```
C のとき:  python3 $S/selftest.py --skills <キットの絶対パス>/.claude/skills
A のとき:  python3 $S/selftest.py --skills ~/.claude/skills
B のとき:  python3 $S/selftest.py --skills /絶対パス/.claude/skills
```

（Windows で `~` が使えないときは `%USERPROFILE%\.claude\skills` の絶対パスにする）

試し運転は、動画・音声・画像を作らず、ネットにもつながりません。
見本の点検は一時フォルダの中のコピーで行い、スキルのフォルダには何も書きません。

結果の読み方：

```
OK        そのまま使えます
準備不足  ffmpeg か Pillow が無いだけ。1 の案内で入れて、もう一度試し運転
NG        ファイルが壊れているか、足りない。キットを展開し直して 3 からやり直す
```

終了コードは 0 = 全部OK / 2 = 準備不足あり / 1 = NG あり。
**画面の表示ではなく、終了コードで判断してください。** パイプ（`| head` など）を通すと終了コードが変わるので、そのまま走らせます。

NG が出たら、出力を要約せずにそのまま見せ、「キットのフォルダを丸ごと展開し直して、もう一度初期設定をして」と案内します。
3回やり直しても NG なら、出力の全文を添えて、購入先のサポートに相談するよう伝えます。

---

## 5 次にやること（この文面を、結果に合わせて埋めて伝える）

```
初期設定が終わりました。
  道具      必須 ◯/◯ そろっています（足りないもの: ◯◯）
  作業場所  /絶対パス/kit-work
  スキル    ◯個 入れました（場所: ◯◯）
  試し運転  OK ◯ / 準備不足 ◯ / NG ◯

次にやること
  1 Claude Code を一度終了して、開き直す（新しいスキルを読み込むため）
  2 「CLAUDE.md の【】を一緒に埋めて」と話しかける
  3 「〇〇についてネタを探して」と話しかけて、1本目のリサーチを作る

いつでも「キットの初期設定をして」と言えば、点検をやり直せます。
```

最後に、次の注意を1回だけ添えます。

```
AIが作ったものは、必ずご自身で読んで確かめてから使ってください。
投稿・送信・お金のやりとりは、AIに任せず、ご自身の手で行ってください。
```

---

## 困ったとき

```
python3 が見つからない           Windows は python。それも無ければ Python 公式ページから入れる
入れたのに「見つかりません」      ターミナルを開き直したか確認（開き直さないと見えない）
スキルが反応しない                Claude Code を開き直したか / 入れた場所（A か B か）を確認
B で入れたのに使えない            Claude Code をそのフォルダで起動しているか確認
Permission denied / 権限エラー    書き込めない場所を選んでいる。ホームの下を選び直す
```
