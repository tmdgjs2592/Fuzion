import subprocess
from runner.interface import BrowserRunner

class ChromiumRunner(BrowserRunner):

    def __init__(self, chrome_path, timeout=5):
        self.chrome_path = chrome_path
        self.timeout = timeout

    def run(self, testcase_path):
        try:
            result = subprocess.run(
                [
                    self.chrome_path,
                    "--headless",
                    "--disable-gpu",
                    "--no-sandbox",
                    testcase_path
                ],
                timeout=self.timeout,
                capture_output=True
            )

            return {
                "status": "ok",
                "exit_code": result.returncode,
                "stderr": result.stderr.decode()
            }

        except subprocess.TimeoutExpired:
            return {
                "status": "timeout",
                "exit_code": None,
                "stderr": ""
            }
