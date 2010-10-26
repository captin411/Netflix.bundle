import cgi, urllib, httplib, sys
from PMS import Log
import oauth, re

NETFLIX_SERVER = 'api.netflix.com'
NETFLIX_PORT   = 80

NETFLIX_VERSION = '1.5'

REQUEST_TOKEN_URL = 'http://api.netflix.com/oauth/request_token'
ACCESS_TOKEN_URL  = 'http://api.netflix.com/oauth/access_token'
AUTHORIZATION_URL = 'https://api-user.netflix.com/oauth/login'
API_URL = 'http://api.netflix.com/'

CONSUMER_KEY    = 'nfeafbf2hpdnyfvr5dd32ka6'
CONSUMER_SECRET = 'bBsa6TqYab'

SORT_ALPHA = 'alphabetical'
SORT_DATE  = 'date_added'
SORT_QUEUE = 'queue_sequence'

RATING_NO_OPINION     = 'no_opinion'
RATING_NOT_INTERESTED = 'not_interested'
#
def locallog(instr):
  sys.stderr.write(str(instr))
  
class NetflixAuthToken(oauth.OAuthToken):
    #
    app_name = None
    user_id = None

    def __init__(self, key, secret, app_name=None, user_id=None):
        self.app_name = 'Plex'
        self.user_id = user_id
        oauth.OAuthToken.__init__(self, key, secret)

    def to_string(self):
        return oauth.OAuthToken.to_string(self)

    @staticmethod
    def from_string(s):
        params = cgi.parse_qs(s, keep_blank_values=False)

        key = params['oauth_token'][0]
        secret = params['oauth_token_secret'][0]

        if 'application_name' in params:
            app_name = params['application_name'][0]
        else:
            app_name = None

        if 'user_id' in params:
            user_id = params['user_id'][0]
        else:
            user_id = None

        return NetflixAuthToken(key, secret, app_name, user_id)

    def __str__(self):
        return self.to_string()

