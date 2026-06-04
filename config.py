"""Paths for user-specific files (gitignored). Copy from *.example files on first setup."""

from pathlib import Path

ROOT = Path(__file__).parent

CANDIDATE_PROFILE_PATH = ROOT / "config" / "candidate_profile.txt"
KEYWORDS_PATH = ROOT / "keywords.txt"
BASE_RESUME_PATH = ROOT / "templates" / "base_resume.txt"

CANDIDATE_PROFILE_EXAMPLE = ROOT / "config" / "candidate_profile.example.txt"
KEYWORDS_EXAMPLE = ROOT / "keywords.example.txt"
BASE_RESUME_EXAMPLE = ROOT / "templates" / "base_resume.example.txt"
