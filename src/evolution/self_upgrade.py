"""
Hermes Self-Upgrade Engine
==========================
Capabilities:
  1. Auto-install missing pip dependencies when needed
  2. Auto-configure MCP servers in opencode/Claude Code config
  3. Auto-register skills in AGENTS.md
  4. Graceful self-restart
  5. Config hot-reload
  6. Version tracking
"""

import asyncio
import json
import logging
import os
import subprocess
import sys
from datetime import datetime
from pathlib import Path
from typing import Optional

logger = logging.getLogger("hermes.evolution.upgrade")

HERMES_VERSION = "0.1.0"


class SelfUpgradeEngine:
    def __init__(self, hermes_root: str):
        self.root = Path(hermes_root)
        self.version_file = self.root / ".hermes_version"
        self.state_file = self.root / "data" / ".upgrade_state.json"
        self._restart_requested = False

    # ──────────────────────────────────────────────
    # 1. Dependency Auto-Install
    # ──────────────────────────────────────────────

    async def ensure_dependencies(self, packages: list[str]) -> list[dict]:
        results = []
        for pkg in packages:
            if self._is_installed(pkg):
                results.append({"package": pkg, "action": "skipped", "reason": "already installed"})
                continue

            logger.info(f"Installing missing dependency: {pkg}")
            try:
                proc = await asyncio.create_subprocess_exec(
                    sys.executable, "-m", "pip", "install", pkg,
                    stdout=asyncio.subprocess.PIPE,
                    stderr=asyncio.subprocess.PIPE,
                )
                stdout, stderr = await proc.communicate()

                if proc.returncode == 0:
                    results.append({"package": pkg, "action": "installed", "success": True})
                    self._record_event("dependency_installed", {"package": pkg})
                    logger.info(f"✅ Installed: {pkg}")
                else:
                    results.append({
                        "package": pkg, "action": "failed",
                        "error": stderr.decode("utf-8", errors="replace")[:200],
                    })
                    logger.warning(f"❌ Failed to install {pkg}: {stderr.decode()[:100]}")
            except Exception as e:
                results.append({"package": pkg, "action": "error", "error": str(e)})

        return results

    def _is_installed(self, package: str) -> bool:
        try:
            # Extract base package name (remove version specifiers like >=1.0)
            pkg_name = package.split(">=")[0].split("==")[0].split("[")[0].strip()
            __import__(pkg_name.replace("-", "_"))
            return True
        except ImportError:
            pass
        # Also check via pip
        try:
            result = subprocess.run(
                [sys.executable, "-m", "pip", "show", pkg_name],
                capture_output=True, text=True, timeout=10,
            )
            return result.returncode == 0
        except Exception:
            return False

    # ──────────────────────────────────────────────
    # 2. MCP Server Auto-Configuration
    # ──────────────────────────────────────────────

    async def register_mcp_server(self, name: str, command: str, args: list[str] | None = None,
                                   env: dict | None = None) -> dict:
        # Detect which config files to update
        configs = self._find_mcp_configs()
        results = []

        for config_path in configs:
            try:
                config = json.loads(config_path.read_text(encoding="utf-8"))
            except (FileNotFoundError, json.JSONDecodeError):
                config = {}

            if "mcpServers" not in config:
                config["mcpServers"] = {}

            if name in config["mcpServers"]:
                results.append({"config": str(config_path), "action": "skipped", "reason": "already exists"})
                continue

            server_entry = {"command": command}
            if args:
                server_entry["args"] = args
            if env:
                server_entry["env"] = env

            config["mcpServers"][name] = server_entry
            config_path.write_text(json.dumps(config, indent=2, ensure_ascii=False), encoding="utf-8")
            results.append({"config": str(config_path), "action": "registered", "mcp": name})
            self._record_event("mcp_registered", {"name": name, "config": str(config_path)})
            logger.info(f"✅ Registered MCP server '{name}' in {config_path.name}")

        return results

    def _find_mcp_configs(self) -> list[Path]:
        configs = []

        # Check opencode config
        opencode_configs = [
            Path.home() / ".opencode.json",
            self.root / ".opencode.json",
        ]
        for p in opencode_configs:
            if p.exists():
                configs.append(p)

        # Check Claude Code config
        claude_dirs = [
            Path.home() / ".claude",
            self.root / ".claude",
        ]
        for d in claude_dirs:
            if d.exists():
                for f in d.iterdir():
                    if f.suffix == ".json" or f.name == "settings.json":
                        configs.append(f)

        # Check .cursor MCP config
        cursor_config = Path.home() / ".cursor" / "mcp.json"
        if cursor_config.exists():
            configs.append(cursor_config)
        cursor_local = self.root / ".cursor" / "mcp.json"
        if cursor_local.exists():
            configs.append(cursor_local)

        return configs

    # ──────────────────────────────────────────────
    # 3. Skills Auto-Registration in AGENTS.md
    # ──────────────────────────────────────────────

    async def register_skill(self, skill_path: str, description: str = "") -> dict:
        agents_file = self.root / "AGENTS.md"
        skill_line = f"- {skill_path}: {description}" if description else f"- {skill_path}"

        if not agents_file.exists():
            content = f"# Hermes Auto-Managed Skills\n<!-- hermes-auto-generated -->\n{skill_line}\n"
            agents_file.write_text(content, encoding="utf-8")
            self._record_event("skill_registered", {"path": skill_path})
            return {"action": "created", "file": str(agents_file), "skill": skill_path}

        content = agents_file.read_text(encoding="utf-8")

        if skill_line in content:
            return {"action": "skipped", "reason": "already registered"}

        if "<!-- hermes-auto-generated -->" in content:
            content = content.replace(
                "<!-- hermes-auto-generated -->",
                f"<!-- hermes-auto-generated -->\n{skill_line}"
            )
        else:
            content += f"\n<!-- hermes-auto-generated -->\n{skill_line}\n"

        agents_file.write_text(content, encoding="utf-8")
        self._record_event("skill_registered", {"path": skill_path})
        logger.info(f"✅ Registered skill: {skill_path}")
        return {"action": "registered", "file": str(agents_file), "skill": skill_path}

    # ──────────────────────────────────────────────
    # 4. Graceful Self-Restart
    # ──────────────────────────────────────────────

    async def request_restart(self, reason: str = ""):
        self._restart_requested = True
        self._record_event("restart_requested", {"reason": reason})
        logger.info(f"🔄 Restart requested: {reason}")

        # Write restart flag
        self.state_file.parent.mkdir(parents=True, exist_ok=True)
        state = {
            "restart": True,
            "reason": reason,
            "timestamp": datetime.utcnow().isoformat(),
        }
        self.state_file.write_text(json.dumps(state), encoding="utf-8")

    async def perform_restart(self):
        """Restart the Hermes process"""
        logger.info("🔄 Performing self-restart...")
        await asyncio.sleep(1)

        # Remove restart flag
        if self.state_file.exists():
            self.state_file.unlink()

        # Restart with same arguments
        os.execl(sys.executable, sys.executable, *sys.argv)

    def should_restart(self) -> bool:
        if self._restart_requested:
            return True
        if self.state_file.exists():
            try:
                state = json.loads(self.state_file.read_text(encoding="utf-8"))
                return state.get("restart", False)
            except Exception:
                pass
        return False

    # ──────────────────────────────────────────────
    # 5. Config Hot-Reload
    # ──────────────────────────────────────────────

    async def hot_reload_config(self, config_path: str) -> dict:
        import yaml
        path = Path(config_path)
        if not path.exists():
            return {"success": False, "message": f"Config not found: {config_path}"}

        with open(path, encoding="utf-8") as f:
            config = yaml.safe_load(f)

        self._record_event("config_reloaded", {"path": config_path})
        logger.info(f"🔄 Config hot-reloaded: {config_path}")
        return {"success": True, "config": config}

    # ──────────────────────────────────────────────
    # 6. Version Tracking
    # ──────────────────────────────────────────────

    async def check_version(self) -> dict:
        current = HERMES_VERSION
        previous = ""
        if self.version_file.exists():
            previous = self.version_file.read_text(encoding="utf-8").strip()

        upgraded = previous and previous != current

        self.version_file.write_text(current, encoding="utf-8")

        if upgraded:
            self._record_event("version_upgraded", {
                "from": previous, "to": current,
                "timestamp": datetime.utcnow().isoformat(),
            })
            logger.info(f"📦 Version upgraded: {previous} → {current}")

        return {
            "current": current,
            "previous": previous or "(first run)",
            "upgraded": upgraded,
        }

    # ──────────────────────────────────────────────
    # Internal
    # ──────────────────────────────────────────────

    def _record_event(self, event_type: str, data: dict):
        events_file = self.root / "data" / "events.jsonl"
        events_file.parent.mkdir(parents=True, exist_ok=True)
        record = {
            "type": event_type,
            "data": data,
            "timestamp": datetime.utcnow().isoformat(),
        }
        with open(events_file, "a", encoding="utf-8") as f:
            f.write(json.dumps(record, ensure_ascii=False) + "\n")

    def get_upgrade_history(self, limit: int = 20) -> list[dict]:
        events_file = self.root / "data" / "events.jsonl"
        if not events_file.exists():
            return []

        events = []
        with open(events_file, encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line:
                    try:
                        events.append(json.loads(line))
                    except json.JSONDecodeError:
                        continue

        return events[-limit:]
