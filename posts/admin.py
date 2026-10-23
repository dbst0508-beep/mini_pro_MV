from django.contrib import admin                          # 어드민 기능 전체를 쓰기 위해 불러옴
from django.db.models import Count                        # 개수를 세어 붙이는 도구 (좋아요 수, 댓글 수, 분석 수 계산용)
from django.urls import reverse                           # 어드민 페이지 주소를 이름으로 찾아 주는 도구 (분석 상세 링크용)
from django.utils import timezone                         # UTC로 저장된 시각을 한국 시간으로 바꾸는 도구
from django.utils.html import format_html, format_html_join  # 안전하게 HTML을 그려 주는 도구 (한 개용, 여러 개 반복용)

from .models import Post, Comment, Like                   # 인라인으로 끼워 넣을 모델들 (Comment, Like는 이제 별도 메뉴 없이 게시물 안에서만 보임)


class CommentInline(admin.TabularInline):                 # 게시물 상세 화면 안에 "이 게시물의 댓글"을 표로 끼워 넣는 클래스
    model = Comment                                       # 끼워 넣을 모델
    extra = 0                                             # 빈 입력 줄을 미리 추가하지 않음
    fields = ["user", "content", "created_at"]            # 표에 보여줄 칸: 작성자, 내용, 작성 시각
    readonly_fields = ["user", "content", "created_at"]   # 내용을 몰래 고치지 못하게 세 칸 모두 보기 전용
    ordering = ["created_at"]                             # 오래된 댓글부터 순서대로 (삭제 체크박스는 남겨 두어 부적절한 댓글을 지울 수 있음)

    def has_add_permission(self, request, obj=None):      # "댓글 추가" 버튼을 보여줄지 정하는 함수
        return False                                      # 운영자가 임의로 댓글을 만들지 못하게 막음


class LikeInline(admin.TabularInline):                    # 게시물 상세 화면 안에 "이 게시물을 좋아요한 사람"을 표로 끼워 넣는 클래스
    model = Like                                          # 끼워 넣을 모델
    extra = 0                                             # 빈 입력 줄을 미리 추가하지 않음
    fields = ["user", "created_at"]                       # 표에 보여줄 칸: 누른 사람, 누른 시각
    readonly_fields = ["user", "created_at"]              # 두 칸 모두 보기 전용
    ordering = ["created_at"]                             # 먼저 누른 사람부터 순서대로
    can_delete = False                                    # 삭제 체크박스를 숨김 (좋아요 기록은 운영자가 지울 이유가 없음)

    def has_add_permission(self, request, obj=None):      # "좋아요 추가" 버튼을 보여줄지 정하는 함수
        return False                                      # 운영자가 임의로 좋아요를 만들지 못하게 막음


