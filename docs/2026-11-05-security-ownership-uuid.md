# 분석 주인 기록 + 본인만 보기 + 업로드 파일명 UUID (2026-11-03 ~ 2026-11-05)

브랜치: `feature/security-ownership-throttle`

보안 점검표 C 묶음 중 "남의 분석 결과 열람"과 "업로드 파일명 노출"을 처리했습니다. 같은 묶음의 요청 횟수 제한과 로그인 시도 제한은 성격이 다른 작업이라 다음 브랜치로 넘겼습니다. 브랜치 이름에 `throttle`이 들어 있지만 이번 브랜치에는 포함되지 않습니다.

| 커밋 | 내용 |
|---|---|
| `776a50d` | feat: 분석 요청자를 `Analysis.user`로 저장 |
| `de45d55` | fix: 독립 업로드 분석 결과를 요청한 본인만 볼 수 있도록 제한 |
| `4545b49` | docs: README의 Gemini 모델명 수정 (`gemini-3.5-flash-lite`) |
| `e318df3` | feat: 업로드 파일명을 UUID로 바꿔 원래 파일명 노출 방지 |
| `426c9dc` | test: 독립 업로드 파일이 UUID 이름으로 저장되는지 확인 |

---

## 1. 기술문서

### 1-1. 왜 바꿨나

독립 업로드 결과 주소는 `/analysis/<analysis_id>/result/`입니다. 번호는 1, 2, 3… 순서대로 늘어납니다.

| 구멍 | 비유 | 실제 문제 |
|---|---|---|
| 결과 화면이 번호만 보고 보여 줌 | 사물함 번호만 대면 아무 사물함이나 열어 줌 | **IDOR**: 로그인도 안 한 사람이 주소의 숫자만 바꿔서 남이 올린 사진과 분석 결과를 볼 수 있음 |
| 분석에 "누가 요청했는지" 칸이 없음 | 사물함에 주인 이름표가 없음 | 막고 싶어도 "이 사람이 주인인가?"를 판단할 근거가 없음 |
| 업로드 파일 이름을 그대로 저장 | 택배 상자에 받는 사람 실명을 크게 써 둠 | `/media/profiles/홍길동_증명사진.jpg`처럼 원래 파일 이름의 개인정보가 URL에 드러나고, `IMG_0001.jpg` 같은 이름은 다음 번호를 짐작하기 쉬움 |

그래서 순서를 이렇게 잡았습니다.
1. **이름표 달기** (`Analysis.user`): 막으려면 먼저 주인을 알아야 합니다.
2. **이름표 확인하기** (`get_visible_analysis`): 결과 화면과 상태 조회 API에서 주인만 통과시킵니다.
3. **파일 이름 지우기** (UUID): 결과 화면을 막아도 사진 파일 자체는 `/media/...` 주소로 바로 열립니다. 그래서 그 주소를 짐작할 수 없게 만듭니다.

### 1-2. 바뀐 파일

| 파일 | 바뀐 내용 |
|---|---|
| `analysis/models.py` | `user` FK 추가 (비워둘 수 있음), `image`의 `upload_to`를 UUID 함수로 |
| `analysis/migrations/0004_analysis_user.py` | `user` 칸 추가 |
| `analysis/migrations/0005_alter_analysis_image.py` | `upload_to` 변경 (DB 구조는 그대로) |
| `analysis/views.py` | 요청·업로드할 때 `user=request.user` 저장, `get_visible_analysis` 추가, 독립 결과 화면과 상태 조회가 이 함수를 거침 |
| `analysis/admin.py` | 분석 목록·상세에 "요청한 사람"(`user`) 표시, 보기 전용 |
| `posts/models.py` + `0002_alter_post_image.py` | 게시물 사진 `upload_to`를 UUID 함수로 |
| `accounts/models.py` + `0003_alter_user_profile_image.py` | 프로필 사진 `upload_to`를 UUID 함수로 |
| `analysis/tests.py` | 주인 저장 확인 2줄, 접근 제한 테스트 5개, UUID 이름 확인 1줄 (Django 57 → 62개) |
| `README.md` | Gemini 모델명 수정, 이번 변경 반영 |

### 1-3. 누가 무엇을 볼 수 있나

