"""Start the MMS Fusion backend server"""
import uvicorn
from app.models.database import init_db

if __name__ == "__main__":
    init_db()
    uvicorn.run("app.main:app", host="0.0.0.0", port=8000, reload=True)
