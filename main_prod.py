from fastapi import FastAPI, HTTPException
from langchain_community.llms import Ollama
from pydantic import BaseModel
from typing import Dict, List, Any, Optional
import json
import asyncio
from dotenv import load_dotenv
import sqlite3
import os
from datetime import datetime
import logging

# Import search components (assumed to exist)
from duck_duck_go import SearchEngine, WebScraper, SearchOrchestrator

# Set up logging
logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")
logger = logging.getLogger(__name__)

# Load environment variables
load_dotenv()

# Initialize FastAPI app
app = FastAPI(title="Travel Information API")

# Initialize search components
searcher = SearchEngine()
scraper = WebScraper()
orchestrator = SearchOrchestrator(searcher, scraper)

# Configure Ollama
ollama_model = Ollama(
    model="mistral",
    base_url="http://localhost:11434",
    temperature=0.7
)

# ============ Data Models ============

class TripRequest(BaseModel):
    trip_id: str
    leg_request_id: str
    itinerary: dict
    message_type: str
    email: str

class SearchResult(BaseModel):
    to_send_notification: str
    quick_tips: Dict[str, List[str]]
    extra_info: str
    title: str

# ============ Constants ============

DEFAULT_RESPONSE = {
    "to_send_notification": "Unable to retrieve accurate information at this time. Please try again later.",
    "quick_tips": {"tips": [
        "Contact support for immediate assistance",
        "Check official sources for current information",
        "Try again in a few minutes"
    ]},
    "extra_info": "Our system encountered a technical issue retrieving the requested information. We apologize for the inconvenience.",
    "title": "Travel Information Update"
}

MESSAGE_TYPES = {
    "flight": {
        "pre_info": ["nearby_places"],
        "current_info": ["current_flight_status", "weather"],
        "post_info": ["reached_destination"]
    },
    "hotel": {
        "pre_info": ["about_hotel", "nearby_places"],
        "current_info": ["about_hotel", "weather"],
        "post_info": ["reached_destination"]
    }
}

