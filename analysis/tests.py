import json  # 콜백 요청 본문을 JSON 글자로 만들 때 씀
import shutil  # 테스트가 끝난 뒤 임시 폴더를 통째로 지울 때 씀
import tempfile  # 임시 폴더를 만들 때 씀
from datetime import timedelta  # "1초" 같은 시간 간격을 표현할 때 씀
from io import BytesIO  # 파일을 디스크에 안 만들고 메모리 안에서 다루기 위함
from unittest.mock import patch  # 테스트 동안만 특정 대상을 "가짜"로 바꿔치기하는 도구
from django.contrib.messages import get_messages
import requests  # 연결 실패/시간 초과 같은 진짜 예외 종류를 가져다 쓰기 위함
from PIL import Image  # 진짜 이미지 데이터를 코드로 직접 만들기 위함
from django.contrib.auth import get_user_model  # 커스텀 User 모델을 안전하게 가져오는 표준 방법
from django.core.files.uploadedfile import SimpleUploadedFile  # "업로드된 파일"인 척하는 객체를 만들어주는 도구
from django.test import TestCase, override_settings  # Django 기본 테스트 도구 + 설정을 잠깐 바꾸는 도구
from django.urls import reverse  # URL 이름("analysis:callback")으로 실제 주소를 만들어주는 함수
from django.utils import timezone  # 현재 시각을 가져올 때 씀
from django.conf import settings
from posts.models import Post  # 분석 대상이 될 게시물
from .models import Analysis  # 테스트할 분석 모델
from .tasks import mark_failed, run_analysis  # 테스트할 실패 기록 함수와 분석 task
from .views import STALE_AFTER, RATE_LIMIT_COUNT # 기준값(10건, 6분)을 테스트에 숫자로 다시 적지 않고 그대로 가져다 씀

User = get_user_model()  # accounts.User 모델을 "User"라는 이름으로 사용

TEMP_MEDIA_ROOT = tempfile.mkdtemp()  # 테스트용 사진을 저장할 임시 폴더 (진짜 media/ 폴더를 더럽히지 않기 위함)


def generate_test_image():  # 테스트에서 쓸 가짜(하지만 진짜 유효한) 이미지 파일을 만드는 함수
    file = BytesIO()  # 메모리 위에 임시 파일 공간을 하나 만듦
    Image.new("RGB", (10, 10)).save(file, "JPEG")  # 10x10 단색 이미지를 만들어 JPEG로 저장
    file.seek(0)  # 파일 "커서"를 처음으로 되돌림 (안 하면 읽을 때 빈 내용만 읽힘)
    return SimpleUploadedFile("test.jpg", file.read(), content_type="image/jpeg")  # 업로드 파일처럼 포장해서 반환


@override_settings(MEDIA_ROOT=TEMP_MEDIA_ROOT)  # 이 클래스(와 상속받는 클래스)의 테스트 동안만 사진 저장 위치를 임시 폴더로 변경
class AnalysisTestCase(TestCase):
    # 이 클래스를 상속받는 모든 테스트 클래스에서 공통으로 쓸 준비물을 만듦
    def setUp(self):
        self.user = User.objects.create_user(username="user1", password="testpass123")  # 게시물 주인
        self.other_user = User.objects.create_user(username="user2", password="testpass123")  # "남"의 역할을 할 유저
        self.post = Post.objects.create(user=self.user, image=generate_test_image(), caption="테스트 게시물")  # 분석 대상 게시물
        self.analysis = Analysis.objects.create(post=self.post, callback_token="test-token")  # 미리 만들어 둔 분석 1건 (상태는 기본값 "대기중")

    @classmethod
    def tearDownClass(cls):  # 이 클래스의 테스트가 전부 끝난 뒤 딱 한 번 실행됨
        shutil.rmtree(TEMP_MEDIA_ROOT, ignore_errors=True)  # 임시 폴더와 그 안의 사진을 통째로 삭제
        super().tearDownClass()  # Django가 원래 하던 뒷정리도 실행


