import json  # 파이썬 값을 JSON 글자로 바꾸는 도구 (가짜 Gemini 답을 만들 때 씀)
import unittest  # 파이썬 기본 테스트 도구 (Django TestCase의 바탕)
from unittest.mock import patch  # 진짜를 잠깐 가짜로 바꿔치기하는 도구

from PIL import Image  # 테스트용 작은 사진을 만들 때 씀

from app.interpretation import (  # 테스트할 대상 불러오기
    FALLBACK_INTERPRETATION,  # Gemini 실패 시 대신 보여 주는 문구
    LLM_TIMEOUT,  # Gemini 답을 기다리는 최대 시간 (30초)
    MAX_LABEL_LENGTH,  # 라벨 최대 글자 수 (15)
    ItemLabelResult,  # Gemini가 돌려주는 "번호 + 라벨" 한 묶음의 모양
    StyleScoreResult,  # Gemini가 돌려주는 "스타일 이름 + 비율" 한 묶음의 모양
    apply_labels,  # 라벨을 아이템에 붙이는 함수
    interpret_style,  # Gemini를 불러 해석을 받아 오는 함수
    normalize_scores,  # 스타일 비율을 정리하는 함수
)

def make_scores(*pairs):
    """(이름, 비율) 묶음들을 Gemini가 돌려준 것과 같은 모양의 객체 리스트로 바꿔 주는 도우미"""
    return [StyleScoreResult(style_name=name, ratio=ratio) for name, ratio in pairs]  # 묶음 하나당 객체 하나


class NormalizeScoresTests(unittest.TestCase):  # normalize_scores 함수 테스트 모음
    def test_ratios_are_scaled_to_100(self):
        """비율 합이 100이 아니어도 100이 되게 맞춘다"""
        scores = make_scores(("캐주얼", 30), ("미니멀", 30))  # 합이 60인 입력

        result = normalize_scores(scores)  # 테스트할 함수 실행

        self.assertEqual(  # 결과가 기대한 것과 똑같은지 확인
            result,
            [
                {"style_name": "캐주얼", "ratio": 50.0},  # 30/60 = 50%
                {"style_name": "미니멀", "ratio": 50.0},  # 30/60 = 50%
            ],
        )

    def test_duplicate_names_are_merged(self):
        """같은 이름이 두 번 나오면 하나로 합친다 (앞뒤 공백은 무시)"""
        scores = make_scores(("캐주얼", 40), (" 캐주얼 ", 20), ("미니멀", 40))  # 캐주얼이 두 번, 한 번은 공백 포함

        result = normalize_scores(scores)

        self.assertEqual(
            result,
            [
                {"style_name": "캐주얼", "ratio": 60.0},  # 40 + 20
                {"style_name": "미니멀", "ratio": 40.0},
            ],
        )

    def test_empty_name_and_zero_ratio_are_dropped(self):
        """이름이 비었거나 비율이 0 이하인 항목은 버린다"""
        scores = make_scores(("", 50), ("캐주얼", 0), ("미니멀", 50))  # 쓸 수 있는 건 미니멀 하나뿐

        result = normalize_scores(scores)

        self.assertEqual(result, [{"style_name": "미니멀", "ratio": 100.0}])  # 남은 하나가 100%

    def test_returns_empty_list_when_nothing_usable(self):
        """쓸 수 있는 항목이 하나도 없으면 빈 리스트를 돌려준다"""
        scores = make_scores(("", 50), ("캐주얼", 0))  # 전부 버려질 입력

        result = normalize_scores(scores)

        self.assertEqual(result, [])  # 0으로 나누다 에러 나지 않고 빈 리스트
def make_items():
    """탐지 결과처럼 생긴 아이템 2개를 새로 만들어 주는 도우미 (테스트마다 깨끗한 새것을 쓰려고 함수로 만듦)"""
    return [
        {"category": "상의", "label": "티셔츠"},  # 1번 아이템 (FashionCLIP이 붙여 둔 라벨이라고 가정)
        {"category": "하의", "label": "바지"},  # 2번 아이템
    ]


class ApplyLabelsTests(unittest.TestCase):  # apply_labels 함수 테스트 모음
    def test_label_is_applied_to_matching_number(self):
        """번호에 해당하는 아이템의 라벨을 Gemini 결과로 바꾼다"""
        items = make_items()

        apply_labels(items, [ItemLabelResult(number=2, label="와이드 청바지")])  # 2번에만 새 라벨

        self.assertEqual(items[0]["label"], "티셔츠")  # 1번은 그대로
        self.assertEqual(items[1]["label"], "와이드 청바지")  # 2번은 바뀜 (번호 2 → 리스트의 [1])

    def test_unknown_number_is_ignored(self):
        """없는 번호가 오면 무시한다 (에러 없이 넘어감)"""
        items = make_items()

        apply_labels(
            items,
            [
                ItemLabelResult(number=0, label="없는 번호"),  # 번호는 1부터라 0은 없음
                ItemLabelResult(number=99, label="없는 번호"),  # 아이템이 2개뿐이라 99도 없음
            ],
        )

        self.assertEqual(items, make_items())  # 아무것도 안 바뀜 (새로 만든 것과 똑같음)

    def test_blank_label_keeps_existing_label(self):
        """빈 라벨이 오면 원래 라벨을 지킨다"""
        items = make_items()

        apply_labels(items, [ItemLabelResult(number=1, label="   ")])  # 공백만 있는 라벨

        self.assertEqual(items[0]["label"], "티셔츠")  # 빈칸으로 덮어쓰지 않음

    def test_long_label_is_cut(self):
        """너무 긴 라벨은 최대 글자 수에서 자른다"""
        items = make_items()

        apply_labels(items, [ItemLabelResult(number=1, label="가" * 30)])  # "가"가 30개인 긴 라벨

        self.assertEqual(items[0]["label"], "가" * MAX_LABEL_LENGTH)  # 15글자만 남음

