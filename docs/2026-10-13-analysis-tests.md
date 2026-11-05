# analysis 앱 테스트 작성 (콜백 · 분석 요청 · 실패 처리, 15개) — 2026-10-13

## 1. 기술문서

### 한 줄 요약
테스트가 하나도 없던 `analysis` 앱에 테스트 15개를 작성했다. Redis, Celery, cv_service를 켜지 않아도 실행되며, 직전 브랜치에서 손으로 확인했던 실패 처리 규칙들을 자동으로 확인한다.

### 왜 지금 썼나
- 직전에 만든 실패 처리는 "완료된 분석은 실패로 덮어쓰지 않는다", "6분이 지나면 실패로 바뀐다" 같은 규칙이 많다. 손으로 확인하려면 서버를 끄고 기다려야 해서 번거롭다.
- 다음 작업(결과 화면 개선)이 뷰와 템플릿을 크게 고친다. 테스트가 먼저 있으면 고치다가 깨진 것을 바로 알 수 있다.
- posts(16개)와 accounts(13개)에는 테스트가 있는데 핵심 기능인 analysis만 없었다.

### 실행 방법
```bash
uv run python manage.py test analysis
```
`Ran 15 tests ... OK`가 나오면 성공이다. 중간에 `[run_analysis] #1 연결 실패: 서버 꺼짐` 같은 줄이 세 번 찍히는데, 실패 상황을 흉내 낸 테스트에서 우리 코드가 남긴 로그라서 정상이다.

### 테스트 목록

| 클래스 | 테스트 | 확인하는 것 |
|---|---|---|
| `AnalysisCallbackTests` | `test_valid_token_saves_results_and_completes` | 토큰이 맞으면 아이템·스타일·해석문이 저장되고 "완료"가 됨 |
| | `test_invalid_token_is_rejected` | 토큰이 틀리면 403으로 거부되고 아무것도 저장되지 않음 |
| | `test_get_request_is_not_allowed` | GET으로 접근하면 405로 거부됨 |
| `RequestAnalysisTests` | `test_logged_in_user_can_request_on_others_post` | 로그인한 유저는 남의 게시물도 분석 요청 가능, Celery에 일이 넘어감 |
| | `test_anonymous_user_cannot_request` | 로그인하지 않으면 요청 불가, 분석도 Celery 작업도 생기지 않음 |
| | `test_upload_creates_analysis_without_post` | 단독 업로드는 게시물 없이 분석이 만들어짐 |
| `AnalysisStatusTests` | `test_recent_pending_stays_pending` | 방금 요청한 분석은 "대기중" 그대로 |
| | `test_stale_pending_becomes_failed` | 6분이 넘은 미완료 분석은 "실패"로 바뀌고 안내 문구가 채워짐 |
| | `test_stale_completed_stays_completed` | 오래됐어도 완료된 분석은 그대로 |
| `MarkFailedTests` | `test_marks_pending_as_failed` | 실패 상태와 문구가 저장됨 |
| | `test_does_not_overwrite_completed` | 완료된 분석은 건드리지 않음 |
| `RunAnalysisTests` | `test_success_sends_request_and_sets_processing` | cv_service에 토큰·콜백 주소·제한 시간을 실어 요청하고 "분석중"이 됨 |
| | `test_connection_error_marks_failed` | 연결 실패 시 "연결할 수 없습니다" 문구로 실패 |
| | `test_timeout_marks_failed` | 시간 초과 시 "시간이 초과" 문구로 실패 |
| | `test_error_response_marks_failed` | 에러 응답 시 "오류가 발생" 문구로 실패 |

### 테스트가 외부에 의존하지 않게 한 두 가지 장치

| 장치 | 무엇을 막나 |
|---|---|
| 가짜로 바꿔치기 (`unittest.mock.patch`) | 테스트가 진짜 Celery(Redis)와 cv_service에 접속하는 것 |
| 임시 폴더 (`override_settings(MEDIA_ROOT=...)`) | 테스트용 사진이 진짜 `media/` 폴더에 쌓이는 것 |

