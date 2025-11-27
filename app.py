import httpx
from bs4 import BeautifulSoup
from urllib.parse import urljoin, urlparse
import cv2
import os
import tempfile
import time
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import TimeoutException, WebDriverException

def get_page_content_selenium(url):
        # Setup Chrome options
        chrome_options = Options()
        chrome_options.add_argument('--headless')  # Run in background
        chrome_options.add_argument('--no-sandbox')
        chrome_options.add_argument('--disable-dev-shm-usage')
        chrome_options.add_argument('--disable-blink-features=AutomationControlled')
        chrome_options.add_argument('--user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36')
        
        driver = webdriver.Chrome(options=chrome_options)
        
        try:
            driver.get(url)
            
            # Wait for page to load (wait for body tag)
            WebDriverWait(driver, 10).until(
                EC.presence_of_element_located((By.TAG_NAME, "body"))
            )
            
            # Try to close common popups/modals
            try:
                popup_selectors = [
                    "button[aria-label*='close' i]",
                    "button[aria-label*='Close' i]",
                    ".modal-close",
                    ".popup-close",
                    "#close",
                    ".close-button",
                    "[class*='close'][class*='button']"
                ]
                
                for selector in popup_selectors:
                    try:
                        close_btn = driver.find_element(By.CSS_SELECTOR, selector)
                        if close_btn.is_displayed():
                            close_btn.click()
                            time.sleep(0.5)  # Wait for popup to close
                            break
                    except:
                        continue
            except:
                pass  # If popup handling fails, continue anyway
            
            # Give page a moment to fully render (especially for lazy-loaded images)
            time.sleep(2)
            
            return driver.page_source
        except TimeoutException:
            print(f"Timeout waiting for page to load: {url}")
            return None
        except WebDriverException as exc:
            print(f"Selenium error for {url}: {exc}")
            return None
        finally:
            driver.quit()
               
def download_image(url):
    try:
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36',
            'Accept': 'image/webp,image/apng,image/*,*/*;q=0.8',
            'Accept-Language': 'en-US,en;q=0.9',
            'Referer': urlparse(url).scheme + '://' + urlparse(url).netloc
        }
        response = httpx.get(url, headers=headers, timeout=10.0, follow_redirects=True)
        response.raise_for_status()
        return response.content
    except (httpx.RequestError, httpx.HTTPStatusError, httpx.TimeoutException):
        # Silently skip failed downloads - don't print errors for each image
        return None
    except Exception:
        return None

def bypass_popup(url):
    """
    Bypass popup on the page.
    """
    pass

def check_size(img_url):
    temp_file = None
    try:
        # Download image
        image_content = download_image(img_url)
        if not image_content:
            return False
        
        # Create a temporary file
        with tempfile.NamedTemporaryFile(delete=False, suffix='.jpg') as tmp_file:
            temp_file = tmp_file.name
            tmp_file.write(image_content)
        
        # Read image using OpenCV
        img = cv2.imread(temp_file)
        if img is None:
            # Try reading as different format or check if it's a valid image
            return False
        
        # Get image dimensions (height, width, channels)
        height, width = img.shape[:2]
        
        # Check if both dimensions are greater than 150
        if width > 150 and height > 150:
            return True
        else:
            return False
            
    except Exception:
        # Silently handle errors - skip this image
        return False
    finally:
        # Clean up temporary file
        if temp_file and os.path.exists(temp_file):
            try:
                os.remove(temp_file)
            except Exception:
                pass

def is_ad_div(div):
       
    # Common ad-related keywords in attributes
    ad_keywords = ['ad', 'banner', 'sponsor', 'advertisement', 'promo', 'promotion', 
                   'adsbygoogle', 'doubleclick', 'adserver', 'advert']
    
    # Get class attribute and convert to list of strings
    div_class = div.get('class', [])
    if div_class:
        # Convert BeautifulSoup's AttributeValueList to regular list of strings
        div_class = [str(cls) for cls in div_class] if isinstance(div_class, list) else [str(div_class)]
    else:
        div_class = []
    
    # Check class and id attributes
    div_attrs = ' '.join([
        ' '.join(div_class),
        str(div.get('id', ''))
    ]).lower()
    
    # Check if any ad keyword is present
    if any(keyword in div_attrs for keyword in ad_keywords):
        return True
    
    return False

def get_page_content(url):

    try:
        # Use a longer timeout and set headers to mimic a browser
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'
        }
        response = httpx.get(url, headers=headers, timeout=30.0, follow_redirects=True)
        response.raise_for_status()
        return response.text
    except httpx.RequestError as e:
        print(f"Request error for {url}: {e}")
        return None
    except httpx.HTTPStatusError as e:
        try:
            return get_page_content_selenium(url)
        except Exception as e:
            print(f"Error with Selenium: {e}")
            return None