# 콜백 테스트 코드 (cv_service가 결과를 돌려보내는 주소)
class AnalysisCallbackTests(AnalysisTestCase):
    def setUp(self):
        super().setUp()  # 부모의 setUp(유저/게시물/분석 만들기)을 먼저 실행
        self.url = reverse("analysis:callback", args=[self.analysis.id])  # 이 분석의 콜백 주소
        self.payload = {  # cv_service가 보내는 것과 같은 모양의 결과 데이터
            "callback_token": "test-token",
            "detected_items": [
                {
                    "category": "하의",
                    "label": "와이드 청바지",
                    "bbox_x": 0.2, "bbox_y": 0.4, "bbox_width": 0.5, "bbox_height": 0.5,
                    "search_url": "https://example.com/search",
                },
            ],
            "style_scores": [
                {"style_name": "캐주얼", "ratio": 60.0},
                {"style_name": "스트릿", "ratio": 40.0},
            ],
            "interpretation": "편안한 핏의 조합입니다.",
        }

    def post_callback(self, payload):  # 콜백 요청을 보내는 동작을 여러 테스트에서 재사용하려고 뽑아냄
        return self.client.post(self.url, data=json.dumps(payload), content_type="application/json")  # dict를 JSON 글자로 바꿔서 전송

    def test_valid_token_saves_results_and_completes(self):
        response = self.post_callback(self.payload)

        self.assertEqual(response.status_code, 200)  # 정상 처리
        self.analysis.refresh_from_db()  # 뷰가 DB를 바꿨으니 최신 상태를 다시 읽어옴
        self.assertEqual(self.analysis.status, Analysis.STATUS_COMPLETED)  # 상태가 "완료"로 바뀌어야 함
        self.assertEqual(self.analysis.interpretation, "편안한 핏의 조합입니다.")  # 해석문이 저장돼야 함
        self.assertEqual(self.analysis.detected_items.count(), 1)  # 아이템 1개 저장
        self.assertEqual(self.analysis.detected_items.get().label, "와이드 청바지")  # 라벨이 그대로 저장
        self.assertEqual(self.analysis.style_scores.count(), 2)  # 스타일 2개 저장

    def test_invalid_token_is_rejected(self):
        self.payload["callback_token"] = "wrong-token"  # 토큰만 틀리게 바꿈
        response = self.post_callback(self.payload)

        self.assertEqual(response.status_code, 403)  # 권한 없음으로 거부돼야 함
        self.analysis.refresh_from_db()
        self.assertEqual(self.analysis.status, Analysis.STATUS_PENDING)  # 상태는 "대기중" 그대로
        self.assertEqual(self.analysis.detected_items.count(), 0)  # 아무것도 저장되면 안 됨

    def test_get_request_is_not_allowed(self):
        response = self.client.get(self.url)  # POST가 아니라 GET으로 접근
        self.assertEqual(response.status_code, 405)  # "허용되지 않은 방식"으로 거부돼야 함

    def test_save_failure_rolls_back_everything_and_marks_failed(self):
        self.payload["style_scores"] = [  # 같은 스타일 이름을 두 번 보냄: DB의 중복 금지 규칙(unique_together)에 걸려 두 번째 저장에서 에러가 남
            {"style_name": "캐주얼", "ratio": 60.0},
            {"style_name": "캐주얼", "ratio": 40.0},
        ]

        with self.assertLogs("analysis.views", level="ERROR"):  # 실패 로그를 화면에 안 찍고 붙잡아 둠
            response = self.post_callback(self.payload)  # 콜백 요청 보내기

        self.assertEqual(response.status_code, 500)  # 보낸 쪽에 실패를 알려야 함
        self.analysis.refresh_from_db()  # 뷰가 DB를 바꿨으니 최신 상태를 다시 읽어옴
        self.assertEqual(self.analysis.detected_items.count(), 0)  # 아이템은 먼저 저장됐었지만 되돌려져서 0개여야 함
        self.assertEqual(self.analysis.style_scores.count(), 0)  # 첫 번째 스타일도 되돌려져서 0개여야 함
        self.assertEqual(self.analysis.status, Analysis.STATUS_FAILED)  # 분석은 "실패"로 표시돼야 함
        self.assertIn("저장하지 못했습니다", self.analysis.error_message)  # 안내 문구가 저장돼야 함

    def test_completed_analysis_rejects_duplicate_callback(self):
        self.analysis.status = Analysis.STATUS_COMPLETED  # 이미 결과가 저장된 상태로 만듦
        self.analysis.save()
        self.payload["style_scores"] = []  # DB 중복 금지 규칙에 우연히 걸리지 않게 비움 → 우리 409 검사만으로 막히는지 확인

        response = self.post_callback(self.payload)

        self.assertEqual(response.status_code, 409)  # 충돌로 거절돼야 함
        self.assertEqual(self.analysis.detected_items.count(), 0)  # 아이템이 추가로 저장되면 안 됨

    def test_wrong_token_on_completed_gets_403_not_409(self):
        self.analysis.status = Analysis.STATUS_COMPLETED
        self.analysis.save()
        self.payload["callback_token"] = "wrong-token"

        response = self.post_callback(self.payload)

        self.assertEqual(response.status_code, 403)  # 토큰 검사가 먼저: 토큰이 없는 사람에게 "완료됐는지"를 알려 주지 않음

    def test_late_callback_on_failed_analysis_is_accepted(self):
        mark_failed(self.analysis.id, "분석 시간이 초과되었습니다.")  # 6분이 지나 실패 처리된 상황

        response = self.post_callback(self.payload)  # 그 뒤에 결과가 늦게 도착

        self.assertEqual(response.status_code, 200)  # 받아들여야 함
        self.analysis.refresh_from_db()
        self.assertEqual(self.analysis.status, Analysis.STATUS_COMPLETED)  # 완료로 살아나야 함
        self.assertEqual(self.analysis.error_message, "")  # 실패 문구는 지워져야 함
        self.assertEqual(self.analysis.detected_items.count(), 1)  # 결과도 저장돼야 함


