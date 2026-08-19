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

# Introspect githubRepoDeploy args
q_args = """
query IntrospectArgs {
    __type(name: "GitHubRepoDeployInput") {
        inputFields {
            name
            type {
                name
                kind
            }
        }
    }
}
"""
res_type = graphql_query(q_args)
print("GitHubRepoDeployInput Fields:", json.dumps(res_type, indent=2, ensure_ascii=False))

# Also check serviceInstanceAutoDeployUpdate input
q_auto = """
query IntrospectAuto {
    __type(name: "ServiceInstanceAutoDeployUpdateInput") {
        inputFields {
            name
            type {
                name
                kind
            }
        }
    }
}
"""
res_auto = graphql_query(q_auto)
print("ServiceInstanceAutoDeployUpdateInput Fields:", json.dumps(res_auto, indent=2, ensure_ascii=False))
