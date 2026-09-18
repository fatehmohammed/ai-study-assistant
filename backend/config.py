import os
import subprocess
from dotenv import load_dotenv

load_dotenv()

DATA_DIR = os.getenv("DATA_DIR", os.path.join(os.path.dirname(__file__), "../data"))
UPLOADS_DIR = os.path.join(DATA_DIR, "uploads")
DB_PATH = os.path.join(DATA_DIR, "chroma_db")
SOFFICE = os.getenv("SOFFICE_PATH", "/usr/bin/soffice")

_raw_origins = os.getenv("CORS_ORIGINS", "http://localhost:3000,http://localhost:3001")
CORS_ORIGINS = [o.strip() for o in _raw_origins.split(",") if o.strip()]

os.makedirs(UPLOADS_DIR, exist_ok=True)
os.makedirs(DB_PATH, exist_ok=True)


def convert_pptx_to_pdf(pptx_path: str) -> str:
    subprocess.run(
        [SOFFICE, "--headless", "--convert-to", "pdf", "--outdir", UPLOADS_DIR, pptx_path],
        check=True,
        capture_output=True,
    )
    pdf_name = os.path.splitext(os.path.basename(pptx_path))[0] + ".pdf"
    return os.path.join(UPLOADS_DIR, pdf_name)
