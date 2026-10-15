from tests.agent.test_prompt_profiles import _make_agent
from agent.system_prompt import build_system_prompt


def test_profile_lifecycle_is_explained_only_when_runtime_is_active():
    active = _make_agent('full')
    prompt = build_system_prompt(active)
    assert 'Native user-profile persistence is enabled.' in prompt
    assert '<user_profile_data>PROFILE BLOCK</user_profile_data>' in prompt
    inactive = _make_agent('full')
    inactive._user_profile_runtime = None
    prompt = build_system_prompt(inactive)
    assert 'Native user-profile persistence is enabled.' not in prompt
    assert '<user_profile_data>' not in prompt
