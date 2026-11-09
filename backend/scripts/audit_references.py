import os

search_terms = [
    "INST_NSE_TATAMOTORS_HIST",
    "INST_NSE_TMPV",
    "INST_NSE_TATAMOTORS",
    "TATAMOTORS",
    "TMPV",
    "TMCV",
    "3456",
    "COST_APPORTIONMENT",
    "PROHIBITED_MERGE",
]

matches = {term: [] for term in search_terms}

ignore_dirs = {".git", "node_modules", ".venv", "__pycache__", ".pytest_cache", "dist"}

for root, dirs, files in os.walk("."):
    dirs[:] = [d for d in dirs if d not in ignore_dirs]
    for file in files:
        if file.endswith((".py", ".ts", ".tsx", ".json", ".sql")):
            path = os.path.join(root, file)
            try:
                with open(path, "r", encoding="utf-8") as f:
                    content = f.read()
                    for term in search_terms:
                        if term in content:
                            matches[term].append(path)
            except Exception:
                pass

print("=== Search Results Across Codebase ===")
for term, file_list in matches.items():
    print(f"\nTerm '{term}' found in {len(file_list)} files:")
    for p in file_list[:10]:
        print(f"  {p}")
    if len(file_list) > 10:
        print(f"  ... and {len(file_list) - 10} more files")