# 분석 요청 테스트 코드 (게시물 기반 A 플로우 + 독립 업로드 B 플로우)
@patch("analysis.views.run_analysis")  # 이 클래스의 테스트 동안 views.py의 run_analysis를 가짜로 바꿈 → 각 테스트가 mock_task로 받음
class RequestAnalysisTests(AnalysisTestCase):
    def test_logged_in_user_can_request_on_others_post(self, mock_task):
        Analysis.objects.filter(pk=self.analysis.pk).update(status=Analysis.STATUS_COMPLETED)  # setUp의 분석을 "완료"로 (진행 중이면 새 요청이 막히므로)        
        self.client.force_login(self.other_user)  # 게시물 주인이 아닌 유저로 로그인
        response = self.client.post(reverse("analysis:request", args=[self.post.id]))

        new_analysis = Analysis.objects.exclude(pk=self.analysis.pk).get()  # setUp에서 만든 것 말고 새로 생긴 분석 1건
        self.assertEqual(new_analysis.post, self.post)  # 그 게시물에 연결돼 있어야 함
        self.assertEqual(new_analysis.user, self.other_user)  # 게시물 주인이 아니라 "요청한 사람"이 분석의 주인이어야 함        
        self.assertTrue(new_analysis.callback_token)  # 콜백 토큰이 채워져 있어야 함
        mock_task.delay.assert_called_once_with(new_analysis.id)  # Celery에 이 분석의 id로 딱 한 번 일을 넘겼어야 함
        self.assertRedirects(
            response,
            reverse("analysis:result", args=[self.post.id]),  # 결과 페이지로 보내야 함
            fetch_redirect_response=False,  # 이동할 페이지까지 실제로 열어보지는 않음
        )

    def test_anonymous_user_cannot_request(self, mock_task):
        response = self.client.post(reverse("analysis:request", args=[self.post.id]))  # 로그인 없이 요청

        self.assertEqual(response.status_code, 302)  # 로그인 페이지로 보내짐
        self.assertEqual(Analysis.objects.count(), 1)  # 새 분석이 만들어지면 안 됨 (setUp의 1건뿐)
        mock_task.delay.assert_not_called()  # Celery에 일을 넘기면 안 됨

    def test_upload_creates_analysis_without_post(self, mock_task):
        self.client.force_login(self.user)
        response = self.client.post(reverse("analysis:upload"), {"image": generate_test_image()})  # 사진만 업로드

        new_analysis = Analysis.objects.exclude(pk=self.analysis.pk).get()
        self.assertIsNone(new_analysis.post)  # 게시물 없이 만들어져야 함
        self.assertEqual(new_analysis.user, self.user)  # 업로드한 사람이 분석의 주인이어야 함        
        self.assertTrue(new_analysis.image)  # 업로드한 사진이 저장돼 있어야 함
        self.assertRegex(new_analysis.image.name, r"^analysis_uploads/[0-9a-f]{32}\.jpg$")  # 원래 이름(test.jpg)이 아니라 무작위 32자로 저장돼야 함
        mock_task.delay.assert_called_once_with(new_analysis.id)
        self.assertRedirects(
            response,
            reverse("analysis:standalone_result", args=[new_analysis.id]),  # 단독 결과 페이지로 보내야 함
            fetch_redirect_response=False,
        )

    def test_upload_without_file_is_rejected(self, mock_task):
        self.client.force_login(self.user)
        response = self.client.post(reverse("analysis:upload"))  # 파일 없이 제출

        self.assertRedirects(response, reverse("analysis:home"), fetch_redirect_response=False)  # 500이 아니라 업로드 화면으로
        self.assertEqual(Analysis.objects.count(), 1)  # setUp의 1건 말고 새로 만들어지면 안 됨
        mock_task.delay.assert_not_called()  # 분석 요청도 가면 안 됨

    def test_upload_non_image_is_rejected(self, mock_task):
        self.client.force_login(self.user)
        fake = SimpleUploadedFile("photo.jpg", b"not an image", content_type="image/jpeg")  # 이름과 형식만 사진인 가짜 파일
        response = self.client.post(reverse("analysis:upload"), {"image": fake})

        self.assertRedirects(response, reverse("analysis:home"), fetch_redirect_response=False)
        self.assertEqual(Analysis.objects.count(), 1)
        mock_task.delay.assert_not_called()
        self.assertTrue(list(get_messages(response.wsgi_request)))  # 실패 안내가 남아 있어야 함

    @patch("config.validators.MAX_UPLOAD_SIZE", 10)  # 진짜 10MB 파일을 만들긴 무거우니, 테스트 동안만 한도를 10바이트로 낮춤
    def test_upload_too_large_is_rejected(self, mock_task):
        self.client.force_login(self.user)
        response = self.client.post(reverse("analysis:upload"), {"image": generate_test_image()})  # 진짜 이미지지만 10바이트보다 큼

        self.assertEqual(Analysis.objects.count(), 1)
        mock_task.delay.assert_not_called()
        self.assertIn("10MB", str(list(get_messages(response.wsgi_request))[0]))  # 크기 안내 문구여야 함
    def fill_rate_limit(self):
        """self.user가 최근에 분석을 한도만큼 요청한 상태로 만듦 (게시물 없는 분석이라 진행 중 검사와는 무관)"""
        for number in range(RATE_LIMIT_COUNT):
            Analysis.objects.create(user=self.user, callback_token=f"limit-{number}")

    def test_request_while_in_progress_does_not_create_new(self, mock_task):
        self.client.force_login(self.other_user)
        response = self.client.post(reverse("analysis:request", args=[self.post.id]))  # setUp의 분석이 아직 "대기중"

        self.assertEqual(Analysis.objects.count(), 1)  # 새 분석이 생기면 안 됨
        mock_task.delay.assert_not_called()
        self.assertRedirects(response, reverse("analysis:result", args=[self.post.id]), fetch_redirect_response=False)  # 진행 중 화면으로

    def test_request_over_limit_is_rejected(self, mock_task):
        Analysis.objects.filter(pk=self.analysis.pk).update(status=Analysis.STATUS_COMPLETED)  # 진행 중 검사에 걸리지 않게
        self.fill_rate_limit()
        self.client.force_login(self.user)
        response = self.client.post(reverse("analysis:request", args=[self.post.id]))

        self.assertEqual(Analysis.objects.count(), 1 + RATE_LIMIT_COUNT)  # setUp 1건 + 채운 10건, 더 늘면 안 됨
        mock_task.delay.assert_not_called()
        self.assertRedirects(response, reverse("posts:detail", args=[self.post.id]), fetch_redirect_response=False)
        self.assertIn("너무 많습니다", str(list(get_messages(response.wsgi_request))[0]))

    def test_old_requests_do_not_count(self, mock_task):
        Analysis.objects.filter(pk=self.analysis.pk).update(status=Analysis.STATUS_COMPLETED)
        self.fill_rate_limit()
        Analysis.objects.filter(callback_token__startswith="limit-").update(
            created_at=timezone.now() - timedelta(hours=2)  # 채운 10건을 2시간 전 요청으로 바꿈 (auto_now_add라 create로는 못 바꿔서 update 사용)
        )
        self.client.force_login(self.user)
        self.client.post(reverse("analysis:request", args=[self.post.id]))

        self.assertEqual(Analysis.objects.count(), 2 + RATE_LIMIT_COUNT)  # 1시간이 지난 요청은 안 세므로 새 분석이 생겨야 함
        mock_task.delay.assert_called_once()

    def test_upload_over_limit_is_rejected(self, mock_task):
        self.fill_rate_limit()
        self.client.force_login(self.user)
        response = self.client.post(reverse("analysis:upload"), {"image": generate_test_image()})  # 정상 사진이지만

        self.assertEqual(Analysis.objects.count(), 1 + RATE_LIMIT_COUNT)  # 횟수 초과라 새 분석이 생기면 안 됨
        mock_task.delay.assert_not_called()
        self.assertRedirects(response, reverse("analysis:home"), fetch_redirect_response=False)

