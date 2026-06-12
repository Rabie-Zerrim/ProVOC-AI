import subprocess
import time
import re
import requests
import sys
import os
import shutil

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

def kill_port_5000():
    try:
        result = subprocess.run(
            ["netstat", "-ano"],
            capture_output=True, text=True
        )
        for line in result.stdout.split("\n"):
            if ":5000" in line and "LISTENING" in line:
                pid = line.strip().split()[-1]
                subprocess.run(
                    ["taskkill", "/PID", pid, "/F"],
                    capture_output=True
                )
                print(f"Killed process {pid} on port 5000")
                break
    except Exception as e:
        print(f"Could not kill port 5000: {e}")

def main():
    print("Starting ProVOC AI services...")
    kill_port_5000()

    # Step 1: Start uvicorn in background
    print("Starting pv-ai...")
    uvicorn_process = subprocess.Popen(
        [sys.executable, "-m", "uvicorn", "main:app",
         "--host", "127.0.0.1", "--port", "5000"],
        cwd=os.path.dirname(os.path.abspath(__file__))
    )
    print("Waiting for pv-ai to start...")
    time.sleep(5)

    # Step 2: Start cloudflare tunnel and capture URL
    print("Starting Cloudflare tunnel...")
    npx_path = shutil.which("npx") or "npx"
    tunnel_process = subprocess.Popen(
        [npx_path, "cloudflared", "tunnel", "--url",
         "http://127.0.0.1:5000"],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        cwd=os.path.dirname(os.path.abspath(__file__))
    )

    # Step 3: Read tunnel URL from output
    tunnel_url = None
    print("Waiting for tunnel URL...")
    start_time = time.time()
    while time.time() - start_time < 30:
        line = tunnel_process.stderr.readline()
        if line:
            match = re.search(
                r'https://[a-z0-9-]+\.trycloudflare\.com',
                line
            )
            if match:
                tunnel_url = match.group(0)
                print(f"Tunnel URL: {tunnel_url}")
                break

    if not tunnel_url:
        print("Failed to get tunnel URL")
        uvicorn_process.terminate()
        tunnel_process.terminate()
        return

    # Step 4: Update Railway
    print("Updating Railway FASTAPI_URL...")
    success = update_railway_fastapi_url(tunnel_url)

    if success:
        print("\n✅ ProVOC AI is ready!")
        print(f"Tunnel: {tunnel_url}")
        print("Railway will redeploy in ~1 minute")
        print("\nPress Ctrl+C to stop all services")
    else:
        print("Failed to update Railway - update FASTAPI_URL manually")

    # Keep running
    try:
        uvicorn_process.wait()
    except KeyboardInterrupt:
        print("\nStopping services...")
        uvicorn_process.terminate()
        tunnel_process.terminate()

if __name__ == "__main__":
    main()
