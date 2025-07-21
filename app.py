import os
import google.generativeai as genai
from flask import Flask, request
from twilio.twiml.messaging_response import MessagingResponse
from twilio.rest import Client

# --- CONFIGURATION ---
# Load credentials from environment variables (we will set these in Render)
TWILIO_ACCOUNT_SID = os.getenv("TWILIO_ACCOUNT_SID")
TWILIO_AUTH_TOKEN = os.getenv("TWILIO_AUTH_TOKEN")
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
DR_SHAGUN_NUMBER = "whatsapp:+917088744604" # Dr. Shagun's number in WhatsApp format
TWILIO_NUMBER = os.getenv("TWILIO_NUMBER") # Your Twilio Sandbox number

# Configure Gemini AI and Twilio Client
genai.configure(api_key=GEMINI_API_KEY)
model = genai.GenerativeModel('gemini-1.5-flash')
client = Client(TWILIO_ACCOUNT_SID, TWILIO_AUTH_TOKEN)

# Load the knowledge base
with open('knowledge.txt', 'r') as f:
    KNOWLEDGE_BASE = f.read()

# Flask app setup
app = Flask(__name__)

# --- FUNCTIONS (Identical to before) ---
def should_escalate(query):
    prompt = f"""
    You are an AI assistant for a dental clinic. Your only job is to decide if a customer query should be answered by you or escalated to the doctor.
    Your knowledge base is strictly limited to the following information:
    --- KNOWLEDGE BASE START ---
    {KNOWLEDGE_BASE}
    --- KNOWLEDGE BASE END ---

    Analyze the following customer query: "{query}"

    If the query can be answered with 100% confidence using ONLY the information in the knowledge base, respond with "NO".
    If the query is about pricing, pain, symptoms, medical advice, a specific patient's case, an emergency, or anything NOT explicitly covered in the knowledge base, you MUST respond with "YES".

    Your response must be only one word: YES or NO.
    """
    response = model.generate_content(prompt)
    decision = response.text.strip().upper()
    print(f"Query: '{query}'. Escalation decision: {decision}")
    return decision == "YES"

def get_direct_answer(query):
    prompt = f"""
    You are a friendly and professional AI assistant for Shagun Dental Studio.
    Using the information below, answer the customer's query.
    --- KNOWLEDGE BASE START ---
    {KNOWLEDGE_BASE}
    --- KNOWLEDGE BASE END ---

    Customer Query: "{query}"
    Your Answer:
    """
    response = model.generate_content(prompt)
    return response.text.strip()

# --- WEBHOOK ROUTE ---
@app.route("/webhook", methods=["POST"])
def webhook():
    incoming_msg = request.values.get('Body', '').strip()
    from_number = request.values.get('From', '')

    # --- CORE LOGIC ---
    # Check if the message is from Dr. Shagun giving instructions
    if from_number == DR_SHAGUN_NUMBER and incoming_msg.lower().startswith("reply to"):
        try:
            parts = incoming_msg.split(":")
            # Format: "Reply to whatsapp:+91...: [The actual reply]"
            target_customer_number = parts[0].replace("Reply to", "").strip()
            reply_content = parts[1].strip()
            
            final_message = f"An update from Dr. Shagun:\n\n{reply_content}"
            # Use Twilio client to send the message
            client.messages.create(from_=TWILIO_NUMBER, to=target_customer_number, body=final_message)
        except Exception as e:
            print(f"Error processing doctor's reply: {e}")
        # Return an empty response to Twilio so it doesn't reply to the doctor
        return str(MessagingResponse()), 200

    # Otherwise, it's a customer query
    else:
        if should_escalate(incoming_msg):
            # Escalate to Dr. Shagun
            response_text = "Thank you for your query. I am consulting with Dr. Shagun and will get back to you shortly."
            escalation_msg = f"--- NEW CUSTOMER QUERY ---\nFrom: {from_number}\nQuery: {incoming_msg}\n\nTo respond, start your message with: 'Reply to {from_number}: '"
            client.messages.create(from_=TWILIO_NUMBER, to=DR_SHAGUN_NUMBER, body=escalation_msg)
        else:
            # Answer directly
            response_text = get_direct_answer(incoming_msg)
        
        # Create a TwiML response to reply to the customer
        twiml_response = MessagingResponse()
        twiml_response.message(response_text)
        return str(twiml_response), 200

if __name__ == "__main__":
    app.run(debug=True, host="0.0.0.0", port=int(os.environ.get("PORT", 8080)))