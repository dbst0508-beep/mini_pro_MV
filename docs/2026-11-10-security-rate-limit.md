# 분석 요청 횟수 제한 + 진행 중 중복 요청 방지 (2026-11-10)

브랜치: `feature/security-rate-limit`

보안 점검표 6번(분석 요청 횟수 제한)을 처리하고, 남은 항목(1·4·8·9·10번 일부, 로그인 시도 제한)은 README의 알려진 한계로 정리해 보안 작업을 마무리했습니다.

| 커밋 | 내용 |
|---|---|
| `c249199` | feat: 분석 요청을 사용자당 1시간 10건으로 제한하고 진행 중인 게시물 분석의 중복 요청 방지 |
| `bee1c5c` | test: 분석 요청 횟수 제한과 진행 중 중복 요청 방지 테스트 추가 |
| (이후 커밋) | feat/test: 분석 버튼 아래에 남은 요청 횟수 표시 |

---

## 1. 기술문서

### 1-1. 왜 바꿨나

분석 한 건이 서버에서 하는 일은 무겁습니다.

```
분석 요청 1번 = 객체 탐지 모델(CPU) + FashionCLIP 라벨링(CPU) + Gemini API 호출 1번
```

그런데 로그인만 하면 분석 요청 버튼을 **무한히** 누를 수 있었습니다.

| 구멍 | 비유 | 실제 문제 |
|---|---|---|
| 요청 횟수 제한 없음 | 무료 시식 코너에서 한 사람이 계속 집어 감 | 반복 요청만으로 Gemini 무료 한도(또는 비용)와 서버 CPU를 다 써 버릴 수 있음. 다른 사람의 분석은 Celery 대기열 뒤로 밀림 |
| 진행 중인데 또 요청 가능 | 주문한 음식이 나오기 전에 같은 주문을 또 넣음 | 버튼을 여러 번 누르면 같은 사진을 똑같이 여러 번 분석함 |

브랜치 C에서 `Analysis.user`(요청한 사람)를 만들어 둔 덕분에, 이제 **"이 사람이 최근에 몇 번 요청했나"**를 DB에서 셀 수 있습니다.

### 1-2. 정한 규칙

| 규칙 | 값 | 이유 |
|---|---|---|
| 사용자당 최대 요청 | **1시간에 10건** (`RATE_LIMIT_COUNT`, `RATE_LIMIT_WINDOW`) | 체크리스트 예시는 1분에 3건이었지만, 분석마다 Gemini 호출이 나가므로 무료 한도를 생각하면 시간 단위가 더 실용적. 정상 사용자가 1시간에 10번 넘게 분석할 일은 드묾 |
| 세는 대상 | 게시물 기반 + 독립 업로드 **합산**, 상태 무관 | 둘 다 같은 Gemini를 씀. 실패한 분석도 이미 모델·Gemini를 썼을 수 있으므로 셈 |
| 진행 중 중복 | 같은 게시물에 `대기중`/`분석중` 분석이 있으면 새로 만들지 않고 결과 화면으로 | 버튼을 여러 번 눌러도 분석은 하나. 완료·실패 뒤에는 기존처럼 재분석 가능 |
| 남은 횟수 표시 | 게시물 상세·AI 분석 화면의 분석 버튼 아래에 `최근 1시간 남은 분석 횟수: 7 / 10` (로그인한 사람만) | 10번째에 갑자기 막히는 대신, 미리 얼마나 남았는지 알 수 있게 |

### 1-3. 요청이 거치는 검사 순서

