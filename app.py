from slack_bolt import App
from slack_bolt.adapter.flask import SlackRequestHandler
from flask import Flask, request, jsonify
from dotenv import load_dotenv
import os

# Load environment variables from .env (for local dev)
load_dotenv()

# Get Slack credentials from environment
SLACK_BOT_TOKEN = os.environ.get("SLACK_BOT_TOKEN")
SLACK_SIGNING_SECRET = os.environ.get("SLACK_SIGNING_SECRET")

# Initialize Slack and Flask apps
app = App(token=SLACK_BOT_TOKEN, signing_secret=SLACK_SIGNING_SECRET)
flask_app = Flask(__name__)
handler = SlackRequestHandler(app)

# Route for Slack event requests
@flask_app.route("/slack/events", methods=["GET", "POST"])
def slack_events():
    if request.method == "GET":
        return "This is the Slack bot endpoint. Please POST to this URL.", 200

    data = request.get_json()
    if data and data.get("type") == "url_verification":
        return jsonify({"challenge": data.get("challenge")})
    return handler.handle(request)

# Handle when user @mentions the bot
@app.event("app_mention")
def handle_mention(event, say):
    user = event.get("user", "unknown")
    say(f"Hi <@{user}>! Ready to place a bet?")

# Run on port provided by Render, bind to all interfaces
if __name__ == "__main__":
    port = int(os.environ.get("PORT", 3000))
    flask_app.run(host="0.0.0.0", port=port)
