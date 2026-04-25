"""
Dependency Agent — checks for outdated and vulnerable packages.
Checks PyPI and npm registries, plus a hardcoded CVE list.
"""
from __future__ import annotations

import json
import re
from typing import Dict, List, Optional

import httpx

from config import GOOGLE_API_KEY, MODEL, KNOWN_VULNERABLE_PACKAGES
from models import Finding

from google import genai
from google.genai import types

_client = None
from gemini_client import get_client, call_with_retry

DEPENDENCY_SYSTEM = """You are DependencyAgent, a security and dependency management expert.

You have been given:
1. Parsed dependency files (requirements.txt, package.json, etc.)
2. Latest version info from PyPI/npm registries
3. Known CVE matches from a vulnerability database

Your job:
- Identify packages that are significantly outdated (2+ major versions behind)
- Flag packages with known CVEs
- Note packages pinned to exact versions (fragile) vs flexible ranges
- Flag packages with no version constraint at all
- Identify potentially abandoned or deprecated packages

Severity:
- Critical: Known CVE with CVSS >= 9.0, or known RCE vulnerability
- High: Known CVE with CVSS 7.0-8.9, or 3+ major versions behind
- Medium: 2 major versions behind, or deprecated package
- Low: Minor version behind, no version constraints

Respond ONLY with valid JSON array:
[
  {
    "file": "requirements.txt",
    "line": null,
    "issue": "package_name==1.0.0 — CVE-XXXX-YYYY: brief description",
    "severity": "Critical|High|Medium|Low",
    "reasoning": "Explanation of risk and recommended version"
  }
]

Return [] if dependencies look healthy. Do not include markdown, only JSON.
"""


def _parse_requirements_txt(content: str) -> Dict[str, str]:
    """Extract {package: version_spec} from requirements.txt."""
    packages = {}
    for line in content.splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        # Handle -r, -e, --index-url etc.
        if line.startswith("-"):
            continue
        # Remove inline comments
        line = line.split("#")[0].strip()
        # Match: package==version, package>=version, package~=version, just package
        match = re.match(r"^([A-Za-z0-9_\-\.]+)\s*([><=!~^][^\s]*)?", line)
        if match:
            pkg = match.group(1).lower()
            ver = (match.group(2) or "").strip()
            packages[pkg] = ver
    return packages


def _parse_package_json(content: str) -> Dict[str, str]:
    """Extract {package: version} from package.json dependencies + devDependencies."""
    try:
        data = json.loads(content)
    except json.JSONDecodeError:
        return {}
    packages = {}
    for section in ("dependencies", "devDependencies", "peerDependencies"):
        for pkg, ver in data.get(section, {}).items():
            packages[pkg.lower()] = ver
    return packages


def _parse_pyproject_toml(content: str) -> Dict[str, str]:
    """Very basic TOML dep extraction (no full TOML parser needed)."""
    packages = {}
    in_deps = False
    for line in content.splitlines():
        if re.match(r'\[tool\.poetry\.dependencies\]|\[project\]', line):
            in_deps = True
            continue
        if line.startswith("[") and in_deps:
            in_deps = False
        if in_deps:
            match = re.match(r'"?([A-Za-z0-9_\-\.]+)"?\s*=\s*"([^"]*)"', line)
            if match:
                packages[match.group(1).lower()] = match.group(2)
    return packages


def _extract_version_number(ver_spec: str) -> Optional[str]:
    """Extract the base version number from a spec like ==1.2.3 or ^1.2.3."""
    match = re.search(r"(\d+)\.(\d+)\.?(\d*)", ver_spec)
    if match:
        return match.group(0)
    return None


def _check_cve(pkg: str, ver_spec: str) -> Optional[Dict]:
    """Check against hardcoded CVE list."""
    pkg_lower = pkg.lower()
    if pkg_lower not in KNOWN_VULNERABLE_PACKAGES:
        return None
    cve_info = KNOWN_VULNERABLE_PACKAGES[pkg_lower]
    current_ver = _extract_version_number(ver_spec)
    if not current_ver:
        return None  # Can't determine version, skip
    try:
        from packaging.version import Version
        if Version(current_ver) < Version(cve_info["below"]):
            return {
                "package": pkg,
                "current": current_ver,
                "below": cve_info["below"],
                "cve": cve_info["cve"],
            }
    except Exception:
        pass
    return None


