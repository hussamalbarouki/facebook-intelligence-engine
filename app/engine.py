"""Facebook extraction adapters, with fail-closed handling for unreadable posts.

Legacy facebook-scraper parses mobile HTML; the preferred GraphQL adapter reads
Facebook's newer UI. Neither adapter guarantees complete data or stable access.
"""
from __future__ import annotations

import itertools
import logging
import os
import re
import tempfile
from datetime import date, datetime, timezone
from urllib.parse import parse_qs, urlparse

from .facebook_session import inspect_session, configure_facebook_session, apply_facebook_cookies

log = logging.getLogger('fb-engine.adapter')


class ExtractionError(RuntimeError):
    """A non-sensitive code safe for job status and client display."""
    def __init__(self, code: str):
        self.code = code
        super().__init__(code)


def validate_facebook_url(url: str) -> str:
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
    if len(url) > 2048:
        raise ValueError('URL too long')
    return url


def parse_post_reference(url: str) -> tuple[str, str] | None:
    """Parse IDs only from well-known post URL patterns, never from profile IDs.

    Share URLs are intentionally not guessed: their opaque IDs aren't post IDs.
    """
    parsed = urlparse(validate_facebook_url(url))
    qs = parse_qs(parsed.query)
    for key in ('story_fbid', 'fbid'):
        value = qs.get(key, [None])[0]
        if isinstance(value, str):
            if re.fullmatch(r'\d{5,30}', value):
                return ('id', value)
            if re.fullmatch(r'pfbid[a-zA-Z0-9]{10,160}', value):
                return ('pfbid', value)
    if parsed.path.rstrip('/') in ('/watch', '/watch/'):
        value = qs.get('v', [None])[0]
        if isinstance(value, str) and re.fullmatch(r'\d{5,30}', value):
            return ('id', value)
    segs = [s for s in parsed.path.split('/') if s]
    for i, seg in enumerate(segs[:-1]):
        if seg.lower() in {'posts','permalink','videos','reel'}:
            value = segs[i+1]
            if re.fullmatch(r'\d{5,30}', value):
                return ('id', value)
            if re.fullmatch(r'pfbid[a-zA-Z0-9]{10,160}', value):
                return ('pfbid', value)
    if segs and re.fullmatch(r'pfbid[a-zA-Z0-9]{10,160}', segs[-1]):
        return ('pfbid', segs[-1])
    return None



def is_share_link(url: str) -> bool:
    """Opaque /share/ URLs do not identify a GraphQL post on their own."""
    path=urlparse(validate_facebook_url(url)).path.lower()
    return path.startswith('/share/')


def resolve_share_link(url: str, cookies_file: str) -> tuple[str, tuple[str,str]]:
    """Resolve Facebook-owned share URLs without blindly following redirects.

    Stop at the first unambiguous post link. Other hosts and arbitrary
    redirects are rejected; never use an external redirect as an HTTP target.
    """
    import html
    import json
    import requests
    from html.parser import HTMLParser
    from urllib.parse import urljoin
    from .facebook_session import apply_facebook_cookies, configure_facebook_session

    class PermalinkParser(HTMLParser):
        def __init__(self):
            super().__init__()
            self.urls=[]
        def handle_starttag(self, tag, attrs):
            data=dict(attrs)
            if tag == 'link' and 'canonical' in data.get('rel','').lower():
                self.urls.append(data.get('href',''))
            if tag == 'meta' and data.get('property','').lower() == 'og:url':
                self.urls.append(data.get('content',''))

    with open(cookies_file,encoding='utf-8') as f:
        cookie_data=json.load(f)
    with requests.Session() as session:
        configure_facebook_session(session)
        apply_facebook_cookies(session,cookie_data)
        current=url
        for _ in range(5):
            validate_facebook_url(current)
            reference=parse_post_reference(current)
            if reference is not None:
                return current,reference
            r=session.get(current,timeout=(5,18),allow_redirects=False)
            if 300 <= r.status_code < 400:
                location=r.headers.get('Location')
                if not location:
                    raise ExtractionError('FACEBOOK_SHARE_REDIRECT_MISSING')
                current=urljoin(current,location)
                validate_facebook_url(current)
                continue
            if r.status_code != 200:
                raise ExtractionError('FACEBOOK_SHARE_HTTP_ERROR')
            parser=PermalinkParser()
            parser.feed(r.text[:1000000])
            for target in parser.urls:
                if not target:
                    continue
                candidate=html.unescape(urljoin(current,target))
                try:
                    validate_facebook_url(candidate)
                    ref=parse_post_reference(candidate)
                except ValueError:
                    continue
                if ref:
                    return candidate,ref
            raise ExtractionError('FACEBOOK_SHARE_LINK_UNRESOLVED')
    raise ExtractionError('FACEBOOK_SHARE_REDIRECT_LIMIT')


