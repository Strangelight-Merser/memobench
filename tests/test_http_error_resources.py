"""HTTP failures release real response bodies, not absent synthetic file handles."""
import io
import os
from pathlib import Path
import unittest
from unittest.mock import patch
from urllib.error import HTTPError
from memobench.adapters_v2.transports import HTTPTransport,TransportError
from memobench.llm_v2 import LLMClient


class HTTPErrorResourceTests(unittest.TestCase):
    def exercise(self,error,client_type):
        if client_type=='adapter':
            client=HTTPTransport('https://fixture.invalid/bridge',live=True)
            with patch.object(client._opener,'open',side_effect=error):
                with self.assertRaisesRegex(TransportError,'^http_error$'):
                    client.request('observe','synthetic-operation',{},Path('/tmp/synthetic-case'))
        else:
            def opener(*args,**kwargs):raise error
            client=LLMClient(endpoint='https://fixture.invalid/chat/completions',model='synthetic',key_env='TEST_HTTP_RESOURCE_KEY',provider='fixture',opener=opener)
            with patch.dict(os.environ,{'TEST_HTTP_RESOURCE_KEY':'fixture-key'}):
                result=client.complete([{'role':'user','content':'synthetic'}],live=True,input_token_bound=20)
            self.assertEqual(result.reason,'http_401')

    def test_absent_body_is_not_closed_even_if_close_would_raise(self):
        for kind in ('adapter','llm'):
            with self.subTest(kind=kind):
                error=HTTPError('https://fixture.invalid',401,'synthetic',{},None)
                error.fp=None  # Python 3.13 replaces constructor None with BytesIO.
                with patch.object(error,'close',side_effect=KeyError('file')) as close:
                    self.exercise(error,kind)
                    close.assert_not_called()

    def test_real_error_body_is_closed(self):
        for kind in ('adapter','llm'):
            with self.subTest(kind=kind):
                body=io.BytesIO(b'synthetic response')
                error=HTTPError('https://fixture.invalid',401,'synthetic',{},body)
                with patch.object(error,'close',wraps=error.close) as close:
                    self.exercise(error,kind)
                    close.assert_called_once_with()
                self.assertTrue(body.closed)

if __name__=='__main__':unittest.main()
