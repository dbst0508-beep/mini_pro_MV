import logging                                              # print 대신 쓰는 기록 도구 (실패 원인을 남길 때 씀)
from django.contrib import messages                          # 화면에 한 번 보여 줄 안내 문구를 남기는 도구
from django.core.exceptions import ValidationError           # 검사 실패 에러
from config.validators import validate_uploaded_image        # 업로드 사진 검사 함수
from django.db import transaction                           # 여러 DB 저장을 "전부 성공 아니면 전부 취소"로 묶는 도구
import secrets                                              # 랜덤한 콜백 토큰을 만드는 표준 라이브러리
from datetime import timedelta                              # "6분" 같은 시간 간격을 표현할 때 씀
from django.utils import timezone                            # 현재 시각을 가져올 때 씀
from django.contrib.auth.decorators import login_required    # 로그인 안 했으면 로그인 페이지로 보내는 데코레이터
from django.http import JsonResponse  # "권한 없음" 응답 (403)
from posts.models import Post                                 # post_id로 게시물 찾을 때 씀
from .tasks import run_analysis,mark_failed                          # 4단계에서 만든 그 task
from django.shortcuts import render,redirect,get_object_or_404
import json                                                # 요청 본문(JSON 문자열)을 파이썬 dict로 변환하는 데 사용
from django.views.decorators.csrf import csrf_exempt        # 이 view는 CSRF 토큰 검사를 건너뛰게 해주는 데코레이터
from django.views.decorators.http import require_POST, require_GET     # GET 등 다른 방식으로는 접근 못 하게 POST만 허용, get만 허용하는 레코드 추가
from .models import Analysis, DetectedItem, StyleScore      # 이 view에서 쓸 모델 3개

STALE_AFTER = timedelta(minutes=6)  # 요청 후 이 시간이 지나도 안 끝나면 실패로 봄 (Celery의 최대 대기 5분보다 길게)

logger = logging.getLogger(__name__)  # 이 파일 전용 기록 담당자 (이름은 "analysis.views"가 됨)

def home(request):                                          # AI 분석 탭의 첫 화면 (사진 업로드 폼)
    return render(request, "analysis/home.html")              # analysis/home.html 템플릿을 화면으로 보여줌


@csrf_exempt                                                  # CSRF 토큰 검사 생략 (콜백_token으로 대신 검증하니까)
@require_POST                                                  # POST 요청만 허용, 다른 방식이면 405 에러
def analysis_callback(request, analysis_id):
    analysis = get_object_or_404(Analysis, pk=analysis_id)      # URL의 analysis_id로 레코드 찾기, 없으면 404

    data = json.loads(request.body)                              # 요청 본문(bytes 형태 JSON 문자열)을 dict로 변환

    sent_token = str(data.get("callback_token", ""))              # 요청에 실린 토큰 (없으면 빈 문자열, 숫자 등이 와도 글자로 바꿈)
    if not secrets.compare_digest(sent_token.encode(), analysis.callback_token.encode()):  # 끝까지 다 비교해서 시간 차이로 정답이 새지 않게 함
        return JsonResponse({"error": "invalid token"}, status=403)  # 안 맞으면 403(권한 없음)으로 거부하고 종료

    if analysis.status == Analysis.STATUS_COMPLETED:                # 토큰은 맞지만 이미 결과가 저장된 분석이면 (같은 콜백이 또 온 경우)
        return JsonResponse({"error": "already completed"}, status=409)  # 409(충돌): 결과를 두 벌 저장하지 않도록 거절
    # ponytail: 콜백 두 개가 정확히 동시에 오면 둘 다 이 검사를 통과할 수 있음. cv_service는 한 번만 보내므로 지금은 충분하고, 필요해지면 select_for_update로 행 잠금

    try:                                                           # 저장 중 어떤 에러가 나도 아래 except가 받도록 감싸기 시작
        with transaction.atomic():                                   # 이 블록 안의 저장을 한 묶음으로: 중간에 에러가 나면 안에서 저장한 것이 전부 취소됨
            for item in data.get("detected_items", []):                # 검출된 아이템 목록을 하나씩 순회 (없으면 빈 리스트)
                DetectedItem.objects.create(                             # 각 아이템마다 DetectedItem 레코드 새로 생성
                    analysis=analysis,                                     # 어느 분석에 속하는지 연결
                    category=item["category"],                             # 필수값이라 없으면 에러 나게 그냥 []로 접근
                    label=item.get("label", ""),                            # 선택값이라 없으면 빈 문자열 기본값
                    bbox_x=item["bbox_x"],
                    bbox_y=item["bbox_y"],
                    bbox_width=item["bbox_width"],
                    bbox_height=item["bbox_height"],
                    search_url=item.get("search_url", ""),
                )

            for score in data.get("style_scores", []):                  # 스타일 비율 목록도 동일하게 순회
                StyleScore.objects.create(
                    analysis=analysis,
                    style_name=score["style_name"],
                    ratio=score["ratio"],
                )

            analysis.interpretation = data.get("interpretation", "")     # LLM 해석 텍스트 채우기
            analysis.status = Analysis.STATUS_COMPLETED                    # 상태를 "완료"로 변경
            analysis.error_message = ""                                     # 늦게 도착해 살린 결과라면 남아 있던 실패 문구를 지움
            analysis.save()                                                 # 변경사항 DB에 저장 (여기까지 와야 묶음 전체가 확정됨)
    except Exception:                                                  # 묶음 안에서 무슨 에러가 나도 (이 시점엔 이미 전부 되돌려진 상태)
        logger.exception("분석 #%s 결과 저장 실패", analysis.id)         # 실패 원인(에러 내용과 위치)을 로그에 남김
        mark_failed(analysis.id, "분석 결과를 저장하지 못했습니다. 다른 사진으로 다시 시도해 주세요.")  # 분석을 바로 "실패"로 표시 (6분 기다리지 않게)
        return JsonResponse({"error": "failed to save result"}, status=500)  # 보낸 쪽(cv_service)에도 실패를 알림

    return JsonResponse({"ok": True})                                   # 처리 성공 응답

