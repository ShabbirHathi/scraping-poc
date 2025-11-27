import httpx
from bs4 import BeautifulSoup
from urllib.parse import urljoin, urlparse
import cv2
import os
import tempfile
import time
import base64
import re
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
                            time.sleep(5)  # Wait for popup to close
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

def verify_image(img_url, img_tag):
    img_url_lower = img_url.lower()
    
    # Check if extension is SVG - skip immediately
    if img_url_lower.endswith('.svg') or '.svg' in img_url_lower.split('?')[0]:
        print(f"    ✗ Skipping SVG image")
        return False
    
    # Check if URL contains "150x150" pattern (common thumbnail naming)
    if '150x150' in img_url:
        print(f"    ✗ Skipping 150x150 thumbnail (detected in URL)")
        return False
    
    # Check if URL contains dimension patterns like "300x200" and extract them
    # Look for patterns like "300x200", "150x150", etc. in the URL
    dimension_pattern = r'(\d+)x(\d+)'
    url_dimensions = re.findall(dimension_pattern, img_url)
    if url_dimensions:
        for dim_match in url_dimensions:
            try:
                w = int(dim_match[0])
                h = int(dim_match[1])
                # If dimensions in URL are <= 150x150, skip it
                if w <= 150 and h <= 150:
                    print(f"    ✗ Skipping small image (URL shows {w}x{h})")
                    return False
            except (ValueError, TypeError):
                pass
    
    # Check HTML attributes for width and height
    width = img_tag.get('width')
    height = img_tag.get('height')
    
    if width and height:
        try:
            w = int(width)
            h = int(height)
            
            # If exactly 150x150, skip it
            if w == 150 and h == 150:
                print(f"    ✗ Skipping 150x150 thumbnail: {w}x{h}")
                return False
            
            # If smaller than 150x150, skip it
            if w <= 150 or h <= 150:
                print(f"    ✗ HTML attributes show size: {w}x{h} - Too small")
                return False
            
            # If greater than 150x150, use it
            if w > 150 and h > 150:
                print(f"    ✓ HTML attributes show size: {w}x{h} - Meets requirement")
                return True
        except (ValueError, TypeError):
            pass
    
    # No size info in HTML or URL - need to download and check
    print(f"    ? No size info in URL/HTML - will download to check")
    return None
               
def download_image_selenium(url):
    driver = None
    try:
        # Setup Chrome options
        chrome_options = Options()
        chrome_options.add_argument('--headless')
        chrome_options.add_argument('--no-sandbox')
        chrome_options.add_argument('--disable-dev-shm-usage')
        chrome_options.add_argument('--disable-blink-features=AutomationControlled')
        chrome_options.add_argument('--user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36')
        
        driver = webdriver.Chrome(options=chrome_options)
        
        # Method 1: Try JavaScript fetch API
        try:
            script = """
            return new Promise((resolve, reject) => {
                fetch(arguments[0])
                    .then(response => {
                        if (!response.ok) {
                            reject(new Error('HTTP error: ' + response.status));
                            return;
                        }
                        return response.blob();
                    })
                    .then(blob => {
                        const reader = new FileReader();
                        reader.onloadend = function() {
                            resolve(reader.result);
                        };
                        reader.onerror = function() {
                            reject(new Error('Failed to read blob'));
                        };
                        reader.readAsDataURL(blob);
                    })
                    .catch(error => {
                        reject(error);
                    });
            });
            """
            
            base64_data = driver.execute_async_script(script, url)
            
            if base64_data and base64_data.startswith('data:'):
                base64_part = base64_data.split(',', 1)[1]
                image_bytes = base64.b64decode(base64_part)
                return image_bytes
        except:
            pass  # Fall through to method 2
        
        # Method 2: Navigate to image URL and get cookies, then use httpx
        try:
            # Navigate to the image URL to establish session
            driver.get(url)
            time.sleep(1)
            
            # Get cookies from Selenium session
            cookies = driver.get_cookies()
            
            # Convert Selenium cookies to httpx format
            cookie_dict = {cookie['name']: cookie['value'] for cookie in cookies}
            
            # Use httpx with cookies
            headers = {
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
                'Accept': 'image/webp,image/apng,image/*,*/*;q=0.8',
                'Accept-Language': 'en-US,en;q=0.9',
                'Referer': urlparse(url).scheme + '://' + urlparse(url).netloc
            }
            
            response = httpx.get(url, headers=headers, cookies=cookie_dict, timeout=15.0, follow_redirects=True)
            response.raise_for_status()
            return response.content
        except:
            pass  # Both methods failed
            
        return None
            
    except Exception:
        return None
    finally:
        if driver:
            try:
                driver.quit()
            except:
                pass

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
        # Try Selenium fallback
        print(f"    HTTP download failed, trying Selenium for: {url}")
        selenium_result = download_image_selenium(url)
        if selenium_result:
            print(f"    ✓ Selenium download successful")
            return selenium_result
        return None
    except Exception:
        # Try Selenium fallback
        print(f"    Exception in HTTP download, trying Selenium for: {url}")
        selenium_result = download_image_selenium(url)
        if selenium_result:
            print(f"    ✓ Selenium download successful")
            return selenium_result
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
            print(f"    Failed to download image: {img_url}")
            return False
        
        # Determine file extension from URL or content type
        file_ext = '.jpg'  # default
        if img_url.lower().endswith('.png'):
            file_ext = '.png'
        elif img_url.lower().endswith('.gif'):
            file_ext = '.gif'
        elif img_url.lower().endswith('.webp'):
            file_ext = '.webp'
        
        # Create a temporary file with appropriate extension
        with tempfile.NamedTemporaryFile(delete=False, suffix=file_ext) as tmp_file:
            temp_file = tmp_file.name
            tmp_file.write(image_content)
        
        # Read image using OpenCV
        img = cv2.imread(temp_file)
        if img is None:
            print(f"    OpenCV failed to read image: {img_url}")
            return False
        
        # Get image dimensions (height, width, channels)
        height, width = img.shape[:2]
        print(f"    Image dimensions: {width}x{height}")
        
        # Check if both dimensions are greater than 150
        if width > 150 and height > 150:
            print(f"    ✓ Image meets size requirement")
            return True
        else:
            print(f"    ✗ Image too small: {width}x{height} (need >150x150)")
            return False
            
    except Exception as e:
        # Print error for debugging
        print(f"    Exception in check_size: {type(e).__name__}: {str(e)}")
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
        # Add delay to allow any server-side processing
        time.sleep(10)
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
            
            # Verify image before downloading (skip SVG, 150x150, etc.)
            verify_result = verify_image(img_url, img_tag)
            if verify_result is False:
                continue  # Skip this image
            if verify_result is True:
                return img_url  # Use this image (size > 150x150 from HTML attributes)
            
            # If verify returns None, need to download and check
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
            
            # Verify image before downloading (skip SVG, 150x150, etc.)
            verify_result = verify_image(img_url, img_tag)
            if verify_result is False:
                continue  # Skip this image
            if verify_result is True:
                return img_url  # Use this image (size > 150x150 from HTML attributes)
            
            # If verify returns None, need to download and check
            if not check_size(img_url):
                continue
            
            return img_url
    
    return None

