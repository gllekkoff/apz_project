import itertools
import logging
import os
from typing import Iterable, List, Optional

import httpx
from fastapi import FastAPI, HTTPException, Request, Response
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse


LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO").upper()
logging.basicConfig(level=LOG_LEVEL, format="%(asctime)s %(levelname)s %(name)s %(message)s")
log = logging.getLogger("api-gateway")


def _split_csv(value: str) -> List[str]:
    return [v.strip().rstrip("/") for v in value.split(",") if v.strip()]


AUTH_SERVICE_URLS = _split_csv(
    os.getenv("AUTH_SERVICE_URLS", "http://auth-service-1:8000,http://auth-service-2:8000")
)
MARKET_SERVICE_URL = os.getenv("MARKET_SERVICE_URL", "http://market-data-service:8000").rstrip("/")
REPORT_SERVICE_URL = os.getenv("REPORT_SERVICE_URL", "http://reporting-service:8000").rstrip("/")
UPSTREAM_TIMEOUT_SECONDS = float(os.getenv("UPSTREAM_TIMEOUT_SECONDS", "10"))

if not AUTH_SERVICE_URLS:
    raise RuntimeError("AUTH_SERVICE_URLS must list at least one auth-service base URL")


PUBLIC_AUTH_PATHS = {"/auth/register", "/auth/login"}

HOP_BY_HOP = {
    "connection",
    "keep-alive",
    "proxy-authenticate",
    "proxy-authorization",
    "te",
    "trailers",
    "transfer-encoding",
    "upgrade",
    "host",
    "content-length",
}


app = FastAPI(
    title="API Gateway",
    description="Public entry point. Routes /auth, /market, and /reports to internal services.",
    version="1.0.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

_auth_pool = itertools.cycle(AUTH_SERVICE_URLS)
_http_client: Optional[httpx.AsyncClient] = None


@app.on_event("startup")
async def _startup() -> None:
    global _http_client
    _http_client = httpx.AsyncClient(timeout=UPSTREAM_TIMEOUT_SECONDS)
    log.info(
        "gateway up: auth=%s, market=%s, reports=%s",
        AUTH_SERVICE_URLS,
        MARKET_SERVICE_URL,
        REPORT_SERVICE_URL,
    )


@app.on_event("shutdown")
async def _shutdown() -> None:
    if _http_client is not None:
        await _http_client.aclose()


def _next_auth_base() -> str:
    return next(_auth_pool)


def _filter_request_headers(headers: Iterable[tuple]) -> dict:
    return {k: v for k, v in headers if k.lower() not in HOP_BY_HOP}


def _filter_response_headers(headers: httpx.Headers) -> dict:
    return {k: v for k, v in headers.items() if k.lower() not in HOP_BY_HOP}


async def _validate_token(authorization: Optional[str]) -> dict:
    if not authorization:
        raise HTTPException(status_code=401, detail="missing Authorization header")

    assert _http_client is not None
    last_exc: Optional[Exception] = None
    for _ in range(len(AUTH_SERVICE_URLS)):
        base = _next_auth_base()
        try:
            resp = await _http_client.post(
                f"{base}/auth/validate",
                headers={"Authorization": authorization},
            )
        except httpx.RequestError as exc:
            last_exc = exc
            log.warning("auth-service %s unreachable: %s", base, exc)
            continue

        if resp.status_code == 401:
            raise HTTPException(status_code=401, detail="invalid or expired token")
        if resp.status_code >= 500:
            last_exc = RuntimeError(f"auth-service {base} returned {resp.status_code}")
            log.warning(str(last_exc))
            continue
        try:
            return resp.json()
        except ValueError:
            return {}

    raise HTTPException(status_code=503, detail=f"auth-service unavailable: {last_exc}")


async def _proxy(
    request: Request,
    bases: List[str],
    upstream_path: str,
) -> Response:
    assert _http_client is not None
    body = await request.body()
    headers = _filter_request_headers(request.headers.items())

    last_exc: Optional[Exception] = None
    for base in bases:
        url = f"{base}{upstream_path}"
        if request.url.query:
            url = f"{url}?{request.url.query}"
        try:
            upstream = await _http_client.request(
                request.method,
                url,
                headers=headers,
                content=body,
            )
        except httpx.RequestError as exc:
            last_exc = exc
            log.warning("upstream %s unreachable: %s", url, exc)
            continue
        return Response(
            content=upstream.content,
            status_code=upstream.status_code,
            headers=_filter_response_headers(upstream.headers),
            media_type=upstream.headers.get("content-type"),
        )

    log.error("all upstreams failed for %s %s: %s", request.method, upstream_path, last_exc)
    return JSONResponse(
        status_code=502,
        content={"detail": f"upstream service unavailable: {last_exc}"},
    )


@app.get("/health")
async def health() -> dict:
    return {
        "status": "ok",
        "service": "api-gateway",
        "upstreams": {
            "auth": AUTH_SERVICE_URLS,
            "market": MARKET_SERVICE_URL,
            "reports": REPORT_SERVICE_URL,
        },
    }


@app.get("/")
async def index() -> dict:
    return {
        "service": "api-gateway",
        "routes": {
            "/auth/*": "auth-service",
            "/market/*": "market-data-service",
            "/reports/*": "reporting-service",
        },
        "public": sorted(PUBLIC_AUTH_PATHS),
    }


@app.api_route(
    "/auth/{full_path:path}",
    methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"],
)
async def proxy_auth(full_path: str, request: Request) -> Response:
    incoming_path = f"/auth/{full_path}"
    if incoming_path not in PUBLIC_AUTH_PATHS:
        await _validate_token(request.headers.get("authorization"))
    start = _next_auth_base()
    ordered = [start] + [u for u in AUTH_SERVICE_URLS if u != start]
    return await _proxy(request, ordered, incoming_path)


@app.api_route(
    "/market/{full_path:path}",
    methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"],
)
async def proxy_market(full_path: str, request: Request) -> Response:
    await _validate_token(request.headers.get("authorization"))
    return await _proxy(request, [MARKET_SERVICE_URL], f"/market/{full_path}")


@app.api_route(
    "/reports/{full_path:path}",
    methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"],
)
async def proxy_reports(full_path: str, request: Request) -> Response:
    await _validate_token(request.headers.get("authorization"))
    return await _proxy(request, [REPORT_SERVICE_URL], f"/reports/{full_path}")
