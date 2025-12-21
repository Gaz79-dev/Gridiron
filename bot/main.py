import os
from contextlib import asynccontextmanager
from pathlib import Path
from dotenv import load_dotenv
import uvicorn
from fastapi import FastAPI, Request
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from fastapi.middleware.cors import CORSMiddleware

# Use absolute imports from the 'bot' package root
from bot.utils.database import Database
from bot.api.routers import events, users, squads, stats, players, white_chats
from bot.api.routers import templates as templates_router
from bot.api import auth

# Load environment variables
load_dotenv()

# --- Define Base Directory ---
# This resolves to /usr/src/app/bot inside the container
BASE_DIR = Path(__file__).resolve().parent

# --- App State & Lifespan for the Web Server ---
@asynccontextmanager
async def lifespan(app: FastAPI):
    """
    Handles application startup and shutdown events for the web server.
    """
    print("Web server starting up...")
    db_instance = Database()
    try:
        # This connect call is crucial as it sets up the JSONB decoder
        await db_instance.connect()
        app.state.db = db_instance
        print("Database connection successful for web server.")
    except Exception as e:
        print(f"FATAL: Database connection failed for web server: {e}")
        app.state.db = None
    
    # The bot instance is managed separately by its own process
    app.state.bot = None 
    
    yield
    
    print("Web server shutting down...")
    if app.state.db:
        await app.state.db.close()

# --- FastAPI App Initialization ---
app = FastAPI(title="Squad Builder API", lifespan=lifespan)

# --- FIX: Corrected Paths for Gridiron/bot/web structure ---
# Since main.py is in 'bot/', and web is in 'bot/web/', we just look in 'web/...'
static_dir = os.path.join(BASE_DIR, "web/static")
templates_dir = os.path.join(BASE_DIR, "web/templates")

# Ensure directories exist to prevent crash loops if something is missing
if not os.path.isdir(static_dir):
    print(f"⚠️  WARNING: Static directory not found at {static_dir}. Creating empty fallback.")
    os.makedirs(static_dir, exist_ok=True)

if not os.path.isdir(templates_dir):
    print(f"⚠️  WARNING: Templates directory not found at {templates_dir}. Creating empty fallback.")
    os.makedirs(templates_dir, exist_ok=True)

print(f"✅ Serving Static Files from: {static_dir}")
print(f"✅ Serving Templates from: {templates_dir}")

# Mount static files (CSS, JS, Images)
app.mount("/static", StaticFiles(directory=static_dir), name="static")

templates = Jinja2Templates(directory=templates_dir)

# --- CORS Middleware ---
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# --- Register API Routers ---
app.include_router(auth.router)
app.include_router(events.router)
app.include_router(squads.router)
app.include_router(users.router)
app.include_router(stats.router)
app.include_router(players.router)
app.include_router(templates_router.router)
app.include_router(white_chats.router)

# --- HTML Page Routes ---

@app.get("/login", tags=["HTML"], summary="Serves the login page")
async def login_page(request: Request):
    return templates.TemplateResponse("login.html", {"request": request})

@app.get("/", tags=["HTML"], summary="Serves the main squad builder page")
async def main_page(request: Request):
    return templates.TemplateResponse("index.html", {"request": request})

@app.get("/admin", tags=["HTML"], summary="Serves the admin page")
async def admin_page(request: Request):
    return templates.TemplateResponse("admin.html", {"request": request})

@app.get("/engagement", tags=["HTML"], summary="Serves the engagement stats page")
async def engagement_page(request: Request):
    return templates.TemplateResponse("engagement.html", {"request": request})

@app.get("/engagement/player/{user_id}", tags=["HTML"], summary="Serves the player detail page")
async def player_detail_page(request: Request, user_id: int):
    return templates.TemplateResponse("player_detail.html", {"request": request, "user_id": user_id})

@app.get("/stats", tags=["HTML"], summary="Serves the new match stats and leaderboards page")
async def stats_page(request: Request):
    return templates.TemplateResponse("stats.html", {"request": request})

@app.get("/events", tags=["HTML"], summary="Serves the event management page")
async def events_page(request: Request):
    return templates.TemplateResponse("events.html", {"request": request})

@app.get("/players", tags=["HTML"], summary="Serves the player ratings page")
async def players_page(request: Request):
    return templates.TemplateResponse("players.html", {"request": request})

if __name__ == "__main__":
    uvicorn.run("bot.main:app", host="0.0.0.0", port=8000, reload=True)
