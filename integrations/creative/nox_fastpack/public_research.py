"""Read-only public research adapters reused from owner Creative Studio V17.
Only explicit CS5 RPC can call these. No background fetch, listener or second API engine.
"""
from __future__ import annotations
import datetime as dt
import json
import os
import re
from urllib.parse import urlencode, quote, urlsplit
from urllib.request import Request, build_opener, HTTPRedirectHandler
from urllib.error import URLError, HTTPError

HOSTS = frozenset(("www.googleapis.com","openlibrary.org","itunes.apple.com",
                   "api.crossref.org","api.worldbank.org","wikimedia.org","api.openalex.org"))
SOURCES = ("books","openlibrary","apple","crossref","worldbank","wikimedia","openalex")
MAX_BYTES = 2_000_000

class ResearchHold(ValueError):
    pass

def research_url(source, query, today=None):
    if source not in SOURCES: raise ResearchHold("CS5_RESEARCH_SOURCE_HOLD")
    if not isinstance(query,str) or not 1 <= len(query.strip()) <= 160 or any(ord(c)<32 for c in query):
        raise ResearchHold("CS5_RESEARCH_QUERY_HOLD")
    q=query.strip()
    if source=="books": address="https://www.googleapis.com/books/v1/volumes?"+urlencode({"q":q,"maxResults":8})
    elif source=="openlibrary": address="https://openlibrary.org/search.json?"+urlencode({"q":q,"limit":8,"fields":"key,title,author_name,edition_count"})
    elif source=="apple": address="https://itunes.apple.com/search?"+urlencode({"term":q,"limit":8,"entity":"podcast"})
    elif source=="crossref": address="https://api.crossref.org/works?"+urlencode({"query":q,"rows":8,"select":"DOI,title,is-referenced-by-count"})
    elif source=="worldbank":
        if not re.fullmatch("[a-zA-Z]{2}",q):raise ResearchHold("CS5_COUNTRY_CODE_HOLD")
        address="https://api.worldbank.org/v2/country/"+q.upper()+"/indicator/SP.POP.TOTL?format=json&per_page=8"
    elif source=="wikimedia":
        parts=q.split("|")
        if len(parts)!=2:raise ResearchHold("CS5_WIKIMEDIA_FORMAT_HOLD")
        lang,title=(p.strip() for p in parts)
        if not re.fullmatch("[a-zA-Z]{2,12}(?:-[a-zA-Z]{2,12})?",lang) or not title:
            raise ResearchHold("CS5_WIKIMEDIA_FORMAT_HOLD")
        end=(today or dt.datetime.now(dt.timezone.utc).date())-dt.timedelta(days=1)
        start=end-dt.timedelta(days=27)
        address="https://wikimedia.org/api/rest_v1/metrics/pageviews/per-article/"+lang.lower()+".wikipedia.org/all-access/user/"+quote(title.replace(" ","_"),safe="")+f"/daily/{start:%Y%m%d}/{end:%Y%m%d}"
    else: address="https://api.openalex.org/works?"+urlencode({"search":q,"per-page":8})
    _check_origin(address)
    return address

def _check_origin(url):
    v=urlsplit(url)
    if v.scheme!="https" or v.hostname not in HOSTS or v.username or v.password:
        raise ResearchHold("CS5_RESEARCH_ORIGIN_HOLD")

class SameHostRedirect(HTTPRedirectHandler):
    def redirect_request(self,req,fp,code,msg,headers,newurl):
        old=urlsplit(req.full_url);new=urlsplit(newurl)
        if new.scheme!="https" or new.hostname!=old.hostname or new.hostname not in HOSTS:
            raise ResearchHold("CS5_RESEARCH_REDIRECT_HOLD")
        return super().redirect_request(req,fp,code,msg,headers,newurl)