# 독립 업로드 분석 접근 제한 테스트 코드 (결과 화면 + 상태 조회)
class StandaloneAccessTests(AnalysisTestCase):
    def setUp(self):
        super().setUp()
        self.standalone = Analysis.objects.create(  # user1이 게시물 없이 올린 분석
            user=self.user, image=generate_test_image(), callback_token="standalone-token",
        )
        self.result_url = reverse("analysis:standalone_result", args=[self.standalone.id])
        self.status_url = reverse("analysis:status", args=[self.standalone.id])

    def test_owner_can_see_result_and_status(self):
        self.client.force_login(self.user)  # 올린 본인으로 로그인

        self.assertEqual(self.client.get(self.result_url).status_code, 200)  # 결과 화면이 보여야 함
        self.assertEqual(self.client.get(self.status_url).status_code, 200)  # 상태 조회도 돼야 함

    def test_other_user_gets_404(self):
        self.client.force_login(self.other_user)  # 남으로 로그인

        self.assertEqual(self.client.get(self.result_url).status_code, 404)  # "없는 것"처럼 보여야 함 (403 아님)
        self.assertEqual(self.client.get(self.status_url).status_code, 404)

    def test_anonymous_gets_404(self):
        self.assertEqual(self.client.get(self.result_url).status_code, 404)  # 로그인 안 하면 볼 수 없음
        self.assertEqual(self.client.get(self.status_url).status_code, 404)

    def test_ownerless_old_upload_is_hidden_from_anonymous(self):
        Analysis.objects.filter(pk=self.standalone.pk).update(user=None)  # user 칸을 만들기 전에 생긴 옛날 분석처럼 만듦

        self.assertEqual(self.client.get(self.result_url).status_code, 404)  # None == None 함정에 빠지지 않아야 함

    def test_post_based_status_is_still_public(self):
        url = reverse("analysis:status", args=[self.analysis.id])  # setUp의 게시물 기반 분석

        self.assertEqual(self.client.get(url).status_code, 200)  # 게시물 기반은 로그인 없이도 지금처럼 조회돼야 함


