# LINEボット登録手順

LINEボットは **LINE公式アカウント + Messaging API** を使って作成します。

1. LINE公式アカウントを作成
	1. https://manager.line.biz/ にアクセス  
	2. 「アカウント作成」をクリック  
	3. LINEアカウントでログイン  
	4. 以下の情報を入力
	   - アカウント名
	   - 業種
	   - メールアドレス	     
	作成すると **LINE公式アカウント（ボットの本体）** ができます。

2. LINE Developers Consoleでプロバイダーを作成
	1. https://developers.line.biz/console/ にアクセス
	2. 「プロバイダー作成」をクリック
	3. プロバイダー名を入力
   プロバイダーとは**LINEボットやAPIを管理するための単位**です。
   例: YaClawProject
  
3. Messaging APIチャネルを作成    
	1. 作成したプロバイダーを開く  
	2. 「Messaging API channel」を作成  
	3. 以下の情報を入力    
	    - Channel name  
	    - Channel description  
    	- Category  
    	- Subcategory  
    作成すると次の情報が発行されます。  
     Channel secret  
     Channel access token
    これを **ボットのプログラムで使用**します。  

4. Webhook URLを設定  
   Messaging API設定画面で  
   Webhook URL
   を設定します。  
   例: https://example.com/callback
   設定後  
   Webhook: ON
   にします。  

5. 応答メッセージをOFFにする  
   LINE公式アカウントの自動返信を無効化します。  
   設定場所  
   LINE Official Account Manager  
   ↓  
   応答設定  
   ↓  
   応答メッセージ: OFF
   これをしないとLINE側の自動返信とボットが競合します。  

6. ボットを友達追加  
   Messaging API設定画面に表示されるQRコードをLINEで読み取ると    
   ボットを友達追加できます。  
  
7. ボットサーバーを起動  
   ボットプログラムでは次の情報を使います。  
   CHANNEL_SECRET  
   CHANNEL_ACCESS_TOKEN
   サーバーが起動すると  
   LINEユーザー  
   ↓  
   LINE Platform  
   ↓ webhook  
   ボットサーバー  
   ↓ API  
   LINE Messaging API
   という流れでメッセージが処理されます。  

まとめ  
LINEボット作成の流れ  
  
1. LINE公式アカウント作成  
2. Developers Consoleでプロバイダー作成  
3. Messaging APIチャネル作成  
4. Webhook URL設定  
5. 自動返信OFF  
6. ボットを友達追加  
7. ボットサーバー起動
