import secrets                                              # 랜덤한 콜백 토큰을 만드는 표준 라이브러리
from django.contrib.auth.decorators import login_required    # 로그인 안 했으면 로그인 페이지로 보내는 데코레이터
from django.http import JsonResponse  # "권한 없음" 응답 (403)
from posts.models import Post                                 # post_id로 게시물 찾을 때 씀
from .tasks import run_dummy_analysis                          # 4단계에서 만든 그 task
from django.shortcuts import render,redirect,get_object_or_404
import json                                                # 요청 본문(JSON 문자열)을 파이썬 dict로 변환하는 데 사용
from django.views.decorators.csrf import csrf_exempt        # 이 view는 CSRF 토큰 검사를 건너뛰게 해주는 데코레이터
from django.views.decorators.http import require_POST, require_GET     # GET 등 다른 방식으로는 접근 못 하게 POST만 허용, get만 허용하는 레코드 추가
from .models import Analysis, DetectedItem, StyleScore      # 이 view에서 쓸 모델 3개

def home(request):
    return render(request, "analysis/home.html")

@csrf_exempt                                                  # CSRF 토큰 검사 생략 (콜백_token으로 대신 검증하니까)
@require_POST                                                  # POST 요청만 허용, 다른 방식이면 405 에러
def analysis_callback(request, analysis_id):
    analysis = get_object_or_404(Analysis, pk=analysis_id)      # URL의 analysis_id로 레코드 찾기, 없으면 404

    data = json.loads(request.body)                              # 요청 본문(bytes 형태 JSON 문자열)을 dict로 변환

    if data.get("callback_token") != analysis.callback_token:     # 요청에 실린 토큰과 DB에 저장된 토큰 비교
        return JsonResponse({"error": "invalid token"}, status=403)  # 안 맞으면 403(권한 없음)으로 거부하고 종료

    for item in data.get("detected_items", []):                    # 검출된 아이템 목록을 하나씩 순회 (없으면 빈 리스트)
        DetectedItem.objects.create(                                 # 각 아이템마다 DetectedItem 레코드 새로 생성
            analysis=analysis,                                         # 어느 분석에 속하는지 연결
            category=item["category"],                                 # 필수값이라 없으면 에러 나게 그냥 []로 접근
            label=item.get("label", ""),                                # 선택값이라 없으면 빈 문자열 기본값
            bbox_x=item["bbox_x"],
            bbox_y=item["bbox_y"],
            bbox_width=item["bbox_width"],
            bbox_height=item["bbox_height"],
            search_url=item.get("search_url", ""),
        )

    for score in data.get("style_scores", []):                       # 스타일 비율 목록도 동일하게 순회
        StyleScore.objects.create(
            analysis=analysis,
            style_name=score["style_name"],
            ratio=score["ratio"],
        )

    analysis.interpretation = data.get("interpretation", "")           # LLM 해석 텍스트 채우기
    analysis.status = Analysis.STATUS_COMPLETED                          # 상태를 "완료"로 변경 (models.py에서 정의한 상수 재사용)
    analysis.save()                                                       # 변경사항 DB에 저장

    return JsonResponse({"ok": True})                                     # 처리 성공 응답

@login_required                                              # 로그인 안 했으면 여기 도달 전에 로그인 페이지로 리다이렉트
@require_POST                                                  # 버튼 누르는 폼의 POST 요청만 허용
def request_analysis(request, post_id):
    post = get_object_or_404(Post, pk=post_id)

    analysis = Analysis.objects.create(                            # 누구 게시물이든 상관없이 바로 생성
        post=post,
        callback_token=secrets.token_hex(32),
    )
    run_dummy_analysis.delay(analysis.id)

    return redirect("analysis:result", post_id=post.id)               # 결과 페이지로 이동


def result(request, post_id):
    post = get_object_or_404(Post, pk=post_id)                        # 결과를 볼 게시물 조회
    analysis = post.analyses.order_by("-created_at").first()             # 가장 최근 분석 기록 (없으면 None)
    return render(request, "analysis/result.html", {"post": post, "analysis": analysis})

@login_required                                               # 업로드도 로그인 필수
@require_POST
def upload_and_analyze(request):
    image = request.FILES["image"]                              # home.html 업로드 폼의 <input name="image">에서 올 값

    analysis = Analysis.objects.create(                          # post= 대신 image= 로 생성 (post는 비워둠)
        image=image,
        callback_token=secrets.token_hex(32),
    )
    run_dummy_analysis.delay(analysis.id)                           # 기존과 완전히 같은 task, post 유무를 신경 안 씀

    return redirect("analysis:standalone_result", analysis_id=analysis.id)

def standalone_result(request, analysis_id):                     # post_id가 아니라 analysis_id로 직접 조회
    analysis = get_object_or_404(Analysis, pk=analysis_id)
    return render(request, "analysis/standalone_result.html", {"analysis": analysis})

@require_GET                                                     # 상태 조회는 GET 요청만 허용 (JS가 fetch로 호출)
def analysis_status(request, analysis_id):
    analysis = get_object_or_404(Analysis, pk=analysis_id)          # 없는 id면 404
    return JsonResponse({"status": analysis.status})                  # 지금 상태값만 JSON으로 돌려줌