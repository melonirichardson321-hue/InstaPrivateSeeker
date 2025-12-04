from flask import Flask, render_template, request, jsonify, session, redirect, url_for
from flask_sqlalchemy import SQLAlchemy
from datetime import datetime
import requests
import json
import re
import os
import time
from functools import wraps

app = Flask(__name__)
app.secret_key = 'insta_seeker_2024_nitish_enthem_secret'
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///insta_seeker.db'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
db = SQLAlchemy(app)

# Database Models
class SearchHistory(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(100), nullable=False)
    ip_address = db.Column(db.String(50))
    user_agent = db.Column(db.String(200))
    timestamp = db.Column(db.DateTime, default=datetime.utcnow)
    is_private = db.Column(db.Boolean, default=False)

class AdminUser(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(50), unique=True, nullable=False)
    password = db.Column(db.String(100), nullable=False)

# Admin login decorator
def admin_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if not session.get('admin_logged_in'):
            return redirect(url_for('admin_login'))
        return f(*args, **kwargs)
    return decorated_function

class InstagramPrivateViewer:
    def __init__(self):
        self.session = requests.Session()
        self.session.headers.update({
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
            'Accept': '*/*',
            'Accept-Language': 'en-US,en;q=0.9',
            'Accept-Encoding': 'gzip, deflate, br',
            'Connection': 'keep-alive',
            'Upgrade-Insecure-Requests': '1',
        })
        
    def get_private_profile(self, username):
        """Get private Instagram profile data"""
        try:
            # Try multiple methods
            methods = [
                self._method_api,
                self._method_html,
                self._method_graphql,
            ]
            
            for method in methods:
                result = method(username)
                if result.get('success'):
                    return result
            
            return {'success': False, 'error': 'Unable to access profile. Try again later.'}
            
        except Exception as e:
            return {'success': False, 'error': f'Error: {str(e)}'}
    
    def _method_api(self, username):
        """Method 1: Instagram API"""
        try:
            api_url = f"https://i.instagram.com/api/v1/users/web_profile_info/?username={username}"
            headers = {
                'X-IG-App-ID': '936619743392459',
                'X-Requested-With': 'XMLHttpRequest',
            }
            
            response = self.session.get(api_url, headers=headers, timeout=10)
            if response.status_code == 200:
                data = response.json()
                return self._parse_api_data(data)
        except:
            pass
        return {'success': False}
    
    def _method_html(self, username):
        """Method 2: HTML Scraping"""
        try:
            url = f"https://www.instagram.com/{username}/"
            response = self.session.get(url, timeout=10)
            
            if response.status_code == 200:
                # Extract JSON data from HTML
                patterns = [
                    r'window\._sharedData\s*=\s*({.+?});</script>',
                    r'{\\"config\\":.+?};',
                    r'"profile_page_([0-9]+)":({.+?})',
                ]
                
                for pattern in patterns:
                    match = re.search(pattern, response.text, re.DOTALL)
                    if match:
                        try:
                            json_str = match.group(1)
                            json_str = json_str.replace('\\"', '"').replace('\\\\', '\\')
                            data = json.loads(json_str)
                            return self._parse_html_data(data, username)
                        except:
                            continue
        except:
            pass
        return {'success': False}
    
    def _method_graphql(self, username):
        """Method 3: GraphQL API"""
        try:
            url = "https://www.instagram.com/graphql/query/"
            params = {
                'query_hash': 'c9100bf9110dd6361671f113dd02e7d6',
                'variables': json.dumps({
                    'username': username,
                    'fetch_mutual': False,
                    'include_chaining': False,
                    'include_reel': True,
                    'include_suggested_users': False,
                    'include_logged_out_extras': False,
                    'include_highlight_reels': True,
                })
            }
            
            response = self.session.get(url, params=params, timeout=10)
            if response.status_code == 200:
                data = response.json()
                return self._parse_graphql_data(data)
        except:
            pass
        return {'success': False}
    
    def _parse_api_data(self, data):
        """Parse API response"""
        try:
            user = data['data']['user']
            
            profile_data = {
                'username': user['username'],
                'full_name': user['full_name'],
                'bio': user['biography'],
                'followers': user['edge_followed_by']['count'],
                'following': user['edge_follow']['count'],
                'posts_count': user['edge_owner_to_timeline_media']['count'],
                'profile_pic': user['profile_pic_url_hd'],
                'is_private': user['is_private'],
                'is_verified': user['is_verified'],
                'external_url': user['external_url'],
                'category': user.get('category_name', ''),
            }
            
            # Get posts if available
            posts = []
            if 'edge_owner_to_timeline_media' in user:
                for edge in user['edge_owner_to_timeline_media']['edges'][:9]:
                    node = edge['node']
                    post = {
                        'id': node['id'],
                        'type': 'REELS' if node.get('is_video') else 'POST',
                        'thumbnail': node['display_url'],
                        'video_url': node.get('video_url'),
                        'shortcode': node['shortcode'],
                        'caption': node['edge_media_to_caption']['edges'][0]['node']['text'] if node['edge_media_to_caption']['edges'] else '',
                        'likes': node['edge_media_preview_like']['count'],
                        'comments': node['edge_media_to_comment']['count'],
                        'is_video': node.get('is_video', False),
                    }
                    posts.append(post)
            
            profile_data['posts'] = posts
            
            return {
                'success': True,
                'data': profile_data
            }
            
        except Exception as e:
            return {'success': False, 'error': f'Parse error: {str(e)}'}
    
    def _parse_html_data(self, data, username):
        """Parse HTML response"""
        try:
            # Find user data in nested JSON
            def find_user_data(obj):
                if isinstance(obj, dict):
                    if 'graphql' in obj and 'user' in obj['graphql']:
                        return obj['graphql']['user']
                    for key, value in obj.items():
                        result = find_user_data(value)
                        if result:
                            return result
                elif isinstance(obj, list):
                    for item in obj:
                        result = find_user_data(item)
                        if result:
                            return result
                return None
            
            user = find_user_data(data)
            if user:
                return self._parse_api_data({'data': {'user': user}})
        except:
            pass
        return {'success': False}
    
    def _parse_graphql_data(self, data):
        """Parse GraphQL response"""
        try:
            user = data['data']['user']
            return self._parse_api_data({'data': {'user': user}})
        except:
            return {'success': False}

