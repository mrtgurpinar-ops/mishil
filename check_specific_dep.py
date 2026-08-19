# -*- coding: utf-8 -*-
import json
import urllib.request

TOKEN = "9f63d90f-1145-4093-a3ca-02677de69f5e"
URL = "https://backboard.railway.com/graphql/v2"
DEP_ID = "51dbee8c-60a1-49da-91d6-3e910877c076"

headers = {
    "Content-Type": "application/json",
    "Authorization": f"Bearer {TOKEN}",
    "User-Agent": "Mozilla/5.0"
}

def graphql_query(query_str, variables=None):
    payload = json.dumps({"query": query_str, "variables": variables or {}}).encode("utf-8")
    req = urllib.request.Request(URL, data=payload, headers=headers)
    with urllib.request.urlopen(req, timeout=15) as resp:
        return json.loads(resp.read().decode("utf-8"))

q = """
query deployment($id: String!) {
    deployment(id: $id) {
        id
        status
        createdAt
        url
    }
}
"""
print("Deployment Status:")
print(json.dumps(graphql_query(q, {"id": DEP_ID}), indent=2))

q_logs = """
query deploymentLogs($deploymentId: String!) {
    deploymentLogs(deploymentId: $deploymentId, limit: 100) {
        message
        severity
        timestamp
    }
}
"""
logs_res = graphql_query(q_logs, {"deploymentId": DEP_ID})
print("\nDeployment Logs:")
for l in logs_res.get("data", {}).get("deploymentLogs", []):
    print(f"[{l.get('severity', 'LOG')}] {l.get('message', '')}")