### 변경 파일

| 파일 | 내용 |
|---|---|
| `analysis/tests.py` | 테스트 15개 작성 (기존에는 빈 파일) |
| `README.md` | 테스트 실행 명령과 analysis 테스트 설명 추가 |

---

## 2. 클래스·함수 단위 코드리뷰

### `TEMP_MEDIA_ROOT`와 `@override_settings` — 사진을 임시 폴더로
테스트에서 게시물을 만들면 사진 파일이 실제로 디스크에 저장된다. 그대로 두면 테스트를 돌릴 때마다 `media/posts/`에 가짜 사진이 쌓인다. `tempfile.mkdtemp()`로 임시 폴더를 만들고, `@override_settings(MEDIA_ROOT=...)`로 테스트 동안만 저장 위치를 그쪽으로 돌렸다. 이 장식은 `AnalysisTestCase`에 한 번만 붙였고, 상속받는 다섯 클래스에 모두 적용된다.

posts 테스트는 `image="posts/test.jpg"`처럼 경로 글자만 넣어서 파일을 만들지 않는다. analysis에서는 그렇게 할 수 없다. `run_analysis`가 사진 파일을 **실제로 열어서** cv_service에 보내기 때문에 진짜 파일이 있어야 한다.

### `tearDownClass` — 뒷정리
클래스의 테스트가 전부 끝난 뒤 임시 폴더를 지운다. 클래스가 다섯 개라 다섯 번 지워지는데, 폴더가 없으면 다음 클래스에서 사진을 저장할 때 다시 만들어지므로 문제가 없다. `ignore_errors=True`는 이미 지워진 폴더를 또 지우려 할 때 에러가 나지 않게 한다.

### `AnalysisTestCase.setUp` — 공통 준비물
유저 두 명(주인과 남), 게시물 하나, "대기중" 분석 하나를 테스트마다 새로 만든다. Django 테스트는 테스트 하나가 끝나면 DB를 원래대로 되돌리기 때문에 테스트끼리 서로 영향을 주지 않는다.

### `TestCase`와 `force_login` — posts 테스트와 다른 점
posts는 DRF로 만든 API라서 `APITestCase`와 `force_authenticate`를 썼다. analysis의 뷰는 일반 Django 뷰(`@login_required`, 세션 로그인)라서 Django 기본 `TestCase`와 `force_login`을 쓴다.

이 차이가 응답에도 나타난다. posts API는 로그인하지 않은 요청에 403을 돌려주지만, analysis의 `@login_required`는 로그인 페이지로 **이동시키므로** 302가 온다.

### `@patch("analysis.views.run_analysis")` — 바꿔치기의 경로
가장 헷갈리기 쉬운 부분이다. `run_analysis`는 `analysis/tasks.py`에 정의돼 있는데 경로는 `analysis.views`로 적었다. 바꿔치기는 "그 이름을 **쓰는 곳**"을 기준으로 해야 하기 때문이다. `views.py`가 `from .tasks import run_analysis`로 가져온 순간 뷰는 자기만의 `run_analysis`라는 이름을 갖게 되고, 뷰가 실제로 부르는 것은 그 이름이다.

클래스에 `@patch`를 붙이면 그 클래스의 모든 테스트 함수에 가짜가 마지막 인자로 들어온다. 그래서 함수마다 `(self, mock_task)`로 받는다.

### `assert_called_once_with` / `assert_not_called` — 가짜에게 묻기
가짜는 아무 일도 하지 않는 대신 "어떤 값으로 몇 번 불렸는지"를 기억한다. 뷰가 Celery에 일을 제대로 넘겼는지를, 실제로 Celery를 돌리지 않고 확인할 수 있다. 로그인하지 않은 요청 테스트에서는 반대로 "한 번도 불리지 않았어야 한다"를 확인한다.

