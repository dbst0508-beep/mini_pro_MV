import requests                                              # FastAPI 서버로 HTTP 요청 보낼 때 씀
from celery import shared_task                                # Celery task로 등록해주는 데코레이터
from django.conf import settings                               # settings.py에 적어둔 주소들 가져오기

from .models import Analysis                                    # analysis_id로 레코드 조회할 때 씀


@shared_task                                                      # 이 함수를 Celery가 "일감"으로 등록, .delay()로 호출 가능해짐
def run_dummy_analysis(analysis_id):
    analysis = Analysis.objects.get(pk=analysis_id)                 # DB에서 해당 분석 레코드 조회 (callback_token도 이미 들어있음)

    image_field = analysis.image if analysis.image else analysis.post.image
    # A 플로우(게시물 기반)면 analysis.image가 비어있어서 analysis.post.image를 씀,
    # B 플로우(독립 업로드)면 analysis.image가 있으니 그걸 그대로 씀

    callback_url = f"{settings.INTERNAL_BASE_URL}/analysis/api/{analysis.id}/callback/"  # 결과를 돌려받을 Django 콜백 주소
    analyze_url = f"{settings.CV_SERVICE_BASE_URL}/analyze"                                # FastAPI의 분석 요청 주소

    with image_field.open("rb") as image_file:                        # 이미지 파일을 바이너리로 열기
        requests.post(                                                   # FastAPI에 "이 사진 분석해줘" 요청
            analyze_url,
            data={                                                         # 파일이 아닌 일반 텍스트 값들
                "callback_url": callback_url,
                "callback_token": analysis.callback_token,
            },
            files={"image": image_file},                                  # 실제 이미지 파일
        )