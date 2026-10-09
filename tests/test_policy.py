from minagent.policy import Decision, Policy, Rule, most_restrictive


def test_first_matching_rule_wins():
    policy = Policy(rules=[
        Rule(pattern="erp.read_*", action="allow"),
        Rule(pattern="erp.*", action="deny"),
    ])
    assert policy.decide("erp.read_po").action == "allow"
    assert policy.decide("erp.post_invoice").action == "deny"


def test_unmatched_tool_is_denied_fail_closed():
    policy = Policy(rules=[Rule(pattern="allowed_*", action="allow")])
    d = policy.decide("something_else")
    assert d.action == "deny"
    assert "fail-closed" in d.reason


def test_default_policy_allows_everything():
    assert Policy().decide("anything").action == "allow"


def test_side_effecting_tool_is_floored_to_ask():
    policy = Policy()  # "*": allow
    assert policy.decide("post_invoice", side_effecting=True).action == "ask"
    # an explicit deny still wins over the ask floor
    deny = Policy(rules=[Rule(pattern="post_*", action="deny")])
    assert deny.decide("post_invoice", side_effecting=True).action == "deny"


def test_most_restrictive_orders_deny_over_ask_over_allow():
    allow, ask, deny = Decision(action="allow"), Decision(action="ask"), Decision(action="deny")
    assert most_restrictive([allow, ask]).action == "ask"
    assert most_restrictive([ask, deny]).action == "deny"
    assert most_restrictive([allow, allow]).action == "allow"
