import os
import google.generativeai as genai
from flask import Flask, request
from twilio.twiml.messaging_response import MessagingResponse
from twilio.rest import Client
import google.api_core.exceptions

# --- CONFIGURATION ---
TWILIO_ACCOUNT_SID = os.getenv("TWILIO_ACCOUNT_SID")
TWILIO_AUTH_TOKEN = os.getenv("TWILIO_AUTH_TOKEN")
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
DR_SHAGUN_NUMBER = "whatsapp:+919031807701"
TWILIO_NUMBER = os.getenv("TWILIO_NUMBER")

# --- INITIALIZATION ---
genai.configure(api_key=GEMINI_API_KEY)
generation_config = genai.GenerationConfig(temperature=0.7)
model = genai.GenerativeModel('gemini-1.5-flash', generation_config=generation_config)
client = Client(TWILIO_ACCOUNT_SID, TWILIO_AUTH_TOKEN)

try:
    with open('knowledge.txt', 'r') as f:
        KNOWLEDGE_BASE = f.read()
except FileNotFoundError:
    KNOWLEDGE_BASE = "No knowledge base found."

app = Flask(__name__)

# --- AI-POWERED FUNCTIONS ---

def triage_query(query):
    """Categorizes the user's query with more autonomy."""
    prompt = f"""
    You are a highly intelligent triage assistant for a dental clinic's WhatsApp bot. Your job is to categorize the user's query. Your judgment must be precise.

    1.  **CLINIC_INFO**: Questions about specific info found ONLY in the clinic's knowledge base below (hours, location, listed services).
        - Knowledge Base: "{KNOWLEDGE_BASE}"
    2.  **GENERAL_HEALTH**: Requests for general information about any dental concept, procedure, or hygiene (e.g., "what is an RCT?", "benefits of flossing?"). You should use your own vast knowledge for this.
    3.  **ESCALATE**: Questions implying a personal situation: mentions of specific pain, symptoms, issues with past treatments, asking for prices/costs, or emergencies.

    Analyze the query: "{query}"
    Respond with ONLY the category name: CLINIC_INFO, GENERAL_HEALTH, or ESCALATE.
    """
    try:
        response = model.generate_content(prompt)
        category = response.text.strip().upper()
        print(f"Query: '{query}'. Triage category: {category}")
        return category
    except Exception as e:
        print(f"!!! ERROR during triage: {e} !!!")
        return "ESCALATE"

def get_clinic_info_answer(query):
    """Answers based on the knowledge base."""
    # This function remains the same
    prompt = f"Using ONLY this info: '{KNOWLEDGE_BASE}', answer the query: '{query}'"
    try:
        response = model.generate_content(prompt)
        return response.text.strip()
    except Exception: return None

def get_general_health_answer(query):
    """Answers using general AI knowledge and adds a disclaimer."""
    prompt = f"""
    As a helpful dental assistant AI, answer the following general question: "{query}"
    IMPORTANT: End your response with a new line and this exact disclaimer: "Please note, this is general information and not a substitute for a professional dental consultation."
    """
    try:
        response = model.generate_content(prompt)
        return response.text.strip()
    except Exception: return None

def rephrase_doctor_reply(instruction):
    """Rephrases the doctor's note into a full sentence."""
    prompt = f"Rephrase the following doctor's instruction into a polite, complete sentence for a patient. Instruction: '{instruction}'"
    try:
        response = model.generate_content(prompt)
        return response.text.strip()
    except Exception:
        return f"An update from Dr. Shagun: {instruction}" # Fallback

# --- MAIN WEBHOOK ROUTE ---
@app.route("/webhook", methods=["POST"])
def webhook():
    incoming_msg = request.values.get('Body', '').strip()
    from_number = request.values.get('From', '')
    print(f"--- INCOMING ---\nFrom: {from_number}\nMessage: '{incoming_msg}'")

    # 1. Handle Doctor's Reply
    if from_number == DR_SHAGUN_NUMBER and incoming_msg.lower().startswith("reply to"):
        print("--- DOCTOR REPLY DETECTED ---")
        try:
            content = incoming_msg[len("Reply to "):]
            parts = content.split(':', 2)
            if len(parts) == 3:
                target_customer_number = f"{parts[0]}:{parts[1]}".strip()
                reply_instruction = parts[2].strip()
                
                # AI-powered rephrasing
                final_message = rephrase_doctor_reply(reply_instruction)
                
                print(f"Target: '{target_customer_number}', Original Instruction: '{reply_instruction}', Rephrased: '{final_message}'")
                client.messages.create(from_=TWILIO_NUMBER, to=target_customer_number, body=final_message)
                print("--- Doctor's reply sent. ---")
            else:
                print("!!! ERROR: Could not parse doctor's reply. !!!")
        except Exception as e:
            print(f"!!! ERROR PROCESSING DOCTOR'S REPLY: {e} !!!")
        return str(MessagingResponse()), 200

    # 2. Handle Customer Query
    else:
        print("--- CUSTOMER QUERY DETECTED ---")
        response_text = ""
        
        # Quick check for simple greetings
        if incoming_msg.lower() in ['hi', 'hello', 'hey', 'thanks', 'thank you', 'ok']:
            response_text = "Hello! How can I help you today regarding Shagun Dental Studio?"
        else:
            category = triage_query(incoming_msg)
            if category == "CLINIC_INFO":
                response_text = get_clinic_info_answer(incoming_msg)
            elif category == "GENERAL_HEALTH":
                response_text = get_general_health_answer(incoming_msg)
            else: # Covers ESCALATE and any other error
                response_text = "Thank you for your query. I am forwarding this to Dr. Shagun for a precise answer and will get back to you shortly."
                escalation_msg = f"--- NEW CUSTOMER QUERY ---\nFrom: {from_number}\nQuery: {incoming_msg}\n\nTo respond, start your message with: 'Reply to {from_number}: '"
                client.messages.create(from_=TWILIO_NUMBER, to=DR_SHAGUN_NUMBER, body=escalation_msg)
        
        if not response_text:
             response_text = "I'm sorry, I'm having a bit of trouble right now. Please try again in a moment."

        twiml_response = MessagingResponse()
        twiml_response.message(response_text)
        return str(twiml_response), 200

if __name__ == "__main__":
    app.run(debug=True, host="0.0.0.0", port=int(os.environ.get("PORT", 8080)))