@admin.register(Post)                                     # 아래 클래스로 Post를 어드민에 등록
class PostAdmin(admin.ModelAdmin):                        # 게시물이 어드민에서 어떻게 보일지 정하는 클래스
    list_display = ["id", "thumbnail", "user", "caption", "analysis_count", "like_count", "comment_count", "created_at"]  # 목록 화면에 보여줄 컬럼들
    list_select_related = ["user"]                        # 작성자 정보를 JOIN으로 한 번에 가져와서 줄마다 쿼리가 나가는 것을 막음
    search_fields = ["caption", "user__username", "comments__content"]  # 검색창이 찾을 대상: 캡션, 작성자 아이디, 댓글 내용 (댓글 메뉴가 없어진 대신)
    list_filter = ["created_at"]                          # 오른쪽 필터 패널: 오늘/지난 7일/이번 달 같은 날짜 필터
    ordering = ["-created_at"]                            # 최신 게시물이 위로 오게 정렬
    fields = ["user", "detail_image", "image", "caption", "created_at", "analysis_results"]  # 상세 화면에 보여줄 칸의 순서 (큰 사진 → 정보 → 분석 결과)
    readonly_fields = ["detail_image", "created_at", "analysis_results"]  # 수정할 수 없는 칸 (큰 사진, 자동 기록 시각, 분석 결과 표)
    inlines = [CommentInline, LikeInline]                 # 상세 화면 아래에 이 게시물의 댓글 표와 좋아요 표를 같이 보여줌

    def get_queryset(self, request):                      # 목록에 쓸 데이터를 가져오는 함수 (어드민이 호출)
        queryset = super().get_queryset(request)          # 기본 게시물 목록을 먼저 받아 옴
        return queryset.annotate(                         # 게시물마다 개수를 계산해서 붙임
            _like_count=Count("likes", distinct=True),    # 좋아요 수 (distinct: 여러 개를 한꺼번에 세도 중복 계산되지 않게)
            _comment_count=Count("comments", distinct=True),  # 댓글 수
            _analysis_count=Count("analyses", distinct=True),  # 분석 횟수 (재분석하면 늘어남)
        )

    @admin.display(description="사진")                     # 컬럼 제목을 "사진"으로 표시
    def thumbnail(self, obj):                             # 목록용 작은 사진 (obj = 목록의 각 Post 한 줄)
        if not obj.image:                                 # 이미지가 없으면
            return "-"                                    # 대시만 표시
        return format_html('<img src="{}" style="height:60px; border-radius:6px;">', obj.image.url)  # 높이 60px 작은 사진을 그림

    @admin.display(description="사진 미리보기")              # 상세 화면의 칸 제목
    def detail_image(self, obj):                          # 상세용 큰 사진
        if not obj.image:                                 # 이미지가 없거나 새 게시물 작성 화면이면
            return "-"                                    # 대시만 표시
        return format_html('<img src="{}" style="max-height:320px; border-radius:8px;">', obj.image.url)  # 최대 높이 320px 큰 사진을 그림

    @admin.display(description="분석 수", ordering="_analysis_count")  # 컬럼 제목 + 클릭하면 분석 횟수 기준 정렬
    def analysis_count(self, obj):                        # 분석 횟수를 보여주는 함수
        return obj._analysis_count                        # get_queryset에서 미리 계산해 둔 값을 그대로 반환

    @admin.display(description="좋아요 수", ordering="_like_count")  # 컬럼 제목 + 좋아요 수 기준 정렬
    def like_count(self, obj):                            # 좋아요 수를 보여주는 함수
        return obj._like_count                            # 미리 계산해 둔 값을 반환

    @admin.display(description="댓글 수", ordering="_comment_count")  # 컬럼 제목 + 댓글 수 기준 정렬
    def comment_count(self, obj):                         # 댓글 수를 보여주는 함수
        return obj._comment_count                         # 미리 계산해 둔 값을 반환

    @admin.display(description="AI 분석 결과")              # 상세 화면의 칸 제목
    def analysis_results(self, obj):                      # 이 게시물의 분석 기록을 스타일 비율 표 + 아이템 표로 그려 주는 함수
        if not obj.pk:                                    # 새 게시물 작성 화면이면 (아직 저장 전이라 분석이 있을 수 없음)
            return "-"                                    # 대시만 표시
        analyses = obj.analyses.prefetch_related("detected_items", "style_scores").order_by("-created_at")  # 이 게시물의 분석들을 최신순으로, 아이템·비율은 미리 한꺼번에 가져옴
        if not analyses:                                  # 분석한 적이 없으면
            return "분석 기록이 없습니다."                    # 안내 문구 표시
        blocks = []                                       # 분석 하나당 만든 HTML 조각을 모아 둘 리스트
        for analysis in analyses:                         # 분석을 하나씩 꺼내서
            url = reverse("admin:analysis_analysis_change", args=[analysis.pk])  # 그 분석의 어드민 상세 페이지 주소 (제목 클릭 시 이동)
            created = timezone.localtime(analysis.created_at).strftime("%Y-%m-%d %H:%M")  # 생성 시각을 한국 시간 "2026-10-20 13:35" 모양으로
            style_rows = format_html_join(                # 스타일 비율 표의 줄들을 반복해서 만듦
                "", "<tr><td>{}</td><td>{}%</td></tr>",   # 구분자 없이, 한 줄 모양: 스타일 이름 | 비율%
                ((s.style_name, s.ratio) for s in sorted(analysis.style_scores.all(), key=lambda s: -s.ratio)),  # 비율이 큰 스타일부터
            )
            item_rows = format_html_join(                 # 탐지 아이템 표의 줄들을 반복해서 만듦
                "", "<tr><td>{}</td><td>{}</td><td>{}</td></tr>",  # 한 줄 모양: 분류 | 세부 라벨 | 검색 링크
                (
                    (
                        i.category,                       # 분류 (상의/하의/…)
                        i.label or "-",                   # 세부 라벨, 없으면 대시
                        format_html('<a href="{}" target="_blank">검색</a>', i.search_url) if i.search_url else "-",  # 쇼핑 검색 링크가 있으면 새 탭으로 여는 링크
                    )
                    for i in analysis.detected_items.all()  # 이 분석에서 탐지된 아이템들을 하나씩
                ),
            )
            blocks.append(format_html(                    # 분석 하나의 박스를 만들어 리스트에 추가
                '<div style="margin-bottom:20px; padding:10px; border:1px solid #ccc; border-radius:6px;">'  # 테두리 있는 박스
                '<b><a href="{}">분석 #{}</a></b> · {} · {}'  # 제목: 분석 번호(상세 링크) · 상태 · 생성 시각
                '<div style="margin-top:6px;"><b>해석</b>: {}</div>'  # AI가 쓴 스타일 해석 글
                '<div><b>실패 사유</b>: {}</div>'         # 실패했을 때의 에러 문구
                '<table style="margin-top:8px;"><tr><th>스타일</th><th>비율</th></tr>{}</table>'  # 스타일 비율 표
                '<table style="margin-top:8px;"><tr><th>분류</th><th>세부 라벨</th><th>쇼핑</th></tr>{}</table>'  # 탐지 아이템 표
                "</div>",
                url, analysis.pk, analysis.get_status_display(), created,  # 위 제목 줄에 들어갈 값들 (상태는 "완료" 같은 한글 표시값)
                analysis.interpretation or "-",           # 해석 글 (비어 있으면 대시)
                analysis.error_message or "-",            # 실패 사유 (비어 있으면 대시)
                style_rows, item_rows,                    # 위에서 만든 두 표의 줄들
            ))
        return format_html_join("", "{}", ((b,) for b in blocks))  # 만들어 둔 박스들을 이어 붙여서 반환