@login_required                                              # 로그인 안 했으면 여기 도달 전에 로그인 페이지로 리다이렉트
@require_POST                                                  # 버튼 누르는 폼의 POST 요청만 허용
def request_analysis(request, post_id):
    post = get_object_or_404(Post, pk=post_id)

    analysis = Analysis.objects.create(                            # 누구 게시물이든 상관없이 바로 생성
        user=request.user,                                           # 요청한 사람을 주인으로 기록
        post=post,
        callback_token=secrets.token_hex(32),
    )

    run_analysis.delay(analysis.id)

    return redirect("analysis:result", post_id=post.id)               # 결과 페이지로 이동


def result(request, post_id):
    post = get_object_or_404(Post, pk=post_id)                        # 결과를 볼 게시물 조회
    analysis = post.analyses.order_by("-created_at").first()             # 가장 최근 분석 기록 (없으면 None)
    failed_retry = None                                                  # "실패한 재분석" 자리 (기본은 없음)

    if analysis and analysis.status == Analysis.STATUS_FAILED:           # 가장 최근 분석이 실패했다면
        last_completed = post.analyses.filter(                            # 이 게시물의 분석 중에서
            status=Analysis.STATUS_COMPLETED                               # 완료된 것만 골라
        ).order_by("-created_at").first()                                  # 그중 가장 최근 것
        if last_completed:                                                # 이전에 성공한 결과가 있으면
            failed_retry = analysis                                        # 실패한 것은 안내용으로 따로 두고
            analysis = last_completed                                      # 화면에는 성공한 결과를 보여줌

    return render(request, "analysis/result.html", {
        "post": post,
        "analysis": analysis,
        "failed_retry": failed_retry,
    })


@login_required                                               # 업로드도 로그인 필수
@require_POST
def upload_and_analyze(request):
    image = request.FILES.get("image")                          # [...] 대신 .get(): 파일이 없으면 KeyError(500) 대신 None
    try:
        validate_uploaded_image(image)                            # 있음 / 10MB 이하 / 진짜 이미지인지 검사
    except ValidationError as error:
        messages.error(request, error.messages[0])                 # 실패 이유를 화면에 보여 주도록 남김
        return redirect("analysis:home")                           # 업로드 화면으로 돌려보냄 (분석은 만들지 않음)
    analysis = Analysis.objects.create(                          # post= 대신 image= 로 생성 (post는 비워둠)
        user=request.user,                                         # 업로드한 사람을 주인으로 기록
        image=image,
        callback_token=secrets.token_hex(32),
    )
    run_analysis.delay(analysis.id)                           # 기존과 완전히 같은 task, post 유무를 신경 안 씀

    return redirect("analysis:standalone_result", analysis_id=analysis.id)

def standalone_result(request, analysis_id):                     # post_id가 아니라 analysis_id로 직접 조회
    analysis = get_object_or_404(Analysis, pk=analysis_id)
    return render(request, "analysis/standalone_result.html", {"analysis": analysis})

@require_GET                                                     # 상태 조회는 GET 요청만 허용 (JS가 fetch로 호출)
def analysis_status(request, analysis_id):
    analysis = get_object_or_404(Analysis, pk=analysis_id)          # 없는 id면 404

    is_waiting = analysis.status in (Analysis.STATUS_PENDING, Analysis.STATUS_PROCESSING)  # 아직 안 끝난 상태인지
    if is_waiting and timezone.now() - analysis.created_at > STALE_AFTER:                  # 안 끝났는데 요청한 지 너무 오래됐으면
        mark_failed(analysis.id, "분석이 시작되지 않았거나 너무 오래 걸리고 있습니다. 잠시 후 다시 시도해 주세요.")
        analysis.refresh_from_db()                                    # 방금 DB에서 바뀐 상태를 다시 읽어옴

    return JsonResponse({"status": analysis.status})                  # 지금 상태값만 JSON으로 돌려줌