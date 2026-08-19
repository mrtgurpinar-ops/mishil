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

def graphql_query(q, vars=None):
    payload = json.dumps({"query": q, "variables": vars or {}}).encode("utf-8")
    req = urllib.request.Request(URL, data=payload, headers=headers)
    with urllib.request.urlopen(req, timeout=15) as resp:
        return json.loads(resp.read().decode("utf-8"))

# Delete duplicate ephemeral services, keep ONLY the clean 'mishil' or primary service
delete_mutation = """
mutation serviceDelete($id: String!) {
    serviceDelete(id: $id)
}
"""

for sid in [
    "2481ed65-c245-4561-9414-332791d5c7f7", # efficient-playfulness
    "8fda4d08-a43d-48de-b1b2-b98211e42625", # exemplary-expression
    "b310e428-c5a5-4395-8798-c257dda88d21", # generous-curiosity
]:
    try:
        r = graphql_query(delete_mutation, {"id": sid})
        print(f"Silindi {sid}:", r)
    except Exception as e:
        print(f"Hata {sid}:", e)

print("Temizlik bitti!")
