with open("backend/tests/test_phase14_9_instrument_master.py", "r", encoding="utf-8") as f:
    content = f.read()

target = 'assert ltim["instrument_id"] == "INST_NSE_LTM"'
replacement = 'assert ltim["instrument_id"] == "INST_NSE_LTIM"'
assert target in content, "target not found"
content = content.replace(target, replacement, 1)

with open("backend/tests/test_phase14_9_instrument_master.py", "w", encoding="utf-8") as f:
    f.write(content)

print("Line 130 patched successfully.")
