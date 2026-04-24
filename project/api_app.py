import os
import sys

import uvicorn

sys.path.insert(0, os.path.dirname(__file__))


if __name__ == "__main__":
    uvicorn.run(
        "api.app:app",
        host=os.environ.get("API_HOST", "127.0.0.1"),
        port=int(os.environ.get("API_PORT", "8000")),
        reload=os.environ.get("API_RELOAD", "false").lower() == "true",
    )

