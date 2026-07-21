from django.test import TestCase  # 일반 Django 뷰 테스트용 (DRF APITestCase 아님)
from django.contrib.auth import get_user_model  # 커스텀 User 모델을 안전하게 가져오는 표준 방법
from posts.models import Post  # 마이페이지 테스트에서 게시물을 직접 만들어봐야 하니까


User = get_user_model()  # accounts.User를 "User"라는 이름으로 사용

#회원가입 페이지 테스트 코드 
class SignupPageTests(TestCase):  # 회원가입 페이지 테스트 클래스
    def test_get_shows_signup_form(self):  # 페이지 열었을 때 폼이 잘 보이는지
        response = self.client.get("/signup/")  # GET으로 회원가입 페이지 요청
        self.assertEqual(response.status_code, 200)  # 정상적으로 페이지가 떠야 함

    def test_valid_signup_creates_user_and_redirects_to_login(self):  # 정상 가입 케이스
        response = self.client.post("/signup/", {
            "username": "newuser",                  # 새로 만들 아이디
            "password1": "verystrongpassword123",   # 비밀번호
            "password2": "verystrongpassword123",   # 비밀번호 확인 (1과 동일해야 통과)
        })
        self.assertEqual(response.status_code, 302)          # 성공하면 리다이렉트(302)여야 함
        self.assertRedirects(response, "/login/")              # 그 리다이렉트 목적지가 로그인 페이지인지까지 확인
        self.assertTrue(User.objects.filter(username="newuser").exists())  # 실제로 DB에 유저가 생겼는지 확인

    def test_password_mismatch_does_not_create_user(self):  # 비밀번호 확인이 안 맞는 케이스
        response = self.client.post("/signup/", {
            "username": "newuser",
            "password1": "verystrongpassword123",
            "password2": "differentpassword456",  # 일부러 다르게 입력
        })
        self.assertEqual(response.status_code, 200)  # 실패하면 리다이렉트 없이 폼을 다시 보여줘야 함 (200)
        self.assertFalse(User.objects.filter(username="newuser").exists())  # DB에 유저가 생기면 안 됨

    def test_duplicate_username_does_not_create_user(self):  # 이미 있는 아이디로 가입 시도하는 케이스
        User.objects.create_user(username="existing", password="testpass123")  # 미리 유저 하나를 DB에 만들어둠

        response = self.client.post("/signup/", {
            "username": "existing",              # 위에서 이미 만든 아이디와 동일하게 시도
            "password1": "anotherpassword123",
            "password2": "anotherpassword123",
        })
        self.assertEqual(response.status_code, 200)  # 중복 아이디는 거부되어 폼이 다시 뜸 (200)
        self.assertEqual(User.objects.filter(username="existing").count(), 1)  # 유저가 2개로 늘어나지 않고 1개 그대로여야 함

    def test_authenticated_user_redirected_away_from_signup(self):  # 이미 로그인한 유저가 회원가입 페이지 접근 시
        self.client.force_login(User.objects.create_user(username="loggedin", password="testpass123"))  # 유저 만들고 바로 세션에 로그인 처리
        response = self.client.get("/signup/")  # 로그인된 상태로 회원가입 페이지 요청
        self.assertRedirects(response, "/")  # 피드(루트 경로)로 리다이렉트되어야 함


