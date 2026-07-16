from django.db import models


class Analysis(models.Model):
    # status 필드에서 쓸 수 있는 값들을 클래스 상수로 미리 정의
    STATUS_PENDING = "pending"
    STATUS_PROCESSING = "processing"
    STATUS_COMPLETED = "completed"
    STATUS_FAILED = "failed"

    # Django가 select 형태로 보여줄 (실제저장값, 화면표시값) 쌍의 목록
    STATUS_CHOICES = [
        (STATUS_PENDING, "대기중"),
        (STATUS_PROCESSING, "분석중"),
        (STATUS_COMPLETED, "완료"),
        (STATUS_FAILED, "실패"),
    ]

    # 어느 게시물에 대한 분석인지 연결 (FK라서 한 Post에 여러 Analysis 가능 = 재분석 허용)
    post = models.ForeignKey(
        "posts.Post",  # 다른 앱의 모델이라 "앱이름.모델명" 문자열로 참조
        on_delete=models.CASCADE,  # 게시물 삭제되면 분석 기록도 같이 삭제
        related_name="analyses",  # post.analyses.all()로 조회 가능
    )
    status = models.CharField(
        max_length=20,
        choices=STATUS_CHOICES,  # 위에서 정의한 4가지 값만 허용
        default=STATUS_PENDING,  # 생성 직후 기본값은 "대기중"
    )
    callback_token = models.CharField(max_length=64, unique=True)  # FastAPI 콜백 요청 검증용 토큰
    error_message = models.TextField(blank=True)  # 실패 시 에러 내용, 평소엔 빈 문자열
    created_at = models.DateTimeField(auto_now_add=True)  # 생성 시각, 최초 1회만 기록
    updated_at = models.DateTimeField(auto_now=True)  # 저장할 때마다 갱신되는 시각 (status 바뀔 때마다 갱신)

    def __str__(self):
        return f"Analysis #{self.pk} ({self.status})"

class DetectedItem(models.Model):
    # 어느 분석 결과에 속한 아이템인지 연결
    analysis = models.ForeignKey(
        Analysis,  # 같은 파일(같은 앱) 안에 있어서 문자열 아니라 클래스로 직접 참조
        on_delete=models.CASCADE,  # 분석 기록 삭제되면 검출된 아이템들도 같이 삭제
        related_name="detected_items",  # analysis.detected_items.all()로 조회
    )
    category = models.CharField(max_length=50)  # 상의/하의/신발/악세서리 등 큰 분류
    label = models.CharField(max_length=100, blank=True)  # 세부 명칭 (예: "니트", "청바지"), 없을 수도 있음

    # 바운딩 박스 좌표 4개 — 이미지 크기를 0~1 비율로 정규화해서 저장 (실제 픽셀 좌표 X)
    bbox_x = models.FloatField()       # 박스 왼쪽 위 x 위치 (0~1)
    bbox_y = models.FloatField()       # 박스 왼쪽 위 y 위치 (0~1)
    bbox_width = models.FloatField()   # 박스 너비 (0~1)
    bbox_height = models.FloatField()  # 박스 높이 (0~1)

    search_url = models.URLField(blank=True)  # 조립된 쇼핑 검색 링크

    def __str__(self):
        return f"{self.category} (analysis #{self.analysis_id})"


class StyleScore(models.Model):
    # 어느 분석 결과에 속한 스타일 점수인지 연결
    analysis = models.ForeignKey(
        Analysis,
        on_delete=models.CASCADE,  # 분석 기록 삭제되면 스타일 점수도 같이 삭제
        related_name="style_scores",  # analysis.style_scores.all()로 조회
    )
    style_name = models.CharField(max_length=50)  # "캐주얼", "스트릿" 같은 스타일 이름
    ratio = models.FloatField()  # 비율(%), 예: 60.0

    class Meta:
        # 같은 analysis 안에 같은 style_name이 중복으로 들어가는 것 방지
        unique_together = ("analysis", "style_name")

    def __str__(self):
        return f"{self.style_name} {self.ratio}% (analysis #{self.analysis_id})"

