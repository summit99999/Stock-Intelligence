with open("backend/tests/test_phase14_9_1_instrument_corrections.py", "r", encoding="utf-8") as f:
    content = f.read()

# 1. Update instrument_id assertions to INST_NSE_LTIM
content = content.replace('assert inst["instrument_id"] == "INST_NSE_LTM"', 'assert inst["instrument_id"] == "INST_NSE_LTIM"')
content = content.replace('assert by_ltm["instrument_id"] == "INST_NSE_LTM"', 'assert by_ltm["instrument_id"] == "INST_NSE_LTIM"')
content = content.replace('assert by_ltim["instrument_id"] == "INST_NSE_LTM"', 'assert by_ltim["instrument_id"] == "INST_NSE_LTIM"')
content = content.replace('assert by_legacy_id["instrument_id"] == "INST_NSE_LTM"', 'assert by_legacy_id["instrument_id"] == "INST_NSE_LTIM"')
content = content.replace('assert rows[0][0] == "INST_NSE_LTM"', 'assert rows[0][0] == "INST_NSE_LTIM"')

# 2. Update cost allocation ratios to 0.6885 and 0.3115
content = content.replace('assert cost_tmpv["adjustment_factor_applied"] == 0.407', 'assert cost_tmpv["adjustment_factor_applied"] == 0.6885')
content = content.replace('assert cost_tmcv["adjustment_factor_applied"] == 0.593', 'assert cost_tmcv["adjustment_factor_applied"] == 0.3115')

# 3. Update actions count to 4 (including HAL split)
content = content.replace('assert len(actions) == 3', 'assert len(actions) == 4')
content = content.replace(
    '        "CA_LTM_SYMBOL_CHANGE_2026",\n    }',
    '        "CA_LTM_SYMBOL_CHANGE_2026",\n        "CA_HAL_SPLIT_2023",\n    }'
)

with open("backend/tests/test_phase14_9_1_instrument_corrections.py", "w", encoding="utf-8") as f:
    f.write(content)

print("Updated test_phase14_9_1_instrument_corrections.py successfully")
