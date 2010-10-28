from PMS import *
from PMS.Objects import *
from PMS.Shortcuts import *

import string, netflix, xmlrpclib, mod_xmlrpcTransport, traceback, re, time, os
import htmlentitydefs
import webbrowser


NETFLIX_PLUGIN_PREFIX    = "/video/netflix"
NETFLIX_RPC_HOST         = "http://netflix.plexapp.com:8999"
CACHE_TIME               = 3600
WI_PLAYER_URL            = "http://www.netflix.com/WiPlayer?movieid=%s"
NETFLIX_ART              = 'art-default.png'
NETFLIX_ICON             = 'icon-default.png'
HOSTED_MODE              = True

NO_ITEMS                 = MessageContainer('No Results','No Results')
TRY_AGAIN                = MessageContainer('Error','An error has happened. Please try again later.')
ERROR                    = MessageContainer('Network Error','A Network error has occurred')

VIDEO_IN_BROWSER         = False


GlobalNetflixRPC      = None
GlobalNetflixSession  = None

__ratingCache         = {}
__quickCache          = {}
__inInstantQ          = {}

def __hasSilverlight():
    retVal = Platform.HasSilverlight
    if retVal == False:
        PMS.Log("trying to find silverlight in other places")
        paths = [
            '/Library/Internet Plug-Ins/Silverlight.plugin',
            os.path.expanduser('~/Library/Internet Plug-Ins/Silverlight.plugin'),
            '/Library/Internet Plug-ins/Silverlight.plugin',
            os.path.expanduser('~/Library/Internet Plug-ins/Silverlight.plugin'),
        ]
        for p in paths:
            if os.path.exists(p):
                PMS.Log("found in %s" % p)
                return True
    else:
        PMS.Log("found silverlight with Platform.HasSilverlight")
    return retVal


## NEW ##
def Start():
    global GlobalNetflixSession

    try:
        Data.Remove('__userFeedsCached')
    except:
        pass

    Plugin.AddPrefixHandler(NETFLIX_PLUGIN_PREFIX, TopMenu, "Netflix", NETFLIX_ICON, NETFLIX_ART)
    MediaContainer.art = R(NETFLIX_ART)
    MediaContainer.ratingColor = "FFEE3725"

    HTTP.__headers["User-agent"] = "Mozilla/5.0 (Macintosh; U; Intel Mac OS X 10_5_6; en-gb) AppleWebKit/528.16 (KHTML, like Gecko) Version/4.0 Safari/528.16"

    if not GlobalNetflixSession:
        GlobalNetflixSession  = NetflixSession()

def CreatePrefs():
    Prefs.Add(id='loginemail', type='text', default='', label='Login Email')
    Prefs.Add(id='password', type='text', default='', label='Password', option='hidden')
    Prefs.Add(id='cookieallow', type='bool', default=False, label='Allow Netflix Cookie')
    Prefs.Add(id='safemode', type='bool', default=False, label='Safe Mode (try if video wont play)')

def SetRating(key, rating):
    global __ratingCache
    if key in __ratingCache:
        del __ratingCache[key]

    if key and key !='':
        title_url = key

        if rating and rating != '':
            rating = int(float(rating)/2)

        r = netflix.NetflixRequest()
        at = GlobalNetflixSession.getAccessToken()
        item = r.rate_title(title_url,rating,at)
        __ratingCache[key] = item
        return MessageContainer("rated","ok: %s %s" % (item['id'], item['user_rating']))
    return MessageContainer("error","No key was provided")


    pass

def RPC(cached=False):
    global GlobalNetflixRPC
    # note a simple bool test should not be done
    # to prevent network problems
    if not cached:
        try:
            return xmlrpclib.ServerProxy(NETFLIX_RPC_HOST,transport=mod_xmlrpcTransport.GzipPersistTransport())
        except:
            return None

    if type(GlobalNetflixRPC) == type(None):
        try:
            GlobalNetflixRPC = xmlrpclib.ServerProxy(NETFLIX_RPC_HOST,transport=mod_xmlrpcTransport.GzipPersistTransport())
        except Except, e:
            PMS.Log(e)
            GlobalNetflixRPC = None

    return GlobalNetflixRPC


# ================================================

def TopMenu():
    if __hasSilverlight() == False:
      return MessageContainer('Error','Silverlight is required for the Netflix plug-in.\nPlease visit http://silverlight.net to install.')

    dir = MediaContainer(disabledViewModes=["Coverflow"], title1="Netflix") 

    try:
        loggedIn = GlobalNetflixSession.loggedIn()
        if not loggedIn:
            PMS.Log("attempting login")
            HTTP.__cookieJar.clear()
            loggedIn = GlobalNetflixSession.tryLogin()
    except Exception, e:
        PMS.Log("Error: %s" % e)
        return ERROR

    if loggedIn:
        dir.Append(Function(DirectoryItem(Menu,"Browse Movies", thumb=R("icon-movie.png")), type="Movies"))
        dir.Append(Function(DirectoryItem(Menu,"Browse TV", thumb=R("icon-tv.png")), type="TV"))
        dir.Append(Function(DirectoryItem(UserQueueMenu,"Your Instant Watch Queue", thumb=R("icon-queue.png"))))
        try:
            otherFeeds = nonRecommendationFeeds()
        except Exception, e:
            PMS.Log("TRY_AGAIN: %s" % e)
            return TRY_AGAIN

        for f in otherFeeds:
            dir.Append(Function(DirectoryItem(PersonalFeed,f['name'], thumb=R(NETFLIX_ICON)), url=f['url']))
        dir.Append(Function(DirectoryItem(MyRecommendations,"My Recommendations", thumb=R(NETFLIX_ICON))))
        dir.Append(Function(InputDirectoryItem(SearchMenu,"Search", "Search Netflix", thumb=R("search.png") )))

    else:
        dir.Append(Function(DirectoryItem(FreeTrial,"Sign up for free trial", thumb=R("icon-movie.png"))))

    dir.Append(PrefsItem(title="Netflix Preferences", thumb=R("icon-prefs.png")))
    dir.nocache = 1

    return dir


