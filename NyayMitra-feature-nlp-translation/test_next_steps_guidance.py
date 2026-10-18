from next_steps_guidance_lookup import get_next_steps, load_guidance_data

def test_all_rules_match():
    data = load_guidance_data()
    failures = []
    for rule in data["guidance_v2"]:
        result = get_next_steps(rule["case_stage"])
        if not result["matched"]:
            failures.append(rule["case_stage"])
    assert not failures, f"These case stages did not match: {failures}"
    print(f"PASS: all {len(data['guidance_v2'])} rules matched correctly.")

def test_unknown_status():
    result = get_next_steps("Completely unknown status")
    assert result["matched"] is False
    print("PASS: unknown status correctly returns matched=False.")

def test_case_insensitive():
    result = get_next_steps("CASE DISPOSED OF")
    assert result["matched"] is True
    assert result["guidance_id"] == "g016"
    print("PASS: case-insensitive matching works.")

def test_extra_spaces():
    result = get_next_steps("   Case    adjourned for want of time   ")
    assert result["matched"] is True
    print("PASS: extra-whitespace input still matches.")

def test_disclaimer_present():
    result = get_next_steps("Case disposed of")
    assert "disclaimer" in result and len(result["disclaimer"]) > 0
    print("PASS: disclaimer is present.")

def test_suggested_action_present():
    result = get_next_steps("Matter dismissed for default")
    assert "suggested_action" in result and len(result["suggested_action"]) > 0
    print("PASS: suggested_action is present for matched results.")

if __name__ == "__main__":
    test_all_rules_match()
    test_unknown_status()
    test_case_insensitive()
    test_extra_spaces()
    test_disclaimer_present()
    test_suggested_action_present()
    print("\nAll next-steps guidance tests passed.")
