import urllib.request
import urllib.error
import json
import sys

BASE_URL = "http://127.0.0.1:5173"
FLASK_URL = "http://127.0.0.1:5000"

def get(url):
    req = urllib.request.Request(url)
    with urllib.request.urlopen(req) as resp:
        return resp.status, resp.read().decode('utf-8'), resp.headers

def post(url, payload):
    body = json.dumps(payload).encode('utf-8')
    req = urllib.request.Request(url, data=body, headers={'Content-Type': 'application/json'}, method='POST')
    with urllib.request.urlopen(req) as resp:
        return resp.status, resp.read().decode('utf-8')

def run_tests():
    passed = 0
    failed = 0

    print("==================================================")
    print(" TRACK GUARD INTEGRATION & ACCEPTANCE TEST SUITE ")
    print("==================================================")

    # Test 1: Frontend Root HTML
    try:
        status, html, _ = get(f"{BASE_URL}/")
        assert status == 200, f"Expected 200, got {status}"
        assert "TRACK GUARD" in html or "root" in html, "Root HTML missing core elements"
        print("[PASS] Test 1: Frontend index HTML served (200 OK)")
        passed += 1
    except Exception as e:
        print(f"[FAIL] Test 1: Frontend index HTML: {e}")
        failed += 1

    # Test 2: Backend Hardware Status API
    try:
        status, data, _ = get(f"{BASE_URL}/api/status")
        assert status == 200
        parsed = json.loads(data)
        assert "connected" in parsed
        assert "fix_state" in parsed
        print(f"[PASS] Test 2: GET /api/status (connected={parsed.get('connected')}, fix_state={parsed.get('fix_state')})")
        passed += 1
    except Exception as e:
        print(f"[FAIL] Test 2: GET /api/status: {e}")
        failed += 1

    # Test 3: Backend GPS Status API
    try:
        status, data, _ = get(f"{BASE_URL}/api/gps")
        assert status == 200
        parsed = json.loads(data)
        gps_st = parsed.get("status", parsed)
        assert "fix_valid" in gps_st
        print(f"[PASS] Test 3: GET /api/gps (fix_valid={gps_st.get('fix_valid')}, error='{gps_st.get('error')[:40]}...')")
        passed += 1
    except Exception as e:
        print(f"[FAIL] Test 3: GET /api/gps: {e}")
        failed += 1

    # Test 4: Mode Switch API
    try:
        status, data = post(f"{BASE_URL}/api/mode", {"mode": "wheel"})
        assert status == 200
        parsed = json.loads(data)
        assert parsed.get("success") is True
        print(f"[PASS] Test 4: POST /api/mode -> wheel (success={parsed.get('success')})")
        passed += 1
    except Exception as e:
        print(f"[FAIL] Test 4: POST /api/mode: {e}")
        failed += 1

    # Test 5: Route Calculation API (OSRM network routing)
    try:
        status, data = post(f"{BASE_URL}/api/route", {
            "start_lat": 12.9716,
            "start_lon": 77.5946,
            "dest_lat": 12.9720,
            "dest_lon": 77.5950
        })
        assert status == 200
        parsed = json.loads(data)
        assert parsed.get("success") is True
        route = parsed.get("route", {})
        coords = route.get("coordinates", [])
        steps = route.get("steps", [])
        assert len(coords) > 2, "Route geometry missing"
        assert len(steps) > 0, "Turn-by-turn steps missing"
        print(f"[PASS] Test 5: POST /api/route (source='{route.get('source')}', distance={route.get('distance_m')}m, steps={len(steps)})")
        passed += 1
    except Exception as e:
        print(f"[FAIL] Test 5: POST /api/route: {e}")
        failed += 1

    # Test 6: Route Calculation Rejection of Straight-Line Fallbacks
    try:
        try:
            status, data = post(f"{BASE_URL}/api/route", {
                "start_lat": 0.0,
                "start_lon": 0.0,
                "dest_lat": 0.1,
                "dest_lon": 0.1
            })
            print("[FAIL] Test 6: Untraversable route was unexpectedly accepted")
            failed += 1
        except urllib.error.HTTPError as e:
            assert e.code == 400
            err_body = json.loads(e.read().decode('utf-8'))
            assert "not permitted" in err_body.get('error', '').lower() or "no traversable" in err_body.get('error', '').lower()
            print(f"[PASS] Test 6: POST /api/route rejected straight-line fallback (400: '{err_body.get('error')[:45]}...')")
            passed += 1
    except Exception as e:
        print(f"[FAIL] Test 6: Route straight-line rejection check: {e}")
        failed += 1

    # Test 7: Start Navigation Session API
    session_id_1 = None
    try:
        status, data = post(f"{BASE_URL}/api/navigation/start", {
            "mode": "integrated",
            "start_lat": 12.9716,
            "start_lon": 77.5946,
            "dest_lat": 12.9720,
            "dest_lon": 77.5950,
            "start_source": "manual"
        })
        assert status == 200
        parsed = json.loads(data)
        assert parsed.get("success") is True
        session_id_1 = parsed.get("session_id")
        assert session_id_1 is not None
        print(f"[PASS] Test 7: POST /api/navigation/start (session_id={session_id_1})")
        passed += 1
    except Exception as e:
        print(f"[FAIL] Test 7: POST /api/navigation/start: {e}")
        failed += 1

    # Test 8: Query Active Navigation Session API
    try:
        status, data, _ = get(f"{BASE_URL}/api/navigation/session")
        assert status == 200
        parsed = json.loads(data)
        sess = parsed.get("session", {})
        assert sess.get("session_id") == session_id_1, f"Expected {session_id_1}, got {sess.get('session_id')}"
        assert sess.get("status") == "active", f"Expected active, got {sess.get('status')}"
        assert sess.get("mode") == "integrated", f"Expected integrated, got {sess.get('mode')}"
        print(f"[PASS] Test 8: GET /api/navigation/session active sync (id={sess.get('session_id')}, status={sess.get('status')})")
        passed += 1
    except Exception as e:
        print(f"[FAIL] Test 8: GET /api/navigation/session: {e}")
        failed += 1

    # Test 9: Cancellation via Stop Navigation (Must record as cancelled, NOT arrival!)
    try:
        status, data = post(f"{BASE_URL}/api/navigation/stop", {
            "session_id": session_id_1,
            "status": "cancelled"
        })
        assert status == 200
        parsed = json.loads(data)
        assert parsed.get("status") == "cancelled"
        print(f"[PASS] Test 9: POST /api/navigation/stop (status={parsed.get('status')}, cancelled without marking arrival)")
        passed += 1
    except Exception as e:
        print(f"[FAIL] Test 9: POST /api/navigation/stop: {e}")
        failed += 1

    # Test 10: Verify Cancelled State in Session API
    try:
        status, data, _ = get(f"{BASE_URL}/api/navigation/session")
        assert status == 200
        parsed = json.loads(data)
        sess = parsed.get("session", {})
        assert sess.get("status") == "cancelled", f"Expected cancelled, got {sess.get('status')}"
        print(f"[PASS] Test 10: Session state correctly reflects cancelled (status={sess.get('status')})")
        passed += 1
    except Exception as e:
        print(f"[FAIL] Test 10: Verify cancelled session state: {e}")
        failed += 1

    # Test 11: Start Second Navigation Session for Manual Completion
    session_id_2 = None
    try:
        status, data = post(f"{BASE_URL}/api/navigation/start", {
            "mode": "wheel",
            "start_lat": 12.9716,
            "start_lon": 77.5946,
            "dest_lat": 12.9720,
            "dest_lon": 77.5950,
            "start_source": "manual"
        })
        assert status == 200
        parsed = json.loads(data)
        session_id_2 = parsed.get("session_id")
        assert session_id_2 is not None
        print(f"[PASS] Test 11: POST /api/navigation/start 2nd session (session_id={session_id_2})")
        passed += 1
    except Exception as e:
        print(f"[FAIL] Test 11: POST /api/navigation/start second session: {e}")
        failed += 1

    # Test 12: Manual Completion API
    try:
        status, data = post(f"{BASE_URL}/api/navigation/complete", {
            "session_id": session_id_2,
            "completion_method": "manual"
        })
        assert status == 200
        parsed = json.loads(data)
        assert parsed.get("success") is True
        assert parsed.get("completion") == "manual"
        print(f"[PASS] Test 12: POST /api/navigation/complete (completion={parsed.get('completion')}, manual arrival logged)")
        passed += 1
    except Exception as e:
        print(f"[FAIL] Test 12: POST /api/navigation/complete: {e}")
        failed += 1

    # Test 13: Navigation History API
    try:
        status, data, _ = get(f"{BASE_URL}/api/history")
        assert status == 200
        parsed = json.loads(data)
        sessions = parsed.get("sessions", [])
        assert len(sessions) > 0, "No historical sessions found"
        print(f"[PASS] Test 13: GET /api/history (sessions count={len(sessions)})")
        passed += 1
    except Exception as e:
        print(f"[FAIL] Test 13: GET /api/history: {e}")
        failed += 1

    # Test 14: Local Tile Serving Check
    try:
        req = urllib.request.Request(f"{BASE_URL}/tiles/0/0/0.png")
        with urllib.request.urlopen(req) as resp:
            assert resp.status == 200
            ct = resp.headers.get("Content-Type")
            assert ct == "image/png"
            print(f"[PASS] Test 14: Local offline tile served (200 OK, Content-Type='{ct}')")
        passed += 1
    except Exception as e:
        print(f"[FAIL] Test 14: Tile serving check: {e}")
        failed += 1

    print("==================================================")
    print(f"RESULTS: {passed} PASSED, {failed} FAILED")
    print("==================================================")
    return failed == 0

if __name__ == "__main__":
    success = run_tests()
    sys.exit(0 if success else 1)
