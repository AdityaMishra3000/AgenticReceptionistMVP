# AgenticReceptionistMVP

AI receptionist bot for qualifying real leads.

## Setup

### 1. Clone the repo

```bash
git clone https://github.com/AdityaMishra3000/AgenticReceptionistMVP.git
cd AgenticReceptionistMVP
```

### 2. Create a virtual environment

```bash
python -m venv venv
source venv/bin/activate
```

### 3. Install dependencies

```bash
pip install -r requirements.txt
```

### 4. Create your `.env`

Copy `.env.example` to `.env` and fill in your own API keys.

```bash
cp .env.example .env
```

### 5. Run the app

```bash
python main.py
```

### 6. Start ngrok

```bash
ngrok http 8000
```

### 7. Configure Twilio Sandbox

Paste your ngrok URL into Twilio Sandbox settings:

```text
https://your-ngrok-url.ngrok-free.dev/webhook
```

---

## Project Structure (Phase 1)

```text
AgenticVoiceModel/
├── main.py
├── requirements.txt
├── README.md
├── .gitignore
└── .env.example
```

---

## Tech Stack

* Python
* FastAPI
* Twilio WhatsApp Sandbox
* Groq (LLaMA)
* Gemini
* Ngrok

---

## Current Status

* Bot is live and tested on real WhatsApp
* Responds correctly in Hinglish
* Gemini quota may fail temporarily
* Groq fallback works correctly
