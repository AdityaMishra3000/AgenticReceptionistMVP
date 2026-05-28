import os
import json
import logging
from fastapi import FastAPI, Form, HTTPException
from twilio.rest import Client as TwilioClient
from dotenv import load_dotenv

# ── LLM clients ──────────────────────────────────────────────────────────────
from google import genai
from google.genai import types as genai_types
from groq import Groq

load_dotenv()

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# ── Config ────────────────────────────────────────────────────────────────────
GEMINI_API_KEY      = os.getenv("GEMINI_API_KEY")
GEMINI_MODEL        = os.getenv("GEMINI_MODEL", "gemini-2.0-flash")
GROQ_API_KEY        = os.getenv("GROQ_API_KEY")
GROQ_MODEL          = os.getenv("GROQ_MODEL", "llama-3.3-70b-versatile")
TWILIO_SID          = os.getenv("TWILIO_SID")
TWILIO_TOKEN        = os.getenv("TWILIO_TOKEN")
TWILIO_FROM         = os.getenv("TWILIO_WHATSAPP_FROM", "whatsapp:+14155238886")

# ── LLM setup ─────────────────────────────────────────────────────────────────
gemini_client = genai.Client(api_key=GEMINI_API_KEY)
groq_client   = Groq(api_key=GROQ_API_KEY)
twilio_client = TwilioClient(TWILIO_SID, TWILIO_TOKEN)

# ── In-memory conversation store  (phone_number → list of messages) ───────────
# Each message: {"role": "user"|"assistant", "content": "..."}
conversations: dict[str, list[dict]] = {}

app = FastAPI()

# ── System prompt ─────────────────────────────────────────────────────────────
SYSTEM_PROMPT = """
You are an AI assistant for a Mumbai real estate broker named Ramesh Bhai.
Your job is to qualify rental property leads through a natural, friendly conversation.

COLLECT these details one at a time — never ask more than ONE question per message:
- contact_name       : caller's name
- contact_phone      : 10-digit mobile number
- bhk                : 1BHK / 2BHK / 3BHK
- area               : preferred area/locality in Mumbai
- budget_min         : minimum monthly rent (INR)
- budget_max         : maximum monthly rent (INR)
- occupancy          : family or bachelor
- furnishing         : furnished / semi-furnished / unfurnished
- move_in_timeline   : immediate / within 1 month / 1-3 months / flexible

RULES:
1. Respond in whatever language the user writes in — Hindi, English, or Hinglish.
2. Ask only ONE question per message, keep it conversational and short.
3. If the user is vague ("thoda sasta", "kahin bhi"), ask a gentle clarifying follow-up.
4. Never invent or confirm property availability — say "Ramesh Bhai will check and confirm."
5. If the user asks something outside property search, say you will connect them with the broker.
6. If the user seems frustrated or angry (2+ negative messages), immediately say:
   "Main aapko Ramesh Bhai se connect karta hoon abhi." and set escalate=true in the lead card.

WHEN all 9 details are collected (or user explicitly ends the conversation), output
your final friendly message AND append this block EXACTLY — no extra text after it:

---LEAD_CARD---
{
  "name": "",
  "phone": "",
  "bhk": "",
  "area": "",
  "budget_min": 0,
  "budget_max": 0,
  "occupancy": "",
  "furnishing": "",
  "timeline": "",
  "intent_score": "hot|warm|cold",
  "escalate": false
}
---END_LEAD_CARD---

Intent score rules:
- hot  : clear budget + timeline is immediate or within 1 month
- warm : has budget but flexible timeline, or timeline soon but vague budget
- cold : just exploring, no clear budget or timeline

Start the very first message (when conversation history is empty) with:
"Namaste! Main Ramesh Bhai ki taraf se bol raha hoon. Kya aap rent ke liye property dhundh rahe hain? 😊"
"""


# ── LLM call with Gemini → Groq fallback ─────────────────────────────────────

