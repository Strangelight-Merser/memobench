import json
from unittest.mock import patch
import httpx
import pytest
from openai import OpenAI, APITimeoutError
from agent.user_profile.extractors import OpenAICompatibleProfileExtractor


def response_body(content='{"updates":[]}', finish='stop'):
    return json.dumps({'id':'fixture', 'object':'chat.completion', 'created':0,
                      'model':'deepseek-flash','choices':[{'index':0,'finish_reason':finish,
                      'message':{'role':'assistant','content':content}}]}).encode()


def extractor(content='{"updates":[]}', finish='stop', url='https://api.deepseek.com/v1/'):
    requests = []
    def handler(request):
        requests.append(request)
        return httpx.Response(200, content=response_body(content, finish), headers={'content-type':'application/json'})
    client = OpenAI(api_key='test-only', base_url=url, http_client=httpx.Client(transport=httpx.MockTransport(handler)))
    return OpenAICompatibleProfileExtractor(model='deepseek-flash', client=client), requests


def test_deepseek_gate_keeps_one_visible_token_without_reasoning():
    e, calls = extractor('是')
    assert e._request_chat_precheck('{}') == '是'
    body = json.loads(calls[0].content)
    assert body['max_tokens'] == 1
    assert body['thinking']['type'] == 'disabled'
    assert calls[0].extensions['timeout']['read'] == 15


def test_deepseek_extraction_is_bounded_and_still_validates_json():
    e, calls = extractor()
    assert e._request_chat_completions({}, '{schema}').updates == []
    body = json.loads(calls[0].content)
    assert body['max_tokens'] == 4096
    assert body['response_format'] == {'type':'json_object'}
    assert body['thinking']['type'] == 'disabled'
    assert body.get('stream') is not True  # HTTP streaming does not change model mode.


@pytest.mark.parametrize('content,finish,match', [
    ('{"updates":[]}', 'length', 'truncated'),
    ('invalid', 'stop', 'invalid profile JSON'),
    ('', 'stop', 'empty profile extraction'),
])
def test_incomplete_or_invalid_profile_is_not_success(content, finish, match):
    e, _ = extractor(content, finish)
    with pytest.raises(RuntimeError, match=match):
        e._request_chat_completions({}, '{schema}')


def test_deepseek_options_do_not_leak_to_other_endpoints():
    e, calls = extractor(url='https://example.invalid/v1')
    e._request_chat_completions({}, '{schema}')
    assert 'thinking' not in json.loads(calls[0].content)


def test_keepalive_cannot_extend_deadline_and_response_closes():
    clock = [0.0]
    class Keepalive(httpx.SyncByteStream):
        closed = False
        def __iter__(self):
            for _ in range(10):
                clock[0] += 20
                yield b'\n'
            yield response_body()
        def close(self):
            self.closed = True
    stream = Keepalive()
    client = OpenAI(api_key='test-only', base_url='https://api.deepseek.com/v1',
                    http_client=httpx.Client(transport=httpx.MockTransport(
                        lambda request: httpx.Response(200, stream=stream))))
    e = OpenAICompatibleProfileExtractor(model='deepseek-flash', client=client)
    with patch('agent.user_profile.extractors.time.monotonic', side_effect=lambda:clock[0]):
        with pytest.raises(TimeoutError, match='response deadline'):
            e._request_chat_completions({}, '{schema}')
    assert clock[0] == 60
    assert stream.closed


def test_transport_timeout_is_not_multiplied_by_sdk_retries():
    calls = []
    def handler(request):
        calls.append(request)
        raise httpx.ReadTimeout('fixture timeout', request=request)
    client = OpenAI(api_key='test-only', base_url='https://api.deepseek.com/v1',
                    http_client=httpx.Client(transport=httpx.MockTransport(handler)))
    e = OpenAICompatibleProfileExtractor(model='deepseek-flash', client=client)
    with pytest.raises(APITimeoutError):
        e._request_chat_completions({}, '{schema}')
    assert len(calls) == 1
