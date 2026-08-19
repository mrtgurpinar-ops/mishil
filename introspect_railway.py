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

# Introspect available mutations for deployment & git in Railway GraphQL
q_schema = """
query Introspect {
    __schema {
        mutationType {
            fields {
                name
                description
                args {
                    name
                    type {
                        name
                        kind
                    }
                }
            }
        }
    }
}
"""
res = graphql_query(q_schema)
mutations = res.get("data", {}).get("__schema", {}).get("mutationType", {}).get("fields", [])
deploy_mutations = [m for m in mutations if "deploy" in m["name"].lower() or "service" in m["name"].lower() or "git" in m["name"].lower()]

print("Available Deploy/Service Mutations in Railway:")
for m in deploy_mutations:
    print(f"- {m['name']}: {m.get('description', '')}")
