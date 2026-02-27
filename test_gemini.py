import urllib.request, urllib.error, json, os
from pathlib import Path

def _load_dotenv():
    env_path = Path(__file__).parent / ".env"
    if not env_path.exists():
        return
    with open(env_path, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            k, _, v = line.partition("=")
            k = k.strip(); v = v.strip().strip('"').strip("'")
            if k and k not in os.environ:
                os.environ[k] = v

_load_dotenv()

key = os.environ.get("GEMINI_API_KEY", "")
if not key:
    print("❌ GEMINI_API_KEY 未設定")
    exit(1)

url = f"https://generativelanguage.googleapis.com/v1beta/models?key={key}"
req = urllib.request.Request(url)

try:
    with urllib.request.urlopen(req, timeout=10) as r:
        d = json.loads(r.read())
        models = [m["name"] for m in d.get("models", []) if "generateContent" in m.get("supportedGenerationMethods", [])]
        print("✅ 可用模型：")
        for m in models:
            print(" ", m)
except Exception as e:
    print("❌ 錯誤:", e)