def resolve_pfbid_numeric_id(ctx, url: str, pfbid: str) -> str:
    """Resolve from a permalink's redirect or a unique post_id close to PFBID.

    Do not select arbitrary post IDs from feed content: ambiguity is an error.
    """
    response=ctx.get(url)
    if getattr(response,'status_code',0) != 200:
        raise ExtractionError('FACEBOOK_POST_HTTP_ERROR')
    final_url=getattr(response,'url','') or ''
    try:
        reference=parse_post_reference(final_url)
        if reference and reference[0] == 'id':
            return reference[1]
    except ValueError:
        pass
    raw=getattr(response,'text','')
    if not isinstance(raw,str):
        raise ExtractionError('FACEBOOK_PFBID_UNRESOLVED')
    normalized=raw.replace('\\/','/').replace('\\"','"')
    candidates=set()
    key=re.compile(r'"(?:post_id|story_fbid|postId)"\s*:\s*"?(?P<id>\d{8,30})')
    for found in re.finditer(re.escape(pfbid),normalized):
        vicinity=normalized[max(0,found.start()-450):min(len(normalized),found.end()+450)]
        candidates.update(m.group('id') for m in key.finditer(vicinity))
    if len(candidates)==1:
        return next(iter(candidates))
    if len(candidates)>1:
        raise ExtractionError('FACEBOOK_PFBID_AMBIGUOUS')
    raise ExtractionError('FACEBOOK_PFBID_UNRESOLVED')


def _string(value):
    if isinstance(value, (datetime, date)):
        return value.isoformat()
    return str(value) if value is not None else None


def _person(p):
    if not isinstance(p, dict):
        return {'name': None, 'profile_url': None, 'type': None}
    return {'name':p.get('name') or p.get('username') or p.get('reactor_name'),
            'profile_url':p.get('link') or p.get('url') or p.get('profile_url'),
            'type':p.get('type') or p.get('reaction_type')}


def _comment(c):
    replies = c.get('replies') or []
    if not isinstance(replies, list):
        replies = list(itertools.islice(replies, 50))
    return {'id':c.get('comment_id'), 'name':c.get('commenter_name'),
            'profile_url':c.get('commenter_url'), 'text':c.get('comment_text'),
            'time':_string(c.get('comment_time')), 'url':c.get('comment_url'),
            'replies':[_comment(r) for r in replies if isinstance(r, dict)]}


def normalize_post(post, source_url, requested_comments, requested_reactors):
    raw_comments = post.get('comments_full') or []
    raw_reactors = post.get('reactors') or []
    if not isinstance(raw_comments, list):
        raw_comments = list(itertools.islice(raw_comments, requested_comments))
    if not isinstance(raw_reactors, list):
        raw_reactors = list(itertools.islice(raw_reactors, requested_reactors))
    comments = [_comment(c) for c in raw_comments if isinstance(c, dict)]
    reactors = [_person(p) for p in raw_reactors]
    return {
        'post': {'id':post.get('post_id'), 'url':post.get('post_url') or source_url,
                 'author':post.get('username'), 'text':post.get('text'), 'time':_string(post.get('time')),
                 'counts':{'comments':post.get('comments'),'likes':post.get('likes'),
                           'shares':post.get('shares'),'reactions_by_type':post.get('reactions')}},
        'comments':comments, 'reactors':reactors,
        'coverage':{'comments_returned':len(comments),'reactors_returned':len(reactors),
                    'comments_requested':requested_comments,'reactors_requested':requested_reactors,
                    'complete':False, 'adapter':'legacy-html',
                    'note':'Results can be partial; no claim of completeness.'}
    }


def _legacy_has_data(raw: dict, result: dict) -> bool:
    """Reject an empty shell returned when old HTML selectors no longer match."""
    return (raw.get('available') is not False and
            (bool(result['comments']) or bool(result['reactors']) or
             bool(raw.get('text')) or bool(raw.get('post_id')) or
             isinstance(raw.get('comments'), int) or isinstance(raw.get('likes'), int)))


def _legacy_scrape(url, comment_limit, reactor_limit, cookies_file):
    from facebook_scraper import get_posts
    opts={'comments':comment_limit or False, 'reactors':reactor_limit or False}
    kwargs={'post_urls':[url], 'options':opts, 'extra_info':True, 'timeout':40}
    if cookies_file:
        kwargs['cookies']=cookies_file
    post = next(iter(get_posts(**kwargs)), None)
    if not isinstance(post, dict) or not post or post.get('available') is False:
        raise ExtractionError('POST_NOT_READABLE')
    result=normalize_post(post,url,comment_limit,reactor_limit)
    if not _legacy_has_data(post,result):
        raise ExtractionError('POST_NOT_PARSED')
    return result


