# -*- coding: utf-8 -*-
import json
import urllib.request

TOKEN = "9f63d90f-1145-4093-a3ca-02677de69f5e"
URL = "https://backboard.railway.com/graphql/v2"
PROJECT_ID = "56fcbff5-ac17-4f21-a05b-758c108bcfc3"
ENV_ID = "19bda2e9-b971-45df-9706-d050f25d9dd7"
SERVICE_ID = "2481ed65-c245-4561-9414-332791d5c7f7"

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

print("1. Ortam değişkenleri tanımlanıyor...")
q_vars = """
mutation variableCollectionUpsert($input: VariableCollectionUpsertInput!) {
    variableCollectionUpsert(input: $input)
}
"""
res_vars = graphql_query(q_vars, {
    "input": {
        "projectId": PROJECT_ID,
        "environmentId": ENV_ID,
        "serviceId": SERVICE_ID,
        "variables": {
            "APP_NAME": "mishil",
            "ENVIRONMENT": "production",
            "PORT": "8080",
            "JWT_SECRET": "super_secret_jwt_key_for_mishil_app_min_32_chars_long",
            "REVENUECAT_WEBHOOK_SECRET": "rc_webhook_secret_example_key",
            "DATABASE_URL": "sqlite:///./mishil.db"
        }
    }
})
print("Variables Response:", json.dumps(res_vars, indent=2))

print("2. Domain bağlanıyor...")
q_domain = """
mutation serviceDomainCreate($input: ServiceDomainCreateInput!) {
    serviceDomainCreate(input: $input) {
        domain
    }
}
"""
res_domain = graphql_query(q_domain, {
    "input": {
        "serviceId": SERVICE_ID,
        "environmentId": ENV_ID
    }
})
print("Domain Response:", json.dumps(res_domain, indent=2))