def MyRecommendations(sender):
    dir = MediaContainer(disabledViewModes=["Coverflow"], title1=sender.title1) 
    try:
        userfeeds = recommendationFeeds()
        for f in userfeeds:
            dir.Append(Function(DirectoryItem(PersonalFeed,f['name'], thumb=R(NETFLIX_ICON)), url=f['url']))
    except:
        pass
    return dir

def FreeTrial(sender):
    url = "http://www.netflix.com/"
    webbrowser.open(url,new=1,autoraise=True)
    return MessageContainer("Free Trial Signup",
"""A browser has been opened so that you may sign up for a free
trial.  If you do not have a mouse and keyboard handy, visit
http://www.netflix.com and sign up for free today!"""
    )
    pass

def PersonalFeed(sender,url=None):
    dir = MediaContainer(disabledViewModes=["Coverflow"], title1=sender.title1) 

    at = GlobalNetflixSession.getAccessToken()
    uid = at.user_id
    PMS.Log(url)
    PMS.Log(uid)
    try:
        items = RPC().getUserFeed(uid,at.to_string(),url)
    except Exception, e:
        PMS.Log("TRY_AGAIN: %s" % e)
        return TRY_AGAIN
    if len(items) == 0:
        return MessageContainer(sender.itemTitle,'No movie or TV shows found')
    populateFromCatalog(items,dir)
    if len(dir) == 0:
        return MessageContainer(sender.itemTitle,'No movie or TV shows found')

    return dir


def Menu(sender,type=None):
    if type=='Movies':
        all_icon = 'icon-movie.png'
    elif type == 'TV':
        all_icon = 'icon-tv.png'
    dir = MediaContainer(disabledViewModes=["Coverflow"], title1=sender.title1) 
    dir.Append(Function(DirectoryItem(AlphaListMenu,"All %s" % type, thumb=R(all_icon)), type=type))
    dir.Append(Function(DirectoryItem(GenreListMenu,"%s by Genres" % type, thumb=R(NETFLIX_ICON)), type=type))
    dir.Append(Function(DirectoryItem(YearListMenu,"%s by Year" % type, thumb=R("icon-year.png")), type=type))
    dir.Append(Function(DirectoryItem(ActorListMenu,"All Actors", thumb=R("icon-people.png")), type=type))
    dir.Append(Function(DirectoryItem(DirectorListMenu,"All Directors", thumb=R("icon-people.png")), type=type))
    return dir

def AlphaListMenu(sender,type=None,query=None):
    if query is not None:
        # handle a query if one was given
        dir = MediaContainer(disabledViewModes=["Coverflow"], title1=sender.title1, title2=query) 
        try:
            items = RPC().getCachedAlpha(query, type)
        except Exception, e:
            PMS.Log("TRY_AGAIN: %s" % e)
            return TRY_AGAIN
        if len(items) == 0:
            return NO_ITEMS
        dir = populateFromCatalog(items, dir)
    else:
        # list possible queries if none is given
        dir = MediaContainer(disabledViewModes=["Coverflow"], title1=sender.title1, title2=sender.itemTitle) 
        dir.Append(Function(DirectoryItem(AlphaListMenu,"#","#",thumb=R(NETFLIX_ICON)), type=type, query="#"))
        for letter in string.ascii_uppercase:
            dir.Append(Function(DirectoryItem(AlphaListMenu,"%s" % letter,letter,thumb=R(NETFLIX_ICON)), type=type, query=letter))
    if len(dir) == 0:
        return MessageContainer(sender.itemTitle,'No movie or TV shows found')
    return dir
    
def GenreListMenu(sender,type=None,query=None):
    if query is not None:
        dir = MediaContainer(disabledViewModes=["Coverflow"], title1=sender.title1, title2=query[-1]) 
        # get the video title in this genre 
        try:
            items = RPC().getCachedGenreTitles(query, type)
            genres = RPC().getGenres(query[-1], type)
        except Exception, e:
            PMS.Log("TRY_AGAIN: %s" % e)
            return TRY_AGAIN

        dir = populateFromCatalog(items, dir)
        #... and now get any sub-genres
        for genre in sorted(genres):
          dir.Append(Function(DirectoryItem(GenreListMenu,"Sub-genre: %s" % genre, thumb=R(NETFLIX_ICON)), type=type, query=query + [ genre ]))
    else:
        # list possible queries if none is given
        dir = MediaContainer(disabledViewModes=["Coverflow"], title1=sender.title1, title2=sender.itemTitle) 
        try:
            genres = RPC().getGenres('__top__', type)
        except Exception, e:
            PMS.Log("TRY_AGAIN: %s" % e)
            return TRY_AGAIN
        for genre in sorted(genres):
            dir.Append(Function(DirectoryItem(GenreListMenu,genre, thumb=R(NETFLIX_ICON)), type=type, query=[ genre ]))

    if len(dir) == 0:
        return MessageContainer(sender.itemTitle,'No movie or TV shows found')
    return dir

