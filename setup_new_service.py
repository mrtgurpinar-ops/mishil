# -*- coding: utf-8 -*-
import json
import urllib.request

TOKEN = "9f63d90f-1145-4093-a3ca-02677de69f5e"
URL = "https://backboard.railway.com/graphql/v2"
PROJECT_ID = "56fcbff5-ac17-4f21-a05b-758c108bcfc3"
ENV_ID = "19bda2e9-b971-45df-9706-d050f25d9dd7"
NEW_SERVICE_ID = "51dbee8c-60a1-49da-91d6-3e910877c076"
OLD_SERVICE_ID = "fd074d3b-2055-4ebc-be99-0b3e067275b2"

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

print("1. Yeni GitHub servisine ortam değişkenleri tanımlanıyor...")
q_vars = """
mutation variableCollectionUpsert($input: VariableCollectionUpsertInput!) {
    variableCollectionUpsert(input: $input)
}
"""
res_vars = graphql_query(q_vars, {
    "input": {
        "projectId": PROJECT_ID,
        "environmentId": ENV_ID,
        "serviceId": NEW_SERVICE_ID,
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

print("\n2. Yeni servise public domain atanıyor...")
q_domain = """
mutation serviceDomainCreate($input: ServiceDomainCreateInput!) {
    serviceDomainCreate(input: $input) {
        domain
    }
}
"""
res_domain = graphql_query(q_domain, {
    "input": {
        "serviceId": NEW_SERVICE_ID,
        "environmentId": ENV_ID
    }
})
print("Domain Response:", json.dumps(res_domain, indent=2))

print("\n3. Yeni servisin deployment durumu kontrol ediliyor...")
q_deps = """
query deployments($serviceId: String!) {
    deployments(first: 3, input: { serviceId: $serviceId }) {
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
"""
res_deps = graphql_query(q_deps, {"serviceId": NEW_SERVICE_ID})
print("Deployments:", json.dumps(res_deps, indent=2))
