# Django 어드민을 "게시물 중심"으로 정리하기 (2026-10-23)

브랜치: `feature/admin-page`

> 한 줄 요약: Django 기본 어드민은 모델마다 메뉴가 따로 있어서 데이터가 쌓이면 "이 아이템이 어느 게시물 것인지" 알 수 없었다. **게시물 하나를 열면 사진, AI 분석 결과(스타일 비율·탐지 아이템), 댓글, 좋아요가 한 화면에 모이도록** 바꿨다. 게시물 없이 올린 독립 업로드 분석은 `Analysis` 메뉴에 남겼다.

---

## 1. 기술문서

### 1-1. 왜 바꿨나

Django는 `admin.site.register(모델)`만 해도 어드민 화면을 만들어 준다. 그런데 기본 상태는 이랬다.

| 문제 | 증상 |
|---|---|
| 이름이 의미 없음 | 목록에 `Analysis object (3)`, `Analysis #1 (completed)`처럼 나옴. 어느 게시물인지 모름 |
| 메뉴가 종류별 서랍 | `Detected items`에 **모든 게시물의 아이템이 섞여서** 나열됨. 아이템이 수백 개가 되면 1번 게시물 것만 보기 어려움 |
| "선택된 파일 없음" | 분석 상세의 `image` 칸은 독립 업로드용이라, 게시물 기반 분석에서는 비어 있어서 사진이 없는 것처럼 보임 |
| 실수로 고칠 수 있음 | AI가 만든 결과(스타일 비율, 탐지 좌표, 콜백 토큰)를 어드민에서 수정할 수 있었음 |

### 1-2. 해결 방향: 서랍 → 폴더

```
(전) 서랍 4개                       (후) 게시물마다 폴더 하나
Detected items  ─ 전부 섞임          Posts
Style scores    ─ 전부 섞임           └─ 게시물 #1 (test1)
Comments        ─ 전부 섞임                ├─ 사진
Likes           ─ 전부 섞임                ├─ AI 분석 결과 (분석 #2: 비율 표 + 아이템 표)
                                          ├─ 댓글 표
                                          └─ 좋아요 표
```

| 메뉴 | 처리 | 이유 |
|---|---|---|
| **Posts** | 중심 화면 | 사진, 분석 결과, 댓글, 좋아요가 모두 이 안에 모임 |
| **Analysis** | 유지 | 게시물 없이 올린 **독립 업로드 분석**의 보관 장소. 상태·실패 사유로 걸러 볼 때도 사용 |
| Detected items / Style scores / Comments / Likes | **메뉴에서 제거** | 게시물(또는 분석) 화면 안에서 보이므로 따로 둘 이유가 없음. DB 데이터는 그대로이고 어드민에 등록만 하지 않음 |
| 사용자, 그룹 | 그대로 | Django 기본 |

### 1-3. 바뀐 파일

| 파일 | 구분 | 내용 |
|---|---|---|
| `posts/models.py` | 수정 | `Post`, `Comment`, `Like`의 `__str__`(표시 이름) 변경. DB 변경 없음 |
| `analysis/models.py` | 수정 | `Analysis`, `DetectedItem`, `StyleScore`의 `__str__` 변경. DB 변경 없음 |
| `posts/admin.py` | 전면 수정 | 게시물 중심 화면, 분석 결과 표, 댓글·좋아요 표, 검색 |
| `analysis/admin.py` | 전면 수정 | 사진 미리보기, 읽기 전용 AI 결과, 아이템·비율 표. 아이템/비율 별도 메뉴 제거 |
| `accounts/tests.py` | 수정 | 마이페이지 비로그인 리다이렉트 테스트를 현재 동작에 맞춤 (트러블슈팅 참고) |

마이그레이션은 필요 없다. `__str__`과 어드민 설정은 DB 구조와 무관하다.

### 1-4. 이름 규칙

한 게시물을 재분석하면 `Analysis`가 여러 개가 되므로, 게시물 번호와 분석 번호를 같이 쓴다.

| 모델 | 표시 이름 예시 |
|---|---|
| Post | `게시물 #1 (test1)` (캡션이 없으면 `게시물 #1`) |
| Analysis | `게시물 #1 (test1) · 분석 #2` / 게시물이 없으면 `독립 업로드 · 분석 #3` |
| DetectedItem | `게시물 #2 (test2) · 분석 #1 · 신발 (화이트 레더 스니커즈)` |
| StyleScore | `게시물 #2 (test2) · 분석 #1 · 미니멀 50.0%` |
| Comment | `게시물 #1 (test1) · admin · 거짓말` |
| Like | `게시물 #1 (test1) ← ltw17` |