```
게시물 기반: POST /analysis/post/<id>/request/
  ├─ 로그인 안 함 → 로그인 페이지 (@login_required, 기존)
  ├─ ① 이 게시물에 진행 중인 분석이 있음 → 결과 화면으로 (새로 안 만듦, 안내 문구 없음)
  ├─ ② 최근 1시간 내 내 요청이 10건 이상 → 게시물 화면으로 + 빨간 안내
  └─ ③ 분석 생성 → Celery

독립 업로드: POST /analysis/upload/
  ├─ 로그인 안 함 → 로그인 페이지 (기존)
  ├─ ① 사진 검사 실패 (없음 / 10MB 초과 / 이미지 아님) → 업로드 화면 + 빨간 안내 (기존)
  ├─ ② 최근 1시간 내 내 요청이 10건 이상 → 업로드 화면 + 빨간 안내
  └─ ③ 분석 생성 → Celery
```

- **게시물 기반에서 진행 중 검사가 횟수 검사보다 먼저인 이유:** 버튼을 두 번 눌렀을 뿐인 사람에게 "요청이 너무 많다"는 경고보다 진행 중 화면을 보여 주는 게 맞습니다. 새 분석을 만들지 않으니 횟수에도 영향이 없습니다.
- **업로드에서 사진 검사가 횟수 검사보다 먼저인 이유:** 이상한 파일을 올린 사람에게는 "사진이 이상하다"가 더 정확한 안내입니다.

### 1-4. 바뀐 파일

| 파일 | 바뀐 내용 |
|---|---|
| `analysis/views.py` | `RATE_LIMIT_COUNT`, `RATE_LIMIT_WINDOW`, `remaining_requests()`, `is_rate_limited()` 추가. `request_analysis`에 진행 중 검사 + 횟수 검사, `upload_and_analyze`에 횟수 검사, `home`이 남은 횟수를 화면에 넘김 |
| `posts/views.py` | `post_detail`이 남은 횟수를 화면에 넘김 (`analysis.views`에서 함수와 한도를 가져옴) |
| `templates/posts/detail.html`, `templates/analysis/home.html` | 분석 버튼 아래 남은 횟수 문구 |
| `static/css/base.css` | `.rate-limit-hint` (작은 회색 글씨) |
| `analysis/tests.py` | 새 규칙 테스트 5개, 기존 테스트 1개 준비 단계 수정 (Django 62 → 67개) |
| `README.md` | 요청 제한 설명, Gemini 무료 등급 데이터 고지, 남은 보안 항목을 알려진 한계로 정리 |

DB 구조는 바뀌지 않았습니다(마이그레이션 없음). C에서 만든 `user`, 원래 있던 `created_at`, `status`만으로 셉니다.

### 1-5. 확인한 것

| 확인 | 결과 |
|---|---|
| Django 테스트 | 67개 통과 (posts 17 · accounts 15 · analysis 35) |
| cv_service 테스트 | 30개 (변경 없음) |
| Docker 재빌드 후 브라우저 | 게시물 상세·AI 분석 화면에 남은 횟수 표시, 분석 1번 요청 후 숫자 1 감소, 로그아웃 상태에서는 안 보임 |

---

## 2. 구성요소 단위 코드리뷰

### 2-1. `is_rate_limited`: DB에서 세기

```python
def is_rate_limited(user):
    since = timezone.now() - RATE_LIMIT_WINDOW
    recent = Analysis.objects.filter(user=user, created_at__gte=since).count()
    return recent >= RATE_LIMIT_COUNT
```