def YearListMenu(sender,type=None,query=None):
    if query is not None:
        # handle a query if one was given
        dir = MediaContainer(disabledViewModes=["Coverflow"], title1=sender.title1, title2=query) 
        try:
            yearTitles = RPC().getCachedYearQuery(int(query), type)
        except Exception, e:
            PMS.Log("TRY_AGAIN: %s" % e)
            return TRY_AGAIN
        dir = populateFromCatalog(yearTitles, dir)
    else:
        # list possible queries if none is given
        dir = MediaContainer(disabledViewModes=["Coverflow"], title1=sender.title1, title2=sender.itemTitle) 
        try:
            years = RPC().getAllYears(type)
        except Exception, e:
            PMS.Log("TRY_AGAIN: %s" % e)
            return TRY_AGAIN
        for y in years:
            dir.Append(Function(DirectoryItem(YearListMenu,"%s" % y,y, thumb=R(NETFLIX_ICON)), type=type, query=y))
    if len(dir) == 0:
        return MessageContainer(sender.itemTitle,'No movie or TV shows found')
    return dir

def ActorListMenu(sender,type=None,query=None):
    if query is not None:
        # handle a query if one was given
        dir = MediaContainer(disabledViewModes=["Coverflow"], title1=sender.title1, title2=sender.itemTitle) 
        try:
            actorTitles = RPC().getCachedActorQuery(query, type)
        except Exception, e:
            PMS.Log("TRY_AGAIN: %s" % e)
            return TRY_AGAIN

        dir = populateFromCatalog(actorTitles, dir)
    else:
        # list possible queries if none is given
        dir = MediaContainer(disabledViewModes=["Coverflow"], title1=sender.title1, title2=sender.itemTitle) 
        try:
            actors = RPC().getAllActors(type)
        except Exception, e:
            PMS.Log("TRY_AGAIN: %s" % e)
            return TRY_AGAIN
        for a in actors:
            dir.Append(Function(DirectoryItem(ActorListMenu,"%s" % a['last_first'],a['last_first'], thumb=R(NETFLIX_ICON)), type=type, query=a['full_name']))
    if len(dir) == 0:
        return MessageContainer(sender.itemTitle,'No movie or TV shows found')
    return dir
   
def DirectorListMenu(sender,type=None,query=None):
    if query is not None:
        # handle a query if one was given
        dir = MediaContainer(disabledViewModes=["Coverflow"], title1=sender.title1, title2=sender.itemTitle) 
        try:
            directorTitles = RPC().getCachedDirectorQuery(query, type)
        except Exception, e:
            PMS.Log("TRY_AGAIN: %s" % e)
            return TRY_AGAIN
        dir = populateFromCatalog(directorTitles, dir)
    else:
        # list possible queries if none is given
        dir = MediaContainer(disabledViewModes=["Coverflow"], title1=sender.title1, title2=sender.itemTitle) 
        try:
            directors = RPC().getAllDirectors(type)
        except Exception, e:
            PMS.Log("TRY_AGAIN: %s" % e)
            return TRY_AGAIN
        for d in directors:
            dir.Append(Function(DirectoryItem(DirectorListMenu,"%s" % d['last_first'],d['last_first'], thumb=R(NETFLIX_ICON)), type=type, query=d['full_name']))
    return dir

def ChildTitlesMenu(sender,parentId=None,query=None):
    dir = MediaContainer(disabledViewModes=["Coverflow"], title1=sender.title1, title2=sender.itemTitle) 

    try:
        childTitles = RPC().getChildrenOfTitle(parentId)
    except Exception, e:
        PMS.Log("TRY_AGAIN: %s" % e)
        return TRY_AGAIN

    dir = populateFromCatalog(childTitles, dir)
    if len(dir) == 0:
        return MessageContainer(sender.itemTitle,'No movie or TV shows found')
    return dir

def UserQueueMenu(sender,max=50,start=0,replaceParent=False):
    dir = MediaContainer(disabledViewModes=["Coverflow"], title1=sender.title1, title2=sender.itemTitle) 

    at = GlobalNetflixSession.getAccessToken()
    instantFeedURL = "http://api.netflix.com/users/%s/queues/instant" % at.user_id
    dir = populateFromFeed(instantFeedURL, dir, False, True, max=max,start=start,replaceParent=replaceParent, encrypt=True)
    if dir is None or len(dir) == 0:
        return MessageContainer(sender.itemTitle,'No movie or TV shows found')
    dir.nocache = 1
    return dir

def RecommendationsMenu(sender):
    dir = MediaContainer(disabledViewModes=["Coverflow"], title1=sender.title1, title2=sender.itemTitle) 
    instantFeed = XML.ElementFromString(HTTP.Request(netflix.NetflixRequest().get_user_feeds(GlobalNetflixSession.accessToken, urlBack=True))).xpath("//link[@title='Recommendations']")[0]
    dir = populateFromFeed(instantFeed.get("href") + "&max_results=50", dir)
    if dir is None or len(dir) == 0:
        return MessageContainer(sender.itemTitle,'No movie or TV shows found')
    return dir

