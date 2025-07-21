import os
import google.generativeai as genai
from flask import Flask, request
from twilio.twiml.messaging_response import MessagingResponse
from twilio.rest import Client

# --- CONFIGURATION ---
# Load credentials from environment variables
TWILIO_ACCOUNT_SID = os.getenv("TWILIO_ACCOUNT_SID")
TWILIO_AUTH_TOKEN = os.getenv("TWILIO_AUTH_TOKEN")
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
DR_SHAGUN_NUMBER = "whatsapp:+919031807701" # Dr. Shagun's number
TWILIO_NUMBER = os.getenv("TWILIO_NUMBER") # Your Twilio Sandbox number

# Configure Gemini AI and Twilio Client
genai.configure(api_key=GEMINI_API_KEY)
model = genai.GenerativeModel('gemini-1.5-flash')
client = Client(TWILIO_ACCOUNT_SID, TWILIO_AUTH_TOKEN)

# Load the knowledge base
try:
    with open('knowledge.txt', 'r') as f:
        KNOWLEDGE_BASE = f.read()
except FileNotFoundError:
    KNOWLEDGE_BASE = "No knowledge base found."

# Flask app setup
app = Flask(__name__)

# --- NEW TRIAGE AND RESPONSE FUNCTIONS ---

def triage_query(query):
    """Uses Gemini to categorize the user's query."""
    prompt = f"""
    You are a highly intelligent triage assistant for a dental clinic's WhatsApp bot. Your job is to categorize the user's query into one of four types.

    Here is the clinic's internal knowledge base for reference:
    --- KNOWLEDGE BASE START ---
    {KNOWLEDGE_BASE}
    --- KNOWLEDGE BASE END ---

    Analyze the user's query: "{query}"

    Categorize it into one of the following types. Respond with ONLY the category name:
    1.  **GREETING**: If the query is a simple greeting like "hello", "hi", "good morning", or a simple closing like "thank you", "ok".
    2.  **CLINIC_INFO**: If the query is asking for specific information found in the knowledge base (e.g., "what are your hours?", "where are you located?", "do you do root canals?").
    3.  **GENERAL_HEALTH**: If the query is a general dental health question that is NOT about a specific person's pain, symptoms, or ongoing treatment (e.g., "what is the best way to whiten teeth?", "how often should I floss?").
    4.  **ESCALATE**: If the query mentions specific pain, symptoms, a problem with an ongoing treatment, asks for a price for a procedure, seems like an emergency, or is about a specific patient's case. Anything that requires a doctor's personal attention.

    Examples:
    - "hi": GREETING
    - "what time do you close?": CLINIC_INFO
    - "is it better to use an electric or manual toothbrush?": GENERAL_HEALTH
    - "my tooth is hurting a lot since yesterday": ESCALATE
    - "how much for a dental implant?": ESCALATE

    Query: "{query}"
    Category:
    """
    try:
        response = model.generate_content(prompt)
        category = response.text.strip().upper()
        print(f"Query: '{query}'. Triage category: {category}")
        return category
    except Exception as e:
        print(f"Error during triage: {e}")
        return "ESCALATE" # Default to escalation if triage fails

def get_clinic_info_answer(query):
    """Generates an answer based on the knowledge base."""
    prompt = f"""
    You are a friendly and professional AI assistant for Shagun Dental Studio.
    Using ONLY the information from the knowledge base below, answer the customer's query.
    --- KNOWLEDGE BASE START ---
    {KNOWLEDGE_BASE}
    --- KNOWLEDGE BASE END ---

    Customer Query: "{query}"
    Your Answer:
    """
    response = model.generate_content(prompt)
    return response.text.strip()

def get_general_health_answer(query):
    """Generates an answer for a general health question with a disclaimer."""
    prompt = f"""
    You are a helpful and knowledgeable dental assistant AI. Answer the following general dental health question in a clear and informative way.
    IMPORTANT: You are not a doctor. End your response with a clear disclaimer on a new line: "Please note, this is general information and not a substitute for a professional dental consultation. For specific advice, please consult with a dentist."

    Question: "{query}"
    Answer:
    """
    response = model.generate_content(prompt)
    return response.text.strip()

# --- MAIN WEBHOOK ROUTE ---
@app.route("/webhook", methods=["POST"])
def webhook():
    incoming_msg = request.values.get('Body', '').strip()
    from_number = request.values.get('From', '')
    print(f"--- INCOMING MESSAGE ---")
    print(f"From: {from_number}")
    print(f"Message: '{incoming_msg}'")

    # --- CORE LOGIC ---
    # 1. Check if the message is from Dr. Shagun giving instructions
    if from_number == DR_SHAGUN_NUMBER and incoming_msg.lower().startswith("reply to"):
        print("--- DOCTOR REPLY DETECTED ---")
        try:
            parts = incoming_msg.split(":", 1)
            target_customer_number_raw = parts[0].replace("Reply to", "")
            target_customer_number = target_customer_number_raw.strip()
            reply_content = parts[1].strip()
            
            print(f"Target Customer Number: '{target_customer_number}'")
            print(f"Reply Content: '{reply_content}'")
            
            final_message = f"An update from Dr. Shagun:\n\n{reply_content}"
            
            client.messages.create(from_=TWILIO_NUMBER, to=target_customer_number, body=final_message)
            print("--- Doctor's reply sent successfully. ---")

        except Exception as e:
            print(f"!!! ERROR PROCESSING DOCTOR'S REPLY: {e} !!!")
        # Return an empty response to Twilio so it doesn't reply to the doctor
        return str(MessagingResponse()), 200

    # 2. If not from the doctor, triage the customer's query
    else:
        print("--- CUSTOMER QUERY DETECTED ---")
        # Quick check for simple greetings to avoid unnecessary API calls
        if incoming_msg.lower() in ['hi', 'hello', 'hey', 'hlo', 'good morning', 'good evening', 'ok', 'thank you', 'thanks']:
             category = "GREETING"
             print("Triage category: GREETING (Quick Check)")
        else:
            category = triage_query(incoming_msg)

        response_text = ""

        if category == "GREETING":
            response_text = "Hello! How can I help you today regarding Shagun Dental Studio?"
        elif category == "CLINIC_INFO":
            response_text = get_clinic_info_answer(incoming_msg)
        elif category == "GENERAL_HEALTH":
            response_text = get_general_health_answer(incoming_msg)
        elif category == "ESCALATE":
            response_text = "Thank you for your query. I am forwarding this to Dr. Shagun for a precise answer and will get back to you shortly."
            escalation_msg = f"--- NEW CUSTOMER QUERY ---\nFrom: {from_number}\nQuery: {incoming_msg}\n\nTo respond, start your message with: 'Reply to {from_number}: '"
            client.messages.create(from_=TWILIO_NUMBER, to=DR_SHAGUN_NUMBER, body=escalation_msg)
        else: # Fallback for any unknown category
            response_text = "I'm sorry, I'm not sure how to handle that. I am forwarding your message to the clinic staff for assistance."
            escalation_msg = f"--- UNHANDLED QUERY ---\nFrom: {from_number}\nQuery: {incoming_msg}\n\nTo respond, start your message with: 'Reply to {from_number}: '"
            client.messages.create(from_=TWILIO_NUMBER, to=DR_SHAGUN_NUMBER, body=escalation_msg)
        
        # 3. Reply to the customer
        twiml_response = MessagingResponse()
        twiml_response.message(response_text)
        return str(twiml_response), 200

if __name__ == "__main__":
    app.run(debug=True, host="0.0.0.0", port=int(os.environ.get("PORT", 8080)))