| 분석 종류 | 결과 화면 | 상태 조회 API | 이유 |
|---|---|---|---|
| 게시물 기반 (`post`가 있음) | 누구나 | 누구나 | 게시물 사진은 이미 피드에 공개돼 있으므로 분석 결과도 공개 |
| 독립 업로드 (`post`가 없음) | **요청한 본인만** | **요청한 본인만** | 피드에 올리지 않은 개인 사진 |
| 독립 업로드인데 `user`가 비어 있음 (이 기능 전에 만든 분석) | 아무도 못 봄 | 아무도 못 봄 | 주인을 알 수 없으면 잠그는 쪽이 안전 (관리자 화면에서는 보임) |

본인이 아니면 **403이 아니라 404**를 돌려줍니다. 403은 "있긴 한데 넌 못 봐"라는 뜻이라, 번호를 바꿔 가며 어떤 번호에 분석이 있는지 알아낼 수 있기 때문입니다.

### 1-4. 업로드 파일 저장 위치

| 대상 | 예전 | 지금 |
|---|---|---|
| 게시물 사진 | `media/posts/원래이름.jpg` | `media/posts/<32자 무작위>.jpg` |
| 프로필 사진 | `media/profiles/원래이름.jpg` | `media/profiles/<32자 무작위>.jpg` |
| 독립 업로드 | `media/analysis_uploads/원래이름.jpg` | `media/analysis_uploads/<32자 무작위>.jpg` |

- 확장자는 원래 파일의 것을 소문자로 바꿔 씁니다(`.JPG` → `.jpg`).
- **이미 저장된 파일은 그대로**입니다. DB에 예전 경로가 그대로 있어서 깨지지 않고, 새로 올리는 파일부터 적용됩니다.
- 마이그레이션 3개는 모두 `AlterField`이고 DB 테이블 구조는 바뀌지 않습니다(`upload_to`는 파이썬 쪽 설정).

### 1-5. 확인한 것

| 확인 | 결과 |
|---|---|
| `makemigrations` | 3개 앱에 `AlterField` 마이그레이션 생성, `upload_to=<앱>.models.<함수이름>`으로 기록됨 |
| Django 테스트 | 62개 통과 (posts 17 · accounts 15 · analysis 30) |
| cv_service 테스트 | 30개 (이번 브랜치에서 변경 없음) |

---

## 2. 구성요소 단위 코드리뷰

### 2-1. `Analysis.user`: 이름표 칸

```python
user = models.ForeignKey(
    settings.AUTH_USER_MODEL,
    on_delete=models.CASCADE,
    related_name="analyses",
    null=True, blank=True,
)
```

- **`null=True`인 이유:** 이 칸을 추가하기 전에 만든 분석들은 주인을 알 수 없습니다. 비워둘 수 없게 하면 마이그레이션이 "기존 행에 뭘 넣을까요?"라고 묻고, 아무 유저나 넣으면 엉뚱한 사람이 주인이 됩니다.
- **`CASCADE`:** 회원이 탈퇴하면 그 사람의 분석 기록도 같이 지웁니다. 게시물(`Post.user`)과 같은 규칙입니다.
- **`related_name="analyses"`:** `Post`에도 같은 이름(`post.analyses`)이 있지만, 붙는 모델이 다르니(`User` vs `Post`) 충돌하지 않습니다. `user.analyses.all()`로 내 분석 목록을 꺼낼 수 있습니다.
- **게시물 기반 분석의 주인은 "요청한 사람"입니다.** 게시물 주인이 아닙니다. 남의 게시물도 분석을 요청할 수 있으므로, 나중에 "한 사람이 하루에 몇 번 요청했나"를 셀 때 이 칸을 씁니다(다음 브랜치의 요청 횟수 제한).

### 2-2. `get_visible_analysis`: 이름표 확인

```python
def get_visible_analysis(request, analysis_id):
    analysis = get_object_or_404(Analysis, pk=analysis_id)
    if analysis.post_id is None and analysis.user != request.user:
        raise Http404
    return analysis
```

- **한 곳에서만 검사:** 결과 화면(`standalone_result`)과 상태 조회 API(`analysis_status`)가 모두 이 함수를 거칩니다. 결과 화면만 막고 상태 API를 빼먹으면, 상태 API로 "이 번호의 분석이 있는지"를 알아낼 수 있습니다.
- **`post_id is None`:** `analysis.post`라고 쓰면 게시물을 DB에서 한 번 더 읽어 옵니다. `post_id`는 이미 읽어 온 숫자라 추가 조회가 없습니다.
- **`analysis.user != request.user`:** 로그인하지 않은 사람의 `request.user`는 `None`이 아니라 `AnonymousUser`라는 객체입니다. 그래서 주인이 비어 있는 옛날 분석(`None`)과 비교해도 같다고 나오지 않습니다(4장 "None == None 함정" 참고).
- **한계:** 게시물 기반 분석은 일부러 공개로 뒀습니다. 게시물을 비공개로 바꾸는 기능이 생기면 이 규칙도 같이 바꿔야 합니다.

