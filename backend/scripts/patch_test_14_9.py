with open("backend/tests/test_phase14_9_instrument_master.py", "r", encoding="utf-8") as f:
    content = f.read()

content = content.replace('assert lti["instrument_id"] == "INST_NSE_LTM"', 'assert lti["instrument_id"] == "INST_NSE_LTIM"')
content = content.replace('assert mindtree["instrument_id"] == "INST_NSE_LTM"', 'assert mindtree["instrument_id"] == "INST_NSE_LTIM"')
content = content.replace('assert ltm["instrument_id"] == "INST_NSE_LTM"', 'assert ltm["instrument_id"] == "INST_NSE_LTIM"')
content = content.replace('a["instrument_id"] == "INST_NSE_LTM"', 'a["instrument_id"] == "INST_NSE_LTIM"')
content = content.replace('assert det["instrument"]["instrument_id"] == "INST_NSE_LTM"', 'assert det["instrument"]["instrument_id"] == "INST_NSE_LTIM"')

with open("backend/tests/test_phase14_9_instrument_master.py", "w", encoding="utf-8") as f:
    f.write(content)

print("Updated test_phase14_9_instrument_master.py with canonical INST_NSE_LTIM")
