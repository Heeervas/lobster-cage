# Google Setup Guide (gogcli)

This guide explains how to set up `gogcli` to allow your agent to access your Google account securely within the Lobster Cage environment.

## 📋 Prerequisites

Before starting the setup, ensure your `lobster-cage/.env` file contains the following variables:

1. **GEMINI_API_KEY**: Your Google Gemini API key.
2. **GOG_KEYRING_PASSWORD**: A strong password used to encrypt your Google credentials locally.

Example `.env` snippet:
```env
GEMINI_API_KEY=your_api_key_here
GOG_KEYRING_PASSWORD=your_secure_password_here
```

## 🤖 Setup Instructions

To initiate the link between your agent and Google account, give the agent the following exact prompt:

> "Help me set up gogcli so you can access my Google account. Use the file backend and the GOG_KEYRING_PASSWORD from my environment."

## ⏳ What to Expect

Once you provide the prompt, the agent will perform the following steps:

1. **Auth URL**: The agent will generate and provide a Google authentication URL.
2. **User Login**: Open the URL in your browser, log in to your Google account, and grant the requested permissions.
3. **Authorization Code**: Google will provide an authorization code. Copy this code.
4. **Agent Confirmation**: Paste the code back into the chat with the agent.
5. **Success**: The agent will confirm that the credentials have been saved and encrypted.

## 🔒 Privacy & Security

- **Encrypted Storage**: Your encrypted tokens are stored locally at [lobster-cage/data/gogcli](lobster-cage/data/gogcli). Due to the containerized environment, the `file` backend is used instead of the OS keychain.
- **Access Control**: Only the agent within your Docker environment can access these credentials, provided it has the `GOG_KEYRING_PASSWORD`.
- **Persistence**: The credentials [persist across container restarts](lobster-cage/docker-compose.yml#L184) thanks to the mounted volume.

---
*Note: Refer to [lobster-cage/README.md](lobster-cage/README.md) for more information on available services and tools.*
