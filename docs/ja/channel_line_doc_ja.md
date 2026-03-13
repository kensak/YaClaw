# LINE チャンネルプラグイン (`channel_line`)

このプラグインは YaClaw を [LINE Messaging API](https://developers.line.biz/ja/docs/messaging-api/) と連携させます。LINEからAIエージェントへメッセージを送り、返答をLINEで受け取ることができます。

---

## 前提条件

LINE Bot SDK v3 をインストールします。

```bash
uv sync
# または手動で:
pip install "line-bot-sdk>=3.0.0"
```

---

## LINEボットの登録

プラグインを使う前に、LINE Messaging API チャンネルを作成する必要があります。  
手順は [LINEボットの登録手順.md](LINEボットの登録手順.md) を参照してください。

---

## settings.json

`channel` の下に `line` エントリを追加します。

```json
{
    "channel": {
        "line": {
            "plugin": "channel_line",
            "channel_access_token": "${LINE_CHANNEL_ACCESS_TOKEN}",
            "channel_secret": "${LINE_CHANNEL_SECRET}",
            "target_id": "${LINE_TARGET_ID}",
            "host": "0.0.0.0",
            "port": 8000,
            "webhook_path": "/webhook",
            "agent": "opencode"
        }
    },
    ...
}
```

すぐ使えるコピーは `examples/settings_line.json` を参照してください。

### 設定キー一覧

| キー | 必須 | デフォルト | 説明 |
|-----|------|-----------|------|
| `plugin` | ✅ | — | `"channel_line"` を指定 |
| `channel_access_token` | ✅ | — | LINE Developers Console で発行した長期チャンネルアクセストークン |
| `channel_secret` | ✅ | — | チャンネルシークレット（Webhook の署名検証に使用） |
| `agent` | ✅ | — | メッセージを転送するエージェントの名前 |
| `target_id` | — | `null`（全員受付） | このLINEユーザーID（`U…`）またはグループID（`C…`）からのメッセージのみ処理する |
| `host` | — | `"0.0.0.0"` | Webhook HTTPサーバーのバインドアドレス |
| `port` | — | `8000` | Webhook HTTPサーバーのポート |
| `webhook_path` | — | `"/webhook"` | Webhook エンドポイントの URL パス |

### .env

```bash
LINE_CHANNEL_ACCESS_TOKEN=チャンネルアクセストークン
LINE_CHANNEL_SECRET=チャンネルシークレット
LINE_TARGET_ID=Uxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx   # 任意: 自分のLINEユーザーID
```

自分のLINEユーザーIDを調べるには、ボットにメッセージを送り、LINE Developers Console の Webhook イベントログ（または受信ログ）で `source.userId` を確認してください。

---

## HTTPS の設定

LINE の Webhook URL は **信頼された認証局（CA）が署名した HTTPS** でなければなりません。自己署名証明書は拒否されます。

### 方法 A — Tailscale Funnel（常時稼働のホームサーバーに推奨）

[Tailscale Funnel](https://tailscale.com/kb/1223/tailscale-funnel) はローカルポートを公開インターネットに HTTPS で公開します。証明書は Tailscale が管理（信頼済み CA）し、URL はマシン名に紐づいて**固定**されます。

```bash
# Tailscale をインストールしてログイン後:
tailscale funnel 8000
```

発行される Webhook URL の例:

```
https://your-machine.taile12345.ts.net/webhook
```

再起動しても URL は変わりません。

### 方法 B — ngrok（ローカル開発・動作確認向け）

```bash
ngrok http 8000
```

`https://…ngrok-free.app` の URL を Webhook URL に設定します。無料プランでは**起動のたびに URL が変わる**ため、その都度 LINE Developers Console を更新する必要があります。

### 方法 C — Let's Encrypt（公開サーバー）

ドメイン名付きの VPS で運用する場合は、[Certbot](https://certbot.eff.org/) で証明書を取得し、nginx 等のリバースプロキシを YaClaw の前に置いてください。

---

## 動作の流れ

```
LINEユーザー ──[メッセージ]──▶ LINE Platform ──[HTTPS Webhook POST]──▶ YaClaw (channel_line)
                                                                              │
                                                                handle_request_message()
                                                                              │
                                                                         エージェントキュー
                                                                              │
                                                                handle_response_message()
                                                                              │
LINEユーザー ◀──[返信]──── LINE Platform ◀──[Reply API]──────────────────
```

1. ユーザーがメッセージを送ると、LINE Platform が Webhook エンドポイントへ HTTPS POST を送信
2. `channel_line` が HMAC-SHA256 署名を検証し、イベントをパース
3. `target_id` が設定されている場合、対象外のユーザー/グループからのメッセージをフィルタリング
4. メッセージテキストを `handle_request_message()` でエージェントへ転送
5. エージェントが返答すると `handle_response_message()` が **Reply API** でLINEへ送信

---

## 既知の制限事項

### Reply API — 30秒タイムアウト

Reply API の `reply_token` は、元のユーザーメッセージから **30秒で失効**します。AIの処理が30秒を超えると返信に失敗し、`warning` レベルのログが記録された上でレスポンスは破棄されます。

**回避策**: Push API に切り替えることで解決できます。`target_id` の設定が必須で、`handle_response_message()` の一部を変更します。

```python
# reply_message() を push_message() に置き換える:
from linebot.v3.messaging import PushMessageRequest
await self.messaging_api.push_message(
    PushMessageRequest(to=self.target_id, messages=messages)
)
```

### Reply API — トークンは1回限り

`reply_token` は **1度しか使えません**。エージェントから複数のレスポンスが届いた場合（`[...]` など中間チャンクの後に最終返答が来る場合）、最初の実テキストレスポンスのみが送信され、2回目以降は破棄されます。

### ローディングアニメーション — 1:1 チャットのみ対応

`[...]`（思考中インジケーター）は LINE の [ローディングアニメーション API](https://developers.line.biz/ja/docs/messaging-api/use-loading-indicator/) を利用しますが、**1:1 のダイレクトメッセージ（UserSource）のみ対応**しています。グループチャットやルームでは自動的にスキップされます。

### メッセージ長の制限

LINE の Reply API は **1回の返信につき最大5メッセージ**、1メッセージあたり最大 **5,000文字**です。25,000文字を超えるレスポンスは切り捨てられ、警告がログに記録されます。

---

## トラブルシューティング

| 症状 | 考えられる原因 | 対処法 |
|------|--------------|--------|
| Webhook 検証が失敗する（400） | `channel_secret` が一致しない | `.env` と LINE Developers Console のシークレットを確認 |
| メッセージが届かない | Webhook が無効、または URL が違う | **Webhookの利用** を ON にして URL とパスを確認 |
| ログに `InvalidSignatureError` | シークレットが正しくない | `channel_secret` が正しいか確認 |
| 返信が API エラーで失敗する | `reply_token` が失効（30秒超） | Push API への切り替えを検討（上記参照） |
| Webhook URL が LINE に拒否される | HTTP または自己署名証明書 | 信頼된 CA の HTTPS を使用（Tailscale Funnel / ngrok / Let's Encrypt） |
| 想定外のユーザーからのメッセージが届く | `target_id` が未設定 | `settings.json` の `target_id` に自分のユーザーIDを設定 |
