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

> **Yet Another 'Claw'-like Tool — Use Your Favorite AI Coding CLI, Through Your Favorite Channel**
>
> Control your favorite AI CLI tool running in your favorite working folder, remotely through your Discord channel.

YaClawはOpenClawの小さな変異種です。あなたがDiscordチャンネルから送ったメッセージをインタラクティブ・モードで動作するAIコーディングCLIツール（Codex CLI, Copilot CLI）へルーティングし、AIからの回答をチャンネルへ返信します。

AIコーディングCLIツールは指定されたフォルダーでインタラクティブ・モードで起動されます。再起動までは同じセッションが続きます。普段あなたが使っている環境がそのまま利用できるため、MCPやスキルなどの仕組みもまったく同じように使えます。

新たなチャンネル（Discordなど）とエージェント（AIコーディングCLIツールなど）への対応は、プラグインによって可能になります。

## インストール

```bash
git clone https://github.com/kensak/YaClaw.git
```

Windows OSはpythonのptyライブラリが未対応のため、そのまま使うことができません。WSLを通して使用してください。

## 使い方

```bash
cd YaClaw
uv run main.py
```

## 設定

`settings.json`でおこないます。

最小限の設定
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

Discordのボット（あらかじめ作成）IDとチャンネルIDはプロジェクトのルート・フォルダーに作った`.env`ファイルに書いてください。

.env
```
DISCORD_BOT_TOKEN=xyz...
DISCORD_CHANNEL_ID=12345...
```

`agent.[agent_name].plugin` には`plugin/`フォルダーにあるプラグイン（pythonファイル）のファイル名（拡張子なし）をセットします。

* Codex CLI: `agent_codex_cli`
* Copilot CLI: `agent_copilot_cli`
* テスト用エコー・エージェント: `agent_echo`

## ログ

ログは`log/log-YYYYMMDD.json`に書かれます。

jq にパイプすることにより柔軟なフィルタリングが可能です。

例: タイプがtraceのログのみを表示する
```bash
cat log/log-20260301.json | jq -c -r 'select(.type == "trace") | [.time, .message] | join(" ")'
```

## 設計

### アクター

チャンネルとエージェントという二種類のアクターがあり、これらの間でメッセージをやりとりするモデルです。

* **チャンネル**: エージェントに対してリクエストを送り、レスポンスを受け取ります。レスポンスはキューによりシリアライズされます。

* **エージェント**: チャンネルや他のエージェントからのリクエストに対してレスポンスを返します。リクエストはキューによりシリアライズされます。

### メッセージのルーティング

`{from: A, to: X}`などはメッセージを表します。（メッセージの内容は省略されています。）

#### 基本動作

チャンネル A ---{from: A, to: X}--> エージェント X
エージェント X ---{from: X, to: A, via: X}--> チャンネル A

#### `reply_to` による返信先の変更

これは、例えば`schedule`チャンネル（HEARTBEATのように定期的にプロンプトをAIに処理させる）を実現するのに便利です。

チャンネル A ---{from: A, to: X, reply_to: B}--> エージェント X
エージェント X ---{from: X, to: B, via: X}--> チャンネル B

#### 転送

メッセージの送信時にあらかじめ転送先を指定しておくことができます。

チャンネル A ---{from: A, to: [X, Y, Z]}--> エージェント X
エージェント X ---{from: X, to: [Y, Z], reply_to: A, via: X}--> エージェント Y
エージェント Y ---{from: Y, to: Z, reply_to: A, via: [X, Y]}--> エージェント Z
エージェント Z ---{from: Z, to: A, via: [X, Y, Z]}--> チャンネル A

## 免責事項

このプロジェクトは実験的なものであり、セキュリティ面での考慮はほとんどされていません。SNSサービスや通信経路からの情報の漏洩にたいする対策は利用者自身で行ってください。AIコーディングCLIツールはハルシネーションを起こすなど思わぬ予想外の反応をすることがあります。ツールに対するデータの保護などの必要な対策は利用者自身で行ってください。本プログラムの利用により発生した損害について作者は一切の責任を負いません。

