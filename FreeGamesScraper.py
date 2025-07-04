import requests
from bs4 import BeautifulSoup
import json
import time
from datetime import datetime, timedelta
import logging
from typing import List, Dict, Optional
import re
import csv
from urllib.parse import urljoin, urlparse
from concurrent.futures import ThreadPoolExecutor, as_completed

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

class FreeGamesScraper:
    def __init__(self):
        self.session = requests.Session()
        self.session.headers.update({
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'
        })
        self.free_games = []
        self.timeout = 15
        
    def scrape_epic_games(self) -> List[Dict]:
        """Scrape Epic Games Store for free games"""
        logger.info("Scraping Epic Games Store...")
        games = []
        
        try:
            url = "https://store-site-backend-static-ipv4.ak.epicgames.com/freeGamesPromotions"
            params = {
                'locale': 'en-US',
                'country': 'US',
                'allowCountries': 'US'
            }



            
            
            response = self.session.get(url, params=params, timeout=self.timeout)
            response.raise_for_status()
            
            data = response.json()
            
            if 'data' in data and 'Catalog' in data['data']:
                search_store = data['data']['Catalog']['searchStore']
                
                for game in search_store['elements']:
                    promotions = game.get('promotions')
                    if promotions:
                        # Current free games
                        if promotions.get('promotionalOffers'):
                            for offer in promotions['promotionalOffers']:
                                if offer.get('promotionalOffers'):
                                    original_price = self._get_epic_original_price(game)
                                    if original_price != "Free":  # Only games that were originally paid
                                        game_info = {
                                            'title': game.get('title', 'Unknown'),
                                            'platform': 'Epic Games Store',
                                            'original_price': original_price,
                                            'current_price': 'Free',
                                            'url': self._get_epic_url(game),
                                            'end_date': offer['promotionalOffers'][0].get('endDate'),
                                            'description': game.get('description', ''),
                                            'image_url': self._get_epic_image_url(game),
                                            'type': 'Current Free Game'
                                        }
                                        games.append(game_info)
                        
                        # Note: Removed upcoming free games section - only showing currently available games
                                
        except Exception as e:
            logger.error(f"Error scraping Epic Games: {e}")
            
        logger.info(f"Found {len(games)} free games on Epic Games Store")
        return games
    
    def scrape_steam_weekend_deals(self) -> List[Dict]:
        """Scrape Steam for weekend deals and temporary free games"""
        logger.info("Scraping Steam for weekend deals...")
        games = []
        
        try:
            # Steam specials API
            url = "https://store.steampowered.com/api/featuredcategories"
            response = self.session.get(url, timeout=self.timeout)
            response.raise_for_status()
            
            data = response.json()
            
            # Check specials for 100% off games
            if 'specials' in data and 'items' in data['specials']:
                for item in data['specials']['items']:
                    if (item.get('final_price') == 0 and 
                        item.get('original_price', 0) > 0 and 
                        item.get('discount_percent') == 100):
                        
                        game_info = {
                            'title': item.get('name', 'Unknown'),
                            'platform': 'Steam',
                            'original_price': f"${item.get('original_price', 0) / 100:.2f}",
                            'current_price': 'Free',
                            'url': f"https://store.steampowered.com/app/{item.get('id', '')}",
                            'discount_percent': item.get('discount_percent', 0),
                            'image_url': item.get('large_capsule_image', ''),
                            'description': 'Steam temporary free promotion',
                            'type': 'Steam Weekend Deal'
                        }
                        games.append(game_info)
                        
        except Exception as e:
            logger.error(f"Error scraping Steam: {e}")
            
        logger.info(f"Found {len(games)} free games on Steam")
        return games
    
    def scrape_gog_giveaways(self) -> List[Dict]:
        """Scrape GOG.com for giveaways"""
        logger.info("Scraping GOG for giveaways...")
        games = []
        
        try:
            # GOG giveaways page
            url = "https://www.gog.com/giveaway"
            response = self.session.get(url, timeout=self.timeout)
            response.raise_for_status()
            
            soup = BeautifulSoup(response.content, 'html.parser')
            
            # Look for giveaway banners or announcements
            giveaway_elements = soup.find_all(['div', 'section'], class_=re.compile(r'giveaway|promo|banner'))
            
            for element in giveaway_elements:
                title_elem = element.find(['h1', 'h2', 'h3', 'span'], class_=re.compile(r'title|name|game'))
                if title_elem:
                    title = title_elem.get_text(strip=True)
                    if title and len(title) > 3:  # Basic validation
                        game_info = {
                            'title': title,
                            'platform': 'GOG',
                            'current_price': 'Free',
                            'url': url,
                            'description': 'GOG Giveaway',
                            'type': 'GOG Giveaway'
                        }
                        games.append(game_info)
                        
        except Exception as e:
            logger.error(f"Error scraping GOG: {e}")
            
        logger.info(f"Found {len(games)} free games on GOG")
        return games
    
    def scrape_itchio_sales(self) -> List[Dict]:
        """Scrape itch.io for free games and pay-what-you-want games"""
        logger.info("Scraping itch.io for free games...")
        games = []
        
        try:
            # itch.io free games
            url = "https://itch.io/games/free"
            response = self.session.get(url, timeout=self.timeout)
            response.raise_for_status()
            
            soup = BeautifulSoup(response.content, 'html.parser')
            
            # Find game cards
            game_cards = soup.find_all('div', class_='game_cell')
            
            for card in game_cards[:10]:  # Limit to first 10 to avoid too much data
                title_elem = card.find('a', class_='title')
                if title_elem:
                    title = title_elem.get_text(strip=True)
                    url_path = title_elem.get('href', '')
                    
                    # Check if it's actually free or pay-what-you-want
                    price_elem = card.find(['span', 'div'], class_=re.compile(r'price'))
                    if price_elem and ('free' in price_elem.get_text().lower() or 
                                      'pay what you want' in price_elem.get_text().lower()):
                        
                        game_info = {
                            'title': title,
                            'platform': 'itch.io',
                            'current_price': 'Free/PWYW',
                            'url': urljoin('https://itch.io', url_path),
                            'description': 'itch.io free/pay-what-you-want game',
                            'type': 'itch.io Free Game'
                        }
                        games.append(game_info)
                        
        except Exception as e:
            logger.error(f"Error scraping itch.io: {e}")
            
        logger.info(f"Found {len(games)} free games on itch.io")
        return games
    
    def scrape_ubisoft_connect(self) -> List[Dict]:
        """Scrape Ubisoft Connect for free games"""
        logger.info("Scraping Ubisoft Connect for free games...")
        games = []
        
        try:
            # Ubisoft free games page
            url = "https://store.ubisoft.com/us/game"
            params = {'prefn1': 'productType', 'prefv1': 'Game'}
            
            response = self.session.get(url, params=params, timeout=self.timeout)
            response.raise_for_status()
            
            soup = BeautifulSoup(response.content, 'html.parser')
            
            # Look for free game promotions
            game_cards = soup.find_all(['div', 'article'], class_=re.compile(r'product|game|card'))
            
            for card in game_cards[:10]:  # Limit results
                title_elem = card.find(['h1', 'h2', 'h3', 'a'], class_=re.compile(r'title|name'))
                price_elem = card.find(['span', 'div'], class_=re.compile(r'price|cost'))
                
                if title_elem and price_elem:
                    title = title_elem.get_text(strip=True)
                    price_text = price_elem.get_text(strip=True).lower()
                    
                    if 'free' in price_text and len(title) > 3:
                        game_info = {
                            'title': title,
                            'platform': 'Ubisoft Connect',
                            'current_price': 'Free',
                            'url': url,
                            'description': 'Ubisoft free game promotion',
                            'type': 'Ubisoft Free Game'
                        }
                        games.append(game_info)
                        
        except Exception as e:
            logger.error(f"Error scraping Ubisoft Connect: {e}")
            
        logger.info(f"Found {len(games)} free games on Ubisoft Connect")
        return games
    
    def scrape_microsoft_store(self) -> List[Dict]:
        """Scrape Microsoft Store for free games"""
        logger.info("Scraping Microsoft Store for free games...")
        games = []
        
        try:
            # Microsoft Store free games
            url = "https://www.microsoft.com/en-us/store/games/xbox"
            response = self.session.get(url, timeout=self.timeout)
            response.raise_for_status()
            
            soup = BeautifulSoup(response.content, 'html.parser')
            
            # This would need to be updated based on current Microsoft Store structure
            # For now, we'll use a placeholder approach
            
        except Exception as e:
            logger.error(f"Error scraping Microsoft Store: {e}")
            
        logger.info(f"Found {len(games)} free games on Microsoft Store")
        return games
    
    def scrape_amazon_prime_gaming(self) -> List[Dict]:
        """Scrape Amazon Prime Gaming for free games"""
        logger.info("Scraping Amazon Prime Gaming for free games...")
        games = []
        
        try:
            # Amazon Prime Gaming page
            url = "https://gaming.amazon.com/loot"
            
            response = self.session.get(url, timeout=self.timeout)
            response.raise_for_status()
            
            soup = BeautifulSoup(response.content, 'html.parser')
            
            # Look for game offers
            game_elements = soup.find_all(['div', 'section'], class_=re.compile(r'offer|game|loot'))
            
            for element in game_elements[:10]:  # Limit results
                title_elem = element.find(['h1', 'h2', 'h3', 'span'], class_=re.compile(r'title|name'))
                if title_elem:
                    title = title_elem.get_text(strip=True)
                    if title and len(title) > 3:
                        game_info = {
                            'title': title,
                            'platform': 'Amazon Prime Gaming',
                            'current_price': 'Free (Prime Required)',
                            'url': url,
                            'description': 'Amazon Prime Gaming free game',
                            'type': 'Prime Gaming Offer'
                        }
                        games.append(game_info)
                        
        except Exception as e:
            logger.error(f"Error scraping Amazon Prime Gaming: {e}")
            
        logger.info(f"Found {len(games)} free games on Amazon Prime Gaming")
        return games
    
    def _get_epic_original_price(self, game_data: Dict) -> str:
        """Extract original price from Epic Games data"""
        try:
            if 'price' in game_data and game_data['price'].get('totalPrice'):
                price = game_data['price']['totalPrice'].get('originalPrice', 0)
                return f"${price / 100:.2f}" if price > 0 else "Free"
            return "Unknown"
        except:
            return "Unknown"
    
    def _get_epic_image_url(self, game_data: Dict) -> str:
        """Extract image URL from Epic Games data"""
        try:
            if 'keyImages' in game_data:
                for image in game_data['keyImages']:
                    if image.get('type') == 'OfferImageWide':
                        return image.get('url', '')
            return ''
        except:
            return ''
    
    def _get_epic_url(self, game_data: Dict) -> str:
        """Generate Epic Games Store URL"""
        try:
            slug = game_data.get('catalogNs', {}).get('mappings', [{}])[0].get('pageSlug', '')
            if slug:
                return f"https://store.epicgames.com/en-US/p/{slug}"
            return "https://store.epicgames.com"
        except:
            return "https://store.epicgames.com"
    
    def scrape_all_platforms_threaded(self) -> List[Dict]:
        """Scrape all platforms using threading for better performance"""
        logger.info("Starting comprehensive threaded scraping...")
        
        all_games = []
        
        # Define scraping functions
        scrapers = [
            self.scrape_epic_games,
            self.scrape_steam_weekend_deals,
            self.scrape_gog_giveaways,
            self.scrape_itchio_sales,
            self.scrape_ubisoft_connect,
            self.scrape_amazon_prime_gaming,
            self.scrape_microsoft_store
        ]
        
        # Use ThreadPoolExecutor for concurrent scraping
        with ThreadPoolExecutor(max_workers=3) as executor:
            future_to_scraper = {executor.submit(scraper): scraper.__name__ for scraper in scrapers}
            
            for future in as_completed(future_to_scraper):
                scraper_name = future_to_scraper[future]
                try:
                    games = future.result()
                    all_games.extend(games)
                    logger.info(f"Completed {scraper_name}")
                except Exception as e:
                    logger.error(f"Error in {scraper_name}: {e}")
        
        # Remove duplicates
        unique_games = self._remove_duplicates(all_games)
        
        logger.info(f"Total unique free games found: {len(unique_games)}")
        self.free_games = unique_games
        return unique_games
    
    def _remove_duplicates(self, games: List[Dict]) -> List[Dict]:
        """Remove duplicate games based on title similarity"""
        unique_games = []
        seen_titles = set()
        
        for game in games:
            title_lower = game['title'].lower().strip()
            # Simple deduplication - could be improved with fuzzy matching
            title_words = set(re.findall(r'\b\w+\b', title_lower))
            
            is_duplicate = False
            for seen_title in seen_titles:
                seen_words = set(re.findall(r'\b\w+\b', seen_title))
                # If 80% of words match, consider it a duplicate
                if len(title_words & seen_words) / max(len(title_words), len(seen_words)) > 0.8:
                    is_duplicate = True
                    break
            
            if not is_duplicate:
                seen_titles.add(title_lower)
                unique_games.append(game)
        
        return unique_games
    
    def save_to_csv(self, filename: str = "free_games.csv"):
        """Save scraped games to CSV file"""
        try:
            if not self.free_games:
                logger.warning("No games to save")
                return
            
            fieldnames = ['title', 'platform', 'original_price', 'current_price', 'url', 
                         'end_date', 'description', 'type', 'scraped_at']
            
            with open(filename, 'w', newline='', encoding='utf-8') as csvfile:
                writer = csv.DictWriter(csvfile, fieldnames=fieldnames)
                writer.writeheader()
                
                for game in self.free_games:
                    row = {field: game.get(field, '') for field in fieldnames}
                    row['scraped_at'] = datetime.now().isoformat()
                    writer.writerow(row)
            
            logger.info(f"Saved {len(self.free_games)} games to {filename}")
            
        except Exception as e:
            logger.error(f"Error saving to CSV: {e}")
    
    def save_to_json(self, filename: str = "free_games.json"):
        """Save scraped games to JSON file"""
        try:
            with open(filename, 'w', encoding='utf-8') as f:
                json.dump({
                    'scraped_at': datetime.now().isoformat(),
                    'total_games': len(self.free_games),
                    'platforms': list(set(game.get('platform', 'Unknown') for game in self.free_games)),
                    'games': self.free_games
                }, f, indent=2, ensure_ascii=False)
            logger.info(f"Saved {len(self.free_games)} games to {filename}")
        except Exception as e:
            logger.error(f"Error saving to JSON: {e}")
    
    def print_summary(self):
        """Print a summary of found games"""
        if not self.free_games:
            print("No free games found.")
            return
        
        # Group by platform
        platforms = {}
        for game in self.free_games:
            platform = game.get('platform', 'Unknown')
            if platform not in platforms:
                platforms[platform] = []
            platforms[platform].append(game)
        
        print(f"\n🎮 Free Games Summary - {len(self.free_games)} Total Games 🎮")
        print("=" * 60)
        
        for platform, games in platforms.items():
            print(f"\n📱 {platform}: {len(games)} games")
            for game in games[:5]:  # Show first 5 games per platform
                print(f"   • {game['title']}")
                if 'original_price' in game and game['original_price']:
                    print(f"     Original: {game['original_price']} → Free")
                if 'end_date' in game and game['end_date']:
                    print(f"     Ends: {game['end_date']}")
            
            if len(games) > 5:
                print(f"   ... and {len(games) - 5} more")
    
    def get_current_free_games(self) -> List[Dict]:
        """Get only currently free games (not upcoming)"""
        # All games in the list are already current since we removed upcoming games
        return self.free_games

def main():
    scraper = FreeGamesScraper()
    
    try:
        print("🚀 Starting Free Games Scraper...")
        print("This will search multiple platforms for CURRENTLY FREE games only.")
        print("Please wait while we scrape the data...\n")
        
        # Scrape all platforms
        games = scraper.scrape_all_platforms_threaded()
        
        # Print summary
        scraper.print_summary()
        
        # Save results
        scraper.save_to_json()
        scraper.save_to_csv()
        
        print(f"\n✅ Scraping completed!")
        print(f"📊 Found {len(games)} free games across all platforms")
        print(f"📄 Results saved to 'free_games.json' and 'free_games.csv'")
        
        # Show summary of currently free games
        if games:
            print(f"\n🎯 All {len(games)} games listed are currently free to claim!")
        else:
            print(f"\n❌ No currently free games found at this time.")
        
    except KeyboardInterrupt:
        print("\n❌ Scraping interrupted by user.")
    except Exception as e:
        logger.error(f"Unexpected error: {e}")
        print(f"\n❌ An error occurred: {e}")

if __name__ == "__main__":
    main()