# 상태 조회 테스트 코드 (결과 페이지가 3초마다 부르는 주소)
class AnalysisStatusTests(AnalysisTestCase):
    def setUp(self):
        super().setUp()
        self.url = reverse("analysis:status", args=[self.analysis.id])  # 이 분석의 상태 조회 주소

    def make_stale(self):  # 이 분석을 "요청한 지 6분이 넘은 것"처럼 만드는 도우미
        old_time = timezone.now() - STALE_AFTER - timedelta(seconds=1)  # 기준 시간보다 1초 더 과거
        Analysis.objects.filter(pk=self.analysis.pk).update(created_at=old_time)  # 생성 시각을 DB에서 직접 과거로 바꿈

    def test_recent_pending_stays_pending(self):
        response = self.client.get(self.url)  # 방금 만든 분석의 상태 조회

        self.assertEqual(response.json()["status"], Analysis.STATUS_PENDING)  # 아직 6분이 안 됐으니 "대기중" 그대로

    def test_stale_pending_becomes_failed(self):
        self.make_stale()
        response = self.client.get(self.url)

        self.assertEqual(response.json()["status"], Analysis.STATUS_FAILED)  # 응답이 "실패"로 와야 함
        self.analysis.refresh_from_db()
        self.assertEqual(self.analysis.status, Analysis.STATUS_FAILED)  # DB에도 "실패"로 저장돼야 함
        self.assertTrue(self.analysis.error_message)  # 화면에 보여줄 안내 문구가 채워져 있어야 함

    def test_stale_completed_stays_completed(self):
        Analysis.objects.filter(pk=self.analysis.pk).update(status=Analysis.STATUS_COMPLETED)  # 이미 완료된 분석으로 만듦
        self.make_stale()
        response = self.client.get(self.url)

        self.assertEqual(response.json()["status"], Analysis.STATUS_COMPLETED)  # 오래됐어도 완료된 건 그대로여야 함


