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
エージェント X ---{to: [Y, Z], reply_to: A}-------> エージェント Y
エージェント Y ---{to: Z, reply_to: A}-----------> エージェント Z
エージェント Z ---{to: A, via: [X,Y,Z]}----------> チャンネル A
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

