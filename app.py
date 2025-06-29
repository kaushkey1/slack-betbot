from slack_bolt import App
from slack_bolt.adapter.flask import SlackRequestHandler
from flask import Flask, request, jsonify
from dotenv import load_dotenv
import openai
import os
import json
import re
from supabase import create_client, Client

# Load environment variables
load_dotenv()

# Slack and OpenAI credentials
SLACK_BOT_TOKEN = os.environ.get("SLACK_BOT_TOKEN")
SLACK_SIGNING_SECRET = os.environ.get("SLACK_SIGNING_SECRET")
OPENAI_API_KEY = os.environ.get("OPENAI_API_KEY")
SUPABASE_URL = os.environ.get("SUPABASE_URL")
SUPABASE_KEY = os.environ.get("SUPABASE_KEY")

openai.api_key = OPENAI_API_KEY
supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)

# Initialize Slack and Flask
app = App(token=SLACK_BOT_TOKEN, signing_secret=SLACK_SIGNING_SECRET)
flask_app = Flask(__name__)
handler = SlackRequestHandler(app)

# ---------- FUNCTION: Parse bet details ----------
def extract_bet_details(message):
    prompt = f"""
You are a bot helping users place bets. Extract 3 pieces of info from this message:
1. The amount they want to bet (a number).
2. The team or option they are betting on.
3. The description of the event or match (like \"Friday's match\").

Input: \"{message}\"

Only return a valid JSON object like this:
{{
  "amount": 50,
  "option": "India",
  "event_query": "Friday's match"
}}

If anything is missing or unclear, return an empty JSON object: {{}}
Do not return anything else.
"""

    try:
        print("📨 Sending message to OpenAI (legacy API)...", flush=True)
        response = openai.ChatCompletion.create(
            model="gpt-3.5-turbo",
            messages=[
                {"role": "system", "content": "You are a helpful Slack betting assistant."},
                {"role": "user", "content": prompt}
            ],
            temperature=0.2
        )
        text = response['choices'][0]['message']['content']
        print("🧠 OpenAI Raw Output:", text, flush=True)

        match = re.search(r'\{.*\}', text, re.DOTALL)
        if match:
            return json.loads(match.group(0))
        else:
            print("⚠️ No valid JSON found in OpenAI output", flush=True)
            return {}
    except Exception as e:
        print("❌ OpenAI exception:", e, flush=True)
        return {}

# ---------- FUNCTION: Get or Create User ----------
def get_or_create_user(slack_id, name):
    result = supabase.table("users").select("*").eq("slack_id", slack_id).execute()
    if result.data and len(result.data) > 0:
        return result.data[0]
    insert_result = supabase.table("users").insert({
        "slack_id": slack_id,
        "name": name,
        "credits": 100
    }).execute()
    return insert_result.data[0]

# ---------- FUNCTION: Find Matching Event ----------
def find_event_by_name(query):
    events = supabase.table("events").select("*").ilike("status", "%open%").execute()
    for event in events.data:
        if query.lower() in event["title"].lower():
            return event
    return None

# ---------- FUNCTION: Place Bet ----------
def place_bet(user, event, amount, option):
    if user["credits"] < amount:
        return False, "❌ You don't have enough credits."

    credit_update = supabase.table("users").update({
        "credits": user["credits"] - amount
    }).eq("id", user["id"]).execute()

    if not credit_update.data:
        return False, "❌ Failed to deduct credits."

    bet_insert = supabase.table("bets").insert({
        "user_id": user["id"],
        "event_id": event["id"],
        "amount": amount,
        "option": option
    }).execute()

    if not bet_insert.data:
        supabase.table("users").update({"credits": user["credits"]}).eq("id", user["id"]).execute()
        print("❌ Failed to insert bet. Response:", bet_insert, flush=True)
        return False, "❌ Bet insert failed. Your credits were restored."

    return True, f"✅ Bet placed! You bet *{amount}* credits on *{option}* for *{event['title']}*."

# ---------- ROUTE: Slack Events ----------
@flask_app.route("/slack/events", methods=["GET", "POST"])
def slack_events():
    if request.method == "GET":
        return "This is the Slack bot endpoint. Please POST to this URL.", 200
    data = request.get_json()
    if data and data.get("type") == "url_verification":
        return jsonify({"challenge": data.get("challenge")})
    return handler.handle(request)

# ---------- EVENT: Bot Mention ----------
@app.event("app_mention")
def handle_mention(event, say):
    user_id = event.get("user")
    text = event.get("text", "").strip().lower()
    message = text.split(" ", 1)[1] if " " in text else ""

    if "show open events" in message:
        print("📥 Detected 'show open events' command", flush=True)
        events = supabase.table("events").select("*").ilike("status", "%open%").execute()
        print("🧪 Raw ALL event data from Supabase:", events.data, flush=True)

        if not events.data:
            print("❌ Still no open events found", flush=True)
            say("📭 There are no open events right now.")
            return

        reply = "*🎯 Open Events:*\n"
        for idx, event in enumerate(events.data, 1):
            title = event["title"]
            options = ", ".join(event["options"]) if isinstance(event["options"], list) else str(event["options"])
            reply += f"{idx}. {title} — Options: {options}\n"

        say(reply)
        return

    if message.startswith("bet") and " on " in message and " for " in message:
        try:
            match = re.search(r'bet (\d+) on (.+?) for (.+)', message)
            if not match:
                raise ValueError("Invalid format")

            amount = int(match.group(1))
            option = match.group(2).strip()
            event_query = match.group(3).strip()

            slack_user_info = app.client.users_info(user=user_id)
            name = slack_user_info["user"]["real_name"]

            user = get_or_create_user(slack_id=user_id, name=name)
            event = find_event_by_name(event_query)

            if not event:
                say(f"❌ I couldn’t find any open event matching '{event_query}'")
                return

            try:
                success, response = place_bet(user, event, amount, option)
                say(response)
            except Exception as e:
                print("❌ Bet placement failed:", e, flush=True)
                say("❌ Something went wrong placing your bet. Please try again or contact support.")
            return
        except Exception as e:
            print("❌ Manual format parse error:", e, flush=True)
            say("❌ Invalid format. Try: `@Fynd-My-Bet bet 50 on India for India vs Pakistan`")
            return

    say(f"Got it, <@{user_id}>! Let me parse that...")
    bet = extract_bet_details(message)
    if not (bet and "amount" in bet and "option" in bet and "event_query" in bet):
        say("❌ I couldn't understand your bet. Try: `@Fynd-My-Bet bet 50 on India for Friday's match`")
        return

    slack_user_info = app.client.users_info(user=user_id)
    name = slack_user_info["user"]["real_name"]

    user = get_or_create_user(slack_id=user_id, name=name)
    event = find_event_by_name(bet["event_query"])

    if not event:
        say(f"❌ I couldn’t find any open event matching '{bet['event_query']}'")
        return

    success, response = place_bet(user, event, bet["amount"], bet["option"])
    say(response)

# ---------- START SERVER ----------
if __name__ == "__main__":
    port = int(os.environ.get("PORT", 3000))
    flask_app.run(host="0.0.0.0", port=port)