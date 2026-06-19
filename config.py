import os
from dotenv import load_dotenv
from pathlib import Path

load_dotenv()


GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
GEMINI_API_KEY_2 = os.getenv("GEMINI_API_KEY_2")
GITHUB_TOKEN = os.getenv("GITHUB_TOKEN")

GEMINI_MODEL = "gemini-2.5-flash"

DB_PATH = Path("data/copilot.db")
REPOS_DIR = Path("data/repos")

REPOS_DIR.mkdir(parents=True, exist_ok=True)
DB_PATH.parent.mkdir(parents=True, exist_ok=True)