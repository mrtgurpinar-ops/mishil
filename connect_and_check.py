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

# Connect GitHub repo to service
q_connect_repo = """
mutation serviceConnectRepo($serviceId: String!, $repo: String!) {
    serviceConnect(serviceId: $serviceId, repo: $repo) {
        id
        name
    }
}
"""
res = graphql_query(q_connect_repo, {"serviceId": "fd074d3b-2055-4ebc-be99-0b3e067275b2", "repo": "mrtgurpinar-ops/mishil"})
print("Connect Repo Response:")
print(json.dumps(res, indent=2, ensure_ascii=False))

# Check deployments
q_deployments = """
query deployments($serviceId: String!) {
    deployments(first: 5, input: { serviceId: $serviceId }) {
        edges {
            node {
                id
                status
                createdAt
                url
            }
        }
    }
}
"""
res_dep = graphql_query(q_deployments, {"serviceId": "fd074d3b-2055-4ebc-be99-0b3e067275b2"})
print("Deployments:")
print(json.dumps(res_dep, indent=2, ensure_ascii=False))
