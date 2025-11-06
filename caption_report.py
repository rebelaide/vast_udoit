from __future__ import print_function
import re
import requests
import concurrent.futures
from bs4 import BeautifulSoup
from google.colab import userdata
import gspread
from gspread_dataframe import set_with_dataframe
import pandas as pd
import math
from urllib.parse import urljoin, urlparse
import PyPDF2
import io
from PIL import Image
import base64

# --------------------------------------------------------------
# 1️⃣ CONSTANTS – your secrets (keep notebook private)
# --------------------------------------------------------------
CANVAS_API_URL   = userdata.get('CANVAS_API_URL')
CANVAS_API_KEY   = userdata.get('CANVAS_API_KEY')
YOUTUBE_API_KEY  = userdata.get('YOUTUBE_API_KEY')

YT_CAPTION_URL = "https://www.googleapis.com/youtube/v3/captions"
YT_VIDEO_URL   = "https://www.googleapis.com/youtube/v3/videos"

YT_PATTERN = (
    r'(?:https?://)?(?:[0-9A-Z-]+.)?(?:youtube|youtu|youtube-nocookie).'
    r'(?:com|be)/(?:watch\?v=|watch\?.+&v=|embed/|v/|.+\?v=)?([^&=\n%\?]{11})'
)

LIB_MEDIA_URLS = [
    "fod.infobase.com",
    "search.alexanderstreet.com",
    "kanopystreaming-com",
    "hosted.panopto.com"
]

# ----------------------------------------------------------------------
# CanvasAPI
# ----------------------------------------------------------------------
try:
    from canvasapi import Canvas
except ImportError as exc:
    raise ImportError("Please install canvasapi via `!pip install canvasapi`") from exc

# ----------------------------------------------------------------------
# Helper Functions
# ----------------------------------------------------------------------
def _auth_header(token: str) -> dict:
    return {"Authorization": f"Bearer {token.strip()}"}

def _add_entry(d, name, status, page, hour="", minute="", second="", file_location=""):
    d[name] = [status, hour, minute, second, page, file_location]

def _check_media_object(url: str):
    try:
        txt = requests.get(url, headers=_auth_header(CANVAS_API_KEY)).text
        if '"kind":"subtitles"' in txt:
            return (url, "Captions in English" if '"locale":"en"' in txt else "No English Captions")
        return (url, "No Captions")
    except requests.RequestException:
        return (url, "Unable to Check Media Object")

def _process_html(soup, course, page, yt_links, media_links, link_media, lib_media):
    media_objs, iframe_objs = [], []

    for a in soup.find_all("a"):
        href = a.get("href")
        if not href:
            continue
        try:
            file_id = a.get("data-api-endpoint").split("/")[-1]
            f = course.get_file(file_id)
            f_url = f.url.split("?")[0]
            if "audio" in f.mime_class:
                _add_entry(link_media, f"Linked Audio File: {f.display_name}",
                           "Manually Check for Captions", page, file_location=f_url)
            if "video" in f.mime_class:
                _add_entry(link_media, f"Linked Video File: {f.display_name}",
                           "Manually Check for Captions", page, file_location=f_url)
        except Exception:
            pass

        if re.search(YT_PATTERN, href):
            yt_links.setdefault(href, []).append(page)
        elif any(u in href for u in LIB_MEDIA_URLS):
            _add_entry(lib_media, href, "Manually Check for Captions", page)
        elif "media_objects" in href:
            media_objs.append(href)

    for frm in soup.find_all("iframe"):
        src = frm.get("src")
        if not src:
            continue
        if re.search(YT_PATTERN, src):
            yt_links.setdefault(src, []).append(page)
        elif any(u in src for u in LIB_MEDIA_URLS):
            _add_entry(lib_media, src, "Manually Check for Captions", page)
        elif "media_objects_iframe" in src:
            iframe_objs.append(src)

    all_media = list(set(media_objs + iframe_objs))
    if all_media:
        with concurrent.futures.ThreadPoolExecutor(max_workers=10) as ex:
            for url, msg in ex.map(_check_media_object, all_media):
                _add_entry(media_links, url, msg, page)

    for vid in soup.find_all("video"):
        if vid.get("data-media_comment_id"):
            name = f"Video Media Comment {vid['data-media_comment_id']}"
            status = "Captions" if vid.find("track") else "No Captions"
            _add_entry(media_links, name, status, page)

    for src in soup.find_all("source"):
        if src.get("type") == "video/mp4":
            name = f"Embedded Canvas Video {src['src']}"
            _add_entry(media_links, name, "Manually Check for Captions", page)

    for aud in soup.find_all("audio"):
        if aud.get("data-media_comment_id"):
            name = f"Audio Media Comment {aud['data-media_comment_id']}"
            status = "Captions" if aud.find("track") else "No Captions"
            _add_entry(media_links, name, status, page)
        else:
            name = f"Embedded Canvas Audio {aud.get('src', '')}"
            _add_entry(media_links, name, "Manually Check for Captions", page)

