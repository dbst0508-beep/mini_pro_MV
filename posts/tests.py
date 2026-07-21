from django.contrib.auth import get_user_model  # 커스텀 User 모델을 안전하게 가져오는 표준 방법
from rest_framework import status                # 200, 201, 403 같은 상태 코드를 이름으로 다루기 위함
from rest_framework.test import APITestCase       # DRF API 테스트 전용 도구

from .models import Post,Comment

User = get_user_model()  # accounts.User 모델을 "User"라는 이름으로 사용


class PostsAPITestCase(APITestCase):
    # 이 클래스를 상속받는 모든 테스트 클래스에서 공통으로 쓸 준비물을 만듦
    def setUp(self):
        # 테스트 메서드 하나가 실행되기 "직전"마다 자동으로 호출되는 특별한 메서드
        self.user = User.objects.create_user(username="user1", password="testpass123")       # 댓글/좋아요를 직접 누를 유저
        self.other_user = User.objects.create_user(username="user2", password="testpass123")  # "남"의 역할을 할 유저 (권한 테스트용)
        self.post = Post.objects.create(user=self.user, image="posts/test.jpg", caption="테스트 게시물")  # 댓글/좋아요를 달 대상 게시물

#좋아요 기능 테스트 코드 
class LikeToggleAPIViewTests(PostsAPITestCase):
    # 클래스 이름 뒤 괄호에 PostsAPITestCase를 써주면, 1단계에서 만든 setUp()이 여기도 그대로 적용됨
    # (self.user, self.other_user, self.post를 이 클래스의 테스트에서도 바로 쓸 수 있음)

    def test_authenticated_user_can_toggle_like(self):
        self.client.force_authenticate(user=self.user)  # 이 클라이언트가 보내는 요청은 self.user로 로그인된 것처럼 처리됨

        url = f"/api/posts/{self.post.id}/like/"  # 좋아요 토글 API 주소

        # 첫 번째 요청: 좋아요를 처음 누르는 상황
        response = self.client.post(url)
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)  # 새로 생성됐으니 201이어야 함
        self.assertTrue(response.data["liked"])                          # 응답의 liked 값이 True여야 함
        self.assertEqual(response.data["like_count"], 1)                 # 좋아요 개수가 1이어야 함

        # 두 번째 요청: 같은 걸 또 누르면 "취소" 동작이어야 함
        response = self.client.post(url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)  # 취소는 200이어야 함
        self.assertFalse(response.data["liked"])                     # liked 값이 False여야 함
        self.assertEqual(response.data["like_count"], 0)              # 다시 0개여야 함

    def test_unauthenticated_user_cannot_like(self):
        url = f"/api/posts/{self.post.id}/like/"  # 로그인 없이 같은 주소에 요청

        response = self.client.post(url)
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)  # 인증 안 됐으니 401이어야 함

#댓글 기능 테스트 코드 
class CommentListCreateAPIViewTests(PostsAPITestCase):
    def test_list_comments(self):
        Comment.objects.create(post=self.post, user=self.user, content="첫 댓글")  # 미리 댓글 하나를 DB에 직접 만들어둠

        url = f"/api/posts/{self.post.id}/comments/"
        response = self.client.get(url)  # 로그인 없이 조회 (IsAuthenticatedOrReadOnly라 조회는 누구나 가능해야 함)

        self.assertEqual(response.status_code, status.HTTP_200_OK)      # 조회는 200이어야 함
        self.assertEqual(len(response.data), 1)                          # 댓글이 정확히 1개 나와야 함
        self.assertEqual(response.data[0]["content"], "첫 댓글")           # 그 내용이 방금 만든 것과 같아야 함

    def test_authenticated_user_can_create_comment(self): 
        self.client.force_authenticate(user=self.user)
        url = f"/api/posts/{self.post.id}/comments/"

        response = self.client.post(url, {"content": "새 댓글"})  # content 값을 실어서 POST
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)  # 생성 성공은 201이어야 함
        self.assertEqual(Comment.objects.count(), 1)                      # 실제로 DB에 1개 저장됐는지 확인

    def test_blank_comment_is_rejected(self):
        self.client.force_authenticate(user=self.user)
        url = f"/api/posts/{self.post.id}/comments/"

        response = self.client.post(url, {"content": "   "})  # 공백만 있는 내용
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)  # 거부되어 400이어야 함
        self.assertEqual(Comment.objects.count(), 0)                          # 저장된 게 하나도 없어야 함

    def test_unauthenticated_user_cannot_create_comment(self):
        url = f"/api/posts/{self.post.id}/comments/"

        response = self.client.post(url, {"content": "댓글"})  # 로그인 없이 작성 시도
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)  # 인증 없으니 401이어야 함