def SearchMenu(sender, query=None):
    dir = MediaContainer(disabledViewModes=["Coverflow"], title1=sender.title1, title2=query) 

    ids = []
    url = netflix.NetflixRequest().search_titles(GlobalNetflixSession.accessToken, query, max_results=100, urlBack=True, instantOnly=True)
    xml = XML.ElementFromURL(url)
    for title in xml.xpath("//catalog_item"):
        id = title.find("link").get('href').split("/")[-1]
        ids.append(id)

    if len(ids) == 0:
        return MessageContainer('Search','No titles found')
    try:
        titleList = RPC().getTitlesByIds(ids,False) # don't sort by title
    except Exception, e:
        PMS.Log("TRY_AGAIN: %s" % e)
        return TRY_AGAIN
    dir = populateFromCatalog(titleList, dir)
    if len(dir) == 0:
        return MessageContainer(sender.itemTitle,'No movie or TV shows found')
    return dir

def allUserFeeds():
    global __inInstantQ
    PMS.Log("[4] INSTANT QUEUE CONTAINS %d items" % len(__inInstantQ))
    __userFeedsCached = Data.LoadObject('__userFeedsCached')

    if __userFeedsCached is None:
        PMS.Log('userFeedsCached is None')
        PMS.Log("[5] INSTANT QUEUE CONTAINS %d items" % len(__inInstantQ))
        at = GlobalNetflixSession.getAccessToken()
        uid = at.user_id
        userfeeds = RPC().getUserFeeds(uid,at.to_string())
        PMS.Log("[6] INSTANT QUEUE CONTAINS %d items" % len(__inInstantQ))
        PMS.Log(userfeeds)
        Data.SaveObject('__userFeedsCached',userfeeds)
        __userFeedsCached = userfeeds
        PMS.Log("[7] INSTANT QUEUE CONTAINS %d items" % len(__inInstantQ))
    return __userFeedsCached

def isFeedBasedOnYou(f):
    if re.match(r'New Arrivals',f['name']):
        return False
    elif re.match(r'Recently Watched',f['name']):
        return False
    else:
        return True

__instantUrl = None
def videoIsInQ(item):
    global __instantUrl, __inInstantQ
    if __instantUrl is None:
        PMS.Log("NO INSTANT URL")
        userFeedXML = HTTP.Request(netflix.NetflixRequest().get_user_feeds(GlobalNetflixSession.accessToken, urlBack=True), cacheTime=0)
        instantFeed = XML.ElementFromString(userFeedXML).xpath("//link[@title='Instant Queue']")[0]
        __instantUrl = instantFeed.get("href")
        PMS.Log("UserFeed=%s, instantFeed=%s, instantURL=%s" % (userFeedXML, instantFeed, __instantUrl))
    if len(__inInstantQ) == 0:
        PMS.Log("SIZE OF INSTANT QUEUE IS 0")
        feed = RSS.FeedFromURL(__instantUrl, cacheTime=0, headers={ 'Pragma': 'no-cache', 'Cache-Control': 'no-cache' })
        ids = []
        count = 0
        for i in feed["items"]:
            count += 1
            try:
                pos = i['nflx_position']
            except:
                pos = count

            for l in i['links']:
                if l['rel'] == 'http://schemas.netflix.com/catalog/title':
                    __inInstantQ[l['href']] = {
                        'position': pos,
                        'id': i['id']
                    }
                    break

    PMS.Log("SIZE OF INSTANT QUEUE IS %d" % len(__inInstantQ))
    if item['href'] in __inInstantQ:
        return __inInstantQ[item['href']]
    else:
        return False

def recommendationFeeds():
    feeds = allUserFeeds()
    ret = []
    for f in feeds:
        if isFeedBasedOnYou(f):
            ret.append(f)

    return ret

def nonRecommendationFeeds():
    feeds = allUserFeeds()
    ret = []
    for f in feeds:
        if not isFeedBasedOnYou(f):
            ret.append(f)
    return ret


## internal helpers
def populateFromFeed(url, dir, titleSort=True, setAllInstant=False, max=50, start=0, replaceParent=False, encrypt=False):

    global __inInstantQ, GlobalNetflixSession
    if setAllInstant:
        __inInstantQ = {}

    dir.replaceParent = replaceParent

    if encrypt == False:
        thisUrl = '%s&max_results=%s&start_index=%s' % (url,max,start)
    else:
        r = netflix.NetflixRequest()
        at = GlobalNetflixSession.getAccessToken()
        thisUrl = r._make_query(access_token=at,query=url,params={'max_results':max,'start_index':start,'output':'atom'},method="GET", returnURL=True)
        PMS.Log('user feed oauth: %s' % thisUrl)

    # Use FeedFromString until the cacheTime bug with FeedFromURL is corrected
    xml  = HTTP.Request(thisUrl, headers={'Pragma': 'no-cache', 'Cache-Control': 'no-cache'}, cacheTime=0)
    feed = RSS.FeedFromString(xml)

    ids = []
    count = 0
    for i in feed["items"]:
        count += 1
        id = i.link.split("/")[-1]
        if setAllInstant:
            try:
                pos = i['nflx_position']
            except:
                pos = count
            for l in i['links']:
                if l['rel'] == 'http://schemas.netflix.com/catalog/title':
                    __inInstantQ[l['href']] = {
                        'position': pos,
                        'id': i['id']
                    }
                    break
        ids.append(id)

    if len(ids) == 0:
        return None

    try:
        titleList = RPC().getTitlesByIds(ids,titleSort)
    except Exception, e:
        PMS.Log("TRY_AGAIN: %s" % e)
        return TRY_AGAIN

    dir = populateFromCatalog(titleList, dir)
    if len(dir) == 0:
        return None