### `fetch_redirect_response=False`
`assertRedirects`는 기본적으로 이동할 페이지까지 실제로 열어 본다. 여기서 확인하려는 것은 "어디로 보내는가"뿐이므로 열어 보지 않게 했다. 결과 페이지의 템플릿이 바뀌어도 이 테스트는 영향을 받지 않는다.

### `make_stale` — 시간을 기다리지 않고 과거로 돌리기
6분을 실제로 기다릴 수 없으니 분석의 생성 시각을 DB에서 과거로 바꾼다. `created_at`은 생성할 때 자동으로 채워지는 칸(`auto_now_add`)이라 만들 때 값을 지정할 수 없어서, 만든 뒤 `filter().update()`로 직접 고쳤다.

기준 시간은 숫자로 적지 않고 `views.py`의 `STALE_AFTER`를 가져다 쓴다. 나중에 6분을 10분으로 바꿔도 테스트는 고칠 필요가 없다.

### `run_analysis(...)`를 직접 호출
`.delay()`를 붙이면 Celery 대기열로 가고, 그냥 부르면 일반 함수처럼 그 자리에서 실행된다. 테스트에서는 직접 불러서 함수 안의 로직만 확인한다.

### `side_effect` — 실패 상황 흉내 내기
- `mock_post.side_effect = ConnectionError(...)`: 가짜 `requests.post`가 불리면 예외를 일으킨다. cv_service를 실제로 끄지 않고 "서버가 꺼진 상황"을 만든다.
- `mock_post.return_value.raise_for_status.side_effect = HTTPError(...)`: 요청은 갔고 응답도 왔는데 에러 응답인 상황. "가짜 `post`가 돌려주는 응답 객체의 `raise_for_status()`가 불리면 예외를 일으켜라"로 읽는다.

예외는 가짜가 아니라 `requests`의 진짜 예외 종류를 썼다. `tasks.py`의 `except`가 예외의 종류를 보고 갈래를 나누기 때문에, 진짜 종류를 써야 올바른 갈래로 들어가는지 확인된다.

### 문구를 `assertIn`으로 확인한 이유
`assertEqual`로 문장 전체를 비교하면 안내 문구의 조사 하나만 고쳐도 테스트가 깨진다. "연결할 수 없습니다"처럼 그 갈래를 구분해 주는 핵심 부분만 들어 있는지 확인했다.

### 이번에 테스트하지 않은 것
- **결과 페이지 화면**(`result`, `standalone_result`): 다음 브랜치에서 템플릿을 크게 고칠 예정이라, 고친 뒤에 쓰는 것이 낫다.
- **cv_service**(FastAPI 쪽): `normalize_scores`, `apply_labels`, `merge_duplicates` 같은 순수 함수는 테스트하기 좋은 대상인데, 별도 프로젝트라 테스트 환경을 따로 갖춰야 한다. 다음 과제로 남긴다.
- **콜백에 잘못된 모양의 데이터가 올 때**: 필수 칸이 빠지면 지금은 500 에러가 난다. 직전 브랜치에서 그 경우 cv_service가 알아채고 실패로 기록되게 했지만, 콜백 자체의 테스트는 없다.

---

## 3. 코드 한 줄 한 줄 주석