def _fetch(url):
    _check_origin(url)
    headers={"Accept":"application/json","User-Agent":"NOX-HELION-CS5/1.0 (user requested metadata)"}
    if urlsplit(url).hostname=="api.openalex.org":
        key=os.environ.get("OPENALEX_API_KEY","").strip()
        if key:headers["Authorization"]="Bearer "+key
    try:
        with build_opener(SameHostRedirect()).open(Request(url,headers=headers),timeout=12) as response:
            raw=response.read(MAX_BYTES+1)
    except HTTPError as exc:raise ResearchHold("CS5_RESEARCH_HTTP_"+str(exc.code)) from exc
    except (URLError,TimeoutError,OSError) as exc:raise ResearchHold("CS5_RESEARCH_API_OFFLINE") from exc
    if len(raw)>MAX_BYTES:raise ResearchHold("CS5_RESEARCH_SIZE_HOLD")
    try:return json.loads(raw.decode("utf-8-sig"))
    except (ValueError,UnicodeError) as exc:raise ResearchHold("CS5_RESEARCH_BAD_JSON") from exc

def _txt(x,limit=240):
    return x[:limit] if isinstance(x,str) else ""

def _safe_link(value):
    if not isinstance(value,str) or len(value)>650:return None
    p=urlsplit(value)
    return value if p.scheme in ("https","http") and p.hostname and not p.username and not p.password else None

def _record(title,detail="",count=None,unit="",link=None):
    return {"title":_txt(title), "detail":_txt(detail),
            "metric":count if type(count) in (int,float) and abs(count)<1e13 else None,
            "unit":_txt(unit,50),"source_url":_safe_link(link)}

def summaries(source,data):
    if source=="worldbank":rows=data[1] if isinstance(data,list) and len(data)>1 else []
    elif source=="crossref":rows=(data.get("message") or {}).get("items",[]) if isinstance(data,dict) else []
    else:
        key={"books":"items","openlibrary":"docs","apple":"results","wikimedia":"items","openalex":"results"}[source]
        rows=data.get(key,[]) if isinstance(data,dict) else []
    if not isinstance(rows,list):raise ResearchHold("CS5_RESEARCH_SHAPE_HOLD")
    found=[]
    for r in rows[:8]:
        if not isinstance(r,dict):continue
        if source=="books":
            z=r.get("volumeInfo") or {}
            if not isinstance(z,dict):z={}
            found.append(_record(z.get("title"),link=z.get("infoLink")))
        elif source=="openlibrary":
            key=r.get("key","")
            found.append(_record(r.get("title"),count=r.get("edition_count"),unit="editions",
                          link="https://openlibrary.org"+key if isinstance(key,str) and key.startswith("/") else None))
        elif source=="apple":found.append(_record(r.get("collectionName") or r.get("trackName"),r.get("artistName"),link=r.get("collectionViewUrl")))
        elif source=="crossref":
            title=r.get("title") or []
            doi=r.get("DOI")
            found.append(_record(title[0] if isinstance(title,list) and title else "",_txt(doi),r.get("is-referenced-by-count"),"citations",
                          "https://doi.org/"+quote(doi,safe="/") if isinstance(doi,str) else None))
        elif source=="worldbank":
            country=r.get("country") or {}
            found.append(_record(country.get("value") if isinstance(country,dict) else "",_txt(r.get("date")),r.get("value"),"population","https://data.worldbank.org/indicator/SP.POP.TOTL"))
        elif source=="wikimedia":found.append(_record(r.get("article"),_txt(r.get("timestamp")),r.get("views"),"pageviews"))
        else:found.append(_record(r.get("title") or r.get("display_name"),str(r.get("publication_year","")),r.get("cited_by_count"),"citations",r.get("id")))
    return found

def research(studio,request,fetcher=None):
    if studio._stop_event.is_set():raise ResearchHold("CS5_STOP_ACTIVE")
    source=request.get("source");query=request.get("query")
    url=research_url(source,query)
    payload=(fetcher or _fetch)(url)
    if studio._stop_event.is_set():raise ResearchHold("CS5_STOP_ACTIVE")
    items=summaries(source,payload)
    return {"status":"LIVE_PUBLIC_METADATA_NOT_SALES" if fetcher is None else "TEST_METADATA_NOT_SALES",
            "source":source,"request_url":url,"observed_at_utc":dt.datetime.now(dt.timezone.utc).isoformat(),
            "count":len(items),"items":items,
            "notice":"Views, citations, catalog editions and population are not sales."}