### 1-5. 게시물 화면 구성

| 위치 | 내용 |
|---|---|
| 목록 | 썸네일, 작성자, 캡션, **분석 수, 좋아요 수, 댓글 수**, 작성일. 숫자 컬럼은 클릭하면 정렬 |
| 목록 검색 | 캡션, 작성자 아이디, **댓글 내용** (댓글 메뉴가 없어진 대신 이 검색으로 찾음) |
| 상세 위쪽 | 작성자, 큰 사진, 캡션, 작성 시각 |
| 상세 "AI 분석 결과" | 분석마다 박스 하나: 제목(분석 번호·상태·시각), 해석 글, 실패 사유, **스타일 비율 표(큰 순)**, **탐지 아이템 표(쇼핑 링크 포함)** |
| 상세 아래쪽 | 댓글 표(작성자 확인, **삭제 체크박스**), 좋아요 표 |

### 1-6. 분석 화면 구성

| 위치 | 내용 |
|---|---|
| 목록 | 이름, 사진, 상태, 탐지 아이템 수, 실패 사유, 생성/갱신 시각. 오른쪽에 **상태 필터**(대기중/분석중/완료/실패)와 날짜 필터 |
| 상세 | 분석한 사진, 게시물 링크, 상태, 에러 메시지, 해석 글, 콜백 토큰, 시각 |
| 상세 아래쪽 | 탐지 아이템 표(분류, 라벨, 박스 좌표, 검색 링크), 스타일 비율 표 |

### 1-7. 안전장치 (데이터가 민감하므로)

| 대상 | 처리 |
|---|---|
| AI 결과(해석, 에러, 박스 좌표, 비율) | 읽기 전용 |
| 콜백 토큰, 시각 | 읽기 전용 (토큰은 보안값) |
| 분석·아이템·비율·좋아요·댓글 직접 추가 | 막음 (앱의 정상 흐름으로만 생김) |
| 분석 상태(`status`) | 수정 가능 (운영자가 멈춘 분석을 정리할 때 필요) |
| 댓글 삭제 | 허용 (부적절한 댓글을 지울 수 있어야 함). 내용 수정은 불가 |

### 1-8. 화면

게시물 목록 — 썸네일과 분석·좋아요·댓글 수가 한눈에 보인다.

<img src="images/admin/01-post-list.jpg" width="900">

게시물 상세 — AI 분석 결과(해석, 스타일 비율, 탐지 아이템)가 게시물 안에 모여 있다.

<img src="images/admin/02-post-detail-analysis.jpg" width="900">

게시물 상세 — 그 게시물의 댓글과 좋아요.

<img src="images/admin/03-post-detail-comments-likes.jpg" width="900">

분석 목록 — 상태, 탐지 아이템 수, 실패 사유와 상태 필터. 독립 업로드는 `독립 업로드 · 분석 #3`으로 표시된다.

<img src="images/admin/04-analysis-list.jpg" width="900">

### 1-9. 알려진 아쉬운 점

- 사이드바와 목록 제목에 `Analysiss`(Analysis + 자동 복수형 `s`)로 보인다. 모델의 `verbose_name_plural`을 지정하면 고쳐지지만 모델 설정 변경(마이그레이션)이 필요해서 이번에는 두지 않았다.
- 게시물 상세의 댓글·좋아요 표는 줄마다 이름(`게시물 #1 (test1) · admin · …`)이 한 번 더 나와서 약간 중복돼 보인다. Django 기본 동작이다.
- 게시물 상세의 "AI 분석 결과"는 직접 그린 HTML 표라서 수정은 안 되고 보기만 된다. 수정이 필요한 경우는 분석 상세 화면을 쓴다.

---

## 2. 클래스·함수 단위 코드리뷰

### `posts/models.py`, `analysis/models.py`

| 항목 | 역할 |
|---|---|
| `__str__` | 어드민의 목록, 제목, 드롭다운에서 객체를 사람이 읽을 이름으로 보여 주는 함수. 이 이름이 모든 어드민 화면에 퍼지므로 한 번만 고치면 전체가 통일됨 |

### `posts/admin.py`