#feed nflx_start_index: 0
#feed nflx_number_of_results: 4
#feed nflx_results_per_page: 2
    try:
        count = int(feed['feed']['nflx_number_of_results'])
    except:
        PMS.Log("WARNING: feed/nflx_number_of_results was not found in xml")
        PMS.Log(xml)
        count = len(ids)

    start = int(start)
    max   = int(max)

    if (start+max) < count:
        dirItem = Function(
            DirectoryItem(
                UserQueueMenu,
                "Next Page...",
                thumb=R(NETFLIX_ICON),
            ),
            max='%s' % (max),
            start='%s' % (start+max),
            replaceParent=(start>0)
         )
        dir.Append(dirItem)

    return dir

def massageTitleInfo(t):
    global __quickCache
    id = t['movieId']
    url = WI_PLAYER_URL % id
    title = t['title']
    short_title = title.strip()

    if t['nf_boxart'] == '':
        t['nf_boxart'] = R(NETFLIX_ICON)

    if t['nf_duration'] != '':
        duration = int(t['nf_duration'])*1000
    else:
        duration = 0

    if t['nf_rating'] != '':
        rating = float(t['nf_rating']) * 2
    else:
        rating = ''

    r_info = getRatingInfo(t['href'])
    user_rating = ''
    try:
        user_rating = float(r_info['user_rating']) * 2
    except:
        pass

    myParent = None
    try:
        if t['type'] == 'programs' and t['parent_href'] != '':
            parentId = t['parent_href'].split('/')[-1]
            try:
                myParent = __quickCache[parentId]
            except:
                try:
                    rpcparent = RPC(cached=True).getTitlesByIds([parentId],False)[0]
                    myParent = massageTitleInfo(rpcparent)
                    __quickCache[parentId] = myParent
                except Exception, e:
                    pass
    except:
        pass

    title_rating = t.get('nf_mpaa_rating','')
    if title_rating == '':
        title_rating = t.get('nf_tv_rating','')
    if myParent and title_rating == '' and myParent['mpaa_tv_rating'] != '':
        title_rating = myParent['mpaa_tv_rating']

    summary = "%s" % unescape(t['nf_synopsis'])
    if myParent and summary == '' and myParent['summary'] != '':
        summary = myParent['summary']

    if duration > 0 or title_rating != '':
        summary = "\n%s" % summary

    item = {
        'id': id,
        'movieId': t['movieId'],
        'type': t['type'],
        'title': unescape(short_title),
        'subtitle': t['release_year'],
        'thumb': t['nf_boxart'],
        'summary': summary,
        'art': '',
        'duration': duration,
        'rating': rating,
        'rating_user': user_rating,
        'mpaa_tv_rating': title_rating,
        'url': url,
        'href': t['href'],
        'parent_href': t['parent_href'],
    }
    return item

def msToRuntime(ms):

    if ms is None or ms <= 0:
        return None

    ret = []

    sec = int(ms/1000) % 60
    min = int(ms/1000/60) % 60
    hr  = int(ms/1000/60/60)

    return "%02d:%02d:%02d" % (hr,min,sec)

def populateFromCatalog(titleList, dir):
    global __quickCache

    # since we are now handling child items, try and flatten
    # the hierarchy in software here to prevent the database from
    # being hit harder than it needs to

    cacheUserRatings(titleList)
    
    madeWebVid = False

    for t in titleList:
        t = massageTitleInfo(t)
        __quickCache[t['id']] = t

        summary = t['summary']
        if t['duration'] > 0:
            summary = "Runtime: %s\n%s" % (msToRuntime(t['duration']),summary)
        if t['mpaa_tv_rating']:
            summary = "Rating: %s\n%s" % (t['mpaa_tv_rating'],summary)

        infoLabel = msToRuntime(t['duration'])
        dirItem = Function(
            PopupDirectoryItem(
                InstantMenu,
                t['title'],
                thumb=t['thumb'],
                summary=summary,
                subtitle=t['subtitle'],
                art='',
                duration=t['duration'],
                rating=t['rating'],
                userRating=t['rating_user'],
                ratingKey=t['href'],
                infoLabel=infoLabel,
            ),
            id="%s" % t['id']
        )
        dir.Append(dirItem)

    if madeWebVid:
        dir.nocache = 1
    return dir

def list_of_n_lists(myList, n):

    lol = map(None, *(iter(myList),) * n)
    if lol[-1][-1] is None:
        newList = []
        for i in lol[-1]:
            if i is None:
                break
            newList.append(i)
        lol[-1] = newList
    return lol