### 2-3. 요청·업로드 뷰: `user=request.user`

두 뷰 모두 `@login_required`가 붙어 있어서 `request.user`는 항상 로그인한 진짜 유저입니다. 그래서 `Analysis.objects.create(...)`에 한 줄만 추가하면 됩니다.

### 2-4. 관리자 화면

- 목록에 `user` 칸을 추가하고, `list_select_related`에 `"user"`를 넣어 목록을 그릴 때 유저를 한 번에 가져옵니다(행마다 DB를 다시 조회하지 않게).
- 상세 화면에서 `user`는 보기 전용입니다. 관리자가 주인을 바꾸면 남의 결과를 보게 만들 수 있기 때문입니다.
- **고쳐야 할 점 (이번 문서 작성 중 발견):** `AnalysisAdmin`에 `readonly_fields`가 두 줄(39번, 41번) 있습니다. 파이썬은 아래 줄로 덮어쓰기 때문에 동작은 맞지만, 위 줄은 지워야 합니다. 또 C-1 커밋에서 `list_filter = ["status", "created_at"]` 줄이 빠져서 **오른쪽 상태 필터(대기중/분석중/완료/실패)가 사라졌습니다.** 39번 줄 자리에 `list_filter`를 되돌리면 두 문제가 같이 해결됩니다.

### 2-5. 업로드 경로 함수 3개

```python
def post_image_path(instance, filename):
    return f"posts/{uuid.uuid4().hex}{Path(filename).suffix.lower()}"
```

- **함수 하나로 합치지 않은 이유:** `upload_to`에는 `(instance, filename)` 두 개만 받는 함수를 넣어야 합니다. 폴더 이름을 인자로 받는 공용 함수를 만들려면 `functools.partial`이나 클래스가 필요한데, 둘 다 마이그레이션에 적기 까다롭습니다. 한 줄짜리 함수 3개가 가장 단순합니다.
- **`uuid4`:** 완전 무작위입니다. `uuid1`은 시각과 컴퓨터 정보로 만들어서 짐작할 여지가 있습니다.
- **확장자를 믿어도 되는 이유:** 업로드 검사(`config/validators.py`)의 `forms.ImageField`가 확장자도 이미지 확장자인지 검사합니다. `.html`, `.php` 같은 이름은 여기까지 오지 못합니다.
- **한계:** UUID는 "주소를 짐작할 수 없게" 할 뿐, 주소를 아는 사람은 여전히 사진을 열 수 있습니다. `/media/`는 로그인 검사 없이 파일을 그대로 내줍니다. 사진 파일 자체를 본인만 열게 하려면 파일을 뷰를 통해 내주는 방식으로 바꿔야 합니다(배포 단계 과제).

---

## 3. 코드 한 줄 한 줄 주석

### 3-1. `analysis/models.py` (추가한 부분)

```python
import uuid                     # 겹치지 않는 무작위 이름을 만들 때 씀
from pathlib import Path        # 파일명에서 확장자(.jpg)만 꺼낼 때 씀

def analysis_image_path(instance, filename):
    """독립 업로드 사진도 무작위 이름으로 저장"""
    # instance: 저장 중인 Analysis 객체 (여기서는 안 씀), filename: 사용자가 올린 원래 파일 이름
    # uuid.uuid4().hex: "3f9a0c...e1" 같은 32자 문자열 (하이픈 없는 버전)
    # Path("내사진.JPG").suffix → ".JPG", .lower() → ".jpg"
    return f"analysis_uploads/{uuid.uuid4().hex}{Path(filename).suffix.lower()}"


class Analysis(models.Model):
    ...
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,  # accounts.User를 문자열로 참조 (모델을 직접 import하지 않음)
        on_delete=models.CASCADE,  # 회원이 탈퇴하면 그 사람의 분석 기록도 같이 삭제
        related_name="analyses",  # user.analyses.all()로 내 분석 목록 조회
        null=True, blank=True,  # 이 칸을 만들기 전에 생긴 분석들은 주인을 알 수 없으므로 비워 둘 수 있게
    )
    ...
    image = models.ImageField(
        upload_to=analysis_image_path,  # 문자열 대신 함수 이름 (괄호 없이! 괄호를 붙이면 지금 한 번 실행한 결과가 들어감)
        blank=True, null=True,  # 게시물 기반 분석에서는 이 칸이 비어 있음
    )
```

