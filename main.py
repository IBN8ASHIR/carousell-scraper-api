import json
import re
import requests
from bs4 import BeautifulSoup
from fastapi import FastAPI, Query

app = FastAPI(title="Carousell Scraper API")

SCRAPER_API_KEY = "4a963c8235341564a382bd078440fbad"  # <-- Paste your key here

@app.get("/")
def home():
    return {"status": "online", "message": "Carousell Scraper API is running with Proxy!"}

@app.get("/scrape")
def scrape_carousell(query: str = Query(..., description="The search query for Carousell")):
    encoded_query = requests.utils.quote(query)
    carousell_url = f"https://www.carousell.com.my/search/{encoded_query}"
    
    try:
        # Route the request through ScraperAPI
        proxy_url = f"http://api.scraperapi.com?api_key={SCRAPER_API_KEY}&url={carousell_url}"
        
        response = requests.get(proxy_url, timeout=30)
        
        if response.status_code != 200:
            return {"error": f"Failed with status code {response.status_code}", "listings": []}

        soup = BeautifulSoup(response.text, 'html.parser')
        listings = []
        seen_ids = set()

        # METHOD A: Standard HTML cards
        cards = soup.find_all('a', href=True)
        for card in cards:
            href = card['href']
            if '/p/' in href:
                clean_path = href.split('?')[0]
                full_url = f"https://www.carousell.com.my{clean_path}" if clean_path.startswith('/') else clean_path
                
                item_id_match = re.search(r'-(\d+)/?$', clean_path)
                item_id = item_id_match.group(1) if item_id_match else clean_path
                
                if item_id in seen_ids:
                    continue
                seen_ids.add(item_id)

                text_chunks = [t.strip() for t in card.stripped_strings if t.strip()]
                price = next((chunk for chunk in text_chunks if re.match(r'^RM\s?[\d,]+$', chunk)), "N/A")
                title = text_chunks[0] if text_chunks else "Unknown Title"
                
                listings.append({
                    "id": item_id,
                    "title": title,
                    "price": price,
                    "url": full_url,
                    "full_text": " | ".join(text_chunks)
                })

        # METHOD B: Fallback to Next.js JSON
        if not listings:
            next_data = soup.find('script', id='__NEXT_DATA__')
            if next_data:
                data = json.loads(next_data.string)
                def find_cards(obj):
                    found = []
                    if isinstance(obj, dict):
                        if 'listingCard' in obj and isinstance(obj['listingCard'], dict):
                            found.append(obj['listingCard'])
                        for k, v in obj.items():
                            found.extend(find_cards(v))
                    elif isinstance(obj, list):
                        for item in obj:
                            found.extend(find_cards(item))
                    return found
                
                for raw in find_cards(data):
                    item_id = str(raw.get('id', ''))
                    if item_id and item_id not in seen_ids:
                        seen_ids.add(item_id)
                        price = str(raw.get('price', 'N/A'))
                        if not price.startswith('RM'):
                            price = f"RM {price}"
                        listings.append({
                            "id": item_id,
                            "title": raw.get('title', 'Unknown Title'),
                            "price": price,
                            "url": f"https://www.carousell.com.my/p/{item_id}",
                            "full_text": raw.get('title', '')
                        })

        return {
            "search_query": query,
            "total_items": len(listings),
            "listings": listings
        }

    except Exception as e:
        return {"error": str(e), "listings": []}