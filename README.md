# AgenticReceptionistMVP

WhatsApp AI receptionist bot for qualifying real estate leads.

## Setup

1. Clone the repo

git clone https://github.com/AdityaMishra3000/AgenticReceptionistMVP.git
cd AgenticReceptionistMVP

2. Create a virtual environment

python -m venv venv
source venv/bin/activate

3. Install dependencies
pip install -r requirements.txt

4. Create your .env
Copy .env.example to .env and fill in your own API keys.

5. Run the app
python main.py

6. Start ngrok
ngrok http 8000

7. Paste the ngrok webhook URL into Twilio Sandbox settings
/webhook
