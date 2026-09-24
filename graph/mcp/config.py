import os
from dotenv import load_dotenv

load_dotenv()

TG_HOST = os.environ.get("TG_HOST", "")
TG_GRAPH = os.environ.get("TG_GRAPH_NAME", "FraudGraph")
TG_USERNAME = os.environ.get("TG_USERNAME", "")
TG_PASSWORD = os.environ.get("TG_PASSWORD", "")
TG_SECRET = os.environ.get("TG_SECRET", "")
TG_GS_PORT = int(os.environ.get("TG_GS_PORT", "14240"))
TG_REST_PORT = int(os.environ.get("TG_REST_PORT", "9000"))

MCP_MODE = os.environ.get("MCP_MODE", "live")