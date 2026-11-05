from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse

from config import BASE_URL
from templating import templates

router = APIRouter(include_in_schema=False, default_response_class=HTMLResponse)


@router.get("/")
def home(request: Request):
    return templates.TemplateResponse(request, "home.html", {"page": "home", "base_url": BASE_URL})


@router.get("/developers")
def developers(request: Request):
    return templates.TemplateResponse(request, "developers.html", {"page": "developers", "base_url": BASE_URL})


@router.get("/playground")
def playground(request: Request):
    return templates.TemplateResponse(request, "playground.html", {"page": "playground", "base_url": BASE_URL})


@router.get("/about")
def about(request: Request):
    return templates.TemplateResponse(request, "about.html", {"page": "about", "base_url": BASE_URL})
