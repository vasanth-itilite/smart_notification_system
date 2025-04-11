from fastapi import FastAPI
from langchain_community.llms import Ollama
from dotenv import load_dotenv
from pydantic import BaseModel
import json
from duck_duck_go import SearchEngine, WebScraper, SearchOrchestrator

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

# Configure Ollama
# By default connects to http://localhost:11434
# Change base_url if Ollama is hosted elsewhere
ollama_model = Ollama(
    model="mistral", # Change to your preferred model - llama3, mistral, etc.
    base_url="http://localhost:11434", # Adjust if needed
    temperature=0.7
)

DEFAULT_RESPONSE = {
    "to_send_notification": "Unable to retrieve accurate information at this time. Please try again later.",
    "quick_tips": {"tips": ["Contact support for immediate assistance", "Check official sources for current information", "Try again in a few minutes"]},
    "extra_info": "Our system encountered a technical issue retrieving the requested information. We apologize for the inconvenience."
}

@app.post("/generate")
async def chat_with_ollama(request: TripRequest):
    try:
        print("Received payload:", request.dict())

        if request.message_type.lower() == "weather":
            query_for_duck_duck = (
                f"form a precise prompt for what needs to be asked to search engine "
                f"to get the weather using this context {request}"
            )
            
            query_we_got_content = ollama_model.invoke(query_for_duck_duck)
            
            results_json = orchestrator.execute(query_we_got_content)
            
            prompt = f"""
            Generate accurate weather information based on this context {request} and these search results {results_json}.
            Return it as valid JSON with ONLY these keys:

            {{
                "to_send_notification": "precise, actionable weather information in 20 words or less",
                "quick_tips": {{"tips": ["practical tip based on weather", "essential item to pack", "useful activity recommendation"]}},
                "extra_info": "Two concise, informative sentences about the forecast and its impact on travel plans"
            }}

            Requirements:
            - Make to_send_notification accurate, concise (max 20 words), and immediately useful
            - Focus on critical weather information that affects travel plans or safety
            - Use double quotes for JSON compliance
            - Use factual weather data from search results only
            - Match temperature units to destination (Celsius for Europe/Asia, Fahrenheit for US)
            - Include weather advisories or warnings if present
            - Return ONLY the specified JSON structure, no extra fields
            """

        elif request.message_type.lower() == "nearby_places":
            query_for_duck_duck = (
                f"form a precise prompt for what needs to be asked to search engine "
                f"to get information about notable places near the destination using this context {request}"
            )
            
            query_we_got_content = ollama_model.invoke(query_for_duck_duck)
            
            results_json = orchestrator.execute(query_we_got_content)
            
            prompt = f"""
            Generate accurate information about notable nearby places based on this context {request} and these search results {results_json}.
            Return it as valid JSON with ONLY these keys:

            {{
                "to_send_notification": "precise information about key nearby attractions or amenities in 20 words or less",
                "quick_tips": {{"tips": ["closest essential amenity", "highest-rated attraction nearby", "time-saving transportation option"]}},
                "extra_info": "Two concise, informative sentences about notable nearby locations that enhance the travel experience"
            }}

            Requirements:
            - Make to_send_notification accurate, concise (max 20 words), and immediately useful
            - Prioritize information about proximity, operating hours, or special considerations
            - Use double quotes for JSON compliance
            - Include factual location data relevant to the trip destination from search results only
            - Mention distance or travel time when relevant
            - Return ONLY the specified JSON structure, no extra fields
            """

        elif request.message_type.lower() == "about_hotel":
            query_for_duck_duck = (
                f"form a precise prompt for what needs to be asked to search engine "
                f"to get information about the hotel in this context {request}"
            )
            
            query_we_got_content = ollama_model.invoke(query_for_duck_duck)
            
            results_json = orchestrator.execute(query_we_got_content)
            
            prompt = f"""
            Generate accurate hotel information based on this context {request} and these search results {results_json}.
            Return it as valid JSON with ONLY these keys:

            {{
                "to_send_notification": "precise hotel information about check-in, amenities, or location in 20 words or less",
                "quick_tips": {{"tips": ["important check-in detail", "valuable hotel service or amenity", "nearby hotel convenience"]}},
                "extra_info": "Two concise, informative sentences about essential hotel features or policies that improve the stay"
            }}

            Requirements:
            - Make to_send_notification accurate, concise (max 20 words), and immediately useful
            - Focus on check-in times, important amenities, or critical location details
            - Use double quotes for JSON compliance
            - Include factual hotel data only from search results
            - Highlight information not obvious from booking confirmations
            - Return ONLY the specified JSON structure, no extra fields
            """

        elif request.message_type.lower() == "current_flight_status":
            query_for_duck_duck = (
                f"form a precise prompt for what needs to be asked to search engine "
                f"to get the current flight status using this context {request}"
            )
            
            query_we_got_content = ollama_model.invoke(query_for_duck_duck)
            
            results_json = orchestrator.execute(query_we_got_content)
            print("results_json", results_json)
            
            prompt = f"""
            Generate accurate flight status information based on this context {request} and these search results {results_json}.
            Return it as valid JSON with ONLY these keys:

            {{
                "to_send_notification": "precise flight status update only if anything has changed in 20 words or less",
                "quick_tips": {{"tips": ["time-sensitive airport advice", "security or check-in recommendation", "practical arrival/departure tip"]}},
                "extra_info": "Two concise, informative sentences about flight details that affect travel plans or connections"
            }}

            Requirements:
            - Make to_send_notification accurate, concise (max 20 words), and immediately useful
            - Prioritize time-sensitive information like delays, gate changes, or boarding times
            - Use double quotes for JSON compliance
            - Include factual flight status data only from search results
            - Mention terminal/gate information when available
            - Return ONLY the specified JSON structure, no extra fields
            """
        else:
            return DEFAULT_RESPONSE

        response_content = ollama_model.invoke(prompt)
        
        # Extract JSON from response
        # The response might contain the JSON inside triple backticks
        if "```json" in response_content:
            json_start = response_content.find("```json") + 7
            json_end = response_content.find("```", json_start)
            cleaned_content = response_content[json_start:json_end].strip()
        elif "```" in response_content:
            json_start = response_content.find("```") + 3
            json_end = response_content.find("```", json_start)
            cleaned_content = response_content[json_start:json_end].strip()
        else:
            cleaned_content = response_content.strip()
        
        try:
            parsed_response = json.loads(cleaned_content)
            required_keys = {"to_send_notification", "quick_tips", "extra_info"}
            
            if set(parsed_response.keys()) != required_keys:
                print(f"Invalid keys in response: {parsed_response.keys()}")
                return DEFAULT_RESPONSE
                
            if not isinstance(parsed_response["quick_tips"], dict) or "tips" not in parsed_response["quick_tips"]:
                print("Invalid quick_tips structure")
                return DEFAULT_RESPONSE
            
            # Ensure we have exactly 3 tips
            if len(parsed_response["quick_tips"]["tips"]) != 3:
                # If fewer than 3, add generic tips to reach 3
                default_tips = {
                    "weather": [
                        "Check forecast updates before heading out each day.",
                        "Pack layered clothing to adapt to changing conditions.",
                        "Have a weather app handy for real-time updates."
                    ],
                    "nearby_places": [
                        "Save offline maps for easier navigation.",
                        "Check opening hours before visiting attractions.",
                        "Ask hotel staff for local recommendations."
                    ],
                    "about_hotel": [
                        "Take photos of room condition upon check-in.",
                        "Program the hotel's number into your phone.",
                        "Confirm checkout time to avoid extra charges."
                    ],
                    "current_flight_status": [
                        "Arrive at the airport at least 2 hours before departure.",
                        "Check your airline's app for real-time updates.",
                        "Keep essential documents in your carry-on luggage."
                    ]
                }
                
                message_type = request.message_type.lower()
                tips_to_use = default_tips.get(message_type, default_tips["current_flight_status"])
                
                while len(parsed_response["quick_tips"]["tips"]) < 3:
                    tip_index = len(parsed_response["quick_tips"]["tips"]) % len(tips_to_use)
                    parsed_response["quick_tips"]["tips"].append(tips_to_use[tip_index])
                
                # If more than 3, truncate to 3
                if len(parsed_response["quick_tips"]["tips"]) > 3:
                    parsed_response["quick_tips"]["tips"] = parsed_response["quick_tips"]["tips"][:3]
            
            # Check if notification is too long and truncate if needed
            if len(parsed_response["to_send_notification"].split()) > 20:
                words = parsed_response["to_send_notification"].split()
                parsed_response["to_send_notification"] = " ".join(words[:20])
                
            return parsed_response
            
        except (json.JSONDecodeError, ValueError) as e:
            print(f"Failed to parse response: {e}, Raw response: {response_content}")
            return DEFAULT_RESPONSE

    except Exception as e:
        print(f"Unexpected error: {e}")
        return DEFAULT_RESPONSE

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8001)