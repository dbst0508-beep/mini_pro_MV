import io  # 파일로 저장하지 않고 메모리 안에서 사진을 만들 때 씀
import unittest  # 파이썬 기본 테스트 도구
from unittest.mock import patch  # 진짜를 잠깐 가짜로 바꿔치기하는 도구
from urllib.parse import quote  # 기대하는 검색 링크를 만들 때 씀 (main.py가 쓰는 것과 같은 도구)

from fastapi.testclient import TestClient  # 서버를 띄우지 않고 가짜 요청을 보내 주는 도구
from PIL import Image  # 테스트용 작은 사진을 만들 때 씀

from app.main import app  # 테스트할 FastAPI 앱


def make_image_file():
    """업로드용 작은 사진 파일을 메모리에 만들어 주는 도우미"""
    buffer = io.BytesIO()  # 메모리 안의 빈 파일
    Image.new("RGB", (10, 10)).save(buffer, format="PNG")  # 10x10 검은 사진을 PNG로 저장
    buffer.seek(0)  # 파일 읽는 위치를 맨 앞으로 되돌림 (안 하면 빈 파일처럼 읽힘)
    return buffer


class AnalyzeEndpointTests(unittest.TestCase):  # /analyze 전체 흐름 테스트 모음
    def setUp(self):
        """테스트마다 먼저 실행됨: 무거운 부품 4개를 가짜로 바꿔 둔다"""
        self.client = TestClient(app, raise_server_exceptions=False)  # 서버 에러가 나면 테스트가 터지지 않고 500 응답으로 받음

        for name in ("detect_items", "label_items", "interpret_style", "send_callback"):  # 가짜로 바꿀 부품 이름 4개
            patcher = patch(f"app.main.{name}")  # main.py 안에서 쓰는 이름을 가짜로 바꿀 준비
            setattr(self, f"mock_{name}", patcher.start())  # 바꾸고, self.mock_detect_items 같은 이름으로 꺼내 쓸 수 있게 보관
            self.addCleanup(patcher.stop)  # 테스트가 끝나면 원래대로 되돌림

        self.mock_detect_items.return_value = [  # 가짜 탐지 결과: 상의 하나
            {"category": "상의", "bbox_x": 0.1, "bbox_y": 0.2, "bbox_width": 0.3, "bbox_height": 0.4},
        ]
        self.mock_label_items.return_value = [  # 가짜 라벨링 결과: 위 아이템에 라벨이 붙은 모양
            {"category": "상의", "label": "흰색 티셔츠", "bbox_x": 0.1, "bbox_y": 0.2, "bbox_width": 0.3, "bbox_height": 0.4},
        ]
        self.mock_interpret_style.return_value = (  # 가짜 Gemini 결과: (스타일 비율 리스트, 해석 글)
            [{"style_name": "캐주얼", "ratio": 60.0}, {"style_name": "미니멀", "ratio": 40.0}],
            "편안한 캐주얼 룩입니다.",
        )

    def post_analyze(self):
        """/analyze에 사진과 콜백 정보를 실어 보내는 도우미"""
        return self.client.post(
            "/analyze",
            files={"image": ("look.png", make_image_file(), "image/png")},  # 사진 파일
            data={"callback_url": "http://django/callback/", "callback_token": "secret-token"},  # 사진 말고 글자 값 2개
        )

    def test_success_sends_callback_with_everything(self):
        """정상 흐름: 탐지, 라벨, 비율, 해석이 모두 담긴 데이터를 콜백으로 보낸다"""
        response = self.post_analyze()  # 가짜 요청 보내기

        self.assertEqual(response.status_code, 200)  # 성공 응답
        self.assertEqual(response.json(), {"ok": True})  # 응답 내용도 약속대로

        self.mock_send_callback.assert_called_once()  # 콜백 전송 함수가 딱 한 번 불렸는지
        callback_url, payload = self.mock_send_callback.call_args.args  # 불릴 때 넘겨받은 값 2개를 꺼냄
        self.assertEqual(callback_url, "http://django/callback/")  # 받은 주소로 보냈는지
        self.assertEqual(payload.callback_token, "secret-token")  # 받은 토큰 그대로 실었는지
        self.assertEqual(payload.detected_items[0].label, "흰색 티셔츠")  # 라벨링 결과가 담겼는지
        self.assertEqual(payload.detected_items[0].bbox_x, 0.1)  # 박스 좌표도 그대로인지
        self.assertEqual([s.style_name for s in payload.style_scores], ["캐주얼", "미니멀"])  # 스타일 비율이 담겼는지
        self.assertEqual(payload.interpretation, "편안한 캐주얼 룩입니다.")  # 해석 글이 담겼는지

    def test_search_url_is_built_from_label(self):
        """라벨로 쇼핑 검색 링크를 만든다 (한글은 URL용으로 변환됨)"""
        self.post_analyze()

        payload = self.mock_send_callback.call_args.args[1]  # 콜백으로 보낸 데이터
        expected = f"https://search.shopping.naver.com/search/all?query={quote('흰색 티셔츠')}"  # 기대하는 링크
        self.assertEqual(payload.detected_items[0].search_url, expected)

    def test_empty_label_gives_empty_search_url(self):
        """라벨이 비어 있으면 검색 링크도 빈 문자열이다"""
        self.mock_label_items.return_value[0]["label"] = ""  # 가짜 라벨링 결과의 라벨을 비움

        self.post_analyze()

        payload = self.mock_send_callback.call_args.args[1]
        self.assertEqual(payload.detected_items[0].search_url, "")

    def test_duplicate_items_are_merged_before_sending(self):
        """같은 아이템(왼발/오른발 신발)은 하나로 합쳐서 보낸다"""
        shoe = {"category": "신발", "label": "흰색 스니커즈", "bbox_x": 0.2, "bbox_y": 0.8, "bbox_width": 0.1, "bbox_height": 0.1}
        self.mock_label_items.return_value = [shoe, dict(shoe, bbox_x=0.6)]  # 위치만 다른 같은 신발 2개 (dict(shoe, ...)는 복사 후 일부만 바꿈)

        self.post_analyze()

        payload = self.mock_send_callback.call_args.args[1]
        self.assertEqual(len(payload.detected_items), 1)  # 하나만 남았는지

    def test_callback_failure_returns_500(self):
        """콜백 전송이 실패하면 500을 돌려준다 (그래야 Django의 Celery가 실패로 기록함)"""
        self.mock_send_callback.side_effect = Exception("Django 저장 실패")  # 가짜에게 "부르면 에러를 내라"고 시킴

        response = self.post_analyze()

        self.assertEqual(response.status_code, 500)  # 에러 응답이 나가는지