def check_all_images(url, soup, max_images_to_check=30):
    # Get all img tags from the entire page
    all_img_tags = soup.find_all('img', recursive=True)
   
    if not all_img_tags:
        return None
    
    images_checked = 0
    fallback_images = []  # Store images with HTML attributes > 150x150 for fallback
    
    print(f"---------------check_all_images-----------------"*10)
    for img_tag in all_img_tags:
        print(f"--------------------------------"*10)
        print(img_tag)
        if images_checked >= max_images_to_check:
            break
        
        # Get image source
        img_src = img_tag.get('src') or img_tag.get('data-src') or img_tag.get('data-lazy-src')
        if not img_src:
            continue
        
        img_url = urljoin(url, img_src)
        
        # Skip data URLs
        if img_url.startswith('data:'):
            continue
        
        images_checked += 1
        
        print(f"Checking image {images_checked}: {img_url}")
        
        # Check if not SVG and has HTML attributes > 150x150 for fallback
        # (Collect these before verify_image so we have them as fallback)
        if not img_url.lower().endswith('.svg'):
            width = img_tag.get('width')
            height = img_tag.get('height')
            if width and height:
                try:
                    w = int(width)
                    h = int(height)
                    if w > 150 and h > 150:
                        fallback_images.append(img_url)
                        print(f"    Stored as fallback candidate (HTML: {w}x{h})")
                except (ValueError, TypeError):
                    pass
        
        # Verify image based on extension and HTML attributes
        verify_result = verify_image(img_url, img_tag)
        
        # If verify returns False, skip this image
        if verify_result is False:
            continue
        
        # If verify returns True, use this image (size > 150x150 from HTML attributes)
        if verify_result is True:
            print(f"  ✓ Found suitable image from HTML attributes: {img_url}")
            return img_url
        
        # If verify returns None, need to download and check
        
        # Try to download and check size
        size_result = check_size(img_url)
        print(f"  Size check result: {size_result}")
        if size_result:
            print(f"  ✓ Found suitable image: {img_url}")
            return img_url
        else:
            print(f"  ✗ Image failed size check or download")
    
    # If no image found via download, use fallback (first image with HTML attributes > 150x150)
    if fallback_images:
        print(f"  Using fallback image (HTML attributes > 150x150): {fallback_images[0]}")
        return fallback_images[0]
    
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
    
    # Step 4: Get all image tags and check first suitable image
    all_images_result = check_all_images(url, soup, max_images_to_check)
    if all_images_result:
        return all_images_result
    
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
        print(f"Images found: {results}")