#
class NetflixRequest(object):
    #
    server = NETFLIX_SERVER
    port = NETFLIX_PORT
    request_token_url = REQUEST_TOKEN_URL
    access_token_url = ACCESS_TOKEN_URL
    authorization_url = AUTHORIZATION_URL
    api_url = API_URL
    signature_method = oauth.OAuthSignatureMethod_HMAC_SHA1()
    api_version = NETFLIX_VERSION

    def __init__(self, consumer_key=CONSUMER_KEY,
                 consumer_secret=CONSUMER_SECRET):
        self.consumer_key = consumer_key
        self.consumer_secret = consumer_secret

        self.connection = httplib.HTTPConnection("%s:%d" %
                                                 (self.server, self.port))
        self.consumer = oauth.OAuthConsumer(self.consumer_key,
                                            self.consumer_secret)

        self.queue_etag = None

    def get_request_token(self):
        req = oauth.OAuthRequest.from_consumer_and_token(
                  self.consumer, http_url=self.request_token_url)
        req.sign_request(self.signature_method, self.consumer, None)

        self.connection.request(req.http_method, self.request_token_url,
                                headers=req.to_header())
        response = self.connection.getresponse()
        # TODO: check the response code
        #Log.Add('get_request_token response: ' + response.read())
        token = NetflixAuthToken.from_string(response.read())
        #locallog('get_request_token: ')
        #localog(token)
        self.connection.close()

        return token

    def get_access_token(self, req_token):
        req = oauth.OAuthRequest.from_consumer_and_token(
                  self.consumer, token=req_token,
                  http_url=self.access_token_url)
        #localog(req)
        
        req.sign_request(self.signature_method, self.consumer, req_token)
        #localog(req.to_header())

        self.connection.request(req.http_method, self.access_token_url, headers=req.to_header())
        #locallog(req.to_header())
        response = self.connection.getresponse()
        # TODO: check the response code
        data = response.read()
        #localog(data)
        token = NetflixAuthToken.from_string(data)
        self.connection.close()

        return token

    def generate_authorization_url(self, req_token):
        params = {'application_name': req_token.app_name,
                  'oauth_consumer_key': self.consumer_key}
        req = oauth.OAuthRequest.from_token_and_callback(
                  token=req_token, http_url=self.authorization_url,
                  parameters=params)

        return req.to_url()

    def _make_query(self, access_token=None, method="GET", query="", params=None, returnURL=True):
        if params is None:
            params = {}

        if query.startswith('http://'):
            url = query
        else:
            url = self.api_url + query

        params['v'] = self.api_version
        params['oauth_consumer_key'] = self.consumer_key
        
        req = oauth.OAuthRequest.from_consumer_and_token(
                  self.consumer, token=access_token, http_method=method,
                  http_url=url, parameters=params)
        req.sign_request(self.signature_method, self.consumer, access_token)
        #locallog(req.to_url())
        if method == 'GET' or method == 'PUT' or method == 'DELETE':
            if returnURL:
              return req.to_url()
            else:  
              self.connection.request(method, req.to_url())
            #was: self.connection.request(method, url, headers=req.to_header()) -- didn't work
        elif method == 'POST':
            headers = {'Content-Type': 'application/x-www-form-urlencoded'}
            self.connection.request(method, url, body=req.to_postdata(), headers=headers)
        else:
            return None

        return self.connection.getresponse()
      
    def get_entireCatalogURL(self, access_token):
        url = 'http://api.netflix.com/catalog/titles/index'
        req = oauth.OAuthRequest.from_consumer_and_token(self.consumer, token=None, http_url=url, http_method="GET")
        req.sign_request(self.signature_method, self.consumer, None)

        return req.to_url()
      
    def _finish_query(self):
        self.connection.close()

    def get_xml(self, method, url, params=None, token=None):
        response = self._make_query(token, method, url, params)
        data = response.read()
        status_code = response.status
        status_msg = response.reason
        self._finish_query()
        return ((status_code, status_msg), data)

    def _get_rating_id_from_title_id(self, title_id):
        # simple method: extract from title_id
        matchstr = re.compile(r".*catalog/titles/.*?/(.*?)(/.*)?$",
                              re.IGNORECASE)
        rating_id = matchstr.match(title_id).group(1)

        if rating_id and rating_id != '':
            return rating_id
        return None

        # complicated method: send title_id request, extract rating_id
        # from result, return that.
        return None

    def get_rating_info(self, title_ids, access_token):
        title_csv = ','.join(title_ids)
        params = {
            'title_refs': ','.join(title_ids)
        }
        url = 'users/%s/ratings/title' % access_token.user_id
        return self._make_query(access_token, 'GET', url, params, False)

    def rate_title(self,title_id,rating,access_token):

        if not rating or rating == '':
            rating = RATING_NOT_INTERESTED

        existing_rating = self.get_title_rating(title_id,access_token)

        if existing_rating is not None:
            # update existing rating
            rating_id = existing_rating['id'].split('/')[-1]
            url = 'users/%s/ratings/title/actual/%s' % (access_token.user_id, rating_id)
            params = {
                'rating': rating    
            }
            r = self._make_query(access_token, 'PUT', url, params, False)
            out = r.read()
            return self.get_title_rating(title_id,access_token)
        else:
            # create new rating
            url = 'users/%s/ratings/title/actual' % access_token.user_id
            params = {
                'title_ref': title_id,
                'rating': rating,
            }
            r = self._make_query(access_token, 'POST', url, params, False)
            out = r.read()
            return self.get_title_rating(title_id,access_token)
        pass
    def get_title_rating(self,title_id,access_token):
        url = 'users/%s/ratings/title' % access_token.user_id
        params = {
            'title_refs': title_id,
        }
        r = self._make_query(access_token, 'GET', url, params, False)

        xml = r.read()

        m = re.search(r'<user_rating(?:\s+value="([^"]+)")?>(.*?)</user_rating>',xml)
        if m:
            id     = re.search(r'<id>(.*?)</id>',xml).group(1)
            if m.group(1):
                rating = m.group(1)
            elif m.group(2):
                rating = m.group(2)
            if rating == RATING_NOT_INTERESTED:
                rating = ''

            m = re.search(r'<predicted_rating(?:\s+value="([^"]+)")?>(.*?)</predicted_rating>',xml)
            if m.group(1):
                predicted = m.group(1)
            elif m.group(2):
                predicted = m.group(2)
            if predicted == RATING_NOT_INTERESTED:
                predicted = ''
            ret = {
                'user_rating': rating,
                'id': id,
                'href': title_id,
                'predicted_rating': predicted
            }
            return ret
        else:
            return None

    def get_title_info(self, title_id, access_token):
        url = title_id
        req = oauth.OAuthRequest.from_consumer_and_token(self.consumer, token=None, http_url=url, http_method="GET")
        req.sign_request(self.signature_method, self.consumer, None)

        return req.to_url()

    def get_title_similars(self, title_id, max_results=None, token=None):
        pass

    def search_titles(self, access_token, term, max_results=None, token=None, expand=None, urlBack=True, instantOnly=False):
        url = 'catalog/titles'        
            
        params = {'term': term }
        if expand is not None:
            params['expand'] = expand

        if instantOnly:
            params['filters'] = 'http://api.netflix.com/categories/title_formats/instant'

        if max_results is not None and max_results > 0:
            params['max_results'] = max_results

        response = self._make_query(access_token, 'GET', url, params, urlBack)
        return (response)
      
    def get_genres(self, access_token=None, returnURL=True):
        url = 'categories/genres'
        params = {}
        response = self._make_query(access_token, 'GET', url, params, returnURL)
        return (response)
      
    def get_title_matches(self, term, token=None):
        pass

    def search_people(self, term, max_results=None, token=None):
        pass

    def get_person_info(self, person_id, token=None):
        pass

    def get_user_info(self, access_token):
        pass

    def get_user_feeds(self, access_token, urlBack=True):
        url = 'users/%s/feeds' % access_token.user_id 
        
        response = self._make_query(access_token, 'GET', url, params=None, returnURL=urlBack)
        return (response)
      
    def get_user_titles_state(self, access_token, title_ids):
        pass

    def get_user_queue(self, access_token, within_secs=None,
                       max_results=None, sort=SORT_QUEUE):
        pass
        # make sub apis for disc/instant, available/saved, entry?

