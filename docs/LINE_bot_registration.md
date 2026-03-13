# LINE Bot Registration

A LINE bot is created using a **LINE Official Account + Messaging API**.

1. **Create a LINE Official Account**
    1. Go to <https://manager.line.biz/>
    2. Click **Create account**
    3. Log in with your LINE account
    4. Fill in the following details:
       - Account name
       - Business type
       - Email address

    This creates your **LINE Official Account** — the body of the bot.

2. **Create a Provider in LINE Developers Console**
    1. Go to <https://developers.line.biz/console/>
    2. Click **Create a provider**
    3. Enter a provider name

    A provider is **the unit used to manage LINE bots and APIs**.  
    Example: `YaClawProject`

3. **Create a Messaging API channel**
    1. Open the provider you just created
    2. Click **Create a Messaging API channel**
    3. Fill in the following details:
       - Channel name
       - Channel description
       - Category
       - Subcategory

    Once created, the following credentials are issued:
    - **Channel secret**
    - **Channel access token**

    These are used in the bot program.

4. **Set the Webhook URL**

    In the Messaging API settings page, set the **Webhook URL**.  
    Example: `https://example.com/webhook`

    After setting it, turn **Use webhook** ON.

5. **Disable auto-reply messages**

    Disable the automatic reply feature of the LINE Official Account.

    Location:  
    LINE Official Account Manager → Response settings → **Auto-reply messages: OFF**

    Without this, the LINE platform's built-in auto-reply will conflict with your bot.

6. **Add the bot as a friend**

    Scan the QR code shown in the Messaging API settings page with your LINE app to add the bot as a friend.

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

---

## Summary

Steps to create a LINE bot:

1. Create a LINE Official Account
2. Create a Provider in Developers Console
3. Create a Messaging API channel
4. Set the Webhook URL
5. Disable auto-reply
6. Add the bot as a friend
7. Start the bot server