def call_gemini(history: list[dict]) -> str:
    """
    google-genai expects history as a list of Content objects.
    We separate the system prompt and pass conversation turns.
    """
    contents = []
    for msg in history:
        role = "user" if msg["role"] == "user" else "model"
        contents.append(
            genai_types.Content(
                role=role,
                parts=[genai_types.Part(text=msg["content"])]
            )
        )

    response = gemini_client.models.generate_content(
        model=GEMINI_MODEL,
        contents=contents,
        config=genai_types.GenerateContentConfig(
            system_instruction=SYSTEM_PROMPT,
            max_output_tokens=1024,
            temperature=0.4,
        ),
    )
    return response.text


def call_groq(history: list[dict]) -> str:
    messages = [{"role": "system", "content": SYSTEM_PROMPT}] + history
    response = groq_client.chat.completions.create(
        model=GROQ_MODEL,
        messages=messages,
        max_tokens=1024,
        temperature=0.4,
    )
    return response.choices[0].message.content


def get_llm_reply(history: list[dict]) -> str:
    """Try Gemini first; fall back to Groq on any error."""
    try:
        reply = call_gemini(history)
        logger.info("LLM: Gemini responded ok")
        return reply
    except Exception as e:
        logger.warning(f"Gemini failed ({e}), falling back to Groq…")

    try:
        reply = call_groq(history)
        logger.info("LLM: Groq fallback responded ok")
        return reply
    except Exception as e:
        logger.error(f"Groq also failed: {e}")
        raise


# ── Lead card handler ─────────────────────────────────────────────────────────

def handle_lead_card(reply: str, user_number: str) -> None:
    try:
        start = reply.index("---LEAD_CARD---") + len("---LEAD_CARD---")
        end   = reply.index("---END_LEAD_CARD---")
        card  = json.loads(reply[start:end].strip())

        logger.info(f"\n{'='*50}")
        logger.info(f"🔥 NEW LEAD — {user_number}")
        logger.info(json.dumps(card, indent=2, ensure_ascii=False))
        logger.info('='*50)

        # ── TODO Phase 2: replace prints with real actions ──────────────────
        # send_lead_to_broker_whatsapp(card)
        # save_to_google_sheet(card)
        # notify_broker_sms(card)
        # ────────────────────────────────────────────────────────────────────

    except (ValueError, json.JSONDecodeError) as e:
        logger.error(f"Lead card parse error: {e}")


# ── WhatsApp sender ───────────────────────────────────────────────────────────

def send_whatsapp(to: str, body: str) -> None:
    # Strip the lead card block before sending to user — they don't need to see JSON
    clean_body = body
    if "---LEAD_CARD---" in body:
        clean_body = body[:body.index("---LEAD_CARD---")].strip()

    twilio_client.messages.create(
        from_=TWILIO_FROM,
        to=to,
        body=clean_body,
    )


# ── Webhook endpoint ──────────────────────────────────────────────────────────

@app.post("/webhook")
async def webhook(From: str = Form(...), Body: str = Form(...)):
    user_number  = From   # e.g. whatsapp:+919XXXXXXXXX
    user_message = Body.strip()

    if not user_message:
        return {"status": "ignored"}

    # Init history for new users
    if user_number not in conversations:
        conversations[user_number] = []

    # Append user turn
    conversations[user_number].append({
        "role": "user",
        "content": user_message,
    })

    try:
        reply = get_llm_reply(conversations[user_number])
        logger.info(f"REPLY: {reply}")
    except Exception:
        reply = "Sorry, technical issue aa gayi. Thodi der baad try karein. 🙏"
        send_whatsapp(user_number, reply)
        return {"status": "llm_error"}

    # Append assistant turn
    conversations[user_number].append({
        "role": "assistant",
        "content": reply,
    })

    # Check for completed lead
    if "---LEAD_CARD---" in reply:
        handle_lead_card(reply, user_number)

    send_whatsapp(user_number, reply)
    return {"status": "ok"}


# ── Health check ──────────────────────────────────────────────────────────────

@app.get("/health")
async def health():
    return {"status": "running", "primary_llm": GEMINI_MODEL, "fallback_llm": GROQ_MODEL}


# ── Local dev entrypoint ──────────────────────────────────────────────────────

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True)