async def _fetch_pypi_latest(pkg: str) -> Optional[str]:
    """Fetch the latest version of a package from PyPI."""
    try:
        async with httpx.AsyncClient(timeout=10) as client:
            resp = await client.get(f"https://pypi.org/pypi/{pkg}/json")
            if resp.status_code == 200:
                return resp.json()["info"]["version"]
    except Exception:
        pass
    return None


async def _fetch_npm_latest(pkg: str) -> Optional[str]:
    """Fetch the latest version of a package from npm registry."""
    try:
        async with httpx.AsyncClient(timeout=10) as client:
            resp = await client.get(f"https://registry.npmjs.org/{pkg}/latest")
            if resp.status_code == 200:
                return resp.json().get("version")
    except Exception:
        pass
    return None


async def run_dependency_agent(files_dict: Dict[str, str]) -> List[Finding]:
    """
    Parse dependency files, check CVEs + registry for outdated packages,
    then call Gemini to reason about the findings.
    """
    dep_content_parts = []
    all_packages: Dict[str, str] = {}  # pkg -> version spec
    is_node = False

    for path, content in files_dict.items():
        import os
        basename = os.path.basename(path)
        if basename == "requirements.txt":
            pkgs = _parse_requirements_txt(content)
            all_packages.update(pkgs)
            dep_content_parts.append(f"### {path} (Python)\n```\n{content}\n```")
        elif basename == "package.json":
            pkgs = _parse_package_json(content)
            all_packages.update(pkgs)
            is_node = True
            dep_content_parts.append(f"### {path} (Node.js)\n```\n{content}\n```")
        elif basename == "pyproject.toml":
            pkgs = _parse_pyproject_toml(content)
            all_packages.update(pkgs)
            dep_content_parts.append(f"### {path} (Python/pyproject)\n```\n{content}\n```")

    if not all_packages and not dep_content_parts:
        return []

    # CVE checks
    cve_hits = []
    for pkg, ver in all_packages.items():
        hit = _check_cve(pkg, ver)
        if hit:
            cve_hits.append(hit)

    # Registry checks (only for packages we have version info for — limit to 15)
    import asyncio
    registry_info = []
    check_pkgs = [(pkg, ver) for pkg, ver in list(all_packages.items())[:15] if ver]

    if is_node:
        latest_versions = await asyncio.gather(
            *[_fetch_npm_latest(pkg) for pkg, _ in check_pkgs],
            return_exceptions=True,
        )
    else:
        latest_versions = await asyncio.gather(
            *[_fetch_pypi_latest(pkg) for pkg, _ in check_pkgs],
            return_exceptions=True,
        )

    for (pkg, current_spec), latest in zip(check_pkgs, latest_versions):
        if isinstance(latest, Exception) or not latest:
            continue
        current_ver = _extract_version_number(current_spec)
        if not current_ver:
            continue
        try:
            from packaging.version import Version
            curr_v = Version(current_ver)
            latest_v = Version(latest)
            if curr_v.major < latest_v.major - 1:
                registry_info.append({
                    "package": pkg,
                    "current": current_ver,
                    "latest": latest,
                    "major_diff": latest_v.major - curr_v.major,
                })
        except Exception:
            continue

    # Build prompt context
    cve_text = "\n".join(
        f"- {h['package']} {h['current']} → {h['cve']} (fix: upgrade to >={h['below']})"
        for h in cve_hits
    ) or "(none)"

    registry_text = "\n".join(
        f"- {r['package']} {r['current']} → latest is {r['latest']} ({r['major_diff']} major versions behind)"
        for r in registry_info
    ) or "(no significantly outdated packages detected)"

    prompt = f"""## Dependency Files
{"".join(dep_content_parts)}

## Known CVE Matches
{cve_text}

## Significantly Outdated Packages (registry check)
{registry_text}

Analyze the above and return your dependency findings as a JSON array.
"""

    result = call_with_retry(
        model=MODEL,
        contents=prompt,
        config=types.GenerateContentConfig(
            system_instruction=DEPENDENCY_SYSTEM,
            temperature=0.1,
            response_mime_type="application/json",
        ),
    )

    from agents.security import _parse_findings
    return _parse_findings(result.text, agent="dependency")
