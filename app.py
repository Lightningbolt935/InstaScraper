"""
Enhanced Instagram Profile Scraper Backend
Features: Rate limiting, error handling, caching, retry logic
"""

from flask import Flask, jsonify, request
from flask_cors import CORS
import instaloader
import json
import time
from datetime import datetime, timedelta
import os
import logging
from functools import wraps

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

app = Flask(__name__)
CORS(app)

# Initialize Instaloader with session
L = instaloader.Instaloader(
    download_pictures=False,
    download_videos=False,
    download_video_thumbnails=False,
    download_geotags=False,
    download_comments=False,
    save_metadata=False,
    compress_json=False,
    quiet=True
)

# Configuration
CACHE_FILE = 'instagram_cache.json'
CACHE_DURATION_MINUTES = 30
MAX_RETRIES = 3
RETRY_DELAY = 5

# Enhanced username list with more diverse profiles
USERNAMES = [
    # Celebrities & Athletes
    'instagram',
    'cristiano',
    'leomessi',
    'selenagomez',
    'therock',
    'kyliejenner',
    'arianagrande',
    'kimkardashian',
    'beyonce',
    'justinbieber',
    
    # Brands & Organizations
    'nike',
    'natgeo',
    'nasa',
    'redbull',
    'spotify',
    
    # Custom usernames (replace with your targets)
    'tarakeshwar_bikumandla',
    'anshsaxenna',
]

# Global cache
cache = {
    'profiles': [],
    'last_update': None,
    'fetch_count': 0,
    'errors': []
}

def load_cache():
    """Load cache from file if exists and valid"""
    try:
        if os.path.exists(CACHE_FILE):
            with open(CACHE_FILE, 'r') as f:
                data = json.load(f)
                
            # Check if cache is still valid
            if data.get('last_update'):
                last_update = datetime.fromisoformat(data['last_update'])
                if datetime.now() - last_update < timedelta(minutes=CACHE_DURATION_MINUTES):
                    logger.info(f"✓ Loaded {len(data['profiles'])} profiles from cache")
                    return data
                else:
                    logger.info("Cache expired, will fetch fresh data")
        
    except Exception as e:
        logger.error(f"Error loading cache: {e}")
    
    return None

def save_cache(data):
    """Save cache to file"""
    try:
        with open(CACHE_FILE, 'w') as f:
            json.dump(data, f, indent=2)
        logger.info("✓ Cache saved to file")
    except Exception as e:
        logger.error(f"Error saving cache: {e}")

def rate_limit(func):
    """Decorator for rate limiting API calls"""
    @wraps(func)
    def wrapper(*args, **kwargs):
        time.sleep(2)  # 2 second delay between requests
        return func(*args, **kwargs)
    return wrapper

@rate_limit
def fetch_profile_data(username, retry_count=0):
    """Fetch data for a single Instagram profile with retry logic"""
    try:
        logger.info(f" Fetching: {username} (attempt {retry_count + 1}/{MAX_RETRIES})")
        
        profile = instaloader.Profile.from_username(L.context, username)
        
        data = {
            'username': profile.username,
            'fullName': profile.full_name or profile.username,
            'followers': profile.followers,
            'following': profile.followees,
            'posts': profile.mediacount,
            'profilePic': profile.profile_pic_url,
            'isVerified': profile.is_verified,
            'biography': profile.biography[:100] if profile.biography else '',
            'externalUrl': profile.external_url or '',
            'isPrivate': profile.is_private,
            'isBusiness': profile.is_business_account,
            'category': profile.business_category_name if hasattr(profile, 'business_category_name') else '',
            'fetchedAt': datetime.now().isoformat(),
            'engagementRate': calculate_engagement_rate(profile)
        }
        
        logger.info(f"✓ Success: @{username} - {data['followers']:,} followers")
        return data, None
        
    except instaloader.exceptions.ProfileNotExistsException:
        error = f"Profile '{username}' does not exist"
        logger.error(f"✗ {error}")
        return None, error
        
    except instaloader.exceptions.ConnectionException as e:
        error = f"Connection error for '{username}'"
        logger.error(f"✗ {error}: {str(e)}")
        
        # Retry logic
        if retry_count < MAX_RETRIES - 1:
            logger.info(f" Retrying in {RETRY_DELAY} seconds...")
            time.sleep(RETRY_DELAY)
            return fetch_profile_data(username, retry_count + 1)
        
        return None, error
        
    except Exception as e:
        error = f"Error fetching '{username}': {str(e)}"
        logger.error(f"✗ {error}")
        return None, error

def calculate_engagement_rate(profile):
    """Calculate estimated engagement rate"""
    try:
        if profile.followers == 0:
            return 0.0
        
        # Simple ratio-based engagement metric
        engagement = (profile.followees / profile.followers) * 100
        return round(engagement, 2)
    except:
        return 0.0

