# -*- coding: utf-8 -*-
import json
import urllib.request
import urllib.error

TOKEN = "9f63d90f-1145-4093-a3ca-02677de69f5e"
URL = "https://backboard.railway.com/graphql/v2"
PROJECT_ID = "56fcbff5-ac17-4f21-a05b-758c108bcfc3"
ENV_ID = "19bda2e9-b971-45df-9706-d050f25d9dd7"

headers = {
    "Content-Type": "application/json",
    "Authorization": f"Bearer {TOKEN}",
    "User-Agent": "Mozilla/5.0"
}

def graphql_query(query_str, variables=None):
    payload = json.dumps({"query": query_str, "variables": variables or {}}).encode("utf-8")
    req = urllib.request.Request(URL, data=payload, headers=headers)
    try:
        with urllib.request.urlopen(req, timeout=20) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        err = e.read().decode("utf-8")
        return {"http_error": e.code, "body": err}
    except Exception as e:
        return {"error": str(e)}

# Trigger fresh GitHub Repo Deploy from main branch
q_github_deploy = """
mutation githubRepoDeploy($input: GitHubRepoDeployInput!) {
    githubRepoDeploy(input: $input)
}
"""
res_deploy = graphql_query(q_github_deploy, {
    "input": {
        "projectId": PROJECT_ID,
        "environmentId": ENV_ID,
        "repo": "mrtgurpinar-ops/mishil",
        "branch": "main"
    }
})
print("GitHub Repo Deploy Response:", json.dumps(res_deploy, indent=2, ensure_ascii=False))
