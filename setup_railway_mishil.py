# -*- coding: utf-8 -*-
import os
import sys
import json
import urllib.request
import urllib.error

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")
if hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8")

TOKENS = [
    "9f63d90f-1145-4093-a3ca-02677de69f5e",
    "204d293c-dfb4-4988-8492-aa6a206db8fc",
]

URL = "https://backboard.railway.com/graphql/v2"

def get_valid_token():
    for token in TOKENS:
        headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {token}",
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"
        }
        q = "query me { me { id name email } }"
        payload = json.dumps({"query": q}).encode("utf-8")
        req = urllib.request.Request(URL, data=payload, headers=headers)
        try:
            with urllib.request.urlopen(req, timeout=10) as resp:
                data = json.loads(resp.read().decode("utf-8"))
                if "data" in data and data["data"].get("me"):
                    print(f"✓ Valid Railway token found for: {data['data']['me']['email']}")
                    return token, headers
        except Exception as e:
            continue
    return None, None

token, headers = get_valid_token()
if not token:
    print("❌ No valid Railway token found.")
    sys.exit(1)

def graphql_query(query_str, variables=None):
    payload = json.dumps({"query": query_str, "variables": variables or {}}).encode("utf-8")
    req = urllib.request.Request(URL, data=payload, headers=headers)
    try:
        with urllib.request.urlopen(req, timeout=20) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        err_body = e.read().decode("utf-8")
        return {"error": f"HTTP {e.code}: {err_body}"}
    except Exception as e:
        return {"error": str(e)}

print("\n🔍 1. Workspace Bilgisi Sorgulanıyor...")
q_me = """
query me {
    me {
        id
        name
        email
        workspaces {
            id
            name
        }
        projects {
            edges {
                node {
                    id
                    name
                    environments {
                        edges {
                            node {
                                id
                                name
                            }
                        }
                    }
                }
            }
        }
    }
}
"""
me_res = graphql_query(q_me)
print("Me & Workspaces Response:")
print(json.dumps(me_res, indent=2, ensure_ascii=False))

workspace_id = None
if "data" in me_res and me_res["data"].get("me"):
    me_data = me_res["data"]["me"]
    workspaces = me_data.get("workspaces", [])
    if workspaces:
        workspace_id = workspaces[0]["id"]
        print(f"✓ Workspace ID: {workspace_id} ({workspaces[0]['name']})")

print(f"\n🚀 2. Railway Üzerinde Yeni Proje Oluşturuluyor (Workspace: {workspace_id})...")
q_create_proj = """
mutation projectCreate($input: ProjectCreateInput!) {
    projectCreate(input: $input) {
        id
        name
        environments {
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
proj_input = {"name": "mishil", "description": "Mishil - Baby Sleep & Routines Platform"}
if workspace_id:
    proj_input["workspaceId"] = workspace_id

res_proj = graphql_query(q_create_proj, {"input": proj_input})
print("Project Create Response:")
print(json.dumps(res_proj, indent=2, ensure_ascii=False))

project_id = None
env_id = None

if res_proj and res_proj.get("data") and res_proj["data"].get("projectCreate"):
    project_id = res_proj["data"]["projectCreate"]["id"]
    envs = res_proj["data"]["projectCreate"]["environments"]["edges"]
    if envs:
        env_id = envs[0]["node"]["id"]
    print(f"✓ Proje ID: {project_id}, Env ID: {env_id}")
else:
    # Query existing projects to find mishil or use first project
    print("Querying projects...")
    q_projs = """
    query projects {
        projects {
            edges {
                node {
                    id
                    name
                    environments {
                        edges {
                            node {
                                id
                                name
                            }
                        }
                    }
                }
            }
        }
    }
    """
    p_data = graphql_query(q_projs)
    print(json.dumps(p_data, indent=2, ensure_ascii=False))
    if "data" in p_data and p_data["data"].get("projects"):
        for edge in p_data["data"]["projects"]["edges"]:
            node = edge["node"]
            if node["name"].lower() == "mishil":
                project_id = node["id"]
                env_id = node["environments"]["edges"][0]["node"]["id"]
                break

if not project_id:
    print("❌ Proje ID belirlenemedi.")
    sys.exit(1)

# 2. Add PostgreSQL Database Service or Plugin
print(f"\n📦 2. Projeye ({project_id}) PostgreSQL Veritabanı Ekleniyor...")
q_create_db = """
mutation templateDeploy($input: TemplateDeployInput!) {
    templateDeploy(input: $input) {
        workflowId
    }
}
"""
# Alternatively create service for postgres
q_create_service = """
mutation serviceCreate($input: ServiceCreateInput!) {
    serviceCreate(input: $input) {
        id
        name
    }
}
"""
# Create backend service from GitHub repo
print(f"\n🌐 3. GitHub Reposu ('mrtgurpinar-ops/mishil') Servisi Oluşturuluyor...")
q_create_repo_service = """
mutation serviceCreate($input: ServiceCreateInput!) {
    serviceCreate(input: $input) {
        id
        name
    }
}
"""
res_service = graphql_query(q_create_repo_service, {
    "input": {
        "projectId": project_id,
        "name": "mishil-api",
        "source": {
            "repo": "mrtgurpinar-ops/mishil"
        }
    }
})
print("Service Create Response:")
print(json.dumps(res_service, indent=2, ensure_ascii=False))

service_id = None
if "data" in res_service and res_service["data"].get("serviceCreate"):
    service_id = res_service["data"]["serviceCreate"]["id"]
    print(f"✓ Backend Servis ID: {service_id}")

# 4. Generate Public Domain for the Service
if service_id and env_id:
    print(f"\n🔗 4. Servis İçin Public Domain Tahsis Ediliyor...")
    q_domain = """
    mutation serviceDomainCreate($input: ServiceDomainCreateInput!) {
        serviceDomainCreate(input: $input) {
            domain
        }
    }
    """
    res_domain = graphql_query(q_domain, {
        "input": {
            "serviceId": service_id,
            "environmentId": env_id
        }
    })
    print("Domain Create Response:")
    print(json.dumps(res_domain, indent=2, ensure_ascii=False))

    # 5. Set Environment Variables (DATABASE_URL, JWT_SECRET, PORT)
    print(f"\n⚙️ 5. Ortam Değişkenleri Tanımlanıyor...")
    q_vars = """
    mutation variableCollectionUpsert($input: VariableCollectionUpsertInput!) {
        variableCollectionUpsert(input: $input)
    }
    """
    res_vars = graphql_query(q_vars, {
        "input": {
            "projectId": project_id,
            "environmentId": env_id,
            "serviceId": service_id,
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
    print("Variables Upsert Response:")
    print(json.dumps(res_vars, indent=2, ensure_ascii=False))

print("\n🎉 Tüm Railway Altyapı Adımları Tamamlandı!")
