from fastapi import FastAPI
from fastapi import Query
from langchain_google_genai import ChatGoogleGenerativeAI
from langchain.schema import HumanMessage
import os
from dotenv import load_dotenv
from pydantic import BaseModel
import json
from duck_duck_go import SearchEngine, WebScraper, SearchOrchestrator
import requests
# Initialize search components
searcher = SearchEngine()
scraper = WebScraper()
orchestrator = SearchOrchestrator(searcher, scraper)

load_dotenv()

app = FastAPI()

class TripRequest(BaseModel):
    trip_id: str
    leg_id: str
    itinerary: dict
    message_type: str

class SendNotificationRequest(BaseModel):
    trip_id: str
    leg_id: str
    message: str

GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
if not GEMINI_API_KEY:
    raise RuntimeError("Missing GEMINI_API_KEY")

model = ChatGoogleGenerativeAI(
    model="gemini-2.5-pro-preview-03-25",
    google_api_key=GEMINI_API_KEY,
    temperature=0.7
)

DEFAULT_RESPONSE = {
    "to_send_notification": "Yo, couldn’t get the scoop this time",
    "quick_tips": {"tips": ["Give it another shot soon", "Bug support if it’s urgent", "Chill, we’ll figure it out"]},
    "extra_info": "Something went wonky on our end. Oops!"
}

@app.post("/generate")
async def chat_with_gemini(request: TripRequest):
    try:
        print("Received payload:", request.dict())

        if request.message_type.lower() == "weather":
            query_for_duck_duck = (
                f"form a precise prompt for what needs to be asked to search engine "
                f"to get the weather using this context {request}"
            )
            message = HumanMessage(content=query_for_duck_duck)
            
            query_we_got = model([message])
            query_we_got_content = str(query_we_got.content)
            
            results_json = orchestrator.execute(query_we_got_content)
            
            prompt = f"""
            Yo, here’s the weather scoop from this context {request} and {results_json}. 
            Return it as valid JSON with ONLY these keys:

            {{
                "to_send_notification": "a 15-word max tip that user should see that we could send to him that would be useful",
                "quick_tips": {{"tips": ["fun tip 1", "fun tip 2", "fun tip 3"]}},
                "extra_info": "1-2 chill sentences about the forecast"
            }}

            Requirements:
            - Make it sound like a cheeky agent reporting a tip
            - Keep it under 10 words for to_send_notification
            - Use double quotes for JSON compliance
            - Keep it concise, casual, and mobile-friendly
            - Add humor where it fits
            - Use factual weather data from search results
            - Match temperature units to destination (Celsius for Paris, Fahrenheit for US)
            - Return ONLY the specified JSON structure, no extra fields
            """

        elif request.message_type.lower() == "nearby_places":
            prompt = f"""
            Alright, boss, here’s the lowdown on nearby spots from this context {request}. 
            Return it as valid JSON with ONLY these keys:

            {{
                "to_send_notification": "a fun 10-word max tip like 'Check out these gems!'",
                "quick_tips": {{"tips": ["fun tip 1", "fun tip 2", "fun tip 3"]}},
                "extra_info": "1-2 laid-back sentences about the places"
            }}

            Requirements:
            - Sound like a witty agent dropping a tip
            - Keep it under 10 words for to_send_notification
            - Use double quotes for JSON compliance
            - Keep it concise, casual, and mobile-friendly
            - Add a sprinkle of humor
            - Include factual places data relevant to the trip destination
            - Return ONLY the specified JSON structure, no extra fields
            """

        elif request.message_type.lower() == "about_hotel":
            prompt = f"""
            Chief, got the hotel scoop from this context {request}. 
            Return it as valid JSON with ONLY these keys:

            {{
                "to_send_notification": "a fun 10-word max tip like 'This place is swanky!'",
                "quick_tips": {{"tips": ["fun tip 1", "fun tip 2", "fun tip 3"]}},
                "extra_info": "1-2 chill sentences about the hotel"
            }}

            Requirements:
            - Sound like a sassy agent giving a tip
            - Keep it under 10 words for to_send_notification
            - Use double quotes for JSON compliance
            - Keep it concise, casual, and mobile-friendly
            - Add some humor
            - Include factual hotel data
            - Return ONLY the specified JSON structure, no extra fields
            """

        elif request.message_type.lower() == "current_flight_status":
            prompt = f"""
            Yo, boss, flight status update from this context {request}. 
            Return it as valid JSON with ONLY these keys:

            {{
                "to_send_notification": "a fun 10-word max tip like 'Flight’s on, pack quick!'",
                "quick_tips": {{"tips": ["fun tip 1", "fun tip 2", "fun tip 3"]}},
                "extra_info": "1-2 relaxed sentences about the flight"
            }}

            Requirements:
            - Sound like a cool agent sharing a tip
            - Keep it under 10 words for to_send_notification
            - Use double quotes for JSON compliance
            - Keep it concise, casual, and mobile-friendly
            - Add a bit of humor
            - Include factual flight status data
            - Return ONLY the specified JSON structure, no extra fields
            """
        else:
            return DEFAULT_RESPONSE

        human_message = HumanMessage(content=prompt)
        response = model([human_message])
        
        response_content = response.content if hasattr(response, "content") else str(response)
        cleaned_content = response_content.replace('```json', '').replace('```', '').strip()
        
        try:
            parsed_response = json.loads(cleaned_content)
            required_keys = {"to_send_notification", "quick_tips", "extra_info"}
            
            if set(parsed_response.keys()) != required_keys:
                print(f"Invalid keys in response: {parsed_response.keys()}")
                return DEFAULT_RESPONSE
                
            if not isinstance(parsed_response["quick_tips"], dict) or "tips" not in parsed_response["quick_tips"]:
                print("Invalid quick_tips structure")
                return DEFAULT_RESPONSE
            
            # now trigger the notification
            # Here you would implement the logic to send the notification
            # For example, you could call a function to send the notification
            # send_notification = SendNotificationRequest(
            #     trip_id=request.trip_id,
            #     leg_id=request.leg_id,
            #     message=parsed_response["to_send_notification"]
            # )
            # store_in_db(request.trip_id, request.leg_id, parsed_response, request.message_type, request.itinerary)
            # trigger_notification(send_notification)
            return parsed_response
            
        except (json.JSONDecodeError, ValueError) as e:
            print(f"Failed to parse response: {e}, Raw response: {response_content}")
            return DEFAULT_RESPONSE

    except Exception as e:
        print(f"Unexpected error: {e}")
        return DEFAULT_RESPONSE
 