DEFAULT_TIPS = {
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

# ============ Database Initialization ============

def initialize_database():
    """Create SQLite database and tables, ensuring all columns are present."""
    db_path = os.path.abspath("travel_info_2.db")
    logger.info(f"Initializing database at: {db_path}")
    
    try:
        with sqlite3.connect(db_path) as conn:
            cursor = conn.cursor()
            
            # Create table if it doesn't exist
            cursor.execute('''
            CREATE TABLE IF NOT EXISTS trip_notifications (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                trip_id TEXT NOT NULL,
                leg_request_id TEXT NOT NULL,
                message_type TEXT NOT NULL,
                notification TEXT NOT NULL,
                quick_tips TEXT NOT NULL,
                extra_info TEXT NOT NULL,
                raw_leg TEXT NOT NULL,
                email TEXT NOT NULL,
                title TEXT NOT NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
            ''')
            
            # Verify table exists and has correct columns
            cursor.execute("PRAGMA table_info(trip_notifications)")
            columns = [col[1] for col in cursor.fetchall()]
            expected_columns = [
                'id', 'trip_id', 'leg_request_id', 'message_type',
                'notification', 'quick_tips', 'extra_info', 'raw_leg',
                'email', 'created_at', 'title',
            ]
            
            if not all(col in columns for col in expected_columns):
                logger.warning(f"Table schema mismatch. Expected columns: {expected_columns}, Found: {columns}")
                raise RuntimeError("Database schema mismatch. Please check the database structure.")
            
            conn.commit()
            logger.info("Database initialized successfully. Columns: %s", columns)
            
            # Confirm table exists
            cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='trip_notifications'")
            if not cursor.fetchone():
                logger.error("Table 'trip_notifications' was not created")
                raise RuntimeError("Failed to create trip_notifications table")
                
    except sqlite3.Error as e:
        logger.error(f"Database initialization failed: {e}")
        raise
    except Exception as e:
        logger.error(f"Unexpected error during database initialization: {e}")
        raise

# Initialize database at startup
initialize_database()

# ============ Helper Functions ============

# Custom JSON encoder to handle datetime objects
class DateTimeEncoder(json.JSONEncoder):
    def default(self, obj):
        if isinstance(obj, datetime):
            return obj.isoformat()
        return super().default(obj)

def process_itinerary(leg: dict, mode: str) -> dict:
    """Extract relevant information from the itinerary based on travel mode."""
    result = {}
    
    if mode == "flight":
        fields = [
            "departure_airport_name", "arrival_airport_name",
            "departure_airport_code", "arrival_airport_code",
            "departure_city", "arrival_city",
            "departure_time", "arrival_time"
        ]
        for field in fields:
            if field in leg:
                result[field] = leg[field]
    
    elif mode == "hotel":
        fields = ["hotel_name", "hotel_address", "check_in_time", "check_out_time"]
        for field in fields:
            if field in leg:
                result[field] = leg[field]
    
    return result

def generate_search_query(request: TripRequest) -> str:
    """Generate a search query based on the request type."""
    message_type = request.message_type.lower()
    
    query_templates = {
        "weather": f"current weather forecast for {get_location_from_request(request)}",
        "nearby_places": f"top attractions near {get_location_from_request(request)}",
        "about_hotel": f"amenities and information for {get_hotel_name(request)}",
        "current_flight_status": f"status of flight {get_flight_info(request)}"
    }
    
    return query_templates.get(message_type, f"travel information for {get_location_from_request(request)}")

def get_location_from_request(request: TripRequest) -> str:
    """Extract location information from the request."""
    itinerary = request.itinerary
    
    if "arrival_city" in itinerary:
        return itinerary["arrival_city"]
    elif "hotel_address" in itinerary and "city_name" in itinerary["hotel_address"]:
        return itinerary["hotel_address"]["city_name"]
    return "destination"

def get_hotel_name(request: TripRequest) -> str:
    """Extract hotel name from the request."""
    itinerary = request.itinerary
    return itinerary.get("hotel_name", "the hotel")

def get_flight_info(request: TripRequest) -> str:
    """Extract flight information from the request."""
    itinerary = request.itinerary
    return f"{itinerary.get('departure_airport_code', '')} to {itinerary.get('arrival_airport_code', '')}"

def generate_prompt(request: TripRequest, search_results: str) -> str:
    """Generate a prompt for the LLM based on the request type and search results."""
    message_type = request.message_type.lower()
    
    prompt_templates = {
        "weather": f"""
            Generate accurate weather information based on this context {request.dict()} and these search results {search_results}.
            Return it as valid JSON with ONLY these keys:

            {{
                "to_send_notification": "precise, actionable weather information in 20 words or less",
                "quick_tips": {{"tips": ["practical tip based on weather", "essential item to pack", "useful activity recommendation"]}},
                "extra_info": "Two concise, informative sentences about the forecast and its impact on travel plans"
                "title": "that would be 5 words max and unique"
            }}

            Requirements:
            - Make to_send_notification accurate, concise (max 20 words), and immediately useful
            - Make title unique and formal notification, genioune
            - Focus on critical weather information that affects travel plans or safety
            - Use double quotes for JSON compliance
            - Use factual weather data from search results only
            - Match temperature units to destination (Celsius for Europe/Asia, Fahrenheit for US)
            - Include weather advisories or warnings if present
            - Return ONLY the specified JSON structure, no extra fields
        """,
        
        "nearby_places": f"""
            Generate accurate information about notable nearby places based on this context {request.dict()} and these search results {search_results}.
            Return it as valid JSON with ONLY these keys:

            {{
                "to_send_notification": "precise information about key nearby attractions or amenities in 20 words or less",
                "quick_tips": {{"tips": ["closest essential amenity", "highest-rated attraction nearby", "time-saving transportation option"]}},
                "extra_info": "Two concise, informative sentences about notable nearby locations that enhance the travel experience"
                "title": "that would be 5 words max and unique"
            }}

            Requirements:
            - Make to_send_notification accurate, concise (max 20 words), and immediately useful
            - Make title unique and formal notification, genioune
            - Prioritize information about proximity, operating hours, or special considerations
            - Use double quotes for JSON compliance
            - Include factual location data relevant to the trip destination from search results only
            - Mention distance or travel time when relevant
            - Return ONLY the specified JSON structure, no extra fields
        """,
        
        "about_hotel": f"""
            Generate accurate hotel information based on this context {request.dict()} and these search results {search_results}.
            Return it as valid JSON with ONLY these keys:

            {{
                "to_send_notification": "precise hotel information about check-in, amenities, or location in 20 words or less",
                "quick_tips": {{"tips": ["important check-in detail", "valuable hotel service or amenity", "nearby hotel convenience"]}},
                "extra_info": "Two concise, informative sentences about essential hotel features or policies that improve the stay"
                "title": "that would be 5 words max and unique"
            }}

            Requirements:
            - Make to_send_notification accurate, concise (max 20 words), and immediately useful
            - Make title unique and formal notification, genioune
            - Focus on check-in times, important amenities, or critical location details
            - Use double quotes for JSON compliance
            - Include factual hotel data only from search results
            - Highlight information not obvious from booking confirmations
            - Return ONLY the specified JSON structure, no extra fields
        """,
        
        "current_flight_status": f"""
            Generate accurate flight status information based on this context {request.dict()} and these search results {search_results}.
            Return it as valid JSON with ONLY these keys:

            {{
                "to_send_notification": "precise flight status update only if anything has changed in 20 words or less",
                "quick_tips": {{"tips": ["time-sensitive airport advice", "security or check-in recommendation", "practical arrival/departure tip"]}},
                "extra_info": "Two concise, informative sentences about flight details that affect travel plans or connections"
                "title": "that would be 5 words max and unique"
            }}

            Requirements:
            - Make to_send_notification accurate, concise (max 20 words), and immediately useful
            - Make title unique and formal notification, genioune
            - Prioritize time-sensitive information like delays, gate changes, or boarding times
            - Use double quotes for JSON compliance
            - Include factual flight status data only from search results
            - Mention terminal/gate information when available
            - Return ONLY the specified JSON structure, no extra fields
        """
    }
    
    return prompt_templates.get(message_type, "")

def extract_json_from_llm_response(response_content: str) -> dict:
    """Extract and parse JSON from LLM response."""
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
        return json.loads(cleaned_content)
    except json.JSONDecodeError as e:
        logger.error(f"Failed to parse JSON from LLM response: {e}")
        return {}

def validate_and_fix_response(parsed_response: dict, request: TripRequest) -> dict:
    """Validate and fix the parsed response."""
    required_keys = {"to_send_notification", "quick_tips", "extra_info", "title"}
    
    if not all(key in parsed_response for key in required_keys):
        logger.warning(f"Invalid response structure for {request.message_type}")
        return DEFAULT_RESPONSE
    
    if not isinstance(parsed_response["quick_tips"], dict) or "tips" not in parsed_response["quick_tips"]:
        parsed_response["quick_tips"] = {"tips": []}
    
    message_type = request.message_type.lower()
    tips_to_use = DEFAULT_TIPS.get(message_type, DEFAULT_TIPS["current_flight_status"])
    
    while len(parsed_response["quick_tips"]["tips"]) < 3:
        tip_index = len(parsed_response["quick_tips"]["tips"]) % len(tips_to_use)
        parsed_response["quick_tips"]["tips"].append(tips_to_use[tip_index])
    
    return parsed_response

# ============ Main Processing Function ============

async def process_request(request: TripRequest) -> dict:
    """Process a trip request and generate travel information."""
    try:
        query_prompt = f"Form a precise search query to get information about {request.message_type} for this trip: {request.dict()}"
        logger.info(f"Generating search query: {query_prompt}")
        search_query = ollama_model.invoke(query_prompt)
        logger.info(f"Search query: {search_query}")
        
        search_results = orchestrator.execute(search_query)
        logger.info(f"Search results: {search_results}")
        
        prompt = generate_prompt(request, search_results)
        if not prompt:
            logger.warning(f"No prompt generated for message_type: {request.message_type}")
            return DEFAULT_RESPONSE
        
        response_content = ollama_model.invoke(prompt)
        logger.info(f"LLM response: {response_content}")
        
        parsed_response = extract_json_from_llm_response(response_content)
        if not parsed_response:
            logger.warning("Failed to parse LLM response")
            return DEFAULT_RESPONSE
        
        return validate_and_fix_response(parsed_response, request)
    
    except Exception as e:
        logger.error(f"Error in process_request for trip_id: {request.trip_id}, message_type: {request.message_type}: {e}")
        return DEFAULT_RESPONSE

# ============ API Routes ============

@app.post("/generate")
async def generate_travel_info(request: TripRequest):
    """Generate travel information based on the request."""
    return await process_request(request)

@app.post("/batch-process")
async def batch_process():
    """Process all itineraries in batch and store results in SQLite database."""
    try:
        # Ensure database is initialized
        initialize_database()
        
        from get_iternary import generate_flight_notifications
        data = generate_flight_notifications()
        logger.info(f"Input data: {data}")
        
        with sqlite3.connect('travel_info_2.db') as conn:
            cursor = conn.cursor()
            
            processed_count = 0
            
            for phase in ["pre_info", "current_info", "post_info"]:
                if phase not in data:
                    logger.info(f"Phase {phase} not found in data")
                    continue
                    
                for pax_key, pax in data[phase].items():
                    logger.info(f"Processing pax: {pax_key}")
                    if not isinstance(pax, (list, tuple)):
                        logger.warning(f"Skipping non-iterable pax: {pax}")
                        continue
                        
                    for leg in pax:
                        logger.info(f"Processing leg: {leg}")
                        leg_request_id = leg.get("leg_request_id")
                        mode = leg.get("mode", "")
                        phase_key = phase
                        
                        if mode in MESSAGE_TYPES and phase_key in MESSAGE_TYPES[mode]:
                            message_types = MESSAGE_TYPES[mode][phase_key]
                        else:
                            message_types = []
                            logger.info(f"No message types for mode: {mode}, phase: {phase}")
                        
                        for message_type in message_types:
                            itinerary = process_itinerary(leg, mode)
                            request = TripRequest(
                                email=leg.get("pax_info", {}).get("email", ""),
                                trip_id=leg.get("trip_id", ""),
                                leg_request_id=leg_request_id,
                                itinerary=itinerary,
                                message_type=message_type
                            )
                            
                            if not all([request.trip_id, request.leg_request_id, request.message_type]):
                                logger.warning(f"Skipping insert due to missing fields: {request.dict()}")
                                continue
                                
                            response = await process_request(request)
                            logger.info(f"Response for {message_type}: {response}")
                            
                            try:
                                cursor.execute(
                                    '''
                                    INSERT INTO trip_notifications 
                                    (trip_id, leg_request_id, message_type, notification, quick_tips, extra_info, raw_leg, email, title)
                                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                                    ''',
                                    (
                                        request.trip_id,
                                        request.leg_request_id,
                                        request.message_type,
                                        response.get("to_send_notification", ""),
                                        json.dumps(response.get("quick_tips", {"tips": []}), cls=DateTimeEncoder),
                                        response.get("extra_info", ""),
                                        json.dumps(leg, cls=DateTimeEncoder),
                                        request.email,
                                        response.get("title", ""),
                                    )
                                )
                                conn.commit()
                                processed_count += 1
                                logger.info(f"Inserted record for trip_id: {request.trip_id}, leg_request_id: {request.leg_request_id}")
                            except sqlite3.Error as db_error:
                                logger.error(f"Database error for trip_id: {request.trip_id}, leg_request_id: {request.leg_request_id}: {db_error}")
                                conn.rollback()
                            from send_node import send_notification
                            send_notification(data={
                                "notification": response.get("to_send_notification", ""),
                                "title": response.get("title", ""),
                                "trip_id": request.trip_id,
                                "leg_request_id": request.leg_request_id,
                                "email": request.email,
                            }, username=request.email)


        logger.info(f"Batch process completed with {processed_count} records inserted")
        return {"success": True, "processed_count": processed_count}
    
    except Exception as e:
        logger.error(f"Batch process error: {e}", exc_info=1)
        return {"success": False, "error": str(e)}

@app.get("/notifications")
async def get_notifications(trip_id: str, leg_request_id: str, email: str):
    """Retrieve stored notifications for a specific trip, optionally filtered by leg_request_id or email."""
    try:
        with sqlite3.connect('travel_info.db') as conn:
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()
            
            query = "SELECT * FROM trip_notifications WHERE trip_id = ?"
            params = [trip_id]
            
            if leg_request_id:
                query += " AND leg_request_id = ?"
                params.append(leg_request_id)
            if email:
                query += " AND email = ?"
                params.append(email)
                
            query += " ORDER BY created_at DESC"
            
            cursor.execute(query, params)
            rows = cursor.fetchall()
            leg = {}
            notifications = []
            for row in rows:
                notification = dict(row)
                leg = json.loads(notification['raw_leg'])
                del notification['raw_leg']
                notification['quick_tips'] = json.loads(notification['quick_tips'])
                notifications.append(notification)
            
            return {
                "mode": leg.get("mode", ""),
                "success": True,
                "trip_id": trip_id,
                "leg_request_id": leg_request_id,
                "email": email,
                "raw_leg": leg,
                "data": notifications
            }
    
    except Exception as e:
        logger.error(f"Error retrieving notifications: {e}")
        return {"success": False, "error": str(e)}

# ============ Main ============

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8002)