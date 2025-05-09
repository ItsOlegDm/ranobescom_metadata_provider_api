import os
from fastapi import FastAPI, Query, HTTPException
from typing import Optional, List
from pydantic import BaseModel
import httpx
from bs4 import BeautifulSoup
import re

app = FastAPI(title="Custom Metadata Provider", version="0.1.0")


# --- SCHEMAS ---
class SeriesMetadata(BaseModel):
    series: str
    sequence: Optional[str] = None


class BookMetadata(BaseModel):
    title: str
    subtitle: Optional[str] = None
    author: Optional[str] = None
    narrator: Optional[str] = None
    publisher: Optional[str] = None
    publishedYear: Optional[str] = None
    description: Optional[str] = None
    cover: Optional[str] = None
    isbn: Optional[str] = None
    asin: Optional[str] = None
    genres: Optional[List[str]] = []
    tags: Optional[List[str]] = []
    series: Optional[List[SeriesMetadata]] = []
    language: Optional[str] = None
    duration: Optional[int] = None


class ErrorResponse(BaseModel):
    error: str


# --- SETTINGS FROM ENV ---
COOKIE_DLE_USER_ID = os.getenv("DLE_USER_ID")
COOKIE_DLE_PASSWORD = os.getenv("DLE_PASSWORD")
COOKIE_PHPSESSID = os.getenv("PHPSESSID")



def get_auth_cookies() -> dict:
    if not all([COOKIE_DLE_USER_ID, COOKIE_DLE_PASSWORD, COOKIE_PHPSESSID]):
        raise HTTPException(status_code=401, detail="Missing required authentication environment variables")
    return {
        "dle_user_id": COOKIE_DLE_USER_ID,
        "dle_password": COOKIE_DLE_PASSWORD,
        "PHPSESSID": COOKIE_PHPSESSID
    }


# --- PARSING UTILITIES ---
async def fetch_and_parse_book(url: str, cookies: dict) -> BookMetadata:
    async with httpx.AsyncClient() as client:
        response = await client.get(url, cookies=cookies)
        if response.status_code != 200:
            raise HTTPException(status_code=500, detail=f"Failed to fetch book page: {url}")

        soup = BeautifulSoup(response.text, "html.parser")
        block = soup.select_one("article[itemtype='http://schema.org/Book']")

        title = block.select_one("h1.title").contents[0].strip()
        subtitle = block.select_one("span.subtitle")
        subtitle = subtitle.get_text(strip=True) if subtitle else None

        description_block = block.select_one("[itemprop='description']")
        description = description_block.get_text(separator="\n", strip=True) if description_block else None

        cover_style = block.select_one(".poster figure.cover")["style"]
        cover_match = re.search(r"url\((.*?)\)", cover_style)
        cover = cover_match.group(1) if cover_match else None

        published = block.select_one("[itemprop='dateCreated']")
        publishedYear = published.get_text(strip=True) if published else None

        lang = block.select_one("[itemprop='locationCreated']")
        language = lang.get_text(strip=True) if lang else None

        publisher_tags = block.select("span.publishers_list span a")
        publisher = ", ".join(a.get_text(strip=True) for a in publisher_tags) if publisher_tags else None

        genres = [a.get_text(strip=True) for a in block.select("#mc-fs-genre a")]
        tags = [a.get_text(strip=True) for a in block.select("[itemprop='keywords'] a")]

        duration_meta = block.select_one("[itemprop='timeRequired']")
        duration = None
        if duration_meta and duration_meta.get("content"):
            match = re.match(r"PT(\d+)H", duration_meta["content"])
            if match:
                duration = int(match.group(1)) * 3600

        return BookMetadata(
            title=title,
            subtitle=subtitle,
            description=description,
            cover=cover,
            publishedYear=publishedYear,
            language=language,
            publisher=publisher,
            genres=genres,
            tags=tags,
            duration=duration
        )


async def perform_search(query: str, cookies: dict) -> List[BookMetadata]:
    data = {"story": query, "do": "search", "subaction": "search"}
    headers = {
        "Content-Type": "application/x-www-form-urlencoded",
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8",
        "Origin": "https://ranobes.com",
        "Referer": "https://ranobes.com/",
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/136.0.0.0 Safari/537.36"
    }

    async with httpx.AsyncClient() as client:
        response = await client.post(
            "https://ranobes.com/index.php",
            data=data,
            cookies=cookies,
            headers=headers
        )
        if response.status_code != 200:
            raise HTTPException(status_code=500, detail="Failed to search ranobes.com")

        soup = BeautifulSoup(response.text, "html.parser")
        articles = soup.select("#dle-content article.block.story.shortstory.mod-poster")
        links = [a.select_one("h2.title a")["href"] for a in articles if a.select_one("h2.title a")]

        results = []
        for link in links:
            try:
                book = await fetch_and_parse_book(link, cookies)
                results.append(book)
            except Exception:
                continue
        return results


# --- ENDPOINTS ---
@app.get(
    "/search",
    response_model=dict,
    responses={
        400: {"model": ErrorResponse},
        401: {"model": ErrorResponse},
        500: {"model": ErrorResponse},
    }
)
async def search(query: str = Query(...)):
    cookies = get_auth_cookies()
    books = await perform_search(query, cookies)
    return {"matches": books}
