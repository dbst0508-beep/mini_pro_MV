from django.contrib import admin                          # 어드민 기능 전체를 쓰기 위해 불러옴
from django.db.models import Count                        # 개수를 세어 붙이는 도구 (탐지 아이템 수 계산용)
from django.utils.html import format_html                 # 안전하게 HTML 태그(<img>, <a>)를 화면에 그려 주는 도구

from .models import Analysis, DetectedItem, StyleScore    # 어드민에 등록할 모델 세 개


class DetectedItemInline(admin.TabularInline):            # 분석 상세 화면 안에 "탐지된 아이템"을 표로 끼워 넣는 클래스
    model = DetectedItem                                  # 끼워 넣을 모델
    extra = 0                                             # 빈 입력 줄을 미리 추가하지 않음
    fields = ["category", "label", "bbox_x", "bbox_y", "bbox_width", "bbox_height", "search_url"]  # 표에 보여줄 칸: 분류, 세부 라벨, 박스 위치·크기, 쇼핑 검색 링크
    readonly_fields = ["category", "label", "bbox_x", "bbox_y", "bbox_width", "bbox_height", "search_url"]  # AI가 만든 결과라서 전부 보기 전용
    ordering = ["id"]                                     # 탐지된 순서대로
    can_delete = False                                    # 이 화면에서 아이템을 지우는 체크박스를 숨김

    def has_add_permission(self, request, obj=None):      # "새 아이템 추가" 버튼을 보여줄지 정하는 함수
        return False                                      # 결과는 AI가 만드는 것이라 직접 추가하지 못하게 막음


class StyleScoreInline(admin.TabularInline):              # 분석 상세 화면 안에 "스타일 비율"을 표로 끼워 넣는 클래스
    model = StyleScore                                    # 끼워 넣을 모델
    extra = 0                                             # 빈 입력 줄을 미리 추가하지 않음
    fields = ["style_name", "ratio"]                      # 표에 보여줄 칸: 스타일 이름, 비율
    readonly_fields = ["style_name", "ratio"]             # 보기 전용
    ordering = ["-ratio"]                                 # 비율이 큰 스타일부터
    can_delete = False                                    # 삭제 체크박스를 숨김

    def has_add_permission(self, request, obj=None):      # "새 스타일 추가" 버튼을 보여줄지 정하는 함수
        return False                                      # 직접 추가하지 못하게 막음


@admin.register(Analysis)                                 # Analysis를 어드민에 등록
class AnalysisAdmin(admin.ModelAdmin):                    # 분석 기록이 어드민에서 어떻게 보일지 정하는 클래스
    list_display = ["__str__", "preview", "status", "item_count", "short_error", "created_at", "updated_at"]  # 목록 컬럼들 (__str__ = 위에서 바꾼 "게시물 #1 (캡션) · 분석 #3" 이름)
    list_filter = ["status", "created_at"]                # 오른쪽 필터: 상태별(대기중/분석중/완료/실패), 날짜별
    search_fields = ["error_message", "interpretation", "post__caption"]  # 에러 내용, 해석 글, 연결된 게시물 캡션으로 검색
    list_select_related = ["post"]                        # 연결된 게시물을 JOIN으로 한 번에 가져옴 (이름에 캡션이 들어가서 필요)
    ordering = ["-created_at"]                            # 최신 분석이 위로
    fields = ["preview_large", "post", "image", "status", "error_message", "interpretation", "callback_token", "created_at", "updated_at"]  # 상세 화면 칸 순서 (분석한 사진이 맨 위)
    readonly_fields = ["preview_large", "post", "image", "error_message", "interpretation", "callback_token", "created_at", "updated_at"]  # 상태 외에는 전부 보기 전용 (콜백 토큰은 보안값이라 수정 금지)
    inlines = [DetectedItemInline, StyleScoreInline]      # 상세 화면 아래에 아이템 표와 스타일 비율 표를 같이 보여줌

    def get_queryset(self, request):                      # 목록에 쓸 데이터를 가져오는 함수 (어드민이 호출)
        queryset = super().get_queryset(request)          # 기본 분석 목록을 먼저 받아 옴
        return queryset.annotate(_item_count=Count("detected_items", distinct=True))  # 분석마다 탐지된 아이템 수를 계산해서 붙임

    def has_add_permission(self, request):                # "분석 추가" 버튼을 보여줄지 정하는 함수
        return False                                      # 분석 기록은 앱의 흐름(요청→콜백)으로만 만들어져야 하므로 직접 추가를 막음

    def _image_url(self, obj):                            # 분석한 사진의 주소를 구하는 내부 도구 (사진이 없으면 None)
        if obj is None:                                   # 어드민이 빈 객체로 호출하는 경우를 대비
            return None                                   # 주소 없음
        if obj.image:                                     # 독립 업로드면 image 칸에 사진이 있음
            return obj.image.url                          # 그 사진 주소
        if obj.post_id:                                   # 게시물 기반이면
            return obj.post.image.url                     # 게시물의 사진 주소
        return None                                       # 둘 다 없으면 주소 없음

    @admin.display(description="사진")                     # 컬럼 제목을 "사진"으로 표시
    def preview(self, obj):                               # 목록용 작은 사진
        url = self._image_url(obj)                        # 분석한 사진 주소 구하기
        if not url:                                       # 주소가 없으면
            return "-"                                    # 대시만 표시
        return format_html('<img src="{}" style="height:60px; border-radius:6px;">', url)  # 높이 60px 작은 사진을 그림

    @admin.display(description="분석한 사진")                # 상세 화면의 칸 제목
    def preview_large(self, obj):                         # 상세용 큰 사진 ("선택된 파일 없음" 대신 실제 분석 사진을 보여줌)
        url = self._image_url(obj)                        # 분석한 사진 주소 구하기
        if not url:                                       # 주소가 없으면
            return "-"                                    # 대시만 표시
        return format_html('<img src="{}" style="max-height:320px; border-radius:8px;">', url)  # 최대 높이 320px 큰 사진을 그림

    @admin.display(description="탐지 아이템 수", ordering="_item_count")  # 컬럼 제목 + 클릭하면 아이템 수 기준 정렬
    def item_count(self, obj):                            # 탐지된 아이템 수를 보여주는 함수
        return obj._item_count                            # get_queryset에서 미리 계산해 둔 값을 반환

    @admin.display(description="실패 사유")                 # 컬럼 제목을 "실패 사유"로 표시
    def short_error(self, obj):                           # 긴 에러 문구를 목록에서 잘라 보여주는 함수
        return obj.error_message[:40] or "-"              # 앞 40글자만, 비어 있으면 대시