REACTION_TYPES={
    '1':'like','1635855486666999':'like',
    '2':'love','1678524932434102':'love',
    '3':'wow','478547315650144':'wow',
    '4':'haha','115940658764963':'haha',
    '7':'sorry','8':'angry','16':'care','613557422527858':'care'
}


def _iso_timestamp(value):
    if value is None:
        return None
    try:
        return datetime.fromtimestamp(int(value), timezone.utc).isoformat()
    except (ValueError,TypeError,OverflowError):
        return None


def _gql_comment(obj, include_replies=False, reply_budget=0):
    owner=obj.owner
    replies=[]
    if include_replies and reply_budget>0 and obj.reply_count:
        try:
            for child in itertools.islice(obj.get_replies(), min(int(obj.reply_count),reply_budget)):
                replies.append(_gql_comment(child))
        except Exception as exc:
            log.warning('GraphQL reply collection partial: %s',type(exc).__name__)
    return {'id':obj.id,'name':owner.name if owner else None,
            'profile_url':owner.url if owner else None,
            'text':obj.text,'time':_iso_timestamp(obj.created_time),
            'url':None,'replies':replies,'reply_count':obj.reply_count}


def _graphql_scrape(url, comment_limit, reactor_limit, cookies_file, reference):
    import facebook_gql_scraper as gql
    if not cookies_file:
        raise ExtractionError('FACEBOOK_COOKIES_REQUIRED')
    # The GraphQL library normally persists auth-derived fb_dtsg state. Keep it
    # in a temporary directory to avoid leaving secrets in persistent storage.
    with tempfile.TemporaryDirectory(prefix='fb-gql-state-') as tmp:
        # Operation discovery must use the requested post, not a hardcoded
        # unrelated celebrity post bundled into the third-party library.
        discovery_url=url
        class SessionAwareFacebookContext(gql.FacebookContext):
            def _load_cookies(self):
                # The upstream library converts the cookie array into a dict by
                # name, discarding browser domain/path scope and duplicates.
                import json as _json
                with open(self._cookies_file,encoding='utf-8') as file:
                    raw=_json.load(file)
                apply_facebook_cookies(self.session,raw)

            def __init__(self, **kwargs):
                super().__init__(**kwargs)
                configure_facebook_session(self.session)

            def _resolve_doc_id(self, operation_name, reference_page_url):
                # Keep the upstream discovery/cache machinery but point its
                # page-loading phase at the actual requested Facebook post.
                return super()._resolve_doc_id(operation_name, discovery_url)

            def get(self, resource_url):
                try:
                    return super().get(resource_url)
                except gql.SessionExpiredError:
                    from urllib.parse import urlsplit
                    host=urlsplit(resource_url).hostname or 'unknown'
                    stage='post' if resource_url == discovery_url else 'asset_or_reference'
                    # Never log Cookie/CSRF values or raw Facebook response.
                    log.warning('Facebook rejected session during GraphQL page discovery: stage=%s host=%s',
                                stage, host)
                    raise ExtractionError('FACEBOOK_SESSION_REJECTED_DURING_DISCOVERY') from None

            def _get_fb_dtsg(self):
                if self.fb_dtsg:
                    return self.fb_dtsg
                report, token = inspect_session(self.get)
                if not token:
                    statuses = {
                        'facebook_login_required':'FACEBOOK_SESSION_NOT_AUTHENTICATED',
                        'facebook_checkpoint':'FACEBOOK_CHECKPOINT_REQUIRED',
                        'facebook_access_restricted':'FACEBOOK_ACCESS_RESTRICTED',
                        'facebook_http_bad_request':'FACEBOOK_HTTP_400',
                        'facebook_connection_error':'FACEBOOK_CONNECTION_ERROR',
                    }
                    raise ExtractionError(statuses.get(report['status'],'FB_DTSG_UNAVAILABLE'))
                self.fb_dtsg=token
                self._save_state()
                return token

        ctx=SessionAwareFacebookContext(cookies_file=cookies_file,
                                        state_file=os.path.join(tmp,'state.json'),quiet=True)
        kind, identifier=reference
        log.info('Extracting Facebook post: reference_kind=%s',kind)
        if kind=='pfbid':
            try:
                post=gql.Post.from_pfbid(ctx,pfbid=identifier)
            except gql.PostNotFoundError:
                identifier=resolve_pfbid_numeric_id(ctx,url,identifier)
                post=gql.Post.from_post_id(ctx,post_id=identifier)
        else:
            post=gql.Post.from_post_id(ctx,post_id=identifier)
        comments=[]
        if comment_limit:
            for item in itertools.islice(post.get_comments(),comment_limit):
                comments.append(_gql_comment(item, include_replies=True, reply_budget=3))
        reactors=[]
        if reactor_limit:
            for reactor in itertools.islice(post.get_reactors(),reactor_limit):
                p=reactor.profile
                reactors.append({'name':p.name if p else None,
                                 'profile_url':p.url if p else None,
                                 'type':REACTION_TYPES.get(str(reactor.reaction_type_id),
                                                          str(reactor.reaction_type_id or 'unknown'))})
        owner=post.owner
        breakdown=post.top_reaction_breakdown or []
        reaction_types={str(x.get('name','')).lower():x.get('count') for x in breakdown if isinstance(x,dict)}
        return {'post':{'id':post.id,'url':post.url or url,
                        'author':owner.name if owner else None,
                        'text':post.text,'time':_iso_timestamp(post.creation_time),
                        'counts':{'comments':post.comments_count,'likes':post.reaction_count,
                                  'shares':post.share_count,'reactions_by_type':reaction_types}},
                'comments':comments,'reactors':reactors,
                'coverage':{'comments_returned':len(comments),'reactors_returned':len(reactors),
                            'comments_requested':comment_limit,'reactors_requested':reactor_limit,
                            'complete':False,'adapter':'graphql',
                            'note':'Names and comments may be restricted or incomplete.'}}


