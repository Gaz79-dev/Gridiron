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
from bot.api.routers import events, users, squads, stats, players
from bot.api.routers import templates as templates_router
from bot.api import auth

# Load environment variables
load_dotenv()

# --- Define Base Directory ---
BASE_DIR = Path(__file__).resolve().parent

# --- App State & Lifespan for the Web Server ---
# bot/main.py

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

# --- FastAPI App Setup ---
app = FastAPI(lifespan=lifespan)
templates_dir = BASE_DIR / "web/templates"
app.mount("/static", StaticFiles(directory=str(BASE_DIR / "web/static")), name="static")
templates = Jinja2Templates(directory=str(templates_dir))

origins = [
    "https://squadbuilder.rdg-clan.co.uk",
    "http://localhost",
    "http://localhost:8000",
]

app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Include all the API routers
app.include_router(auth.router)
app.include_router(users.router)
app.include_router(events.router)
app.include_router(squads.router)
app.include_router(stats.router)
app.include_router(templates_router.router)
app.include_router(players.router)

# --- Web Page Routes ---
@app.get("/login", tags=["HTML"], summary="Serves the login page")
async def login_page(request: Request):
    return templates.TemplateResponse("login.html", {"request": request})

@app.get("/", tags=["HTML"], summary="Serves the main squad builder page")
async def main_page(request: Request):
    return templates.TemplateResponse("index.html", {"request": request})

@app.get("/admin", tags=["HTML"], summary="Serves the admin page")
async def admin_page(request: Request):
    return templates.TemplateResponse("admin.html", {"request": request})

# --- FIX START: Rename old stats page to engagement and add new stats page ---
@app.get("/engagement", tags=["HTML"], summary="Serves the engagement stats page")
async def engagement_page(request: Request):
    return templates.TemplateResponse("engagement.html", {"request": request})

@app.get("/engagement/player/{user_id}", tags=["HTML"], summary="Serves the player detail page")
async def player_detail_page(request: Request, user_id: int):
    return templates.TemplateResponse("player_detail.html", {"request": request, "user_id": user_id})

@app.get("/stats", tags=["HTML"], summary="Serves the new match stats and leaderboards page")
async def stats_page(request: Request):
    return templates.TemplateResponse("stats.html", {"request": request})
# --- FIX END ---

@app.get("/events", tags=["HTML"], summary="Serves the event management page")
async def events_page(request: Request):
    return templates.TemplateResponse("events.html", {"request": request})

@app.get("/players", tags=["HTML"], summary="Serves the player ratings page")
async def players_page(request: Request):
    return templates.TemplateResponse("players.html", {"request": request})
