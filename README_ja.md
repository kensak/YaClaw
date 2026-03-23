# YaClaw

```
    ██╗   ██╗ █████╗ 
    ╚██╗ ██╔╝██╔══██╗
     ╚████╔╝ ███████║
      ╚██╔╝  ██╔══██║
       ██║   ██║  ██║
       ╚═╝   ╚═╝  ╚═╝
          ██████╗██╗      █████╗ ██╗    ██╗
         ██╔════╝██║     ██╔══██╗██║    ██║
         ██║     ██║     ███████║██║ █╗ ██║
         ██║     ██║     ██╔══██║██║███╗██║
         ╚██████╗███████╗██║  ██║╚███╔███╔╝
          ╚═════╝╚══════╝╚═╝  ╚═╝ ╚══╝╚══╝
```

[![Python](https://img.shields.io/badge/python-3.13+-blue.svg)](https://www.python.org/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)
[![Platform](https://img.shields.io/badge/platform-Windows%20%7C%20Linux%20%7C%20macOS-lightgrey.svg)]()

[English](README.md)

> **Yet Another 'Claw'-like Tool — Use Your Favorite AI Coding CLI, Through Your Favorite Channel**

**SNSからAIコーディングCLIをリモート操作する、シンプルなブリッジツール。**

> **ACPネイティブメッセージ！** YaClawの標準プラグインはテキストの代わりに [Agent Client Protocol (ACP)](https://agentclientprotocol.com/) JSON-RPC オブジェクトをメッセージ・ボディーに使用するようになりました。チャンネルは許可ボタン、設定メニューなど ACP が提供する機能をフルに活用できます — さらに多くの機能が追加予定です。

---

## なにができるの？

YaClawは、DiscordやLINEに書いたメッセージをAIコーディングCLIへ届け、AIの返答をチャンネルに投稿します。エージェントは設定した作業ディレクトリで、あなたのマシン上で動き続けるため、**AGENTS.md、SOUL.md、MCP設定、スキル、ファイルアクセス、コマンド実行など、ローカル環境がそのまま使えます**。

```
あなた ─[Discord / LINEメッセージ]──▶ YaClaw ──▶ エージェント（Copilot / Codex / Gemini / OpenCode / …）
                                              （あなたのマシン上で動作）
      ◀─[Discord / LINEへ返信]────────────────────────────────────
```

---

## 特徴

- **ACP対応** — ACP対応のCLIエージェント（Copilot、Codex、Gemini、OpenCode等）とチャンネルが stdio JSON-RPC 2.0 で接続。モデルを選択するメニューなど、豊富な機能がSNS上で利用可能です。
- **セッション持続** — 再起動しない限り同じセッションが継続。会話の文脈が失われません
- **セッション選択** — 利用可能なセッションを一覧表示し、再開するセッションを選択
- **思考出力制御** — エージェントごとに思考チャンクのストリーミングを有効/無効化（`output_thought`）
- **環境そのまま** — MCP設定・スキル・ファイルシステムなど、ローカル環境を完全に活用
- **スケジューラー対応** — 定期的にAIへプロンプトを送り、自動タスクを実行
- **プラグイン拡張** — チャンネルもエージェントもPythonプラグインで自由に追加
- **軽量・シンプル** — `uv run main.py` の1コマンドで起動

---

## 対応チャンネル・エージェント

| 種別 | 名前 | プラグイン |
|------|------|-----------|
| チャンネル | Discord | `channel_discord` |
| チャンネル | LINE | `channel_line` — [設定ガイド](docs/ja/channel_line_doc_ja.md) |
| チャンネル | スケジューラー | `channel_schedule` |
| チャンネル | ターミナル（テスト用） | `channel_terminal` |
| チャンネル | おしゃべり（テスト用） | `channel_random_talker` |
| エージェント | ACP対応CLIすべて（Copilot、Codex、Gemini、OpenCode等） | `agent_acp` |
| エージェント | エコー（テスト用） | `agent_echo` |

---

## クイックスタート

### 前提

- Windows、Linux、または macOS
- [uv](https://github.com/astral-sh/uv) インストール済み
- ACP対応CLIを少なくとも1つインストール済み（例: `copilot`、`opencode`、`gemini`、`codex`）
- Discord / LINE のボット作成済み

### Step 1: クローン

```bash
git clone https://github.com/kensak/YaClaw.git
cd YaClaw
```

### Step 2: `.env` ファイルを作成

Discordの場合
```bash
# .env
DISCORD_BOT_TOKEN=your_bot_token_here
DISCORD_CHANNEL_ID=your_channel_id_here
```

### Step 3: `settings.json` を設定

```json
{
    "channel": {
        "discord": {
            "plugin": "channel_discord",
            "channel_id": "${DISCORD_CHANNEL_ID}",
            "bot_token": "${DISCORD_BOT_TOKEN}",
            "agent": "opencode",
            "output_thought": false,
            "require_mention": false
        }
    },
    "agent": {
        "opencode": {
            "plugin": "agent_acp",
            "command": "opencode",
            "args": ["acp"],
            "work_dir": "workspace/opencode"
        }
    }
}
```

> `agent.[name].plugin` の値は `plugins/` フォルダー内のPythonファイル名（拡張子なし）です。
>
> **`agent_acp` の主な設定キー:**
> | キー | 説明 |
> |-----|------|
> | `command` | 起動するCLI実行ファイル |
> | `args` | CLIへ渡す引数（ACPフラグやセッション再開フラグをここに指定） |
> | `work_dir` | エージェントプロセスの作業ディレクトリ |

### Step 4: 起動

```bash
uv run main.py
```

### Step 5: Discord / LINE で試す

設定したチャンネルにメッセージを送り、AIからの返信が来れば成功です！

---

## コマンド

AIコーディングCLIとチャンネルの双方が対応している場合のみ使用可能です。  
それぞれのコマンドでは選択肢の一覧が表示され、ユーザーがその中から選ぶことができます。

- /sessions — セッションの選択
- /ai_models — AIモデルの変更
- /modes — エージェント・モードの変更
- /reasoning_efforts — 思考努力レベルの変更

---

## 設定サンプル

`examples/` フォルダーにさまざまな設定例があります。

| ファイル | 内容 |
|----------|------|
| `settings_copilot_acp.json` | GitHub Copilot CLI（ACP経由） |
| `settings_codex_acp.json` | OpenAI Codex CLI（ACP経由、`@zed-industries/codex-acp` 使用） |
| `settings_gemini_acp.json` | Google Gemini CLI（ACP経由） |
| `settings_opencode_acp.json` | OpenCode（ACP経由） |
| `settings_line.json` | LINE Messaging API チャンネル |
| `settings_schedule.json` | スケジューラーを使った自動タスク |
| `settings_forward_test.json` | エージェント間転送のテスト |
| `settings_terminal_conversation_test.json` | ターミナルでAIと会話するテスト |

---

## ログ

ログは `log/log-YYYYMMDD.json` に記録されます。`jq` を使うと柔軟にフィルタリングできます。

```bash
# trace ログのみ表示
cat log/log-20260101.json | jq -c -r 'select(.type == "trace" and .name == "main") | [.time, .message] | join(" ")'
```

---

<details>
<summary>プラグインの書き方（クリックして展開）</summary>

`plugins/` フォルダに Python ファイルを置き、`Channel` または `Agent` の派生クラスを **1つだけ** 定義します。クラス名は任意ですが、ファイル名（拡張子なし）を `settings.json` の `plugin` フィールドに指定します。

```json
{
    "channel": { "my_ch": { "plugin": "my_channel_plugin", "agent": "my_agent", ... } },
    "agent":   { "my_agent": { "plugin": "my_agent_plugin", ... } }
}
```

---

### チャンネルプラグイン

シンプルな text-body チャンネルの実装例として `plugins/text_body/channel_random_talker_text_body.py` を参考にしてください。

```python
from yaclaw.channel import Channel

class MyChannel(Channel):

    async def initialize(self, channel_name, channel_settings):
        # 初期化処理。self.channel_name / self.channel_settings は
        # フレームワークが設定済みなのでここで使用できる。
        # 失敗時は False を返すと起動が中止される。
        return True

    async def start_listener(self):
        # 外部からメッセージを受け取るループ処理をここに書く。
        # 文字列をそのままエージェントへ送る場合:
        await self.handle_request_message("こんにちは")

        # reply_to などを明示的に指定したい場合:
        # request = await self.create_request_skeleton()
        # request["body"] = "こんにちは"
        # request["reply_to"] = "other_channel"
        # await self.handle_request_message(request)

    async def handle_response_message(self, response):
        # エージェントからの返答を受け取る。
        # response["body"] に返答テキストが入っている。
        print(response["body"])

    async def stop(self):
        # シャットダウン時の処理（ループ停止フラグなど）
        pass

    async def finalize(self):
        # リソース解放など後始末
        pass
```

**ポイント**

- `handle_request_message(msg)` の引数は **文字列** または **辞書（リクエストメッセージ）** のどちらでも可。
- `create_request_skeleton()` を使うと `from_` / `to_` / `reply_to` が自動設定された辞書を取得できる。
- `handle_response_message` はフレームワーク内部のキューによってシリアライズされて呼び出されるため、並行呼び出しを心配する必要はない。

ACP-body チャンネルの実装としては、`plugins/channel_random_talker.py`を参照してください。ACP ハンドシェークや method/notification の処理をおこなっています。SNSサービスと通信するより現実的な例としては `plugins/channel_discord.py` を参照してください。

---

### エージェントプラグイン

text-body エージェントの実装例として `plugins/text_body/agent_echo_text_body.py` を参考にしてください。

```python
from yaclaw.agent import Agent

class MyAgent(Agent):

    async def initialize(self, agent_name, agent_settings):
        # 初期化処理。失敗時は False を返す。
        return True

    async def start_handler(self):
        # リクエストキューとは独立して動く処理（外部プロセス起動など）をここに書く。
        # 単純なエージェントでは何もしなくてよい（すぐ return してよい）。
        pass

    async def handle_request_message(self, request):
        # request["body"] にリクエストテキストが入っている。
        body = request["body"]

        # レスポンスの骨格を作成（from/to/via などが自動設定される）
        response = await self.create_response_skeleton(request)
        response["body"] = f"受け取りました: {body}"

        # チャンネル（または次のエージェント）へ返す
        await self.handle_response_message(response)

    async def stop(self):
        pass

    async def finalize(self):
        pass
```

**ポイント**

- `start_handler` と `handle_request_message` は **並行して** 動作する（`asyncio.TaskGroup`）。
- `create_response_skeleton(request)` を必ず使うことで、転送チェーン（`to` がリストの場合）が正しく処理される。
- `handle_response_message(response)` を呼ぶと、`response["to_"]` の宛先（チャンネルまたは次のエージェント）へ自動でルーティングされる。

ACP-body エージェントの実装は以下の例を参考にしてください:
- `plugins/agent_echo.py` もっとも簡単な例。
- `plugins/agent_acp.py` AI コーディング CLI と連携する例。

</details>

---

<details>
<summary>設計詳細（クリックして展開）</summary>

### アクター

チャンネルとエージェントという二種類のアクターがあり、これらの間でメッセージをやりとりするモデルです。

- **チャンネル**: エージェントにリクエストを送り、レスポンスを受け取ります。レスポンスはキューによりシリアライズされます。
- **エージェント**: チャンネルや他のエージェントからのリクエストに対してレスポンスを返します。リクエストはキューによりシリアライズされます。

### メッセージのルーティング

`{from: A, to: X}` はメッセージを表します。（内容は省略）

#### 基本動作

```
チャンネル A ---{from: A, to: X}-----------> エージェント X
             <--{from: X, to: A, via: X}---
```

#### `reply_to` による返信先の変更

`schedule` チャンネルのような定期プロンプトに便利です。

```
チャンネル A ---{from: A, to: X, reply_to: B}---> エージェント X
チャンネル B <--{from: X, to: B, via: X}--------
```

#### 転送

送信時にあらかじめ転送先を指定できます。

```
チャンネル A ---{from: A, to: [X, Y, Z]}---------> エージェント X
エージェント X ---{from: X, to: [Y, Z], reply_to: A, via: X}---> エージェント Y
エージェント Y ---{from: Y, to: Z, reply_to: A, via: [X, Y]}---> エージェント Z
エージェント Z ---{from: Z, to: A, via: [X,Y,Z]}----------> チャンネル A
```

</details>

---

## コントリビューション

バグ報告・機能要望・プルリクエスト、どれも歓迎です！
新しいチャンネルやエージェントのプラグインを作ったら、ぜひシェアしてください。

---

## 免責事項

情報漏洩・AIの予期しない動作（ハルシネーション等）に対する対策は利用者自身の責任で行ってください。本プログラムの利用により生じた損害について作者は一切の責任を負いません。

---

## ライセンス

[MIT License](LICENSE)