# mark_failed 테스트 코드 (실패를 기록하는 함수)
class MarkFailedTests(AnalysisTestCase):
    def test_marks_pending_as_failed(self):
        mark_failed(self.analysis.id, "테스트 실패 문구")

        self.analysis.refresh_from_db()
        self.assertEqual(self.analysis.status, Analysis.STATUS_FAILED)  # "실패"로 바뀌어야 함
        self.assertEqual(self.analysis.error_message, "테스트 실패 문구")  # 넘긴 문구가 그대로 저장돼야 함

    def test_does_not_overwrite_completed(self):
        Analysis.objects.filter(pk=self.analysis.pk).update(status=Analysis.STATUS_COMPLETED)  # 이미 완료된 분석
        mark_failed(self.analysis.id, "테스트 실패 문구")

        self.analysis.refresh_from_db()
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
        self.assertEqual(sent["headers"]["X-Internal-Token"], settings.INTERNAL_API_TOKEN)  # 내부 출입증을 실어 보냈어야 함
        self.analysis.refresh_from_db()
        self.assertEqual(self.analysis.status, Analysis.STATUS_PROCESSING)  # 콜백이 오기 전이니 "분석중"이어야 함

    def test_connection_error_marks_failed(self, mock_post):
        mock_post.side_effect = requests.exceptions.ConnectionError("서버 꺼짐")  # 가짜가 불리면 "연결 실패" 예외를 일으키게 설정
        with self.assertLogs("analysis.tasks", level="ERROR") as logs:  # 이 블록 안에서 남은 에러 로그를 화면에 안 찍고 붙잡아 둠 (하나도 안 남으면 테스트 실패)
            run_analysis(self.analysis.id)  # 테스트할 task 실행

        self.analysis.refresh_from_db()  # task가 DB를 바꿨으니 최신 상태를 다시 읽어옴
        self.assertEqual(self.analysis.status, Analysis.STATUS_FAILED)  # 분석이 "실패"로 바뀌었는지
        self.assertIn("연결할 수 없습니다", self.analysis.error_message)  # 연결 실패용 문구여야 함
        self.assertIn("연결 실패", logs.output[0])  # 붙잡은 첫 로그에 "연결 실패"가 있는지 (로그가 실제로 남았는지 확인)

    def test_timeout_marks_failed(self, mock_post):
        mock_post.side_effect = requests.exceptions.Timeout("응답 없음")  # "시간 초과" 예외를 일으키게 설정
        with self.assertLogs("analysis.tasks", level="ERROR") as logs:  # 에러 로그를 붙잡아 둠
            run_analysis(self.analysis.id)

        self.analysis.refresh_from_db()
        self.assertEqual(self.analysis.status, Analysis.STATUS_FAILED)
        self.assertIn("시간이 초과", self.analysis.error_message)  # 시간 초과용 문구여야 함
        self.assertIn("시간 초과", logs.output[0])  # 로그에도 "시간 초과"가 남았는지

    def test_error_response_marks_failed(self, mock_post):
        mock_post.return_value.raise_for_status.side_effect = requests.exceptions.HTTPError("500")  # 응답은 왔지만 에러 응답인 상황
        with self.assertLogs("analysis.tasks", level="ERROR") as logs:  # 에러 로그를 붙잡아 둠 (traceback이 화면에 쏟아지는 것도 막아 줌)
            run_analysis(self.analysis.id)

        self.analysis.refresh_from_db()
        self.assertEqual(self.analysis.status, Analysis.STATUS_FAILED)
        self.assertIn("오류가 발생", self.analysis.error_message)  # 그 밖의 오류용 문구여야 함
        self.assertIn("오류", logs.output[0])  # 로그에도 "오류"가 남았는지

