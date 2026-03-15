# LINE Bot Registration

A LINE bot is created using a **LINE Business Account + Messaging API**.

1. **Create a LINE Business Account**

    1. Go to <https://manager.line.biz/>
    2. Click **Create account**
    3. Log in with your personal LINE account
    4. Fill in the following details:
       - Account name
       - Business type
       - Email address

    This creates your **LINE Business Account**.

2. **Create a Messaging API channel**

    1. Go to [Account Manager](https://developers.line.biz/account/) and select your account
    2. Click **Chat** in the top bar
    3. Click **Messaging API** in the left menu
    4. Click the **Enable Messaging API** button
    5. Enter your developer information and click **Agree**
    6. Enter a provider name  
       A provider is **the unit used to manage LINE bots and APIs**.  
       Example: `YaClawProject`
    7. Leave the **Privacy policy** and **Terms of use** fields blank and click **OK**
    8. The Messaging API screen is displayed  
       Note down the following:  
       **Channel secret** → `CHANNEL_SECRET`  
       The Webhook URL can be left blank for now.

3. **Disable auto-reply messages**

    In Account Manager → **Response settings**, set:

    - Chat: **ON**
    - Auto-reply messages: **OFF**

    Without this, the LINE platform's built-in auto-reply will conflict with your bot.

4. **Add the bot as a friend**

    Open [LINE Developers Console](https://developers.line.biz/console/) and navigate to your channel page.  
    Select the **Messaging API** tab.  
    Scan the QR code shown there with your LINE app to add the bot as a friend.

5. **Issue a Channel access token**

    On the same **Messaging API** tab, click the **Issue** button under **Channel access token**.  
    Note down the issued token → `CHANNEL_ACCESS_TOKEN`

6. **Set the Webhook URL**

    On the same **Messaging API** tab, click **Edit** next to **Webhook URL** and enter your URL.  
    (The domain of the URL must be registered in the DNS at this point.)
    Example: `https://xyz.tail123abc.ts.net/webhook`
    Then turn **Use webhook** ON.

7. **Start the bot server**

    The bot program requires the following credentials:

    - `CHANNEL_SECRET`
    - `CHANNEL_ACCESS_TOKEN`

    Once the server is running, messages are processed in this flow:

    ```
    LINE user
        ↓
    LINE Platform
        ↓  webhook
    Bot server (YaClaw)
        ↓  API
    LINE Messaging API
    ```
