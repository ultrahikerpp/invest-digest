import urllib.request

channel_id = "UC23rnlQU_qE3cec9x709peA"
rss_url = f"https://www.youtube.com/feeds/videos.xml?channel_id={channel_id}"

req = urllib.request.Request(rss_url, headers={
    'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 Chrome/120.0.0.0 Safari/537.36',
})

try:
    with urllib.request.urlopen(req, timeout=10) as resp:
        content = resp.read().decode('utf-8')
        print(f"Success! First 500 chars:")
        print(content[:500])
except Exception as e:
    print(f"Error: {e}")
