# -*- coding: utf-8 -*-
import json
import urllib.request

TOKEN = "9f63d90f-1145-4093-a3ca-02677de69f5e"
URL = "https://backboard.railway.com/graphql/v2"
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

# Query latest deployments and their logs
q_deps = """
query project($id: String!) {
    project(id: $id) {
        id
        name
        services {
            edges {
                node {
                    id
                    name
                }
            }
        }
    }
}
"""
res = graphql_query(q_deps, {"id": "56fcbff5-ac17-4f21-a05b-758c108bcfc3"})
print(json.dumps(res, indent=2, ensure_ascii=False))

# Query deployments for service
q_service_deps = """
query deployments($serviceId: String!) {
    deployments(first: 3, input: { serviceId: $serviceId }) {
        edges {
            node {
                id
                status
                canRedeploy
                staticUrl
                createdAt
            }
        }
    }
}
"""
res_deps = graphql_query(q_service_deps, {"serviceId": "fd074d3b-2055-4ebc-be99-0b3e067275b2"})
print("Deployments:")
print(json.dumps(res_deps, indent=2, ensure_ascii=False))

# If deployment exists, get deployment logs
if "data" in res_deps and res_deps["data"].get("deployments"):
    edges = res_deps["data"]["deployments"]["edges"]
    if edges:
        latest_dep_id = edges[0]["node"]["id"]
        print(f"\nFetching logs for deployment: {latest_dep_id} (Status: {edges[0]['node']['status']})...")
        q_logs = """
        query deploymentLogs($deploymentId: String!) {
            deploymentLogs(deploymentId: $deploymentId, limit: 100) {
                message
                severity
                timestamp
            }
        }
        """
        logs_res = graphql_query(q_logs, {"deploymentId": latest_dep_id})
        if "data" in logs_res and logs_res["data"].get("deploymentLogs"):
            for entry in logs_res["data"]["deploymentLogs"]:
                print(f"[{entry.get('severity', 'LOG')}] {entry.get('message', '')}")
        else:
            print("Logs response:", json.dumps(logs_res, indent=2, ensure_ascii=False))