| 항목 | 역할 |
|---|---|
| `CommentInline` | 게시물 상세 안에 댓글 표를 끼워 넣음. 내용은 읽기 전용, 삭제 체크박스는 유지 |
| `LikeInline` | 게시물 상세 안에 좋아요 표를 끼워 넣음. 전부 읽기 전용, 삭제 불가 |
| `PostAdmin.get_queryset` | 목록을 가져올 때 좋아요·댓글·분석 개수를 한 번에 계산해서 붙임 (줄마다 세지 않음) |
| `Count(..., distinct=True)` | 여러 관계를 동시에 JOIN하면 행이 곱해져서 개수가 부풀려지는데, `distinct`로 중복 계산을 막음 |
| `thumbnail` / `detail_image` | 목록용 작은 사진 / 상세용 큰 사진을 `<img>`로 그림 |
| `analysis_count`, `like_count`, `comment_count` | 미리 계산해 둔 값을 컬럼으로 보여 주고, `ordering=`으로 클릭 정렬을 지원 |
| `analysis_results` | 게시물의 분석들을 최신순으로 꺼내 스타일 비율 표와 아이템 표가 든 HTML 박스로 만듦 |
| `format_html`, `format_html_join` | 값에 `<`, `>` 같은 문자가 있어도 안전하게(이스케이프해서) HTML로 만드는 도구. DB에 들어 있는 글(해석, 캡션)을 화면에 그릴 때 꼭 필요 |
| `search_fields`의 `comments__content` | 게시물 검색창에서 댓글 내용으로도 찾음 |
| `has_add_permission` → `False` | "추가" 버튼을 숨겨서 운영자가 가짜 데이터를 만들지 못하게 함 |

### `analysis/admin.py`

| 항목 | 역할 |
|---|---|
| `DetectedItemInline` / `StyleScoreInline` | 분석 상세 안에 아이템 표와 비율 표를 끼워 넣음. 전부 읽기 전용, 추가·삭제 불가 |
| `AnalysisAdmin.get_queryset` | 목록에서 분석마다 탐지 아이템 수를 한 번에 계산 |
| `_image_url` | 분석한 사진 주소를 구함. 독립 업로드는 `image`, 게시물 기반은 `post.image`. 둘 다 없으면 `None` |
| `preview` / `preview_large` | 목록용 작은 사진 / 상세용 큰 사진. 비어 있던 `image` 칸 대신 실제 분석 사진을 보여 줌 |
| `item_count`, `short_error` | 아이템 수, 실패 사유 앞 40글자를 컬럼으로 표시 |
| `readonly_fields` | 상태 외 모든 칸 읽기 전용 |
| `has_add_permission` → `False` | 분석은 "요청 → 콜백" 흐름으로만 만들어져야 하므로 직접 추가 금지 |

---

## 3. 한 줄 한 줄 주석 코드

### 3-1. `posts/models.py` (바뀐 `__str__` 3개)

```python
# Post 클래스 안
    def __str__(self):                                        # 어드민·셸에서 게시물을 문자열로 보여줄 때 쓰는 이름
        if self.caption:                                      # 캡션이 있으면
            return f"게시물 #{self.pk} ({self.caption[:20]})"    # "게시물 #1 (오늘의 코디)"처럼 번호 + 캡션 앞 20글자
        return f"게시물 #{self.pk}"                             # 캡션이 비어 있으면 번호만 표시

# Comment 클래스 안
    def __str__(self):                                        # 댓글을 문자열로 보여줄 때 쓰는 이름
        return f"{self.post} · {self.user} · {self.content[:20]}"  # "게시물 #1 (캡션) · 작성자 · 댓글 앞부분"처럼 어느 게시물의 누구 댓글인지까지 표시

# Like 클래스 안
    def __str__(self):                                        # 좋아요를 문자열로 보여줄 때 쓰는 이름
        return f"{self.post} ← {self.user}"                    # "게시물 #1 (캡션) ← 누른 사람"처럼 어느 게시물에 누가 눌렀는지 표시
```

### 3-2. `analysis/models.py` (바뀐 `__str__` 3개)

