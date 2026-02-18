from codex_home.config import Settings
from codex_home.queueing import build_retry_policy, normalize_retry_intervals


def test_normalize_retry_intervals_single_retry():
    assert normalize_retry_intervals(1, [30, 120]) == 30


def test_normalize_retry_intervals_expands_schedule():
    assert normalize_retry_intervals(3, [15]) == [15, 15, 15]


def test_normalize_retry_intervals_truncates_schedule():
    assert normalize_retry_intervals(2, [10, 20, 30]) == [10, 20]


def test_build_retry_policy_disabled():
    settings = Settings.model_validate(
        {
            "QUEUE_RETRY_MAX": 0,
            "QUEUE_RETRY_INTERVALS": "10,20",
        }
    )
    assert build_retry_policy(settings) is None


def test_build_retry_policy_enabled():
    settings = Settings.model_validate(
        {
            "QUEUE_RETRY_MAX": 3,
            "QUEUE_RETRY_INTERVALS": "5,15",
        }
    )
    retry_policy = build_retry_policy(settings)
    assert retry_policy is not None
    assert retry_policy.max == 3
    assert retry_policy.intervals == [5, 15, 15]