def update_cache_data():
    """Update cache with fresh Instagram data"""
    logger.info("\n" + "="*60)
    logger.info(" STARTING INSTAGRAM DATA FETCH")
    logger.info("="*60)
    
    profiles = []
    errors = []
    start_time = time.time()
    
    for idx, username in enumerate(USERNAMES, 1):
        logger.info(f"\n[{idx}/{len(USERNAMES)}] Processing: @{username}")
        
        profile_data, error = fetch_profile_data(username)
        
        if profile_data:
            profiles.append(profile_data)
        elif error:
            errors.append({'username': username, 'error': error})
    
    # Sort by followers (descending)
    profiles.sort(key=lambda x: x['followers'], reverse=True)
    
    cache['profiles'] = profiles
    cache['last_update'] = datetime.now().isoformat()
    cache['fetch_count'] += 1
    cache['errors'] = errors
    
    elapsed_time = time.time() - start_time
    
    logger.info("\n" + "="*60)
    logger.info(f" FETCH COMPLETE!")
    logger.info(f"   Success: {len(profiles)}/{len(USERNAMES)} profiles")
    logger.info(f"   Failed:  {len(errors)} profiles")
    logger.info(f"   Time:    {elapsed_time:.2f} seconds")
    logger.info("="*60 + "\n")
    
    # Save to file
    save_cache(cache)
    
    return profiles, errors

@app.route('/', methods=['GET'])
def index():
    """Root endpoint with API documentation"""
    return jsonify({
        'name': 'Instagram Profile Analytics API',
        'version': '2.0.0',
        'description': 'Enhanced backend with caching, rate limiting, and error handling',
        'endpoints': {
            'GET /': 'API documentation',
            'GET /api/health': 'Health check',
            'GET /api/profiles': 'Get all cached profiles',
            'POST /api/refresh': 'Force refresh all profiles',
            'GET /api/stats': 'Get analytics statistics'
        },
        'cache_info': {
            'profiles_cached': len(cache['profiles']),
            'last_update': cache['last_update'],
            'total_fetches': cache['fetch_count']
        },
        'status': 'healthy'
    })

@app.route('/api/health', methods=['GET'])
def health_check():
    """Health check endpoint"""
    return jsonify({
        'status': 'healthy',
        'profiles_cached': len(cache['profiles']),
        'last_update': cache['last_update'],
        'cache_age_minutes': get_cache_age_minutes(),
        'errors_count': len(cache.get('errors', []))
    })

@app.route('/api/profiles', methods=['GET'])
def get_profiles():
    """Get all profiles with optional filtering"""
    verified_only = request.args.get('verified', '').lower() == 'true'
    min_followers = int(request.args.get('min_followers', 0))
    
    profiles = cache['profiles']
    
    # Apply filters
    if verified_only:
        profiles = [p for p in profiles if p.get('isVerified')]
    
    if min_followers > 0:
        profiles = [p for p in profiles if p.get('followers', 0) >= min_followers]
    
    return jsonify({
        'success': True,
        'data': profiles,
        'last_update': cache['last_update'],
        'total': len(profiles),
        'cache_age_minutes': get_cache_age_minutes(),
        'errors': cache.get('errors', [])
    })

@app.route('/api/refresh', methods=['POST'])
def refresh_profiles():
    """Force refresh all profiles"""
    logger.info(" Manual refresh requested")
    
    profiles, errors = update_cache_data()
    
    return jsonify({
        'success': True,
        'message': f'Successfully refreshed {len(profiles)} profiles',
        'data': profiles,
        'last_update': cache['last_update'],
        'errors': errors,
        'stats': {
            'successful': len(profiles),
            'failed': len(errors),
            'total_requested': len(USERNAMES)
        }
    })

@app.route('/api/stats', methods=['GET'])
def get_stats():
    """Get analytics statistics"""
    profiles = cache['profiles']
    
    if not profiles:
        return jsonify({
            'success': False,
            'message': 'No data available'
        })
    
    total_followers = sum(p.get('followers', 0) for p in profiles)
    total_following = sum(p.get('following', 0) for p in profiles)
    total_posts = sum(p.get('posts', 0) for p in profiles)
    verified_count = sum(1 for p in profiles if p.get('isVerified'))
    
    avg_followers = total_followers / len(profiles)
    avg_posts = total_posts / len(profiles)
    
    top_5 = sorted(profiles, key=lambda x: x.get('followers', 0), reverse=True)[:5]
    
    return jsonify({
        'success': True,
        'stats': {
            'total_profiles': len(profiles),
            'verified_profiles': verified_count,
            'total_followers': total_followers,
            'total_following': total_following,
            'total_posts': total_posts,
            'avg_followers': round(avg_followers, 2),
            'avg_posts': round(avg_posts, 2),
            'top_5_profiles': [
                {'username': p['username'], 'followers': p['followers']}
                for p in top_5
            ]
        },
        'last_update': cache['last_update']
    })

def get_cache_age_minutes():
    """Get cache age in minutes"""
    if not cache['last_update']:
        return None
    
    last_update = datetime.fromisoformat(cache['last_update'])
    age = datetime.now() - last_update
    return round(age.total_seconds() / 60, 1)

if __name__ == '__main__':
    print("\n" + "="*60)
    print(" INSTAGRAM ANALYTICS BACKEND SERVER")
    print("="*60)
    
    # Try to load from cache first
    cached_data = load_cache()
    if cached_data:
        cache.update(cached_data)
        logger.info(f"✓ Using cached data ({get_cache_age_minutes()} minutes old)")
    else:
        # Fetch fresh data
        logger.info("  No valid cache found, fetching fresh data...")
        update_cache_data()
    
    # Start Flask server
    port = int(os.environ.get('PORT', 5000))
    
    print("\n" + "="*60)
    print(f"✓ Server running on http://localhost:{port}")
    print(f"✓ API documentation: http://localhost:{port}/")
    print(f"✓ Profiles endpoint: http://localhost:{port}/api/profiles")
    print(f"✓ Health check: http://localhost:{port}/api/health")
    print("="*60 + "\n")
    
    app.run(host='0.0.0.0', port=port, debug=False)