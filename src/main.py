import asyncio
import logging
import os
import sys
from pathlib import Path

import yaml

from src.engines.opencode_engine import OpencodeEngine
from src.engines.claude_code_engine import ClaudeCodeEngine
from src.engines.hermes_engine import HermesDirectEngine
from src.evolution.self_upgrade import SelfUpgradeEngine
from src.memory.memory_store import MemoryStore
from src.plugin.plugin_manager import PluginManager
from src.executor.iterative_executor import IterativeExecutor
from src.im_gateway.feishu.adapter import FeishuAdapter
from src.llm import LLMClient, LLMConfig
from src.operator.ide_launcher import IDELauncher
from src.operator.db_client import DatabaseClient, DatabaseConfig
from src.operator.system_ops import SystemOperator
from src.processor.intent_recognizer import IntentRecognizer
from src.processor.project_matcher import ProjectMatcher
from src.processor.context_manager import ContextManager
from src.processor.context_compressor import ContextCompressor
from src.orchestrator.task_planner import TaskPlanner
from src.scanner.project_scanner import ProjectScanner
from src.skills.registry import SkillRegistry
from src.skills.base import SkillContext
from src.skills.generator import SkillGenerator

logger = logging.getLogger("hermes")


def _get_hermes_root() -> Path:
    return Path(__file__).parent.parent


def load_config() -> dict:
    config_path = _get_hermes_root() / "config" / "default.yaml"
    with open(config_path, encoding="utf-8") as f:
        return yaml.safe_load(f)