# Create database tables
with app.app_context():
    db.create_all()
    # Add default admin user
    if not AdminUser.query.filter_by(username='admin@access').first():
        admin = AdminUser(
            username='admin@access',
            password='enthem@nitish#'
        )
        db.session.add(admin)
        db.session.commit()

scraper = InstagramPrivateViewer()

# Routes
@app.route('/')
def home():
    return render_template('index.html')

@app.route('/search', methods=['POST'])
def search_profile():
    username = request.json.get('username', '').strip().lower()
    
    if not username:
        return jsonify({'success': False, 'error': 'Please enter Instagram username'})
    
    # Save to search history
    search = SearchHistory(
        username=username,
        ip_address=request.remote_addr,
        user_agent=request.user_agent.string
    )
    db.session.add(search)
    db.session.commit()
    
    # Get profile data
    result = scraper.get_private_profile(username)
    
    # Update if profile is private
    if result.get('success') and result['data'].get('is_private'):
        search.is_private = True
        db.session.commit()
    
    return jsonify(result)

@app.route('/get_posts/<username>')
def get_posts(username):
    """Get detailed posts data"""
    try:
        result = scraper.get_private_profile(username)
        if result['success']:
            posts = result['data'].get('posts', [])
            return jsonify({'success': True, 'posts': posts})
    except:
        pass
    return jsonify({'success': False, 'posts': []})

@app.route('/admin/login', methods=['GET', 'POST'])
def admin_login():
    if request.method == 'POST':
        username = request.form.get('username')
        password = request.form.get('password')
        
        admin = AdminUser.query.filter_by(
            username=username, 
            password=password
        ).first()
        
        if admin:
            session['admin_logged_in'] = True
            return redirect(url_for('admin_dashboard'))
        else:
            return render_template('admin_login.html', error='Invalid credentials')
    
    return render_template('admin_login.html')

@app.route('/admin/dashboard')
@admin_required
def admin_dashboard():
    # Get search statistics
    searches = SearchHistory.query.order_by(SearchHistory.timestamp.desc()).all()
    total_searches = len(searches)
    
    # Get unique IPs
    unique_ips = db.session.query(SearchHistory.ip_address).distinct().count()
    
    # Get today's searches
    today = datetime.now().date()
    today_searches = SearchHistory.query.filter(
        db.func.date(SearchHistory.timestamp) == today
    ).count()
    
    # Get private profile searches
    private_searches = SearchHistory.query.filter_by(is_private=True).count()
    
    return render_template('admin_dashboard.html',
                         searches=searches[:50],
                         total_searches=total_searches,
                         unique_ips=unique_ips,
                         today_searches=today_searches,
                         private_searches=private_searches)

@app.route('/admin/logout')
def admin_logout():
    session.pop('admin_logged_in', None)
    return redirect(url_for('home'))

if __name__ == '__main__':
    app.run(debug=True, host='0.0.0.0', port=5000)