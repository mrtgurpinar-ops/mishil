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

q = """
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
res = graphql_query(q, {"id": "56fcbff5-ac17-4f21-a05b-758c108bcfc3"})
print(json.dumps(res, indent=2, ensure_ascii=False))
