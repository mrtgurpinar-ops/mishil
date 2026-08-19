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

# Delete old broken services
for sid in ["fd074d3b-2055-4ebc-be99-0b3e067275b2", "51dbee8c-60a1-49da-91d6-3e910877c076", "ce8645f4-6b64-495c-a4cb-b9d8e9f6d974"]:
    q = """
    mutation serviceDelete($id: String!) {
        serviceDelete(id: $id)
    }
    """
    try:
        res = graphql_query(q, {"id": sid})
        print(f"Deleted service {sid}:", res)
    except Exception as e:
        print(f"Failed to delete {sid}:", e)
