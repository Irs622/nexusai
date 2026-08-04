import ast
import os
from pathlib import Path

SRC_DIR = Path(__file__).parent.parent / "src" / "nexusai"

def parse_file_imports(filepath):
    try:
        with open(filepath, "r", encoding="utf-8") as f:
            tree = ast.parse(f.read(), filename=str(filepath))
    except Exception as e:
        print(f"Error parsing {filepath}: {e}")
        return []

    imports = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                imports.append((node.lineno, alias.name, "", alias.name))
        elif isinstance(node, ast.ImportFrom):
            module = node.module or ""
            for alias in node.names:
                full_import = f"{module}.{alias.name}" if module else alias.name
                imports.append((node.lineno, full_import, module, alias.name))
    return imports

def audit():
    print("=== NexusAI Import Dependency Audit ===")
    all_files = list(SRC_DIR.glob("**/*.py"))
    print(f"Total Python files in src/nexusai: {len(all_files)}\n")

    CONCRETE_PROVIDERS = {
        "OpenAIProvider", "OpenRouterProvider", "GeminiProvider",
        "AnthropicProvider", "OllamaProvider"
    }
    CONCRETE_MODULES = {"openrouter", "gemini", "anthropic", "ollama"}
    FORBIDDEN_PACKAGES = {"runtime", "brain", "memory", "workflow", "automation"}

    violations = []

    for py_file in all_files:
        rel_path = py_file.relative_to(SRC_DIR)
        parts = rel_path.parts
        pkg = parts[0] if parts else ""

        imports = parse_file_imports(py_file)

        for item in imports:
            lineno, full_imp, module, imported_symbol = item[0], item[1], item[2], item[3]

            # Rule A001: providers MUST NOT import runtime, brain, memory, workflow, automation
            if pkg == "providers":
                for forbidden in FORBIDDEN_PACKAGES:
                    if f"nexusai.{forbidden}" in full_imp or module.startswith(f"nexusai.{forbidden}"):
                        violations.append(("A001", str(rel_path), lineno, full_imp, f"providers package MUST NOT import nexusai.{forbidden}"))

            # Rule A002: runtime MUST NOT import concrete provider adapters
            if pkg == "runtime":
                for concrete_mod in CONCRETE_MODULES:
                    if f"nexusai.providers.{concrete_mod}" in full_imp or module.startswith(f"nexusai.providers.{concrete_mod}"):
                        violations.append(("A002", str(rel_path), lineno, full_imp, f"runtime MUST NOT import concrete provider module '{concrete_mod}'"))
                if imported_symbol in CONCRETE_PROVIDERS:
                    violations.append(("A002", str(rel_path), lineno, full_imp, f"runtime MUST NOT import concrete provider class '{imported_symbol}'"))

            # Rule A003: brain MUST NOT import concrete provider adapters
            if pkg == "brain":
                for concrete_mod in CONCRETE_MODULES:
                    if f"nexusai.providers.{concrete_mod}" in full_imp or module.startswith(f"nexusai.providers.{concrete_mod}"):
                        violations.append(("A003", str(rel_path), lineno, full_imp, f"brain MUST NOT import concrete provider module '{concrete_mod}'"))
                if imported_symbol in CONCRETE_PROVIDERS:
                    violations.append(("A003", str(rel_path), lineno, full_imp, f"brain MUST NOT import concrete provider class '{imported_symbol}'"))

            # Rule A004: memory MUST NOT import providers
            if pkg == "memory":
                if "nexusai.providers" in full_imp or module.startswith("nexusai.providers"):
                    violations.append(("A004", str(rel_path), lineno, full_imp, "memory MUST NOT import nexusai.providers"))

            # Rule A005: workflow MUST NOT import concrete provider adapters
            if pkg == "workflow":
                for concrete_mod in CONCRETE_MODULES:
                    if f"nexusai.providers.{concrete_mod}" in full_imp or module.startswith(f"nexusai.providers.{concrete_mod}"):
                        violations.append(("A005", str(rel_path), lineno, full_imp, f"workflow MUST NOT import concrete provider module '{concrete_mod}'"))
                if imported_symbol in CONCRETE_PROVIDERS:
                    violations.append(("A005", str(rel_path), lineno, full_imp, f"workflow MUST NOT import concrete provider class '{imported_symbol}'"))

            # Rule A006: security MUST NOT import concrete provider adapters
            if pkg == "security":
                for concrete_mod in CONCRETE_MODULES:
                    if f"nexusai.providers.{concrete_mod}" in full_imp or module.startswith(f"nexusai.providers.{concrete_mod}"):
                        violations.append(("A006", str(rel_path), lineno, full_imp, f"security MUST NOT import concrete provider module '{concrete_mod}'"))
                if imported_symbol in CONCRETE_PROVIDERS:
                    violations.append(("A006", str(rel_path), lineno, full_imp, f"security MUST NOT import concrete provider class '{imported_symbol}'"))

    print(f"Audit completed across {len(all_files)} files. Total Violations Found: {len(violations)}\n")
    if violations:
        for v in violations:
            print(f"❌ [Rule {v[0]}] src/nexusai/{v[1]}:{v[2]} imports '{v[3]}' --> {v[4]}")
    else:
        print("✅ CLEAN AUDIT! Zero architecture boundary violations detected across src/nexusai.")

if __name__ == "__main__":
    audit()