- **Redis 카운터 대신 DB를 쓴 이유:** 분석 요청은 어차피 `Analysis` 행을 하나씩 만듭니다. 이미 있는 기록을 세면 되니 따로 카운터를 관리할 필요가 없습니다. 캐시 카운터는 서버를 다시 켜면 사라지거나, 분석 기록과 숫자가 어긋날 수 있습니다.
- **"최근 1시간"이 계속 움직이는 방식(sliding window):** "매 정각에 0으로 초기화"가 아니라 "지금부터 1시간 전까지"를 셉니다. 정각 직전에 10번, 직후에 10번 해서 짧은 시간에 20번 요청하는 틈이 없습니다.
- **`.count()`:** 행을 파이썬으로 가져오지 않고 DB에 `SELECT COUNT(*)`만 시킵니다. `len(...)`을 쓰면 10건을 전부 읽어 옵니다.
- **`user` 칸이 빈 옛날 분석은 세지 않습니다.** 누구의 요청인지 모르니까요.
- **한계 (동시 요청):** "세기"와 "만들기" 사이에 틈이 있습니다. 같은 사람의 요청 두 개가 정확히 동시에 들어오면 둘 다 9건으로 세고 둘 다 통과해서 11건이 될 수 있습니다. 비용을 막는 목적에는 몇 건 넘는 정도는 괜찮다고 보고 그대로 뒀습니다. 정확히 막으려면 유저 행을 `select_for_update`로 잠그고 세야 합니다.
- **한계 (안내 문구):** "1시간 뒤에 다시 시도해 주세요"라고 안내하지만, 실제로는 가장 오래된 요청이 1시간을 넘기는 순간 다시 가능해집니다. 문구를 정확히 하려면 가장 오래된 요청 시각을 따로 조회해야 해서 단순하게 뒀습니다.

### 2-2. 진행 중 중복 검사

```python
in_progress = post.analyses.filter(
    status__in=[Analysis.STATUS_PENDING, Analysis.STATUS_PROCESSING]
).exists()
if in_progress:
    return redirect("analysis:result", post_id=post.id)
```

- **`.exists()`:** "하나라도 있나?"만 알면 되므로 개수를 세지 않고, DB가 하나를 찾는 즉시 멈춥니다.
- **누가 요청했든 막습니다.** 같은 게시물 사진을 두 사람이 동시에 분석해도 결과는 같으니, 진행 중인 결과를 같이 보면 됩니다.
- **멈춰 버린 분석은 어떻게 되나?** Celery가 꺼져 `대기중`에서 멈춘 분석이 있으면 새 요청이 계속 결과 화면으로 보내집니다. 그런데 결과 화면은 3초마다 상태 조회 API를 부르고, 이 API가 6분이 지난 미완료 분석을 `실패`로 바꿉니다(`STALE_AFTER`). 그러면 다시 요청할 수 있습니다. 기존 실패 처리 장치가 이 경우도 풀어 줍니다.
- **한계 (진짜 동시 클릭):** 2-1과 같은 틈이 있습니다. 버튼을 아주 빠르게 두 번 눌러 요청 두 개가 동시에 처리되면 둘 다 "진행 중 없음"으로 보고 분석이 두 개 생길 수 있습니다. 화면에서 버튼을 한 번 누르면 비활성화하거나, 게시물 행을 잠그면 막을 수 있습니다.
- **독립 업로드에는 이 검사가 없습니다.** 매번 다른 사진일 수 있어서 "같은 분석"을 판단할 기준이 없습니다. 횟수 제한만 적용됩니다.

### 2-3. `remaining_requests`: 화면 숫자와 막는 기준을 하나로

```python
def remaining_requests(user):
    ...
    return max(RATE_LIMIT_COUNT - recent, 0)

def is_rate_limited(user):
    return remaining_requests(user) == 0
```

- **세는 곳은 한 군데:** 처음에는 `is_rate_limited`가 직접 셌습니다. 화면에 남은 횟수를 보여 주려고 세는 함수를 따로 만들 때, 막는 함수가 **그 결과를 그대로 쓰도록** 바꿨습니다. 세는 코드가 두 벌이면 한쪽만 고쳤을 때 "화면엔 3번 남았다는데 막힘" 같은 일이 생깁니다.
- **`max(..., 0)`:** 동시 요청으로 한도를 넘으면(2-1 한계) `10 - 11 = -1`이 됩니다. 화면에 "-1 / 10"이 나오지 않게 0으로 바닥을 깔았습니다. 막는 조건도 `== 0`이라 음수일 때도 막힙니다.
- **`posts/views.py`가 `analysis.views`를 import:** 게시물 상세 화면에도 숫자가 필요해서 함수를 가져다 씁니다. `analysis/views.py`는 `posts/models.py`만 불러오므로 서로 물고 물리는 import(순환 import)는 생기지 않습니다.
- **한도 숫자도 넘깁니다(`rate_limit_count`):** 템플릿에 `/ 10`을 직접 쓰면, 한도를 바꿨을 때 화면만 옛 숫자로 남습니다(5-3).
- **대가:** 게시물 상세와 AI 분석 화면을 열 때마다 `COUNT` 쿼리가 한 번 더 나갑니다. `user`에 인덱스가 있는 가벼운 쿼리라 그대로 뒀습니다.