# 결과 페이지 테스트 코드 (게시물 기반)
class ResultViewTests(AnalysisTestCase):
    def setUp(self):
        super().setUp()
        self.url = reverse("analysis:result", args=[self.post.id])  # 이 게시물의 결과 페이지 주소

    def complete(self, analysis):  # 분석을 "완료" 상태로 만드는 도우미
        Analysis.objects.filter(pk=analysis.pk).update(status=Analysis.STATUS_COMPLETED)

    def add_failed_retry(self):  # 나중에 요청한 재분석이 실패한 상황을 만드는 도우미
        return Analysis.objects.create(
            post=self.post, callback_token="retry-token",
            status=Analysis.STATUS_FAILED, error_message="재분석 실패 문구",
        )

    def test_completed_result_shows_photo_and_title(self):
        self.complete(self.analysis)
        response = self.client.get(self.url)

        self.assertContains(response, self.post.image.url)  # 게시물 사진이 화면에 있어야 함
        self.assertContains(response, "AI 스타일 분석 결과")  # 결과 제목이 나와야 함

    def test_failed_retry_falls_back_to_previous_completed(self):
        self.complete(self.analysis)
        self.add_failed_retry()
        response = self.client.get(self.url)

        self.assertContains(response, "AI 스타일 분석 결과")  # 이전에 성공한 결과를 보여줘야 함
        self.assertContains(response, "이전 분석 결과를 보여드립니다")  # 재분석이 실패했다는 안내도 있어야 함
        self.assertContains(response, "재분석 실패 문구")  # 실패 이유도 함께

    def test_failed_without_previous_shows_error(self):
        Analysis.objects.filter(pk=self.analysis.pk).update(
            status=Analysis.STATUS_FAILED, error_message="첫 분석 실패 문구",
        )
        response = self.client.get(self.url)

        self.assertContains(response, "분석에 실패했습니다")  # 보여줄 이전 결과가 없으니 실패 화면
        self.assertNotContains(response, "AI 스타일 분석 결과")  # 결과 제목은 나오면 안 됨
