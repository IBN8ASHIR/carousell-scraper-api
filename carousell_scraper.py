import csv
import json
import re
from io import StringIO
import requests
from bs4 import BeautifulSoup
from curl_cffi import requests as cffi_requests

# Activepieces Catch Webhook URL
ACTIVEPIECES_WEBHOOK_URL = "https://cloud.activepieces.com/api/v1/webhooks/2cDtsQnKGzf8GrHSFkN7s"

def push_to_activepieces(listings, query_name):
    """Sends extracted listings payload to Activepieces workflow."""
    payload = {
        "search_query": query_name,
        "total_items": len(listings),
        "listings": listings
    }
    
    print("Sending listings to Activepieces...")
    response = requests.post(ACTIVEPIECES_WEBHOOK_URL, json=payload)
    
    if response.status_code in [200, 201, 202]:
        print("🎉 Scraped listings successfully sent to Activepieces!")
    else:
        print(f"Failed to send to Activepieces. Status: {response.status_code}")


# ----------------------------------------------------
# 1. FETCH DYNAMIC SEARCH QUERY FROM GOOGLE SHEETS
# ----------------------------------------------------
# Replace YOUR_SHEET_ID with the ID from your Google Sheet URL
# e.g., https://docs.google.com/spreadsheets/d/1abc12345xyz/edit -> ID is "1abc12345xyz"
SHEET_ID = "1xnj4NgR9ytLTh-iUBa-u7WnH9EXMwXcXmUzYnKGSIeU" 
SHEET_CSV_URL = f"https://docs.google.com/spreadsheets/d/{SHEET_ID}/export?format=csv"

print("Checking Task Queue in Google Sheets...")
search_query = "Canon R50" # Default fallback

try:
    sheet_response = requests.get(SHEET_CSV_URL)
    if sheet_response.status_code == 200:
        reader = csv.DictReader(StringIO(sheet_response.text))
        for row in reader:
            if str(row.get('is_active')).strip().upper() == 'TRUE':
                search_query = row.get('search_query').strip()
                break
        print(f"Active mission found: Hunting for '{search_query}'")
    else:
        print("Could not fetch Google Sheet CSV, using default search query.")
except Exception as e:
    print(f"Error reading Google Sheet: {e}. Using default search query.")

# Build the Carousell URL dynamically
encoded_query = requests.utils.quote(search_query)
carousell_url = f"https://www.carousell.com.my/search/{encoded_query}"

# ----------------------------------------------------
# ----------------------------------------------------
# 2. SCRAPE CAROUSELL WITH CURL_CFFI
# ----------------------------------------------------
print(f"Fetching listings from: {carousell_url}")
response = cffi_requests.get(carousell_url, impersonate="chrome110")

if response.status_code == 200:
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

    # METHOD B: Fallback to Next.js JSON payload if HTML cards were empty (Certified/Mobile tab override)
    if not listings:
        print("HTML cards empty, attempting JSON fallback parsing...")
        next_data_script = soup.find('script', id='__NEXT_DATA__')
        if next_data_script:
            try:
                data = json.loads(next_data_script.string)
                
                # Bulletproof recursive search to find listings anywhere in the JSON blob
                def find_listing_cards(obj):
                    found_cards = []
                    if isinstance(obj, dict):
                        # If we find a listing, grab it!
                        if 'listingCard' in obj and isinstance(obj['listingCard'], dict):
                            found_cards.append(obj['listingCard'])
                        # Keep digging through dictionaries
                        for key, value in obj.items():
                            found_cards.extend(find_listing_cards(value))
                    elif isinstance(obj, list):
                        # Keep digging through lists
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
            except Exception as e:
                print(f"JSON parsing fallback error: {e}")