### `analysis/tests.py` (전체)
```python
import json  # 콜백 요청 본문을 JSON 글자로 만들 때 씀
import shutil  # 테스트가 끝난 뒤 임시 폴더를 통째로 지울 때 씀
import tempfile  # 임시 폴더를 만들 때 씀
from datetime import timedelta  # "1초" 같은 시간 간격을 표현할 때 씀
from io import BytesIO  # 파일을 디스크에 안 만들고 메모리 안에서 다루기 위함
from unittest.mock import patch  # 테스트 동안만 특정 대상을 "가짜"로 바꿔치기하는 도구

import requests  # 연결 실패/시간 초과 같은 진짜 예외 종류를 가져다 쓰기 위함
from PIL import Image  # 진짜 이미지 데이터를 코드로 직접 만들기 위함
from django.contrib.auth import get_user_model  # 커스텀 User 모델을 안전하게 가져오는 표준 방법
from django.core.files.uploadedfile import SimpleUploadedFile  # "업로드된 파일"인 척하는 객체를 만들어주는 도구
from django.test import TestCase, override_settings  # Django 기본 테스트 도구 + 설정을 잠깐 바꾸는 도구
from django.urls import reverse  # URL 이름("analysis:callback")으로 실제 주소를 만들어주는 함수
from django.utils import timezone  # 현재 시각을 가져올 때 씀

from posts.models import Post  # 분석 대상이 될 게시물
from .models import Analysis  # 테스트할 분석 모델
from .tasks import mark_failed, run_analysis  # 테스트할 실패 기록 함수와 분석 task
from .views import STALE_AFTER  # "이 시간이 지나면 실패"의 기준값 (6분)을 그대로 가져다 씀

User = get_user_model()  # accounts.User 모델을 "User"라는 이름으로 사용

TEMP_MEDIA_ROOT = tempfile.mkdtemp()  # 테스트용 사진을 저장할 임시 폴더 (진짜 media/ 폴더를 더럽히지 않기 위함)


def generate_test_image():  # 테스트에서 쓸 가짜(하지만 진짜 유효한) 이미지 파일을 만드는 함수
    file = BytesIO()  # 메모리 위에 임시 파일 공간을 하나 만듦
    Image.new("RGB", (10, 10)).save(file, "JPEG")  # 10x10 단색 이미지를 만들어 JPEG로 저장
    file.seek(0)  # 파일 "커서"를 처음으로 되돌림 (안 하면 읽을 때 빈 내용만 읽힘)
    return SimpleUploadedFile("test.jpg", file.read(), content_type="image/jpeg")  # 업로드 파일처럼 포장해서 반환


@override_settings(MEDIA_ROOT=TEMP_MEDIA_ROOT)  # 이 클래스(와 상속받는 클래스)의 테스트 동안만 사진 저장 위치를 임시 폴더로 변경
class AnalysisTestCase(TestCase):  # 아래 다섯 테스트 클래스가 상속받는 공통 부모
    def setUp(self):  # 테스트 하나가 실행되기 직전마다 자동으로 호출됨
        self.user = User.objects.create_user(username="user1", password="testpass123")  # 게시물 주인
        self.other_user = User.objects.create_user(username="user2", password="testpass123")  # "남"의 역할을 할 유저
        self.post = Post.objects.create(user=self.user, image=generate_test_image(), caption="테스트 게시물")  # 분석 대상 게시물 (사진이 임시 폴더에 실제로 저장됨)
        self.analysis = Analysis.objects.create(post=self.post, callback_token="test-token")  # 미리 만들어 둔 분석 1건 (상태는 기본값 "대기중")

    @classmethod  # 객체가 아니라 클래스 자체에 붙는 메서드라는 표시
    def tearDownClass(cls):  # 이 클래스의 테스트가 전부 끝난 뒤 딱 한 번 실행됨
        shutil.rmtree(TEMP_MEDIA_ROOT, ignore_errors=True)  # 임시 폴더와 그 안의 사진을 통째로 삭제 (이미 없어도 에러 내지 않음)
        super().tearDownClass()  # Django가 원래 하던 뒷정리도 실행


# 콜백 테스트 코드 (cv_service가 결과를 돌려보내는 주소)
class AnalysisCallbackTests(AnalysisTestCase):
    def setUp(self):
        super().setUp()  # 부모의 setUp(유저/게시물/분석 만들기)을 먼저 실행
        self.url = reverse("analysis:callback", args=[self.analysis.id])  # 이 분석의 콜백 주소
        self.payload = {  # cv_service가 보내는 것과 같은 모양의 결과 데이터
            "callback_token": "test-token",  # setUp에서 만든 분석의 토큰과 같은 값
            "detected_items": [  # 탐지된 아이템 목록 (1개)
                {
                    "category": "하의",  # 큰 분류
                    "label": "와이드 청바지",  # 세부 명칭
                    "bbox_x": 0.2, "bbox_y": 0.4, "bbox_width": 0.5, "bbox_height": 0.5,  # 위치와 크기 (0~1 비율)
                    "search_url": "https://example.com/search",  # 쇼핑 검색 링크
                },
            ],
            "style_scores": [  # 스타일 비율 목록 (2개)
                {"style_name": "캐주얼", "ratio": 60.0},
                {"style_name": "스트릿", "ratio": 40.0},
            ],
            "interpretation": "편안한 핏의 조합입니다.",  # 해석문
        }

    def post_callback(self, payload):  # 콜백 요청을 보내는 동작을 여러 테스트에서 재사용하려고 뽑아냄
        return self.client.post(self.url, data=json.dumps(payload), content_type="application/json")  # dict를 JSON 글자로 바꿔서 전송

    def test_valid_token_saves_results_and_completes(self):
        response = self.post_callback(self.payload)  # 올바른 토큰으로 콜백 전송

        self.assertEqual(response.status_code, 200)  # 정상 처리
        self.analysis.refresh_from_db()  # 뷰가 DB를 바꿨으니 최신 상태를 다시 읽어옴
        self.assertEqual(self.analysis.status, Analysis.STATUS_COMPLETED)  # 상태가 "완료"로 바뀌어야 함
        self.assertEqual(self.analysis.interpretation, "편안한 핏의 조합입니다.")  # 해석문이 저장돼야 함
        self.assertEqual(self.analysis.detected_items.count(), 1)  # 아이템 1개 저장
        self.assertEqual(self.analysis.detected_items.get().label, "와이드 청바지")  # 라벨이 그대로 저장
        self.assertEqual(self.analysis.style_scores.count(), 2)  # 스타일 2개 저장

    def test_invalid_token_is_rejected(self):
        self.payload["callback_token"] = "wrong-token"  # 토큰만 틀리게 바꿈
        response = self.post_callback(self.payload)  # 틀린 토큰으로 콜백 전송

        self.assertEqual(response.status_code, 403)  # 권한 없음으로 거부돼야 함
        self.analysis.refresh_from_db()  # 최신 상태 다시 읽기
        self.assertEqual(self.analysis.status, Analysis.STATUS_PENDING)  # 상태는 "대기중" 그대로
        self.assertEqual(self.analysis.detected_items.count(), 0)  # 아무것도 저장되면 안 됨

    def test_get_request_is_not_allowed(self):
        response = self.client.get(self.url)  # POST가 아니라 GET으로 접근
        self.assertEqual(response.status_code, 405)  # "허용되지 않은 방식"으로 거부돼야 함


# 분석 요청 테스트 코드 (게시물 기반 A 플로우 + 독립 업로드 B 플로우)
@patch("analysis.views.run_analysis")  # 이 클래스의 테스트 동안 views.py의 run_analysis를 가짜로 바꿈 → 각 테스트가 mock_task로 받음
class RequestAnalysisTests(AnalysisTestCase):
    def test_logged_in_user_can_request_on_others_post(self, mock_task):
        self.client.force_login(self.other_user)  # 게시물 주인이 아닌 유저로 로그인
        response = self.client.post(reverse("analysis:request", args=[self.post.id]))  # 남의 게시물에 분석 요청

        new_analysis = Analysis.objects.exclude(pk=self.analysis.pk).get()  # setUp에서 만든 것 말고 새로 생긴 분석 1건
        self.assertEqual(new_analysis.post, self.post)  # 그 게시물에 연결돼 있어야 함
        self.assertTrue(new_analysis.callback_token)  # 콜백 토큰이 채워져 있어야 함
        mock_task.delay.assert_called_once_with(new_analysis.id)  # Celery에 이 분석의 id로 딱 한 번 일을 넘겼어야 함
        self.assertRedirects(
            response,  # 뷰가 돌려준 응답이
            reverse("analysis:result", args=[self.post.id]),  # 결과 페이지로 보내는지 확인
            fetch_redirect_response=False,  # 이동할 페이지까지 실제로 열어보지는 않음
        )

    def test_anonymous_user_cannot_request(self, mock_task):
        response = self.client.post(reverse("analysis:request", args=[self.post.id]))  # 로그인 없이 요청

        self.assertEqual(response.status_code, 302)  # 로그인 페이지로 보내짐
        self.assertEqual(Analysis.objects.count(), 1)  # 새 분석이 만들어지면 안 됨 (setUp의 1건뿐)
        mock_task.delay.assert_not_called()  # Celery에 일을 넘기면 안 됨

    def test_upload_creates_analysis_without_post(self, mock_task):
        self.client.force_login(self.user)  # 로그인
        response = self.client.post(reverse("analysis:upload"), {"image": generate_test_image()})  # 사진만 업로드

        new_analysis = Analysis.objects.exclude(pk=self.analysis.pk).get()  # 새로 생긴 분석 1건
        self.assertIsNone(new_analysis.post)  # 게시물 없이 만들어져야 함
        self.assertTrue(new_analysis.image)  # 업로드한 사진이 저장돼 있어야 함
        mock_task.delay.assert_called_once_with(new_analysis.id)  # Celery에 일을 넘겼어야 함
        self.assertRedirects(
            response,  # 뷰가 돌려준 응답이
            reverse("analysis:standalone_result", args=[new_analysis.id]),  # 단독 결과 페이지로 보내는지 확인
            fetch_redirect_response=False,  # 이동할 페이지는 열어보지 않음
        )


# 상태 조회 테스트 코드 (결과 페이지가 3초마다 부르는 주소)
class AnalysisStatusTests(AnalysisTestCase):
    def setUp(self):
        super().setUp()  # 공통 준비물 먼저
        self.url = reverse("analysis:status", args=[self.analysis.id])  # 이 분석의 상태 조회 주소

    def make_stale(self):  # 이 분석을 "요청한 지 6분이 넘은 것"처럼 만드는 도우미
        old_time = timezone.now() - STALE_AFTER - timedelta(seconds=1)  # 기준 시간보다 1초 더 과거
        Analysis.objects.filter(pk=self.analysis.pk).update(created_at=old_time)  # 생성 시각을 DB에서 직접 과거로 바꿈

    def test_recent_pending_stays_pending(self):
        response = self.client.get(self.url)  # 방금 만든 분석의 상태 조회

        self.assertEqual(response.json()["status"], Analysis.STATUS_PENDING)  # 아직 6분이 안 됐으니 "대기중" 그대로

    def test_stale_pending_becomes_failed(self):
        self.make_stale()  # 오래된 분석으로 만듦
        response = self.client.get(self.url)  # 상태 조회

        self.assertEqual(response.json()["status"], Analysis.STATUS_FAILED)  # 응답이 "실패"로 와야 함
        self.analysis.refresh_from_db()  # 최신 상태 다시 읽기
        self.assertEqual(self.analysis.status, Analysis.STATUS_FAILED)  # DB에도 "실패"로 저장돼야 함
        self.assertTrue(self.analysis.error_message)  # 화면에 보여줄 안내 문구가 채워져 있어야 함

    def test_stale_completed_stays_completed(self):
        Analysis.objects.filter(pk=self.analysis.pk).update(status=Analysis.STATUS_COMPLETED)  # 이미 완료된 분석으로 만듦
        self.make_stale()  # 오래된 분석으로 만듦
        response = self.client.get(self.url)  # 상태 조회

        self.assertEqual(response.json()["status"], Analysis.STATUS_COMPLETED)  # 오래됐어도 완료된 건 그대로여야 함


# mark_failed 테스트 코드 (실패를 기록하는 함수)
class MarkFailedTests(AnalysisTestCase):
    def test_marks_pending_as_failed(self):
        mark_failed(self.analysis.id, "테스트 실패 문구")  # "대기중"인 분석을 실패로 기록

        self.analysis.refresh_from_db()  # 최신 상태 다시 읽기
        self.assertEqual(self.analysis.status, Analysis.STATUS_FAILED)  # "실패"로 바뀌어야 함
        self.assertEqual(self.analysis.error_message, "테스트 실패 문구")  # 넘긴 문구가 그대로 저장돼야 함

    def test_does_not_overwrite_completed(self):
        Analysis.objects.filter(pk=self.analysis.pk).update(status=Analysis.STATUS_COMPLETED)  # 이미 완료된 분석
        mark_failed(self.analysis.id, "테스트 실패 문구")  # 실패로 기록 시도

        self.analysis.refresh_from_db()  # 최신 상태 다시 읽기
        self.assertEqual(self.analysis.status, Analysis.STATUS_COMPLETED)  # "완료"가 유지돼야 함
        self.assertEqual(self.analysis.error_message, "")  # 실패 문구도 들어가면 안 됨


# run_analysis 테스트 코드 (Celery task)
@patch("analysis.tasks.requests.post")  # 테스트 동안 cv_service로 보내는 요청을 가짜로 바꿈 → 진짜 서버 없이 상황을 흉내 냄
class RunAnalysisTests(AnalysisTestCase):
    def test_success_sends_request_and_sets_processing(self, mock_post):
        run_analysis(self.analysis.id)  # .delay() 없이 직접 부르면 Celery를 거치지 않고 바로 실행됨

        mock_post.assert_called_once()  # cv_service에 요청을 딱 한 번 보냈어야 함
        sent = mock_post.call_args.kwargs  # 그 요청에 실어 보낸 값들
        self.assertEqual(sent["data"]["callback_token"], "test-token")  # 이 분석의 토큰을 보냈어야 함
        self.assertIn(f"/analysis/api/{self.analysis.id}/callback/", sent["data"]["callback_url"])  # 이 분석의 콜백 주소를 보냈어야 함
        self.assertIn("timeout", sent)  # 제한 시간을 걸었어야 함

        self.analysis.refresh_from_db()  # 최신 상태 다시 읽기
        self.assertEqual(self.analysis.status, Analysis.STATUS_PROCESSING)  # 콜백이 오기 전이니 "분석중"이어야 함

    def test_connection_error_marks_failed(self, mock_post):
        mock_post.side_effect = requests.exceptions.ConnectionError("서버 꺼짐")  # 가짜가 불리면 "연결 실패" 예외를 일으키게 설정
        run_analysis(self.analysis.id)  # task 실행

        self.analysis.refresh_from_db()  # 최신 상태 다시 읽기
        self.assertEqual(self.analysis.status, Analysis.STATUS_FAILED)  # "실패"로 기록돼야 함
        self.assertIn("연결할 수 없습니다", self.analysis.error_message)  # 연결 실패용 문구여야 함

    def test_timeout_marks_failed(self, mock_post):
        mock_post.side_effect = requests.exceptions.Timeout("응답 없음")  # "시간 초과" 예외를 일으키게 설정
        run_analysis(self.analysis.id)  # task 실행

        self.analysis.refresh_from_db()  # 최신 상태 다시 읽기
        self.assertEqual(self.analysis.status, Analysis.STATUS_FAILED)  # "실패"로 기록돼야 함
        self.assertIn("시간이 초과", self.analysis.error_message)  # 시간 초과용 문구여야 함

    def test_error_response_marks_failed(self, mock_post):
        mock_post.return_value.raise_for_status.side_effect = requests.exceptions.HTTPError("500")  # 응답은 왔지만 에러 응답인 상황
        run_analysis(self.analysis.id)  # task 실행

        self.analysis.refresh_from_db()  # 최신 상태 다시 읽기
        self.assertEqual(self.analysis.status, Analysis.STATUS_FAILED)  # "실패"로 기록돼야 함
        self.assertIn("오류가 발생", self.analysis.error_message)  # 그 밖의 오류용 문구여야 함
```

