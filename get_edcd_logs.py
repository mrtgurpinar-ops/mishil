# -*- coding: utf-8 -*-
import json
import urllib.request

TOKEN = "9f63d90f-1145-4093-a3ca-02677de69f5e"
URL = "https://backboard.railway.com/graphql/v2"
DEP_ID = "edcd9e0c-e3cd-4523-8a88-5be10ff35a3d"

headers = {
    "Content-Type": "application/json",
    "Authorization": f"Bearer {TOKEN}",
    "User-Agent": "Mozilla/5.0"
}

payload = json.dumps({
    "query": """
    query deploymentLogs($deploymentId: String!) {
        deploymentLogs(deploymentId: $deploymentId, limit: 100) {
            message
            severity
        }
    }
    """,
    "variables": {"deploymentId": DEP_ID}
}).encode("utf-8")

req = urllib.request.Request(URL, data=payload, headers=headers)
with urllib.request.urlopen(req) as resp:
    data = json.loads(resp.read().decode("utf-8"))
    for l in data.get("data", {}).get("deploymentLogs", []):
        print(f"[{l.get('severity', 'LOG')}] {l.get('message', '')}")