`posts/models.py`의 `post_image_path`, `accounts/models.py`의 `profile_image_path`도 폴더 이름만 다르고 똑같습니다. 세 파일 모두 **함수가 클래스보다 위에** 있어야 합니다.

### 3-2. `analysis/views.py`: 요청자 저장

```python
@login_required                              # 로그인 안 했으면 여기 오기 전에 로그인 페이지로 보냄
@require_POST
def request_analysis(request, post_id):
    post = get_object_or_404(Post, pk=post_id)
    analysis = Analysis.objects.create(
        user=request.user,                   # 요청한 사람을 주인으로 기록 (게시물 주인이 아님)
        post=post,
        callback_token=secrets.token_hex(32),
    )
```

`upload_and_analyze`도 같은 방식으로 `user=request.user`를 넣습니다.

### 3-3. `analysis/views.py`: 접근 제한

```python
def get_visible_analysis(request, analysis_id):
    """이 사람이 볼 수 있는 분석만 돌려줌. 독립 업로드는 요청한 본인만, 게시물 기반은 누구나"""
    analysis = get_object_or_404(Analysis, pk=analysis_id)          # 없는 번호면 404
    if analysis.post_id is None and analysis.user != request.user:   # 독립 업로드인데 요청한 사람이 아니면
        raise Http404                                                # 남의 분석은 "없는 것"처럼 404
    return analysis                                                  # 통과하면 분석 객체를 그대로 돌려줌


def standalone_result(request, analysis_id):
    analysis = get_visible_analysis(request, analysis_id)   # 예전: get_object_or_404(Analysis, pk=analysis_id)
    return render(request, "analysis/standalone_result.html", {"analysis": analysis})


@require_GET
def analysis_status(request, analysis_id):
    analysis = get_visible_analysis(request, analysis_id)   # 결과 화면과 같은 규칙
    ...
```

`raise Http404`는 함수를 그 자리에서 멈추고, Django가 받아서 404 페이지를 보여 줍니다. 그래서 부르는 쪽(`standalone_result`)은 "통과했으면 볼 수 있는 분석"이라고 믿고 그냥 쓰면 됩니다.

### 3-4. `analysis/tests.py`: 대표 테스트

```python
class StandaloneAccessTests(AnalysisTestCase):
    def setUp(self):
        super().setUp()                                     # 부모의 준비(유저 2명, 게시물, 게시물 기반 분석)를 먼저 실행
        self.standalone = Analysis.objects.create(          # user가 게시물 없이 올린 분석
            user=self.user, image=generate_test_image(), callback_token="standalone-token",
        )
        self.result_url = reverse("analysis:standalone_result", args=[self.standalone.id])
        self.status_url = reverse("analysis:status", args=[self.standalone.id])

    def test_other_user_gets_404(self):
        self.client.force_login(self.other_user)            # 남으로 로그인
        self.assertEqual(self.client.get(self.result_url).status_code, 404)  # 결과 화면: 없는 것처럼
        self.assertEqual(self.client.get(self.status_url).status_code, 404)  # 상태 API도 같이 막혀야 함

    def test_ownerless_old_upload_is_hidden_from_anonymous(self):
        Analysis.objects.filter(pk=self.standalone.pk).update(user=None)  # 주인 칸이 생기기 전의 옛날 분석처럼
        self.assertEqual(self.client.get(self.result_url).status_code, 404)  # 로그인 안 한 사람에게도 안 보여야 함

    def test_post_based_status_is_still_public(self):
        url = reverse("analysis:status", args=[self.analysis.id])  # 게시물 기반 분석
        self.assertEqual(self.client.get(url).status_code, 200)    # 이건 지금처럼 누구나 조회 가능해야 함 (막다가 정상 기능을 깨지 않았는지)
```

UUID 확인은 기존 업로드 테스트에 한 줄을 추가했습니다.

```python
self.assertRegex(new_analysis.image.name, r"^analysis_uploads/[0-9a-f]{32}\.jpg$")
# ^ ... $       : 처음부터 끝까지 이 모양이어야 함
# [0-9a-f]{32}  : 0~9, a~f 문자가 정확히 32개 (uuid4().hex 모양)
# \.jpg         : 진짜 점(.) + jpg ("\" 없으면 점은 "아무 글자"라는 뜻)
```

