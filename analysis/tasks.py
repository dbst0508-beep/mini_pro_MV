import time                                              # 오래 걸리는 척 흉내낼 때 쓸 대기 함수
import requests                                            # 콜백 엔드포인트로 HTTP 요청 보낼 때 씀
from celery import shared_task                              # Celery task로 등록해주는 데코레이터
from django.conf import settings                             # settings.py에 적어둔 INTERNAL_BASE_URL 가져오기

from .models import Analysis                                  # analysis_id로 레코드 조회할 때 씀


@shared_task                                                    # 이 함수를 Celery가 "일감"으로 등록, .delay()로 호출 가능해짐
def run_dummy_analysis(analysis_id):
    analysis = Analysis.objects.get(pk=analysis_id)               # DB에서 해당 분석 레코드 조회 (callback_token도 이미 들어있음)

    time.sleep(5)                                                   # 실제 CV/LLM이 몇 초 걸리는 걸 흉내내기 위한 일부러 넣은 지연

    payload = {                                                      # 콜백 엔드포인트한테 보낼 더미 결과 데이터
        "callback_token": analysis.callback_token,                     # 3단계에서 만든 토큰 검증 통과용
        "detected_items": [
            {
                "category": "상의", "label": "니트",
                "bbox_x": 0.1, "bbox_y": 0.1, "bbox_width": 0.4, "bbox_height": 0.5,
                "search_url": "https://search.shopping.naver.com/search/all?query=니트",
            },
            {
                "category": "하의", "label": "청바지",
                "bbox_x": 0.15, "bbox_y": 0.55, "bbox_width": 0.35, "bbox_height": 0.4,
                "search_url": "https://search.shopping.naver.com/search/all?query=청바지",
            },
        ],
        "style_scores": [
            {"style_name": "캐주얼", "ratio": 60.0},
            {"style_name": "스트릿", "ratio": 40.0},
        ],
        "interpretation": "캐주얼한 니트와 청바지 조합으로, 편안하면서도 트렌디한 스트릿 무드가 느껴지는 룩입니다.",
    }

    callback_url = f"{settings.INTERNAL_BASE_URL}/analysis/api/{analysis.id}/callback/"  # 3단계에서 만든 그 주소
    requests.post(callback_url, json=payload)                          # 실제 HTTP POST 요청 전송