def check_header_image(url, soup, max_images_to_check=10):
   
    # Common header/nav selectors
    header_selectors = [
        'header',
        'nav',
        {'class': 'header'},
        {'id': 'header'},
        {'class': 'navbar'},
        {'id': 'navbar'},
        {'class': 'nav'},
        {'id': 'nav'},
        {'class': 'site-header'},
        {'id': 'site-header'},
        {'class': 'main-header'},
        {'id': 'main-header'}
    ]
    
    # Collect header/nav elements, preserving order and avoiding duplicates
    header_elements = []
    seen_ids = set()
    for selector in header_selectors:
        if isinstance(selector, str):
            found_elements = soup.find_all(selector)
        else:
            found_elements = soup.find_all(attrs=selector)
        
        for element in found_elements:
            element_id = id(element)
            if element_id not in seen_ids:
                seen_ids.add(element_id)
                header_elements.append(element)
    
    if not header_elements:
        return None
    
    images_checked = 0
    
    for header_element in header_elements:
        img_tags = header_element.find_all('img')
        for img_tag in img_tags:
            if images_checked >= max_images_to_check:
                return None
            
            img_src = img_tag.get('src') or img_tag.get('data-src') or img_tag.get('data-lazy-src')
            if not img_src:
                continue
            
            img_url = urljoin(url, img_src)
            
            if img_url.startswith('data:'):
                continue
            
            images_checked += 1
            
            if check_size(img_url):
                return img_url
    
    return None

def check_container_images(url, soup, container_tag, max_images_to_check=20):
    containers = soup.find_all(container_tag, recursive=True)
    images_checked = 0
    
    for container in containers:
        # Check if the container has ad keywords in class or id
        if is_ad_div(container):
            continue
        
        img_tags = container.find_all('img')
        if not img_tags:
            continue
        
        for img_tag in img_tags:
            if images_checked >= max_images_to_check:
                return None
            
            img_src = img_tag.get('src') or img_tag.get('data-src') or img_tag.get('data-lazy-src')
            if not img_src:
                continue
            
            img_url = urljoin(url, img_src)
            
            if img_url.startswith('data:'):
                continue
            
            images_checked += 1
            
            if not check_size(img_url):
                continue
            
            return img_url
    
    return None

def scrape_first_image(url, max_images_to_check=20):
   
    html_content = get_page_content(url)
    if not html_content:
        return None
    
    soup = BeautifulSoup(html_content, 'html.parser')
    
    # Step 1: First check header/nav for images
    header_image = check_header_image(url, soup, max_images_to_check)
    if header_image:
        return header_image
    
    # Step 2: Check figure tags for images (often used for main content images)
    figure_image = check_container_images(url, soup, 'figure', max_images_to_check)
    if figure_image:
        return figure_image
    
    # Step 3: Check divs for images
    div_image = check_container_images(url, soup, 'div', max_images_to_check)
    if div_image:
        return div_image
    
    return None

def scrape_images_from_links(links):
   
    results = []
    
    for idx, url in enumerate(links, start=1):
        print(f"Processing [{idx}/{len(links)}]: {url}")
        image_url = scrape_first_image(url)
        
        result_item = {
            "id": idx,
            "url": url,
            "image_path": image_url if image_url else "No image found"
        }
        
        results.append(result_item)
        
        if image_url:
            print(f"  ✓ Found image: {image_url}\n")
        else:
            print(f"  ✗ No image found\n")
    
    return results


if __name__ == "__main__":
    # Scrape images from all URLs in links.md
    
    links = [
        "https://www.businessinsider.com/ai-consulting-startups-2025-10",
        "https://rtslabs.com/ai-conulting-company-in-usa/",
        "https://www.code-brew.com/top-10-ai-consulting-companies-in-usa/",
        "https://www.secondtalent.com/resources/ai-startup-funding-investment/",
        "https://creyos.com/blog/telemedicine-key-updates",
        "https://www.ejbi.org/scholarly-articles/the-impact-of-telemedicine-and-digital-health-on-healthcare-delivery-systems-13114.html",
        "https://www.sermo.com/resources/future-of-telemedicine/",
        "https://www.ruralhealth.us/blogs/2025/02/5-telemedicine-trends-for-hospital-leaders-in-2025"
    ]
    
    results = scrape_images_from_links(links)
    
    if results: 
        # Save results to JSON
        import json
        with open('result.json', 'w', encoding='utf-8') as f:
            json.dump(results, f, indent=2, ensure_ascii=False)
        
        print(f"\nResults saved to result.json")
        print(f"Total URLs processed: {len(results)}")
        print(f"Images found: {sum(1 for item in results if item['image_path'])}")