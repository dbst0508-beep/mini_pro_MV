import unittest  # 파이썬 기본 테스트 도구
from unittest.mock import patch  # 진짜를 잠깐 가짜로 바꿔치기하는 도구

from app.callback import is_allowed_callback_url, send_callback  # 테스트할 함수 2개
from app.schemas import CallbackPayload  # send_callback에 넘길 데이터 모양


class IsAllowedCallbackUrlTests(unittest.TestCase):
    def test_allowed_hosts_pass(self):
        """compose(web)와 터미널 실행(localhost, 127.0.0.1) 주소는 통과"""
        for url in (
            "http://web:8000/analysis/api/1/callback/",
            "http://localhost:8000/analysis/api/1/callback/",
            "http://127.0.0.1:8000/analysis/api/1/callback/",
        ):
            with self.subTest(url=url):  # 하나가 실패해도 나머지도 검사하고, 어느 주소가 실패했는지 알려 줌
                self.assertTrue(is_allowed_callback_url(url))

    def test_tricky_urls_are_blocked(self):
        """이름만 비슷하거나 숨겨 놓은 주소는 막힘"""
        for url in (
            "http://evil.com/",                  # 그냥 외부 주소
            "http://web.evil.com/",              # 앞부분만 web
            "http://evil.com/?q=web",            # 뒤에 web을 숨김
            "http://localhost@evil.com/",        # @ 앞은 사용자 이름이라 진짜 호스트는 evil.com
            "http://169.254.169.254/latest/",    # 클라우드 서버의 비밀 정보 주소
            "file:///etc/passwd",                # http가 아닌 주소
            "",                                  # 빈 값
        ):
            with self.subTest(url=url):
                self.assertFalse(is_allowed_callback_url(url))


class SendCallbackTests(unittest.TestCase):
    @patch("app.callback.requests.post")  # 진짜로 보내지 않고 가짜로 바꿈
    def test_does_not_follow_redirects(self, mock_post):
        """리다이렉트를 따라가지 않도록 설정해서 보낸다"""
        payload = CallbackPayload(callback_token="t")  # 나머지 필드는 기본값(빈 리스트/빈 문자열)

        send_callback("http://web:8000/callback/", payload)

        self.assertIs(mock_post.call_args.kwargs["allow_redirects"], False)


if __name__ == "__main__":
    unittest.main()


