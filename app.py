from slack_bolt import App
from slack_bolt.adapter.flask import SlackRequestHandler
from flask import Flask, request, jsonify
from dotenv import load_dotenv
import openai
import os
import json
import re

# Load environment variables
load_dotenv()

SLACK_BOT_TOKEN = os.environ.get("SLACK_BOT_TOKEN")
SLACK_SIGNING_SECRET = os.environ.get("SLACK_SIGNING_SECRET")
OPENAI_API_KEY = os.environ.get("OPENAI_API_KEY")

openai.api_key = OPENAI_API_KEY

# Set up Slack and Flask apps
app = App(token=SLACK_BOT_TOKEN, signing_secret=SLACK_SIGNING_SECRET)
flask_app = Flask(__name__)
handler = SlackRequestHandler(app)

# ---------- OPENAI PARSING FUNCTION ----------
def extract_bet_details(message):
    prompt = f"""
You are a bot helping users place bets. Extract 3 pieces of info from this message:
1. The amount they want to bet (a number).
2. The team or option they are betting on.
3. The description of the event or match (like "Friday's match").

Input: "{message}"

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
        response = openai.ChatCompletion.create(
            model="gpt-4o",
            messages=[
                {"role": "system", "content": "You are a helpful Slack betting assistant."},
                {"role": "user", "content": prompt}
            ],
            temperature=0.2
        )
        text = response['choices'][0]['message']['content']
        print("🧠 OpenAI Raw Output:", text)

        # Extract JSON using regex (handles triple backticks etc.)
        match = re.search(r'\{.*\}', text, re.DOTALL)
        if match:
            return json.loads(match.group(0))
        else:
            return {}
    except Exception as e:
        print("❌ OpenAI error:", e)
        return {}

# ---------- SLACK EVENTS ROUTE ----------
@flask_app.route("/slack/events", methods=["GET", "POST"])
def slack_events():
    if request.method == "GET":
        return "This is the Slack bot endpoint. Please POST to this URL.", 200

    data = request.get_json()
    if data and data.get("type") == "url_verification":
        return jsonify({"challenge": data.get("challenge")})
    return handler.handle(request)

# ---------- HANDLE BOT MENTIONS ----------
@app.event("app_mention")
def handle_mention(event, say):
    user = event.get("user")
    text = event.get("text", "")

    # Remove bot mention from start of message
    message = text.split(" ", 1)[1] if " " in text else ""

    say(f"Got it, <@{user}>! Let me parse that...")

    bet = extract_bet_details(message)

    if bet and "amount" in bet and "option" in bet and "event_query" in bet:
        say(f"🧠 You want to bet *{bet['amount']}* credits on *{bet['option']}* for *{bet['event_query']}*.")
    else:
        say("❌ I couldn't understand your bet. Please try again with something like:\n`@Fynd-My-Bet 50 on India for Friday’s match`")

# ---------- RUN FLASK SERVER ----------
if __name__ == "__main__":
    port = int(os.environ.get("PORT", 3000))
    flask_app.run(host="0.0.0.0", port=port)