# ----------------------------------------------------------------------
# YouTube Helpers
# ----------------------------------------------------------------------
YT_DUR_RE = re.compile(r"[0-9]+[HMS]")

def _parse_iso8601(duration: str):
    h, m, sec = "0", "0", "0"
    for token in YT_DUR_RE.findall(duration):
        unit = token[-1]
        val = token[:-1]
        if unit == "H":
            h = val
        elif unit == "M":
            m = val
        elif unit == "S":
            sec = val
    return h, m, sec

def _check_youtube(task):
    key, vid, pages, api_key = task
    if not vid:
        return key, "this is a playlist, check individual videos", ("", "", ""), pages
    try:
        r1 = requests.get(f"{YT_VIDEO_URL}?part=contentDetails&id={vid}&key={api_key}")
        dur = r1.json()["items"][0]["contentDetails"]["duration"]
        h, m, s = _parse_iso8601(dur)

        r2 = requests.get(f"{YT_CAPTION_URL}?part=snippet&videoId={vid}&key={api_key}")
        caps = r2.json().get("items", [])
        status = "No Captions"
        if caps:
            langs = {c["snippet"]["language"]: c["snippet"]["trackKind"] for c in caps}
            if "en" in langs or "en-US" in langs:
                kind = langs.get("en") or langs.get("en-US")
                if kind == "standard":
                    status = "Captions found in English"
                elif kind == "asr":
                    status = "Automatic Captions in English"
                else:
                    status = "Captions in English (unknown kind)"
            else:
                status = "No Captions in English"
        return key, status, (h, m, s), pages
    except Exception:
        return key, "Unable to Check Youtube Video", ("", "", ""), pages

# ----------------------------------------------------------------------
# NEW FUNCTIONS: Time handling and totaling
# ----------------------------------------------------------------------
def _consolidate_time(hour_str, minute_str, second_str):
    """
    Convert hour, minute, second strings to consolidated "HH:MM" format.
    Rounds up seconds to the next minute if seconds > 0.
    Returns tuple: (formatted_string, total_minutes_for_summing)
    """
    try:
        hours = int(hour_str) if hour_str and hour_str.strip() else 0
        minutes = int(minute_str) if minute_str and minute_str.strip() else 0
        seconds = int(second_str) if second_str and second_str.strip() else 0
        
        # Calculate total minutes for summing (before rounding up seconds)
        total_minutes = hours * 60 + minutes + (1 if seconds > 0 else 0)
        
        # Round up to next minute if there are any seconds
        if seconds > 0:
            minutes += 1
        
        # Handle minute overflow
        if minutes >= 60:
            hours += minutes // 60
            minutes = minutes % 60
        
        return f"{hours:02d}:{minutes:02d}", total_minutes
    except (ValueError, TypeError):
        return "", 0

def _minutes_to_duration(total_minutes):
    """Convert total minutes back to HH:MM format"""
    if total_minutes <= 0:
        return "00:00"
    
    hours = total_minutes // 60
    minutes = total_minutes % 60
    return f"{hours:02d}:{minutes:02d}"

# ----------------------------------------------------------------------
# ACCESSIBILITY TESTING FUNCTIONS
# ----------------------------------------------------------------------

def _add_accessibility_issue(issues_dict, issue_type, description, location, severity="Error"):
    """Add an accessibility issue to the tracking dictionary"""
    key = f"{issue_type}: {description}"
    if key not in issues_dict:
        issues_dict[key] = []
    issues_dict[key].append({
        'severity': severity,
        'location': location,
        'description': description
    })

