#!/usr/bin/env python

import cookielib
import json
import oauth2 as oauth
import urllib
import urllib2
import urlparse

REQUEST_TOKEN_URL = 'https://sso.openx.com/api/index/initiate'
ACCESS_TOKEN_URL = 'https://sso.openx.com/api/index/token'
AUTHORIZATION_URL = 'https://sso.openx.com/login/process'
API_PATH = '/ox/3.0'
HTTP_METHOD_OVERRIDES = ['DELETE', 'PUT']

class OX3APIClient(object):
    
    def __init__(self, domain, realm, consumer_key, consumer_secret,
                    callback_url='oob',
                    request_token_url=REQUEST_TOKEN_URL,
                    access_token_url=ACCESS_TOKEN_URL,
                    authorization_url=AUTHORIZATION_URL,
                    api_path=API_PATH):
        """
        
        domain -- Your UI domain. The API is accessed off this domain.
        realm -- Your sso realm. While not necessary for all OAuth 
            implementations, it is a requirement for OpenX Enterprise
        consumer_key -- Your consumer key.
        consumer_secret -- Your consumer secret.
        callback_url -- Callback URL to redirect to on successful authorization.
            We default to 'oob' for headless login.
        request_token -- Only override for debugging.
        access_token -- Only override for debugging.
        authorization_url -- Only override for debugging.
        api_path -- Only override for debugging.
        """
        self.domain = domain
        self.realm = realm
        self.consumer_key = consumer_key
        self.consumer_secret = consumer_secret
        self.request_token_url = request_token_url
        self.access_token_url = access_token_url
        self.authorization_url = authorization_url
        self.callback_url = callback_url
        self.api_path = api_path
        
        # You shouldn't need to access the oauth2 consumer and token objects
        # directly so we'll keep them "private".
        self._consumer = oauth.Consumer(self.consumer_key, self.consumer_secret)
        self._token = oauth.Token('', '')
        
        # Similarly you probably won't need to access the cookie jar directly,
        # so it is private as well.
        self._cookie_jar = cookielib.LWPCookieJar()
        opener = urllib2.build_opener(urllib2.HTTPCookieProcessor(self._cookie_jar))
        urllib2.install_opener(opener)
    
    def _sign_request(self, req):
        """Utility method to sign a request."""
        parameters = {'oauth_callback': self.callback_url}
        headers = req.headers
        data = req.data
        
        # Add any (POST) data to the parameters to be signed in the OAuth
        # request as well as store 'stringified' copy for the request's body.
        if data:
            parameters.update(data)
            data = urllib.urlencode(data)
        
        # Create a temporary oauth2 Request object and sign it so we can steal
        # the Authorization header.
        oauth_req = oauth.Request.from_consumer_and_token(
            consumer=self._consumer,
            token=self._token,
            http_method=req.get_method(),
            http_url=req.get_full_url(),
            parameters=parameters,
            is_form_encoded=True)
        
        oauth_req.sign_request(
            oauth.SignatureMethod_HMAC_SHA1(),
            self._consumer,
            self._token)
        
        # Update or original requests headers to include the OAuth Authorization
        # header and return it.
        req.headers.update(oauth_req.to_header(realm=self.realm))
        return urllib2.Request(req.get_full_url(), headers=req.headers, data=data)
    
    def request(self, url, method='GET', headers={}, data=None, sign=False):
        """Helper method to make a (optionally OAuth signed) HTTP request."""
        
        # Since we are using a urllib2.Request object we need to assign a value
        # other than None to "data" in order to make the request a POST request,
        # even if there is no data to post.
        if method == 'POST':
            data = data if data else ''
        
        req = urllib2.Request(url, headers=headers, data=data)
        
        # We need to set the request's get_method function to return a HTTP
        # method for any values other than GET or POST.
        if method in HTTP_METHOD_OVERRIDES:
            req.get_method = lambda: method
        
        if sign:
            req = self._sign_request(req)
        
        return urllib2.urlopen(req)
    
    def fetch_request_token(self):
        """Helper method to fetch and set request token.
        
        Returns oauth2.Token object.
        """
        res = self.request(url=self.request_token_url, method='POST', sign=True)
        self._token = oauth.Token.from_string(res.read())
        return self._token
    
    def authorize_token(self, email, password):
        """Helper method to authorize."""
        data = {
            'email': email,
            'password': password,
            'oauth_token': self._token.key}
        
        res = self.request(
                url=self.authorization_url,
                method='POST',
                data=data,
                sign=True)
        
        verifier = urlparse.parse_qs(res.read())['oauth_verifier'][0]
        self._token.set_verifier(verifier)
    
    def fetch_access_token(self):
        """Helper method to fetch and set access token.
        
        Returns oauth2.Token object.
        """
        res = self.request(url=self.access_token_url, method='POST', sign=True)
        self._token = oauth.Token.from_string(res.read())
        return self._token
    
    def validate_session(self):
        """Validate an API session."""
        
        # We need to store our access token as the openx3_access_token cookie.
        # This cookie will be passed to all future API requests.
        cookie = cookielib.Cookie(
            version=0,
            name='openx3_access_token',
            value=self._token.key,
            port=None,
            port_specified=False,
            domain=self.domain,
            domain_specified=True,
            domain_initial_dot=False,
            path='/',
            path_specified=True,
            secure=False,
            expires=None,
            discard=False,
            comment=None,
            comment_url=None,
            rest={})
        
        self._cookie_jar.set_cookie(cookie)
        
        url = 'http://'+self.domain+API_PATH+'/a/session/validate'
        res = self.request(url=url, method='PUT')
        return res.read()
    
    def _resolve_url(self, url):
        """"""
        parse_res = urlparse.urlparse(url)
        if not parse_res.scheme:
            url ='http://%s%s%s' % (self.domain, API_PATH, parse_res.path)
        
        return url
    
    def get(self, url, data=None):
        """"""
        res = self.request(self._resolve_url(url), method='GET', data=data)
        return json.loads(res.read())
    
    def post(self, url, data=None):
        """"""
        res = self.request(self._resolve_url(url), method='POST', data=data)
        return json.loads(res.read())
    
    def delete(self, url):
        """"""
        res = self.request(self._resolve_url(url), method='DELETE')
        return json.loads(res.read())
    
