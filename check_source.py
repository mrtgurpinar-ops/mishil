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

# Query service source
q_source = """
query service($id: String!) {
    service(id: $id) {
        id
        name
        source {
            image
            repo
        }
    }
}
"""
print("Service Source:")
print(json.dumps(graphql_query(q_source, {"id": "fd074d3b-2055-4ebc-be99-0b3e067275b2"}), indent=2))
