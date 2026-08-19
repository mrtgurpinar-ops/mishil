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
    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except Exception as e:
        return {"error": str(e)}

q_service = """
query service($id: String!) {
    service(id: $id) {
        id
        name
        updatedAt
    }
}
"""
res = graphql_query(q_service, {"id": "fd074d3b-2055-4ebc-be99-0b3e067275b2"})
print("Service Detail:")
print(json.dumps(res, indent=2, ensure_ascii=False))

# Query project services
q_project = """
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
res_proj = graphql_query(q_project, {"id": "56fcbff5-ac17-4f21-a05b-758c108bcfc3"})
print("Project Info:")
print(json.dumps(res_proj, indent=2, ensure_ascii=False))
