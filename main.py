import os
from fastapi import FastAPI, WebSocket, WebSocketDisconnect, Query
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
import requests
from typing import Optional

app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.get("/")
def read_root():
    return {"message": "Hello from FastAPI Backend!"}

@app.get("/api/hello")
def hello():
    return {"message": "Hello from the backend API!"}

@app.get("/test")
def test_database():
    """Test endpoint to check if database is available and accessible"""
    response = {
        "backend": "✅ Running",
        "database": "❌ Not Available",
        "database_url": None,
        "database_name": None,
        "connection_status": "Not Connected",
        "collections": []
    }
    
    try:
        # Try to import database module
        from database import db
        
        if db is not None:
            response["database"] = "✅ Available"
            response["database_url"] = "✅ Configured"
            response["database_name"] = db.name if hasattr(db, 'name') else "✅ Connected"
            response["connection_status"] = "Connected"
            
            # Try to list collections to verify connectivity
            try:
                collections = db.list_collection_names()
                response["collections"] = collections[:10]  # Show first 10 collections
                response["database"] = "✅ Connected & Working"
            except Exception as e:
                response["database"] = f"⚠️  Connected but Error: {str(e)[:50]}"
        else:
            response["database"] = "⚠️  Available but not initialized"
            
    except ImportError:
        response["database"] = "❌ Database module not found (run enable-database first)"
    except Exception as e:
        response["database"] = f"❌ Error: {str(e)[:50]}"
    
    # Check environment variables
    import os
    response["database_url"] = "✅ Set" if os.getenv("DATABASE_URL") else "❌ Not Set"
    response["database_name"] = "✅ Set" if os.getenv("DATABASE_NAME") else "❌ Not Set"
    
    return response

# ----------------------
# Emergency helper
# ----------------------
DEFAULT_EMERGENCY_NUMBERS = {
    "global": "112",
    "us": "911",
    "uk": "999",
    "eu": "112",
    "in": "112",
}

SAMPLE_HOSPITALS = [
    {"city": "san francisco", "name": "Zuckerberg San Francisco General Hospital", "phone": "+1 628-206-8000", "address": "1001 Potrero Ave, San Francisco, CA"},
    {"city": "new york", "name": "NYU Langone Health", "phone": "+1 212-263-7300", "address": "550 1st Ave, New York, NY"},
    {"city": "london", "name": "St Thomas' Hospital", "phone": "+44 20 7188 7188", "address": "Westminster Bridge Rd, London"},
    {"city": "bangalore", "name": "Manipal Hospital", "phone": "+91 80 2502 5555", "address": "HAL Old Airport Rd, Bengaluru"},
]

class EmergencyResponse(BaseModel):
    query: Optional[str] = None
    name: str
    address: Optional[str] = None
    phone: str
    note: Optional[str] = None

@app.get("/api/emergency", response_model=EmergencyResponse)
def emergency_lookup(
    q: Optional[str] = Query(None, description="City or address to search"),
    lat: Optional[float] = Query(None),
    lon: Optional[float] = Query(None),
    country: Optional[str] = Query(None, description="2-letter country code for local emergency number")
):
    # Try OpenStreetMap Nominatim if coordinates or query available
    name = None
    address = None
    phone = None

    def local_emergency(cc: Optional[str]):
        if not cc:
            return DEFAULT_EMERGENCY_NUMBERS["global"]
        cc = cc.lower()
        return DEFAULT_EMERGENCY_NUMBERS.get(cc, DEFAULT_EMERGENCY_NUMBERS["global"])

    try:
        if lat is not None and lon is not None:
            url = "https://nominatim.openstreetmap.org/search"
            params = {
                "q": "hospital",
                "format": "json",
                "limit": 1,
                "addressdetails": 1,
                "extratags": 1,
                "viewbox": f"{lon-0.1},{lat+0.1},{lon+0.1},{lat-0.1}",
                "bounded": 1,
            }
            headers = {"User-Agent": "FlamesBlueMedicalApp/1.0"}
            r = requests.get(url, params=params, headers=headers, timeout=5)
            if r.ok and isinstance(r.json(), list) and r.json():
                item = r.json()[0]
                name = item.get("display_name", "Nearest Hospital")
                address = item.get("display_name")
                phone = item.get("extratags", {}).get("phone")
        elif q:
            url = "https://nominatim.openstreetmap.org/search"
            params = {"q": f"hospital near {q}", "format": "json", "limit": 1, "addressdetails": 1, "extratags": 1}
            headers = {"User-Agent": "FlamesBlueMedicalApp/1.0"}
            r = requests.get(url, params=params, headers=headers, timeout=5)
            if r.ok and isinstance(r.json(), list) and r.json():
                item = r.json()[0]
                name = item.get("display_name", "Nearest Hospital")
                address = item.get("display_name")
                phone = item.get("extratags", {}).get("phone")
    except Exception:
        # Fall back to samples below
        pass

    if not name and q:
        city = q.lower()
        for h in SAMPLE_HOSPITALS:
            if h["city"] in city:
                name = h["name"]
                address = h.get("address")
                phone = h.get("phone")
                break

    if not name:
        name = "Nearest Emergency Hospital"
        address = q or "Your area"

    if not phone:
        phone = f"Local emergency: {local_emergency(country)}"

    return EmergencyResponse(query=q, name=name, address=address, phone=phone, note="If this is life-threatening, call emergency now.")

# ----------------------
# Simple Chatbot (WebSocket)
# ----------------------

def generate_bot_reply(text: str) -> str:
    t = (text or "").strip().lower()
    if not t:
        return "Hello! I'm your medical assistant. How can I help you today?"
    if any(k in t for k in ["emergency", "bleeding", "unconscious", "chest pain"]):
        return "This may be an emergency. Please call your local emergency number immediately or visit the nearest hospital. Do you want me to find nearby hospitals?"
    if any(k in t for k in ["fever", "temperature", "flu"]):
        return "For fever, rest, stay hydrated, and consider acetaminophen as directed. If fever persists >48 hours or is very high, consult a doctor."
    if any(k in t for k in ["headache", "migraine"]):
        return "Headaches can have many causes. Try hydration, rest, and avoiding bright screens. Seek care if it's severe, sudden, or with neurological symptoms."
    if any(k in t for k in ["covid", "cough", "cold"]):
        return "If you have cough or cold symptoms, rest, fluids, and isolation may help. Test if concerned and seek care for breathing difficulty."
    return "I hear you. Could you share a bit more about your symptoms, duration, and any medications? I'll guide you next."

class ChatMessage(BaseModel):
    role: str
    content: str

@app.websocket("/ws/chat")
async def websocket_endpoint(websocket: WebSocket):
    await websocket.accept()
    try:
        while True:
            text = await websocket.receive_text()
            reply = generate_bot_reply(text)
            await websocket.send_text(reply)
    except WebSocketDisconnect:
        pass

# HTTP fallback for chat
class ChatRequest(BaseModel):
    message: str

class ChatResponse(BaseModel):
    reply: str

@app.post("/api/chat", response_model=ChatResponse)
def chat(req: ChatRequest):
    return ChatResponse(reply=generate_bot_reply(req.message))


if __name__ == "__main__":
    import uvicorn
    port = int(os.getenv("PORT", 8000))
    uvicorn.run(app, host="0.0.0.0", port=port)
