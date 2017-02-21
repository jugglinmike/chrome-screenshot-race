import logging
from multiprocessing import Process
import requests
from SimpleHTTPServer import SimpleHTTPRequestHandler
import SocketServer
import time

PORT = 8089
def server(port):
    httpd = SocketServer.TCPServer(('', port), SimpleHTTPRequestHandler)
    httpd.serve_forever()

p = Process(target=server, args=(PORT,))
p.daemon = True
p.start()

def request(method, uri, data=None):
    logging.info('  --> %s %s %s' % (method.upper(), uri, data))

    response = getattr(requests, method)('http://localhost:4444/%s' % uri, json=data)

    if response.status_code != 200:
        raise Exception(response.text)

    logging.info('  <-- %s' % response.json())

    return response.json()

def report(count, first_reading, curr_reading, later_reading):
    document = '''<!DOCTYPE html>
<style>img { border: solid 1px #555; }</style>
<p>Captured %s screen shots over %s seconds.</p>
<table>
  <tr>
    <td>
      Initial screen capture<br />
      callback strategy: %s<br />
      document.readyState: %s<br />
      documentElement.scrollHeight: %s<br />
      window.ONLOAD_FIRED: %s<br />
      [img.naturalWidth, img.naturalHeight]: %s
    </td>
    <td><img src="data:img/png;base64,%s" /></td>
  </tr>
  <tr>
    <td>Abberant rendering<br />
      callback strategy: %s<br />
      document.readyState: %s<br />
      documentElement.scrollHeight: %s<br />
      window.ONLOAD_FIRED: %s<br />
      [img.naturalWidth, img.naturalHeight]: %s
    </td>
    <td><img src="data:img/png;base64,%s" /></td>
  </tr>
  <tr>
    <td>Above document, re-captured after %s second delay</td>
    <td><img src="data:img/png;base64,%s" /></td>
  </tr>
</table>
''' % (count,
        curr_reading['time'] - first_reading['time'],
        first_reading['pageState']['callbackStrategy'],
        first_reading['pageState']['readyState'],
        first_reading['pageState']['scrollHeight'],
        first_reading['pageState']['onload_fired'],
        first_reading['pageState']['natural_dimensions'],
        first_reading['screenshot'],
        curr_reading['pageState']['callbackStrategy'],
        curr_reading['pageState']['readyState'],
        curr_reading['pageState']['scrollHeight'],
        curr_reading['pageState']['onload_fired'],
        curr_reading['pageState']['natural_dimensions'],
        curr_reading['screenshot'],
        later_reading['time'] - curr_reading['time'],
        later_reading['screenshot'])

    return document

def take_reading(session_id):
    result = request('get', 'session/%s/screenshot' % session_id)

    return {
        'pageState': None,
        'screenshot': result['value'],
        'time': time.time()
    }

session_id = request('post', 'session', dict(desiredCapabilities={}))['sessionId']

try:
    request('post', 'session/%s/timeouts/async_script' % session_id, dict(ms=1000))

    first_reading = None
    count = 0

    while True:
        count += 1
        request('post', 'session/%s/url' % session_id, dict(url='about:blank'))
        request('post', 'session/%s/url' % session_id, dict(url='http://localhost:%s/' % PORT))

        script = '''
            var callback = arguments[0];
            function done(strategy) {
              callback({
                callbackStrategy: strategy,
                readyState: document.readyState,
                scrollHeight: document.documentElement.scrollHeight,
                onload_fired: window.ONLOAD_FIRED,
                natural_dimensions: [
                  document.getElementsByTagName('img')[0].naturalWidth,
                  document.getElementsByTagName('img')[0].naturalHeight
                ]
              });
            }
            if (document.readyState === 'complete') {
              done('synchronous');
            } else {
              onload = done.bind(null, 'asynchronous');
            }
        '''
        result = request('post', 'session/%s/execute_async' % session_id, dict(script=script, args=[]))
        curr_reading = take_reading(session_id)
        curr_reading['pageState'] = result['value']

        if first_reading is None:
            first_reading = curr_reading
        elif first_reading['screenshot'] != curr_reading['screenshot']:
            time.sleep(2)

            later_reading = take_reading(session_id)
            break

    with open('results.html', 'w') as f:
        f.write(report(count, first_reading, curr_reading, later_reading))

finally:
    request('delete', 'session/%s' % session_id)
