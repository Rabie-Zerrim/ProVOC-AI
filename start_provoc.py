import subprocess
import time
import requests
import sys
import os
import shutil

# Prefer a local ngrok.exe in the project directory (downloaded as fallback),
# then fall back to whatever is in PATH.
_SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
_LOCAL_NGROK = os.path.join(_SCRIPT_DIR, "ngrok.exe")
NGROK_BIN = _LOCAL_NGROK if os.path.isfile(_LOCAL_NGROK) else (shutil.which("ngrok") or "ngrok")

RAILWAY_TOKEN = "d2559107-cb3a-45b3-8329-70e1d01dc3f9"
SERVICE_ID = "8ba91b6e-21d3-440c-9eb6-5c89bfd8c066"
ENVIRONMENT_ID = "2f1deec4-be99-4254-abba-62c398c74e74"

RAILWAY_API = "https://backboard.railway.app/graphql/v2"


def update_railway_fastapi_url(tunnel_url: str) -> bool:
    query = """
    mutation UpsertVariables($input: VariableCollectionUpsertInput!) {
      variableCollectionUpsert(input: $input)
    }
    """
    variables = {
        "input": {
            "projectId": "1d168992-120e-45b9-b225-3ce6bafa9117",
            "environmentId": ENVIRONMENT_ID,
            "serviceId": SERVICE_ID,
            "variables": {
                "FASTAPI_URL": tunnel_url
            }
        }
    }
    headers = {
        "Authorization": f"Bearer {RAILWAY_TOKEN}",
        "Content-Type": "application/json"
    }
    try:
        response = requests.post(
            RAILWAY_API,
            json={"query": query, "variables": variables},
            headers=headers
        )
        data = response.json()
        if "errors" in data:
            print(f"Railway API error: {data['errors']}")
            return False
        print(f"Railway FASTAPI_URL updated to: {tunnel_url}")
        return True
    except Exception as e:
        print(f"Failed to update Railway: {e}")
        return False


def kill_port(port: int):
    try:
        result = subprocess.run(
            ["netstat", "-ano"],
            capture_output=True, text=True
        )
        for line in result.stdout.split("\n"):
            if f":{port}" in line and "LISTENING" in line:
                pid = line.strip().split()[-1]
                subprocess.run(["taskkill", "/PID", pid, "/F"], capture_output=True)
                print(f"Killed process {pid} on port {port}")
                break
    except Exception as e:
        print(f"Could not kill port {port}: {e}")


def main():
    print("Starting ProVOC AI services...")

    # Kill anything on ports 5000 (uvicorn) and 4040 (ngrok dashboard)
    kill_port(5000)
    kill_port(4040)

    # Step 1: Start uvicorn in background
    print("Starting pv-ai on port 5000...")
    uvicorn_process = subprocess.Popen(
        [sys.executable, "-m", "uvicorn", "main:app",
         "--host", "127.0.0.1", "--port", "5000"],
        cwd=os.path.dirname(os.path.abspath(__file__))
    )
    print("Waiting for pv-ai to start...")
    time.sleep(5)

    # Step 2: Start ngrok
    print(f"Starting ngrok tunnel (using {NGROK_BIN})...")
    ngrok_process = subprocess.Popen([NGROK_BIN, "http", "5000"])

    # Step 3: Wait for ngrok to open its local API
    time.sleep(3)

    # Step 4: Get tunnel URL from ngrok local API (retry up to ~12 s total)
    print("Getting tunnel URL from ngrok API...")
    tunnel_url = None
    for attempt in range(6):
        try:
            response = requests.get("http://127.0.0.1:4040/api/tunnels", timeout=3)
            tunnels = response.json().get("tunnels", [])
            if tunnels:
                tunnel_url = tunnels[0]["public_url"]
                break
        except Exception:
            pass
        time.sleep(2)

    if not tunnel_url:
        print("ERROR: Could not get tunnel URL from ngrok API after multiple attempts.")
        print("Make sure ngrok is installed and authenticated.")
        uvicorn_process.terminate()
        ngrok_process.terminate()
        return

    print(f"Tunnel URL: {tunnel_url}")

    # Step 5: Update Railway FASTAPI_URL
    print("Updating Railway FASTAPI_URL...")
    success = update_railway_fastapi_url(tunnel_url)

    if success:
        print("\n✅ ProVOC AI is ready!")
        print(f"Tunnel: {tunnel_url}")
        print("Railway will redeploy in ~1 minute")
        print("\nPress Ctrl+C to stop all services")
    else:
        print("WARNING: Failed to update Railway — set FASTAPI_URL manually.")

    # Keep running until Ctrl+C
    try:
        uvicorn_process.wait()
    except KeyboardInterrupt:
        print("\nStopping services...")
        uvicorn_process.terminate()
        ngrok_process.terminate()


if __name__ == "__main__":
    main()