### 2-4. 기준값을 위쪽 상수로

`RATE_LIMIT_COUNT = 10`, `RATE_LIMIT_WINDOW = timedelta(hours=1)`을 파일 위쪽에 `STALE_AFTER`와 나란히 뒀습니다. 테스트도 이 상수를 import해서 쓰므로, 나중에 20건으로 바꿔도 테스트를 고칠 필요가 없습니다. 실행 환경마다 바꿀 값이 아니라서 환경변수로는 빼지 않았습니다.

---

## 3. 코드 한 줄 한 줄 주석

### 3-1. `analysis/views.py`: 기준값과 검사 함수

```python
STALE_AFTER = timedelta(minutes=6)       # (기존) 6분 지나도 안 끝나면 실패로 봄

RATE_LIMIT_COUNT = 10                    # 한 사람이 아래 시간 동안 요청할 수 있는 분석 수 (분석마다 Gemini 호출 = 비용)
RATE_LIMIT_WINDOW = timedelta(hours=1)   # 횟수를 세는 기간

def is_rate_limited(user):
    """최근 1시간 동안 이 사람이 요청한 분석이 10건 이상이면 True"""
    since = timezone.now() - RATE_LIMIT_WINDOW    # 지금 시각 - 1시간 = 세기 시작할 시각
    recent = Analysis.objects.filter(
        user=user,                                # 이 사람이 요청한 분석 중에서
        created_at__gte=since,                    # __gte = "크거나 같다" → since 이후에 만든 것만
    ).count()                                     # 개수만 DB에서 셈
    return recent >= RATE_LIMIT_COUNT             # 이미 10건이면 11번째는 막음 (> 가 아니라 >=)
```

`>=`인 이유: 이미 10건을 했으면 지금 요청이 11번째입니다. `>`로 쓰면 11번째까지 허용돼서 실제 한도가 11건이 됩니다.

### 3-2. `analysis/views.py`: `request_analysis`

```python
@login_required
@require_POST
def request_analysis(request, post_id):
    post = get_object_or_404(Post, pk=post_id)

    in_progress = post.analyses.filter(                                   # 이 게시물의 분석 중에서
        status__in=[Analysis.STATUS_PENDING, Analysis.STATUS_PROCESSING]  # __in = "이 목록 중 하나" → 대기중 또는 분석중
    ).exists()                                                            # 하나라도 있으면 True
    if in_progress:
        return redirect("analysis:result", post_id=post.id)               # 새로 만들지 않고 진행 중 화면으로 (안내 문구 없음)

    if is_rate_limited(request.user):                                     # 최근 요청이 너무 많으면
        messages.error(request, "분석 요청이 너무 많습니다. 1시간 뒤에 다시 시도해 주세요.")  # 다음 화면에 한 번 보여 줄 빨간 안내
        return redirect("posts:detail", post_id=post.id)                  # 분석은 만들지 않고 게시물 화면으로

    analysis = Analysis.objects.create(...)                               # (기존) 여기까지 오면 생성
```

`return redirect(...)`가 함수를 그 자리에서 끝내므로, 아래의 `create`는 실행되지 않습니다. 검사를 통과한 요청만 맨 아래까지 내려옵니다.

