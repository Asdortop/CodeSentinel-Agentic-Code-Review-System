import os
from dotenv import load_dotenv

load_dotenv()

GOOGLE_API_KEY: str = os.getenv("GOOGLE_API_KEY", "")
GITHUB_TOKEN: str = os.getenv("GITHUB_TOKEN", "")

MODEL: str = "gemini-2.0-flash"

MAX_FILES: int = 40
MAX_LINES: int = 300

RELEVANT_EXTENSIONS = {
    ".py", ".js", ".ts", ".jsx", ".tsx",
    ".java", ".go", ".rb", ".php", ".cs",
    ".env", ".toml", ".cfg", ".ini",
}

RELEVANT_FILENAMES = {
    "requirements.txt", "package.json", "pyproject.toml",
    "Pipfile", "go.mod", "pom.xml", "build.gradle",
    ".env", ".env.example", ".env.local", ".env.production",
    "Dockerfile", "docker-compose.yml", "docker-compose.yaml",
}

# Simple hardcoded CVE list — package → affected_versions_below (semver string)
KNOWN_VULNERABLE_PACKAGES = {
    # Python
    "requests": {"below": "2.28.0", "cve": "CVE-2023-32681"},
    "urllib3": {"below": "1.26.5", "cve": "CVE-2021-33503"},
    "cryptography": {"below": "41.0.0", "cve": "CVE-2023-38325"},
    "pillow": {"below": "10.0.0", "cve": "CVE-2023-44271"},
    "werkzeug": {"below": "2.3.8", "cve": "CVE-2023-46136"},
    "flask": {"below": "2.3.0", "cve": "CVE-2023-30861"},
    "django": {"below": "3.2.20", "cve": "CVE-2023-36053"},
    "pyyaml": {"below": "6.0", "cve": "CVE-2022-1471"},
    "jinja2": {"below": "3.1.3", "cve": "CVE-2024-22195"},
    "paramiko": {"below": "2.10.1", "cve": "CVE-2022-24302"},
    # JS / Node
    "lodash": {"below": "4.17.21", "cve": "CVE-2021-23337"},
    "axios": {"below": "0.27.2", "cve": "CVE-2023-45857"},
    "express": {"below": "4.18.2", "cve": "CVE-2022-24999"},
    "jsonwebtoken": {"below": "9.0.0", "cve": "CVE-2022-23529"},
    "minimist": {"below": "1.2.6", "cve": "CVE-2021-44906"},
    "node-fetch": {"below": "2.6.7", "cve": "CVE-2022-0235"},
    "qs": {"below": "6.10.3", "cve": "CVE-2022-24999"},
    "semver": {"below": "7.5.2", "cve": "CVE-2022-25883"},
    "tough-cookie": {"below": "4.1.3", "cve": "CVE-2023-26136"},
    "word-wrap": {"below": "1.2.4", "cve": "CVE-2023-26115"},
}
