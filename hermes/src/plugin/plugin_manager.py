"""
Plugin Manager — Hermes 插件管理体系
====================================
每个插件是一个目录，包含 plugin.yaml 和 .py 文件。

插件目录结构：
plugins/
  my_plugin/
    plugin.yaml    # 元数据
    *.py           # Skill 代码（自动加载到技能系统）

plugin.yaml 格式：
name: my_plugin
version: 1.0.0
description: 我的插件
author: user
dependencies:
  - pandas
  - pillow
"""
import json
import logging
import os
from pathlib import Path

import yaml

logger = logging.getLogger("hermes.plugin")


class PluginInfo:
    def __init__(self, path: str):
        self.path = Path(path)
        self.name = self.path.name
        self.version = "0.1.0"
        self.description = ""
        self.author = ""
        self.dependencies: list[str] = []
        self.enabled = True
        self._load_metadata()

    def _load_metadata(self):
        yaml_path = self.path / "plugin.yaml"
        if yaml_path.exists():
            try:
                with open(yaml_path, encoding="utf-8") as f:
                    data = yaml.safe_load(f) or {}
                self.name = data.get("name", self.name)
                self.version = data.get("version", "0.1.0")
                self.description = data.get("description", "")
                self.author = data.get("author", "")
                self.dependencies = data.get("dependencies", [])
            except Exception as e:
                logger.warning(f"Failed to load {yaml_path}: {e}")

    def __repr__(self):
        return f"Plugin({self.name} v{self.version})"


class PluginManager:
    def __init__(self, *plugin_dirs: str):
        self._dirs = [Path(d) for d in plugin_dirs]
        self._plugins: dict[str, PluginInfo] = {}

    def discover(self):
        for d in self._dirs:
            if not d.exists():
                d.mkdir(parents=True, exist_ok=True)
            for child in sorted(d.iterdir()):
                if child.is_dir() and not child.name.startswith("_"):
                    info = PluginInfo(str(child))
                    self._plugins[info.name] = info
                    logger.info(f"  📦 Plugin: {info}")
        return self._plugins

    def get(self, name: str) -> PluginInfo | None:
        return self._plugins.get(name)

    def get_all(self) -> list[PluginInfo]:
        return list(self._plugins.values())

    def get_skill_paths(self) -> list[str]:
        """Get all plugin directories as skill discovery paths"""
        return [str(p.path) for p in self._plugins.values() if p.enabled]

    async def install_dependencies(self, upgrader) -> list[dict]:
        """Install all plugin dependencies"""
        all_deps = []
        for plugin in self._plugins.values():
            all_deps.extend(plugin.dependencies)
        if all_deps:
            return await upgrader.ensure_dependencies(list(set(all_deps)))
        return []