### 3-3. `analysis/views.py`: `upload_and_analyze`

```python
    try:
        validate_uploaded_image(image)             # (기존) 사진 검사
    except ValidationError as error:
        messages.error(request, error.messages[0])
        return redirect("analysis:home")
    if is_rate_limited(request.user):              # 독립 업로드도 같은 한도에 포함
        messages.error(request, "분석 요청이 너무 많습니다. 1시간 뒤에 다시 시도해 주세요.")
        return redirect("analysis:home")           # 업로드 화면으로 (분석은 만들지 않음)
    analysis = Analysis.objects.create(...)        # (기존)
```

### 3-4. 남은 횟수 표시

```python
# analysis/views.py
def remaining_requests(user):
    """최근 1시간 기준으로 이 사람이 더 요청할 수 있는 분석 수 (0 미만으로는 안 내려감)"""
    since = timezone.now() - RATE_LIMIT_WINDOW
    recent = Analysis.objects.filter(user=user, created_at__gte=since).count()
    return max(RATE_LIMIT_COUNT - recent, 0)        # max(a, 0): a가 음수면 0, 아니면 a 그대로

def is_rate_limited(user):
    """더 요청할 수 있는 횟수가 0이면 True"""
    return remaining_requests(user) == 0            # 세는 일은 위 함수에 맡김

def home(request):
    remaining = remaining_requests(request.user) if request.user.is_authenticated else None
    # "A if 조건 else B": 조건이 참이면 A, 아니면 B → 로그인 안 했으면 None (비로그인 유저로 DB를 셀 수 없으므로)
    return render(request, "analysis/home.html", {"remaining_requests": remaining, "rate_limit_count": RATE_LIMIT_COUNT})
```

```html
<!-- templates/analysis/home.html, posts/detail.html: 둘 다 {% if user.is_authenticated %} 안 -->
<p class="rate-limit-hint">최근 1시간 남은 분석 횟수: {{ remaining_requests }} / {{ rate_limit_count }}</p>
```

```python
# analysis/tests.py
    def test_home_shows_remaining_requests(self, mock_task):
        Analysis.objects.create(user=self.user, callback_token="used-1")  # 최근 1시간에 1건 요청한 상태
        self.client.force_login(self.user)
        response = self.client.get(reverse("analysis:home"))
        self.assertContains(response, f"{RATE_LIMIT_COUNT - 1} / {RATE_LIMIT_COUNT}")
        # assertContains: 응답이 200이고, 화면 HTML 안에 이 글자("9 / 10")가 있는지 확인
```

### 3-5. `analysis/tests.py`: 대표 테스트

```python
from .views import STALE_AFTER, RATE_LIMIT_COUNT   # 숫자 10을 테스트에 다시 적지 않고 코드의 값을 그대로 씀

    def fill_rate_limit(self):
        """self.user가 최근에 분석을 한도만큼 요청한 상태로 만듦"""
        for number in range(RATE_LIMIT_COUNT):                         # 0부터 9까지 10번
            Analysis.objects.create(user=self.user, callback_token=f"limit-{number}")  # 토큰은 unique라 번호를 붙임
        # 게시물 없는 분석이라 "이 게시물에 진행 중인 분석" 검사에는 걸리지 않음 → 횟수 검사만 따로 시험 가능
        # test_로 시작하지 않으므로 테스트로 실행되지 않는 도우미 함수

    def test_old_requests_do_not_count(self, mock_task):
        Analysis.objects.filter(pk=self.analysis.pk).update(status=Analysis.STATUS_COMPLETED)  # setUp 분석을 "완료"로 (진행 중 검사 통과용)
        self.fill_rate_limit()                                         # 10건 채움
        Analysis.objects.filter(callback_token__startswith="limit-").update(
            created_at=timezone.now() - timedelta(hours=2)             # 그 10건을 2시간 전 요청으로 바꿈
        )
        # created_at은 auto_now_add라서 create(created_at=...)로 넣어도 무시되고 "지금"이 들어감.
        # update()는 DB에 바로 쓰므로 auto_now_add를 거치지 않음
        self.client.force_login(self.user)
        self.client.post(reverse("analysis:request", args=[self.post.id]))

        self.assertEqual(Analysis.objects.count(), 2 + RATE_LIMIT_COUNT)  # setUp 1 + 옛 요청 10 + 새 요청 1
        mock_task.delay.assert_called_once()                           # Celery에도 한 번 넘겨야 함
```

