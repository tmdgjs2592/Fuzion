from dotenv import load_dotenv
import os
import subprocess
from pathlib import Path
from runner.interface import BrowserRunner

class ChromiumRunner(BrowserRunner):
    def __init__(self, chrome_path, timeout=5, debug=False):
        self.chrome_path = chrome_path
        self.timeout = timeout
        self.debug = debug

    def run(self, testcase_path):
        if not os.path.isfile(testcase_path):
            raise FileNotFoundError(f"Testcase not found: {testcase_path}")

        testcase_url = Path(testcase_path).resolve().as_uri()

        args = [
            self.chrome_path,
            "--headless=new",
            "--disable-gpu",
            "--no-sandbox",
            "--dump-dom",
            testcase_url,
        ]

        if self.debug:
            print("RUN:", args, flush=True)

        proc = subprocess.Popen(
            args,
            stdout=subprocess.DEVNULL,        
            stderr=subprocess.PIPE,
            text=True,
            encoding="utf-8",
            errors="replace",
            creationflags=subprocess.CREATE_NEW_PROCESS_GROUP,
        )

        try:
            _, stderr = proc.communicate(timeout=self.timeout)
            code = proc.returncode
            return {
                "status": "ok" if code == 0 else "crash",
                "exit_code": code,
                "stderr": stderr or ""
            }

        except subprocess.TimeoutExpired:
            subprocess.run(
                ["taskkill", "/F", "/T", "/PID", str(proc.pid)],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
            return {"status": "timeout", "exit_code": None, "stderr": ""}
