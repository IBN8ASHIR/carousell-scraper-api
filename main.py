import json
import re
import requests
from bs4 import BeautifulSoup
from curl_cffi import requests as cffi_requests
from fastapi import FastAPI, Query

app = FastAPI(title="Carousell Scraper API")

@app.get("/")
def home():
    return {"status": "online", "message": "Carousell Scraper API is running!"}

@app.get("/scrape")
def scrape_carousell(query: str = Query(..., description="The search query for Carousell")):
    encoded_query = requests.utils.quote(query)
    carousell_url = f"https://www.carousell.com.my/search/{encoded_query}"
    
    try:
        response = cffi_requests.get(carousell_url, impersonate="chrome110", timeout=15)
        if response.status_code != 200:
            return {"error": f"Failed with status code {response.status_code}", "listings": []}

        soup = BeautifulSoup(response.text, 'html.parser')
        listings = []
        seen_ids = set()

        # METHOD A: Extract from standard HTML cards
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

        # METHOD B: Fallback to Next.js JSON payload
        if not listings:
            next_data_script = soup.find('script', id='__NEXT_DATA__')
            if next_data_script:
                data = json.loads(next_data_script.string)
                
                def find_listing_cards(obj):
                    found_cards = []
                    if isinstance(obj, dict):
                        if 'listingCard' in obj and isinstance(obj['listingCard'], dict):
                            found_cards.append(obj['listingCard'])
                        for key, value in obj.items():
                            found_cards.extend(find_listing_cards(value))
                    elif isinstance(obj, list):
                        for item in obj:
                            found_cards.extend(find_listing_cards(item))
                    return found_cards
                
                raw_cards = find_listing_cards(data)
                for listing_data in raw_cards:
                    item_id = str(listing_data.get('id', ''))
                    if item_id and item_id not in seen_ids:
                        seen_ids.add(item_id)
                        price = str(listing_data.get('price', 'N/A'))
                        if not price.startswith('RM'):
                            price = f"RM {price}"
                            
                        listings.append({
                            "id": item_id,
                            "title": listing_data.get('title', 'Unknown Title'),
                            "price": price,
                            "url": f"https://www.carousell.com.my/p/{item_id}",
                            "full_text": listing_data.get('title', '')
                        })

        return {
            "search_query": query,
            "total_items": len(listings),
            "listings": listings
        }

    except Exception as e:
        return {"error": str(e), "listings": []}