@app.get("/trips")
async def get_trip_details(trip_id: str = Query(...), leg_id: str = Query(...)):
    try:
        import sqlite3
        conn = sqlite3.connect('trip_details.db')
        cursor = conn.cursor()

        cursor.execute("SELECT * FROM trip_details WHERE trip_id = ? AND leg_id = ?", (trip_id, leg_id))
        row = cursor.fetchone()

        if row is None:
            return {"error": "Trip not found"}

        return {
            "itinerary": json.loads(row[2])
        }
    except Exception as e:
        return {"error": str(e)}

def store_in_db(trip_id: str, leg_id: str, parsed_response: dict, message_type: str, itinerary: dict):
    import sqlite3
    try:
        conn = sqlite3.connect('trip_details.db')
        cursor = conn.cursor()

        cursor.execute("INSERT INTO trip_details (trip_id, leg_id, parsed_response, message_type, itinerary) VALUES (?, ?, ?, ?, ?)", (trip_id, leg_id, json.dumps(parsed_response), message_type, json.dumps(itinerary)))
        conn.commit()
    except Exception as e:
        print(f"Error storing in database: {e}")
    finally:
        if conn:
            conn.close()

def trigger_notification(request: SendNotificationRequest):
    # Here you would implement the logic to send the notification
    try:
        res = requests.post(
            "http://localhost:8000/nodes/send_notification",
            json={
                "trip_id": request.trip_id,
                "leg_id": request.leg_id,
                "message": request.message
            }
        )

        if res.status_code != 200:
            print(f"Failed to send notification: {res.text}")
    except Exception as e:
        print(f"Error sending notification: {e}")

    print("Notification sent successfully")


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8001)