def load_env(env_path: Path):
    """Load .env file into os.environ"""
    if not env_path.exists():
        logger.warning(f".env file not found at {env_path}")
        return
    with open(env_path, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, _, value = line.partition("=")
            key = key.strip()
            value = value.strip().strip('"').strip("'")
            if key and key not in os.environ:
                os.environ[key] = value


def resolve_config(config: dict) -> dict:
    def _walk(obj):
        if isinstance(obj, dict):
            return {k: _walk(v) for k, v in obj.items()}
        if isinstance(obj, str) and obj.startswith("${") and obj.endswith("}"):
            return os.environ.get(obj[2:-1], obj)
        return obj
    return _walk(config)


def setup_logging(level: str):
    logging.basicConfig(
        level=getattr(logging, level.upper()),
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    )


class Hermes:
    def __init__(self, config: dict):
        self.config = config
        self.root = _get_hermes_root()
        self.llm_client = None
        self.scanner = None
        self.matcher = None
        self.recognizer = None
        self.planner = None
        self.upgrader = SelfUpgradeEngine(str(self.root))
        self.engines: dict[str, OpencodeEngine | ClaudeCodeEngine] = {}
        self.ide_launcher = IDELauncher()
        self.db_client = DatabaseClient()
        self.system_ops = SystemOperator()
        self.feishu_adapter = None
        self._feishu_webhook = None
        self._last_task: dict | None = None
        self.skill_registry = SkillRegistry()
        self.skill_generator = None
        self.evolution_recorder = None
        self.context_manager = ContextManager(
            db_path=str(self.root / "data" / "context" / "sessions.db")
        )
        self.context_compressor = None
        self.memory = None
        self.plugin_manager = None
        self.iterative_executor = None

    async def initialize(self):
        resolved = resolve_config(self.config)
        logger.info("=" * 50)
        logger.info(f"Hermes v{__import__('src.evolution.self_upgrade', fromlist=['HERMES_VERSION']).HERMES_VERSION}")
        logger.info("=" * 50)

        # ── Step 0: Self-Upgrade check ──
        version_info = await self.upgrader.check_version()
        if version_info["upgraded"]:
            logger.info(f"📦 Upgraded from {version_info['previous']} to {version_info['current']}")

        # ── Step 1: Init LLM ──
        ai_cfg = resolved.get("ai", {})
        if ai_cfg.get("api_key"):
            llm_config = LLMConfig.from_dict(ai_cfg)
            self.llm_client = LLMClient(llm_config)
            await self.llm_client.initialize()
            logger.info(f"✅ AI: {llm_config.provider} / {llm_config.model}")
        else:
            self.llm_client = None
            logger.warning("⚠️  No AI configured — fallback defaults will be used")

        # ── Step 2: Scan projects ──
        workspace_root = resolved.get("workspace_root", "")
        if not workspace_root:
            # Default to parent of hermes root or cwd
            candidates = [str(self.root.parent), os.getcwd()]
            for c in candidates:
                root = Path(c)
                if root.exists() and any(d.is_dir() and not d.name.startswith(".") for d in root.iterdir()):
                    workspace_root = str(root.resolve())
                    break
            if not workspace_root:
                workspace_root = os.getcwd()

        self.scanner = ProjectScanner(workspace_root=workspace_root)
        projects = await self.scanner.scan_all(depth=3)
        logger.info(f"✅ Projects: {len(projects)} scanned from {workspace_root}")
        if projects:
            for p in sorted(projects.values(), key=lambda x: x.name):
                lang = p.language or "?"
                logger.info(f"   📁 {p.name:25s} {lang:15s} {p.path}")
            logger.info("  💡 说项目名即可自动匹配（支持模糊搜索）")
        else:
            logger.info("  ⚠️  No projects found. You can still reference projects by path.")

        # ── Step 3: Load database configs ──
        db_config_path = resolved.get("databases_config", "./config/databases.yaml")
        self.db_client.load_configs(str(self.root / db_config_path))
        dbs = self.db_client.list_databases()
        if dbs:
            logger.info(f"✅ Databases: {len(dbs)} configured")
            for db in dbs:
                logger.info(f"   🗄️  {db['name']:20s} {db['type']:15s}")

        # ── Step 4: Init processors ──
        self.matcher = ProjectMatcher(self.scanner, self.llm_client)
        self.recognizer = IntentRecognizer(self.llm_client)

        # ── Step 5: Init planner ──
        self.planner = TaskPlanner(project_matcher=self.matcher)

        # ── Step 6: Init engines ──
        engine_cfg = resolved.get("engines", {})
        self.engines["opencode"] = OpencodeEngine(
            executable=engine_cfg.get("opencode", {}).get("executable", "opencode"),
            timeout=engine_cfg.get("opencode", {}).get("timeout", 600),
        )
        self.engines["claude_code"] = ClaudeCodeEngine(
            executable=engine_cfg.get("claude_code", {}).get("executable", "claude"),
            timeout=engine_cfg.get("claude_code", {}).get("timeout", 600),
        )

        # ── Step 7: Init Context System ──
        self.context_compressor = ContextCompressor(llm_client=self.llm_client)
        await self.context_manager.initialize()

        # ── Step 8: Init Feishu ──
        feishu_cfg = resolved.get("im", {}).get("feishu", {})
        if feishu_cfg.get("app_id"):
            self.feishu_adapter = FeishuAdapter(
                app_id=feishu_cfg["app_id"],
                app_secret=feishu_cfg.get("app_secret", ""),
                verification_token=feishu_cfg.get("verification_token", ""),
                encrypt_key=feishu_cfg.get("encrypt_key", ""),
            )
            await self.feishu_adapter.initialize()
            logger.info("✅ Feishu adapter ready")

        # ── Step 9: Discover Skills ──
        logger.info("📦 Discovering skills...")
        self.skill_registry.discover(
            str(self.root / "src" / "skills" / "builtin"),
            str(self.root / "custom_skills"),
        )
        loaded = self.skill_registry.get_all()
        logger.info(f"✅ Loaded {len(loaded)} skills: {[s.name for s in loaded]}")

        # ── Step 10: Initialize Skill Generator ──
        self.skill_generator = SkillGenerator(
            llm_client=self.llm_client,
            skill_registry=self.skill_registry,
            output_dir=str(self.root / "custom_skills"),
        )
        logger.info("  🤖 Skill generator ready (auto-create on demand)")

        # ── Step 11: Initialize Evolution System ──
        from src.evolution.evolution_recorder import EvolutionRecorder
        self.evolution_recorder = EvolutionRecorder(
            data_dir=str(self.root / "data" / "evolution")
        )
        stats = self.evolution_recorder.get_stats()
        if stats.get("total", 0) > 0:
            logger.info(f"  📊 Evolution: {stats['total']} tasks, {stats['success_rate']}% success")

        # ── Step 12: Initialize Memory System ──
        self.memory = MemoryStore(db_path=str(self.root / "data" / "memory" / "hermes.db"))
        await self.memory.initialize()
        mem_stats = await self.memory.get_stats()
        if mem_stats.get("total", 0) > 0:
            logger.info(f"  🧠 Memory: {mem_stats['total']} entries")

        # ── Step 13: Initialize Plugin System ──
        self.plugin_manager = PluginManager(
            str(self.root / "plugins"),
        )
        plugins = self.plugin_manager.discover()
        if plugins:
            logger.info(f"  🔌 Plugins: {len(plugins)} loaded")
            await self.plugin_manager.install_dependencies(self.upgrader)
            self.skill_registry.discover(*self.plugin_manager.get_skill_paths())

        # ── Step 14: Initialize Iterative Executor ──
        self.iterative_executor = IterativeExecutor(
            llm_client=self.llm_client,
            system_ops=self.system_ops,
        )

        # ── Step 15: Register MCP servers if needed ──
        await self.upgrader.register_mcp_server(
            "code-review-graph",
            "node",
            args=["@anthropic/mcp-server-code-review-graph"],
        )

        logger.info("✅ All systems ready")
        logger.info("🚀 Hermes is ready!")

    async def start_feishu_ws(self):
        if not self.feishu_adapter:
            logger.info("Feishu not configured, skipping")
            return

        self.feishu_adapter.start_ws(self._on_feishu_message)
        logger.info("✅ Feishu WebSocket started (no ngrok needed!)")

    async def _on_feishu_message(self, user_id: str, text: str):
        logger.info(f"📩 Processing Feishu message from {user_id}: {text[:80]}")
        async for chunk in self.process_message(user_id, text):
            await self.feishu_adapter.send_message(user_id, chunk)

    async def process_message(self, user_id: str, text: str):
        logger.info(f"📩 {user_id}: {text[:120]}")

        # ── Retry / 修复处理（在意图识别之前）──
        is_retry = any(kw in text for kw in ["报错了", "修复", "重试", "retry"])
        if is_retry and self._last_task:
            orig = self._last_task.get("text", "")
            if orig:
                yield f"🔧 正在重试上次操作: {orig[:60]}..."
                async for chunk in self.process_message(user_id, orig):
                    yield chunk
                return

        # ── 记录用户消息到上下文 ──
        self.context_manager.add_turn(user_id, "user", text)

        # ── Step 1: Recognize intent ──
        intent_result = await self.recognizer.recognize(text)
        intent = intent_result.get("intent", "chat")
        params = intent_result.get("params", {})

        # 记录最后任务（供修复使用）
        self._last_task = {"user_id": user_id, "text": text, "intent": intent}

        # ── 构建上下文注入 ──
        session = self.context_manager.get_or_create_session(user_id)
        session_str = session.to_system_prompt()
        # 如果对话过长，压缩历史
        if len(session.turns) > 15 and self.context_compressor:
            compressed = await self.context_compressor.compress(session.turns, budget=10)
            session.turns = compressed

        # ── Step 2: Find matching skill ──
        ctx = SkillContext(
            text=text,
            intent=intent,
            params=params,
            user_id=user_id,
            hermes=self,
            context_str=session_str,
        )
        skill = await self.skill_registry.find_skill(ctx)

        if skill:
            logger.info(f"🎯 Skill: {skill.name}")
            response_parts = []
            async for chunk in skill.execute(ctx):
                response_parts.append(chunk)
                yield chunk
            # 记录 Hermes 回复到上下文
            full_response = "\n".join(response_parts)
            if full_response.strip():
                self.context_manager.add_turn(user_id, "assistant", full_response[:500])
        else:
            msg = "🤖 抱歉，没有找到能处理这个请求的技能。"
            self.context_manager.add_turn(user_id, "assistant", msg)
            yield msg

        # 持久化当前会话
        await self.context_manager.persist_session(user_id)

    async def _execute_with_stream(self, engine, instruction, workspace=None):
        from pathlib import Path as _Path
        import shutil as _shutil
        import sys as _sys

        project_dir = _Path(workspace) if workspace else _Path.cwd()
        if not project_dir.exists():
            yield f"项目目录不存在: {project_dir}"
            return

        # Resolve executable path (handle .cmd wrappers on Windows)
        exe = engine.executable
        resolved = _shutil.which(exe)
        if not resolved:
            # Try with .cmd extension on Windows
            if _sys.platform == "win32":
                resolved = _shutil.which(exe + ".cmd")
            if not resolved:
                yield f"❌ 未找到 {exe}，请确认已安装并在 PATH 中"
                return

        try:
            # On Windows, .cmd files must be run via shell
            if _sys.platform == "win32" and resolved.endswith(".cmd"):
                cmd = f'cd /d "{project_dir}" && "{resolved}" {instruction}'
                process = await asyncio.create_subprocess_shell(
                    cmd,
                    stdout=asyncio.subprocess.PIPE,
                    stderr=asyncio.subprocess.STDOUT,
                )
            else:
                process = await asyncio.create_subprocess_exec(
                    resolved,
                    instruction,
                    cwd=str(project_dir),
                    stdout=asyncio.subprocess.PIPE,
                    stderr=asyncio.subprocess.STDOUT,
                )

            while True:
                line = await process.stdout.readline()
                if not line:
                    break
                yield line.decode("utf-8", errors="replace").rstrip()

            await process.wait()
        except Exception as e:
            yield f"❌ 执行异常: {e}"


async def main():
    # Load .env before doing anything else
    load_env(_get_hermes_root() / ".env")

    config = load_config()
    resolved = resolve_config(config)
    setup_logging(resolved.get("server", {}).get("log_level", "INFO"))

    hermes = Hermes(config)
    await hermes.initialize()

    # Start Feishu WebSocket (no ngrok needed!)
    await hermes.start_feishu_ws()

    logger.info("")
    logger.info("=" * 50)
    logger.info("Interactive CLI Mode — enter 'exit' to quit")
    if hermes.feishu_adapter:
        logger.info("  📡 飞书 Bot 已在线 — 发送消息到飞书即可交互")
    # Show evolution stats
    if hermes.evolution_recorder:
        stats = hermes.evolution_recorder.get_stats()
        if stats.get("total", 0) > 0:
            logger.info(f"  📚 进化记录: {stats['total']} 次 | 成功率 {stats['success_rate']}%")
    logger.info("")
    logger.info("  💻 给 agent 项目加个 .gitignore")
    logger.info("  🖥️  用 idea 打开 agent 项目")
    logger.info("  🗄️  查一下 users 表")
    logger.info("  📦  安装 pandas")
    logger.info("=" * 50)

    while True:
        try:
            text = input("\n💬 > ").strip()
            if text.lower() in ("exit", "quit", "q"):
                break
            if not text:
                continue

            async for chunk in hermes.process_message("cli_user", text):
                print(chunk)

        except KeyboardInterrupt:
            break
        except Exception as e:
            logger.error(f"Error: {e}", exc_info=True)

    logger.info("Hermes shutting down...")


if __name__ == "__main__":
    asyncio.run(main())