#댓글 수정/삭제 테스트 코드 
class CommentDetailAPIViewTests(PostsAPITestCase):  # 댓글 상세(조회/수정/삭제) API를 테스트할 클래스
    def setUp(self):  # 이 클래스의 테스트가 실행되기 전마다 호출됨
        super().setUp()  # 부모 클래스(PostsAPITestCase)의 setUp을 먼저 실행 -> self.user, self.other_user, self.post 준비
        self.comment = Comment.objects.create(post=self.post, user=self.user, content="원본 댓글")  # 수정/삭제 대상이 될 댓글을 미리 만듦
        self.url = f"/api/posts/{self.post.id}/comments/{self.comment.id}/"  # 조회/수정/삭제가 전부 같은 주소를 쓰므로 미리 변수로 저장

    def test_owner_can_update_comment(self):  # 작성자 본인이 댓글을 수정하는 정상 케이스
        self.client.force_authenticate(user=self.user)  # 댓글 작성자 본인으로 로그인한 것처럼 처리

        response = self.client.patch(self.url, {"content": "수정된 댓글"})  # PATCH는 전체가 아닌 일부 필드만 바꾸는 요청
        self.assertEqual(response.status_code, status.HTTP_200_OK)  # 수정 성공은 200이어야 함
        self.assertEqual(response.data["content"], "수정된 댓글")  # 응답에 바뀐 내용이 그대로 실려와야 함

        self.comment.refresh_from_db()  # self.comment는 setUp 때 만든 "옛날" 값이라 DB 최신 값으로 다시 채워줌
        self.assertEqual(self.comment.content, "수정된 댓글")  # DB에도 실제로 반영됐는지 확인

    def test_owner_can_delete_comment(self):  # 작성자 본인이 댓글을 삭제하는 정상 케이스
        self.client.force_authenticate(user=self.user)  # 댓글 작성자 본인으로 로그인

        response = self.client.delete(self.url)  # 삭제 요청
        self.assertEqual(response.status_code, status.HTTP_204_NO_CONTENT)  # 삭제 성공은 관례상 204(본문 없음)여야 함
        self.assertEqual(Comment.objects.count(), 0)  # DB에서 실제로 사라졌는지 확인

    def test_non_owner_cannot_update_comment(self):  # 남의 댓글을 수정하려는 케이스
        self.client.force_authenticate(user=self.other_user)  # 댓글 작성자가 아닌 다른 유저로 로그인

        response = self.client.patch(self.url, {"content": "남이 수정 시도"})  # 남의 댓글 수정 시도
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)  # IsOwnerOrReadOnly가 막아서 403이어야 함

        self.comment.refresh_from_db()  # DB 최신 상태 다시 불러오기
        self.assertEqual(self.comment.content, "원본 댓글")  # 거부됐으니 내용이 바뀌지 않고 그대로여야 함

    def test_non_owner_cannot_delete_comment(self):  # 남의 댓글을 삭제하려는 케이스
        self.client.force_authenticate(user=self.other_user)  # 댓글 작성자가 아닌 다른 유저로 로그인

        response = self.client.delete(self.url)  # 남의 댓글 삭제 시도
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)  # IsOwnerOrReadOnly가 막아서 403이어야 함
        self.assertEqual(Comment.objects.count(), 1)  # 삭제되지 않고 그대로 1개 남아있어야 함

    def test_unauthenticated_user_cannot_update_comment(self):  # 로그인 없이 수정하려는 케이스
        response = self.client.patch(self.url, {"content": "비로그인 수정 시도"})  # 로그인 없이 수정 요청
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)  # 인증 자체가 안 됐으니 401 (403이 아님)

    def test_unauthenticated_user_cannot_delete_comment(self):  # 로그인 없이 삭제하려는 케이스
        response = self.client.delete(self.url)  # 로그인 없이 삭제 요청
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)  # 위와 동일하게 401이어야 함
        self.assertEqual(Comment.objects.count(), 1)  # 삭제되지 않고 그대로 1개 남아있어야 함