def make_detected_items():
    """위치 정보까지 들어 있는 탐지 결과 2개를 만들어 주는 도우미 (프롬프트를 만들 때 위치가 필요함)"""
    return [
        {"category": "상의", "label": "티셔츠", "bbox_x": 0.2, "bbox_y": 0.1, "bbox_width": 0.6, "bbox_height": 0.4},  # 1번
        {"category": "하의", "label": "바지", "bbox_x": 0.2, "bbox_y": 0.5, "bbox_width": 0.6, "bbox_height": 0.5},  # 2번
    ]


@patch("app.interpretation.client")  # 이 클래스의 모든 테스트에서 진짜 Gemini 접속 준비물을 가짜로 바꿈
class InterpretStyleTests(unittest.TestCase):  # interpret_style 함수 테스트 모음
    def setUp(self):
        self.image = Image.new("RGB", (10, 10))  # 가로세로 10픽셀짜리 검은 사진 (내용은 중요하지 않음)

    def test_failure_returns_fallback_and_keeps_labels(self, mock_client):
        """Gemini가 실패하면 대체 문구와 빈 비율을 돌려주고, 원래 라벨은 그대로 둔다"""
        mock_client.interactions.create.side_effect = Exception("503 서버 혼잡")  # 가짜에게 "부르면 에러를 내라"고 시킴
        items = make_detected_items()

        style_scores, interpretation = interpret_style(self.image, items)

        self.assertEqual(style_scores, [])  # 스타일 비율은 비어 있음
        self.assertEqual(interpretation, FALLBACK_INTERPRETATION)  # 해석 자리엔 대체 문구
        self.assertEqual(items[0]["label"], "티셔츠")  # FashionCLIP 라벨이 살아 있음

    def test_success_returns_scores_and_applies_labels(self, mock_client):
        """Gemini가 성공하면 정리된 비율과 해석을 돌려주고, 라벨을 Gemini 것으로 바꾼다"""
        answer = {  # Gemini가 돌려줄 답을 미리 만들어 둠
            "style_scores": [{"style_name": "캐주얼", "ratio": 60}, {"style_name": "미니멀", "ratio": 40}],
            "interpretation": "편안해 보이는 조합입니다.",
            "item_labels": [{"number": 1, "label": "흰색 반팔티"}],
        }
        mock_client.interactions.create.return_value.output_text = json.dumps(answer)  # 가짜에게 "이 답을 JSON 글자로 돌려줘라"고 시킴
        items = make_detected_items()

        style_scores, interpretation = interpret_style(self.image, items)

        self.assertEqual(
            style_scores,
            [{"style_name": "캐주얼", "ratio": 60.0}, {"style_name": "미니멀", "ratio": 40.0}],
        )
        self.assertEqual(interpretation, "편안해 보이는 조합입니다.")
        self.assertEqual(items[0]["label"], "흰색 반팔티")  # 1번 라벨이 Gemini 것으로 바뀜
        self.assertEqual(items[1]["label"], "바지")  # 답에 없던 2번은 그대로

    def test_broken_answer_returns_fallback(self, mock_client):
        """Gemini가 약속한 모양이 아닌 답을 주면 실패로 처리한다"""
        mock_client.interactions.create.return_value.output_text = "JSON이 아닌 그냥 글"  # 엉뚱한 답

        style_scores, interpretation = interpret_style(self.image, make_detected_items())

        self.assertEqual(style_scores, [])
        self.assertEqual(interpretation, FALLBACK_INTERPRETATION)

    def test_call_uses_timeout(self, mock_client):
        """Gemini를 부를 때 제한 시간을 함께 넘긴다 (오늘 고친 부분이 실수로 지워지지 않게 지킴)"""
        mock_client.interactions.create.side_effect = Exception("실패")  # 결과는 중요하지 않으니 바로 실패시킴

        interpret_style(self.image, make_detected_items())

        called_with = mock_client.interactions.create.call_args.kwargs  # 가짜가 "어떤 옵션으로 불렸는지" 기록해 둔 것
        self.assertEqual(called_with["timeout"], LLM_TIMEOUT)  # timeout=30으로 불렸는지 확인

