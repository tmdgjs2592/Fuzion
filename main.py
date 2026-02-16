from runner.chromium_runner import ChromiumRunner
import os

load_dotenv()

chrome_path = os.getenv("CHROME_PATH")
runner = ChromiumRunner(
    chrome_path=r"C:\Program Files\Google\Chrome\Application\chrome.exe",
    timeout=5
)

result = runner.run("corpus/test_00001.html")

print(result)
