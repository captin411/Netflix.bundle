import xmlrpclib
import httplib
import zlib, gzip, sys
from cStringIO import StringIO

class GzipPersistTransport(xmlrpclib.Transport):
    '''Provides a Transport for the xmlrpclib that uses httplib 
supporting persistent connections and compression
Does not close the connection after each request.'''

    connection = None

    def request(self, host, handler, request_body, verbose=0):
        if self.connection: print("self.connection")
        if not self.connection:
          host, extra_headers, x509 = self.get_host_info(host)
          self.connection = httplib.HTTPConnection(host)
          self.headers = {"User-Agent" : self.user_agent,
                          "Content-Type" : "text/xml",
                          "Accept": "text/xml",
                          'Accept-Encoding': 'gzip'}                    
          if extra_headers:
            for key, item in extra_headers:
                self.headers[key] = item
        
        self.headers["Content-Length"] = str(len(request_body))
        self.connection.request('POST',
            handler, request_body, self.headers)
        r = self.connection.getresponse()
        if r.status != 200:
            self.connection.close()
            self.connection = None
            raise xmlrpclib.ProtocolError( host + handler,
                r.status, r.reason, '' )
        
        if r.msg.has_key('content-encoding'):
          #sys.stderr.write("deflate content")
          #compresseddata = r.read()
          #data = zlib.decompress(compresseddata)
          if r.msg['content-encoding'] == 'gzip':
            compresseddata = r.read()
            compressedstream = StringIO(compresseddata)
            gzipper = gzip.GzipFile(fileobj=compressedstream)
            data = gzipper.read()
          elif self.headers['content-encoding'] == 'identity':
            data = r.read()
        else:
          data = r.read()
        
        p, u = self.getparser()
        p.feed(data)
        p.close()
        
        self.connection.close()
        self.connection = None
        return u.close()

#if __name__==__main__:
    # use the Transport class like this:
#    server = xmlrpclib.ServerProxy('http://someurl',
#            transport=GzipPersistTransport())
#    server.call_remote_function()