def cacheUserRatings(titleList):
    global __ratingCache
    __ratingCache = {}

    if len(titleList) == 0:
        return

    titles = [ t['href'] for t in titleList ]
    for t in titles:
        __ratingCache[t] = None

    at = GlobalNetflixSession.getAccessToken()
    for someTitles in list_of_n_lists(titles,40):
        r = netflix.NetflixRequest()
        res  = r.get_rating_info(title_ids=someTitles,access_token=at)
        if res.status != 200:
            PMS.Log("netflix api query failure: %s" % res.status)
            PMS.Log(res.read())
            return
        try:
            html = res.read()
            xml  = XML.ElementFromString(html)
            if xml is not None:
                items = parseRatingXML(xml)
                for item in items:
                    __ratingCache[item['href']] = item
        except Exception, e:
            PMS.Log(e)
            pass

    pass

def parseRatingXML(xml):
    items = []
    for ri in xml.xpath('//ratings_item'):
        href = ri.xpath('.//link[@rel="http://schemas.netflix.com/catalog/title"]')[0].get('href')
        id   = ri.xpath('.//id/text()')[0]
        predicted_rating = ''
        try:
            predicted_rating = ri.xpath('.//predicted_rating/text()')[0]
        except:
            pass
        user_rating = ''
        try:
            user_rating = ri.xpath('.//user_rating/text()')[0]
        except:
            pass
        item = {
            'id': id,
            'href': href,
            'predicted_rating': predicted_rating,
            'user_rating': user_rating
        }
        items.append(item)

    return items

def getRatingInfo(url):
    global __ratingCache
    if url in __ratingCache:
        return __ratingCache[url]

    r = netflix.NetflixRequest()
    at = GlobalNetflixSession.getAccessToken()
    res  = r.get_rating_info(title_ids=[url],access_token=at)
    if res.status != 200:
        PMS.Log("netflix api query failure: %s" % res.status)
        PMS.Log(res.read())
        return
    html = res.read()
    xml  = XML.ElementFromString(html)
    items = parseRatingXML(xml)
    for item in items:
        __ratingCache[item['href']] = item

    if url in __ratingCache:
        return __ratingCache[url]
    else:
        return {}

def InstantMenu(sender, id=''):
    try:
        item = __quickCache[id]
    except:
        try:
            rpcitem = RPC().getTitlesByIds([id],False)[0]
        except Exception, e:
            PMS.Log("TRY_AGAIN: %s" % e)
            return TRY_AGAIN
        item = massageTitleInfo(rpcitem)

    dir = MediaContainer(title1="Options",title2=sender.itemTitle,disabledViewModes=["Coverflow"])

    madeWebVid = False

    if item['type'] in ['programs','movies']:
        bookmark = 0
        try:
            r = netflix.NetflixRequest()
            at = GlobalNetflixSession.getAccessToken()
            url = 'http://api.netflix.com/users/%s/title_states' % at.user_id
            res = r._make_query(access_token=at,query=url,params={'title_refs': item['href']},method="GET", returnURL=False)
            xmlStr = res.read()
            xml = XML.ElementFromString(xmlStr)
            bookmark = int(xml.xpath('//playback_bookmark/text()')[0])  
        except Exception, e:
            PMS.Log(e)
            pass

        PMS.Log("bookmark: %d" % bookmark)
        bookmark = bookmark * 1000

        if bookmark > 0:
            wvi = makeWebvideoItem(item)
            wvi.title = "Restart Video"
            dir.Append(wvi)
            wvi = makeWebvideoItem(item,mode='resume')
            wvi.title = "Resume Video - %s" % msToRuntime(bookmark)
            dir.Append(wvi)
        else:
            wvi = makeWebvideoItem(item)
            wvi.title = "Play Video"
            dir.Append(wvi)
        madeWebVid = True
    else:
        summary = item['summary']
        if item['type'] != 'programs' and item['duration'] > 0:
            summary = "Runtime: %s\n%s" % (msToRuntime(item['duration']),summary)
        if item['mpaa_tv_rating']:
            summary = "Rating: %s\n%s" % (item['mpaa_tv_rating'],summary)
        infoLabel = msToRuntime(item['duration'])
        dirItem = Function(
            DirectoryItem(
                ChildTitlesMenu,
                "View Episodes",
                summary=summary,
                thumb=item['thumb'],
                art='',
                subtitle=item['subtitle'],
                duration=item['duration'],
                infoLabel=infoLabel,
                rating=item['rating'],
                userRating=item['rating_user'],
                ratingKey=item['href'],
            ),
            parentId=item['href']
         )
        dir.Append(dirItem)

    if item['type'] != 'programs':
        if videoIsInQ(item):
            dir.Append(Function(DirectoryItem(QueueItem,"Remove from Instant Queue",thumb=R("icon-queue.png")),add="0",id="%s"%id))
        else:
            dir.Append(Function(DirectoryItem(QueueItem,"Add to Instant Queue",thumb=R("icon-queue.png")),add="1",id="%s"%id))

    if madeWebVid:
        dir.nocache = 1
    if len(dir) == 0:
        return MessageContainer(sender.itemTitle,'No movie or TV shows found')
    return dir

#def RateStub(sender,key,rating):
#    return SetRating(key,rating)