---

## 4. 복습

### IDOR (Insecure Direct Object Reference)
주소에 들어 있는 번호(`/analysis/7/result/`)를 그대로 믿고 데이터를 보여 주는 문제입니다. 로그인 검사(`@login_required`)만으로는 막을 수 없습니다. "로그인했나?"가 아니라 **"이 사람의 것인가?"**를 물어봐야 합니다.

### 404 vs 403
- 403: "있는데 너는 못 봐" → 번호가 존재한다는 정보가 샙니다.
- 404: "그런 거 없어" → 남의 것과 진짜 없는 것을 구분할 수 없습니다.
남의 개인 데이터는 404가 보통입니다. GitHub의 비공개 저장소도 권한이 없으면 404를 보여 줍니다.

### None == None 함정
주인 비교를 `analysis.user_id == request.user.id`처럼 **번호로** 했다면 어떻게 될까요? 로그인하지 않은 사람의 `request.user.id`는 `None`이고, 주인이 비어 있는 옛날 분석의 `user_id`도 `None`입니다. `None == None`은 `True`라서 **아무나 통과**합니다. 객체끼리 비교(`analysis.user != request.user`)하면 `None`과 `AnonymousUser`라서 다르게 나옵니다. `test_ownerless_old_upload_is_hidden_from_anonymous`가 이 경우를 지킵니다.

### 검사는 한 함수에 모은다
같은 규칙을 뷰마다 따로 쓰면 하나를 빼먹기 쉽습니다(상태 API처럼). `get_visible_analysis` 하나에 모으면 규칙을 바꿀 때도 한 곳만 고치면 됩니다.

### 나중에 추가하는 FK는 `null=True`
이미 데이터가 있는 테이블에 "비워둘 수 없는" 칸을 추가하면, 기존 행에 넣을 값이 없습니다. 주인을 모르는 기존 행은 비워 두고, 새 행부터 채웁니다.

### `upload_to`에 함수 넣기
Django가 파일을 저장할 때 `함수(모델 객체, 원래 파일명)`을 불러서 돌려받은 경로에 저장합니다. 마이그레이션 파일에는 `upload_to=posts.models.post_image_path`처럼 **함수의 이름(주소)**이 적힙니다. 그래서
- `lambda`(이름 없는 함수)는 쓸 수 없고,
- 나중에 이 함수 이름을 바꾸거나 지우면 옛날 마이그레이션 파일이 깨집니다.

### 파이썬은 위에서 아래로 읽는다
클래스 본문은 파일을 읽는 순간 실행됩니다. 그래서 `upload_to=profile_image_path`가 실행될 때 그 함수가 이미 위에 정의돼 있어야 합니다. 함수 **안**에서 다른 함수를 부르는 건 순서와 상관없지만(실행할 때 찾으니까), 클래스 본문은 다릅니다.

### `return` 아래 줄은 실행되지 않는다
`return`을 만나면 함수가 끝납니다. 같은 들여쓰기로 그 아래에 쓴 줄은 문법 에러도 없이 조용히 무시됩니다(5-2 참고).

### `--env-file .env`
`SECRET_KEY`를 `.env`로 옮긴 뒤로는 `manage.py`로 실행하는 모든 명령(`makemigrations`, `migrate`, `test`, `runserver`)에 `uv run --env-file .env`가 필요합니다.

---

## 5. 트러블슈팅

### 5-1. 테스트 5개가 `RecursionError`, 3개가 `200 != 404`
- **증상:** 상태 조회 API를 부르는 테스트 5개가 `RecursionError: maximum recursion depth exceeded`로 터지고, 접근 제한 테스트 3개가 404 대신 200을 받음.
- **원인:** `get_visible_analysis` 안 첫 줄이 `get_object_or_404(...)`가 아니라 **자기 자신(`get_visible_analysis(...)`)**을 부르고 있었습니다. 함수가 끝없이 자기를 부르다 파이썬의 한계(약 1000번)에 걸렸습니다. 결과 화면 쪽 테스트 3개는 접근 검사가 제대로 적용되지 않은 상태라 남의 분석인데도 200이 나왔습니다.
- **해결:** 첫 줄을 `get_object_or_404(Analysis, pk=analysis_id)`로 바꾸고, 두 뷰의 첫 줄을 `get_visible_analysis(...)`로 바꿨습니다.
- **배운 점:** "기존 코드의 첫 줄을 새 함수 호출로 바꿔라"를 새 함수 **안**에도 적용하면 재귀가 됩니다. 바꿀 위치를 정확히 짚어야 합니다.

