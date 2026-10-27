# 6-71 Parts Desk

An interactive parts desk for the Detroit Diesel 6-71 marine engine, built on
[String](https://usestring.ai)'s web access API.

Click a part on the engine diagram to see:

- **What the manuals say:** the pages that cover it in a library of
  marine-engine and Detroit Diesel service manuals, and its 6-71 part numbers
  from GM Diesel's 1953 Series 71 owners parts book.
- **Live sources via String:** vendor listings found with String search. Each
  listing is fetched through String, which extracts price, stock, condition and
  part number with a JSON schema. A plain HTTP scraper fetches the same page at
  the same time, so you can see which vendor sites block an ordinary scraper.

The manual data comes from a GraphRAG project over OCR'd nautical PDFs. Only the
excerpts, part numbers and figure crops are included here, not the manuals.

## Run locally

```sh
python -m venv venv && venv/bin/pip install -r requirements.txt
echo "STRING_API_KEY=your-key" > .env
venv/bin/python app.py      # http://localhost:5001
```

## Layout

| Path | What it is |
|---|---|
| `app.py` | Flask routes: the page, the parts catalog, sources, listing checks |
| `parts_desk.py` | String search and fetch calls, the plain-scraper comparison |
| `data/catalog.json` | Parts, manual-page excerpts and parts-book numbers |
| `data/parts_sources.json` | Cached String search results, one entry per part |
| `templates/parts.html` | The page |
| `public/static/parts/` | Engine photo and figure crops from the manuals |

Deployed on Vercel; set `STRING_API_KEY` in the project's environment variables.
