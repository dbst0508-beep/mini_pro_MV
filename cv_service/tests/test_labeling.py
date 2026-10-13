import unittest  # 파이썬 기본 테스트 도구

from app.labeling import merge_duplicates  # 테스트할 함수 불러오기


class MergeDuplicatesTests(unittest.TestCase):  # merge_duplicates 함수 테스트 모음
    def test_same_category_and_label_are_merged(self):
        """카테고리와 라벨이 모두 같으면 첫 번째 것만 남긴다 (왼발/오른발 신발)"""
        left_shoe = {"category": "신발", "label": "흰색 스니커즈", "bbox_x": 0.2}  # 왼발
        right_shoe = {"category": "신발", "label": "흰색 스니커즈", "bbox_x": 0.6}  # 오른발 (위치만 다름)

        result = merge_duplicates([left_shoe, right_shoe])

        self.assertEqual(result, [left_shoe])  # 먼저 나온 왼발만 남음

    def test_different_label_is_kept(self):
        """카테고리가 같아도 라벨이 다르면 둘 다 남긴다"""
        items = [
            {"category": "상의", "label": "흰색 반팔티"},  # 안에 입은 옷
            {"category": "상의", "label": "검정 가디건"},  # 겉에 걸친 옷
        ]

        result = merge_duplicates(items)

        self.assertEqual(result, items)  # 서로 다른 옷이라 그대로

    def test_same_label_in_different_category_is_kept(self):
        """라벨이 같아도 카테고리가 다르면 둘 다 남긴다"""
        items = [
            {"category": "상의", "label": "데님"},
            {"category": "하의", "label": "데님"},
        ]

        result = merge_duplicates(items)

        self.assertEqual(result, items)

    def test_order_is_preserved(self):
        """중복을 빼도 남은 아이템의 순서는 그대로다"""
        items = [
            {"category": "상의", "label": "티셔츠"},
            {"category": "신발", "label": "스니커즈"},
            {"category": "하의", "label": "청바지"},
            {"category": "신발", "label": "스니커즈"},  # 두 번째 신발 (빠질 것)
        ]

        result = merge_duplicates(items)

        self.assertEqual(
            [item["category"] for item in result],  # 결과에서 카테고리만 뽑아 순서 확인
            ["상의", "신발", "하의"],
        )

    def test_empty_list(self):
        """아이템이 하나도 없으면 빈 리스트를 돌려준다"""
        self.assertEqual(merge_duplicates([]), [])