### 5-2. 함수는 넣었는데 파일 이름이 안 바뀜
- **증상:** 세 모델 파일에 UUID 함수가 들어갔지만, 필드는 여전히 `upload_to="posts/"`였습니다. 두 파일에서는 새 필드 줄이 함수 안의 `return` 아래에 들어가 있었습니다.
- **원인:** 안내 예시에서 함수와 필드 줄을 붙여 보여 줘서, "기존 필드 줄을 바꾼다"가 아니라 "이 덩어리를 추가한다"로 읽혔습니다. `return` 아래 줄은 에러 없이 무시되니 겉으로는 멀쩡해 보였습니다.
- **해결:** `return` 아래 줄을 지우고, 클래스 안의 기존 필드 줄을 `upload_to=함수이름`으로 바꿨습니다.
- **확인 방법:** `grep -n "upload_to" */models.py`로 실제 필드 줄만 모아 보면 바로 보입니다.

### 5-3. `class User`가 두 개 / 함수가 클래스 아래
- **증상:** `accounts/models.py`에 예전 `class User`와 새 `class User`가 같이 있었고, 고친 뒤에는 함수가 클래스 아래로 가 있었습니다.
- **원인:** 같은 이름의 모델을 두 번 정의하면 Django가 같은 모델을 두 번 등록하려고 합니다. 함수가 아래에 있으면 클래스 본문이 실행될 때 함수가 아직 없어서 `NameError: name 'profile_image_path' is not defined`가 납니다.
- **해결:** 예전 클래스를 지우고 함수를 클래스 위로 옮겼습니다. 결과 순서: import → 함수 → 클래스.

### 5-4. `makemigrations`가 `KeyError: 'DJANGO_SECRET_KEY'`
- **원인:** `--env-file .env` 없이 실행했습니다. `settings.py`가 `os.environ["DJANGO_SECRET_KEY"]`로 읽어서, 없으면 바로 멈춥니다(일부러 그렇게 만든 것).
- **해결:** `uv run --env-file .env python manage.py makemigrations`

### 5-5. cv_service 테스트 개수가 31개로 세어짐
- **증상:** `grep -c "def test_"`로 세면 31개인데, 발표 자료와 이전 문서에는 30개로 적혀 있었습니다.
- **원인:** `cv_service/tests/test_callback.py` 맨 아래에 `test_does_not_follow_redirects`와 `if __name__ == "__main__":` 덩어리가 **한 번 더** 붙어 있습니다(48~58번 줄). 이 함수는 `if` 블록 안에 들어가 있어 테스트로 실행되지 않습니다. 실제로 실행되는 테스트는 30개입니다.
- **해결:** 48~58번 줄(중복된 덩어리)을 지우면 됩니다. 테스트 개수는 30개 그대로입니다.
- **배운 점:** 코드에서 글자로 센 숫자보다 **실행 결과에 찍힌 숫자**가 정확합니다.

### 5-6. 관리자 분석 목록의 상태 필터가 사라짐
- **증상:** README에는 "상태 필터(대기중/분석중/완료/실패)"가 있다고 적혀 있는데, `analysis/admin.py`에 `list_filter`가 없습니다.
- **원인:** C-1 커밋(`776a50d`)에서 `user`를 추가하면서 `list_filter = ["status", "created_at"]` 줄이 지워지고, 그 자리에 `readonly_fields` 줄이 하나 더 생겼습니다.
- **해결:** `analysis/admin.py` 39번 줄(위쪽 `readonly_fields`)을 `list_filter = ["status", "created_at"]`로 바꾸면 됩니다.

### 남은 과제 (이번 브랜치에서는 하지 않음)
- **요청 횟수 제한:** 한 사람이 분석을 무한히 요청하면 Gemini 비용이 계속 나갑니다. `Analysis.user`가 생겼으니 이제 셀 수 있습니다.
- **로그인 시도 제한:** 비밀번호를 무한히 대입해 볼 수 있습니다.
- **사진 파일 자체의 접근 제한:** `/media/` 주소를 아는 사람은 로그인 없이 사진을 열 수 있습니다 (2-5 한계).
- **주인이 비어 있는 옛날 독립 업로드:** 관리자 화면에서만 보입니다. 필요하면 관리자가 정리합니다.