```python
# Analysis 클래스 안
    def __str__(self):                                        # 분석 기록을 문자열로 보여줄 때 쓰는 이름
        target = str(self.post) if self.post_id else "독립 업로드"  # 게시물 기반이면 게시물 이름(Post.__str__), 아니면 "독립 업로드"
        return f"{target} · 분석 #{self.pk}"                    # "게시물 #1 (캡션) · 분석 #3"처럼 대상 + 분석 번호 (재분석하면 번호가 달라서 구분됨)

# DetectedItem 클래스 안
    def __str__(self):                                        # 탐지된 아이템을 문자열로 보여줄 때 쓰는 이름
        name = f"{self.category} ({self.label})" if self.label else self.category  # 세부 라벨이 있으면 "상의 (니트)", 없으면 "상의"
        return f"{self.analysis} · {name}"                     # "게시물 #1 (캡션) · 분석 #3 · 상의 (니트)"처럼 어느 분석의 아이템인지까지 표시

# StyleScore 클래스 안
    def __str__(self):                                        # 스타일 비율을 문자열로 보여줄 때 쓰는 이름
        return f"{self.analysis} · {self.style_name} {self.ratio}%"  # "게시물 #1 (캡션) · 분석 #3 · 캐주얼 60.0%"처럼 어느 분석의 점수인지까지 표시
```

### 3-3. `posts/admin.py`

```python
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
```

### 3-4. `analysis/admin.py`

```python
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
    list_display = ["__str__", "preview", "status", "item_count", "short_error", "created_at", "updated_at"]  # 목록 컬럼들 (__str__ = "게시물 #1 (캡션) · 분석 #3" 이름)
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
```

---

## 4. 복습

### 어드민은 "모델 목록"이 기본, "사람이 볼 화면"은 직접 만든다
- `admin.site.register(모델)`만 하면 모델별 메뉴가 생긴다. 편하지만 데이터 관계(어느 게시물의 아이템인지)는 알려 주지 않는다.
- 운영자가 필요한 것은 모델 목록이 아니라 **"이 게시물에서 무슨 일이 있었나"**다. 그래서 부모(게시물) 화면에 자식(분석, 댓글, 좋아요)을 모았다.

### 인라인(Inline)
- 부모 상세 화면 아래에 자식 데이터를 표로 끼워 넣는 기능이다 (`TabularInline`).
- **인라인 안의 인라인은 Django가 기본으로 지원하지 않는다.** 게시물 → 분석 → 아이템 3단 구조는 인라인으로 안 되어서, 분석 결과는 `analysis_results` 함수로 HTML 표를 직접 그렸다. 대신 이 부분은 수정이 안 되는 "보기 전용"이다.

### `__str__`은 화면 전체의 이름표
- 어드민은 목록, 제목, 드롭다운, 필터에서 모두 객체의 `__str__`을 쓴다. 한 번 잘 고치면 모든 화면이 한꺼번에 읽기 쉬워진다.
- DB 구조와 무관해서 마이그레이션이 필요 없다.

### N+1 문제 피하기
- 목록 100줄에서 줄마다 "좋아요 몇 개?"를 물으면 쿼리가 101번 나간다.
- `annotate(Count(...))`로 개수를 목록 쿼리에 같이 계산하고, `list_select_related`로 작성자·게시물을 JOIN해서 가져오면 쿼리 수가 일정해진다.

### 읽기 전용(readonly)은 안전장치
- AI가 만든 결과와 보안값(콜백 토큰)을 사람이 어드민에서 고칠 수 있으면 데이터 신뢰가 깨진다.
- 수정이 필요한 것(분석 상태)만 열어 두고 나머지는 잠갔다. "추가" 버튼도 막아 가짜 데이터가 생기지 않게 했다.

### HTML을 직접 그릴 때는 `format_html`
- DB의 글(캡션, 해석)에 `<script>` 같은 문자가 들어 있어도 `format_html`은 글자로 바꿔서(이스케이프) 보여 준다. 문자열을 `f"..."`로 이어 붙여 HTML을 만들면 이런 보호가 없다.

### 로그인 상태는 브라우저 하나에 하나
- 어드민과 일반 페이지는 같은 세션을 공유한다. 한 브라우저에서 계정을 바꾸면 옛 탭의 폼은 CSRF 토큰이 맞지 않는다. 시연할 때 어드민은 시크릿 창에서 연다.

### 화면 캡처할 때
- Swagger나 어드민 화면에는 **토큰, 콜백 토큰, 로컬 주소**가 보일 수 있다. 커밋하기 전에 가리거나 잘라 낸다. 한 번 커밋하면 기록에 남는다.

---

## 5. 트러블슈팅

### 5-1. 분석 상세에서 "선택된 파일 없음"으로 보임