---

## 4. 복습 (이번에 새로 익힌 개념)

### 가짜로 바꿔치기 (mock)
테스트하려는 코드가 바깥의 무언가(Celery, 다른 서버, 인터넷)를 부를 때, 테스트 동안만 그 부분을 아무 일도 하지 않는 가짜로 바꾸는 기법. 얻는 것이 세 가지다.
- 바깥 서비스가 꺼져 있어도 테스트가 돌아간다.
- "서버가 꺼졌다", "응답이 안 온다" 같은 만들기 어려운 상황을 마음대로 만들 수 있다.
- 가짜가 "어떻게 불렸는지"를 기억하므로, 우리 코드가 바깥을 올바르게 불렀는지 확인할 수 있다.

### 바꿔치기는 "쓰는 곳"을 기준으로
`from .tasks import run_analysis`로 가져오면 가져온 파일에 그 이름이 새로 생긴다. 뷰가 부르는 것은 뷰 파일 안의 이름이므로 `analysis.views.run_analysis`를 바꿔야 한다. 정의된 곳(`analysis.tasks.run_analysis`)을 바꾸면 뷰는 여전히 진짜를 부른다.

반대로 `tasks.py`는 `import requests`로 모듈을 통째로 가져와 `requests.post(...)`라고 부르므로, `analysis.tasks.requests.post`를 바꾸면 된다.

