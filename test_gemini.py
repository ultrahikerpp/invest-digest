import urllib.request, urllib.error, json, os

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
