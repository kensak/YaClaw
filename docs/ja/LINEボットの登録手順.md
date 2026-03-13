# LINEボット登録手順

LINEボットは **LINE公式アカウント + Messaging API** を使って作成します。

1. LINE Businessアカウントを作成

	1. https://manager.line.biz/ にアクセス  
	2. 「アカウント作成」をクリック  
	3. LINE個人アカウントでログイン  
	4. 以下の情報を入力

	   - アカウント名
	   - 業種
	   - メールアドレス	     

	作成すると **LINE Businessアカウント** ができます。

2. Messaging APIチャネルを作成

	1. [アカウント・マネージャー](https://developers.line.biz/account/) にアクセスし、
      アカウントを選ぶ。
   2. 上部バーの「チャット」をクリック
   3. 左メニューから「Messaging API」をクリック
   4. 「Messaging APIを利用する」ボタンをクリック
   5. 開発者情報を入力し、「同意する」をクリック
	6. プロバイダー名を入力
      プロバイダーとは**LINEボットやAPIを管理するための単位**です。
      例: YaClawProject
   7. 「プライバシーポリシー」と「利用規約」は空のまま「OK」を押す。
   8. Messaging API画面が表示される
      次の情報をひかえておく。
      Channel secret -> CHANNEL_SECRET
      Webhook URLは空欄のままでよい。

3. 応答メッセージをOFFにする  

   アカウント・マネージャーの「応答設定」で

   - チャット: ON
   - 応答メッセージ: OFF

   これをしないとLINE側の自動返信とボットが競合します。  

4. ボットを友達追加  

   [LINE Developpers](https://developers.line.biz/console/)から
   チャンネルのページを開く。
   Messaging APIタブを選ぶ。
   表示されるQRコードをLINEで読み取るとボットを友達追加できます。  

5. Channel access tokenを発行

   同じくMessaging APIタブで、
   チャネルアクセストークンの「発行」ボタンを押す。
   発行されたトークンをひかえておく -> CHANNEL_ACCESS_TOKEN

6. Webhook URLを設定  

   同じくMessaging APIタブで、
   Webhook URLの「編集」ボタンを押してURLを設定します。  
   例: https://xyz.tail123abc.ts.net/webhook
   続けて「Webhookの利用」をONにします。

7. ボットサーバーを起動  

   ボットプログラムでは次の情報を使います。  

   - CHANNEL_SECRET
   - CHANNEL_ACCESS_TOKEN

   サーバーが起動すると  
   LINEユーザー  
   ↓  
   LINE Platform  
   ↓ webhook  
   ボットサーバー  
   ↓ API  
   LINE Messaging API
   という流れでメッセージが処理されます。  