def _check_images_accessibility(soup, location, accessibility_issues):
    """Check for image accessibility issues"""
    images = soup.find_all('img')
    
    for img in images:
        src = img.get('src', '')
        alt = img.get('alt')
        
        # Check for missing alt text
        if alt is None:
            _add_accessibility_issue(
                accessibility_issues,
                "Missing Alt Text",
                f"Image missing alt attribute: {src[:50]}...",
                location,
                "Error"
            )
        elif alt.strip() == "":
            _add_accessibility_issue(
                accessibility_issues,
                "Empty Alt Text",
                f"Image has empty alt text: {src[:50]}...",
                location,
                "Suggestion"
            )
        elif len(alt) > 125:
            _add_accessibility_issue(
                accessibility_issues,
                "Long Alt Text",
                f"Alt text exceeds 125 characters ({len(alt)} chars): {alt[:50]}...",
                location,
                "Suggestion"
            )
        
        # Check for images that might be decorative but have alt text
        if alt and any(word in alt.lower() for word in ['image', 'picture', 'photo', 'graphic']):
            _add_accessibility_issue(
                accessibility_issues,
                "Generic Alt Text",
                f"Alt text may be too generic: '{alt}'",
                location,
                "Suggestion"
            )

def _check_links_accessibility(soup, location, accessibility_issues):
    """Check for link accessibility issues"""
    links = soup.find_all('a')
    
    vague_link_text = [
        'click here', 'read more', 'more', 'here', 'link', 'this', 'continue',
        'go', 'next', 'previous', 'back', 'download', 'view', 'see more'
    ]
    
    for link in links:
        href = link.get('href', '')
        link_text = link.get_text(strip=True).lower()
        
        # Check for empty link text
        if not link_text:
            _add_accessibility_issue(
                accessibility_issues,
                "Empty Link Text",
                f"Link has no text content: {href[:50]}...",
                location,
                "Error"
            )
        
        # Check for vague link text
        elif link_text in vague_link_text:
            _add_accessibility_issue(
                accessibility_issues,
                "Vague Link Text",
                f"Link text is not descriptive: '{link_text}' -> {href[:50]}...",
                location,
                "Error"
            )
        
        # Check for URLs as link text
        elif link_text.startswith(('http://', 'https://', 'www.')):
            _add_accessibility_issue(
                accessibility_issues,
                "URL as Link Text",
                f"URL used as link text: {link_text[:50]}...",
                location,
                "Suggestion"
            )
        
        # Check for very long link text
        elif len(link_text) > 100:
            _add_accessibility_issue(
                accessibility_issues,
                "Long Link Text",
                f"Link text is very long ({len(link_text)} chars): {link_text[:50]}...",
                location,
                "Suggestion"
            )

def _check_headings_accessibility(soup, location, accessibility_issues):
    """Check for heading structure issues"""
    headings = soup.find_all(['h1', 'h2', 'h3', 'h4', 'h5', 'h6'])
    
    if not headings:
        return
    
    heading_levels = []
    for heading in headings:
        level = int(heading.name[1])
        heading_levels.append(level)
        
        # Check for empty headings
        heading_text = heading.get_text(strip=True)
        if not heading_text:
            _add_accessibility_issue(
                accessibility_issues,
                "Empty Heading",
                f"Empty {heading.name.upper()} heading found",
                location,
                "Error"
            )
    
    # Check for skipped heading levels
    if heading_levels:
        for i in range(1, len(heading_levels)):
            current_level = heading_levels[i]
            prev_level = heading_levels[i-1]
            
            if current_level > prev_level + 1:
                _add_accessibility_issue(
                    accessibility_issues,
                    "Skipped Heading Level",
                    f"Heading level jumps from H{prev_level} to H{current_level}",
                    location,
                    "Error"
                )

