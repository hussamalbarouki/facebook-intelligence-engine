"""Adapter for kevinzg/facebook-scraper. Replace this file for a future engine."""
from datetime import date, datetime
from urllib.parse import urlparse


def validate_facebook_url(url: str) -> str:
    """Validate before handing an URL to third-party scraper code."""
    url = url.strip()
    parsed = urlparse(url)
    host = (parsed.hostname or '').lower().rstrip('.')
    if parsed.scheme != 'https' or host not in {
        'facebook.com', 'www.facebook.com', 'm.facebook.com',
        'mbasic.facebook.com', 'web.facebook.com', 'fb.com', 'www.fb.com'
    } or parsed.username or parsed.password or parsed.port not in (None, 443):
        raise ValueError('Only direct HTTPS Facebook post URLs are allowed')
    if not parsed.path or parsed.path == '/':
        raise ValueError('A post URL is required')
    if len(url) > 4096:
        raise ValueError('URL too long')
    return url


def _string(value):
    if isinstance(value, (datetime, date)):
        return value.isoformat()
    return str(value) if value is not None else None


def _person(p):
    if not isinstance(p, dict):
        return {'name': None, 'profile_url': None, 'type': None}
    return {
        'name': p.get('name') or p.get('username') or p.get('reactor_name'),
        'profile_url': p.get('link') or p.get('url') or p.get('profile_url'),
        'type': p.get('type') or p.get('reaction_type')
    }


def _comment(c):
    replies = c.get('replies') or []
    if not isinstance(replies, list):
        # Some versions return a generator. Materialize it for a consistent API.
        replies = list(replies)
    return {
        'id': c.get('comment_id'),
        'name': c.get('commenter_name'),
        'profile_url': c.get('commenter_url'),
        'text': c.get('comment_text'),
        'time': _string(c.get('comment_time')),
        'url': c.get('comment_url'),
        'replies': [_comment(r) for r in replies if isinstance(r, dict)]
    }


def normalize_post(post, source_url, requested_comments, requested_reactors):
    raw_comments = post.get('comments_full') or []
    raw_reactors = post.get('reactors') or []
    if not isinstance(raw_comments, list):
        raw_comments = list(raw_comments)
    if not isinstance(raw_reactors, list):
        raw_reactors = list(raw_reactors)
    comments = [_comment(c) for c in raw_comments if isinstance(c, dict)]
    reactors = [_person(p) for p in raw_reactors]
    return {
        'post': {
            'id': post.get('post_id'),
            'url': post.get('post_url') or source_url,
            'author': post.get('username'),
            'text': post.get('text'),
            'time': _string(post.get('time')),
            'counts': {
                'comments': post.get('comments'),
                'likes': post.get('likes'),
                'shares': post.get('shares'),
                'reactions_by_type': post.get('reactions')
            }
        },
        'comments': comments,
        'reactors': reactors,
        'coverage': {
            'comments_returned': len(comments),
            'reactors_returned': len(reactors),
            'comments_requested': requested_comments,
            'reactors_requested': requested_reactors,
            'complete': False,
            'note': 'Counts and lists may be partial or unavailable; completeness is not verified.'
        }
    }


def scrape_post(url, comment_limit, reactor_limit, cookies_file=None):
    from facebook_scraper import get_posts
    options = {'comments': comment_limit if comment_limit else False,
               'reactors': reactor_limit if reactor_limit else False}
    kwargs = {'post_urls': [url], 'options': options, 'extra_info': True, 'timeout': 40}
    if cookies_file:
        kwargs['cookies'] = cookies_file
    post = next(iter(get_posts(**kwargs)), None)
    if not post or post.get('available') is False:
        raise RuntimeError('Post unavailable or Facebook blocked extraction')
    return normalize_post(post, url, comment_limit, reactor_limit)