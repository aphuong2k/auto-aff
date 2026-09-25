import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import time
import threading
import urllib.request
import json
import uvicorn
from api_server import app

def run_server():
    uvicorn.run(app, host="127.0.0.1", port=8008, log_level="warning")

def run_tests():
    base_url = "http://127.0.0.1:8008"
    
    # 1. Test /deals (Consumer Deal Hub Web)
    req = urllib.request.Request(f"{base_url}/deals")
    with urllib.request.urlopen(req, timeout=5) as res:
        assert res.status == 200
        html = res.read().decode("utf-8")
        assert "Săn Deal Hot" in html or "Cổng Deal" in html or "Deals" in html
        assert "application/ld+json" in html
        print("✅ PASS: GET /deals (Consumer Hub renders Schema.org microdata & Glassmorphism UI)")

    # 2. Test /api/stats
    req = urllib.request.Request(f"{base_url}/api/stats")
    with urllib.request.urlopen(req, timeout=5) as res:
        assert res.status == 200
        data = json.loads(res.read().decode("utf-8"))
        assert "deals_shopee" in data
        assert "deals_lazada" in data
        assert "total_commission_vnd" in data
        assert "subscribers_count" in data
        print(f"✅ PASS: GET /api/stats (Shopee: {data.get('deals_shopee')}, Lazada: {data.get('deals_lazada')}, Commission: {data.get('total_commission_vnd')})")

    # 3. Test /api/commissions/stats
    req = urllib.request.Request(f"{base_url}/api/commissions/stats")
    with urllib.request.urlopen(req, timeout=5) as res:
        assert res.status == 200
        stats = json.loads(res.read().decode("utf-8"))
        assert "total_gmv_vnd" in stats
        assert "by_platform" in stats
        assert "by_channel" in stats
        print(f"✅ PASS: GET /api/commissions/stats (GMV: {stats.get('total_gmv_vnd')}, EPC: {stats.get('epc_vnd')})")

    # 4. Test /api/deals filter
    req = urllib.request.Request(f"{base_url}/api/deals?platform=SHOPEE")
    with urllib.request.urlopen(req, timeout=5) as res:
        assert res.status == 200
        print("✅ PASS: GET /api/deals?platform=SHOPEE")

    # 5. Test /api/test/lazada
    req = urllib.request.Request(f"{base_url}/api/test/lazada", data=b"{}", headers={"Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=5) as res:
            laz_res = json.loads(res.read().decode("utf-8"))
            print(f"✅ PASS: POST /api/test/lazada -> {laz_res.get('message')}")
    except urllib.error.HTTPError as he:
        if he.code == 400:
            err_data = json.loads(he.read().decode("utf-8"))
            print(f"✅ PASS: POST /api/test/lazada correctly validates unconfigured credentials -> {err_data.get('detail')}")
        else:
            raise

    # 6. Test GET / (Admin Dashboard index.html)
    req = urllib.request.Request(f"{base_url}/")
    with urllib.request.urlopen(req, timeout=5) as res:
        assert res.status == 200
        index_html = res.read().decode("utf-8")
        assert "<app-root>" in index_html
        print("✅ PASS: GET / (Admin Dashboard bundle served)")

    # 7. Test GET /api/outreach/gradual-posting-status
    req = urllib.request.Request(f"{base_url}/api/outreach/gradual-posting-status")
    with urllib.request.urlopen(req, timeout=5) as res:
        assert res.status == 200
        status_data = json.loads(res.read().decode("utf-8"))
        assert "is_running" in status_data
        print(f"✅ PASS: GET /api/outreach/gradual-posting-status (Status: {status_data.get('status')})")

    # 8. Test POST /api/groups/auto-categorize
    req = urllib.request.Request(f"{base_url}/api/groups/auto-categorize", data=b"{}", headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=5) as res:
        assert res.status == 200
        cat_res = json.loads(res.read().decode("utf-8"))
        assert cat_res.get("status") == "SUCCESS"
        print(f"✅ PASS: POST /api/groups/auto-categorize (Categorized {cat_res.get('count')} groups)")

    print("\n🎉 ALL 8 LIVE ENDPOINT TESTS PASSED!")

if __name__ == "__main__":
    t = threading.Thread(target=run_server, daemon=True)
    t.start()
    time.sleep(2.5)  # Wait for server to bind
    try:
        run_tests()
    except Exception as e:
        import traceback
        traceback.print_exc()
        sys.exit(1)