def QueueItem(sender,add='',id=''):
    global __inInstantQ
    add = int(add)
    try:
        item = __quickCache[id]
    except:
        try:
            rpcitem = RPC().getTitlesByIds([id],False)[0]
        except Exception, e:
            PMS.Log("TRY_AGAIN: %s" % e)
            return TRY_AGAIN
        item = massageTitleInfo(rpcitem)

    title = "Success"
    vidInQ = videoIsInQ(item)
    res = None
    __inInstantQ = {}
    if add:
        if vidInQ:
            title = "Error"
            message = "Title already in your Instant Queue"
        else:
            message = "Title added to your Instant Queue"
            try:
                r = netflix.NetflixRequest()
                at = GlobalNetflixSession.getAccessToken()
                params = {
                    'title_ref': item['href']
                }
                url = 'http://api.netflix.com/users/%s/queues/instant' % at.user_id
                res = r._make_query(access_token=at,query=url,params=params,method="POST", returnURL=False)
            except Exception, e:
                PMS.Log(e)
                title = "Error"
                message = "There was a problem adding this title to your Instant Queue"
    else:
        if not vidInQ:
            title = "Error"
            message = "Title is not in your Instant Queue"
        else:
            message = "Title removed from your Instant Queue"
            url = vidInQ['id']
            r = netflix.NetflixRequest()
            at = GlobalNetflixSession.getAccessToken()
            try:
                res = r._make_query(access_token=at,query=url,method="DELETE", returnURL=False)
            except Exception, e:
                PMS.Log(e)
                title = "Error"
                message = "There was a problem removing this title from your Instant Queue"

    if res is not None and res.status >= 400:
        title = "Error"
        if res.status == 400 and add:
            message = """There are too many items in your Queue. You
will need to remove some before you can add
any more"""
        else:
            message = "Try again..."

    return MessageContainer(title,message)

def getPlayerUrl(url='',mode='restart'):
    if not HOSTED_MODE or Prefs.Get('safemode'):
        return url

    PMS.Log("building movie url")
    at = GlobalNetflixSession.accessToken
    url,p = url.split('?')
    movieId = p.split('=')[-1]
    userUrl = "http://api.netflix.com/users/%s" % (at.user_id)
    PMS.Log("user id: %s" % at.user_id)
    PMS.Log("user url: %s" % userUrl)

    params = {
        'movieid': movieId,
        'user': userUrl
    }
    PMS.Log("params: %s" % repr(params))
    r = netflix.NetflixRequest()
    url = r._make_query(access_token=at,query=url,params=params,method="GET", returnURL=True)
    PMS.Log("final url built: %s" % repr(url))

    return "%s#%s" % (url,mode)

def BuildPlayerUrl(sender,url='',mode='restart',forcePlay=False,setCookiePref=False):

    if setCookiePref:
        Prefs.Set('cookieallow',True)

    cookieallow = Prefs.Get('cookieallow')
    if cookieallow or forcePlay:
        url = getPlayerUrl(url,mode)

        key = WebVideoItem(url).key
        key = key[:16] + key[16:].replace('.','%2E')
        PMS.Log("NEW KEY: " + key)
         
        if VIDEO_IN_BROWSER:
            webbrowser.open(url,new=1,autoraise=True)
        else:
            return Redirect(WebVideoItem(url))
            #return Redirect(key)
    else:
        return CookieWarning(sender,url,mode)

def CookieWarning(sender,url,mode):
    dir = MediaContainer(disabledViewModes=["Coverflow"], title1=sender.title1, noHistory=True) 
    dir.Append(
        Function(WebVideoItem(
            BuildPlayerUrl,
            "Allow Cookie Once",
            summary="Netflix would like to set a cookie.  Is this OK?",
            thumb=R(NETFLIX_ICON)
        ),url=url,mode=mode,forcePlay=True)
    )
    dir.Append(
        Function(WebVideoItem(
            BuildPlayerUrl,
            "Yes, Don't Ask Again",
            summary="Allow Netflix to set cookies and don't ask this again",
            thumb=R(NETFLIX_ICON)
        ),url=url,mode=mode,forcePlay=True,setCookiePref=True)
    )
    return dir


def makeWebvideoItem(item={},mode='restart'):

    cookieallow = Prefs.Get('cookieallow')
    summary = item['summary']
    if item['type'] != 'programs' and item['duration'] > 0:
        summary = "Runtime: %s\n%s" % (msToRuntime(item['duration']),summary)
    if item['mpaa_tv_rating']:
        summary = "Rating: %s\n%s" % (item['mpaa_tv_rating'],summary)
    if cookieallow:

        wvi = Function(WebVideoItem(
            BuildPlayerUrl,
            item['title'],
            summary=summary,
            subtitle=item['subtitle'],
            duration=item['duration'],
            thumb=item['thumb'],
            art=item['art'],
            rating=item['rating'],
            userRating=item['rating_user'],
            ratingKey=item['href'],
        ),url="%s"%item['url'],mode=mode)
    else:
        infoLabel = msToRuntime(item['duration'])
        wvi = Function(DirectoryItem(
            CookieWarning,
            item['title'],
            summary=summary,
            subtitle=item['subtitle'],
            duration=item['duration'],
            infoLabel=infoLabel,
            thumb=item['thumb'],
            art=item['art'],
            rating=item['rating'],
            userRating=item['rating_user'],
            ratingKey=item['href'],
        ),url="%s"%item['url'],mode=mode)

    return wvi

