import logging
import shlex
import subprocess
import time
import unittest
from urllib.error import URLError
from urllib.request import urlopen

import manage

# importing main enables logging, we switch it off again here to prevent
# selenium debug lines from flooding the test output
logging.disable(logging.CRITICAL)

from app.main import application


class PhantomTest(unittest.TestCase):

    def __init__(self, methodName='runTest'):
        self.single = None
        super().__init__(methodName)

    def set_single(self, single):
        """Set a single CasperJS test (class name) to run."""
        self.single = single

    def test_run(self):
        try:
            self._spawn_live_server()
            return_code = self.run_phantom_test(self.single)
        finally:
            self._post_teardown()
            self._terminate_live_server()
        try:
            return (0 if return_code == 0 else 1)
        except NameError:
            return 1

    def _spawn_live_server(self):
        self.port = application.config['LIVE_SERVER_PORT']
        self._server_url = 'http://localhost:{}'.format(self.port)
        command_line = 'python manage.py run_test_server'
        self._process = subprocess.Popen(shlex.split(command_line))
        # wait a few seconds for the server to start listening
        timeout = 5
        start_time = time.time()
        while time.time() - start_time < timeout:
            time.sleep(0.5)
            try:
                urlopen(self._server_url)
            except URLError:
                pass
            else:
                break
        else:
            assert False, "timed out waiting for server to respond"

    def _post_teardown(self):
        if getattr(self, '_ctx', None) is not None:
            self._ctx.pop()
            del self._ctx

    def _terminate_live_server(self):
        if self._process:
            self._process.terminate()

    def run_phantom_test(self, single=None):
        coffee_build_result = manage.coffeebuild()
        self.assertEqual(coffee_build_result, 0,
                         'casperjs test failed: coffeescript build error.')
        command = ["./node_modules/.bin/casperjs", "test",
                   "--fail-fast",  # stop at first failed assertion
                   "app/static/compiled-js/tests/browser.js"
                   ]
        if single:
            command.append("--single={}".format(str(single)))
        return_code = subprocess.call(command)
        self.assertEqual(return_code, 0, "phantomjs test failed")
        return (0 if return_code == 0 else 1)

if __name__ == "__main__":
    tester = PhantomTest()
    tester.run()
