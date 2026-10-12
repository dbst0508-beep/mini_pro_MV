import requests                                              # FastAPI 서버로 HTTP 요청 보낼 때 씀
from celery import shared_task                                # Celery task로 등록해주는 데코레이터
from django.conf import settings                               # settings.py에 적어둔 주소들 가져오기

from .models import Analysis                                    # analysis_id로 레코드 조회할 때 씀

ANALYZE_TIMEOUT = (5, 300)  # (연결 대기 5초, 응답 대기 300초) — 서버 켠 직후 첫 분석은 몇 분 걸릴 수 있어 넉넉하게


def mark_failed(analysis_id, message):
    """분석을 실패 상태로 바꾸고 안내 문구를 저장 (이미 완료된 분석은 건드리지 않음)"""
    Analysis.objects.filter(pk=analysis_id).exclude(      # 이 id의 분석 중에서, 완료된 것은 빼고
        status=Analysis.STATUS_COMPLETED
    ).update(                                              # 조건에 맞는 레코드만 DB에서 바로 수정
        status=Analysis.STATUS_FAILED,
        error_message=message,
    )


@shared_task                                                      # 이 함수를 Celery가 "일감"으로 등록, .delay()로 호출 가능해짐
def run_analysis(analysis_id):
    analysis = Analysis.objects.get(pk=analysis_id)                 # DB에서 해당 분석 레코드 조회 (callback_token도 이미 들어있음)

    Analysis.objects.filter(pk=analysis_id, status=Analysis.STATUS_PENDING).update(
        status=Analysis.STATUS_PROCESSING                             # "대기중"일 때만 "분석중"으로 변경
    )

    image_field = analysis.image if analysis.image else analysis.post.image
    # A 플로우(게시물 기반)면 analysis.image가 비어있어서 analysis.post.image를 씀,
    # B 플로우(독립 업로드)면 analysis.image가 있으니 그걸 그대로 씀

    callback_url = f"{settings.INTERNAL_BASE_URL}/analysis/api/{analysis.id}/callback/"  # 결과를 돌려받을 Django 콜백 주소
    analyze_url = f"{settings.CV_SERVICE_BASE_URL}/analyze"                                # FastAPI의 분석 요청 주소

    try:
        with image_field.open("rb") as image_file:                        # 이미지 파일을 바이너리로 열기
            response = requests.post(                                        # FastAPI에 "이 사진 분석해줘" 요청
                analyze_url,
                data={                                                         # 파일이 아닌 일반 텍스트 값들
                    "callback_url": callback_url,
                    "callback_token": analysis.callback_token,
                },
                files={"image": image_file},                                  # 실제 이미지 파일
                timeout=ANALYZE_TIMEOUT,                                       # 이 시간 넘게 답이 없으면 포기
            )
        response.raise_for_status()                                         # 응답이 에러(4xx/5xx)면 예외를 일으킴
    except requests.exceptions.ConnectionError as error:                  # 서버가 꺼져 있어 연결 자체가 안 될 때
        print(f"[run_analysis] #{analysis_id} 연결 실패: {error}")
        mark_failed(analysis_id, "분석 서버에 연결할 수 없습니다. 잠시 후 다시 시도해 주세요.")
    except requests.exceptions.Timeout as error:                           # 제한 시간 안에 답이 안 올 때
        print(f"[run_analysis] #{analysis_id} 시간 초과: {error}")
        mark_failed(analysis_id, "분석 시간이 초과되었습니다. 잠시 후 다시 시도해 주세요.")
    except Exception as error:                                              # 그 밖의 모든 문제 (서버 에러 응답, 이미지 파일 없음 등)
        print(f"[run_analysis] #{analysis_id} 오류: {error}")
        mark_failed(analysis_id, "분석 중 오류가 발생했습니다. 다른 사진으로 다시 시도해 주세요.")
