# Ranobes Metadata Provider for Audiobookshelf

This is a custom metadata provider for [Audiobookshelf](https://www.audiobookshelf.org/), using data scraped from [ranobes.com](https://ranobes.com).

It fetches metadata for books via an authenticated search request, and parses the book details using BeautifulSoup.

## Requirements

- Python 3.9+
- Cookies from an authenticated ranobes.com session:
  - `DLE_USER_ID`
  - `DLE_PASSWORD`
  - `PHPSESSID`