### `return_value`와 `side_effect`
- `return_value`: 가짜가 불렸을 때 돌려줄 값.
- `side_effect`: 가짜가 불렸을 때 일으킬 예외(또는 대신 실행할 동작).

### `setUp`과 `tearDownClass`
- `setUp`: 테스트 하나마다 직전에 실행. 준비물을 매번 새로 만든다.
- `tearDownClass`: 클래스의 테스트가 전부 끝난 뒤 한 번 실행. 뒷정리에 쓴다.

자식 클래스에서 `setUp`을 다시 정의할 때는 `super().setUp()`을 먼저 불러야 부모의 준비물이 만들어진다.

### `override_settings`
테스트 동안만 Django 설정값을 바꿔 준다. 테스트가 끝나면 원래 값으로 돌아온다.

### `refresh_from_db()`가 테스트에서 자주 나오는 이유
`self.analysis`는 `setUp`에서 만든 시점의 내용을 들고 있다. 뷰나 함수가 DB를 바꿔도 손에 든 객체는 그대로이므로, 결과를 확인하기 전에 다시 읽어 와야 한다.

### 상태 코드 정리
- 200: 정상
- 302: 다른 페이지로 이동시킴 (로그인 필요한 페이지에 비로그인으로 접근했을 때 등)
- 403: 권한 없음
- 405: 허용되지 않은 요청 방식 (POST만 받는 주소에 GET으로 접근 등)

### 테스트가 주는 것
"지금 잘 동작한다"를 확인하는 것보다, **나중에 코드를 고쳤을 때 깨진 것을 바로 알려 주는 것**이 더 큰 가치다. 20초로 줄였다가 6분으로 되돌리며 손으로 확인했던 일을, 이제는 명령 한 줄이 1초 안에 대신 한다.

---

## 5. 트러블슈팅

이번 브랜치에서는 실제 디버깅이 필요했던 문제가 없었다. 테스트 6개와 15개가 각각 첫 실행에 통과했다.

### 결과 검증
- 1차(콜백 + 분석 요청): `Ran 6 tests ... OK`
- 2차(상태 조회 + `mark_failed` + `run_analysis` 추가): `Ran 15 tests ... OK`
- Redis, Celery, cv_service를 켜지 않은 상태에서 실행됨.
