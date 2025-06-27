from slack_bolt import App
from slack_bolt.adapter.flask import SlackRequestHandler
from flask import Flask, request, jsonify
from dotenv import load_dotenv
import os

load_dotenv()

app = App(
    token=os.environ["SLACK_BOT_TOKEN"],
    signing_secret=os.environ["SLACK_SIGNING_SECRET"]
)

flask_app = Flask(__name__)
handler = SlackRequestHandler(app)

@flask_app.route("/slack/events", methods=["POST"])
def slack_events():
    data = request.get_json()
    if data.get("type") == "url_verification":
        return jsonify({"challenge": data.get("challenge")})
    return handler.handle(request)

@app.event("app_mention")
def handle_mention(event, say):
    user = event['user']
    say(f"Hi <@{user}>! Ready to place a bet?")

if __name__ == "__main__":
    flask_app.run(port=3000)