def _check_color_accessibility(soup, location, accessibility_issues):
    """Check for color-related accessibility issues"""
    # Look for elements that might rely on color alone
    elements_with_style = soup.find_all(attrs={'style': True})
    
    for element in elements_with_style:
        style = element.get('style', '').lower()
        
        # Check for color-only emphasis
        if 'color:' in style and element.get_text(strip=True):
            text_content = element.get_text(strip=True)
            # Check if this might be used for emphasis without other indicators
            if not any(tag in str(element).lower() for tag in ['<strong>', '<b>', '<em>', '<i>', '<u>']):
                _add_accessibility_issue(
                    accessibility_issues,
                    "Color Only Emphasis",
                    f"Text may rely on color alone for meaning: '{text_content[:50]}...'",
                    location,
                    "Suggestion"
                )

def _check_tables_accessibility(soup, location, accessibility_issues):
    """Check for table accessibility issues"""
    tables

def _check_tables_accessibility(soup, location, accessibility_issues):
    """Check for table accessibility issues"""
    tables = soup.find_all('table')
    
    for table in tables:
        # Check for missing table headers
        headers = table.find_all(['th'])
        if not headers:
            _add_accessibility_issue(
                accessibility_issues,
                "Missing Table Headers",
                "Table found without proper header cells (th elements)",
                location,
                "Error"
            )
        
        # Check for missing caption
        caption = table.find('caption')
        if not caption:
            _add_accessibility_issue(
                accessibility_issues,
                "Missing Table Caption",
                "Table missing descriptive caption",
                location,
                "Suggestion"
            )
        
        # Check for complex tables without proper scope
        rows = table.find_all('tr')
        if len(rows) > 3:  # Arbitrary threshold for "complex"
            headers_with_scope = table.find_all('th', attrs={'scope': True})
            if headers and not headers_with_scope:
                _add_accessibility_issue(
                    accessibility_issues,
                    "Missing Header Scope",
                    "Complex table headers missing scope attributes",
                    location,
                    "Suggestion"
                )

def _check_lists_accessibility(soup, location, accessibility_issues):
    """Check for list accessibility issues"""
    # Find improperly structured lists (using line breaks instead of list elements)
    text_content = soup.get_text()
    lines = text_content.split('\n')
    
    # Look for patterns that suggest lists but aren't marked up as such
    potential_list_lines = []
    for line in lines:
        stripped = line.strip()
        if stripped and (
            stripped.startswith(('•', '-', '*', '1.', '2.', '3.', '4.', '5.')) or
            re.match(r'^\d+\.', stripped) or
            stripped.startswith(('Step ', 'First', 'Second', 'Third', 'Next', 'Finally'))
        ):
            potential_list_lines.append(stripped)
    
    if len(potential_list_lines) >= 2:
        # Check if there are actual lists nearby
        lists = soup.find_all(['ul', 'ol'])
        if not lists:
            _add_accessibility_issue(
                accessibility_issues,
                "Improper List Structure",
                f"Content appears to be a list but not marked up as such: {potential_list_lines[0][:30]}...",
                location,
                "Suggestion"
            )

def _check_pdf_accessibility(course, location, accessibility_issues):
    """Check PDF files for accessibility issues"""
    try:
        # Get files from the course
        files = course.get_files()
        for file_obj in files:
            if file_obj.mime_class == 'pdf':
                _add_accessibility_issue(
                    accessibility_issues,
                    "PDF File Detected",
                    f"PDF file requires manual accessibility review: {file_obj.display_name}",
                    location,
                    "Needs Review"
                )
    except Exception as e:
        # If we can't access files, just note it
        pass

def _check_media_accessibility(soup, location, accessibility_issues):
    """Check for media accessibility issues"""
    # Check for videos without captions
    videos = soup.find_all('video')
    for video in videos:
        tracks = video.find_all('track', kind='captions')
        if not tracks:
            src = video.get('src', 'unknown')
            _add_accessibility_issue(
                accessibility_issues,
                "Video Without Captions",
                f"Video element missing captions: {src[:50]}...",
                location,
                "Error"
            )
    
    # Check for audio without transcripts
    audios = soup.find_all('audio')
    for audio in audios:
        src = audio.get('src', 'unknown')
        _add_accessibility_issue(
            accessibility_issues,
            "Audio Content",
            f"Audio element requires transcript verification: {src[:50]}...",
            location,
            "Needs Review"
        )