##
# http://effbot.org/zone/re-sub.htm#unescape-html
# Removes HTML or XML character references and entities from a text string.
#
# @param text The HTML (or XML) source text.
# @return The plain text, as a Unicode string, if necessary.
def unescape(text):
    def fixup(m):
        text = m.group(0)
        if text[:2] == "&#":
            # character reference
            try:
                if text[:3] == "&#x":
                    return unichr(int(text[3:-1], 16))
                else:
                    return unichr(int(text[2:-1]))
            except ValueError:
                pass
        else:
            # named entity
            try:
                text = unichr(htmlentitydefs.name2codepoint[text[1:-1]])
            except KeyError:
                pass
        return text # leave as is
    return re.sub("&#?\w+;", fixup, text)

def clearCaches():
    global __ratingCache, __quickCache, __inInstantQ, __instantUrl
    Data.Remove('__userFeedsCached')
    PMS.Log("INSTANT QUEUE CONTAINS %d items" % len(__inInstantQ))
    __ratingCache         = {}
    __quickCache          = {}
    __inInstantQ          = {}
    __instantUrl          = None
    PMS.Log("INSTANT QUEUE CONTAINS %d items" % len(__inInstantQ))

class NetflixSession():
    def __init__(self):
        self.__TOKEN_KEY = 'accesstoken'
        self.__username = Prefs.Get("loginemail")
        self.__password = Prefs.Get("password")
        pass

    def getAccessToken(self):
        tok = Data.LoadObject(self.__TOKEN_KEY)
        if tok != None:
            tok.app_name = 'Plex'
            PMS.Log(repr(tok.__dict__))
        return tok
    def setAccessToken(self, tokObj):
        if tokObj == None:
            Data.Remove(self.__TOKEN_KEY)
        else:
            Data.SaveObject(self.__TOKEN_KEY,tokObj)
    def delAccessToken(self):
        self.setAccessToken(tokObj=None)
    accessToken = property(fget=getAccessToken,fset=setAccessToken,fdel=delAccessToken)

    def getUsername(self):
        return Prefs.Get("loginemail")
    def setUsername(self,user):
        if user != self.getUsername():
            self.setAccessToken(None)
        Prefs.Set("loginemail")
    def delUsername(self):
        self.setUsername(user=None)
    username = property(fget=getUsername,fset=setUsername,fdel=delUsername)

    def getPassword(self):
        return Prefs.Get("password")
    def setPassword(self,password):
        if password != self.getPassword():
            self.setAccessToken(None)
        Prefs.Set("password",password)
    def delPassword(self):
        self.setPassword(password=None)
    password = property(fget=getPassword,fset=setPassword,fdel=delPassword)

    def refreshCredentials(self):
        if self.__username != Prefs.Get("loginemail"):
            clearCaches()
            self.__username = Prefs.Get("loginemail")
            self.setAccessToken(tokObj=None)

        if self.__password != Prefs.Get("password"):
            clearCaches()
            self.__password = Prefs.Get("password")
            self.setAccessToken(tokObj=None)

        return True

    def loggedIn(self):
        self.refreshCredentials()
        ret = self.getAccessToken() != None
        if not ret and Data.Load('login_converted') is None:
            self.tryLogin()
            Data.Save('login_converted','True')
            ret = self.getAccessToken() != None
        if ret:
            PMS.Log('checking access token validity')
            r = netflix.NetflixRequest()
            at = self.getAccessToken()
            if at is not None:
                url = 'http://api.netflix.com/users/%s' % at.user_id
                res = r._make_query(access_token=at,query=url,method="GET", returnURL=False)
                if res.status == 401:
                    PMS.Log('access token was found to be revoked: 401')
                    self.setAccessToken(tokObj=None)
                    return False

        return ret

    def tryLogin(self):
        PMS.Log("tryLogin()")
        self.refreshCredentials()
        u = self.getUsername()
        p = self.getPassword()

        if u == '' or u is None or p == '' or p is None:
            return False

        try:
            r = netflix.NetflixRequest()
            reqToken = r.get_request_token()

            values =  {'nextpage': 'http://www.netflix.com/',
                      'SubmitButton': 'Click Here to Continue',
                      'movieid': '',
                      'trkid': '',
                      'email': u,
                      'password1': p,
                      'RememberMe': 'True'}
            x = HTTP.Request('https://www.netflix.com/Login', values, cacheTime=0)

            origParams = {'oauth_callback': '', 'oauth_token': reqToken.key, 
                        'application_name':'Plex', 'oauth_consumer_key':netflix.CONSUMER_KEY,
                        'accept_tos': 'checked', 'login': u, 'password': p,'x':'166','y':'13'}
            x = HTTP.Request("https://api-user.netflix.com/oauth/login", origParams, cacheTime=0)
            xml = XML.ElementFromString(x,isHTML=True)

            errFound = None
            try:
                errFound = xml.xpath('//p[@id="error"]/text()')[0]
                PMS.Log(errFound)
            except:
                pass

            if errFound:
                PMS.Log("Netflix responded with an error: %s" % errFound)
                PMS.Log("Your username/pass are probably wrong")
                PMS.Log(".. or you're using an input method")
                PMS.Log(".. which seem to be causing character problems.")
                PMS.Log(".. Some things which have caused problems are:")
                PMS.Log("     -- using VNC to enter user/pass")
                PMS.Log("     -- Rowmote in some cases")
                return False

            at = r.get_access_token(reqToken)
            self.setAccessToken(at)
            if not at:
                return False
            else:
                return True
        except Exception, e:
            PMS.Log("(error) '%s' repr(%s)" % (e,repr(e)))
            return False
