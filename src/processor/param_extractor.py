import re


class ParamExtractor:
    async def extract(self, text: str, intent: str) -> dict:
        params = {}

        if intent == "code_generation":
            params["language"] = self._detect_language(text)
            params["framework"] = self._detect_framework(text)
            params["description"] = text

        elif intent == "code_modification":
            params["file_path"] = self._extract_file_path(text)
            params["change_description"] = text

        elif intent == "bug_fix":
            params["file_path"] = self._extract_file_path(text)
            params["error_description"] = text

        return params

    def _detect_language(self, text: str) -> str:
        keywords = {
            "python": ["python", "py", "flask", "django", "fastapi"],
            "javascript": ["javascript", "js", "node", "react", "vue"],
            "typescript": ["typescript", "ts", "angular", "nest"],
            "java": ["java", "spring", "maven"],
            "go": ["go", "golang"],
            "rust": ["rust", "cargo"],
        }
        text_lower = text.lower()
        for lang, words in keywords.items():
            if any(w in text_lower for w in words):
                return lang
        return "unknown"

    def _detect_framework(self, text: str) -> str:
        frameworks = ["fastapi", "flask", "django", "react", "vue", "spring", "express"]
        for fw in frameworks:
            if fw in text.lower():
                return fw
        return ""

    def _extract_file_path(self, text: str) -> str:
        # Match both forward-slash and backslash paths
        paths = re.findall(r'[\w/\\\-]+\.[a-zA-Z]+', text)
        return paths[0] if paths else ""