def _check_form_accessibility(soup, location, accessibility_issues):
    """Check for form accessibility issues"""
    # Check for form inputs without labels
    inputs = soup.find_all(['input', 'textarea', 'select'])
    
    for input_elem in inputs:
        input_type = input_elem.get('type', 'text')
        input_id = input_elem.get('id')
        input_name = input_elem.get('name', 'unnamed')
        
        # Skip hidden inputs and buttons
        if input_type in ['hidden', 'submit', 'button']:
            continue
        
        # Check for associated label
        label = None
        if input_id:
            label = soup.find('label', attrs={'for': input_id})
        
        if not label:
            # Check if input is wrapped in a label
            parent_label = input_elem.find_parent('label')
            if not parent_label:
                _add_accessibility_issue(
                    accessibility_issues,
                    "Form Input Without Label",
                    f"Form input missing associated label: {input_name}",
                    location,
                    "Error"
                )

def _run_accessibility_checks(soup, course, location, accessibility_issues):
    """Run all accessibility checks on the parsed HTML"""
    _check_images_accessibility(soup, location, accessibility_issues)
    _check_links_accessibility(soup, location, accessibility_issues)
    _check_headings_accessibility(soup, location, accessibility_issues)
    _check_color_accessibility(soup, location, accessibility_issues)
    _check_tables_accessibility(soup, location, accessibility_issues)
    _check_lists_accessibility(soup, location, accessibility_issues)
    _check_media_accessibility(soup, location, accessibility_issues)
    _check_form_accessibility(soup, location, accessibility_issues)
    _check_pdf_accessibility(course, location, accessibility_issues)

def _process_html_with_accessibility(soup, course, page, yt_links, media_links, link_media, lib_media, accessibility_issues):
    """Enhanced HTML processing that includes accessibility checks"""
    # Run original media processing
    _process_html(soup, course, page, yt_links, media_links, link_media, lib_media)
    
    # Run accessibility checks
    _run_accessibility_checks(soup, course, page, accessibility_issues)

