# -*- coding: utf-8 -*-
import json
import urllib.request

TOKEN = "9f63d90f-1145-4093-a3ca-02677de69f5e"
URL = "https://backboard.railway.com/graphql/v2"
SERVICE_ID = "8fda4d08-a43d-48de-b1b2-b98211e42625"

headers = {
    "Content-Type": "application/json",
    "Authorization": f"Bearer {TOKEN}",
    "User-Agent": "Mozilla/5.0"
}

payload = json.dumps({
    "query": """
    query deployments($serviceId: String!) {
        deployments(first: 2, input: { serviceId: $serviceId }) {
            edges {
                node {
                    id
                    status
                    staticUrl
                    createdAt
                }
            }
        }
    }
    """,
    "variables": {"serviceId": SERVICE_ID}
}).encode("utf-8")

req = urllib.request.Request(URL, data=payload, headers=headers)
with urllib.request.urlopen(req) as resp:
    data = json.loads(resp.read().decode("utf-8"))
    print(json.dumps(data, indent=2))
