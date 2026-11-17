"""Three small real, read-only API proof adapters with fixed account targets."""
import re
from urllib.parse import quote

from .core import BridgeError, HTTPSJSON


class Providers:
    def __init__(self, config, transport=None):
        self.config=config
        self.transport=transport or HTTPSJSON()

    def _token(self,key):
        token=self.config.get(key)
        if not token:
            raise BridgeError("PENDING_CREDENTIALS")
        if "\r" in token or "\n" in token:
            raise BridgeError("INVALID_CREDENTIAL")
        return token

    def notion_search(self,query="NOX",limit=10):
        if not isinstance(query,str) or len(query)>200 or type(limit) is not int or not 1<=limit<=50:
            raise BridgeError("INVALID_SEARCH")
        self.config.reject_secrets(query)
        value=self.transport.request("api.notion.com","POST","/v1/search",{
            "Authorization":"Bearer "+self._token("NOX_NOTION_TOKEN"),
            "Notion-Version":self.config.get("NOX_NOTION_VERSION","2026-03-11")},
            {"query":query,"page_size":limit,"filter":{"property":"object","value":"page"},
             "sort":{"direction":"descending","timestamp":"last_edited_time"}})
        rows=value.get("results")
        if not isinstance(rows,list):
            raise BridgeError("NOTION_INVALID_RESPONSE")
        pages=[]
        for row in rows[:limit]:
            if not isinstance(row,dict) or row.get("object")!="page":
                raise BridgeError("NOTION_INVALID_RESPONSE")
            props=row.get("properties",{})
            title=""
            if isinstance(props,dict):
                for prop in props.values():
                    if isinstance(prop,dict) and prop.get("type")=="title" and isinstance(prop.get("title"),list):
                        parts=[]
                        for x in prop["title"]:
                            if isinstance(x,dict):
                                text=x.get("plain_text")
                                if text is None and isinstance(x.get("text"),dict):
                                    text=x["text"].get("content","")
                                parts.append(text if isinstance(text,str) else "")
                        title="".join(parts)[:500]
                        break
            pages.append({"id":row.get("id"),"title":title,"url":row.get("url"),"last_edited_time":row.get("last_edited_time")})
        return self.config.redact({"status":"proof_succeeded","service":"notion","pages":pages,
                                   "has_more":bool(value.get("has_more")),"remote_verified":True,
                                   "scope":"titles_of_pages_shared_with_integration"})

    def github_repo(self):
        target=self.config.get("NOX_GITHUB_REPO")
        if not re.fullmatch(r"[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+",target) or any(p in (".","..") for p in target.split("/")):
            raise BridgeError("GITHUB_REPO_NOT_CONFIGURED")
        data=self.transport.request("api.github.com","GET","/repos/"+target,{
            "Authorization":"Bearer "+self._token("NOX_GITHUB_TOKEN"),
            "Accept":"application/vnd.github+json",
            "X-GitHub-Api-Version":self.config.get("NOX_GITHUB_API_VERSION","2026-03-10")})
        if not isinstance(data.get("full_name"),str) or data["full_name"].casefold()!=target.casefold():
            raise BridgeError("GITHUB_REPO_IDENTITY_MISMATCH")
        return self.config.redact({"status":"proof_succeeded","service":"github","remote_verified":True,
                                   **{k:data.get(k) for k in ("id","full_name","html_url","private","default_branch")}})

    def gitlab_project(self):
        target=self.config.get("NOX_GITLAB_PROJECT")
        if not re.fullmatch(r"[A-Za-z0-9_.-]+(?:/[A-Za-z0-9_.-]+)*",target) or any(p in (".","..") for p in target.split("/")):
            raise BridgeError("GITLAB_PROJECT_NOT_CONFIGURED")
        data=self.transport.request("gitlab.com","GET","/api/v4/projects/"+quote(target,safe=""),{
            "PRIVATE-TOKEN":self._token("NOX_GITLAB_TOKEN")})
        if (target.isdigit() and str(data.get("id"))!=target) or (not target.isdigit() and data.get("path_with_namespace")!=target):
            raise BridgeError("GITLAB_PROJECT_IDENTITY_MISMATCH")
        return self.config.redact({"status":"proof_succeeded","service":"gitlab","remote_verified":True,
                                   **{k:data.get(k) for k in ("id","path_with_namespace","web_url","visibility","default_branch")}})