`test_old_requests_do_not_count`는 **제한이 풀리는지**를 확인합니다. "막는다"만 테스트하면, 실수로 기간 조건(`created_at__gte`)을 빼먹어 한 번 걸리면 영원히 막히는 버그를 잡을 수 없습니다.

---

## 4. 복습

### Rate limiting (요청 횟수 제한)
"일정 시간 안에 할 수 있는 요청 수"를 제한하는 것입니다. 로그인 검사(누가)와 권한 검사(무엇을)로는 막을 수 없는, **"얼마나 자주"**의 문제를 다룹니다. 비용이 드는 외부 API(Gemini)나 무거운 작업(모델 추론) 앞에는 거의 항상 필요합니다.

### 고정 창(fixed window) vs 움직이는 창(sliding window)
- 고정 창: "14:00~15:00에 10건". 14:59에 10건, 15:00에 10건 → 1분 사이에 20건이 가능합니다.
- 움직이는 창: "지금부터 1시간 전까지 10건". 언제 재도 1시간 안에 10건을 넘지 않습니다.
이번에는 이미 있는 `created_at`으로 세니 움직이는 창이 오히려 더 간단했습니다.

### Django 조회 조건 `__gte`, `__in`, `__startswith`
필드 이름 뒤에 `__조건`을 붙여 SQL 조건을 만듭니다.
| 쓰는 법 | 뜻 | SQL |
|---|---|---|
| `created_at__gte=t` | t 이후(포함) | `created_at >= t` |
| `status__in=[a, b]` | a 또는 b | `status IN (a, b)` |
| `callback_token__startswith="limit-"` | "limit-"로 시작 | `LIKE 'limit-%'` |

### `.count()` vs `.exists()` vs `len()`
- `.exists()`: 있나 없나만. 하나 찾으면 멈춤 → 가장 가벼움
- `.count()`: 개수. DB가 세서 숫자만 돌려줌
- `len(queryset)`: 행을 전부 파이썬으로 가져온 뒤 셈 → 개수만 필요하면 낭비

### 검사 → 생성 사이의 틈 (race condition)
"세고 나서 만든다"는 두 단계 사이에 다른 요청이 끼어들 수 있습니다. 요청이 동시에 오면 둘 다 같은 숫자를 보고 통과합니다. 정확히 막으려면 DB 잠금(`select_for_update`)이나 DB 제약(unique)이 필요합니다. 이번에는 "비용을 크게 새지 않게"가 목적이라 작은 오차를 받아들였습니다. 이런 결정은 **이유와 함께 기록해 두는 것**이 중요합니다.

### `auto_now_add`는 `create()`로 못 바꾼다
`auto_now_add=True` 필드는 저장할 때 Django가 "지금"으로 덮어씁니다. 테스트에서 과거 시각을 만들려면 `QuerySet.update()`로 DB에 직접 써야 합니다. 기존 상태 조회 테스트(6분 지난 분석)도 같은 방법을 씁니다.

### 새 규칙은 기존 테스트의 전제를 깬다
테스트 준비물(`setUp`)이 만드는 분석이 `대기중`이라서, "진행 중이면 막는다"는 규칙을 넣자 기존 요청 테스트의 전제가 틀려졌습니다. 기능을 추가할 때는 **기존 테스트가 무엇을 당연하게 여기고 있었는지**도 같이 봐야 합니다.

