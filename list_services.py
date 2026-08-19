# -*- coding: utf-8 -*-
import json
import urllib.request

TOKEN = "9f63d90f-1145-4093-a3ca-02677de69f5e"
URL = "https://backboard.railway.com/graphql/v2"
PROJECT_ID = "56fcbff5-ac17-4f21-a05b-758c108bcfc3"

headers = {
    "Content-Type": "application/json",
    "Authorization": f"Bearer {TOKEN}",
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"
}

def graphql_query(q, vars=None):
    payload = json.dumps({"query": q, "variables": vars or {}}).encode("utf-8")
    req = urllib.request.Request(URL, data=payload, headers=headers)
    with urllib.request.urlopen(req, timeout=15) as resp:
        return json.loads(resp.read().decode("utf-8"))

q = """
query getProject($id: String!) {
  project(id: $id) {
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

res = graphql_query(q, {"id": PROJECT_ID})
services = res["data"]["project"]["services"]["edges"]
print("Aktif Servisler:")
for s in services:
    print(f"- ID: {s['node']['id']}, Name: {s['node']['name']}")