| | 내용 |
|---|---|
| 증상 | 분석을 열면 `Image` 칸이 "선택된 파일 없음"이라 사진이 없는 것처럼 보임 |
| 원인 | `Analysis.image`는 **독립 업로드 전용** 칸이라 게시물 기반 분석에서는 원래 비어 있음. 분석한 사진은 `post.image`에 있었음 |
| 해결 | `_image_url`로 독립 업로드는 `image`, 게시물 기반은 `post.image`를 골라서 상세 맨 위에 실제 사진을 미리보기로 보여 줌. `image`는 읽기 전용으로 변경 |
| 교훈 | 이름 문제처럼 보였지만 "그 칸이 무엇을 위한 칸인지"가 원인이었음 |

### 5-2. 별도 메뉴를 그대로 두면 데이터가 섞여 보임

| | 내용 |
|---|---|
| 증상 | `Detected items`, `Style scores`, `Comments`에 모든 게시물의 데이터가 한 목록으로 섞여 나열됨 |
| 원인 | Django 어드민의 목록은 모델별로 평평하게 나열되는 구조라서 부모-자식 관계가 보이지 않음 |
| 해결 | 해당 메뉴를 어드민에서 제거하고, 게시물 상세(인라인 + 직접 그린 분석 표)와 분석 상세(인라인)에서 보게 함. 단, 3단 인라인은 지원되지 않아 분석 표는 `format_html`로 직접 그림 |
| 보완 | 댓글 메뉴가 없어진 대신 게시물 검색에 `comments__content`를 추가해 댓글 내용으로 게시물을 찾을 수 있게 함 |

### 5-3. 일반 유저 → 어드민 로그인 뒤 일반 페이지에서 403 (CSRF)

| | 내용 |
|---|---|
| 증상 | 일반 유저로 로그인한 탭을 열어 둔 채, 같은 브라우저에서 어드민에 관리자로 로그인하고 돌아와 POST하면 "CSRF 검증에 실패했습니다" 403 |
| 원인 | 어드민과 일반 페이지는 같은 세션을 쓰고, 로그인하면 CSRF 토큰이 새로 바뀜. 옛 탭의 폼에는 예전 토큰이 남아 있어서 불일치 |
| 해결 | 버그가 아니라 Django의 정상 보안 동작이라 코드는 그대로 둠. 새로고침하면 정상. 시연 시 어드민은 시크릿 창에서 열기 |
| 참고 | 배포할 때(`DEBUG = False`)는 영어 도움말 대신 한 줄만 나옴. 나중에 `CSRF_FAILURE_VIEW`로 안내 페이지를 만들 수 있음 |

### 5-4. 마이페이지 테스트 1개가 실패 (어드민과 무관한 기존 문제)

| | 내용 |
|---|---|
| 증상 | `manage.py test posts analysis accounts` 중 `test_requires_login` 실패. `'/login/' != '/login/?next=%2Fmypage%2F'` |
| 원인 | 테스트는 `@login_required` 시절 동작(`?next=` 붙음)을 기대하는데, 뷰가 다른 유저 프로필(`username`)도 보여 주도록 바뀌면서 비로그인이면 `redirect("accounts:login_page")`로 `next` 없이 보냄. 뷰를 바꿀 때 테스트를 같이 고치지 않았음 |
| 해결 | 현재 동작(`/login/`)에 테스트를 맞춤. `login_page`가 로그인 후 항상 피드로 보내서 `next`를 붙여도 쓰이지 않기 때문 |
| 교훈 | 이번 작업의 변경(`__str__`)이 원인이 아니라는 것을 확인하려고 나머지 48개가 통과하는지 먼저 본 것이 도움이 됨 |

### 5-5. 스크린샷에 토큰이 찍힘

| | 내용 |
|---|---|
| 증상 | Swagger 캡처의 curl 박스에 `X-CSRFTOKEN` 값이, 어드민 분석 상세에 콜백 토큰이 그대로 보임 |
| 원인 | Swagger는 실행한 요청을 curl 명령으로 보여 주고, 어드민은 읽기 전용이라도 칸의 값을 그대로 보여 줌 |
| 해결 | 커밋하기 **전에** 해당 부분을 가리거나 잘라 냄. 요청 화면과 응답을 나눠 찍어 curl 박스가 안 나오게 함 |
| 교훈 | 한 번 커밋하면 지워도 git 기록에 남아서 고치기 어려우므로 `git add` 전에 확인 |
