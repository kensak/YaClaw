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
[![Platform](https://img.shields.io/badge/platform-Linux%20%7C%20WSL-lightgrey.svg)](https://learn.microsoft.com/windows/wsl/)
[![Status](https://img.shields.io/badge/status-experimental-orange.svg)]()

[English](README.md)

> **Yet Another 'Claw'-like Tool — Use Your Favorite AI Coding CLI, Through Your Favorite Channel**

**DiscordからAIコーディングCLIをリモート操作する、シンプルなブリッジツール。**

---

## なにができるの？

YaClawは、Discordに書いたメッセージをそのままCodex CLIやCopilot CLIへ届け、AIの返答をチャンネルに投稿します。AIエージェントはあなたの開発マシン上で動き続けるため、**MCPの設定・ファイルアクセス・コマンド実行などの環境がまるごと使えます**。

```
あなた ─[Discordメッセージ]──▶ YaClaw ──▶ Codex CLI / Copilot CLI
                                              （あなたのマシン上で動作）
      ◀─[Discordへ返信]────────────────────────────────────────────
```

---

## 特徴

- **セッション持続** — 再起動しない限り同じセッションが継続。会話の文脈が失われません
- **環境そのまま** — MCP設定・スキル・ファイルシステムなど、ローカル環境を完全に活用
- **スケジューラー対応** — 定期的にAIへプロンプトを送り、自動タスクを実行
- **プラグイン拡張** — チャンネルもエージェントもPythonプラグインで自由に追加
- **軽量・シンプル** — `uv run main.py` の1コマンドで起動

---

## 対応チャンネル・エージェント

| 種別 | 名前 | プラグイン |
|------|------|-----------|
| チャンネル | Discord | `channel_discord` |
| チャンネル | スケジューラー | `channel_schedule` |
| エージェント | GitHub Copilot CLI | `agent_copilot_cli` |
| エージェント | OpenAI Codex CLI | `agent_codex_cli` |
| エージェント | エコー（テスト用） | `agent_echo` |

---

## クイックスタート

### 前提

- Linux / WSL 環境（Windowsネイティブは `pty` 非対応のため不可）
- [uv](https://github.com/astral-sh/uv) インストール済み
- Codex CLI または Copilot CLI インストール済み
- Discord ボット作成済み

### Step 1: クローン

```bash
git clone https://github.com/kensak/YaClaw.git
cd YaClaw
```

### Step 2: `.env` ファイルを作成

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
            "agent": "codex"
        }
    },
    "agent": {
        "codex": {
            "plugin": "agent_codex_cli",
            "work_dir": "workspace/codex"
        }
    }
}
```

> `agent.[name].plugin` の値は `plugins/` フォルダー内のPythonファイル名（拡張子なし）です。

### Step 4: 起動

```bash
uv run main.py
```

### Step 5: Discordで試す

設定したチャンネルにメッセージを送り、AIからの返信が来れば成功です！

---

## 設定サンプル

`examples/` フォルダーにさまざまな設定例があります。

| ファイル | 内容 |
|----------|------|
| `settings_minimal_codex.json` | Codex CLIの最小構成 |
| `settings_minimal_copilot.json` | Copilot CLIの最小構成 |
| `settings_schedule.json` | スケジューラーを使った自動タスク |
| `settings_forward_test.json` | エージェント間転送のテスト |

---

## ログ

ログは `log/log-YYYYMMDD.json` に記録されます。`jq` を使って柔軟にフィルタリングできます。

```bash
# trace ログのみ表示
cat log/log-20260301.json | jq -c -r 'select(.type == "trace") | [.time, .message] | join(" ")'
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

### チャンネルプラグイン（基本）

シンプルなチャンネルの実装例として `plugins/channel_random_talker.py` を参考にしてください。

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
- `create_request_skeleton()` を使うと `from` / `to` / `reply_to` が自動設定された辞書を取得できる。
- `handle_response_message` はフレームワーク内部のキューによってシリアライズされて呼び出されるため、並行呼び出しを心配する必要はない。

---

### SNSチャンネルプラグイン

Discord のような外部サービスと連携するチャンネルの実装例として `plugins/channel_discord.py` を参考にしてください。

```python
from yaclaw.channel import Channel

class MySnsBotChannel(Channel):

    async def initialize(self, channel_name, channel_settings):
        # settings.json から認証情報などを読み取る
        self.token = channel_settings.get("bot_token", None)
        if self.token is None:
            return False   # 必須設定が無ければ False で起動中止
        # SDKクライアントの生成など
        self.client = MyBotClient()
        return True

    async def start_listener(self):
        # 外部ライブラリの非同期イベントループをここで起動する。
        # この関数はループが終了するまでブロックし続ける。
        @self.client.on_message
        async def on_message(msg):
            await self.handle_request_message(msg.text)

        await self.client.start(self.token)

    async def handle_response_message(self, response):
        body = response.get("body", "")
        if not body:          # 空返答はスキップ
            return
        await self.client.send(body)

    async def stop(self):
        await self.client.close()   # クライアントを適切にクローズする

    async def finalize(self):
        pass
```

**ポイント**

- `start_listener` 内で外部ライブラリのイベントループを `await` する。
- `response["body"]` が空の場合は何もしないなど、堅牢な実装を心がける。
- `stop` でクライアントを必ずクローズし、`asyncio.TaskGroup` のタスクが正常終了できるようにする。

---

### エージェントプラグイン

エージェントの実装例として `plugins/agent_echo.py` を参考にしてください。

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
- `handle_response_message(response)` を呼ぶと、`response["to"]` の宛先（チャンネルまたは次のエージェント）へ自動でルーティングされる。

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

本プロジェクトは実験的であり、セキュリティ対策は最小限です。情報漏洩・AIの予期しない動作（ハルシネーション等）に対する対策は利用者自身の責任で行ってください。本プログラムの利用により生じた損害について作者は一切の責任を負いません。

---

## ライセンス

[MIT License](LICENSE)