# ----------------------------------------------------------------------
# MAIN FUNCTION (UPDATED)
# ----------------------------------------------------------------------
def run_caption_report(course_input: str) -> str:
    """Generate caption report and accessibility report, write to Google Sheet with multiple tabs."""

    # Authenticate Google Sheets for Colab
    print("🔐 Authenticating with Google Sheets …")
    from google.colab import auth
    from google.auth import default
    auth.authenticate_user()
    creds, _ = default()
    gc = gspread.authorize(creds)

    # Get Canvas course
    if "courses/" in course_input:
        course_id = course_input.split("courses/")[-1].split("/")[0].split("?")[0]
    else:
        course_id = course_input.strip()

    canvas = Canvas(CANVAS_API_URL, CANVAS_API_KEY)
    course = canvas.get_course(course_id)
    print(f"\n📘 Processing Canvas course: {course.name}\n")

    # Data containers
    yt_links, media_links, link_media, lib_media = {}, {}, {}, {}
    accessibility_issues = {}

    def _handle_with_accessibility(html, location):
        if not html:
            return
        soup = BeautifulSoup(html.encode("utf-8"), "html.parser")
        _process_html_with_accessibility(soup, course, location, yt_links, media_links, link_media, lib_media, accessibility_issues)

    # --------------------------------------------------------------
    # Scanning sections with printouts (updated to include accessibility)
    # --------------------------------------------------------------
    print("🔎 Scanning Pages …")
    for p in course.get_pages():
        _handle_with_accessibility(course.get_page(p.url).body, p.html_url)

    print("🔎 Scanning Assignments …")
    for a in course.get_assignments():
        _handle_with_accessibility(a.description, a.html_url)

    print("🔎 Scanning Discussions …")
    for d in course.get_discussion_topics():
        _handle_with_accessibility(d.message, d.html_url)

    print("🔎 Scanning Syllabus …")
    try:
        syllabus = canvas.get_course(course_id, include="syllabus_body")
        _handle_with_accessibility(syllabus.syllabus_body, f"{CANVAS_API_URL}/courses/{course_id}/assignments/syllabus")
    except Exception:
        print("⚠️  Could not load syllabus.")
        pass

    print("🔎 Scanning Modules …")
    for mod in course.get_modules():
        for item in mod.get_module_items(include="content_details"):
            mod_url = f"{CANVAS_API_URL}/courses/{course_id}/modules/items/{item.id}"
            if item.type == "ExternalUrl":
                href = item.external_url
                if re.search(YT_PATTERN, href):
                    yt_links.setdefault(href, []).append(mod_url)
                if any(u in href for u in LIB_MEDIA_URLS):
                    _add_entry(lib_media, href, "Manually Check for Captions", mod_url)
            if item.type == "File":
                try:
                    f = course.get_file(item.content_id)
                    f_url = f.url.split("?")[0]
                    name = f.display_name
                    if "audio" in f.mime_class:
                        _add_entry(link_media, f"Linked Audio File: {name}", "Manually Check for Captions", mod_url, file_location=f_url)
                    if "video" in f.mime_class:
                        _add_entry(link_media, f"Linked Video File: {name}", "Manually Check for Captions", mod_url, file_location=f_url)
                except Exception:
                    pass

    print("🔎 Scanning Announcements …")
    for ann in course.get_discussion_topics(only_announcements=True):
        _handle_with_accessibility(ann.message, ann.html_url)

    # --------------------------------------------------------------
    # YouTube processing (unchanged)
    # --------------------------------------------------------------
    print("\n▶️  Checking YouTube captions …")
    yt_tasks, yt_processed = [], {}
    for key, pages in yt_links.items():
        if "list" in key:
            yt_processed[key] = ["this is a playlist, check individual videos", "", "", ""] + pages
            continue
        vid_match = re.findall(YT_PATTERN, key, re.IGNORECASE)
        video_id = vid_match[0] if vid_match else None
        if video_id:
            yt_tasks.append((key, video_id, pages, YOUTUBE_API_KEY))
        else:
            yt_processed[key] = ["Unable to parse Video ID", "", "", ""] + pages

    if yt_tasks:
        with concurrent.futures.ThreadPoolExecutor(max_workers=10) as ex:
            for k, st, (h, m, s), pg in ex.map(_check_youtube, yt_tasks):
                yt_processed[k] = [st, h, m, s] + pg
    yt_links = yt_processed

    # --------------------------------------------------------------
    # Compile VAST results (unchanged)
    # --------------------------------------------------------------
    print("\n📊 Compiling VAST results …")

    # Check if there are any linked audio/video files
    has_linked_files = len(link_media) > 0

    rows = []
    total_minutes = 0  # Track total duration
    
    for container in (yt_links, media_links, link_media, lib_media):
        for key, vals in container.items():
            # Extract time components (if they exist)
            if len(vals) >= 4:
                status, hour, minute, second = vals[0], vals[1], vals[2], vals[3]
                location = vals[4] if len(vals) > 4 else ""
                file_location = vals[5] if len(vals) > 5 else ""
                
                # Consolidate time and get minutes for totaling
                duration, minutes_to_add = _consolidate_time(hour, minute, second)
                total_minutes += minutes_to_add
                
                # Build row based on whether we have file locations
                if has_linked_files:
                    rows.append([key, status, duration, location, file_location])
                else:
                    rows.append([key, status, duration, location])
            else:
                # Fallback for entries without time data
                if has_linked_files:
                    rows.append([key] + vals + [""] * (5 - len(vals)))
                else:
                    rows.append([key] + vals + [""] * (4 - len(vals)))

    # Add total row
    total_duration = _minutes_to_duration(total_minutes)
    if has_linked_files:
        total_row = ["Total Duration", "", total_duration, "", ""]
    else:
        total_row = ["Total Duration", "", total_duration, ""]
    
    rows.append(total_row)

    # Define columns based on whether there are linked files
    if has_linked_files:
        columns = [
            "Media", "Caption Status", "Duration (HH:MM)", "Location", "File Location"
        ]
    else:
        columns = [
            "Media", "Caption Status", "Duration (HH:MM)", "Location"
        ]

    vast_df = pd.DataFrame(rows, columns=columns)

    # --------------------------------------------------------------
    # Compile Accessibility results
    # --------------------------------------------------------------
    print("\n♿ Compiling Accessibility results …")
    
    accessibility_rows = []
    error_count = 0
    suggestion_count = 0
    review_count = 0
    
    for issue_key, occurrences in accessibility_issues.items():
        for occurrence in occurrences:
            severity = occurrence['severity']
            location = occurrence['location']
            description = occurrence['description']
            
            accessibility_rows.append([
                issue_key,
                severity,
                description,
                location
            ])
            
            # Count by severity
            if severity == "Error":
                error_count += 1
            elif severity == "Suggestion":
                suggestion_count += 1
            elif severity == "Needs Review":
                review_count += 1

    # Add summary row
    summary_row = [
        "SUMMARY",
        f"Errors: {error_count}, Suggestions: {suggestion_count}, Needs Review: {review_count}",
        f"Total Issues: {len(accessibility_rows)}",
        ""
    ]
    accessibility_rows.insert(0, summary_row)

    accessibility_df = pd.DataFrame(accessibility_rows, columns=[
        "Issue Type", "Severity", "Description", "Location"
    ])

    # --------------------------------------------------------------
    # Create or replace Google Sheet with multiple tabs
    # --------------------------------------------------------------