---

## 5. 트러블슈팅

### 5-1. 새 규칙 때문에 기존 테스트가 깨질 상황 (미리 처리)
- **상황:** `AnalysisTestCase.setUp`이 게시물 분석을 하나 만드는데, 상태 기본값이 `대기중`입니다. 진행 중 검사를 넣으면 `test_logged_in_user_can_request_on_others_post`의 요청이 "진행 중"에 걸려 새 분석이 생기지 않으므로 실패합니다.
- **처리:** 코드를 넣기 전에 이 영향을 미리 확인하고, 그 테스트 첫 줄에서 setUp의 분석을 `완료`로 바꿨습니다. 테스트가 확인하려던 것("남의 게시물도 분석 요청 가능")은 그대로입니다.
- **배운 점:** 공용 준비물(`setUp`)을 쓰는 테스트가 많을수록, 새 규칙 하나가 여러 테스트에 영향을 줍니다. 규칙을 넣기 전에 `grep "analysis:request"`로 이 주소를 부르는 테스트를 먼저 찾아봤습니다.

### 5-2. `fill_rate_limit`이 진행 중 검사에 걸리지 않게
- **고민:** 한도를 채우려고 게시물 분석을 10개 만들면, 그 분석들이 `대기중`이라 횟수 검사 전에 진행 중 검사에 먼저 걸립니다. 그러면 횟수 제한을 시험할 수 없습니다.
- **처리:** 한도 채우기용 분석은 **게시물 없이**(`post=None`) 만들었습니다. 횟수에는 포함되지만(같은 `user`) 이 게시물의 진행 중 검사에는 안 걸립니다. 두 규칙을 따로따로 시험할 수 있게 됐습니다.

### 5-3. 템플릿에 한도 숫자 `/ 10`을 직접 씀
- **증상:** AI 분석 화면 템플릿에 `{{ remaining_requests }} / 10`처럼 한도가 숫자로 들어갔습니다. 테스트는 통과했습니다.
- **원인:** 안내 예시에 처음 `/ 10`으로 적었다가 아래에서 고쳐 달라고 덧붙여서, 헷갈리게 전달됐습니다. 테스트가 잡지 못한 이유는 지금 한도가 실제로 10이라 화면에 "9 / 10"이 똑같이 나오기 때문입니다.
- **해결:** `/ {{ rate_limit_count }}`로 바꾸고, `home` 뷰가 `RATE_LIMIT_COUNT`를 넘기게 했습니다.
- **배운 점:** 테스트가 통과해도 "**지금 값과 우연히 같아서**" 통과했을 수 있습니다. 화면에 숫자를 직접 쓰는 곳은 코드를 직접 읽어서 확인해야 합니다.

### 보안 작업 마무리: 남은 항목 (README 알려진 한계에 기록)
| 점검표 | 내용 | 남긴 이유 |
|---|---|---|
| 1번 일부 | `ALLOWED_HOSTS`가 코드에 고정 | 로컬·compose 실행에는 문제없음. 배포할 때 도메인과 함께 환경변수로 |
| 4번 일부 | 콜백 본문이 JSON이 아니면 500 | 콜백은 출입증·토큰을 가진 cv_service만 보냄. 결과는 실패 처리로 정리됨 |
| 8번 | 컨테이너가 root로 실행됨 | `media/` 쓰기 권한 확인이 필요해 배포 단계에서 |
| 10번 | 개발용 `runserver` | 배포 단계에서 gunicorn·nginx |
| (추가) | 로그인 시도 횟수 제한 없음 | 비밀번호 대입 공격 가능. 배포 전 django-axes 같은 도구나 캐시 기반 잠금 |
| 9번 | Gemini 무료 등급 데이터 사용 | 코드 변경 없음. README에 고지 |