def _has_requested_interactions(result, comments, reactors):
    # Reading post metadata is not the same as successfully extracting names.
    if comments==0 and reactors==0:
        return True
    returned=bool((comments and result['comments']) or (reactors and result['reactors']))
    counts=result.get('post',{}).get('counts',{})
    announced=[]
    if comments: announced.append(counts.get('comments'))
    if reactors: announced.append(counts.get('likes'))
    if returned:
        return True
    # A genuinely empty post can have zero interactions, but never assume null
    # means zero or that a summary with a positive count is a successful extract.
    return (len(announced)>0 and all(isinstance(x,(int,float)) and x==0 for x in announced))


def scrape_post(url, comment_limit, reactor_limit, cookies_file=None):
    """Prefer GraphQL with cookies; use legacy HTML only as a fallback.

    All-empty unreadable results fail with an explicit error instead of being
    shown in PHP as a successful extraction of zero comments and zero likes.
    """
    reference=parse_post_reference(url)
    attempted=[]
    last_code='POST_URL_UNSUPPORTED' if reference is None else 'POST_NOT_PARSED'
    resolved_url=url
    if cookies_file and not reference and is_share_link(url):
        try:
            resolved_url,reference=resolve_share_link(url,cookies_file)
            log.info('Opaque Facebook share URL resolved: kind=%s',reference[0])
        except ExtractionError as exc:
            attempted.append('share-link-unresolved')
            last_code=exc.code
        except Exception as exc:
            log.warning('Facebook share link resolution failed: %s',type(exc).__name__)
            attempted.append('share-link-failed')
            last_code='FACEBOOK_SHARE_LINK_UNRESOLVED'
    if cookies_file and reference:
        try:
            result=_graphql_scrape(resolved_url,comment_limit,reactor_limit,cookies_file,reference)
            if _has_requested_interactions(result,comment_limit,reactor_limit):
                return result
            attempted.append('graphql-empty')
            last_code='NO_INTERACTIONS_EXTRACTED'
        except ExtractionError as exc:
            log.warning('GraphQL session bootstrap or extraction failed: %s',exc.code)
            attempted.append('graphql-'+exc.code.lower())
            last_code=exc.code
        except Exception as exc:
            reason = type(exc).__name__
            log.warning('GraphQL adapter failed: %s', reason)
            if reason == 'SessionExpiredError':
                attempted.append('graphql-session-rejected')
                last_code='FACEBOOK_SESSION_REJECTED_ON_GRAPHQL'
            elif reason == 'PostNotFoundError':
                attempted.append('graphql-post-unresolved')
                last_code='GRAPHQL_POST_NOT_RESOLVED'
            else:
                attempted.append('graphql-failed')
                last_code='GRAPHQL_EXTRACT_FAILED'
    try:
        result=_legacy_scrape(resolved_url,comment_limit,reactor_limit,cookies_file)
        if _has_requested_interactions(result,comment_limit,reactor_limit):
            return result
        attempted.append('legacy-empty')
        last_code='NO_INTERACTIONS_EXTRACTED'
    except Exception as exc:
        log.warning('Legacy HTML adapter failed: %s',type(exc).__name__)
        attempted.append('legacy-failed')
        if not attempted[:-1]:
            last_code='POST_NOT_PARSED'
    log.warning('Post extraction failed after adapters: %s', ','.join(attempted))
    raise ExtractionError(last_code)