# --------------------------------------------------------------
# Create or replace Google Sheet with multiple tabs (NO SHARING)
# --------------------------------------------------------------
print("\n📄 Creating or updating Google Sheet …")
sheet_title = f"{course.name} VAST Report"

try:
    existing_sheets = gc.list_spreadsheet_files()
    sheet = next((s for s in existing_sheets if s["name"] == sheet_title), None)
except Exception:
    sheet = None

if sheet:
    print(f"♻️  Found existing sheet: {sheet_title}. Updating contents …")
    sh = gc.open_by_key(sheet["id"])
    
    # Ensure we have the worksheets we need
    worksheet_names = [ws.title for ws in sh.worksheets()]
    
    # Get or create VAST Report worksheet
    if "VAST Report" in worksheet_names:
        vast_ws = sh.worksheet("VAST Report")
        vast_ws.clear()
    else:
        # If no VAST Report exists, check if we can rename sheet1
        if len(worksheet_names) == 1 and worksheet_names[0] == "Sheet1":
            vast_ws = sh.sheet1
            vast_ws.update_title("VAST Report")
            vast_ws.clear()
        else:
            # Add new VAST Report worksheet
            vast_ws = sh.add_worksheet(title="VAST Report", rows=1000, cols=10)
    
    # Get or create Accessibility Issues worksheet
    if "Accessibility Issues" in worksheet_names:
        accessibility_ws = sh.worksheet("Accessibility Issues")
        accessibility_ws.clear()
    else:
        accessibility_ws = sh.add_worksheet(title="Accessibility Issues", rows=1000, cols=10)
    
    # Clean up any unwanted worksheets (but keep at least our two)
    current_worksheets = sh.worksheets()
    for ws in current_worksheets:
        if ws.title not in ["VAST Report", "Accessibility Issues"] and len(current_worksheets) > 2:
            try:
                sh.del_worksheet(ws)
                current_worksheets.remove(ws)  # Update our list
            except Exception as e:
                print(f"⚠️  Could not delete worksheet '{ws.title}': {e}")
            
else:
    print(f"🆕 No existing sheet found. Creating new sheet: {sheet_title}")
    sh = gc.create(sheet_title)
    vast_ws = sh.sheet1
    vast_ws.update_title("VAST Report")
    
    # Create accessibility worksheet
    accessibility_ws = sh.add_worksheet(title="Accessibility Issues", rows=1000, cols=10)

# Write data to worksheets
print("📝 Writing VAST Report data...")
set_with_dataframe(vast_ws, vast_df)

print("📝 Writing Accessibility Issues data...")
set_with_dataframe(accessibility_ws, accessibility_df)

print(f"\n✅ Report complete for: {course.name}")
print(f"📎 Google Sheet URL: {sh.url}")
print(f"⏱️  Total media duration: {total_duration}")
print(f"♿ Accessibility Issues Found:")
print(f"   🔴 Errors: {error_count}")
print(f"   🟡 Suggestions: {suggestion_count}")
print(f"   🔵 Needs Review: {review_count}")
print(f"   📊 Total: {len(accessibility_rows)-1}")  # -1 for summary row

return sh.url


# ----------------------------------------------------------------------
# Usage example (unchanged)
# ----------------------------------------------------------------------
# run_caption_report("your_course_id_here")

