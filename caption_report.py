# @title VAST PHP with Built-in Accessibility Tests {display-mode: "form"}

course_url = "https://boisestatecanvas.instructure.com/courses/1834" # @param {"type":"string","placeholder":"Enter your course url here"}

import subprocess
import time
import sys
import os
import json
from google.colab import userdata

try:
    # Get secrets from Google Colab userdata
    try:
        canvas_api_url = userdata.get('CANVAS_API_URL')
        canvas_api_key = userdata.get('CANVAS_API_KEY') 
        youtube_api_key = userdata.get('YOUTUBE_API_KEY')
    except Exception as e:
        print("❌ Error accessing userdata secrets:")
        print("Please make sure you have set the following secrets in Google Colab:")
        print("- CANVAS_API_URL")
        print("- CANVAS_API_KEY") 
        print("- YOUTUBE_API_KEY")
        print("\nTo add secrets: Click the key icon (🔑) in the left sidebar")
        raise e

    # Validate that secrets exist
    if not canvas_api_url or not canvas_api_key or not youtube_api_key:
        missing = []
        if not canvas_api_url: missing.append('CANVAS_API_URL')
        if not canvas_api_key: missing.append('CANVAS_API_KEY')
        if not youtube_api_key: missing.append('YOUTUBE_API_KEY')
        
        print(f"❌ Missing required secrets: {', '.join(missing)}")
        print("\nPlease add these secrets in Google Colab:")
        print("1. Click the key icon (🔑) in the left sidebar")
        print("2. Add each secret with the exact names listed above")
        sys.exit(1)

    # Authenticate with Google for Sheets access
    print("🔐 Authenticating with Google Sheets...")
    
    # Use gspread with Google Colab authentication
    from google.colab import auth
    import gspread
    from google.auth import default
    
    auth.authenticate_user()
    creds, _ = default()
    gc = gspread.authorize(creds)
    
    # Test the authentication by trying to access Google Drive
    try:
        # This will fail if authentication didn't work
        gc.list_spreadsheet_files()
        print("✅ Google Sheets authentication successful!")
    except Exception as e:
        print(f"❌ Google Sheets authentication failed: {e}")
        print("Please try running the cell again and make sure to complete the authentication process.")
        sys.exit(1)

    # Check if already set up
    repo_path = '/content/vast_php'
    if not os.path.exists(repo_path):
        print("📥 Setting up PHP environment...")
        
        # Create directory
        os.makedirs(repo_path, exist_ok=True)
        
        # Install PHP and Composer
        print("🔧 Installing PHP and Composer...")
        subprocess.check_call(["apt", "update", "-qq"])
        subprocess.check_call(["apt", "install", "-y", "-qq", "php", "php-cli", "php-curl", "php-json", "php-mbstring", "php-xml", "unzip"])
        
        # Install Composer
        subprocess.check_call(["curl", "-sS", "https://getcomposer.org/installer", "-o", "/tmp/composer-setup.php"])
        subprocess.check_call(["php", "/tmp/composer-setup.php", "--install-dir=/usr/local/bin", "--filename=composer"])
        
        print("📦 Creating PHP project structure...")
        
        # Create composer.json without PHPAlly
        composer_json = """{
    "require": {
        "guzzlehttp/guzzle": "^7.0",
        "symfony/dom-crawler": "^6.0",
        "symfony/css-selector": "^6.0"
    }
}"""
        
        with open(f"{repo_path}/composer.json", "w") as f:
            f.write(composer_json)
        
        # Install PHP dependencies
        print("📦 Installing PHP dependencies...")
        subprocess.check_call(["composer", "install", "--no-dev", "-q"], cwd=repo_path)
        
        # Create the main PHP script with built-in accessibility tests
        php_script = '''<?php
// Composer autoload
require_once 'vendor/autoload.php';

use GuzzleHttp\\Client;
use GuzzleHttp\\Pool;
use GuzzleHttp\\Psr7\\Request;
use Symfony\\Component\\DomCrawler\\Crawler;

// Get command line arguments
if ($argc < 5) {
    die("❌ Missing required arguments\\nUsage: php script.php <course_url> <canvas_api_url> <canvas_api_key> <youtube_api_key>\\n");
}

$courseInput = $argv[1];
$CANVAS_API_URL = $argv[2];
$CANVAS_API_KEY = $argv[3];
$YOUTUBE_API_KEY = $argv[4];

define('YT_CAPTION_URL', 'https://www.googleapis.com/youtube/v3/captions');
define('YT_VIDEO_URL', 'https://www.googleapis.com/youtube/v3/videos');
define('YT_PATTERN', '/(?:https?:\\/\\/)?(?:[0-9A-Z-]+\\.)?(?:youtube|youtu|youtube-nocookie)\\.(?:com|be)\\/(?:watch\\?v=|watch\\?.+&v=|embed\\/|v\\/|.+\\?v=)?([^&=\\n%\\?]{11})/i');

$LIB_MEDIA_URLS = [
    "fod.infobase.com",
    "search.alexanderstreet.com", 
    "kanopystreaming-com",
    "hosted.panopto.com"
];

// Accessibility test configuration
$ALT_TEXT_MAX_LENGTH = 120;
$PLACEHOLDER_TERMS = ['nbsp', ' ', 'spacer', 'image', 'img', 'photo', 'picture', 'graphic'];

// Helper Functions
function authHeader($token) {
    return ['Authorization' => 'Bearer ' . trim($token)];
}

function addEntry(&$array, $name, $status, $page, $hour = "", $minute = "", $second = "", $fileLocation = "") {
    $array[$name] = [$status, $hour, $minute, $second, $page, $fileLocation];
}

function addAccessibilityEntry(&$array, $test, $status, $count, $page, $details = "") {
    $array[] = [
        'test' => $test,
        'status' => $status,
        'count' => $count,
        'page' => $page,
        'details' => $details
    ];
}

function consolidateTime($hourStr, $minuteStr, $secondStr) {
    try {
        $hours = $hourStr && trim($hourStr) ? (int)$hourStr : 0;
        $minutes = $minuteStr && trim($minuteStr) ? (int)$minuteStr : 0;
        $seconds = $secondStr && trim($secondStr) ? (int)$secondStr : 0;
        
        $totalMinutes = $hours * 60 + $minutes + ($seconds > 0 ? 1 : 0);
        
        if ($seconds > 0) {
            $minutes++;
        }
        
        if ($minutes >= 60) {
            $hours += intval($minutes / 60);
            $minutes = $minutes % 60;
        }
        
        return [sprintf("%02d:%02d", $hours, $minutes), $totalMinutes];
    } catch (Exception $e) {
        return ["", 0];
    }
}

function minutesToDuration($totalMinutes) {
    if ($totalMinutes <= 0) return "00:00";
    $hours = intval($totalMinutes / 60);
    $minutes = $totalMinutes % 60;
    return sprintf("%02d:%02d", $hours, $minutes);
}

function getCanvasData($endpoint) {
    global $CANVAS_API_URL, $CANVAS_API_KEY;
    $client = new Client(['timeout' => 30]);
    try {
        $response = $client->get($CANVAS_API_URL . $endpoint, [
            'headers' => authHeader($CANVAS_API_KEY)
        ]);
        return json_decode($response->getBody(), true);
    } catch (Exception $e) {
        echo "⚠️  Error fetching: $endpoint - " . $e->getMessage() . "\\n";
        return [];
    }
}

function checkMediaObject($url) {
    global $CANVAS_API_KEY;
    $client = new Client(['timeout' => 10]);
    try {
        $response = $client->get($url, ['headers' => authHeader($CANVAS_API_KEY)]);
        $text = $response->getBody()->getContents();
        
        if (strpos($text, '"kind":"subtitles"') !== false) {
            return [$url, strpos($text, '"locale":"en"') !== false ? "Captions in English" : "No English Captions"];
        }
        return [$url, "No Captions"];
    } catch (Exception $e) {
        return [$url, "Unable to Check Media Object"];
    }
}

function parseIso8601($duration) {
    $h = $m = $sec = "0";
    preg_match_all('/([0-9]+)[HMS]/', $duration, $matches, PREG_SET_ORDER);
    foreach ($matches as $match) {
        $unit = substr($match[0], -1);
        $val = $match[1];
        switch ($unit) {
            case 'H': $h = $val; break;
            case 'M': $m = $val; break;
            case 'S': $sec = $val; break;
        }
    }
    return [$h, $m, $sec];
}

function checkYoutube($key, $videoId) {
    global $YOUTUBE_API_KEY;
    if (!$videoId) {
        return [$key, "Unable to parse Video ID", ["", "", ""]];
    }
    
    $client = new Client(['timeout' => 15]);
    
    try {
        // Get video duration
        $response1 = $client->get(YT_VIDEO_URL . "?part=contentDetails&id={$videoId}&key={$YOUTUBE_API_KEY}");
        $data1 = json_decode($response1->getBody(), true);
        
        if (empty($data1['items'])) {
            return [$key, "Video not found or private", ["", "", ""]];
        }
        
        $duration = $data1['items'][0]['contentDetails']['duration'];
        list($h, $m, $s) = parseIso8601($duration);
        
        // Get captions
        $response2 = $client->get(YT_CAPTION_URL . "?part=snippet&videoId={$videoId}&key={$YOUTUBE_API_KEY}");
        $data2 = json_decode($response2->getBody(), true);
        $caps = $data2['items'] ?? [];
        
        $status = "No Captions";
        if (!empty($caps)) {
            $langs = [];
            foreach ($caps as $cap) {
                $langs[$cap['snippet']['language']] = $cap['snippet']['trackKind'];
            }
            
            if (isset($langs['en']) || isset($langs['en-US'])) {
                $kind = $langs['en'] ?? $langs['en-US'];
                if ($kind === 'standard') {
                    $status = "Captions found in English";
                } elseif ($kind === 'asr') {
                    $status = "Automatic Captions in English";
                } else {
                    $status = "Captions in English (unknown kind)";
                }
            } else {
                $status = "No Captions in English";
            }
        }
        
        return [$key, $status, [$h, $m, $s]];
    } catch (Exception $e) {
        return [$key, "Unable to Check Youtube Video: " . $e->getMessage(), ["", "", ""]];
    }
}

// Built-in Accessibility Test Functions
function testImgAltIsDifferent($crawler, $location, &$accessibilityResults) {
    $issues = [];
    $crawler->filter('img')->each(function (Crawler $node) use (&$issues) {
        $src = $node->attr('src');
        $alt = $node->attr('alt');
        
        if ($src && $alt) {
            $filename = pathinfo(parse_url($src, PHP_URL_PATH), PATHINFO_FILENAME);
            if (strtolower($alt) === strtolower($filename)) {
                $issues[] = "Alt text matches filename: '$alt'";
            }
        }
    });
    
    $status = empty($issues) ? 'PASS' : 'FAIL';
    $details = empty($issues) ? '' : implode('; ', array_slice($issues, 0, 3));
    addAccessibilityEntry($accessibilityResults, 'imgAltIsDifferent', $status, count($issues), $location, $details);
}

function testImgAltIsTooLong($crawler, $location, &$accessibilityResults) {
    global $ALT_TEXT_MAX_LENGTH;
    $issues = [];
    
    $crawler->filter('img')->each(function (Crawler $node) use (&$issues, $ALT_TEXT_MAX_LENGTH) {
        $alt = $node->attr('alt');
        if ($alt && strlen($alt) > $ALT_TEXT_MAX_LENGTH) {
            $issues[] = "Alt text too long (" . strlen($alt) . " chars): " . substr($alt, 0, 50) . "...";
        }
    });
    
    $status = empty($issues) ? 'PASS' : 'FAIL';
    $details = empty($issues) ? '' : implode('; ', array_slice($issues, 0, 3));
    addAccessibilityEntry($accessibilityResults, 'imgAltIsTooLong', $status, count($issues), $location, $details);
}

function testImgAltNotPlaceHolder($crawler, $location, &$accessibilityResults) {
    global $PLACEHOLDER_TERMS;
    $issues = [];
    
    $crawler->filter('img')->each(function (Crawler $node) use (&$issues, $PLACEHOLDER_TERMS) {
        $alt = strtolower(trim($node->attr('alt')));
        if ($alt && in_array($alt, $PLACEHOLDER_TERMS)) {
            $issues[] = "Placeholder alt text: '$alt'";
        }
    });
    
    $status = empty($issues) ? 'PASS' : 'FAIL';
    $details = empty($issues) ? '' : implode('; ', array_slice($issues, 0, 3));
    addAccessibilityEntry($accessibilityResults, 'imgAltNotPlaceHolder', $status, count($issues), $location, $details);
}

function testImgAltNotEmptyInAnchor($crawler, $location, &$accessibilityResults) {
    $issues = [];
    
    $crawler->filter('a img')->each(function (Crawler $node) use (&$issues) {
        $alt = trim($node->attr('alt'));
        if (empty($alt)) {
            $src = $node->attr('src');
            $issues[] = "Image in link missing alt text: " . ($src ? basename($src) : 'unknown');
        }
    });
    
    $status = empty($issues) ? 'PASS' : 'FAIL';
    $details = empty($issues) ? '' : implode('; ', array_slice($issues, 0, 3));
    addAccessibilityEntry($accessibilityResults, 'imgAltNotEmptyInAnchor', $status, count($issues), $location, $details);
}

function testTableDataShouldHaveTh($crawler, $location, &$accessibilityResults) {
    $issues = [];
    
    $crawler->filter('table')->each(function (Crawler $node, $i) use (&$issues) {
        $hasTh = $node->filter('th')->count() > 0;
        $hasTd = $node->filter('td')->count() > 0;
        
        if ($hasTd && !$hasTh) {
            $issues[] = "Table " . ($i + 1) . " has data but no headers";
        }
    });
    
    $status = empty($issues) ? 'PASS' : 'FAIL';
    $details = empty($issues) ? '' : implode('; ', $issues);
    addAccessibilityEntry($accessibilityResults, 'tableDataShouldHaveTh', $status, count($issues), $location, $details);
}

function testTableThShouldHaveScope($crawler, $location, &$accessibilityResults) {
    $issues = [];
    
    $crawler->filter('th')->each(function (Crawler $node, $i) use (&$issues) {
        $scope = $node->attr('scope');
        if (!$scope || !in_array($scope, ['row', 'col', 'rowgroup', 'colgroup'])) {
            $text = trim($node->text());
            $issues[] = "Header missing scope: " . (strlen($text) > 30 ? substr($text, 0, 30) . "..." : $text);
        }
    });
    
    $status = empty($issues) ? 'PASS' : 'FAIL';
    $details = empty($issues) ? '' : implode('; ', array_slice($issues, 0, 3));
    addAccessibilityEntry($accessibilityResults, 'tableThShouldHaveScope', $status, count($issues), $location, $details);
}

function testObjectMustContainText($crawler, $location, &$accessibilityResults) {
    $issues = [];
    
    $crawler->filter('object')->each(function (Crawler $node, $i) use (&$issues) {
        $text = trim($node->text());
        if (empty($text)) {
            $type = $node->attr('type') ?: 'unknown';
            $issues[] = "Object " . ($i + 1) . " ($type) missing text content";
        }
    });
    
    $status = empty($issues) ? 'PASS' : 'FAIL';
    $details = empty($issues) ? '' : implode('; ', $issues);
    addAccessibilityEntry($accessibilityResults, 'objectMustContainText', $status, count($issues), $location, $details);
}

function testEmbedHasAssociatedNoEmbed($crawler, $location, &$accessibilityResults) {
    $issues = [];
    
    $crawler->filter('embed')->each(function (Crawler $node, $i) use (&$issues) {
        // Check if there's a noembed tag nearby or alternative text
        $parent = $node->parents()->first();
        $hasNoEmbed = $parent->filter('noembed')->count() > 0;
        $hasAlt = !empty(trim($node->attr('alt')));
        
        if (!$hasNoEmbed && !$hasAlt) {
            $src = $node->attr('src') ?: 'unknown';
            $issues[] = "Embed " . ($i + 1) . " missing alternative: " . basename($src);
        }
    });
    
    $status = empty($issues) ? 'PASS' : 'FAIL';
    $details = empty($issues) ? '' : implode('; ', array_slice($issues, 0, 3));
    addAccessibilityEntry($accessibilityResults, 'embedHasAssociatedNoEmbed', $status, count($issues), $location, $details);
}

function testAMustContainText($crawler, $location, &$accessibilityResults) {
    $issues = [];
    
    $crawler->filter('a')->each(function (Crawler $node, $i) use (&$issues) {
        $text = trim($node->text());
        $title = trim($node->attr('title'));
        $ariaLabel = trim($node->attr('aria-label'));
        
        if (empty($text) && empty($title) && empty($ariaLabel)) {
            $href = $node->attr('href') ?: 'unknown';
            $issues[] = "Link missing text: " . (strlen($href) > 50 ? substr($href, 0, 50) . "..." : $href);
        }
    });
    
    $status = empty($issues) ? 'PASS' : 'FAIL';
    $details = empty($issues) ? '' : implode('; ', array_slice($issues, 0, 3));
    addAccessibilityEntry($accessibilityResults, 'aMustContainText', $status, count($issues), $location, $details);
}

function testDeprecatedTags($crawler, $location, &$accessibilityResults) {
    $deprecatedTags = ['basefont', 'font', 'blink', 'marquee'];
    
    foreach ($deprecatedTags as $tag) {
        $count = $crawler->filter($tag)->count();
        $status = $count === 0 ? 'PASS' : 'FAIL';
        $details = $count > 0 ? "$count $tag tag(s) found" : '';
        addAccessibilityEntry($accessibilityResults, $tag . 'IsNotUsed', $status, $count, $location, $details);
    }
}

function testHeadersHaveText($crawler, $location, &$accessibilityResults) {
    $issues = [];
    
    $crawler->filter('h1, h2, h3, h4, h5, h6')->each(function (Crawler $node) use (&$issues) {
        $text = trim($node->text());
        if (empty($text)) {
            $tagName = $node->nodeName();
            $issues[] = "Empty $tagName header found";
        }
    });
    
    $status = empty($issues) ? 'PASS' : 'FAIL';
    $details = empty($issues) ? '' : implode('; ', $issues);
    addAccessibilityEntry($accessibilityResults, 'headersHaveText', $status, count($issues), $location, $details);
}

function runAccessibilityTests($html, $location, &$accessibilityResults) {
    if (!$html) return;
    
    try {
        $crawler = new Crawler($html);
        
        // Run all accessibility tests
        testImgAltIsDifferent($crawler, $location, $accessibilityResults);
        testImgAltIsTooLong($crawler, $location, $accessibilityResults);
        testImgAltNotPlaceHolder($crawler, $location, $accessibilityResults);
        testImgAltNotEmptyInAnchor($crawler, $location, $accessibilityResults);
        testTableDataShouldHaveTh($crawler, $location, $accessibilityResults);
        testTableThShouldHaveScope($crawler, $location, $accessibilityResults);
        testObjectMustContainText($crawler, $location, $accessibilityResults);
        testEmbedHasAssociatedNoEmbed($crawler, $location, $accessibilityResults);
        testAMustContainText($crawler, $location, $accessibilityResults);
        testDeprecatedTags($crawler, $location, $accessibilityResults);
        testHeadersHaveText($crawler, $location, $accessibilityResults);
        
    } catch (Exception $e) {
        echo "⚠️  Accessibility test error for $location: " . $e->getMessage() . "\\n";
    }
}

function processContent($html, $location, &$ytLinks, &$mediaLinks, &$libMedia, &$linkMedia, &$accessibilityResults) {
    global $LIB_MEDIA_URLS;
    
    if (!$html) return;
    
    // Run accessibility tests first
    runAccessibilityTests($html, $location, $accessibilityResults);
    
    $crawler = new Crawler($html);
    
    // Process anchor tags
    $crawler->filter('a')->each(function (Crawler $node) use ($location, &$ytLinks, &$libMedia, &$mediaLinks, &$linkMedia, $LIB_MEDIA_URLS) {
        $href = $node->attr('href');
        if (!$href) return;
        
        // Check for Canvas file links
        $apiEndpoint = $node->attr('data-api-endpoint');
        if ($apiEndpoint && strpos($apiEndpoint, '/files/') !== false) {
            try {
                $fileId = basename($apiEndpoint);
                $file = getCanvasFile($fileId);
                if ($file) {
                    $fileUrl = explode('?', $file['url'])[0];
                    $fileName = $file['display_name'];
                    $mimeClass = $file['mime_class'] ?? '';
                    
                    if (strpos($mimeClass, 'audio') !== false) {
                        addEntry($linkMedia, "Linked Audio File: " . $fileName, "Manually Check for Captions", $location, "", "", "", $fileUrl);
                    }
                    if (strpos($mimeClass, 'video') !== false) {
                        addEntry($linkMedia, "Linked Video File: " . $fileName, "Manually Check for Captions", $location, "", "", "", $fileUrl);
                    }
                }
            } catch (Exception $e) {
                // Skip on error
            }
        }
        
        if (preg_match(YT_PATTERN, $href)) {
            if (!isset($ytLinks[$href])) $ytLinks[$href] = [];
            $ytLinks[$href][] = $location;
        } elseif (arrayContainsSubstring($LIB_MEDIA_URLS, $href)) {
            addEntry($libMedia, $href, "Manually Check for Captions", $location);
        } elseif (strpos($href, 'media_objects') !== false) {
            $result = checkMediaObject($href);
            addEntry($mediaLinks, $result[0], $result[1], $location);
        }
    });
    
    // Process iframe tags
    $crawler->filter('iframe')->each(function (Crawler $node) use ($location, &$ytLinks, &$libMedia, &$mediaLinks, $LIB_MEDIA_URLS) {
        $src = $node->attr('src');
        if (!$src) return;
        
        if (preg_match(YT_PATTERN, $src)) {
            if (!isset($ytLinks[$src])) $ytLinks[$src] = [];
            $ytLinks[$src][] = $location;
        } elseif (arrayContainsSubstring($LIB_MEDIA_URLS, $src)) {
            addEntry($libMedia, $src, "Manually Check for Captions", $location);
        } elseif (strpos($src, 'media_objects_iframe') !== false) {
            $result = checkMediaObject($src);
            addEntry($mediaLinks, $result[0], $result[1], $location);
        }
    });
    
    // Process video tags
    $crawler->filter('video')->each(function (Crawler $node) use ($location, &$mediaLinks) {
        $mediaCommentId = $node->attr('data-media_comment_id');
        if ($mediaCommentId) {
            $name = "Video Media Comment " . $mediaCommentId;
            $hasTrack = $node->filter('track')->count() > 0;
            $status = $hasTrack ? "Captions" : "No Captions";
            addEntry($mediaLinks, $name, $status, $location);
        }
    });
    
    // Process source tags
    $crawler->filter('source')->each(function (Crawler $node) use ($location, &$mediaLinks) {
        if ($node->attr('type') === 'video/mp4') {
            $name = "Embedded Canvas Video " . $node->attr('src');
            addEntry($mediaLinks, $name, "Manually Check for Captions", $location);
        }
    });
    
    // Process audio tags
    $crawler->filter('audio')->each(function (Crawler $node) use ($location, &$mediaLinks) {
        $mediaCommentId = $node->attr('data-media_comment_id');
        if ($mediaCommentId) {
            $name = "Audio Media Comment " . $mediaCommentId;
            $hasTrack = $node->filter('track')->count() > 0;
            $status = $hasTrack ? "Captions" : "No Captions";
            addEntry($mediaLinks, $name, $status, $location);
        } else {
            $name = "Embedded Canvas Audio " . ($node->attr('src') ?: '');
            addEntry($mediaLinks, $name, "Manually Check for Captions", $location);
        }
    });
}

function getCanvasFile($fileId) {
    global $CANVAS_API_URL, $CANVAS_API_KEY;
    $client = new Client(['timeout' => 10]);
    try {
        $response = $client->get($CANVAS_API_URL . "/api/v1/files/{$fileId}", [
            'headers' => authHeader($CANVAS_API_KEY)
        ]);
        return json_decode($response->getBody(), true);
    } catch (Exception $e) {
        return null;
    }
}

function arrayContainsSubstring($array, $string) {
    foreach ($array as $item) {
        if (strpos($string, $item) !== false) {
            return true;
        }
    }
    return false;
}

// Extract course ID
if (strpos($courseInput, 'courses/') !== false) {
    $parts = explode('courses/', $courseInput);
    $courseId = explode('/', explode('?', $parts[1])[0])[0];
} else {
    $courseId = trim($courseInput);
}

echo "🚀 Starting VAST Caption Report with Accessibility Tests...\\n";
echo "📘 Processing Canvas course ID: $courseId\\n\\n";

// Get course info
$course = getCanvasData("/api/v1/courses/{$courseId}");
if (empty($course)) {
    die("❌ Could not fetch course information. Check your Canvas API credentials and course ID.\\n");
}

$courseName = $course['name'] ?? 'Unknown Course';
echo "📘 Course: $courseName\\n\\n";

// Data containers
$ytLinks = [];
$mediaLinks = [];
$libMedia = [];
$linkMedia = [];
$accessibilityResults = [];
$totalMinutes = 0;

// Scan pages
echo "🔎 Scanning Pages...\\n";
$pages = getCanvasData("/api/v1/courses/{$courseId}/pages");
foreach ($pages as $page) {
    $pageData = getCanvasData("/api/v1/courses/{$courseId}/pages/" . $page['url']);
    processContent($pageData['body'] ?? '', $page['html_url'] ?? '', $ytLinks, $mediaLinks, $libMedia, $linkMedia, $accessibilityResults);
}

// Scan assignments
echo "🔎 Scanning Assignments...\\n";
$assignments = getCanvasData("/api/v1/courses/{$courseId}/assignments");
foreach ($assignments as $assignment) {
    processContent($assignment['description'] ?? '', $assignment['html_url'] ?? '', $ytLinks, $mediaLinks, $libMedia, $linkMedia, $accessibilityResults);
}

// Scan discussions
echo "🔎 Scanning Discussions...\\n";
$discussions = getCanvasData("/api/v1/courses/{$courseId}/discussion_topics");
foreach ($discussions as $discussion) {
    processContent($discussion['message'] ?? '', $discussion['html_url'] ?? '', $ytLinks, $mediaLinks, $libMedia, $linkMedia, $accessibilityResults);
}

// Scan syllabus
echo "🔎 Scanning Syllabus...\\n";
try {
    $syllabusData = getCanvasData("/api/v1/courses/{$courseId}?include[]=syllabus_body");
    processContent($syllabusData['syllabus_body'] ?? '', $CANVAS_API_URL . "/courses/{$courseId}/assignments/syllabus", $ytLinks, $mediaLinks, $libMedia, $linkMedia, $accessibilityResults);
} catch (Exception $e) {
    echo "⚠️  Could not load syllabus.\\n";
}

// Scan modules
echo "🔎 Scanning Modules...\\n";
$modules = getCanvasData("/api/v1/courses/{$courseId}/modules");
foreach ($modules as $module) {
    $moduleItems = getCanvasData("/api/v1/courses/{$courseId}/modules/{$module['id']}/items?include[]=content_details");
    foreach ($moduleItems as $item) {
        $modUrl = $CANVAS_API_URL . "/courses/{$courseId}/modules/items/{$item['id']}";
        
        if ($item['type'] === 'ExternalUrl') {
            $href = $item['external_url'];
            if (preg_match(YT_PATTERN, $href)) {
                if (!isset($ytLinks[$href])) $ytLinks[$href] = [];
                $ytLinks[$href][] = $modUrl;
            }
            if (arrayContainsSubstring($LIB_MEDIA_URLS, $href)) {
                addEntry($libMedia, $href, "Manually Check for Captions", $modUrl);
            }
        }
        if ($item['type'] === 'File' && isset($item['content_id'])) {
            $file = getCanvasFile($item['content_id']);
            if ($file) {
                $fileUrl = explode('?', $file['url'])[0];
                $fileName = $file['display_name'];
                $mimeClass = $file['mime_class'] ?? '';
                
                if (strpos($mimeClass, 'audio') !== false) {
                    addEntry($linkMedia, "Linked Audio File: " . $fileName, "Manually Check for Captions", $modUrl, "", "", "", $fileUrl);
                }
                if (strpos($mimeClass, 'video') !== false) {
                    addEntry($linkMedia, "Linked Video File: " . $fileName, "Manually Check for Captions", $modUrl, "", "", "", $fileUrl);
                }
            }
        }
    }
}

// Scan announcements
echo "🔎 Scanning Announcements...\\n";
$announcements = getCanvasData("/api/v1/courses/{$courseId}/discussion_topics?only_announcements=true");
foreach ($announcements as $announcement) {
    processContent($announcement['message'] ?? '', $announcement['html_url'] ?? '', $ytLinks, $mediaLinks, $libMedia, $linkMedia, $accessibilityResults);
}

// Process YouTube links
echo "\\n▶️  Checking YouTube captions...\\n";
$results = [];

foreach ($ytLinks as $key => $pages) {
    if (strpos($key, 'list') !== false) {
        $results[] = [$key, "This is a playlist, check individual videos", "", implode("; ", $pages)];
        continue;
    }
    
    preg_match(YT_PATTERN, $key, $matches);
    $videoId = $matches[1] ?? null;
    
    list($url, $status, $time) = checkYoutube($key, $videoId);
    list($duration, $minutes) = consolidateTime($time[0], $time[1], $time[2]);
    $totalMinutes += $minutes;
    
    $results[] = [$url, $status, $duration, implode("; ", $pages)];
}

// Add media links to results
foreach ($mediaLinks as $key => $vals) {
    $status = $vals[0];
    $location = $vals[4] ?? "";
    $results[] = [$key, $status, "", $location];
}

// Add library media to results
foreach ($libMedia as $key => $vals) {
    $status = $vals[0];
    $location = $vals[4] ?? "";
    $results[] = [$key, $status, "", $location];
}

// Add linked media to results
foreach ($linkMedia as $key => $vals) {
    $status = $vals[0];
    $location = $vals[4] ?? "";
    $fileLocation = $vals[5] ?? "";
    $results[] = [$key, $status, "", $location];
}

// Determine if we have linked files
$hasLinkedFiles = !empty($linkMedia);

// Prepare data for output
if ($hasLinkedFiles) {
    $columns = ["Media", "Caption Status", "Duration (HH:MM)", "Location", "File Location"];
} else {
    $columns = ["Media", "Caption Status", "Duration (HH:MM)", "Location"];
}

// Accessibility columns
$accessibilityColumns = ["Test Name", "Status", "Issues Found", "Location", "Details"];

// Output results as JSON for Python to process
$outputData = [
    'courseName' => $courseName,
    'totalDuration' => minutesToDuration($totalMinutes),
    'totalMinutes' => $totalMinutes,
    'hasLinkedFiles' => $hasLinkedFiles,
    'columns' => $columns,
    'results' => $results,
    'accessibilityColumns' => $accessibilityColumns,
    'accessibilityResults' => $accessibilityResults
];

echo "\\n" . json_encode($outputData) . "\\n";
?>'''
        
        with open(f"{repo_path}/vast_report.php", "w") as f:
            f.write(php_script)
        
        print("✅ PHP environment with built-in accessibility tests setup complete!")
        
    else:
        print("✅ PHP environment already exists!")
    
    # Validate course URL
    if not course_url:
        print("❌ Please provide a course URL!")
        sys.exit(1)
    
    print("🚀 Running VAST Caption Report with Built-in Accessibility Tests...")
    print("----------------------------------------------------------")
    
    # Run the PHP script
    result = subprocess.run([
        "php", f"{repo_path}/vast_report.php", 
        course_url, 
        canvas_api_url, 
        canvas_api_key, 
        youtube_api_key
    ], 
    cwd=repo_path,
    capture_output=True, 
    text=True
    )
    
    if result.returncode == 0:
        # Parse PHP output
        output_lines = result.stdout.strip().split('\n')
        json_line = output_lines[-1]  # Last line should be JSON
        
        try:
            data = json.loads(json_line)
            
            # Display console output (everything except the JSON line)
            console_output = '\n'.join(output_lines[:-1])
            print(console_output)
            
            # Create Google Sheet using Python
            print("\n📄 Creating/updating Google Sheet with accessibility results...")
            
            course_name = data['courseName']
            total_duration = data['totalDuration']
            has_linked_files = data['hasLinkedFiles']
            columns = data['columns']
            results = data['results']
            accessibility_columns = data['accessibilityColumns']
            accessibility_results = data['accessibilityResults']
            
            sheet_title = f"{course_name} VAST Report"
            
            # Check for existing sheet
            try:
                existing_sheets = gc.list_spreadsheet_files()
                existing_sheet = next((s for s in existing_sheets if s["name"] == sheet_title), None)
            except:
                existing_sheet = None
            
            if existing_sheet:
                print("♻️  Found existing sheet. Updating contents...")
                sh = gc.open_by_key(existing_sheet["id"])
                # Clear all worksheets
                for ws in sh.worksheets():
                    ws.clear()
            else:
                print("🆕 Creating new Google Sheet...")
                sh = gc.create(sheet_title)
            
            # Create/get worksheets
            try:
                media_ws = sh.worksheet("Media Analysis")
            except:
                media_ws = sh.add_worksheet("Media Analysis", rows=1000, cols=10)
            
            try:
                accessibility_ws = sh.worksheet("Accessibility Tests")
            except:
                accessibility_ws = sh.add_worksheet("Accessibility Tests", rows=1000, cols=10)
            
            # Prepare media sheet data
            media_data = [columns]
            for row in results:
                if has_linked_files and len(row) < 5:
                    row.append("")  # Add empty file location if needed
                media_data.append(row)
            
            # Add total row
            if has_linked_files:
                media_data.append(["Total Duration", "", total_duration, "", ""])
            else:
                media_data.append(["Total Duration", "", total_duration, ""])
            
            # Prepare accessibility sheet data
            accessibility_data = [accessibility_columns]
            for result in accessibility_results:
                accessibility_data.append([
                    result['test'],
                    result['status'],
                    result['count'],
                    result['page'],
                    result['details'][:500] if len(result['details']) > 500 else result['details']  # Truncate long details
                ])
            
            # Write to sheets
            try:
                # Install required packages if not present
                try:
                    from gspread_dataframe import set_with_dataframe
                    import pandas as pd
                except ImportError:
                    print("📦 Installing required packages...")
                    subprocess.check_call([sys.executable, "-m", "pip", "install", "gspread-dataframe", "pandas"])
                    from gspread_dataframe import set_with_dataframe
                    import pandas as pd
                
                # Write media data
                if len(media_data) > 1:
                    media_df = pd.DataFrame(media_data[1:], columns=media_data[0])
                    set_with_dataframe(media_ws, media_df)
                
                # Write accessibility data
                if accessibility_data and len(accessibility_data) > 1:
                    accessibility_df = pd.DataFrame(accessibility_data[1:], columns=accessibility_data[0])
                    set_with_dataframe(accessibility_ws, accessibility_df)
                else:
                    # If no accessibility results, add a note
                    accessibility_ws.update('A1:E1', [accessibility_columns])
                    accessibility_ws.update('A2', [["No accessibility issues found or tests could not be run"]])
                
                # Make sheet public
                try:
                    sh.share('', perm_type='anyone', role='reader')
                except:
                    pass
                
                print(f"\n✅ Report completed successfully!")
                print(f"📎 Google Sheet URL: {sh.url}")
                print(f"⏱️  Total media duration: {total_duration}")
                print(f"🔍 Accessibility tests run: {len(accessibility_results)} results")
                
                # Display summary
                print(f"\n📊 Media Results Summary:")
                print("=" * 80)
                print(f"{'Media':<50} {'Caption Status':<30} {'Duration':<12} Location")
                print("=" * 80)
                
                for row in results[:10]:  # Show first 10 results
                    print(f"{row[0][:49]:<50} {row[1][:29]:<30} {row[2]:<12} {row[3][:50] if len(row) > 3 else ''}")
                
                if len(results) > 10:
                    print(f"... and {len(results) - 10} more results")
                
                print("=" * 80)
                print(f"{'TOTAL DURATION':<50} {'':<30} {total_duration:<12}")
                print("=" * 80)
                
                # Display accessibility summary
                if accessibility_results:
                    print(f"\n🔍 Accessibility Test Summary:")
                    print("=" * 80)
                    
                    # Count pass/fail
                    pass_count = sum(1 for r in accessibility_results if r['status'] == 'PASS')
                    fail_count = sum(1 for r in accessibility_results if r['status'] == 'FAIL')
                    error_count = sum(1 for r in accessibility_results if r['status'] == 'ERROR')
                    
                    print(f"✅ Passed: {pass_count}")
                    print(f"❌ Failed: {fail_count}")
                    print(f"⚠️  Errors: {error_count}")
                    print("=" * 80)
                    
                    # Show failed tests
                    failed_tests = [r for r in accessibility_results if r['status'] == 'FAIL' and r['count'] > 0]
                    if failed_tests:
                        print("Top accessibility issues:")
                        for test in failed_tests[:5]:  # Show top 5 issues
                            print(f"• {test['test']}: {test['count']} issues found")
                
            except Exception as e:
                print(f"❌ Error writing to Google Sheets: {e}")
                print("Raw data available in PHP output above")
                
        except json.JSONDecodeError:
            print("❌ Error parsing PHP output")
            print("PHP Output:", result.stdout)
        
    else:
        print("❌ Error running PHP script:")
        print(result.stderr)
        if result.stdout:
            print("Output:", result.stdout)

except subprocess.CalledProcessError as e:
    print(f"❌ Error during setup: {e}")
    print("Please check your internet connection and try again.")

except Exception as e:
    print(f"❌ Unexpected error: {e}")
    import traceback
    traceback.print_exc()
