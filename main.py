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

    def row(event_title, reading):
        return '''
          <tr>
            <th>%s</th>
            <td>
              <ul>
                <li>callback strategy: %s</li>
                <li>document.readyState: %s</li>
                <li>documentElement.scrollHeight: %s</li>
                <li>window.ONLOAD_FIRED: %s</li>
                <li>[img.naturalWidth, img.naturalHeight]: %s</li>
              </ul>
            </td>
            <td><img src="data:img/png;base64,%s" /></td>
          </tr>''' % (
            event_title,
            reading['pageState']['callbackStrategy'],
            reading['pageState']['readyState'],
            reading['pageState']['scrollHeight'],
            reading['pageState']['onload_fired'],
            reading['pageState']['natural_dimensions'],
            reading['screenshot']
        )

    document = '''<!DOCTYPE html>
<style>img { border: solid 1px #555; width: 300px; }</style>
<p>Captured %s screen shots over %s seconds.</p>
<table>
  <thead>
    <tr>
      <th>Event</th>
      <th>Page State (prior to screen capture)</th>
      <th>Screen Capture</th>
    </tr>
  </thead>
  <tbody>
    %s
    %s
  </tbody>
</table>
<p>Above document, re-captured after %s second delay:</p>
<img src="data:img/png;base64,%s" />
''' % (count,
        curr_reading['time'] - first_reading['time'],
        row('Initial rendering', first_reading),
        row('First aberrant rendering', curr_reading),
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
