# Fuzion
Fuzzer Generator
Make sure you have google chrome installed, put your path to that chrome installation inside the .env
As an example, the env in the chrome path should look like this:

```env
CHROME_PATH=C:\Program Files\Google\Chrome\Application\chrome.exe
DEBUG=false
```

pip install -r requirements.txt

Domato Usage (Temporary Standin Generator)
Generate input to test using 
`py third_party/domato/generator.py --output_dir corpus -n 1000`

Run testing harness by using
`py main.py`

Directory Guide:
```
Fuzion/
│
├── generator/        # Testcase generation logic (custom generators)
│
├── detector/         # Result classification and crash detection logic
│
├── runner/           # Browser execution logic (ChromiumRunner, interfaces)
│
├── third_party/      # External tools (e.g., Domato HTML generator)
│
├── corpus/
│   ├── generated/    # Raw generated input testcases (.html files)
│   ├── runs/         # Per-execution logs and metadata
│   └── failures/     # Interesting or crashing testcases promoted from runs
│
├── main.py           # Orchestration entry point
├── .env         # Configuration handling
└── requirements.txt # For setting up python libraries
```