# 로그인 페이지 테스트 코드 
class LoginPageTests(TestCase):  # 로그인 페이지 테스트 클래스
    def setUp(self):  # 이 클래스의 모든 테스트가 실행되기 전마다 호출됨
        self.user = User.objects.create_user(username="testuser", password="testpass123")  # 로그인 시도할 유저를 미리 만들어둠

    def test_get_shows_login_form(self):  # 페이지 열었을 때 폼이 잘 보이는지
        response = self.client.get("/login/")  # GET으로 로그인 페이지 요청
        self.assertEqual(response.status_code, 200)  # 정상적으로 페이지가 떠야 함

    def test_valid_login_redirects_and_authenticates(self):  # 정상 로그인 케이스
        response = self.client.post("/login/", {
            "username": "testuser",
            "password": "testpass123",
        }, follow=True)  # follow=True: 리다이렉트된 곳까지 실제로 따라가서 그 페이지 응답까지 받아옴

        self.assertRedirects(response, "/")  # 최종적으로 피드(루트)에 도착했는지 확인
        self.assertTrue(response.context["user"].is_authenticated)  # 도착한 페이지 기준으로 실제 로그인된 상태인지 확인

    def test_invalid_password_does_not_authenticate(self):  # 비밀번호가 틀린 케이스
        response = self.client.post("/login/", {
            "username": "testuser",
            "password": "wrongpassword",
        })
        self.assertEqual(response.status_code, 200)  # 실패하면 리다이렉트 없이 폼을 다시 보여줌
        self.assertFalse(response.context["user"].is_authenticated)  # 여전히 비로그인 상태여야 함

    def test_authenticated_user_redirected_away_from_login(self):  # 이미 로그인한 유저가 로그인 페이지 접근 시
        self.client.force_login(self.user)  # 세션에 바로 로그인 처리
        response = self.client.get("/login/")  # 로그인된 상태로 로그인 페이지 요청
        self.assertRedirects(response, "/")  # 피드로 리다이렉트되어야 함

#로그아웃 테스트 코드 
class LogoutViewTests(TestCase):  # 로그아웃 뷰 테스트 클래스
    def setUp(self):
        self.user = User.objects.create_user(username="testuser", password="testpass123")  # 로그아웃 시도할 유저를 미리 만들어둠

    def test_post_logs_out_and_redirects(self):  # 정상 로그아웃 케이스
        self.client.force_login(self.user)  # 먼저 로그인 상태로 만들어둠

        response = self.client.post("/logout/", follow=True)  # POST로 로그아웃 요청, 리다이렉트까지 따라감
        self.assertRedirects(response, "/")  # 피드로 리다이렉트되는지 확인
        self.assertFalse(response.context["user"].is_authenticated)  # 도착한 페이지 기준으로 비로그인 상태가 됐는지 확인

    def test_get_is_not_allowed_and_keeps_user_logged_in(self):  # GET으로 접근하면 막히는지 확인
        self.client.force_login(self.user)  # 먼저 로그인 상태로 만들어둠

        response = self.client.get("/logout/")  # GET으로 로그아웃 시도
        self.assertEqual(response.status_code, 405)  # @require_POST가 막아서 405여야 함
        self.assertIn("_auth_user_id", self.client.session)  # 세션에 로그인 정보가 그대로 남아있는지 확인 (로그아웃 안 됐어야 함)

class MypageTests(TestCase):  # 마이페이지 테스트 클래스
    def setUp(self):
        self.user = User.objects.create_user(username="testuser", password="testpass123")  # 마이페이지 주인
        self.other_user = User.objects.create_user(username="otheruser", password="testpass123")  # "남"의 역할

    def test_requires_login(self):  # 비로그인 유저가 마이페이지에 접근하는 케이스
        response = self.client.get("/mypage/")  # 로그인 없이 요청
        self.assertRedirects(response, "/login/?next=/mypage/")  # 로그인 페이지로 리다이렉트되어야 함

    def test_shows_only_my_posts(self):  # 내 게시물만 보이고 남의 게시물은 안 보이는지
        Post.objects.create(user=self.user, image="posts/mine.jpg", caption="내 게시물")  # 내 게시물 하나
        Post.objects.create(user=self.other_user, image="posts/theirs.jpg", caption="남의 게시물")  # 남의 게시물 하나

        self.client.force_login(self.user)  # 마이페이지 주인으로 로그인 처리
        response = self.client.get("/mypage/")  # 마이페이지 요청

        self.assertEqual(response.status_code, 200)  # 정상적으로 페이지가 떠야 함
        self.assertEqual(list(response.context["posts"]), [Post.objects.get(user=self.user)])  # 화면에 넘어간 게시물 목록이 "내 게시물"만 딱 1개여야 함